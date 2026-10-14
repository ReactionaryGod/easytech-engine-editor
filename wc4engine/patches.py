"""Named engine patches: what they do, how to detect them in any library, and how to apply them to the base.

The base library is the one shipped in the APK (World Conqueror 4 1.30.0, already a "Play Mod" repack with the
challenge-cap removal and the General Bank patch). Every build starts from it, so patches are deterministic.
"""
import hashlib

from . import arm64, framework

BASE_SHA1 = "a7a602a823ec"          # first 12 hex digits of the APK library's SHA-1

CHALLENGE_SITE = 0x2345bc
CHALLENGE_STATES = {
    "vanilla": ("ldrb w8, [x19, #0x3a0]", "Vanilla caps: in challenge conquests (1939-1980 challenge) the player's "
                "units are clamped to low tiers and their generals' medals/ribbons start at level 1."),
    "removed": ("mov w8, #0", "Caps removed (Play Mod): the player's map units keep the tier and medal levels "
                "written in the .btl."),
    "tier12": (None, "Caps removed, and in a new challenge game the player's elite troops that have a general use "
               "their tier-12 ArmySettings row (uncommanded elites keep the map tier). Needs the engine extension."),
}

MF_SITES = [(0x2cc598, "b.eq #0x2cc604", "conquest country picker"),
            (0x2b2b08, "b.eq #0x2b2b94", "second conquest map scene")]

BANK_SITES = [0x2a5568, 0x3085b8, 0x308f44, 0x308f58, 0x3093e4, 0x3093f8, 0x308bc0]


def sha1(data):
    return hashlib.sha1(bytes(data)).hexdigest()


def detect(elf):
    """Describe which known patches a library contains."""
    out = {}
    d1 = lambda a: arm64.disasm1(elf.read(a, 4), a)        # noqa: E731
    cur = d1(CHALLENGE_SITE)
    if cur == CHALLENGE_STATES["vanilla"][0]:
        out["challenge"] = "vanilla"
    elif cur == CHALLENGE_STATES["removed"][0]:
        out["challenge"] = "removed"
    elif cur.startswith("b "):
        out["challenge"] = "tier12"
    else:
        out["challenge"] = "unknown: " + cur
    mf = [d1(a) for a, _, _ in MF_SITES]
    out["mf_picker"] = "unlocked" if all(x == "nop" for x in mf) else \
        "vanilla" if mf == [e for _, e, _ in MF_SITES] else "mixed: %s" % mf
    out["general_bank"] = "patched" if d1(0x3085b8) == "b #0x202e68" else "vanilla"
    ext = d1(0x39f370)
    if ext.startswith("b #") and int(ext[3:], 16) >= framework.CODE_BASE:
        out["engine_ext"] = "engine extension (this editor)"
    elif d1(0x382844).startswith("mov x0, x19") and d1(0x382844 + 8).startswith("bl #0xa14"):
        out["engine_ext"] = "elite-skin patch of 2026-10-13 (patch_so.py)"
    else:
        out["engine_ext"] = "none"
    out["grown"] = elf.is_grown()
    out["sha1"] = sha1(elf.data)
    out["is_base"] = out["sha1"].startswith(BASE_SHA1)
    return out


PATCH_INFO = [
    dict(id="general_bank", name="General Bank slot limit", builtin=True,
         desc="CorpsSettings.SeniorSeat above 31 overflowed the General Bank scene's seat table. The scene object "
              "is enlarged and the seat builder is replaced by a bounds-checked copy in dead code at 0x202e68 "
              "(supports up to 256 seats). Already present in the APK library, so every build keeps it.",
         sites=BANK_SITES),
    dict(id="challenge", name="Challenge conquest player caps",
         desc="Loader 0x2345bc decides whether the player's units in challenge conquests (ConquerSettings "
              "Difficulty != 0) are restricted.", sites=[CHALLENGE_SITE]),
    dict(id="mf_picker", name="Mysterious Forces selectable in conquest",
         desc="The conquest map tap handler ignores CountrySettings Id 48. Two `b.eq` are NOPed so Mysterious "
              "Forces can be picked (it still needs a capital entry in the conquest .btl).",
         sites=[a for a, _, _ in MF_SITES]),
    dict(id="engine_ext", name="Engine extension (skills, perks, stat effects, elite skins)",
         desc="Code cave after the R-X segment (the file grows by 64 KiB, PT_LOAD[0] covers it) plus new .bss "
              "tables. Adds new skill and perk Types, behaviour aliases, generic stat effects, the data-driven "
              "elite-skin effects of 2026-10-13, and the optional tier-12 challenge rule.",
         sites=[]),
]


def apply_simple(elf, challenge="removed", mf_picker=True, log=print):
    """Patches that are plain instruction swaps (run before the engine extension)."""
    cur = arm64.disasm1(elf.read(CHALLENGE_SITE, 4), CHALLENGE_SITE)
    if challenge in ("vanilla", "removed"):
        want = CHALLENGE_STATES[challenge][0]
        if cur != want:
            elf.write(CHALLENGE_SITE, arm64.assemble(want, CHALLENGE_SITE))
            log("challenge caps: %s -> %s" % (cur, want))
    elif challenge == "tier12":
        if cur != "mov w8, #0":                     # the framework expects the Play Mod instruction
            elf.write(CHALLENGE_SITE, arm64.assemble("mov w8, #0", CHALLENGE_SITE))
    for a, orig, what in MF_SITES:
        cur = arm64.disasm1(elf.read(a, 4), a)
        if mf_picker and cur == orig:
            elf.write(a, arm64.NOP)
            log("Mysterious Forces picker: NOP at %#x (%s)" % (a, what))
        elif not mf_picker and cur == "nop":
            elf.write(a, arm64.assemble(orig, a))
            log("Mysterious Forces picker: restored %s at %#x" % (orig, a))


def apply_asm_patches(elf, patches, log=print):
    """User patches from the code browser: dict(addr, hex, orig, note, enabled)."""
    for p in patches:
        if not p.get("enabled", True):
            continue
        a = int(p["addr"], 16) if isinstance(p["addr"], str) else p["addr"]
        new = bytes.fromhex(p["hex"])
        orig = bytes.fromhex(p["orig"]) if p.get("orig") else None
        if framework.CODE_BASE <= a < framework.CODE_LIMIT:
            raise ValueError("patch at %#x is inside the engine-extension cave" % a)
        cur = elf.read(a, len(new))
        if orig is not None and cur != orig and cur != new:
            raise ValueError("patch '%s' at %#x: expected original bytes %s, found %s"
                             % (p.get("note", ""), a, orig.hex(), cur.hex()))
        elf.write(a, new)
        log("asm patch %#x (%d bytes): %s" % (a, len(new), p.get("note", "")))
