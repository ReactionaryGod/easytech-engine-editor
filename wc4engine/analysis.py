"""Static analysis of the library for the code browser: functions, strings, xrefs, call graph.

Function starts come from .eh_frame_hdr (every compiled function has an FDE). Cross references are found by
a linear sweep of .text: direct branches, and ADRP + ADD/LDR/STR pairs. Results are cached next to the editor
(keyed by the library's SHA-1) because the sweep takes ~15 s.
"""
import bisect
import hashlib
import os
import pickle
import re
import struct

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

from . import arm64

_cs = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
_cs.detail = False


def _num(s):
    s = s.strip().lstrip("#")
    return int(s, 16) if s.startswith(("0x", "-0x")) else int(s)


class Analysis:
    def __init__(self, elf, cache_dir=None):
        self.elf = elf
        self.sha1 = hashlib.sha1(bytes(elf.data)).hexdigest()
        self.cache_dir = cache_dir
        t = elf.section(".text")
        self.ta, self.ts = t.sh_addr, t.sh_size
        ro = elf.section(".rodata")
        self.roa, self.ros = ro.sh_addr, ro.sh_size
        self.funcs = self._funcs()
        self._xrefs = None
        self._calls = None
        self._strings = None
        self.names = {}

    # ----------------------------------------------------------------- functions
    def _funcs(self):
        h = self.elf.section(".eh_frame_hdr")
        o, ha = h.sh_offset, h.sh_addr
        d = self.elf.data
        n = struct.unpack_from("<I", d, o + 8)[0]
        starts = {ha + struct.unpack_from("<i", d, o + 12 + 8 * k)[0] for k in range(n)}
        return sorted(s for s in starts if self.ta <= s < self.ta + self.ts)

    def func_of(self, addr):
        k = bisect.bisect_right(self.funcs, addr) - 1
        if k < 0:
            return addr, addr + 4
        end = self.funcs[k + 1] if k + 1 < len(self.funcs) else self.ta + self.ts
        if addr >= end:          # code outside known functions (e.g. the extension cave)
            return addr & ~3, (addr & ~3) + 4
        return self.funcs[k], end

    # ----------------------------------------------------------------- caches
    def _cache(self, name, builder):
        path = None
        if self.cache_dir:
            os.makedirs(self.cache_dir, exist_ok=True)
            path = os.path.join(self.cache_dir, "%s.%s.pkl" % (self.sha1[:16], name))
            if os.path.exists(path):
                with open(path, "rb") as f:
                    return pickle.load(f)
        val = builder()
        if path:
            with open(path, "wb") as f:
                pickle.dump(val, f)
        return val

    def _sweep(self):
        refs, calls = {}, {}
        o = self.elf.off(self.ta)
        regs = {}
        for a, sz, mn, ops in _cs.disasm_lite(bytes(self.elf.data[o:o + self.ts]), self.ta):
            if mn == "adrp":
                r, imm = ops.split(", ")
                regs[r] = _num(imm)
            elif mn in ("add", "ldr", "ldrb", "ldrh", "str", "ldrsw", "ldp", "strb", "strh", "stp", "ldrsh",
                        "ldrsb") and regs:
                parts = [p.strip() for p in ops.replace("[", "").replace("]", "").replace("!", "").split(",")]
                if mn == "add" and len(parts) == 3 and parts[1] in regs and parts[2].startswith("#"):
                    refs.setdefault(regs[parts[1]] + _num(parts[2]), []).append(a)
                elif mn != "add":
                    base = parts[2] if mn in ("ldp", "stp") and len(parts) > 2 else parts[1] if len(parts) > 1 else None
                    if base in regs:
                        idx = 3 if mn in ("ldp", "stp") else 2
                        imm = _num(parts[idx]) if len(parts) > idx and parts[idx].startswith("#") else 0
                        refs.setdefault(regs[base] + imm, []).append(a)
            elif mn == "adr":
                r, imm = ops.split(", ")
                refs.setdefault(_num(imm), []).append(a)
            if mn in ("bl", "b") and ops.startswith("#0x"):
                calls.setdefault(int(ops[1:], 16), []).append(a)
            elif (mn.startswith("b.") or mn in ("cbz", "cbnz", "tbz", "tbnz")) and "#0x" in ops:
                t = int(ops.rsplit("#", 1)[1], 16)
                calls.setdefault(t, []).append(a)
            if mn in ("b", "ret", "br"):
                regs = {}
        return refs, calls

    def _ensure_sweep(self):
        if self._xrefs is None:
            self._xrefs, self._calls = self._cache("sweep", self._sweep)

    def xrefs_to(self, addr):
        """Code addresses that reference `addr` as data (ADRP pairs, ADR)."""
        self._ensure_sweep()
        return self._xrefs.get(addr, [])

    def callers(self, addr):
        """Code addresses that branch to `addr` (bl/b/conditional)."""
        self._ensure_sweep()
        return self._calls.get(addr, [])

    # ----------------------------------------------------------------- strings
    def strings(self):
        if self._strings is None:
            def build():
                out = []
                o = self.elf.off(self.roa)
                blob = bytes(self.elf.data[o:o + self.ros])
                for m in re.finditer(rb"[\x20-\x7e]{4,}\x00", blob):
                    out.append((self.roa + m.start(), m.group()[:-1].decode("ascii")))
                return out
            self._strings = self._cache("strings", build)
        return self._strings

    def find_strings(self, q, limit=200):
        q = q.lower()
        return [(a, s) for a, s in self.strings() if q in s.lower()][:limit]

    # ----------------------------------------------------------------- disassembly
    def disasm(self, start, count=None, end=None):
        if end is None:
            end = start + 4 * (count or 64)
        if not self.elf.is_exec(start):
            raise ValueError("%#x is not in executable code" % start)
        size = end - start
        o = self.elf.off(start, size)
        if o is None:
            raise ValueError("range not in file")
        return arm64.disasm(bytes(self.elf.data[o:o + size]), start)

    def annotate(self, ins):
        """Short comment for an instruction: referenced string or call target."""
        a, sz, mn, ops = ins
        tgt = arm64.branch_target(mn, ops)
        if tgt is not None:
            f0, _ = self.func_of(tgt)
            nm = self.names.get(f0)
            return ("-> %s" % nm) if nm and f0 == tgt else ""
        self._ensure_sweep()
        return ""

    def refs_in_range(self, start, end):
        """Map code address -> referenced data address, for annotation of a disassembly window."""
        self._ensure_sweep()
        out = {}
        # reverse lookup limited to the window: scan the (sorted) refs lazily
        if not hasattr(self, "_rev"):
            rev = {}
            for t, lst in self._xrefs.items():
                for a in lst:
                    rev[a] = t
            self._rev = rev
        for a in range(start, end, 4):
            t = self._rev.get(a)
            if t is not None:
                out[a] = t
        return out

    def describe_data(self, t):
        if self.roa <= t < self.roa + self.ros:
            try:
                s = self.elf.cstr(t, 120)
                if s and all(32 <= ord(c) < 127 for c in s[:40]):
                    return '"%s"' % s
            except Exception:
                pass
        return "%#x" % t
