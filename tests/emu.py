"""Unicorn harness: map a built libworld-conqueror-4.so and call single functions with fake game objects."""
import struct

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_PROT_ALL
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_PC,
                                 UC_ARM64_REG_X29, UC_ARM64_REG_CPACR_EL1)

STACK, STACK_SIZE = 0x7f000000, 0x100000
HEAP, HEAP_SIZE = 0x60000000, 0x400000
SENTINEL = 0x7e000000


def xreg(n):
    return UC_ARM64_REG_X0 + n if n <= 28 else {29: UC_ARM64_REG_X29, 30: UC_ARM64_REG_LR}[n]


class Emu:
    def __init__(self, elf):
        self.elf = elf
        self.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        top = (elf.bss_end + 0xffff) & ~0xffff
        self.uc.mem_map(0, top, UC_PROT_ALL)
        for p in elf.loads:
            self.uc.mem_write(p.p_vaddr, bytes(elf.data[p.p_offset:p.p_offset + p.p_filesz]))
        self.uc.mem_map(STACK, STACK_SIZE, UC_PROT_ALL)
        self.uc.mem_map(HEAP, HEAP_SIZE, UC_PROT_ALL)
        self.uc.mem_map(SENTINEL, 0x1000, UC_PROT_ALL)
        self.uc.mem_write(SENTINEL, bytes.fromhex("c0035fd6"))      # ret (never executed)
        self.uc.reg_write(UC_ARM64_REG_CPACR_EL1, 0x300000)         # enable FP/SIMD
        self.brk = HEAP

    # ----------------------------------------------------------------- memory helpers
    def alloc(self, size, align=16):
        self.brk = (self.brk + align - 1) & ~(align - 1)
        p = self.brk
        self.brk += size
        self.uc.mem_write(p, bytes(size))
        return p

    def w32(self, a, v):
        self.uc.mem_write(a, struct.pack("<i" if v < 0 else "<I", v))

    def w64(self, a, v):
        self.uc.mem_write(a, struct.pack("<Q", v))

    def w8(self, a, v):
        self.uc.mem_write(a, bytes([v & 0xff]))

    def r32(self, a):
        return struct.unpack("<i", self.uc.mem_read(a, 4))[0]

    def r64(self, a):
        return struct.unpack("<Q", self.uc.mem_read(a, 8))[0]

    def vector(self, ptrs):
        """Allocate a pointer array, return (begin, end)."""
        b = self.alloc(max(8, 8 * len(ptrs)))
        for i, p in enumerate(ptrs):
            self.w64(b + 8 * i, p)
        return b, b + 8 * len(ptrs)

    def set_vec(self, at, ptrs, cap_extra=0):
        b, e = self.vector(ptrs)
        self.w64(at, b)
        self.w64(at + 8, e)
        self.w64(at + 16, e + 8 * cap_extra)

    # ----------------------------------------------------------------- calls
    def call(self, addr, regs=None, until=SENTINEL, max_insn=200000):
        sp = STACK + STACK_SIZE - 0x1000
        for i in range(31):
            self.uc.reg_write(xreg(i), 0)
        self.uc.reg_write(UC_ARM64_REG_SP, sp)
        self.uc.reg_write(UC_ARM64_REG_LR, SENTINEL)
        for k, v in (regs or {}).items():
            self.uc.reg_write(xreg(int(k[1:])), v & 0xffffffffffffffff)
        self.uc.emu_start(addr, until, count=max_insn)
        pc = self.uc.reg_read(UC_ARM64_REG_PC)
        if pc != until:
            raise RuntimeError("stopped at %#x (expected %#x)" % (pc, until))
        return self.uc.reg_read(UC_ARM64_REG_X0)

    def reg(self, n):
        return self.uc.reg_read(xreg(n))

    def sp(self):
        return self.uc.reg_read(UC_ARM64_REG_SP)
