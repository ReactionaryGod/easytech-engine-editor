"""Builds the engine extension on the base library and emulates the new routines with Unicorn.
Usage: python tests/test_framework.py [base .so]   (default: env WC4_BASE_SO or the extracted APK's lib)"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from wc4engine import arm64, framework                                  # noqa: E402
from wc4engine.elf import Elf                                            # noqa: E402
from wc4engine.framework import ExtConfig, SkillExt, FeatureExt, Effect  # noqa: E402
from emu import Emu                                                      # noqa: E402

DEFAULT_BASE = os.path.join(os.path.dirname(os.path.dirname(HERE)), "World Conqueror 4_1.30.0_learning", "lib",
                            "arm64-v8a", "libworld-conqueror-4.so")


def base_path():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return os.environ.get("WC4_BASE_SO", DEFAULT_BASE)


def build(cfg):
    elf = Elf.load(base_path())
    info = framework.apply(elf, cfg, log=lambda *_: None)
    return Elf(bytes(elf.data)), info


CFG = ExtConfig(
    skills=[SkillExt(200, [34, 33], [Effect(5, [2], True), Effect(3, [], False, 4)]),
            SkillExt(34, [171], [], custom=False)],
    features=[FeatureExt(170, 92, [Effect(3, [2], True)]), FeatureExt(4, 0, [Effect(7, [1], False, 2)])],
    legacy_skins=True, tier12=True)

failures = []


def check(name, got, want):
    ok = got == want
    print("%-46s %s" % (name, "ok" if ok else "FAIL got %r want %r" % (got, want)))
    if not ok:
        failures.append(name)


def main():
    elf, info = build(CFG)
    L, B = info["labels"], info["bss"]
    print("code %d bytes, %d sites" % (info["code_size"], len(info["sites"])))

    # ---- ELF layout
    check("PT_LOAD[1] offset == vaddr", elf.loads[1].p_offset, elf.loads[1].p_vaddr)
    check("PT_LOAD[0] end", elf.loads[0].p_filesz, 0xa16000 if info["code_size"] <= 0x1000 else elf.loads[0].p_filesz)
    check(".dynamic still parses", elf.section(".dynamic").sh_addr, 0xa75be8)
    check("dynamic data moved with segment", elf.read(0xa75be8, 16), Elf.load(base_path()).read(0xa75be8, 16))
    check("bss extended", elf.bss_end >= B["EMPTY"] + 0x18, True)
    # every patched bl-site lives in a function that saved x30 and never uses it as a scratch register
    em = Emu(elf)

    def fake_ds():
        return em.alloc(0x4800)

    def row(type_, level=1, chance=0, effect=0, size=0x78):
        r = em.alloc(size)
        em.w32(r + 0x20, type_)
        em.w32(r + 0x24, level)
        em.w32(r + 0x28, chance)
        em.w32(r + 0x2c, effect)
        return r

    # ---- skill table getters
    ds = fake_ds()
    r34 = [row(34, 0), row(34, 1)]
    em.set_vec(ds + 0x1bb8 + 34 * 0x18, r34)
    r200 = [row(200, 0), row(200, 1), row(200, 2)]
    em.set_vec(B["EXT_S"] + (200 - 192) * 0x18, r200)
    check("GetSkill(34, 1) native", em.call(0x209940, dict(x0=ds, x1=34, x2=1)), r34[1])
    check("GetSkill(200, 2) extended", em.call(0x209940, dict(x0=ds, x1=200, x2=2)), r200[2])
    check("GetSkill(200, 3) out of levels", em.call(0x209940, dict(x0=ds, x1=200, x2=3)), 0)
    check("GetSkill(900, 0) out of types", em.call(0x209940, dict(x0=ds, x1=900, x2=0)), 0)
    check("GetSkill(-1, 0)", em.call(0x209940, dict(x0=ds, x1=0xffffffff, x2=0)), 0)
    check("MaxLevel(200)", em.call(0x209b50, dict(x0=ds, x1=200)) & 0xffffffff, 2)
    check("MaxLevel(34)", em.call(0x209b50, dict(x0=ds, x1=34)) & 0xffffffff, 1)
    em.call(L["h_s_load"], dict(x8=200, x19=ds))
    check("loader slot(200)", em.reg(11) + 0x1bb8, B["EXT_S"] + 8 * 0x18)
    em.call(L["h_s_load"], dict(x8=5, x19=ds))
    check("loader slot(5)", em.reg(11), ds + 5 * 0x18)
    em.call(L["h_s_load"], dict(x8=4000, x19=ds))
    check("loader slot(4000) -> trash", em.reg(11) + 0x1bb8, B["TRASH_S"])
    em.call(L["h_s_load"], dict(x8=200, x19=ds, x16=0x1111, x17=0x2222, x10=0x3333))
    check("loader helper preserves x8/x10/x16/x17", (em.reg(8), em.reg(10), em.reg(16), em.reg(17)),
          (200, 0x3333, 0x1111, 0x2222))
    em.call(L["h_s_209a30"], dict(x24=300, x22=ds))
    check("series loop slot(300)", em.reg(8) + 0x1bb8, B["EXT_S"] + (300 - 192) * 0x18)

    # ---- feature table getters
    f92 = [row(92, 0), row(92, 1)]
    em.set_vec(ds + 0x2dc8 + 92 * 0x18, f92)
    f170 = [row(170, 0), row(170, 1)]
    em.set_vec(B["EXT_F"] + (170 - 167) * 0x18, f170)
    check("GetFeature(92, 1) native", em.call(0x20bb98, dict(x0=ds, x1=92, x2=1)), f92[1])
    check("GetFeature(170, 1) extended", em.call(0x20bb98, dict(x0=ds, x1=170, x2=1)), f170[1])
    check("GetFeature(170, -1)", em.call(0x20bb98, dict(x0=ds, x1=170, x2=0xffffffff)), 0)
    check("feature tail (170, lvl 1)", em.call(L["t_feat_tail"], dict(x0=ds, x2=170, x8=1)), f170[1])
    em.call(L["h_f_load"], dict(x8=167, x19=ds))
    check("feature loader slot(167) -> ext", em.reg(11) + 0x2dc8, B["EXT_F"])
    em.call(L["h_f_load"], dict(x8=166, x19=ds))
    check("feature loader slot(166) native", em.reg(11), ds + 166 * 0x18)

    # ---- feature remap after load: row 170 -> base 92, display 170
    sp = 0x7f000000 + 0x100000 - 0x1000
    rr = row(170, 1)
    em.w32(rr + 0x74, 0x5555)
    em.w64(sp + 0x18, rr)
    em.call(L["f_post"], dict(x21=7))
    check("remap type", (em.r32(rr + 0x20), em.r32(rr + 0x74), em.reg(21)), (92, 170, 8))
    rn = row(5, 1)
    em.w32(rn + 0x74, 0x5555)
    em.w64(sp + 0x18, rn)
    em.call(L["f_post"], dict(x21=0))
    check("non-custom row: display cleared", (em.r32(rn + 0x20), em.r32(rn + 0x74)), (5, 0))
    em.call(L["fd_w1w2_x0"], dict(x0=rr))
    check("display stub (custom)", (em.reg(1), em.reg(2)), (170, 1))
    em.call(L["fd_w3w4_x23"], dict(x23=rn))
    check("display stub (native)", (em.reg(3), em.reg(4)), (5, 1))

    # ---- skill aliases (0x39f370) and switch dispatch
    gen = em.alloc(0x100)
    s200 = row(200, 1, 20, 15, 0x68)
    em.w32(s200 + 0x30, 15)
    s5 = row(120, 1, 0, 0, 0x68)
    em.set_vec(gen + 0xa0, [s5, 0, s200])
    check("HasSkill(120) direct", em.call(0x39f370, dict(x0=gen, x1=120)), s5)
    check("HasSkill(34) via custom 200", em.call(0x39f370, dict(x0=gen, x1=34)), s200)
    check("HasSkill(33) via custom 200 (2nd base)", em.call(0x39f370, dict(x0=gen, x1=33)), s200)
    check("HasSkill(171) not owned", em.call(0x39f370, dict(x0=gen, x1=171)), 0)
    s34 = row(34, 1, 20, 0, 0x68)
    em.set_vec(gen + 0xa0, [s34])
    check("existing 34 also counts as 171", em.call(0x39f370, dict(x0=gen, x1=171)), s34)
    em.call(L["bt_x0"], dict(x0=s200, x9=9, x12=12))
    check("switch type of 200 = primary 34", (em.reg(8), em.reg(9), em.reg(12)), (34, 9, 12))
    em.call(L["bt_x0"], dict(x0=s34))
    check("switch type of 34 unchanged", em.reg(8), 34)

    # ---- stat bonus
    army = em.alloc(0x200)
    arow = em.alloc(0x100)
    em.w32(arow + 0x3c, 2)          # armor
    em.w32(arow + 0x38, 80)
    em.w64(army + 8, arow)
    gen2 = em.alloc(0x100)
    em.set_vec(gen2 + 0xa0, [s200])
    em.w64(army + 0x78, gen2)
    feat = row(92, 1, 100, 6)
    em.w32(feat + 0x74, 170)
    em.set_vec(army + 0x30, [feat])
    check("bonus attack% (skill from row 15)", em.call(L["ext_bonus"], dict(x0=army, x1=5)), 15)
    check("bonus defence (skill 4 + feature 6)", em.call(L["ext_bonus"], dict(x0=army, x1=3)), 10)
    check("bonus crit (none)", em.call(L["ext_bonus"], dict(x0=army, x1=1)), 0)
    em.w32(arow + 0x3c, 1)          # infantry: armor-only effects drop, feature 4 range applies? (not owned)
    check("bonus attack% for infantry", em.call(L["ext_bonus"], dict(x0=army, x1=5)), 0)
    check("bonus defence for infantry (fixed 4 only)", em.call(L["ext_bonus"], dict(x0=army, x1=3)), 4)
    # elite skin: country +0x650 vector of EliteSkin rows {Id, Army, Index, Effect}
    em.w32(arow + 0x3c, 2)
    country = em.alloc(0x700)
    sk = em.alloc(0x20)
    em.w32(sk + 4, 80)
    em.w32(sk + 8, 1)
    em.w32(sk + 0xc, 2010)          # crit damage +10
    em.set_vec(country + 0x650, [sk])
    em.w64(army + 0x70, country)
    em.w8(army + 0xbc, 1)
    check("skin crit damage +10", em.call(L["ext_bonus"], dict(x0=army, x1=2)), 10)
    check("skin does not leak to crit chance", em.call(L["ext_bonus"], dict(x0=army, x1=1)), 0)
    em.w32(arow + 0x38, 0x35)       # BM-21 legacy row: Effect < 1000 = crit chance
    em.w32(sk + 4, 0x35)
    em.w32(sk + 0xc, 7)
    check("legacy BM-21 crit chance", em.call(L["ext_bonus"], dict(x0=army, x1=1)), 7)

    # ---- integration: the engine's own max-HP routine (0x37c16c) runs through the tr_hp hook
    cfg2 = ExtConfig(features=[FeatureExt(170, 92, [Effect(6, [2], False, 50)])])
    elf2, info2 = build(cfg2)
    em2 = Emu(elf2)
    army = em2.alloc(0x200)
    arow = em2.alloc(0x100)
    em2.w32(arow + 0x94, 1000)       # ArmySettings.HP
    em2.w32(arow + 0x3c, 2)          # armor
    em2.w64(army + 8, arow)
    em2.w32(army + 0xd4, 100)        # HP %
    lvl = em2.alloc(0x10)
    em2.w32(lvl + 4, 20)             # level HP bonus
    em2.w64(army + 0x10, lvl)
    feat = em2.alloc(0x78)
    em2.w32(feat + 0x20, 92)
    em2.w32(feat + 0x74, 170)
    em2.set_vec(army + 0x30, [feat])
    em2.set_vec(army + 0x88, [])
    em2.w32(army + 0xd8, 1020)
    em2.w32(army + 0xdc, 1020)
    em2.call(0x37c16c, dict(x0=army))
    check("engine max HP 1020 +50% (perk effect)", em2.r32(army + 0xdc), 1530)
    em2.w32(arow + 0x3c, 1)          # infantry: effect is armor-only
    em2.call(0x37c16c, dict(x0=army))
    check("engine max HP for infantry unchanged", em2.r32(army + 0xdc), 1020)

    # ---- every bl site sits in a function that saved x30
    from wc4engine.analysis import Analysis
    an = Analysis(elf)
    for addr, grp in info["sites"]:
        ins = arm64.disasm(elf.read(addr, 4), addr)[0]
        if ins[2] != "bl":
            continue
        f0, f1 = an.func_of(addr)
        body = arm64.disasm(elf.read(f0, min(f1 - f0, 0x40)), f0)
        saves = any("x30" in i[3] and i[2] in ("stp", "str") for i in body)
        check("x30 saved in %x (site %x)" % (f0, addr), saves, True)
        full = arm64.disasm(Elf.load(base_path()).read(f0, f1 - f0), f0)
        misuse = [hex(i[0]) for i in full if re.search(r"[xw]30", i[3])
                  and not (i[2] in ("stp", "ldp", "str", "ldr") and "[sp" in i[3])]
        check("x30 not a scratch reg in %x" % f0, misuse, [])

    print("\n%d failure(s)" % len(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
