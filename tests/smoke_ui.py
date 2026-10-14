"""Builds every screen inside a real Flet session and reports exceptions. Usage: python tests/smoke_ui.py [package]"""
import asyncio, os, sys, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import flet as ft
from wc4engine.ui import theme as T
from wc4engine.ui.shell import Shell

PKG = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WC4_TEST_PKG", "")
errors = []

async def main(page: ft.Page):
    T.apply(page)
    from wc4engine import projects
    reg = projects.ensure_defaults(projects.load())
    sh = Shell(page, reg, 0)
    sh.build()
    c = sh.ctx
    steps = [("overview", None), ("patches", None), ("skills", None), ("perks", None), ("code", None),
             ("code", 0x3cc8bc), ("build", None), ("skills", 34), ("perks", 92), ("skills", 1)]
    for name, arg in steps:
        sh.show(name, arg)
        body = sh.body.content
        txt = str(body)[:0]
        print("page %-9s %s -> %s" % (name, arg, type(body).__name__))
        if isinstance(body, ft.Container) and "could not be loaded" in repr(body):
            errors.append((name, arg))
        await asyncio.sleep(0.4)
    # select items in the content pages
    for kind, t in (("skill", 34), ("skill", 6), ("perk", 92), ("perk", 4)):
        sh.show(kind + "s")
        row = sh.body.content
        try:
            from wc4engine.ui import editors
            ctl = editors.build(c, kind, t, lambda *_: None)
            page.add(ctl) if False else None
            print("editor", kind, t, "ok")
        except Exception:
            traceback.print_exc(); errors.append((kind, t))
    # custom drafts
    for kind in ("skill", "perk"):
        try:
            free = c.be.free_type(kind)
            c.cache[kind + ":draft"] = __import__("wc4engine.ui.editors", fromlist=["x"]).blank(kind, free)
            from wc4engine.ui import editors
            editors.build(c, kind, free, lambda *_: None, draft=True)
            print("custom editor", kind, free, "ok")
        except Exception:
            traceback.print_exc(); errors.append(("custom", kind))
    await asyncio.sleep(1)
    print("ERRORS:", errors)
    await page.window.close()

ft.run(main)
