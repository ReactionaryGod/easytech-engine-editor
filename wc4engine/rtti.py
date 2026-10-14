"""C++ RTTI class names -> vtables -> virtual functions (needs R_AARCH64_RELATIVE relocations).

Both EasyTech libraries are stripped but keep RTTI, so class names such as `CBuffHitBonus` survive. A vtable's first
two slots are offset-to-top and the typeinfo pointer; the virtual functions follow.
"""
import re
import struct
from collections import defaultdict

R_AARCH64_RELATIVE = 1027


class Rtti:
    def __init__(self, elf, analysis):
        self.elf, self.an = elf, analysis
        self.rel = self._relocs()
        self.by_value = defaultdict(list)
        for loc, v in self.rel.items():
            self.by_value[v].append(loc)
        self._classes = None

    def _relocs(self):
        s = self.elf.section(".rela.dyn")
        rel = {}
        d = self.elf.data
        for k in range(s.sh_size // 24):
            off, info, add = struct.unpack_from("<QQq", d, s.sh_offset + 24 * k)
            if info & 0xffffffff == R_AARCH64_RELATIVE:
                rel[off] = add
        return rel

    def classes(self):
        """{name: [(typeinfo, vtable, [virtual function addresses])]}"""
        if self._classes is not None:
            return self._classes
        an, elf = self.an, self.elf
        o = elf.off(an.roa)
        blob = bytes(elf.data[o:o + an.ros])
        out = {}
        for m in re.finditer(rb"(\d+)([A-Z]\w+)\x00", blob):
            if int(m.group(1)) != len(m.group(2)):
                continue
            name_addr = an.roa + m.start()
            for loc in self.by_value.get(name_addr, []):
                ti = loc - 8
                for loc2 in self.by_value.get(ti, []):
                    vt = loc2 - 8
                    fns, p = [], vt + 16
                    while p in self.rel and an.ta <= self.rel[p] < an.ta + an.ts:
                        fns.append(self.rel[p])
                        p += 8
                    out.setdefault(m.group(2).decode(), []).append((ti, vt, fns))
        self._classes = out
        return out

    def virtual_names(self, prefix=""):
        """{function address: 'Class::vN'} for classes whose name contains `prefix`."""
        names = {}
        for cls, lst in self.classes().items():
            if prefix not in cls:
                continue
            for _ti, _vt, fns in lst:
                for i, f in enumerate(fns):
                    names.setdefault(f, "%s::v%d" % (cls, i))
        return names
