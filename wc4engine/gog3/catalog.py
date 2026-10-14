"""Engine catalog for Glory of Generals 3: where libiron.so implements each Buff Type.

Two sources:
  * switches whose selector is loaded from `[row, #0xc]` (BuffSettings.Type): every case is decoded into a short
    mechanism ("adds Value to +0x44", "sets flag 0x4 in +0x20", "scales +0x58 by 1+Value/100");
  * compare constants inside the virtual functions of the CBuff* classes (RTTI) for phases that are not switches
    (damage taken, before/after hit, auras).
"""
import re

from .. import arm64, catalog as wc4catalog
from ..rtti import Rtti
from . import buff_types


def _mechanism(an, target):
    """Describe a switch case from its first instructions."""
    try:
        ins = an.disasm(target, 6)
    except ValueError:
        return ""
    txt = [(i[2], i[3]) for i in ins]
    slot = None
    for mn, ops in txt:
        m = re.search(r"\[x0, #(0x[0-9a-f]+)\]", ops)
        if m:
            slot = m.group(1)
            break
    mns = [m for m, _ in txt]
    if "orr" in mns:
        mask = next(o for m, o in txt if m == "orr").rsplit("#", 1)[1]
        return "sets flag %s in +%s" % (mask, slot)
    if ("fmul" in mns or "fdiv" in mns) and slot:
        return "scales +%s by (1 + Value/100)" % slot
    if "add" in mns and slot:
        return "adds Value to +%s" % slot
    if "cmp" in mns and slot:
        return "raises +%s to at least Value" % slot
    return ""


def build(an):
    """Returns {type: [dict(addr, func, func_name, kind, note)]} (cached in the analysis cache)."""
    def make():
        rt = Rtti(an.elf, an)
        vnames = rt.virtual_names("Buff")
        for f, n in rt.virtual_names("Entity").items():
            vnames.setdefault(f, n)
        out = {}

        def add(t, addr, kind, note):
            f0, _ = an.func_of(addr)
            out.setdefault(t, []).append(dict(addr=addr, func=f0, func_name=vnames.get(f0, ""), kind=kind, note=note))

        o = an.elf.off(an.ta)
        brs = [a for a, _sz, mn, ops in arm64._cs.disasm_lite(bytes(an.elf.data[o:o + an.ts]), an.ta)
               if mn == "br" and ops.startswith("x") and ops != "x30"]
        buff_virtuals = [f for f, n in vnames.items() if "Buff" in n and "Entity" not in n]

        def near_buff_code(addr):
            f0 = an.func_of(addr)[0]
            return any(abs(f0 - v) <= 0x1000 for v in buff_virtuals)

        for br in brs:
            if not near_buff_code(br):
                continue                            # other tables that happen to switch on a field at +0xc
            win = an.disasm(br - 44, end=br + 4)
            if not any(re.match(r"w\d+, \[x\d+, #0xc\]$", i[3]) and i[2] == "ldr" for i in win):
                continue
            for t, tgt in wc4catalog._switch_cases(an, br).items():
                add(t, tgt, "switch", _mechanism(an, tgt))
        # compare constants in the virtuals of the buff classes
        for f, name in vnames.items():
            if "Buff" not in name:
                continue
            f0, f1 = an.func_of(f)
            if any(i[2] == "br" and i[3].startswith("x") for i in an.disasm(f0, end=f1)):
                continue                            # switch functions are handled above
            for a, _sz, mn, ops in an.disasm(f0, end=f1):
                m = re.match(r"w\d+, (?:w\d+, )?#(0x[0-9a-f]+|\d+)$", ops)
                if mn in ("cmp", "sub") and m and int(m.group(1), 0) >= 36:
                    t = int(m.group(1), 0)
                    if t in buff_types.BUFF_TYPES:
                        add(t, a, "compare", "checked in %s" % name)
        for t in out:
            out[t].sort(key=lambda u: (u["kind"] != "switch", u["addr"]))
        return out
    return an._cache("gog3catalog2", make)
