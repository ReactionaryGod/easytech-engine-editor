"""Minimal ELF64 (AArch64, little endian) reader/editor for libworld-conqueror-4.so.

Only what the editor needs: program/section headers, vaddr <-> file offset mapping, and the two layout changes
the engine extension uses:
  * grow_code(): insert 0x10000 bytes after the R-X segment so PT_LOAD[0] can cover a 44 KiB code cave
    (vaddr == file offset is kept for PT_LOAD[0]; PT_LOAD[1] moves by 0x10000 so offset == vaddr there too);
  * grow_bss(): extend PT_LOAD[1].p_memsz so new zero-initialised globals exist after .bss.
"""
import struct

PT_LOAD, PT_DYNAMIC, PT_NOTE, PT_GNU_RELRO = 1, 2, 4, 0x6474E552
PF_X, PF_W, PF_R = 1, 2, 4


class Phdr:
    FMT = "<IIQQQQQQ"
    SIZE = 56

    def __init__(self, raw, index, pos):
        (self.p_type, self.p_flags, self.p_offset, self.p_vaddr, self.p_paddr,
         self.p_filesz, self.p_memsz, self.p_align) = struct.unpack(self.FMT, raw)
        self.index, self.pos = index, pos

    def pack(self):
        return struct.pack(self.FMT, self.p_type, self.p_flags, self.p_offset, self.p_vaddr, self.p_paddr,
                           self.p_filesz, self.p_memsz, self.p_align)


class Shdr:
    FMT = "<IIQQQQIIQQ"
    SIZE = 64

    def __init__(self, raw, index, pos):
        (self.sh_name, self.sh_type, self.sh_flags, self.sh_addr, self.sh_offset, self.sh_size,
         self.sh_link, self.sh_info, self.sh_addralign, self.sh_entsize) = struct.unpack(self.FMT, raw)
        self.index, self.pos, self.name = index, pos, ""

    def pack(self):
        return struct.pack(self.FMT, self.sh_name, self.sh_type, self.sh_flags, self.sh_addr, self.sh_offset,
                           self.sh_size, self.sh_link, self.sh_info, self.sh_addralign, self.sh_entsize)


class Elf:
    def __init__(self, data):
        self.data = bytearray(data)
        if self.data[:4] != b"\x7fELF" or self.data[4] != 2 or self.data[5] != 1:
            raise ValueError("not a 64-bit little-endian ELF file")
        if struct.unpack_from("<H", self.data, 18)[0] != 183:
            raise ValueError("not an AArch64 ELF file")
        self._parse()

    @classmethod
    def load(cls, path):
        with open(path, "rb") as f:
            return cls(f.read())

    # ------------------------------------------------------------------ parsing
    def _parse(self):
        d = self.data
        self.e_phoff = struct.unpack_from("<Q", d, 0x20)[0]
        self.e_shoff = struct.unpack_from("<Q", d, 0x28)[0]
        self.e_phentsize, self.e_phnum, self.e_shentsize, self.e_shnum, self.e_shstrndx = \
            struct.unpack_from("<HHHHH", d, 0x36)
        self.phdrs = [Phdr(bytes(d[self.e_phoff + i * Phdr.SIZE: self.e_phoff + (i + 1) * Phdr.SIZE]), i,
                           self.e_phoff + i * Phdr.SIZE) for i in range(self.e_phnum)]
        self.shdrs = []
        if self.e_shoff and self.e_shoff + self.e_shnum * Shdr.SIZE <= len(d):
            self.shdrs = [Shdr(bytes(d[self.e_shoff + i * Shdr.SIZE: self.e_shoff + (i + 1) * Shdr.SIZE]), i,
                               self.e_shoff + i * Shdr.SIZE) for i in range(self.e_shnum)]
            if self.e_shstrndx < len(self.shdrs):
                st = self.shdrs[self.e_shstrndx]
                for s in self.shdrs:
                    end = d.index(b"\0", st.sh_offset + s.sh_name)
                    s.name = d[st.sh_offset + s.sh_name:end].decode("ascii", "replace")
        self.loads = [p for p in self.phdrs if p.p_type == PT_LOAD]

    def _write_headers(self):
        struct.pack_into("<Q", self.data, 0x28, self.e_shoff)
        for p in self.phdrs:
            self.data[p.pos:p.pos + Phdr.SIZE] = p.pack()
        for s in self.shdrs:
            s.pos = self.e_shoff + s.index * Shdr.SIZE
            self.data[s.pos:s.pos + Shdr.SIZE] = s.pack()

    # ------------------------------------------------------------------ queries
    def section(self, name):
        for s in self.shdrs:
            if s.name == name:
                return s
        return None

    def off(self, vaddr, size=1):
        """File offset of a virtual address (only bytes backed by the file)."""
        for p in self.loads:
            if p.p_vaddr <= vaddr and vaddr + size <= p.p_vaddr + p.p_filesz:
                return p.p_offset + (vaddr - p.p_vaddr)
        return None

    def vaddr(self, offset):
        for p in self.loads:
            if p.p_offset <= offset < p.p_offset + p.p_filesz:
                return p.p_vaddr + (offset - p.p_offset)
        return None

    def is_exec(self, vaddr):
        for p in self.loads:
            if p.p_vaddr <= vaddr < p.p_vaddr + p.p_memsz:
                return bool(p.p_flags & PF_X)
        return False

    def read(self, vaddr, size):
        o = self.off(vaddr, size)
        if o is None:
            raise ValueError("address %#x+%d is not file-backed" % (vaddr, size))
        return bytes(self.data[o:o + size])

    def write(self, vaddr, blob):
        o = self.off(vaddr, len(blob))
        if o is None:
            raise ValueError("address %#x+%d is not file-backed" % (vaddr, len(blob)))
        self.data[o:o + len(blob)] = blob

    def u32(self, vaddr):
        return struct.unpack("<I", self.read(vaddr, 4))[0]

    def cstr(self, vaddr, limit=512):
        o = self.off(vaddr)
        end = self.data.find(b"\0", o, o + limit)
        return self.data[o:end if end >= 0 else o + limit].decode("utf-8", "replace")

    @property
    def text(self):
        return self.loads[0]

    @property
    def code_end(self):
        """End of the executable mapping (vaddr)."""
        return self.loads[0].p_vaddr + self.loads[0].p_filesz

    @property
    def bss_end(self):
        p = self.loads[-1]
        return p.p_vaddr + p.p_memsz

    # ------------------------------------------------------------------ layout changes
    GROW = 0x10000

    def is_grown(self):
        """True when PT_LOAD[1] already has offset == vaddr (code area inserted)."""
        return self.loads[1].p_offset == self.loads[1].p_vaddr

    def grow_code(self, new_text_end):
        """Make PT_LOAD[0] (R-X) end at new_text_end. If needed, first insert GROW bytes of zeros
        at the end of PT_LOAD[0]'s page so that the file grows instead of overlapping PT_LOAD[1]."""
        l0, l1 = self.loads[0], self.loads[1]
        assert l0.p_offset == 0 and l0.p_vaddr == 0 and l0.p_flags == PF_R | PF_X, "unexpected PT_LOAD[0]"
        if not self.is_grown():
            gap = l1.p_vaddr - l1.p_offset
            assert gap == self.GROW, "PT_LOAD[1] offset/vaddr gap is %#x, expected %#x" % (gap, self.GROW)
            ins = (l0.p_filesz + 0xfff) & ~0xfff      # insertion point: first page after the R-X data
            assert ins <= l1.p_offset
            assert not any(self.data[l0.p_filesz:ins]), "padding after PT_LOAD[0] is not empty"
            self.data[ins:ins] = bytes(self.GROW)
            for p in self.phdrs:
                if p.p_offset >= ins:
                    p.p_offset += self.GROW
            for s in self.shdrs:
                if s.sh_offset >= ins:
                    s.sh_offset += self.GROW
            if self.e_shoff >= ins:
                self.e_shoff += self.GROW
        limit = self.loads[1].p_vaddr & ~0xffff            # stay below PT_LOAD[1]'s 64 KiB page
        assert new_text_end <= limit, "code area would overlap PT_LOAD[1] (%#x > %#x)" % (new_text_end, limit)
        if new_text_end > l0.p_filesz:
            l0.p_filesz = l0.p_memsz = new_text_end
        self._write_headers()
        self._parse()

    def grow_bss(self, new_end):
        l1 = self.loads[-1]
        if new_end > l1.p_vaddr + l1.p_memsz:
            l1.p_memsz = new_end - l1.p_vaddr
            self._write_headers()
            self._parse()
