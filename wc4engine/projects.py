"""Project registry: which mod packages the editor knows (one per game) and which is open."""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(HERE, "projects.json")
GAMES = {"wc4": "World Conqueror 4", "gog3": "Glory of Generals 3"}
GOG3_DIR = os.environ.get("GOG3_DIR", "")      # unpacked Glory of Generals 3 APK (assets/ and lib/)


def load():
    if os.path.exists(REGISTRY):
        try:
            with open(REGISTRY, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    return {"projects": [], "active": 0}


def save(reg):
    with open(REGISTRY, "w", encoding="utf-8", newline="\n") as f:
        json.dump(reg, f, ensure_ascii=False, indent=1)


def workspace():
    return os.path.dirname(HERE)           # ...\ModdingStuff


def _newest_wc4_package():
    mods = os.path.join(workspace(), "mods")
    if os.path.isdir(mods):
        subs = [d for d in sorted(os.listdir(mods)) if os.path.isdir(os.path.join(mods, d, "assets"))]
        if subs:
            return os.path.join(mods, subs[-1])
    return None


def ensure_defaults(reg):
    have = {p["game"] for p in reg["projects"]}
    if "wc4" not in have:
        pkg = _newest_wc4_package()
        if pkg:
            reg["projects"].append({"game": "wc4", "package": pkg})
    if "gog3" not in have and GOG3_DIR and os.path.isdir(os.path.join(GOG3_DIR, "assets")):
        pkg = os.path.join(workspace(), "mods_gog3", "main")
        os.makedirs(pkg, exist_ok=True)
        pf = os.path.join(pkg, "engine_project.json")
        if not os.path.exists(pf):
            with open(pf, "w", encoding="utf-8", newline="\n") as f:
                json.dump({"game": "gog3", "version": 1, "asm_patches": [],
                           "paths": {"base_so": os.path.join(GOG3_DIR, "lib", "arm64-v8a", "libiron.so"),
                                     "assets": os.path.join(GOG3_DIR, "assets"),
                                     "backups": os.path.join(workspace(), "backups")}}, f, indent=1)
        reg["projects"].append({"game": "gog3", "package": pkg})
    reg["projects"].sort(key=lambda p: p["game"] != "wc4")
    return reg


def add(reg, game, package):
    reg["projects"] = [p for p in reg["projects"] if os.path.abspath(p["package"]) != os.path.abspath(package)]
    reg["projects"].append({"game": game, "package": os.path.abspath(package)})
    return reg


def game_of(package):
    pf = os.path.join(package, "engine_project.json")
    if os.path.exists(pf):
        try:
            with open(pf, encoding="utf-8") as f:
                return json.load(f).get("game", "wc4")
        except (OSError, ValueError):
            pass
    return "wc4"
