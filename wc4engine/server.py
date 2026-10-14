"""Backend handlers shared by the UI: each takes (app, query, body) and returns plain data.

The Flet screens call them in-process through ui/backend.py; there is no network server."""
import base64
import json
import os
import re
import threading

from . import arm64, catalog, framework, gamedata, patches
from .analysis import Analysis
from .elf import Elf
from .project import Project

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache")


class ApiError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


class App:
    def __init__(self, package):
        self.lock = threading.RLock()
        self.project = Project(package)
        self._base = None          # (path, Elf, Analysis)
        self._built = None         # (key, Elf, Analysis, ext info)
        self._orig_types = None
        self.known_funcs = catalog.KNOWN_FUNCS

    # ------------------------------------------------------------------ libraries
    def base(self):
        p = self.project.data["paths"]["base_so"]
        if not self._base or self._base[0] != p:
            elf = self.project.base_elf()
            self._base = (p, elf, Analysis(elf, CACHE))
        return self._base

    def built(self):
        key = json.dumps([self.project.data["options"], self.project.data["custom_skills"],
                          self.project.data["custom_perks"], self.project.data["skill_extras"],
                          self.project.data["perk_extras"], self.project.data["asm_patches"]], sort_keys=True)
        if not self._built or self._built[0] != key:
            elf, ext = self.project.build_library(log=lambda *_: None)
            elf = Elf(bytes(elf.data))
            an = Analysis(elf, None)
            an.funcs = self.base()[2].funcs
            if ext:
                for name, a in ext["labels"].items():
                    an.names[a] = "ext." + name
            self._built = (key, elf, an, ext)
        return self._built

    def view(self, which):
        if which == "built":
            _, elf, an, _ = self.built()
            return elf, an
        _, elf, an = self.base()
        return elf, an

    def catalog(self):
        return catalog.build(self.base()[2])

    def original_types(self):
        """Skill / perk Types present in the extracted game (custom Types must avoid them)."""
        if self._orig_types is None:
            a = self.project.data["paths"]["assets"]
            with open(os.path.join(a, "json", "SkillSettings.json"), "rb") as f:
                s = {r["Type"] for r in gamedata.JsonTable(f.read()).rows}
            with open(os.path.join(a, "json", "ArmyFeatureSettings.json"), "rb") as f:
                p = {r["Type"] for r in gamedata.JsonTable(f.read()).rows}
            self._orig_types = (s, p)
        return self._orig_types

    # ------------------------------------------------------------------ helpers
    def gd(self):
        return self.project.gd

    def texts(self, prefix_name, prefix_desc, t):
        gd = self.gd()
        return ({l: gd.text("%s%d" % (prefix_name, t), l) for l in gamedata.LANGS},
                {l: gd.text("%s%d" % (prefix_desc, t), l) for l in gamedata.LANGS})


# ====================================================================== API handlers
def api_state(app, q, body):
    pr = app.project
    out = dict(package=pr.package, project=pr.data, project_exists=os.path.exists(pr.path),
               langs=gamedata.LANGS, lang_names=gamedata.LANG_NAMES,
               categories={k: dict(key=v[0], name=v[1], desc=v[2]) for k, v in framework.CATEGORIES.items()},
               unit_classes=framework.UNIT_CLASSES, challenge_states={k: v[1] for k, v in
                                                                         patches.CHALLENGE_STATES.items()},
               patch_info=patches.PATCH_INFO, max_type=framework.MAX_TYPE,
               skill_native=framework.SKILL_NATIVE, feat_native=framework.FEAT_NATIVE)
    try:
        _, elf, _ = app.base()
        out["base"] = patches.detect(elf)
        out["base"]["size"] = len(elf.data)
    except Exception as e:
        out["base_error"] = str(e)
    lib = os.path.join(pr.package, "lib", "arm64-v8a", "libworld-conqueror-4.so")
    if os.path.exists(lib):
        try:
            out["package_lib"] = patches.detect(Elf.load(lib))
            out["package_lib"]["size"] = os.path.getsize(lib)
        except Exception as e:
            out["package_lib"] = {"error": str(e)}
    return out


def api_save_project(app, q, body):
    pr = app.project
    for k in ("paths", "options"):
        if k in body:
            pr.data[k].update(body[k])
    if "paths" in body:
        pr._gd = None
        app._orig_types = None
    pr.save()
    return {"ok": True}


def _skill_rows_by_type(app):
    by = {}
    for r in app.gd().rows("SkillSettings"):
        by.setdefault(r["Type"], []).append(r)
    return by


def api_skills(app, q, body):
    gd = app.gd()
    by = _skill_rows_by_type(app)
    cat = app.catalog()["skill"]
    custom = {int(s["type"]): s for s in app.project.data["custom_skills"]}
    extras = app.project.data["skill_extras"]
    out = []
    for t in sorted(set(by) | set(custom)):
        rows = sorted(by.get(t, []), key=lambda r: r.get("Level", 0))
        c = custom.get(t)
        name = gd.text("skill_name_%d" % t) or (c and c.get("names", {}).get("en")) or (rows[0]["Name"] if rows else "")
        out.append(dict(type=t, name=name, cn=rows[0]["Name"] if rows else "", series=rows[0]["Series"] if rows else
                        (c or {}).get("series", 0), levels=len(rows) if not c else len(c["levels"]),
                        custom=bool(c), usage=len(cat.get(t, [])), extras=str(t) in extras,
                        sub=bool(rows) and rows[0]["Name"] and not gd.text("skill_name_%d" % t)))
    return {"skills": out}


def api_skill(app, q, body):
    t = int(q["type"][0])
    gd = app.gd()
    rows = sorted(_skill_rows_by_type(app).get(t, []), key=lambda r: r.get("Level", 0))
    names, descs = app.texts("skill_name_", "skill_info_", t)
    custom = next((s for s in app.project.data["custom_skills"] if int(s["type"]) == t), None)
    return dict(type=t, rows=rows, names=names, descs=descs, custom=custom,
                extras=app.project.data["skill_extras"].get(str(t)),
                usage=app.catalog()["skill"].get(t, []),
                original=t in app.original_types()[0])


def api_skill_rows(app, q, body):
    """Edit existing SkillSettings rows of one Type (values only)."""
    t = int(body["type"])
    if any(int(s["type"]) == t for s in app.project.data["custom_skills"]):
        raise ApiError("custom skills are edited in their own form")
    rows = {r["Id"]: r for r in app.gd().rows("SkillSettings") if r["Type"] == t}
    editable = {"ActivatesChance", "SkillEffect", "IfPercent", "CostMedal", "Score", "OpenDefault", "Series",
                "ArmyBuff", "AurasRange", "NeedStageId", "NeedScenarioId", "Name"}
    for ch in body["rows"]:
        r = rows.get(ch["Id"])
        if not r:
            continue
        for k, v in ch.items():
            if k in editable and k in r:
                r[k] = v if k == "Name" else int(v)
    app.gd().mark("SkillSettings")
    app.gd().save(app.project.backup_dir(), log=lambda *_: None)
    return {"ok": True}


def api_texts(app, q, body):
    kind = body["kind"]           # skill | perk
    t = int(body["type"])
    kn, kd = ("skill_name_%d", "skill_info_%d") if kind == "skill" else ("feat_name_%d", "feat_desc_%d")
    gd = app.gd()
    for lang, v in body.get("names", {}).items():
        if v is not None:
            gd.set_text(lang, kn % t, v)
    for lang, v in body.get("descs", {}).items():
        if v is not None:
            gd.set_text(lang, kd % t, v)
    gd.save(app.project.backup_dir(), log=lambda *_: None)
    return {"ok": True}


def api_extras(app, q, body):
    kind, t = body["kind"], str(int(body["type"]))
    key = "skill_extras" if kind == "skill" else "perk_extras"
    x = {"also": [int(v) for v in body.get("also", [])], "effects": body.get("effects", [])}
    if kind == "perk":
        x.pop("also")
    if any(x.values()):
        app.project.data[key][t] = x
    else:
        app.project.data[key].pop(t, None)
    app.project.save()
    return {"ok": True}


def _validate_custom(app, kind, item, old_type=None):
    t = int(item["type"])
    orig = app.original_types()[0 if kind == "skill" else 1]
    if t in orig:
        raise ApiError("Type %d exists in the original game data; pick a free Type" % t)
    lo = 1 if kind == "perk" else 0
    if not (lo <= t <= framework.MAX_TYPE):
        raise ApiError("Type must be %d..%d" % (lo, framework.MAX_TYPE))
    lst = app.project.data["custom_skills" if kind == "skill" else "custom_perks"]
    if any(int(s["type"]) == t for s in lst) and t != old_type:
        raise ApiError("Type %d is already a custom %s" % (t, kind))
    if not item.get("levels"):
        raise ApiError("at least one level is required")
    if kind == "perk" and int(item.get("base") or 0) and int(item["base"]) not in orig:
        raise ApiError("base perk Type %s does not exist" % item["base"])
    if kind == "skill":
        for b in item.get("bases", []):
            if int(b) not in orig:
                raise ApiError("base skill Type %s does not exist" % b)


def api_custom_save(app, q, body):
    kind = body["kind"]
    item = body["item"]
    old = body.get("old_type")
    _validate_custom(app, kind, item, int(old) if old is not None else None)
    key = "custom_skills" if kind == "skill" else "custom_perks"
    lst = app.project.data[key]
    idx = next((i for i, s in enumerate(lst) if old is not None and int(s["type"]) == int(old)), None)
    if idx is None:
        lst.append(item)
    else:
        lst[idx] = item
    app.project.save()
    return {"ok": True, "type": int(item["type"])}


def api_custom_delete(app, q, body):
    key = "custom_skills" if body["kind"] == "skill" else "custom_perks"
    t = int(body["type"])
    app.project.data[key] = [s for s in app.project.data[key] if int(s["type"]) != t]
    app.project.save()
    return {"ok": True}


def api_free_type(app, q, body):
    kind = q["kind"][0]
    orig = app.original_types()[0 if kind == "skill" else 1]
    used = {int(s["type"]) for s in app.project.data["custom_skills" if kind == "skill" else "custom_perks"]}
    start = framework.SKILL_NATIVE if kind == "skill" else framework.FEAT_NATIVE
    for t in range(start, framework.MAX_TYPE + 1):
        if t not in orig and t not in used:
            return {"type": t}
    raise ApiError("no free Type")


def _perk_rows_by_type(app):
    by = {}
    for r in app.gd().rows("ArmyFeatureSettings"):
        by.setdefault(r["Type"], []).append(r)
    return by


def api_perks(app, q, body):
    gd = app.gd()
    by = _perk_rows_by_type(app)
    cat = app.catalog()["feature"]
    custom = {int(p["type"]): p for p in app.project.data["custom_perks"]}
    units = {}
    for u in gd.rows("ArmySettings"):
        for f in u.get("Feature") or []:
            units[f] = units.get(f, 0) + 1
    out = []
    for t in sorted(set(by) | set(custom)):
        rows = sorted(by.get(t, []), key=lambda r: r.get("Level", 0))
        c = custom.get(t)
        name = gd.text("feat_name_%d" % t) or (c and c.get("names", {}).get("en")) or (rows[0]["Name"] if rows else "")
        out.append(dict(type=t, name=name, cn=rows[0]["Name"] if rows else "",
                        levels=len(rows) if not c else len(c["levels"]), custom=bool(c),
                        usage=len(cat.get(t, [])), units=units.get(t, 0) if not c else len(c.get("units", [])),
                        extras=str(t) in app.project.data["perk_extras"]))
    return {"perks": out}


def api_perk(app, q, body):
    t = int(q["type"][0])
    gd = app.gd()
    rows = sorted(_perk_rows_by_type(app).get(t, []), key=lambda r: r.get("Level", 0))
    names, descs = app.texts("feat_name_", "feat_desc_", t)
    lvdesc = {l: {lv: gd.text("feat_desc_%d_Lv%d" % (t, lv), l) for lv in range(2, 5)} for l in ("en",)}
    custom = next((p for p in app.project.data["custom_perks"] if int(p["type"]) == t), None)
    units = [dict(id=u["Id"], name=gd.text("unit_name_%d" % u["Id"]) or u["Name"], army=u["Army"],
                  level=(u.get("FeatureLevel") or [])[u["Feature"].index(t)]
                  if len(u.get("FeatureLevel") or []) > u["Feature"].index(t) else 1)
             for u in gd.rows("ArmySettings") if t in (u.get("Feature") or [])]
    return dict(type=t, rows=rows, names=names, descs=descs, lvdescs=lvdesc, custom=custom, units=units,
                extras=app.project.data["perk_extras"].get(str(t)),
                usage=app.catalog()["feature"].get(t, []), original=t in app.original_types()[1])


def api_perk_rows(app, q, body):
    t = int(body["type"])
    if any(int(p["type"]) == t for p in app.project.data["custom_perks"]):
        raise ApiError("custom perks are edited in their own form")
    rows = {r["Id"]: r for r in app.gd().rows("ArmyFeatureSettings") if r["Type"] == t}
    editable = {"ActivatesChance", "FeatureEffect", "SecondEffect", "RelatedArmyId", "AntiairId", "Condition",
                "CD", "Range", "Round", "ArmyBuff", "ArmyBuffRound", "Auras", "AgainstArmy", "Name"}
    for ch in body["rows"]:
        r = rows.get(ch["Id"])
        if not r:
            continue
        for k, v in ch.items():
            if k in editable and k in r:
                r[k] = v if k == "Name" else [int(x) for x in v] if k == "AgainstArmy" else int(v)
    app.gd().mark("ArmyFeatureSettings")
    app.gd().save(app.project.backup_dir(), log=lambda *_: None)
    return {"ok": True}


def api_units(app, q, body):
    gd = app.gd()
    out = []
    for u in gd.rows("ArmySettings"):
        out.append(dict(id=u["Id"], army=u["Army"], type=u["Type"], elite=u.get("Elite", 0),
                        name=gd.text("unit_name_%d" % u["Id"]) or u["Name"], features=u.get("Feature") or [],
                        levels=u.get("FeatureLevel") or []))
    return {"units": out}


def api_generals(app, q, body):
    gd = app.gd()
    out = []
    for g in gd.rows("GeneralSettings"):
        if not g.get("Id"):
            continue
        out.append(dict(id=g["Id"], name=gd.text(g.get("EName") or "", "en") or g.get("EName") or g.get("Name"),
                        type=g.get("Type"), skills=g.get("Skills") or [], max=g.get("SkillsMax")))
    return {"generals": out}


# ---------------------------------------------------------------------- code browser
def _addr(v):
    v = str(v).strip().lower()
    return int(v, 16) if v.startswith("0x") or re.search(r"[a-f]", v) else int(v, 16)


def api_disasm(app, q, body):
    elf, an = app.view(q.get("view", ["base"])[0])
    addr = _addr(q["addr"][0]) & ~3
    before = int(q.get("before", ["40"])[0])
    after = int(q.get("after", ["160"])[0])
    if not elf.is_exec(addr):
        raise ApiError("%#x is not executable code" % addr)
    start = max(addr - 4 * before, elf.loads[0].p_vaddr)
    end = min(addr + 4 * after, elf.code_end)
    ins = an.disasm(start, end=end)
    refs = an.refs_in_range(start, end) if an._xrefs is not None or an.cache_dir else {}
    f0, f1 = an.func_of(addr)
    out = []
    for a, sz, mn, ops in ins:
        tgt = arm64.branch_target(mn, ops)
        note = ""
        if a in refs:
            note = an.describe_data(refs[a])
        elif tgt is not None:
            nm = an.names.get(tgt) or app.known_funcs.get(tgt, "")
            note = nm
        out.append(dict(a=a, b=elf.read(a, sz).hex(), m=mn, o=ops, t=tgt, n=note,
                        f=a in an.funcs or a in an.names))
    return dict(addr=addr, func=[f0, f1], func_name=an.names.get(f0) or app.known_funcs.get(f0, ""),
                ins=out, code_end=elf.code_end)


def api_xrefs(app, q, body):
    elf, an = app.view(q.get("view", ["base"])[0])
    addr = _addr(q["addr"][0])
    callers = [dict(a=a, f=an.func_of(a)[0]) for a in an.callers(addr)][:500]
    data = [dict(a=a, f=an.func_of(a)[0]) for a in an.xrefs_to(addr)][:500]
    return dict(addr=addr, callers=callers, data=data)


def api_funcs(app, q, body):
    _, an = app.view(q.get("view", ["base"])[0])
    s = q.get("q", [""])[0].strip().lower()
    out = []
    if s:
        for a, nm in list(app.known_funcs.items()) + [(a, n) for a, n in an.names.items()]:
            if s in nm.lower() or s in "%x" % a:
                out.append(dict(a=a, n=nm))
        for a in an.funcs:
            if ("%x" % a).startswith(s.lstrip("0x")) and len(out) < 300:
                out.append(dict(a=a, n=app.known_funcs.get(a, "")))
    else:
        out = [dict(a=a, n=n) for a, n in sorted(app.known_funcs.items())]
    return dict(funcs=out[:300], total=len(an.funcs))


def api_strings(app, q, body):
    _, an = app.view("base")
    s = q.get("q", [""])[0]
    res = an.find_strings(s, 300) if s else []
    return dict(strings=[dict(a=a, s=t, refs=len(an.xrefs_to(a))) for a, t in res])


def api_hex(app, q, body):
    elf, _ = app.view(q.get("view", ["base"])[0])
    addr = _addr(q["addr"][0])
    n = min(int(q.get("len", ["256"])[0]), 4096)
    o = elf.off(addr)
    if o is None:
        raise ApiError("not file-backed")
    return dict(addr=addr, hex=bytes(elf.data[o:o + n]).hex())


def api_assemble(app, q, body):
    elf, _ = app.view("base")
    addr = _addr(body["addr"]) & ~3
    if body.get("hex"):
        blob = bytes.fromhex(re.sub(r"\s", "", body["hex"]))
    else:
        try:
            blob = arm64.assemble(body["asm"], addr)
        except arm64.AsmError as e:
            raise ApiError("assembler: %s" % e)
    if len(blob) % 4:
        raise ApiError("patch length must be a multiple of 4")
    orig = elf.read(addr, len(blob))
    return dict(addr=addr, hex=blob.hex(), orig=orig.hex(),
                new=[dict(a=a, m=m, o=o) for a, s, m, o in arm64.disasm(blob, addr)],
                old=[dict(a=a, m=m, o=o) for a, s, m, o in arm64.disasm(orig, addr)])


def api_patch_add(app, q, body):
    r = api_assemble(app, q, body)
    lst = app.project.data["asm_patches"]
    lst.append(dict(addr="%#x" % r["addr"], hex=r["hex"], orig=r["orig"], note=body.get("note", ""),
                    asm=body.get("asm", ""), enabled=True))
    app.project.save()
    return {"ok": True}


def api_patch_edit(app, q, body):
    lst = app.project.data["asm_patches"]
    i = int(body["index"])
    if body.get("delete"):
        lst.pop(i)
    else:
        for k in ("enabled", "note"):
            if k in body:
                lst[i][k] = body[k]
    app.project.save()
    return {"ok": True}


def api_build(app, q, body):
    lines = []
    try:
        app.project.build(log=lines.append, write_data=body.get("write_data", True))
        app._built = None
        return dict(ok=True, log=lines)
    except Exception as e:
        lines.append("ERROR: %s" % e)
        return dict(ok=False, log=lines)


def api_preview(app, q, body):
    """Dry run: assemble the library in memory and report the extension layout."""
    _, elf, an, ext = app.built()
    out = dict(size=len(elf.data), detect=patches.detect(elf))
    if ext:
        out["ext"] = dict(code_size=ext["code_size"], labels={k: v for k, v in sorted(ext["labels"].items(),
                                                                                       key=lambda kv: kv[1])},
                          bss=ext["bss"], sites=[dict(a=a, g=g) for a, g in ext["sites"]])
    return out


def api_icon(app, q, body):
    kind, t = q["kind"][0], int(q["type"][0])
    gd = app.gd()
    if kind == "skill":
        c = next((s for s in app.project.data["custom_skills"] if int(s["type"]) == t), None)
        if c and (c.get("icon") or {}).get("png_b64"):
            return base64.b64decode(c["icon"]["png_b64"])
        if c and (c.get("icon") or {}).get("from_type") is not None and \
                not gd.find_asset("image/general_skill/general_skill_%d.webp" % t):
            t = int(c["icon"]["from_type"])
        return gamedata.skill_icon_png(gd, t)
    lv = int(q.get("level", ["1"])[0])
    if not hasattr(app, "_atlas") or app._atlas is None:
        app._atlas = gamedata.FeatAtlas(gd)
    c = next((p for p in app.project.data["custom_perks"] if int(p["type"]) == t), None)
    if c and (c.get("icon") or {}).get("png_b64"):
        return base64.b64decode(c["icon"]["png_b64"])
    png = app._atlas.icon_png(t, lv)
    if png is None and c:
        png = app._atlas.icon_png(int((c.get("icon") or {}).get("from_type") or c.get("base") or 1), lv)
    return png
