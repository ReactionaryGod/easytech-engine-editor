"""Engine extension for libworld-conqueror-4.so (WC4 1.30.0, arm64).

What it adds to the engine (all addresses are vaddr == file offset in PT_LOAD[0]):

1. Extended type tables. The data system keeps one vector<row*> per skill Type (dataSys+0x1bb8, Types 0-191)
   and per feature Type (dataSys+0x2dc8, Types 1-166). A Type outside those ranges overwrote the next
   field. Types up to MAX_TYPE now go to new tables in an enlarged .bss; every accessor is redirected.
2. Skill behaviour aliases. "Type T also counts as skill B": the general-skill query 0x39f370 (233 call
   sites) matches aliases, and the five switch dispatchers in the damage code use T's *primary* base.
   The row keeps Type T, so names, icons, upgrades and saves stay T's own.
3. Perk (feature) remapping. A custom feature row is stored under its own Type T, then its Type field is
   set to the base feature B (engine logic, which is mostly inlined loops, sees B with T's numbers) and
   T is kept at row+0x74 for the tooltip/icon code, which is redirected to read it.
4. Generic stat effects for skills and features: crit chance, crit damage, defence, mobility, attack %,
   max HP %, max range. Value = the row's SkillEffect / FeatureEffect or a fixed number, filtered by unit
   class (ArmySettings.Type). Hooks: crit chance 0x382844, crit damage 0x38373c, attack 0x3841d4/0x3842e4,
   defence 0x37d738, mobility 0x382e0c, max HP 0x37c3bc, max range 0x380850.
5. Elite-skin effects (EliteSkinSettings.Effect = category*1000 + value), same as the 2026-10-13 patch.
6. Optional: challenge conquests give the player's commanded elites their tier-12 row (site 0x2345bc).
"""
import struct
from dataclasses import dataclass, field

from . import arm64
from .elf import Elf

MAX_TYPE = 511
SKILL_NATIVE, SKILL_OFF = 192, 0x1bb8          # skill Types 0..191 live in dataSys
FEAT_NATIVE, FEAT_OFF = 167, 0x2dc8            # feature Types 1..166 (index 167 overlaps the next map)

CODE_BASE = 0xa15000                            # first byte after the original R-X page
CODE_LIMIT = 0xa20000                           # 64 KiB page below PT_LOAD[1]

# stat effect categories (shared with EliteSkinSettings.Effect = category*1000 + value)
CATEGORIES = {
    1: ("crit_chance", "Crit chance", "+{v}% chance to land a critical attack"),
    2: ("crit_damage", "Crit damage", "+{v}% critical damage"),
    3: ("defence", "Defence", "+{v} defence"),
    4: ("mobility", "Mobility", "+{v} mobility (immobile units stay immobile)"),
    5: ("attack", "Attack %", "+{v}% minimum and maximum attack"),
    6: ("max_hp", "Max HP %", "+{v}% maximum HP"),
    7: ("range", "Range", "+{v} maximum attack range"),
}

UNIT_CLASSES = {1: "Infantry", 2: "Armor", 3: "Artillery", 4: "Navy", 5: "Air", 6: "Missile", 7: "Nuke",
                8: "Defence building", 9: "City", 10: "Satellite", 11: "Mine", 12: "Fortress", 13: "Helicopter"}


@dataclass
class Effect:
    category: int                 # CATEGORIES key
    classes: list = field(default_factory=list)   # ArmySettings.Type values; empty = all units
    from_row: bool = True         # use SkillEffect / FeatureEffect of the row
    value: int = 0                # used when from_row is False

    @classmethod
    def from_dict(cls, d):
        return cls(int(d["category"]), [int(c) for c in d.get("classes", [])], bool(d.get("from_row", True)),
                   int(d.get("value", 0)))


@dataclass
class SkillExt:
    type: int
    bases: list = field(default_factory=list)      # behaviour types; first = primary for custom types
    effects: list = field(default_factory=list)    # [Effect]
    custom: bool = True                            # custom Type (primary base drives switch dispatch)


@dataclass
class FeatureExt:
    type: int
    base: int = 0                                  # 0 = no remap (generic effects only)
    effects: list = field(default_factory=list)


@dataclass
class ExtConfig:
    skills: list = field(default_factory=list)     # [SkillExt]
    features: list = field(default_factory=list)   # [FeatureExt]
    legacy_skins: bool = True                      # BM-21 crit chance / Hawkeye crit damage from Effect < 1000
    tier12: bool = False                           # challenge conquest tier-12 rule (site 0x2345bc)


# ------------------------------------------------------------------------------------------ site table
# (address, expected original instructions, replacement source or callable(labels) -> source, group)
def _sites(cfg, L):
    s = [
        # extended skill tables
        (0x209940, ["mov w8, #0x18"], "b %#x" % L["g_skill_get"], "tables"),
        (0x209b50, ["mov w8, #0x18"], "b %#x" % L["g_skill_maxlv"], "tables"),
        (0x20999c, ["smaddl x8, w1, w8, x0"], "bl %#x" % L["h_s_209974"], "tables"),
        (0x209a80, ["madd x8, x24, x25, x22"], "bl %#x" % L["h_s_209a30"], "tables"),
        (0x209af4, ["cmp x24, #0xc0"], "cmp x24, #%d" % (MAX_TYPE + 1), "tables"),
        (0x1e9358, ["madd x11, x8, x11, x19"], "bl %#x" % L["h_s_load"], "tables"),
        (0x1df18c, ["ldp x29, x30, [sp, #0x20]"], "b %#x" % L["reset_s_tail"], "tables"),
        # extended feature tables + remap
        (0x20bb98, ["tbnz w2, #0x1f, #0x20bbc8"], "b %#x" % L["g_feat_get"], "tables"),
        (0x20bc3c, ["mov w9, #0x18"], "b %#x" % L["t_feat_tail"], "tables"),
        (0x20c268, ["mov w9, #0x18"], "b %#x" % L["t_feat_tail"], "tables"),
        (0x1ebf6c, ["madd x11, x8, x11, x19"], "bl %#x" % L["h_f_load"], "tables"),
        (0x1ec010, ["add w21, w21, #1"], "bl %#x" % L["f_post"], "tables"),
        (0x1df258, ["ldp x29, x30, [sp, #0x20]"], "b %#x" % L["reset_f_tail"], "tables"),
        # feature tooltip / icons use the display type
        (0x29cd2c, ["ldr w3, [x23, #0x20]"], "bl %#x" % L["fd_w3_x23"], "display"),
        (0x29cd74, ["ldp w3, w4, [x23, #0x20]"], "bl %#x" % L["fd_w3w4_x23"], "display"),
        (0x29cd9c, ["ldr w3, [x23, #0x20]"], "bl %#x" % L["fd_w3_x23"], "display"),
        (0x29d214, ["ldp w1, w2, [x26, #0x20]"], "bl %#x" % L["fd_w1w2_x26"], "display"),
        (0x29d22c, ["ldp w1, w2, [x26, #0x20]"], "bl %#x" % L["fd_w1w2_x26"], "display"),
        (0x29d3c4, ["ldp w1, w2, [x27, #0x20]"], "bl %#x" % L["fd_w1w2_x27"], "display"),
        (0x29d3dc, ["ldp w1, w2, [x27, #0x20]"], "bl %#x" % L["fd_w1w2_x27"], "display"),
        (0x30f9f4, ["ldp w1, w2, [x0, #0x20]"], "bl %#x" % L["fd_w1w2_x0"], "display"),
        (0x310650, ["ldp w1, w2, [x0, #0x20]"], "bl %#x" % L["fd_w1w2_x0"], "display"),
        # skill behaviour aliases
        (0x39f370, ["str x23, [sp, #-0x40]!"], "b %#x" % L["c39f370"], "skills"),
        (0x3cc8bc, ["ldr w8, [x25, #0x20]"], "bl %#x" % L["bt_x25"], "skills"),
        (0x3ccf4c, ["ldr w8, [x0, #0x20]"], "bl %#x" % L["bt_x0"], "skills"),
        (0x3cd2f8, ["ldr w8, [x0, #0x20]"], "bl %#x" % L["bt_x0"], "skills"),
        (0x3d4cf0, ["ldr w8, [x0, #0x20]"], "bl %#x" % L["bt_x0"], "skills"),
        (0x3d4fcc, ["ldr w8, [x0, #0x20]"], "bl %#x" % L["bt_x0"], "skills"),
        (0x27208c, ["ldr w8, [x21, #0x20]"], "bl %#x" % L["bt_x21"], "skills"),
        # stat hooks (crit chance replaces the BM-21 skin block)
        (0x382844, ["ldrb w8, [x19, #0xbc]", "cbz w8, #0x38287c", "ldr x8, [x19, #8]", "ldr w8, [x8, #0x38]",
                    "cmp w8, #0x35", "b.ne #0x38287c", "ldr x0, [x19, #0x70]", "cbz x0, #0x38287c",
                    "mov w1, #0x35", "mov w2, #1", "bl #0x39b1c8", "cbz x0, #0x38287c", "ldr w8, [x0, #0xc]",
                    "add w20, w8, w20"],
         "mov x0, x19; mov w1, #1; bl %#x; add w20, w20, w0; b #0x38287c" % L["ext_bonus"] + "; nop" * 9, "stats"),
        (0x383564, ["cbz w9, #0x383598"], "b #0x383598", "stats"),
        (0x38373c, ["mov w0, w19"], "b %#x" % L["tr_critdmg"], "stats"),
        (0x3841d4, ["mov w0, w19"], "b %#x" % L["tr_attack"], "stats"),
        (0x3842e4, ["mov w0, w19"], "b %#x" % L["tr_attack"], "stats"),
        (0x37d738, ["mov w0, w20"], "bl %#x" % L["tr_defence"], "stats"),
        (0x382e0c, ["cmp w19, #1"], "bl %#x" % L["tr_mobility"], "stats"),
        (0x37c3bc, ["ldr w8, [x19, #0xdc]"], "bl %#x" % L["tr_hp"], "stats"),
        (0x380850, ["ldp x29, x30, [sp, #0x20]"], "b %#x" % L["tr_range"], "stats"),
    ]
    return s


# sites whose `bl` relies on the enclosing function having saved x30 (checked by tests)
BL_SITES_FUNCS = {}

# ------------------------------------------------------------------------------------------ code generation
class _Gen:
    def __init__(self):
        self.lines = []
        self.n = 0

    def emit(self, *ls):
        for x in ls:
            self.lines.extend(x if isinstance(x, list) else [x])

    def label(self, stem):
        self.n += 1
        return "%s_%d" % (stem, self.n)


def _vecptr(g, kind, t, ds, out, fail, s1, s2):
    """out = address of vector<row*> for Type w<t> (ds = x<ds> dataSys); branch to `fail` if out of range."""
    nat, base = (SKILL_NATIVE, SKILL_OFF) if kind == "s" else (FEAT_NATIVE, FEAT_OFF)
    ext = "EXT_S" if kind == "s" else "EXT_F"
    l_ext, l_done = g.label("vx"), g.label("vd")
    g.emit("cmp w%d, #%d" % (t, nat), "b.hs %s" % l_ext,
           "mov w%d, #0x18" % s1,
           "smaddl x%d, w%d, w%d, x%d" % (out, t, s1, ds),
           "add x%d, x%d, #%d, lsl #12" % (out, out, base >> 12),
           "add x%d, x%d, #%#x" % (out, out, base & 0xfff),
           "b %s" % l_done,
           "%s:" % l_ext,
           "cmp w%d, #%d" % (t, MAX_TYPE), "b.hi %s" % fail,
           "sub w%d, w%d, #%d" % (s2, t, nat),
           "mov w%d, #0x18" % s1,
           "adrp x%d, %s@PAGE" % (out, ext),
           "add x%d, x%d, %s@PAGEOFF" % (out, out, ext),
           "umaddl x%d, w%d, w%d, x%d" % (out, s2, s1, out),
           "%s:" % l_done)


def _slot_helper(g, name, kind, t, ds, out, oob):
    """bl-called: x<out> = slot base such that [x<out> + table offset] is the vector (oob -> TRASH/EMPTY)."""
    base = SKILL_OFF if kind == "s" else FEAT_OFF
    l_fail, l_done = g.label("sf"), g.label("sd")
    g.emit("%s:" % name, "stp x16, x17, [sp, #-16]!")
    _vecptr(g, kind, t, ds, out, l_fail, 16, 17)
    g.emit("b %s" % l_done, "%s:" % l_fail,
           "adrp x%d, %s@PAGE" % (out, oob), "add x%d, x%d, %s@PAGEOFF" % (out, out, oob),
           "%s:" % l_done,
           "sub x%d, x%d, #%d, lsl #12" % (out, out, base >> 12),
           "sub x%d, x%d, #%#x" % (out, out, base & 0xfff),
           "ldp x16, x17, [sp], #16", "ret")


def _efx_scan(g, kind_imm):
    """Add matching EFX entries to w17. In: w0 type, w1 row value, w14 class bit, w16 category. Uses x2-x7."""
    l_loop, l_next, l_ok, l_add, l_end = (g.label(x) for x in ("ex", "en", "eo", "ea", "ee"))
    g.emit("adr x3, EFX", "ldr w4, [x3], #4",
           "%s:" % l_loop, "cbz w4, %s" % l_end, "sub w4, w4, #1",
           "ldrh w5, [x3]", "cmp w5, w0", "b.ne %s" % l_next,
           "ldrb w6, [x3, #2]", "cmp w6, #%d" % kind_imm, "b.ne %s" % l_next,
           "ldrb w7, [x3, #3]", "cmp w7, w16", "b.ne %s" % l_next,
           "ldrh w5, [x3, #4]", "cbz w5, %s" % l_ok, "tst w5, w14", "b.eq %s" % l_next,
           "%s:" % l_ok, "ldrb w6, [x3, #6]", "ldr w7, [x3, #8]", "tbz w6, #0, %s" % l_add, "mov w7, w1",
           "%s:" % l_add, "add w17, w17, w7",
           "%s:" % l_next, "add x3, x3, #12", "b %s" % l_loop,
           "%s:" % l_end)


def build_cave(cfg, bss_base):
    """Returns (lines, bss_layout, bss_end)."""
    n_s = MAX_TYPE + 1 - SKILL_NATIVE
    n_f = MAX_TYPE + 1 - FEAT_NATIVE
    bss = {}
    p = bss_base
    for name, size in (("EXT_S", n_s * 0x18), ("TRASH_S", 0x18), ("EXT_F", n_f * 0x18), ("TRASH_F", 0x18),
                       ("EMPTY", 0x18)):
        bss[name] = p
        p += size
    bss_end = (p + 0xff) & ~0xff

    g = _Gen()
    # ---------------------------------------------------------------- skill table accessors
    g.emit("g_skill_get:")                       # x0 ds, w1 type, w2 level -> x0 row
    _vecptr(g, "s", 1, 0, 8, "gs_null", 9, 10)
    g.emit("ldp x9, x10, [x8]", "sub x10, x10, x9", "asr x10, x10, #3", "sxtw x11, w2", "cmp x10, x11",
           "b.ls gs_null", "ldr x0, [x9, x11, lsl #3]", "ret", "gs_null:", "mov x0, xzr", "ret")
    g.emit("g_skill_maxlv:")                     # x0 ds, w1 type -> w0 levels-1
    _vecptr(g, "s", 1, 0, 8, "gm_none", 9, 10)
    g.emit("ldp x9, x10, [x8]", "sub x10, x10, x9", "lsr x10, x10, #3", "sub w0, w10, #1", "ret",
           "gm_none:", "mov w0, #-1", "ret")
    _slot_helper(g, "h_s_209974", "s", 1, 0, 8, "EMPTY")
    _slot_helper(g, "h_s_209a30", "s", 24, 22, 8, "EMPTY")
    _slot_helper(g, "h_s_load", "s", 8, 19, 11, "TRASH_S")
    g.emit("reset_s_tail:",
           "adrp x8, EXT_S@PAGE", "add x8, x8, EXT_S@PAGEOFF", "mov w9, #%d" % (n_s + 1),
           "rs_loop:", "ldr x10, [x8]", "str x10, [x8, #8]", "add x8, x8, #0x18", "subs w9, w9, #1",
           "b.ne rs_loop",
           "ldp x29, x30, [sp, #0x20]", "ldp x20, x19, [sp, #0x10]", "ldr x21, [sp], #0x30", "ret")
    # ---------------------------------------------------------------- feature table accessors
    g.emit("g_feat_get:", "tbnz w2, #31, gf_null")   # x0 ds, w1 type, w2 level -> x0 row
    _vecptr(g, "f", 1, 0, 8, "gf_null", 9, 10)
    g.emit("ldp x9, x10, [x8]", "sub x10, x10, x9", "asr x10, x10, #3", "sxtw x11, w2", "cmp x10, x11",
           "b.ls gf_null", "ldr x0, [x9, x11, lsl #3]", "ret", "gf_null:", "mov x0, xzr", "ret")
    g.emit("t_feat_tail:")                       # x0 ds, w2 type, w8 level -> x0 row
    _vecptr(g, "f", 2, 0, 9, "tf_null", 10, 11)
    g.emit("ldp x10, x11, [x9]", "sub x11, x11, x10", "asr x11, x11, #3", "sxtw x8, w8", "cmp x11, x8",
           "b.ls tf_null", "ldr x0, [x10, x8, lsl #3]", "ret", "tf_null:", "mov x0, xzr", "ret")
    _slot_helper(g, "h_f_load", "f", 8, 19, 11, "TRASH_F")
    g.emit("f_post:",                            # bl from the feature loader, row at [sp, #0x18]
           "ldr x9, [sp, #0x18]", "cbz x9, fp_done", "str wzr, [x9, #0x74]", "ldr w10, [x9, #0x20]",
           "adr x11, FALIAS", "ldr w12, [x11], #4",
           "fp_loop:", "cbz w12, fp_done", "ldrh w13, [x11], #2", "ldrh w14, [x11], #2", "sub w12, w12, #1",
           "cmp w13, w10", "b.ne fp_loop", "str w10, [x9, #0x74]", "str w14, [x9, #0x20]",
           "fp_done:", "add w21, w21, #1", "ret")
    g.emit("reset_f_tail:",
           "adrp x8, EXT_F@PAGE", "add x8, x8, EXT_F@PAGEOFF", "mov w9, #%d" % (n_f + 1),
           "rf_loop:", "ldr x10, [x8]", "str x10, [x8, #8]", "add x8, x8, #0x18", "subs w9, w9, #1",
           "b.ne rf_loop",
           "ldp x29, x30, [sp, #0x20]", "ldp x20, x19, [sp, #0x10]", "ldr x21, [sp], #0x30", "ret")
    # display type stubs: type = row+0x74 if set, else row+0x20; level = row+0x24
    for name, rt, rl, row in (("fd_w3_x23", 3, None, 23), ("fd_w3w4_x23", 3, 4, 23), ("fd_w1w2_x26", 1, 2, 26),
                              ("fd_w1w2_x27", 1, 2, 27), ("fd_w1w2_x0", 1, 2, 0)):
        l = g.label("fd")
        g.emit("%s:" % name, "ldr w%d, [x%d, #0x74]" % (rt, row), "cbnz w%d, %s" % (rt, l),
               "ldr w%d, [x%d, #0x20]" % (rt, row), "%s:" % l)
        if rl is not None:
            g.emit("ldr w%d, [x%d, #0x24]" % (rl, row))
        g.emit("ret")
    # ---------------------------------------------------------------- skill behaviour aliases
    g.emit("c39f370:",
           "str x23, [sp, #-0x40]!", "stp x22, x21, [sp, #0x10]", "stp x20, x19, [sp, #0x20]",
           "stp x29, x30, [sp, #0x30]", "add x29, sp, #0x30", "mov x20, x0", "mov w19, w1",
           "ldp x8, x9, [x0, #0xa0]",
           "cs_loop:", "cmp x8, x9", "b.hs cs_medals", "ldr x0, [x8], #8", "cbz x0, cs_loop",
           "ldr w10, [x0, #0x20]", "cmp w10, w19", "b.eq cs_found",
           "adr x11, SALIAS", "ldr w12, [x11], #4",
           "cs_al:", "cbz w12, cs_loop", "ldrh w13, [x11], #2", "ldrh w14, [x11], #2", "sub w12, w12, #1",
           "cmp w13, w10", "b.ne cs_al", "and w14, w14, #0x7fff", "cmp w14, w19", "b.ne cs_al",
           "cs_found:", "b #0x39f480",
           "cs_medals:", "b #0x39f3c8")
    g.emit("bt_x25:", "ldr w8, [x25, #0x20]", "b s_primary",
           "bt_x21:", "ldr w8, [x21, #0x20]", "b s_primary",
           "bt_x0:", "ldr w8, [x0, #0x20]", "b s_primary",
           "s_primary:",                          # w8 type -> primary base or itself; preserves everything else
           "stp x9, x10, [sp, #-16]!", "stp x11, x12, [sp, #-16]!",
           "adr x9, SALIAS", "ldr w10, [x9], #4",
           "sp_loop:", "cbz w10, sp_done", "ldrh w11, [x9], #2", "ldrh w12, [x9], #2", "sub w10, w10, #1",
           "cmp w11, w8", "b.ne sp_loop", "tbz w12, #15, sp_loop", "and w8, w12, #0x7fff",
           "sp_done:", "ldp x11, x12, [sp], #16", "ldp x9, x10, [sp], #16", "ret")
    # ---------------------------------------------------------------- stat bonus
    g.emit("ext_bonus:",                          # x0 army, w1 category -> w0; leaf, clobbers x0-x17
           "mov x15, x0", "mov w16, w1", "mov w17, wzr",
           "ldr x8, [x15, #8]", "cbz x8, eb_done",
           "ldr w9, [x8, #0x3c]", "mov w14, #1", "lsl w14, w14, w9",
           # elite skin (EliteSkinSettings rows owned by the army's country, Index 1, army code match)
           "ldrb w9, [x15, #0xbc]", "cbz w9, sk_end",
           "ldr x9, [x15, #0x70]", "cbz x9, sk_end",
           "ldr w10, [x8, #0x38]",
           "ldr x11, [x9, #0x650]", "ldr x12, [x9, #0x658]",
           "sb_loop:", "cmp x11, x12", "b.eq sk_end", "ldr x13, [x11], #8",
           "ldr w0, [x13, #4]", "cmp w0, w10", "b.ne sb_loop",
           "ldr w0, [x13, #8]", "cmp w0, #1", "b.ne sb_loop",
           "ldr w0, [x13, #0xc]", "mov w2, #1000", "udiv w3, w0, w2", "cbz w3, sb_legacy",
           "cmp w3, w16", "b.ne sk_end", "msub w0, w3, w2, w0", "add w17, w17, w0", "b sk_end",
           "sb_legacy:")
    if cfg.legacy_skins:
        g.emit("cmp w16, #1", "b.ne sb_l2", "cmp w10, #0x35", "b.eq sb_eff",
               "sb_l2:", "cmp w16, #2", "b.ne sk_end", "cmp w10, #0x31", "b.ne sk_end",
               "sb_eff:", "add w17, w17, w0")
    g.emit("sk_end:",
           "ldr x9, [x15, #0x78]", "cbz x9, eb_feats", "ldp x10, x11, [x9, #0xa0]",
           "eb_sk:", "cmp x10, x11", "b.hs eb_feats", "ldr x12, [x10], #8", "cbz x12, eb_sk",
           "ldr w0, [x12, #0x20]", "ldr w1, [x12, #0x30]")
    _efx_scan(g, 0)
    g.emit("b eb_sk",
           "eb_feats:", "ldp x10, x11, [x15, #0x30]",
           "eb_ft:", "cmp x10, x11", "b.hs eb_done", "ldr x12, [x10], #8", "cbz x12, eb_ft",
           "ldr w0, [x12, #0x74]", "cbnz w0, eb_ft_t", "ldr w0, [x12, #0x20]",
           "eb_ft_t:", "ldr w1, [x12, #0x2c]")
    _efx_scan(g, 1)
    g.emit("b eb_ft",
           "eb_done:", "mov w0, w17", "ret")
    # getter trampolines
    g.emit("tr_attack:",                          # b from min/max attack exits (x20 army, w19 value)
           "stp x29, x30, [sp, #-16]!", "mov x0, x20", "mov w1, #5", "bl ext_bonus",
           "mul w8, w19, w0", "mov w9, #100", "sdiv w8, w8, w9", "add w19, w19, w8",
           "ldp x29, x30, [sp], #16", "mov w0, w19", "ldp x20, x19, [sp], #0x20", "ret",
           "tr_critdmg:",                         # b from the crit damage exit (x20 army, w19 value)
           "stp x29, x30, [sp, #-16]!", "mov x0, x20", "mov w1, #2", "bl ext_bonus", "add w19, w19, w0",
           "ldp x29, x30, [sp], #16", "mov w0, w19", "ldp x20, x19, [sp], #0x20", "ret",
           "tr_defence:",                         # bl from the defence exit (x19 army, w20 value) -> w0
           "stp x29, x30, [sp, #-16]!", "mov x0, x19", "mov w1, #3", "bl ext_bonus", "add w0, w0, w20",
           "ldp x29, x30, [sp], #16", "ret",
           "tr_mobility:",                        # bl replacing `cmp w19, #1` (x20 army)
           "stp x29, x30, [sp, #-16]!", "cmp w19, #1", "b.lt tm_done", "mov x0, x20", "mov w1, #4",
           "bl ext_bonus", "add w19, w19, w0",
           "tm_done:", "ldp x29, x30, [sp], #16", "cmp w19, #1", "ret",
           "tr_hp:",                              # bl replacing `ldr w8, [x19, #0xdc]` (x19 army, w20 max HP)
           "stp x29, x30, [sp, #-16]!", "mov x0, x19", "mov w1, #6", "bl ext_bonus",
           "mul w8, w20, w0", "mov w9, #100", "sdiv w8, w8, w9", "add w20, w20, w8",
           "ldp x29, x30, [sp], #16", "ldr w8, [x19, #0xdc]", "ret",
           "tr_range:",                           # b replacing the range getter epilogue (x19 army, w0 range)
           "mov w20, w0", "mov x0, x19", "mov w1, #7", "bl ext_bonus", "add w0, w0, w20",
           "ldp x29, x30, [sp, #0x20]", "ldp x20, x19, [sp, #0x10]", "ldp x22, x21, [sp], #0x30", "ret")
    if cfg.tier12:
        g.emit("cave_tier12:",                    # b from 0x2345bc in the map troop loader
               "ldrb w8, [x19, #0x3a0]", "cbz w8, ct_out",
               "ldr x8, [x24, #0xe8]", "cbz x8, ct_out",
               "ldrb w8, [x8, #0x158]", "cbnz w8, ct_out",
               "ldr w9, [sp, #0x9c]", "tbnz w9, #0, ct_out",
               "ldrsh w8, [x25, #0x10]", "cmp w8, #1", "b.lt ct_out",
               "ldr x8, [x19, #8]", "ldr x0, [x8, #0x158]", "ldrsb w1, [x25, #2]", "mov w2, w26",
               "mov w3, #12", "mov w4, wzr", "bl #0x20bf40", "cbz x0, ct_out",
               "ldrb w8, [x0, #0x48]", "cbz w8, ct_out", "mov w8, #12", "str w8, [sp, #0xf0]",
               "ct_out:", "ldr w3, [sp, #0xf0]", "b #0x2345e0")
    # ---------------------------------------------------------------- data tables
    salias = []
    for s in cfg.skills:
        for i, b in enumerate(s.bases):
            prim = 0x8000 if (s.custom and i == 0) else 0
            salias.append((s.type, b | prim))
    falias = [(f.type, f.base) for f in cfg.features if f.base]
    efx = []
    for kind, items in ((0, cfg.skills), (1, cfg.features)):
        for it in items:
            for e in it.effects:
                mask = 0
                for c in e.classes:
                    mask |= 1 << c
                efx.append((it.type, kind, e.category, mask, 1 if e.from_row else 0, e.value))
    g.emit(".align 4", "SALIAS:", ".word %d" % len(salias))
    for t, b in salias:
        g.emit(".hword %d, %d" % (t, b))
    g.emit(".align 4", "FALIAS:", ".word %d" % len(falias))
    for t, b in falias:
        g.emit(".hword %d, %d" % (t, b))
    g.emit(".align 4", "EFX:", ".word %d" % len(efx))
    for t, k, c, m, fl, v in efx:
        g.emit(".hword %d" % t, ".byte %d, %d" % (k, c), ".hword %d" % m, ".byte %d, 0" % fl, ".word %d" % v)
    return g.lines, bss, bss_end


def _resolve_bss(lines, bss):
    out = []
    for ln in lines:
        for k, v in bss.items():
            ln = ln.replace(k + "@PAGEOFF", "#%#x@PAGEOFF" % v).replace(k + "@PAGE", "#%#x@PAGE" % v)
        out.append(ln)
    return out


def site_table(cfg, labels):
    sites = _sites(cfg, labels)
    if cfg.tier12:
        sites.append((0x2345bc, ["mov w8, #0"], "b %#x" % labels["cave_tier12"], "tier12"))
    return sites


def check_site(elf, addr, expect):
    cur = [arm64.disasm1(elf.read(addr + 4 * k, 4), addr + 4 * k) for k in range(len(expect))]
    return cur == expect, cur


def apply(elf, cfg, log=print):
    """Apply the engine extension to an Elf built from the base library (sites must be original)."""
    bss_base = (elf.bss_end + 0xff) & ~0xff
    lines, bss, bss_end = build_cave(cfg, bss_base)
    code, labels = arm64.assemble_program(_resolve_bss(lines, bss), CODE_BASE)
    if CODE_BASE + len(code) > CODE_LIMIT:
        raise ValueError("engine extension code too large (%d bytes)" % len(code))
    sites = site_table(cfg, labels)
    bad = []
    for addr, expect, new, grp in sites:
        ok, cur = check_site(elf, addr, expect)
        if not ok:
            bad.append("%#x: expected %s, found %s" % (addr, expect, cur))
    if bad:
        raise ValueError("library does not match the expected base at:\n  " + "\n  ".join(bad))
    elf.grow_code(CODE_BASE + ((len(code) + 0xfff) & ~0xfff))
    elf.grow_bss(bss_end)
    elf.write(CODE_BASE, code)
    for addr, expect, new, grp in sites:
        blob = arm64.assemble(new, addr)
        assert len(blob) <= 4 * len(expect), hex(addr)
        elf.write(addr, blob)
    log("engine extension: %d bytes of code at %#x, %d sites, .bss +%#x at %#x"
        % (len(code), CODE_BASE, len(sites), bss_end - bss_base, bss_base))
    return dict(code_size=len(code), labels=labels, bss=bss, sites=[(a, g) for a, _, _, g in sites])
