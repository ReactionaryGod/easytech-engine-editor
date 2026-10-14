"""Thin wrappers around capstone (disassembly) and keystone (assembly) for AArch64."""
import re
import struct

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
from keystone import Ks, KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN, KsError

_cs = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
_cs.detail = False
_ks = Ks(KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN)


class AsmError(Exception):
    pass


def disasm(blob, addr):
    """List of (address, size, mnemonic, op_str); undecodable words become `.word`."""
    out, pos = [], 0
    while pos < len(blob):
        got = False
        for a, sz, mn, ops in _cs.disasm_lite(blob[pos:], addr + pos):
            out.append((a, sz, mn, ops))
            pos += sz
            got = True
        if pos < len(blob):
            w = blob[pos:pos + 4]
            out.append((addr + pos, len(w), ".word", "%#010x" % struct.unpack("<I", w.ljust(4, b"\0"))[0]))
            pos += 4
        if not got and pos >= len(blob):
            break
    return out


def disasm1(word_bytes, addr):
    r = disasm(word_bytes[:4], addr)
    return (r[0][2] + " " + r[0][3]).strip() if r else ""


def assemble(src, addr):
    """Assemble `src` (keystone syntax, `;` or newlines between instructions, absolute branch targets)."""
    lines = []
    for ln in src.replace(";", "\n").split("\n"):
        ln = ln.split("//")[0].strip()
        if ln:
            lines.append(ln)
    if not lines:
        return b""
    try:
        enc, _ = _ks.asm("\n".join(lines), addr)
    except KsError as e:
        raise AsmError(str(e))
    if enc is None:
        raise AsmError("nothing assembled")
    return bytes(enc)


def assemble_program(lines, base):
    """Assemble a label-carrying program (one instruction or `label:` per line) at `base`.
    Returns (code, labels). `.word N`, `.hword N`, `.byte N` and `.align N` (power of two) are supported for data."""
    clean = []
    for ln in lines:
        ln = ln.split("//")[0].strip()
        if ln:
            clean.append(ln)
    # pass 1: sizes
    labels, pc = {}, base
    for ln in clean:
        if ln.endswith(":"):
            labels[ln[:-1]] = pc
        else:
            pc += _size(ln, pc)
    # pass 2: encode piecewise with labels resolved to absolute addresses
    out = bytearray()
    pc = base
    for ln in clean:
        if ln.endswith(":"):
            continue
        sz = _size(ln, pc)
        d = _directive(ln, pc)
        m = re.match(r"adr\s+x(\d+),\s*([A-Za-z_]\w*)$", ln)
        if d is not None:
            out += d
        elif m and m.group(2) in labels:      # keystone cannot encode adr to an absolute target
            out += enc_adr(pc, int(m.group(1)), labels[m.group(2)])
        else:
            src = _subst(ln, labels)
            try:
                enc = assemble(src, pc)
            except AsmError as e:
                raise AsmError("%s (line %r -> %r at %#x)" % (e, ln, src, pc))
            if len(enc) != 4:
                raise AsmError("%s -> %d bytes" % (ln, len(enc)))
            out += enc
        assert len(out) == pc + sz - base, ln
        pc += sz
    return bytes(out), labels


def _directive(ln, pc):
    if ln.startswith(".word"):
        return b"".join(struct.pack("<i" if int(v, 0) < 0 else "<I", int(v, 0)) for v in ln[5:].split(","))
    if ln.startswith(".hword"):
        return b"".join(struct.pack("<H", int(v, 0) & 0xffff) for v in ln[6:].split(","))
    if ln.startswith(".byte"):
        return bytes(int(v, 0) & 0xff for v in ln[5:].split(","))
    if ln.startswith(".align"):
        a = int(ln[6:], 0)
        return bytes((-pc) % a)
    return None


def _size(ln, pc):
    d = _directive(ln, pc)
    return len(d) if d is not None else 4


_LABEL_RE = re.compile(r"(?<![\w#.])([A-Za-z_][A-Za-z0-9_]*)(?![\w(])")
_REGS = re.compile(r"^(x\d+|w\d+|sp|xzr|wzr|lsl|lsr|asr|sxtw|uxtw|sxtb|uxtb|sxth|uxth|eq|ne|hs|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le|al|nv|cs|cc|s\d+|d\d+|q\d+|v\d+)$")


def _subst(ln, labels):
    if " " not in ln:
        return ln
    mn, ops = ln.split(None, 1)

    def rep(m):
        name = m.group(1)
        if name in labels and not _REGS.match(name):
            return "#%#x" % labels[name]
        return name
    ops = _LABEL_RE.sub(rep, ops)
    # adrp/add helpers: name@PAGE / name@PAGEOFF
    ops = re.sub(r"#(0x[0-9a-f]+)@PAGEOFF", lambda m: "#%#x" % (int(m.group(1), 16) & 0xfff), ops)
    ops = re.sub(r"#(0x[0-9a-f]+)@PAGE", lambda m: "#%#x" % (int(m.group(1), 16) & ~0xfff), ops)
    return mn + " " + ops


# ---------------------------------------------------------------- small encoders (used for site patches)
def enc_b(pc, target):
    return struct.pack("<I", 0x14000000 | (((target - pc) >> 2) & 0x3ffffff))


def enc_adr(pc, rd, target):
    imm = target - pc
    assert -(1 << 20) <= imm < (1 << 20), "adr out of range"
    imm &= 0x1fffff
    return struct.pack("<I", 0x10000000 | ((imm & 3) << 29) | ((imm >> 2) << 5) | rd)


def enc_bl(pc, target):
    return struct.pack("<I", 0x94000000 | (((target - pc) >> 2) & 0x3ffffff))


NOP = bytes.fromhex("1f2003d5")


def branch_target(mn, ops):
    """Absolute target of a direct branch, or None."""
    if mn in ("b", "bl") or mn.startswith("b."):
        m = re.match(r"#(0x[0-9a-f]+)$", ops)
        return int(m.group(1), 16) if m else None
    if mn in ("cbz", "cbnz"):
        m = re.search(r"#(0x[0-9a-f]+)$", ops)
        return int(m.group(1), 16) if m else None
    if mn in ("tbz", "tbnz"):
        m = re.search(r"#(0x[0-9a-f]+)$", ops)
        return int(m.group(1), 16) if m else None
    return None
