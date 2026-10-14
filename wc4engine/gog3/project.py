"""Glory of Generals 3 project: paths, assembly patches for libiron.so, and the data store."""
import datetime
import hashlib
import json
import os
import shutil

from .. import patches
from ..elf import Elf
from .store import Gog3Store

PROJECT_FILE = "engine_project.json"
LIB_NAME = "libiron.so"
LIB_REL = os.path.join("lib", "arm64-v8a", LIB_NAME)

DEFAULT = {
    "game": "gog3",
    "version": 1,
    "paths": {"base_so": "", "assets": "", "backups": ""},
    "asm_patches": [],
}


class Gog3Project:
    game = "gog3"

    def __init__(self, package):
        self.package = os.path.abspath(package)
        self.path = os.path.join(self.package, PROJECT_FILE)
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                self.data = json.load(f)
            for k, v in DEFAULT.items():
                self.data.setdefault(k, json.loads(json.dumps(v)))
        else:
            self.data = json.loads(json.dumps(DEFAULT))
        self._store = None

    def save(self):
        os.makedirs(self.package, exist_ok=True)
        with open(self.path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)

    def backup_dir(self):
        b = self.data["paths"].get("backups") or os.path.join(os.path.dirname(self.package), "backups")
        return os.path.join(b, datetime.date.today().isoformat() + "_gog3_engine_editor")

    @property
    def store(self):
        if self._store is None:
            self._store = Gog3Store(self.data["paths"]["assets"], self.package, self.backup_dir())
        return self._store

    def reset_store(self):
        self._store = None

    # ------------------------------------------------------------------ library
    def base_elf(self):
        p = self.data["paths"]["base_so"]
        if not p or not os.path.exists(p):
            raise FileNotFoundError("base library not found: %r (set it on the Overview page)" % p)
        return Elf.load(p)

    def build_library(self, log=print):
        elf = self.base_elf()
        patches.apply_asm_patches(elf, self.data["asm_patches"], log)
        return elf, None

    def build(self, log=print, write_data=True):
        lines = []

        def L(msg):
            lines.append(msg)
            log(msg)
        active = [p for p in self.data["asm_patches"] if p.get("enabled", True)]
        dst = os.path.join(self.package, LIB_REL)
        if active:
            elf, _ = self.build_library(L)
            if os.path.exists(dst):
                b = os.path.join(self.backup_dir(), LIB_REL)
                if not os.path.exists(b):
                    os.makedirs(os.path.dirname(b), exist_ok=True)
                    shutil.copy2(dst, b)
                    L("backed up previous library to %s" % b)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(bytes(elf.data))
            L("wrote %s (%d bytes, sha1 %s)" % (LIB_REL, len(elf.data), hashlib.sha1(bytes(elf.data)).hexdigest()[:12]))
        else:
            L("no enabled assembly patches: %s left as it is" % LIB_NAME)
        L("skills, perks, buffs, conditions and icons are saved straight into the package when you edit them")
        self.save()
        self._changes(L)
        return lines

    def _changes(self, log):
        d = self.data
        body = "\n".join("  asm patch %s: %s (%s)" % (a["addr"], a.get("note", ""), a["hex"])
                         for a in d["asm_patches"] if a.get("enabled", True))
        if not body or d.get("_last_changes") == body:
            return
        d["_last_changes"] = body
        self.save()
        p = os.path.join(self.package, "CHANGES.txt")
        with open(p, "a", encoding="utf-8", newline="\n") as f:
            f.write("\nGoG3 engine editor build %s:\n%s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), body))

    def detect(self):
        elf = self.base_elf()
        return dict(sha1=hashlib.sha1(bytes(elf.data)).hexdigest(), size=len(elf.data), grown=elf.is_grown(),
                    note="Modified build (credits: lib.so by 摸鱼的雅木). There is no unmodified copy to compare with.")
