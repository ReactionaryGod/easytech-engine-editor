"""Where the engine hard-codes each skill Type and feature (perk) Type.

Three kinds of evidence are collected from the code:
  * query  - a call to a by-type lookup with a constant Type (general skill 0x39f370, feature 0x37c880 ...);
  * switch - a jump-table / compare-chain case on a row's Type (general skill slots in the damage code);
  * inline - `ldr wT, [row, #0x20]; cmp wT, #Type` on rows taken from the army feature vector (+0x30) or the
             general skill vector (+0xa0), the usual inlined loop.
The catalog is approximate (a site may also be reached for unrelated objects) but every entry is a real
instruction the user can open in the code browser.
"""
import re

from . import arm64

SKILL_QUERIES = {
    0x39f370: ("w1", "general has skill Type (returns the row)"),
}
FEATURE_QUERIES = {
    0x37c880: ("w1", "army feature by Type"),
    0x37e624: ("w1", "army active feature by Type"),
    0x20bb98: ("w1", "feature row by Type/level"),
    0x20bbd8: ("w2", "unit settings list Type"),
    0x20c208: ("w2", "unit settings list Type"),
}
# general skill-slot dispatchers (row Type in w8 after `bl 0x39f30c`)
SKILL_SWITCHES = [0x3cc8d8, 0x3ccf68, 0x3cd314, 0x3d4ff0, 0x2720a4]   # last: aura skills (AurasRange)
SKILL_CMP_CHAINS = [0x3d4cf0]
FEATURE_SWITCHES = [0x3cb104, 0x3d4970]

KNOWN_FUNCS = {
    0x3c9928: "combat: counter-attack / crit rolls",
    0x3cd484: "damage calculation",
    0x3d7e18: "attack resolution and after-attack effects",
    0x3cc828: "damage % bonuses (general skills)",
    0x3cd2a4: "terrain / HP-state damage bonuses",
    0x3d4c1c: "damage reduction / dodge",
    0x3d4364: "feature damage modifiers",
    0x3d353c: "critical attack",
    0x3caf34: "feature effects on attack",
    0x38272c: "crit chance getter",
    0x38332c: "crit damage getter",
    0x3840d0: "min attack getter",
    0x3841e0: "max attack getter",
    0x3842f0: "attack modifiers",
    0x37d1bc: "defence getter",
    0x382b10: "mobility getter",
    0x37c16c: "max HP getter",
    0x3803dc: "max range getter",
    0x384f18: "ignore-defence %",
    0x386ad4: "counter-attack modifiers",
    0x3a1544: "crit chance from general",
    0x3a1a74: "crit damage from general",
    0x392a70: "income bonuses",
    0x37a504: "unit turn start (healing)",
    0x3b74c0: "AI attack evaluation",
    0x26c838: "UI",
    0x271fdc: "aura skills on nearby units",
}


def _num(s):
    s = s.strip().lstrip("#")
    return int(s, 0)


def _const_arg(an, site, reg):
    """Constant loaded into `reg` (w1/w2) shortly before `site`."""
    try:
        ins = an.disasm(max(site - 48, an.func_of(site)[0]), end=site)
    except ValueError:
        return None
    for a, sz, mn, ops in reversed(ins):
        if ops.startswith(reg + ",") or ops.startswith("x" + reg[1:] + ","):
            m = re.match(r"[wx]\d+, (?:wzr, )?#(0x[0-9a-f]+|\d+)$", ops)
            if mn in ("mov", "orr") and m:
                return int(m.group(1), 0)
            return None
        if mn in ("bl", "blr", "b", "ret", "br"):
            return None
    return None


def _func_label(an, addr):
    f0, _ = an.func_of(addr)
    return f0, KNOWN_FUNCS.get(f0, "")


def _switch_cases(an, br):
    """Decode `sub wI, wT, #lo; cmp wI, #n; b.hi def; ldrsw x8, [xB, xI, lsl #2]; add x8, x8, xB; br x8`."""
    f0, _ = an.func_of(br)
    win = an.disasm(br - 44, end=br + 4)
    lo, n, default, base_reg = 0, None, None, None
    for a, sz, mn, ops in win:
        if mn == "sub" and ops.count("#") == 1 and not ops.startswith("sp"):
            lo = _num(ops.rsplit("#", 1)[1])
        elif mn == "cmp" and "#" in ops:
            n = _num(ops.rsplit("#", 1)[1])
        elif mn == "b.hi":
            default = int(ops.lstrip("#"), 16)
        elif mn == "ldrsw" and "lsl #2" in ops:
            base_reg = ops.split("[")[1].split(",")[0]
    if n is None or base_reg is None:
        return {}
    table = None
    refs = an.refs_in_range(f0, br)
    for a in sorted(refs, reverse=True):
        ins = an.disasm(a, 1)[0]
        if ins[2] == "add" and ins[3].startswith(base_reg + ","):
            table = refs[a]
            break
    if table is None:
        return {}
    out = {}
    for i in range(n + 1):
        off = int.from_bytes(an.elf.read(table + 4 * i, 4), "little", signed=True)
        tgt = table + off
        if tgt != default:
            out[lo + i] = tgt
    return out


def _cmp_chain(an, site):
    """`ldr w8, [row, #0x20]` followed by cmp w8,#imm / b.cond chains."""
    out = {}
    for a, sz, mn, ops in an.disasm(site + 4, 48):
        m = re.match(r"w8, #(0x[0-9a-f]+|\d+)$", ops)
        if mn == "cmp" and m:
            out[int(m.group(1), 0)] = a
        elif ops.startswith("w8,") and mn != "cmp":
            break
        elif mn in ("ret", "br"):
            break
    return out


def _inline_scan(an):
    """Inline Type comparisons on rows read from army+0x30 (features) or general+0xa0 (skills)."""
    elf = an.elf
    o = elf.off(an.ta)
    res = {"skill": {}, "feature": {}}
    it = {}      # iterator register -> kind
    rows = {}    # row register -> kind
    types = {}   # w register -> kind
    fi = 0
    funcs = an.funcs
    for a, sz, mn, ops in arm64._cs.disasm_lite(bytes(elf.data[o:o + an.ts]), an.ta):
        while fi < len(funcs) and funcs[fi] <= a:
            it.clear(); rows.clear(); types.clear()
            fi += 1
        parts = [p.strip() for p in ops.replace("[", "").replace("]", "").replace("!", "").split(",")]
        dst = parts[0] if parts else ""
        if mn == "ldp" and len(parts) >= 4 and parts[3] in ("#0x30", "#0xa0"):
            k = "feature" if parts[3] == "#0x30" else "skill"
            it[parts[0]] = k
            for r in parts[:2]:
                rows.pop(r, None); types.pop("w" + r[1:], None)
            continue
        if mn == "ldr" and len(parts) >= 2 and parts[1] in it and dst.startswith("x"):
            rows[dst] = it[parts[1]]
            types.pop("w" + dst[1:], None)
            continue
        if mn == "ldr" and len(parts) == 3 and parts[1] in rows and parts[2] == "#0x20" and dst.startswith("w"):
            types[dst] = rows[parts[1]]
            continue
        if mn == "cmp" and dst in types and len(parts) == 2 and parts[1].startswith("#"):
            res[types[dst]].setdefault(_num(parts[1]), []).append(a)
            continue
        # any other write kills tracking of the destination register
        if dst and mn not in ("cmp", "cmn", "tst", "str", "strb", "strh", "stp", "b", "bl", "cbz", "cbnz",
                              "tbz", "tbnz", "ret", "br", "blr") and not mn.startswith("b."):
            x = "x" + dst[1:] if dst[:1] in "wx" else dst
            it.pop(x, None); rows.pop(x, None); types.pop("w" + x[1:], None)
        if mn in ("bl", "blr"):
            for r in list(rows) + list(it):
                if r in ("x0", "x1", "x2", "x3", "x4", "x5", "x6", "x7", "x8", "x9", "x10", "x11", "x12",
                         "x13", "x14", "x15", "x16", "x17"):
                    rows.pop(r, None); it.pop(r, None)
            for r in list(types):
                if int(r[1:]) <= 17:
                    types.pop(r)
    return res


def build(an):
    """Returns {"skill": {type: [usage...]}, "feature": {...}} where usage = dict(addr, func, kind, note)."""
    def make():
        out = {"skill": {}, "feature": {}}

        def add(kind, t, addr, how, note=""):
            f0, fname = _func_label(an, addr)
            out[kind].setdefault(t, []).append(dict(addr=addr, func=f0, func_name=fname, kind=how, note=note))

        for fn, (reg, note) in SKILL_QUERIES.items():
            for s in an.callers(fn):
                t = _const_arg(an, s, reg)
                if isinstance(t, int):
                    add("skill", t, s, "query", note)
        for fn, (reg, note) in FEATURE_QUERIES.items():
            for s in an.callers(fn):
                t = _const_arg(an, s, reg)
                if isinstance(t, int):
                    add("feature", t, s, "query", note)
        for br in SKILL_SWITCHES:
            for t, tgt in _switch_cases(an, br).items():
                add("skill", t, tgt, "switch", "case in general-skill dispatcher at %#x" % br)
        for site in SKILL_CMP_CHAINS:
            for t, a in _cmp_chain(an, site).items():
                add("skill", t, a, "switch", "compare chain at %#x" % site)
        for br in FEATURE_SWITCHES:
            for t, tgt in _switch_cases(an, br).items():
                add("feature", t, tgt, "switch", "case in feature dispatcher at %#x" % br)
        inl = _inline_scan(an)
        for kind in ("skill", "feature"):
            for t, sites in inl[kind].items():
                for s in sites:
                    add(kind, t, s, "inline", "inlined Type check")
        for kind in out:
            for t in out[kind]:
                out[kind][t].sort(key=lambda u: u["addr"])
        return out
    return an._cache("catalog2", make)
