"""Project file + build.

The project lives in the mod package as `engine_project.json`. It records the paths, the patch choices, custom
skills and perks, behaviour/effect additions to existing types, and raw asm patches from the code browser.
Build = base library -> simple patches -> engine extension -> asm patches -> package `lib/arm64-v8a/`, plus the
json rows, stringtable entries and icons for custom skills/perks.
"""
import copy
import datetime
import json
import os
import shutil

from . import framework, gamedata, patches
from .elf import Elf
from .framework import Effect, ExtConfig, FeatureExt, SkillExt

PROJECT_FILE = "engine_project.json"
LIB_REL = os.path.join("lib", "arm64-v8a", "libworld-conqueror-4.so")

DEFAULT = {
    "version": 1,
    "paths": {"base_so": "", "assets": "", "backups": ""},
    "options": {"challenge": "tier12", "mf_picker": True, "engine_ext": True, "legacy_skins": True},
    "custom_skills": [],
    "skill_extras": {},
    "custom_perks": [],
    "perk_extras": {},
    "asm_patches": [],
}


def guess_paths(package):
    root = os.path.dirname(os.path.dirname(os.path.abspath(package)))
    cands = [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d, "assets")) and
             os.path.exists(os.path.join(root, d, LIB_REL))] if os.path.isdir(root) else []
    base = os.path.join(root, cands[0], LIB_REL) if cands else ""
    assets = os.path.join(root, cands[0], "assets") if cands else ""
    return {"base_so": base, "assets": assets, "backups": os.path.join(root, "backups")}


class Project:
    def __init__(self, package):
        self.package = os.path.abspath(package)
        self.path = os.path.join(self.package, PROJECT_FILE)
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                self.data = json.load(f)
            for k, v in DEFAULT.items():
                self.data.setdefault(k, copy.deepcopy(v))
            for k, v in DEFAULT["options"].items():
                self.data["options"].setdefault(k, v)
        else:
            self.data = copy.deepcopy(DEFAULT)
            self.data["paths"] = guess_paths(self.package)
        self._gd = None

    def save(self):
        with open(self.path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)

    @property
    def gd(self):
        if self._gd is None:
            self._gd = gamedata.GameData(self.data["paths"]["assets"], self.package)
        return self._gd

    def backup_dir(self):
        b = self.data["paths"].get("backups") or os.path.join(os.path.dirname(os.path.dirname(self.package)),
                                                                 "backups")
        return os.path.join(b, datetime.date.today().isoformat() + "_engine_editor")

    # ------------------------------------------------------------------ framework config
    def ext_config(self):
        d = self.data
        skills = []
        for s in d["custom_skills"]:
            skills.append(SkillExt(int(s["type"]), [int(b) for b in s.get("bases", [])],
                                   [Effect.from_dict(e) for e in s.get("effects", [])], True))
        for t, x in d["skill_extras"].items():
            if x.get("also") or x.get("effects"):
                skills.append(SkillExt(int(t), [int(b) for b in x.get("also", [])],
                                       [Effect.from_dict(e) for e in x.get("effects", [])], False))
        feats = []
        for p in d["custom_perks"]:
            feats.append(FeatureExt(int(p["type"]), int(p.get("base", 0) or 0),
                                    [Effect.from_dict(e) for e in p.get("effects", [])]))
        for t, x in d["perk_extras"].items():
            if x.get("effects"):
                feats.append(FeatureExt(int(t), 0, [Effect.from_dict(e) for e in x["effects"]]))
        o = d["options"]
        return ExtConfig(skills, feats, bool(o.get("legacy_skins", True)), o.get("challenge") == "tier12")

    # ------------------------------------------------------------------ library
    def base_elf(self):
        p = self.data["paths"]["base_so"]
        if not p or not os.path.exists(p):
            raise FileNotFoundError("base library not found: %r (set it on the Overview page)" % p)
        return Elf.load(p)

    def build_library(self, log=print):
        elf = self.base_elf()
        info = patches.detect(elf)
        if info["grown"] or info["engine_ext"] != "none":
            raise ValueError("the base library already contains an engine extension; pick the APK's original "
                             "libworld-conqueror-4.so as base")
        if not info["is_base"]:
            log("note: base SHA-1 %s is not the known APK library; every patch site is still verified"
                % info["sha1"][:12])
        o = self.data["options"]
        challenge = o.get("challenge", "removed")
        if challenge == "tier12" and not o.get("engine_ext", True):
            challenge = "removed"
        patches.apply_simple(elf, challenge, bool(o.get("mf_picker", True)), log)
        ext = None
        if o.get("engine_ext", True):
            ext = framework.apply(elf, self.ext_config(), log)
        patches.apply_asm_patches(elf, self.data["asm_patches"], log)
        return elf, ext

    # ------------------------------------------------------------------ game data for custom types
    def skill_ids(self, s):
        base = int(s.get("id_base") or 10000 + int(s["type"]) * 10)
        return [base + i + 1 for i in range(len(s["levels"]))]

    def perk_ids(self, p):
        base = int(p.get("id_base") or 400000 + int(p["type"]) * 10)
        return [base + i + 1 for i in range(len(p["levels"]))]

    def write_skill_rows(self, log=print):
        gd = self.gd
        rows = gd.rows("SkillSettings")
        custom_types = {int(s["type"]) for s in self.data["custom_skills"]}
        managed = set(self.data.get("_managed_skill_types", [])) | custom_types
        keep = [r for r in rows if r.get("Type") not in managed]
        removed = len(rows) - len(keep)
        new_rows = []
        for s in self.data["custom_skills"]:
            ids = self.skill_ids(s)
            for i, (lv, rid) in enumerate(zip(s["levels"], ids)):
                new_rows.append({
                    "Id": rid, "Name": s.get("names", {}).get("cn") or s.get("names", {}).get("en", ""),
                    "Level": i + 1, "Type": int(s["type"]), "Series": int(s.get("series", 0)),
                    "ActivatesChance": int(lv.get("chance", 100)), "IfPercent": int(s.get("if_percent", 0)),
                    "SkillEffect": int(lv.get("effect", 0)),
                    "UpgradeId": ids[i + 1] if i + 1 < len(ids) else 0,
                    "CostMedal": int(lv.get("cost", 0)), "OpenDefault": int(s.get("open_default", 0)),
                    "NeedStageId": 0, "NeedScenarioId": 0, "Score": int(lv.get("score", lv.get("cost", 0))),
                    "ArmyBuff": int(s.get("army_buff", 0)), "AurasRange": int(s.get("auras_range", 0))})
        clash = {r["Id"] for r in keep} & {r["Id"] for r in new_rows}
        if clash:
            raise ValueError("custom skill Ids already used: %s" % sorted(clash)[:10])
        rows[:] = keep + new_rows
        gd.mark("SkillSettings")
        self.data["_managed_skill_types"] = sorted(custom_types)
        for s in self.data["custom_skills"]:
            t = int(s["type"])
            for lang in gamedata.LANGS:
                n = s.get("names", {}).get(lang) or s.get("names", {}).get("en")
                dsc = s.get("descs", {}).get(lang) or s.get("descs", {}).get("en")
                if n:
                    gd.set_text(lang, "skill_name_%d" % t, n)
                if dsc:
                    gd.set_text(lang, "skill_info_%d" % t, dsc)
        log("SkillSettings: %d custom rows (%d old rows replaced)" % (len(new_rows), removed))

    def write_perk_rows(self, log=print):
        gd = self.gd
        rows = gd.rows("ArmyFeatureSettings")
        custom_types = {int(p["type"]) for p in self.data["custom_perks"]}
        managed = set(self.data.get("_managed_perk_types", [])) | custom_types
        keep = [r for r in rows if r.get("Type") not in managed]
        new_rows = []
        for p in self.data["custom_perks"]:
            for i, (lv, rid) in enumerate(zip(p["levels"], self.perk_ids(p))):
                new_rows.append({
                    "Id": rid, "Name": p.get("names", {}).get("cn") or p.get("names", {}).get("en", ""),
                    "Type": int(p["type"]), "Level": i + 1,
                    "ActivatesChance": int(lv.get("chance", 100)), "FeatureEffect": int(lv.get("effect", 0)),
                    "SecondEffect": int(lv.get("second", 0)),
                    "AgainstArmy": [int(x) for x in lv.get("against", [])],
                    "RelatedArmyId": int(lv.get("related", 0)), "AntiairId": int(lv.get("antiair", 0)),
                    "Condition": int(lv.get("condition", 0)), "CD": int(lv.get("cd", 0)),
                    "Range": int(lv.get("range", 0)), "Round": int(lv.get("round", 0)),
                    "ArmyBuff": int(lv.get("buff", 0)), "ArmyBuffRound": int(lv.get("buff_round", 0)),
                    "Auras": int(lv.get("auras", 0))})
        clash = {r["Id"] for r in keep} & {r["Id"] for r in new_rows}
        if clash:
            raise ValueError("custom perk Ids already used: %s" % sorted(clash)[:10])
        rows[:] = keep + new_rows
        gd.mark("ArmyFeatureSettings")
        self.data["_managed_perk_types"] = sorted(custom_types)
        for p in self.data["custom_perks"]:
            t = int(p["type"])
            for lang in gamedata.LANGS:
                n = p.get("names", {}).get(lang) or p.get("names", {}).get("en")
                dsc = p.get("descs", {}).get(lang) or p.get("descs", {}).get("en")
                if n:
                    gd.set_text(lang, "feat_name_%d" % t, n)
                if dsc:
                    gd.set_text(lang, "feat_desc_%d" % t, dsc)
        # unit assignment: ArmySettings Feature / FeatureLevel lists
        units = gd.rows("ArmySettings")
        by_id = {u["Id"]: u for u in units}
        prev = {int(k): v for k, v in self.data.get("_managed_perk_units", {}).items()}
        changed = 0
        for t in managed:                          # drop previous assignments of managed types
            for uid in prev.get(t, []):
                u = by_id.get(uid)
                if u and t in u.get("Feature", []):
                    i = u["Feature"].index(t)
                    u["Feature"].pop(i)
                    if i < len(u.get("FeatureLevel", [])):
                        u["FeatureLevel"].pop(i)
                    changed += 1
        assigned = {}
        for p in self.data["custom_perks"]:
            t = int(p["type"])
            for a in p.get("units", []):
                u = by_id.get(int(a["id"]))
                if not u:
                    continue
                lvl = int(a.get("level", 1))
                feats, levels = u.setdefault("Feature", []), u.setdefault("FeatureLevel", [])
                if t in feats:
                    continue
                if lvl != 1 or levels:
                    while len(levels) < len(feats):
                        levels.append(1)
                    feats.append(t)
                    levels.append(lvl)
                else:
                    feats.append(t)
                assigned.setdefault(t, []).append(u["Id"])
                changed += 1
        if changed:
            gd.mark("ArmySettings")
        self.data["_managed_perk_units"] = {str(k): v for k, v in assigned.items()}
        log("ArmyFeatureSettings: %d custom rows; ArmySettings: %d feature list changes" % (len(new_rows), changed))

    def write_general_skills(self, log=print):
        """Custom skills given to generals (GeneralSettings.Skills, by skill Id)."""
        gd = self.gd
        gens = gd.rows("GeneralSettings")
        by_id = {g["Id"]: g for g in gens}
        prev = self.data.get("_managed_general_skills", {})
        changed = 0
        for gid, sids in prev.items():
            g = by_id.get(int(gid))
            if g:
                before = len(g.get("Skills") or [])
                g["Skills"] = [x for x in (g.get("Skills") or []) if x not in sids]
                changed += before - len(g["Skills"])
        given = {}
        for s in self.data["custom_skills"]:
            ids = self.skill_ids(s)
            for a in s.get("generals", []):
                g = by_id.get(int(a["id"]))
                if not g:
                    continue
                lvl = max(1, min(int(a.get("level", len(ids))), len(ids)))
                sid = ids[lvl - 1]
                g.setdefault("Skills", [])
                if g["Skills"] is None:
                    g["Skills"] = []
                if sid not in g["Skills"]:
                    g["Skills"].append(sid)
                    changed += 1
                given.setdefault(str(g["Id"]), []).append(sid)
        if changed:
            gd.mark("GeneralSettings")
        self.data["_managed_general_skills"] = given
        log("GeneralSettings: %d skill list changes" % changed)

    def write_icons(self, log=print):
        gd = self.gd
        bdir = self.backup_dir()
        n = 0
        for s in self.data["custom_skills"]:
            ic = s.get("icon") or {}
            t = int(s["type"])
            if ic.get("png_b64"):
                import base64
                gamedata.write_skill_icon(gd, t, src_png=base64.b64decode(ic["png_b64"]), backup_dir=bdir)
                n += 1
            elif ic.get("from_type") is not None:
                gamedata.write_skill_icon(gd, t, from_type=int(ic["from_type"]), backup_dir=bdir)
                n += 1
        if self.data["custom_perks"]:
            atlas = gamedata.FeatAtlas(gd)
            for p in self.data["custom_perks"]:
                t = int(p["type"])
                ic = p.get("icon") or {}
                for lv in range(1, len(p["levels"]) + 1):
                    if ic.get("png_b64"):
                        import base64
                        atlas.add(t, lv, png=base64.b64decode(ic["png_b64"]))
                    else:
                        src = int(ic.get("from_type") or p.get("base") or 1)
                        atlas.add(t, lv, from_type=src, from_level=min(lv, 4))
            atlas.save(bdir)
            n += 1
        log("icons: %d written" % n)

    # ------------------------------------------------------------------ full build
    def build(self, log=print, write_data=True):
        lines = []

        def L(msg):
            lines.append(msg)
            log(msg)
        elf, ext = self.build_library(L)
        dst = os.path.join(self.package, LIB_REL)
        bdir = self.backup_dir()
        if os.path.exists(dst):
            b = os.path.join(bdir, LIB_REL)
            if not os.path.exists(b):
                os.makedirs(os.path.dirname(b), exist_ok=True)
                shutil.copy2(dst, b)
                L("backed up previous library to %s" % b)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(bytes(elf.data))
        L("wrote %s (%d bytes, sha1 %s)" % (LIB_REL, len(elf.data), patches.sha1(elf.data)[:12]))
        if write_data:
            self.gd.reload()
            self.write_skill_rows(L)
            self.write_perk_rows(L)
            self.write_general_skills(L)
            self.gd.save(bdir, L)
            self.write_icons(L)
        self.save()
        self._changes(lines)
        return lines

    def _changes(self, lines):
        p = os.path.join(self.package, "CHANGES.txt")
        d = self.data
        out = ["", "Engine editor build %s:" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M")]
        o = d["options"]
        out.append("  options: challenge=%s, MF picker=%s, engine extension=%s"
                   % (o.get("challenge"), o.get("mf_picker"), o.get("engine_ext")))
        for s in d["custom_skills"]:
            out.append("  custom skill %s %s: bases %s, %d levels, %d effects"
                       % (s["type"], s.get("names", {}).get("en", ""), s.get("bases", []), len(s["levels"]),
                          len(s.get("effects", []))))
        for p_ in d["custom_perks"]:
            out.append("  custom perk %s %s: base %s, %d levels, %d effects, %d units"
                       % (p_["type"], p_.get("names", {}).get("en", ""), p_.get("base"), len(p_["levels"]),
                          len(p_.get("effects", [])), len(p_.get("units", []))))
        for t, x in d["skill_extras"].items():
            out.append("  skill %s extras: also %s, %d effects" % (t, x.get("also", []), len(x.get("effects", []))))
        for t, x in d["perk_extras"].items():
            out.append("  perk %s extras: %d effects" % (t, len(x.get("effects", []))))
        for a in d["asm_patches"]:
            out.append("  asm patch %s: %s (%s)" % (a["addr"], a.get("note", ""), a["hex"]))
        out.append("  (project file: engine_project.json; tool: ModdingStuff\\WC4EngineEditor)")
        body = "\n".join(out[2:])
        if d.get("_last_changes") == body:          # same content as the previous build: don't repeat it
            return
        d["_last_changes"] = body
        self.save()
        with open(p, "a", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(out) + "\n")
