# Glory of Generals 3: skills, perks and buffs in `libiron.so`

Findings behind the GoG3 side of the editor (library: modded 9.5 MB arm64 build; every address below is a file
offset = vaddr of that library). Verified against the shipped json and the code.

## Data model

| Table | Row fields |
|---|---|
| `SkillSettings` | `Id, Name, Type, Level, ArmyType, BuffId`: one row per skill **level**; `Type` groups the levels |
| `ArmyFeatureSettings` | `Id, BuffId[], PicName`: one row per perk |
| `BuffSettings` | `Id, Condition, PR, Type, Key, Value, BuffId, Range, Round, EffectId` |
| `GeneralSettings.Skills` | skill row Ids; `ArmySettings.Feature`: perk Ids |

Texts: `skill_<Id>`, `skill_desc_<Id>`, `feat_name_<Id>`, `feat_desc_<Id>` (`{0}` chance, `{1}` value, `{2}` range).
Icons: `skill_<Id>.png` (`image/image_skill.xml`), `army_feature<Id>.png` (`image/image_ui2.xml`). Atlases are
registered in `image_resource.xml`, so extra icons can live in their own atlas.

## Buff row in memory (loader `0x1ca328`)

`+0 Id, +4 Condition, +8 PR, +0xc Type, +0x10 Key, +0x14 Value, +0x18 BuffId, +0x1c Range, +0x20 Round,
+0x24 EffectId, +0x28 condition object` (looked up in the table loaded from `config/def_buff.xml`).

## Conditions are data

`config/def_buff.xml` defines conditions as comparisons (`comp`, with `self` / `target` / `constant` / `array`
parameters and a `proptype`) or logic (`and` / `or` / `not` over other condition ids). Army property types: 1 unit
class, 2 in city area, 3 at sea, 4 terrain, 5 building, 6 fortification, 7 morale, 8 unit size, 9 counter-attack,
10 unit type, 11 unit class (ships excluded), 12 not moved. The editor adds new conditions in one marked block.

## Effect Types are code

The engine applies a buff in **phases**, one class per phase; each class's apply function switches on the buff Type:

| Types | Phase / class | Mechanism (decoded) |
|---|---|---|
| 1-33 | unit properties, apply at `0x30a7b0` | each case adds Value to a slot or sets a flag bit |
| 36-47 | hit bonus `CBuffHitBonus` (`0x30aa14`); air strike `CBuffStrikeBonus` (`0x30b17c`) | add / scale a fight slot, or set flags (44 = ignore buildings, 45 = ignore anti-air) |
| 52-54 | `CBuffBeHitBonus`, `CBuffBeStrikeBonus` | damage taken |
| 61 | `CBuffBeforeHitBonus` | enemy does not fight back (PR = chance) |
| 71-80 | `CBuffAfterHitBonus`, `CBuffAfterStrikeBonus` | extra attack, morale effects, HP |
| 85 | `CBuffAfterAirborne` | morale after airborne |
| 98, 99 | `CBuffAuras` | applies the chained `BuffId` to units within `Range` |
| 301-305 | `CCountryBuffBonus` (`0x31747c`) | country-wide flags and values |

67 Types are implemented; 15 of them (4, 11, 15, 16, 27, 28, 39, 41-43, 74, 76, 77, 304, 305) are not used by any
shipped data, so they are free building blocks. Adding a brand-new Type means patching these switches.

## How it was found

1. String xrefs: `json/BuffSettings.json` led to the loader; its stores gave the row layout.
2. RTTI (`CBuff*` classes, vtables from `R_AARCH64_RELATIVE` relocations) gave the phase classes and their virtuals.
3. Each virtual was scanned for jump tables selecting on `[row, #0xc]`; every case was decoded to what it stores.
4. Compare-only phases (damage taken, auras) were read from the compare constants inside the virtuals.
5. Labels come from the game's own `skill_desc_*` / `feat_desc_*` strings.
