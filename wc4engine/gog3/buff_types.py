"""Glory of Generals 3: what each Buff `Type` does.

Every skill and perk in GoG3 is a list of `Buff` rows (BuffSettings.json): Condition (def_buff.xml), PR (chance),
Type (what happens), Key, Value, BuffId (a chained buff), Range, Round, EffectId (animation). The engine groups
Types into phases, each handled by a class (CBuffHitBonus ...) whose apply function switches on the Type.

The labels below were derived from the game's own skill/perk descriptions (stringtable `skill_desc_*`,
`feat_desc_*`) and from reading the apply functions; entries marked "?" are inferred from one use only.
"""

PHASES = [
    (0, 35, "property", "Passive property of the unit/tile", "CArmyBuffBonus / CBuffArmyProp"),
    (36, 51, "hit", "While attacking (damage dealt)", "CBuffHitBonus (land/sea), CBuffStrikeBonus (air strike)"),
    (52, 60, "behit", "While being attacked (damage taken)", "CBuffBeHitBonus, CBuffBeStrikeBonus"),
    (61, 70, "beforehit", "Before the attack resolves", "CBuffBeforeHitBonus"),
    (71, 84, "afterhit", "After the attack resolves", "CBuffAfterHitBonus, CBuffAfterStrikeBonus"),
    (85, 97, "airborne", "After an airborne drop", "CBuffAfterAirborne"),
    (98, 99, "aura", "Applies a chained buff to nearby units", "CBuffAuras"),
    (301, 310, "country", "Country-wide setting", "CCountryBuffBonus"),
]

# type: (label, what Value means, notes)
BUFF_TYPES = {
    0: ("Nothing", "-", ""),
    1: ("Attack bonus", "attack points added", "usually used through an aura (98/99)"),
    2: ("Fortification defence bonus", "defence points", "units on fortifications and neighbours"),
    3: ("Transport ship attack not reduced", "flag (100)", ""),
    4: ("Property slot +0x44 (unused in data)", "number added", "implemented by the engine, no game data uses it"),
    5: ("Property slot +0x2c", "number added", "only a stray buff row uses it"),
    6: ("Vision +", "grids of vision", ""),
    7: ("Morale never declines", "morale id", "Samurai"),
    8: ("Fire chance on airstrike", "percent added", ""),
    9: ("Fire immunity", "flag", "area will not catch fire"),
    10: ("Attack not reduced when damaged", "flag", ""),
    11: ("Property flag 8 (unused in data)", "flag", "implemented by the engine, no game data uses it"),
    12: ("Splash damage behind target", "-", "PR is the chance; needs 'did not move' condition"),
    13: ("Attack range +", "grids", ""),
    14: ("Ignore terrain move cost (special)", "flag", ""),
    15: ("Terrain flag 1 (unused in data)", "flag", "implemented by the engine, no game data uses it"),
    16: ("Terrain flag 2 (unused in data)", "flag", "implemented by the engine, no game data uses it"),
    17: ("Ignore terrain move cost (desert)", "flag", ""),
    18: ("Ignore terrain move cost (mountain)", "flag", ""),
    19: ("Ignore terrain move cost (jungle)", "flag", ""),
    20: ("Ignore terrain move cost (snow)", "flag", ""),
    21: ("Can build fortifications", "flag", ""),
    22: ("Blocks enemy airborne nearby", "-", "air raid damage -35% in the area"),
    23: ("Build rounds reduced", "rounds", ""),
    24: ("Air operation range +", "grids", ""),
    25: ("Area bombing", "percent / grids", "air attacks hit units in 6 grids"),
    26: ("Morale not reduced (conditional)", "morale id", "used with a building condition"),
    27: ("Property flag 0x100 (unused in data)", "flag", "implemented by the engine, no game data uses it"),
    28: ("Property slot +0x50 (unused in data)", "number added", "implemented by the engine, no game data uses it"),
    29: ("Economy output +", "money per round", "in building areas"),
    30: ("Replenish cost reduced", "percent", ""),
    31: ("Replenish extra HP", "percent", ""),
    32: ("HP per round", "HP", ""),
    33: ("Morale boost to allies", "morale points", "cannot raise above high"),
    36: ("Damage + (flat)", "damage added", ""),
    37: ("Damage + % (conditional)", "percent", "combine with a target condition"),
    38: ("Critical hit rate +", "percent", ""),
    39: ("Hit bonus (type 39)", "?", "adds to a fight counter"),
    40: ("Ignore enemy defence", "percent", ""),
    41: ("Hit flag A", "flag", "sets a fight flag bit"),
    42: ("Hit flag B", "flag", "sets a fight flag bit"),
    43: ("Hit flag C", "flag", "sets a fight flag bit"),
    44: ("Ignore building/fortification defence", "flag", "strategic bombing"),
    45: ("Ignore anti-air defence", "flag", ""),
    46: ("Damage + % vs special units", "percent", ""),
    47: ("Damage + % (target condition)", "percent", "perks such as Machine Gun"),
    52: ("Counterattack damage reduced", "percent", ""),
    53: ("Damage taken reduced", "percent", ""),
    54: ("Damage taken reduced (conditional)", "percent", "e.g. against air"),
    61: ("Enemy does not fight back", "-", "PR is the chance; EffectId is the animation"),
    71: ("Attack again after annihilating", "-", "PR is the chance"),
    72: ("Attack again after attacking", "-", "PR is the chance"),
    74: ("After-hit effect 74 (unused in data)", "?", "implemented in CBuffAfterHitBonus"),
    76: ("After-hit effect 76 (unused in data)", "percent", "implemented in CBuffAfterHitBonus"),
    77: ("After-hit effect 77 (unused in data)", "?", "implemented in CBuffAfterHitBonus"),
    73: ("Destroy fortifications after annihilating", "-", "PR is the chance"),
    75: ("Extra enemy morale loss on counter", "morale points", ""),
    78: ("Enemy morale loss around after kill", "morale points", ""),
    79: ("Own morale recovery after kill", "morale points", ""),
    80: ("HP + % after kill", "percent", ""),
    85: ("Morale up after airborne", "morale points", ""),
    98: ("Aura (land / sea)", "-", "BuffId = buff applied, Range = grids"),
    99: ("Aura (incl. airports / carriers)", "-", "BuffId = buff applied, Range = grids"),
    301: ("Country flag A", "flag", ""),
    302: ("Country value A", "number added", ""),
    303: ("Country value B", "number added", ""),
    304: ("Country flag B", "flag", ""),
    305: ("Country value C", "number added", ""),
}


def phase_of(t):
    for lo, hi, key, label, cls in PHASES:
        if lo <= t <= hi:
            return key, label, cls
    return "unknown", "Unknown", ""


def label_of(t):
    return BUFF_TYPES.get(t, ("Type %d" % t, "?", ""))[0]
