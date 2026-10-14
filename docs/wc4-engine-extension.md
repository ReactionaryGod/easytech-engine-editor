# World Conqueror 4 1.30.0: the engine extension

Library: `libworld-conqueror-4.so` (arm64). Addresses are vaddr = file offset in `PT_LOAD[0]`.

## What the engine does

- `CDataSystem` keeps one `vector<row*>` per **skill Type** (`dataSys+0x1bb8`, 24-byte slots, Types 0-191) and per
  **feature (perk) Type** (`dataSys+0x2dc8`, Types 1-166). Rows are loaded by `0x1e8f44` / `0x1ebc64`, found by
  `0x209940` (skill) and `0x20bb98` / `0x20bbd8` / `0x20c208` (feature). A Type past the end overwrote the next field.
- A general's skills are rows in `general+0xa0`. `0x39f370` (233 call sites) answers "does the general have skill
  Type T"; damage code also dispatches on the slot's Type through five jump tables (`0x3cc8d8`, `0x3ccf68`,
  `0x3cd314`, `0x3d4cf0`, `0x3d4fcc`, plus the aura switch at `0x27208c`).
- A unit's perks are rows in `army+0x30`, matched by Type in mostly inlined loops. Tooltips and icons read the row
  Type (`feat_name_<Type>`, `feat_<Type>_<Level>.png`) at nine sites.
- Stat getters: crit chance `0x38272c`, crit damage `0x38332c`, min/max attack `0x3840d0` / `0x3841e0`, defence
  `0x37d1bc`, mobility `0x382b10`, max HP `0x37c16c`, max range `0x3803dc`.

## What the extension adds

A code cave at `0xa15000` (the file grows by 64 KiB so PT_LOAD[0] can cover it; PT_LOAD[1] keeps offset = vaddr) plus
enlarged `.bss`:

1. **Extended tables:** new accessors and loader hooks route Types 192-511 / 167-511 to tables in `.bss`; a Type
   beyond that goes to a trash slot.
2. **Skill aliases:** `0x39f370` is replaced by a copy that also matches aliases; the jump-table sites read the
   alias's *primary* base type, so a custom skill takes the branch of an existing skill.
3. **Perk remap:** after a perk row is loaded its `Type` becomes the base perk and the custom Type is kept at
   `row+0x74`, which the tooltip/icon code reads.
4. **Stat effects:** a leaf routine sums matching effects (skill rows, perk rows and equipped elite skins) by
   category and unit class; seven getter hooks add the result.
5. The data-driven elite-skin effects and the optional tier-12 challenge rule from the earlier patch.

39 hook sites in total; each is compared with the expected original instruction before writing.

## Verification

`tests/test_framework.py` maps the built library in Unicorn and checks the table accessors, aliasing, remap, effect
sums, ELF layout, that no hooked function uses `x30` as a scratch register, and runs the engine's own max-HP routine
through the hook. Not yet tested in the game on a device.
