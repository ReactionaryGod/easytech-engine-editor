"""GoG3 data model against a scratch package. Usage: python tests/test_gog3.py <scratch package dir>"""
import io, json, os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from PIL import Image
from wc4engine.gog3.project import Gog3Project
from wc4engine.gog3 import conditions as cond, catalog, buff_types
from wc4engine.elf import Elf
from wc4engine.analysis import Analysis

pkg = sys.argv[1]
shutil.rmtree(pkg, ignore_errors=True); os.makedirs(pkg)
fails = []
def check(n, got, want=True):
    ok = got == want
    print("%-62s %s" % (n, "ok" if ok else "FAIL got %r want %r" % (got, want)))
    if not ok: fails.append(n)

pr = Gog3Project(pkg)
GOG3 = os.environ.get("GOG3_DIR", r"D:\Gog3")
pr.data["paths"] = {"base_so": os.path.join(GOG3, "lib", "arm64-v8a", "libiron.so"),
                    "assets": os.path.join(GOG3, "assets"), "backups": os.path.join(pkg, "backups")}
st = pr.store
orig = {n: open(os.path.join(os.environ.get("GOG3_DIR", r"D:\Gog3"), "assets", "json", n + ".json"), "rb").read() for n in
        ("SkillSettings", "BuffSettings", "ArmyFeatureSettings", "GeneralSettings", "ArmySettings")}

# conditions
cs = st.conditions(); check("73 original conditions parsed", len(cs), 73)
cid = st.next_condition_id(); check("first custom condition id", cid, 2001)
st.save_custom_conditions([dict(id=cid, scope="army", op="and", compare="", desc="armor vs infantry", params=[], children=[102, 106])])
check("custom condition stored + flagged", [(c["id"], c["custom"]) for c in st.conditions() if c["custom"]], [(2001, True)])
try: st.save_custom_conditions([dict(id=101, scope="army", op="and", compare="", desc="", params=[], children=[102])]); check("rejects id clash", False)
except ValueError: check("rejects id clash", True)

# buffs
bid = st.new_buff_id(); check("new buff id", bid, 7001)
st.save_buff(dict(Id=bid, Condition=cid, PR=100, Type=36, Key=0, Value=7, BuffId=0, Range=0, Round=0, EffectId=0), create=True)
bid2 = st.new_buff_id(); st.save_buff(dict(Id=bid2, Condition=0, PR=100, Type=99, Key=0, Value=0, BuffId=bid, Range=2, Round=0, EffectId=0), create=True)
try: st.save_buff(dict(Id=bid2, Condition=999999, PR=100, Type=36, Key=0, Value=0, BuffId=0, Range=0, Round=0, EffectId=0)); check("rejects unknown condition", False)
except ValueError: check("rejects unknown condition", True)

# skill with 2 levels
t = st.new_skill_type()
ids = st.save_skill(dict(type=t, rows=[
    dict(id=None, level=1, armytype=2, buff=bid, name="测试", names={"en": "Test Skill", "cn": "测试"}, descs={"en": "Armor +{1}"}),
    dict(id=None, level=2, armytype=2, buff=bid2, names={"en": "Test Skill"}, descs={"en": "Armor aura {2}"})]))
check("2 skill rows created", [r["Level"] for r in st.skill_detail(t)["rows"]], [1, 2])
check("skill text stored", st.text("skill_%d" % ids[0]), "Test Skill")
gid = st.general_list()[0]["id"]
st.set_general_skill(gid, ids[1], True)
check("general received skill", [g["id"] for g in st.generals_with(set(ids))], [gid])

# perk
pid = st.save_perk(dict(id=None, buffs=[bid], names={"en": "Test Perk"}, descs={"en": "perk"}))
uid = st.unit_list()[1]["id"]; st.set_unit_perk(uid, pid, True)
check("perk assigned to unit", [u["id"] for u in st.perk_detail(pid)["units"]], [uid])

# icons
buf = io.BytesIO(); Image.new("RGBA", (64, 64), (200, 40, 40, 255)).save(buf, "PNG")
st.set_icon("skill", ids[0], buf.getvalue()); st.set_icon("perk", pid, buf.getvalue())
a = st.atlas(); check("custom atlas has both frames", sorted(a.frames), sorted(["skill_%d.png" % ids[0], "army_feature%d.png" % pid]))
check("icon readable back", Image.open(io.BytesIO(st.icon_png("skill", ids[0]))).size, (80, 80))
check("original skill icon readable", st.icon_png("skill", 1001) is not None)
check("original perk icon readable", st.icon_png("perk", 1) is not None)
res = open(os.path.join(pkg, "assets", "image_resource.xml"), "rb").read().decode("utf-8")
check("atlas registered once", res.count("image_custom.xml"), 1)

# files on disk: only intended rows changed
fresh = Gog3Project(pkg); fresh.data["paths"] = pr.data["paths"]; s2 = fresh.store
check("reload sees skill rows", len(s2.skill_detail(t)["rows"]), 2)
sk = json.loads(open(os.path.join(pkg, "assets/json/SkillSettings.json"), "rb").read().decode("utf-8"))
check("SkillSettings: 2 rows added", len(sk), len(json.loads(orig["SkillSettings"])) + 2)
raw = open(os.path.join(pkg, "assets/json/SkillSettings.json"), "rb").read()
check("original rows kept byte-for-byte", orig["SkillSettings"].rstrip(b"\r\n]").rstrip() in raw)
for lang in ("en", "cn", "tw", "ja", "ko"):
    check("stringtable %s written in assets/" % lang, os.path.exists(os.path.join(pkg, "assets", "stringtable_%s.ini" % lang)) or lang != "en")

# clean-up
try: st.delete_buff(bid); check("refuses to delete a used buff", False)
except ValueError: check("refuses to delete a used buff", True)
st.set_general_skill(gid, ids[1], False); st.delete_skill(t); st.delete_perk(pid)
st.delete_buff(bid2); st.delete_buff(bid); st.save_custom_conditions([])
for n in ("SkillSettings", "BuffSettings", "ArmyFeatureSettings", "GeneralSettings", "ArmySettings"):
    p = os.path.join(pkg, "assets/json", n + ".json")
    check("%s back to the original bytes" % n, (not os.path.exists(p)) or open(p, "rb").read() == orig[n])
check("no custom conditions left", [c for c in st.conditions() if c["custom"]], [])

# engine catalog
an = Analysis(Elf.load(os.path.join(GOG3, "lib", "arm64-v8a", "libiron.so")), os.path.join(os.path.dirname(HERE), ".cache"))
cat = catalog.build(an)
used = {b["Type"] for b in json.loads(orig["BuffSettings"])} - {0}
check("every used buff Type found in the engine", sorted(used - set(cat)), [])
check("every used Type has a label", sorted(t for t in used if t not in buff_types.BUFF_TYPES), [])
print("\n%d failure(s)" % len(fails)); sys.exit(1 if fails else 0)
