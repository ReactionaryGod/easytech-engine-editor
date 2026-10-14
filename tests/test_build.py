"""End-to-end: custom skill + perk + extras -> build into a scratch package -> verify outputs. Usage: test_build.py <scratch package>"""
import json, os, sys, hashlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
from wc4engine.project import Project
from wc4engine import patches, gamedata
from wc4engine.elf import Elf
from wc4engine.framework import FeatureExt
from emu import Emu

pkg = sys.argv[1]
fails = []
def check(n, got, want=True):
    ok = got == want
    print("%-58s %s" % (n, "ok" if ok else "FAIL got %r want %r" % (got, want)))
    if not ok: fails.append(n)

pr = Project(pkg)
GAME = os.environ.get("WC4_GAME_DIR", os.path.join(os.path.dirname(os.path.dirname(HERE)), "World Conqueror 4_1.30.0_learning"))


def setpaths(p):
    p.data["paths"] = {"base_so": os.path.join(GAME, "lib", "arm64-v8a", "libworld-conqueror-4.so"),
                       "assets": os.path.join(GAME, "assets"), "backups": os.path.join(pkg, "backups")}


setpaths(pr)
with open(os.path.join(pkg, "CHANGES.txt"), "w") as _f:     # the test counts the entries it adds
    _f.write("base" + chr(10))
pr.data["custom_skills"] = [{
    "type": 200, "names": {"en": "Test Skill", "cn": "测试"}, "descs": {"en": "Armor attack +[#00FF00#%d]%%"},
    "series": 1, "if_percent": 1, "open_default": 1, "bases": [34],
    "effects": [{"category": 5, "classes": [2], "from_row": True, "value": 0}],
    "levels": [{"chance": 20, "effect": 5, "cost": 100}, {"chance": 40, "effect": 9, "cost": 200}],
    "icon": {"from_type": 34}, "generals": [{"id": 1, "level": 2}]}]
pr.data["custom_perks"] = [{
    "type": 170, "base": 92, "names": {"en": "Test Perk"}, "descs": {"en": "A test perk."},
    "levels": [{"chance": 100, "effect": 30, "second": 7}, {"chance": 100, "effect": 40, "second": 9}],
    "effects": [{"category": 3, "classes": [2], "from_row": False, "value": 4}],
    "icon": {"from_type": 92}, "units": [{"id": 332001, "level": 1}]}]
pr.data["skill_extras"] = {"6": {"also": [], "effects": [{"category": 1, "classes": [], "from_row": False, "value": 3}]}}
log = pr.build(log=lambda *_: None)
print("\n".join("   " + l for l in log))

lib = os.path.join(pkg, "lib", "arm64-v8a", "libworld-conqueror-4.so")
d = patches.detect(Elf.load(lib))
check("library carries the editor's extension", "this editor" in d["engine_ext"])
check("challenge tier12 / MF unlocked / bank", (d["challenge"], d["mf_picker"], d["general_bank"]), ("tier12", "unlocked", "patched"))

gd = pr.gd
gd.reload()
sk = [r for r in gd.rows("SkillSettings") if r["Type"] == 200]
check("2 skill rows, chained", [(r["Id"], r["Level"], r["UpgradeId"]) for r in sk], [(12001, 1, 12002), (12002, 2, 0)])
check("skill row fields", (sk[1]["ActivatesChance"], sk[1]["SkillEffect"], sk[1]["IfPercent"], sk[1]["OpenDefault"]), (40, 9, 1, 1))
g1 = next(g for g in gd.rows("GeneralSettings") if g["Id"] == 1)
check("general 1 got skill 12002", 12002 in g1["Skills"])
pk = [r for r in gd.rows("ArmyFeatureSettings") if r["Type"] == 170]
check("2 perk rows", [(r["Id"], r["Level"], r["FeatureEffect"], r["SecondEffect"]) for r in pk], [(401701, 1, 30, 7), (401702, 2, 40, 9)])
u = next(x for x in gd.rows("ArmySettings") if x["Id"] == 332001)
check("unit 332001 has perk 170", 170 in u["Feature"], True)
check("feature/level lists aligned", len(u["Feature"]) == len(u.get("FeatureLevel") or []) or not u.get("FeatureLevel"))
for lang in gamedata.LANGS:
    check("%s: skill_name_200 / feat_name_170" % lang, (gd.text("skill_name_200", lang) != "", gd.text("feat_name_170", lang) != ""), (True, True))
check("cn name used", gd.text("skill_name_200", "cn"), "测试")
check("skill icon written", os.path.exists(os.path.join(pkg, "assets/image/general_skill/general_skill_200.webp")))
atlas = gamedata.FeatAtlas(gd)
check("atlas has feat_170_1/2", ("feat_170_1.png" in atlas.frames, "feat_170_2.png" in atlas.frames), (True, True))
check("atlas xml keeps CRLF + header", atlas.xml_raw.startswith(b'<Texture name="image_feats_hd.png" />\r\n<Images>'))

# emulate the built library with the data the editor wrote
elf = Elf.load(lib); em = Emu(elf)
ds = em.alloc(0x4800)
def row(t, lv): r = em.alloc(0x78); em.w32(r+0x20, t); em.w32(r+0x24, lv); return r
em.set_vec(ds + 0x1bb8 + 34*0x18, [row(34, 0)])
ext = elf.bss_end
# EXT_S is the first bss table after the original bss; find it from the built library layout
base = Elf.load(pr.data["paths"]["base_so"])
ext_s = (base.bss_end + 0xff) & ~0xff
em.set_vec(ext_s + (200-192)*0x18, [row(200, 1), row(200, 2)])
check("emulated GetSkill(200,1) found", em.call(0x209940, dict(x0=ds, x1=200, x2=1)) != 0)
gen = em.alloc(0x100); s200 = row(200, 2); em.set_vec(gen + 0xa0, [s200])
check("general with 200 counts as Blitzkrieg(34)", em.call(0x39f370, dict(x0=gen, x1=34)), s200)

# second build is idempotent
before = {p: hashlib.sha1(open(p, "rb").read()).hexdigest() for p in
          [lib] + [os.path.join(pkg, "assets/json", n) for n in ("SkillSettings.json", "ArmyFeatureSettings.json", "GeneralSettings.json", "ArmySettings.json")]
          + [os.path.join(pkg, "stringtable_en.ini")]}
pr2 = Project(pkg); pr2.build(log=lambda *_: None)
after = {p: hashlib.sha1(open(p, "rb").read()).hexdigest() for p in before}
check("rebuild is byte-identical", before == after)
ch = open(os.path.join(pkg, "CHANGES.txt"), encoding="utf-8").read()
check("CHANGES.txt not duplicated", ch.count("Engine editor build"), 1)

# removing the custom items cleans the json again
pr3 = Project(pkg)
pr3.data["custom_skills"] = []; pr3.data["custom_perks"] = []; pr3.data["skill_extras"] = {}
pr3.build(log=lambda *_: None); pr3.gd.reload()
check("rows removed after deleting the custom skill/perk",
      (any(r["Type"] == 200 for r in pr3.gd.rows("SkillSettings")), any(r["Type"] == 170 for r in pr3.gd.rows("ArmyFeatureSettings"))), (False, False))
g1 = next(g for g in pr3.gd.rows("GeneralSettings") if g["Id"] == 1)
check("general 1 skill removed again", 12002 in g1["Skills"], False)
u = next(x for x in pr3.gd.rows("ArmySettings") if x["Id"] == 332001)
check("unit perk removed again", 170 in u["Feature"], False)
print("\n%d failure(s)" % len(fails)); sys.exit(1 if fails else 0)
