"""In-process access to the editor backends (WC4 and GoG3). Pages never touch HTTP."""
import hashlib

from .. import server
from ..gog3.app import Gog3App


class _Base:
    def _q(self, **kw):
        return {k: [str(v)] for k, v in kw.items() if v is not None}

    def call(self, fn, body=None, **query):
        """Run one of the shared code-browser/project handlers from server.py."""
        with self.app.lock:
            return fn(self.app, self._q(**query), body or {})

    @property
    def project(self):
        return self.app.project


class Backend(_Base):
    """World Conqueror 4."""
    game = "wc4"

    def __init__(self, package):
        self.app = server.App(package)

    def state(self):
        return self.call(server.api_state)

    def save_project(self, **parts):
        return self.call(server.api_save_project, parts)

    def skills(self):
        return self.call(server.api_skills)["skills"]

    def skill(self, t):
        return self.call(server.api_skill, type=t)

    def perks(self):
        return self.call(server.api_perks)["perks"]

    def perk(self, t):
        return self.call(server.api_perk, type=t)

    def units(self):
        return self.call(server.api_units)["units"]

    def generals(self):
        return self.call(server.api_generals)["generals"]

    def free_type(self, kind):
        return self.call(server.api_free_type, kind=kind)["type"]

    def icon(self, kind, t, level=1):
        try:
            return self.call(server.api_icon, kind=kind, type=t, level=level)
        except Exception:
            return None

    def build(self, write_data=True):
        return self.call(server.api_build, dict(write_data=write_data))

    def preview(self):
        return self.call(server.api_preview)


class Gog3Backend(_Base):
    """Glory of Generals 3."""
    game = "gog3"

    def __init__(self, package):
        self.app = Gog3App(package)

    @property
    def store(self):
        return self.app.project.store

    def state(self):
        pr = self.app.project
        out = dict(package=pr.package, project=pr.data, project_exists=_exists(pr.path), game="gog3")
        try:
            out["base"] = pr.detect()
        except Exception as e:
            out["base_error"] = str(e)
        lib = _lib(pr)
        if lib:
            data = open(lib, "rb").read()
            out["package_lib"] = dict(sha1=hashlib.sha1(data).hexdigest(), size=len(data))
        return out

    def save_project(self, **parts):
        pr = self.app.project
        for k, v in parts.items():
            if isinstance(v, dict):
                pr.data[k].update(v)
        pr.reset_store()
        self.app._base = None
        pr.save()
        return {"ok": True}

    def icon(self, kind, rid, level=1):
        try:
            return self.store.icon_png(kind, rid)
        except Exception:
            return None

    def build(self, write_data=True):
        lines = []
        try:
            self.app.project.build(log=lines.append)
            self.app._built = None
            return dict(ok=True, log=lines)
        except Exception as e:
            lines.append("ERROR: %s" % e)
            return dict(ok=False, log=lines)

    def preview(self):
        _, elf, _, _ = self.app.built()
        return dict(size=len(elf.data), detect=dict(challenge="-", mf_picker="-", general_bank="-",
                                                    engine_ext="none (GoG3 needs no engine code for data edits)"),
                    patches=len([p for p in self.app.project.data["asm_patches"] if p.get("enabled", True)]))


def _exists(path):
    import os
    return os.path.exists(path)


def _lib(pr):
    import os
    p = os.path.join(pr.package, "lib", "arm64-v8a", "libiron.so")
    return p if os.path.exists(p) else None


def open_backend(entry):
    return Gog3Backend(entry["package"]) if entry["game"] == "gog3" else Backend(entry["package"])
