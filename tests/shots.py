"""Shows pages in a real window and screenshots them: python tests/shots.py outdir page[:arg] ..."""
import asyncio, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import flet as ft
from wc4engine.ui import theme as T
from wc4engine.ui.shell import Shell
from wc4engine import projects
PKG = os.environ.get("WC4_TEST_PKG") or os.path.join(os.path.dirname(os.path.dirname(HERE)), "mods", "2026-10-12_scorpion_side_chara_rank")
GAME = os.environ.get("WC4_TEST_GAME", "wc4")
out, specs = sys.argv[1], sys.argv[2:]

async def main(page: ft.Page):
    page.title = "WC4 Engine Editor"
    page.window.width, page.window.height = 1280, 760
    T.apply(page)
    reg = projects.ensure_defaults(projects.load())
    if os.environ.get("WC4_TEST_PKG"):
        projects.add(reg, GAME, PKG)
    idx = next(i for i, p in enumerate(reg["projects"]) if p["game"] == GAME)
    sh = Shell(page, reg, idx); sh.build()
    for i, s in enumerate(specs):
        name, _, arg = s.partition(":")
        a = (arg if arg == "run" else int(arg, 0)) if arg else None
        if name == "newskill" or name == "newperk":
            kind = name[3:]
            sh.show(kind + "s"); await asyncio.sleep(0.5)
            c = sh.ctx; free = c.be.free_type(kind)
            from wc4engine.ui import editors
            c.cache[kind + ":draft"] = editors.blank(kind, free)
            sh.body.content.controls[1].content = editors.build(c, kind, free, lambda *_: None, draft=True)
            page.update()
        else:
            sh.show(name, a)
        await asyncio.sleep(2.2)
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(HERE, "shot.ps1"),
                        os.path.join(out, "%02d_%s.png" % (i, s.replace(":", "_")))], check=False)
    await page.window.close()
ft.run(main)
