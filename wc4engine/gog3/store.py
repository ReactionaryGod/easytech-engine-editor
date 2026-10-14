"""Glory of Generals 3 data model: skills, perks, buffs and conditions.

Every operation writes straight into the mod package (json / stringtables / config / images), with the first
pre-edit version of each file copied to the backups folder. There is no separate "unbuilt" state for this data.

Model (all verified against libiron.so and the shipped json):
  SkillSettings  one row per skill LEVEL: Id, Name, Type (skill), Level, ArmyType, BuffId
  ArmyFeatureSettings  one row per perk: Id, BuffId[], PicName
  BuffSettings   Id, Condition, PR, Type, Key, Value, BuffId (chained), Range, Round, EffectId
  GeneralSettings.Skills  skill row Ids; ArmySettings.Feature  perk Ids
  texts: skill_<Id> / skill_desc_<Id>, feat_name_<Id> / feat_desc_<Id>
  icons: skill_<Id>.png (image/image_skill.xml), army_feature<Id>.png (image/image_ui2.xml)
"""
import io
import os

from .. import gamedata
from ..atlas import NamedAtlas
from . import conditions as cond

LANGS = ["en", "cn", "tw", "ja", "ko"]
LANG_NAMES = {"en": "English", "cn": "Chinese (simplified)", "tw": "Chinese (traditional)", "ja": "Japanese",
              "ko": "Korean"}
NEW_BUFF_BASE = 7001
CUSTOM_ATLAS = "image_custom"           # new icons live here, registered in image_resource.xml


class Gog3Store:
    def __init__(self, assets_dir, package_dir, backup_dir):
        self.gd = gamedata.GameData(assets_dir, package_dir, strings_in_assets=True, langs=LANGS)
        self.backup_dir = backup_dir
        self._atlas = None

    # ------------------------------------------------------------------ plumbing
    def _save(self):
        self.gd.save(self.backup_dir, log=lambda *_: None)

    def rows(self, name):
        return self.gd.rows(name)

    def text(self, key, lang="en"):
        return self.gd.text(key, lang)

    def texts(self, prefix, rid):
        return {l: self.gd.text("%s%d" % (prefix, rid), l) for l in LANGS}

    def _set_texts(self, prefix, rid, by_lang):
        for lang in LANGS:
            v = by_lang.get(lang)
            if v is not None and v != "":
                self.gd.set_text(lang, "%s%d" % (prefix, rid), v)
            elif v == "" and self.gd.text("%s%d" % (prefix, rid), lang):
                self.gd.delete_text(lang, "%s%d" % (prefix, rid))

    def _next_id(self, rows, start):
        used = {r["Id"] for r in rows}
        i = max(start, max(used, default=0) + 1)
        return i

    # ------------------------------------------------------------------ buffs
    def buff_map(self):
        return {b["Id"]: b for b in self.rows("BuffSettings")}

    def buff_summary(self, bid):
        b = self.buff_map().get(bid)
        if not b:
            return "buff %s (missing)" % bid
        from . import buff_types
        s = "%s %s" % (buff_types.label_of(b["Type"]), b["Value"])
        if b["PR"] != 100:
            s += " @%d%%" % b["PR"]
        if b["BuffId"]:
            s += " -> %d" % b["BuffId"]
        return s

    def buff_usage(self, bid):
        """What references this buff: skills, perks, and buffs that chain to it."""
        out = []
        for s in self.rows("SkillSettings"):
            if s["BuffId"] == bid:
                out.append(("skill", s["Id"], self.text("skill_%d" % s["Id"]) or s["Name"]))
        for f in self.rows("ArmyFeatureSettings"):
            if bid in f["BuffId"]:
                out.append(("perk", f["Id"], self.text("feat_name_%d" % f["Id"])))
        for b in self.rows("BuffSettings"):
            if b["BuffId"] == bid:
                out.append(("buff", b["Id"], "chains to it"))
        return out

    def save_buff(self, row, create=False):
        rows = self.rows("BuffSettings")
        clean = {k: int(row[k]) for k in ("Id", "Condition", "PR", "Type", "Key", "Value", "BuffId", "Range",
                                          "Round", "EffectId")}
        if clean["BuffId"] and clean["BuffId"] not in self.buff_map():
            raise ValueError("chained buff %d does not exist" % clean["BuffId"])
        if clean["BuffId"] == clean["Id"]:
            raise ValueError("a buff cannot chain to itself")
        if not 0 <= clean["PR"] <= 100:
            raise ValueError("PR (chance) must be 0-100")
        known = {c["id"] for c in self.conditions()}
        if clean["Condition"] and clean["Condition"] not in known:
            raise ValueError("condition %d is not defined in def_buff.xml" % clean["Condition"])
        existing = next((r for r in rows if r["Id"] == clean["Id"]), None)
        if existing and create:
            raise ValueError("buff Id %d already exists" % clean["Id"])
        if existing:
            existing.update(clean)
        else:
            rows.append(clean)
        self.gd.mark("BuffSettings")
        self._save()
        return clean["Id"]

    def new_buff_id(self):
        return self._next_id(self.rows("BuffSettings"), NEW_BUFF_BASE)

    def delete_buff(self, bid):
        use = [u for u in self.buff_usage(bid)]
        if use:
            raise ValueError("buff %d is still used by %s" % (bid, ", ".join("%s %s" % (k, i) for k, i, _ in use[:6])))
        rows = self.rows("BuffSettings")
        rows[:] = [r for r in rows if r["Id"] != bid]
        self.gd.mark("BuffSettings")
        self._save()

    # ------------------------------------------------------------------ skills
    def skill_groups(self):
        by = {}
        for s in self.rows("SkillSettings"):
            by.setdefault(s["Type"], []).append(s)
        gen_use = {}
        for g in self.rows("GeneralSettings"):
            for sid in g.get("Skills") or []:
                gen_use[sid] = gen_use.get(sid, 0) + 1
        out = []
        for t in sorted(by):
            rows = sorted(by[t], key=lambda r: r["Level"])
            out.append(dict(type=t, name=self.text("skill_%d" % rows[0]["Id"]) or rows[0]["Name"],
                            cn=rows[0]["Name"], levels=len(rows), ids=[r["Id"] for r in rows],
                            generals=sum(gen_use.get(r["Id"], 0) for r in rows)))
        return out

    def skill_detail(self, type_):
        rows = sorted([r for r in self.rows("SkillSettings") if r["Type"] == type_], key=lambda r: r["Level"])
        return dict(type=type_, rows=[dict(r, names=self.texts("skill_", r["Id"]), descs=self.texts("skill_desc_", r["Id"]),
                                           summary=self.buff_summary(r["BuffId"])) for r in rows])

    def new_skill_type(self):
        return max((r["Type"] for r in self.rows("SkillSettings")), default=0) + 1

    def save_skill(self, spec):
        """spec: {type, rows:[{id|None, level, armytype, buff, name (cn), names{}, descs{}}]}.
        Rows missing from the spec are deleted (and removed from generals)."""
        t = int(spec["type"])
        rows = self.rows("SkillSettings")
        keep = set()
        for r in spec["rows"]:
            buff = int(r["buff"])
            if buff and buff not in self.buff_map():
                raise ValueError("buff %d does not exist" % buff)
        for r in spec["rows"]:
            rid = r.get("id")
            row = next((x for x in rows if x["Id"] == rid), None) if rid else None
            if row is None:
                rid = self._next_id(rows, 1)
                row = {"Id": rid, "Name": "", "Type": t, "Level": 1, "ArmyType": 0, "BuffId": 0}
                rows.append(row)
            row.update(Name=r.get("name") or row["Name"] or (r.get("names", {}).get("en") or "skill"), Type=t,
                       Level=int(r["level"]), ArmyType=int(r["armytype"]), BuffId=int(r["buff"]))
            keep.add(rid)
            self._set_texts("skill_", rid, r.get("names", {}))
            self._set_texts("skill_desc_", rid, r.get("descs", {}))
            r["id"] = rid
        gone = [x["Id"] for x in rows if x["Type"] == t and x["Id"] not in keep]
        for gid in gone:
            self._drop_skill_row(gid)
        self.gd.mark("SkillSettings")
        self._save()
        return [r["id"] for r in spec["rows"]]

    def _drop_skill_row(self, rid):
        rows = self.rows("SkillSettings")
        rows[:] = [x for x in rows if x["Id"] != rid]
        for g in self.rows("GeneralSettings"):
            if rid in (g.get("Skills") or []):
                g["Skills"] = [s for s in g["Skills"] if s != rid]
                self.gd.mark("GeneralSettings")
        for lang in LANGS:
            self.gd.delete_text(lang, "skill_%d" % rid)
            self.gd.delete_text(lang, "skill_desc_%d" % rid)

    def delete_skill(self, type_):
        for r in [r for r in self.rows("SkillSettings") if r["Type"] == type_]:
            self._drop_skill_row(r["Id"])
        self.gd.mark("SkillSettings")
        self._save()

    def generals_with(self, ids):
        out = []
        for g in self.rows("GeneralSettings"):
            have = [i for i in (g.get("Skills") or []) if i in ids]
            if have:
                out.append(dict(id=g["Id"], name=g.get("Ename") or g.get("Name"), rows=have))
        return out

    def general_list(self):
        return [dict(id=g["Id"], name=g.get("Ename") or g.get("Name"), skills=len(g.get("Skills") or []))
                for g in self.rows("GeneralSettings")]

    def set_general_skill(self, general_id, row_id, give, drop_group=None):
        g = next(x for x in self.rows("GeneralSettings") if x["Id"] == general_id)
        skills = g.setdefault("Skills", [])
        if drop_group:
            skills[:] = [s for s in skills if s not in drop_group]
        if give and row_id not in skills:
            skills.append(row_id)
        if not give and row_id in skills:
            skills.remove(row_id)
        self.gd.mark("GeneralSettings")
        self._save()

    # ------------------------------------------------------------------ perks
    def perk_list(self):
        use = {}
        for u in self.rows("ArmySettings"):
            for f in u.get("Feature") or []:
                use[f] = use.get(f, 0) + 1
        return [dict(id=f["Id"], name=self.text("feat_name_%d" % f["Id"]) or "perk %d" % f["Id"], buffs=f["BuffId"],
                     units=use.get(f["Id"], 0)) for f in self.rows("ArmyFeatureSettings")]

    def perk_detail(self, pid):
        f = next(x for x in self.rows("ArmyFeatureSettings") if x["Id"] == pid)
        units = [dict(id=u["Id"], name=self.text("army_%d" % u["Id"]) or u["Name"], type=u["Type"])
                 for u in self.rows("ArmySettings") if pid in (u.get("Feature") or [])]
        return dict(id=pid, buffs=list(f["BuffId"]), pic=f.get("PicName"), names=self.texts("feat_name_", pid),
                    descs=self.texts("feat_desc_", pid), units=units,
                    summaries=[self.buff_summary(b) for b in f["BuffId"]])

    def new_perk_id(self):
        return self._next_id(self.rows("ArmyFeatureSettings"), 1)

    def save_perk(self, spec):
        pid = spec.get("id") or self.new_perk_id()
        rows = self.rows("ArmyFeatureSettings")
        bm = self.buff_map()
        for b in spec["buffs"]:
            if int(b) not in bm:
                raise ValueError("buff %s does not exist" % b)
        row = next((r for r in rows if r["Id"] == pid), None)
        if row is None:
            row = {"Id": pid, "BuffId": [], "PicName": None}
            rows.append(row)
        row["BuffId"] = [int(b) for b in spec["buffs"]]
        self._set_texts("feat_name_", pid, spec.get("names", {}))
        self._set_texts("feat_desc_", pid, spec.get("descs", {}))
        self.gd.mark("ArmyFeatureSettings")
        self._save()
        return pid

    def set_unit_perk(self, unit_id, perk_id, give):
        u = next(x for x in self.rows("ArmySettings") if x["Id"] == unit_id)
        feats = u.setdefault("Feature", [])
        if give and perk_id not in feats:
            feats.append(perk_id)
        if not give and perk_id in feats:
            feats.remove(perk_id)
        self.gd.mark("ArmySettings")
        self._save()

    def unit_list(self):
        return [dict(id=u["Id"], name=self.text("army_%d" % u["Id"]) or u["Name"], type=u["Type"])
                for u in self.rows("ArmySettings")]

    def delete_perk(self, pid):
        rows = self.rows("ArmyFeatureSettings")
        rows[:] = [r for r in rows if r["Id"] != pid]
        for u in self.rows("ArmySettings"):
            if pid in (u.get("Feature") or []):
                u["Feature"] = [f for f in u["Feature"] if f != pid]
                self.gd.mark("ArmySettings")
        for lang in LANGS:
            self.gd.delete_text(lang, "feat_name_%d" % pid)
            self.gd.delete_text(lang, "feat_desc_%d" % pid)
        self.gd.mark("ArmyFeatureSettings")
        self._save()

    # ------------------------------------------------------------------ conditions
    def _cond_path(self):
        return self.gd._pkg_asset("config/def_buff.xml")

    def _cond_text(self):
        p = self.gd.find_asset("config/def_buff.xml")
        with open(p, "rb") as f:
            raw = f.read()
        self._bom = raw.startswith(b"\xef\xbb\xbf")
        return raw[3:].decode("utf-8") if self._bom else raw.decode("utf-8")

    def conditions(self):
        text = self._cond_text()
        cs = cond.parse(text)
        by = {c["id"]: c for c in cs}
        for c in cs:
            c["english"] = cond.describe(c, by)
        return cs

    def save_custom_conditions(self, customs):
        """customs: list of condition dicts to keep in the editor block (replaces the block)."""
        ids = [c["id"] for c in customs]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate condition ids")
        text = self._cond_text()
        original = {c["id"] for c in cond.parse(text) if not c["custom"]}
        for c in customs:
            if c["id"] in original:
                raise ValueError("condition id %d is used by the original game" % c["id"])
            for k in c["children"]:
                if k not in original and k not in ids:
                    raise ValueError("condition %d refers to unknown condition %d" % (c["id"], k))
        new = cond.with_custom(text, customs)
        cond.parse(new)                                  # must stay well-formed
        dst = self._cond_path()
        gamedata._backup(dst, self.gd.package, self.backup_dir)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        data = new.encode("utf-8")
        with open(dst, "wb") as f:
            f.write((b"\xef\xbb\xbf" if self._bom else b"") + data)

    def next_condition_id(self):
        ids = [c["id"] for c in self.conditions()]
        return max(cond.CUSTOM_BASE, max(ids) + 1)

    # ------------------------------------------------------------------ icons
    def atlas(self):
        if self._atlas is None:
            self._atlas = NamedAtlas(self.gd, "image/%s.xml" % CUSTOM_ATLAS, "image/%s.png" % CUSTOM_ATLAS)
        return self._atlas

    def icon_png(self, kind, rid):
        """PNG bytes of a skill (kind='skill') or perk (kind='perk') icon, from the custom atlas or the game's."""
        name = ("skill_%d.png" if kind == "skill" else "army_feature%d.png") % rid
        png = self.atlas().png(name)
        if png:
            return png
        xml, img = ("image/image_skill.xml", "image/image_skill.png") if kind == "skill" else \
            ("image/image_ui2.xml", "image/image_ui2.png")
        return NamedAtlas(self.gd, xml, img, writable=False).png(name)

    def set_icon(self, kind, rid, png):
        name = ("skill_%d.png" if kind == "skill" else "army_feature%d.png") % rid
        size = (80, 80) if kind == "skill" else (60, 60)
        a = self.atlas()
        a.set(name, png, size)
        a.save(self.backup_dir)
        self._register_atlas()

    def _register_atlas(self):
        p = self.gd.find_asset("image_resource.xml")
        with open(p, "rb") as f:
            raw = f.read()
        text = raw.decode("utf-8")
        tag = '<file name="%s.xml"/>' % CUSTOM_ATLAS
        if tag in text:
            return
        i = text.index('<file name="image_skill.xml"/>')
        j = text.index("\n", i) + 1
        nl = "\r\n" if "\r\n" in text else "\n"
        text = text[:j] + "    " + tag + nl + text[j:]
        dst = self.gd._pkg_asset("image_resource.xml")
        gamedata._backup(dst, self.gd.package, self.backup_dir)
        with open(dst, "wb") as f:
            f.write(text.encode("utf-8"))
