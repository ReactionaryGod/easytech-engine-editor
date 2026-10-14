"""App object for GoG3 projects (same interface the code-browser handlers in server.py expect)."""
import json
import os
import threading

from ..analysis import Analysis
from ..elf import Elf
from ..rtti import Rtti
from . import catalog
from .project import Gog3Project

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".cache")

# hand-identified functions of libiron.so (see reference/GoG3_reference.md and the buff study)
KNOWN = {
    0x1ca328: "load json/BuffSettings.json (row: +0 Id, +4 Condition, +8 PR, +0xc Type, +0x10 Key, +0x14 Value, "
              "+0x18 BuffId, +0x1c Range, +0x20 Round, +0x24 EffectId)",
    0x1cc064: "load json/SkillSettings.json",
    0x1ccaa4: "load json/ArmyFeatureSettings.json",
    0x1cc364: "load json/GeneralSettings.json",
    0x1c356c: "load all json tables (calls the buff loader)",
    0x30a7b0: "buff apply: unit property buffs (Types 1-33)",
    0x30aa14: "buff apply: hit bonuses (Types 36-47)",
    0x30b17c: "buff apply: air strike bonuses (Types 36-47)",
    0x30b0d8: "buff apply: airforce property buffs",
    0x31747c: "buff apply: country buffs (Types 301-305)",
    0x207de8: "CEntityBattle loader (see BtlEditorPC docs)",
    0x1e3ab8: "FlatBuffers verifier of the battle root table",
}


class Gog3App:
    def __init__(self, package):
        self.lock = threading.RLock()
        self.project = Gog3Project(package)
        self.known_funcs = dict(KNOWN)
        self._base = None
        self._built = None

    def base(self):
        p = self.project.data["paths"]["base_so"]
        if not self._base or self._base[0] != p:
            elf = self.project.base_elf()
            an = Analysis(elf, CACHE)
            self._label(an)
            self._base = (p, elf, an)
        return self._base

    def _label(self, an):
        try:
            names = an.cache_names if hasattr(an, "cache_names") else None
            if names is None:
                names = an._cache("gog3names1", lambda: Rtti(an.elf, an).virtual_names("C"))
            an.names.update(names)
        except Exception:
            pass

    def built(self):
        key = json.dumps(self.project.data["asm_patches"], sort_keys=True)
        if not self._built or self._built[0] != key:
            elf, _ = self.project.build_library(log=lambda *_: None)
            elf = Elf(bytes(elf.data))
            an = Analysis(elf, None)
            base_an = self.base()[2]
            an.funcs, an.names = base_an.funcs, base_an.names
            self._built = (key, elf, an, None)
        return self._built

    def view(self, which):
        if which == "built":
            _, elf, an, _ = self.built()
            return elf, an
        _, elf, an = self.base()
        return elf, an

    def catalog(self):
        return catalog.build(self.base()[2])
