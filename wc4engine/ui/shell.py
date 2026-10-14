"""Main window: navigation, top bar, page switching, notifications, dialogs, background work."""
import traceback

import flet as ft

from . import theme as T
from .. import __version__, projects
from .backend import open_backend

NAV = {
    "wc4": [
        ("overview", "Overview", ft.Icons.DASHBOARD_OUTLINED),
        ("patches", "Engine patches", ft.Icons.BUILD_CIRCLE_OUTLINED),
        None,
        ("skills", "Skills", ft.Icons.STAR_OUTLINE),
        ("perks", "Perks", ft.Icons.SHIELD_OUTLINED),
        None,
        ("code", "Code browser", ft.Icons.CODE),
        ("build", "Build", ft.Icons.INVENTORY_2_OUTLINED),
    ],
    "gog3": [
        ("overview", "Overview", ft.Icons.DASHBOARD_OUTLINED),
        ("patches", "Assembly patches", ft.Icons.BUILD_CIRCLE_OUTLINED),
        None,
        ("skills", "Skills", ft.Icons.STAR_OUTLINE),
        ("perks", "Perks", ft.Icons.SHIELD_OUTLINED),
        ("buffs", "Buffs", ft.Icons.BOLT_OUTLINED),
        ("conditions", "Conditions", ft.Icons.RULE),
        ("types", "Buff types", ft.Icons.LIST_ALT),
        None,
        ("code", "Code browser", ft.Icons.CODE),
        ("build", "Build", ft.Icons.INVENTORY_2_OUTLINED),
    ],
}


class Ctx:
    """Shared by all pages."""

    def __init__(self, page, entry):
        self.page = page
        self.entry = entry
        self.game = entry["game"]
        self.be = open_backend(entry)
        self.state = None
        self.cache = {}
        self.unbuilt = False
        self.current = None
        self.on_unbuilt = None

    # ------------------------------------------------------------- feedback
    def toast(self, msg, error=False):
        self.page.show_dialog(ft.SnackBar(
            content=T.txt(msg, 13, T.TEXT), bgcolor=T.SURFACE3 if not error else "#3a1f1c",
            duration=7000 if error else 3000, show_close_icon=True))

    def guard(self, fn, ok=None):
        """Run fn(); show `ok` or the error. Returns fn's result or None."""
        try:
            r = fn()
            if ok:
                self.toast(ok)
            return r
        except Exception as e:
            traceback.print_exc()
            self.toast(str(e), error=True)
            return None

    def background(self, work, done, label="Working…"):
        """Run work() in a thread with a busy dialog, then done(result) on success."""
        dlg = ft.AlertDialog(modal=True, content=ft.Row([ft.ProgressRing(width=22, height=22, color=T.ACCENT),
                                                         T.txt(label, 14)], spacing=14, tight=True))
        self.page.show_dialog(dlg)

        def run():
            try:
                res = work()
            except Exception as e:
                traceback.print_exc()
                self.page.pop_dialog()
                self.toast(str(e), error=True)
                return
            self.page.pop_dialog()
            try:
                done(res)
            except Exception as e:
                traceback.print_exc()
                self.toast(str(e), error=True)
            self.page.update()
        self.page.run_thread(run)

    def dialog(self, title, content, actions, width=560):
        """actions: [(label, callback|None, style)] where style in (None, 'primary', 'danger'); callback gets no args."""
        def close(cb):
            def h(e):
                self.page.pop_dialog()
                if cb:
                    cb()
            return h
        btns = []
        for label, cb, style in actions:
            if style == "primary":
                btns.append(T.primary(label, close(cb)))
            elif style == "danger":
                btns.append(T.button(label, close(cb), color=T.DANGER))
            else:
                btns.append(ft.TextButton(content=label, on_click=close(cb)))
        self.page.show_dialog(ft.AlertDialog(
            title=T.h2(title), content=ft.Container(content=content, width=width), actions=btns,
            bgcolor=T.SURFACE, shape=ft.RoundedRectangleBorder(radius=12)))

    def confirm(self, title, text, label, on_yes):
        self.dialog(title, T.txt(text), [("Cancel", None, None), (label, on_yes, "danger")], width=440)

    # ------------------------------------------------------------- data
    def refresh_state(self):
        self.state = self.be.state()
        return self.state

    def mark_unbuilt(self, v=True):
        self.unbuilt = v
        if self.on_unbuilt:
            self.on_unbuilt()

    def cached(self, key, fn):
        if key not in self.cache:
            self.cache[key] = fn()
        return self.cache[key]

    def drop(self, *keys):
        for k in keys:
            self.cache.pop(k, None)

    def icon(self, kind, t, level=1, size=36, radius=7):
        data = self.be.icon(kind, t, level)
        inner = ft.Image(src=data, width=size, height=size, fit=ft.BoxFit.CONTAIN) if data else \
            ft.Icon(ft.Icons.HIDE_IMAGE_OUTLINED, color=T.FAINT, size=size * 0.5)
        return ft.Container(content=inner, width=size, height=size, bgcolor="#0f1419", border_radius=radius,
                            border=ft.Border.all(1, T.BORDER), alignment=ft.Alignment.CENTER)

    def go(self, name, arg=None):
        self.show(name, arg)


class Shell:
    def __init__(self, page, registry, index=0):
        self.page = page
        self.registry = registry
        self.index = index
        self.nav_col = ft.Column(spacing=2)
        self.body = ft.Container(expand=True)
        self.badge = T.chip("Unbuilt changes", T.ACCENT)
        self.badge.visible = False
        self.pkg_text = T.txt("", 12, T.TEXT, mono=True, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS)
        self.ctx = None
        self.pages = {}
        self._open(index)

    def _open(self, index):
        entry = self.registry["projects"][index]
        self.index = index
        self.ctx = Ctx(self.page, entry)
        self.ctx.show = self.show
        self.ctx.on_unbuilt = self._update_badge
        self.pages = self._pages(entry["game"])

    def _pages(self, game):
        from . import (g3_buffs, g3_skills, page_build, page_code, page_content, page_overview, page_patches)
        common = {"overview": page_overview.view, "patches": page_patches.view, "code": page_code.view,
                  "build": page_build.view}
        if game == "gog3":
            common.update({
                "skills": lambda c, a: page_content.page(c, g3_skills.SkillProvider(c), a),
                "perks": lambda c, a: page_content.page(c, g3_skills.PerkProvider(c), a),
                "buffs": lambda c, a: page_content.page(c, g3_buffs.BuffProvider(c), a),
                "conditions": lambda c, a: page_content.page(c, g3_buffs.ConditionProvider(c), a),
                "types": lambda c, a: page_content.page(c, g3_buffs.TypeProvider(c), a)})
        else:
            common.update({"skills": lambda c, a: page_content.view(c, "skill", a),
                           "perks": lambda c, a: page_content.view(c, "perk", a)})
        return common

    def switch(self, index):
        if index == self.index:
            return
        self._open(index)
        self.pkg_text.value = self.registry["projects"][index]["package"]
        self.badge.visible = False
        try:
            self.ctx.refresh_state()
        except Exception as e:
            self.ctx.toast(str(e), error=True)
        self.show("overview")

    def build(self):
        top = ft.Container(
            content=ft.Row([
                ft.Row([ft.Container(content=ft.Icon(ft.Icons.SHIELD, color=T.ACCENT_INK, size=17), width=30, height=30,
                                     bgcolor=T.ACCENT, border_radius=7, alignment=ft.Alignment.CENTER),
                        ft.Column([T.txt("EasyTech Engine Editor", 14.5, weight=ft.FontWeight.W_600),
                                   T.txt("v" + __version__ + " · native library editor", 11, T.MUTED)], spacing=0)],
                       spacing=10, width=220),
                self.game_dd(), ft.Container(content=self.pkg_text, expand=True),
                self.badge,
                T.primary("Build package", lambda e: self.show("build", "run"), icon=ft.Icons.PLAY_ARROW),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
            height=54, padding=ft.Padding.symmetric(horizontal=16), bgcolor="#11161d",
            border=ft.Border.only(bottom=ft.BorderSide(1, T.BORDER)))
        nav = ft.Container(
            content=ft.Column([self.nav_col, ft.Container(expand=True),
                               T.txt("Builds start from the APK's original library and write into the mod package. "
                                     "Replaced files are backed up first.", 11.5, T.FAINT)], expand=True),
            width=212, bgcolor=T.SURFACE, padding=ft.Padding.symmetric(horizontal=8, vertical=12),
            border=ft.Border.only(right=ft.BorderSide(1, T.BORDER)))
        self.page.add(ft.Column([top, ft.Row([nav, self.body], expand=True, spacing=0,
                                             vertical_alignment=ft.CrossAxisAlignment.STRETCH)],
                                expand=True, spacing=0))
        try:
            st = self.ctx.refresh_state()
            self.pkg_text.value = st["package"]
        except Exception as e:
            self.ctx.toast(str(e), error=True)
        self.show("overview")

    def game_dd(self):
        opts = [ft.DropdownOption(key=str(i), text=projects.GAMES.get(p["game"], p["game"]))
                for i, p in enumerate(self.registry["projects"])]
        return ft.Dropdown(options=opts, value=str(self.index), width=230, dense=True, text_size=13,
                           border_color="#354255", on_select=lambda e: self.switch(int(e.control.value)))

    def _update_badge(self):
        self.badge.visible = self.ctx.unbuilt
        self.badge.update()

    def _nav(self, active):
        self.nav_col.controls.clear()
        pr = (self.ctx.state or {}).get("project", {})
        counts = {"patches": len(pr.get("asm_patches", []))}
        if self.ctx.game == "wc4":
            counts.update(skills=len(pr.get("custom_skills", [])), perks=len(pr.get("custom_perks", [])))
        for item in NAV[self.ctx.game]:
            if item is None:
                self.nav_col.controls.append(ft.Container(height=1, bgcolor=T.BORDER,
                                                          margin=ft.Margin.symmetric(vertical=8, horizontal=6)))
                continue
            key, label, icon = item
            on = key == active
            right = [T.txt(str(counts[key]) + (" asm" if key == "patches" else " new"), 11,
                           T.ACCENT if on else T.FAINT)] if counts.get(key) else []
            self.nav_col.controls.append(ft.Container(
                content=ft.Row([ft.Icon(icon, size=18, color=T.ACCENT if on else T.MUTED),
                                T.txt(label, 13.5, T.ACCENT if on else T.MUTED, ft.FontWeight.W_500),
                                ft.Container(expand=True), *right], spacing=10),
                padding=ft.Padding.symmetric(horizontal=10, vertical=8), border_radius=6,
                bgcolor=T.soft(T.ACCENT, 0.14) if on else None, ink=True,
                on_click=lambda e, k=key: self.show(k)))

    def show(self, name, arg=None):
        self.ctx.current = name
        self._nav(name)
        self.body.content = ft.Container(content=ft.Row([ft.ProgressRing(width=20, height=20, color=T.ACCENT),
                                                         T.muted("Loading…")], spacing=12), padding=30)
        self.page.update()
        try:
            self.body.content = self.pages[name](self.ctx, arg)
        except Exception as e:
            traceback.print_exc()
            self.body.content = T.scroll_page(T.note("This page could not be loaded: %s" % e, T.DANGER))
        self._nav(name)
        self.page.update()


def run(registry, index=0):
    def main(page: ft.Page):
        page.title = "EasyTech Engine Editor"
        page.window.width = 1280
        page.window.height = 800
        page.window.min_width = 1000
        page.window.min_height = 640
        T.apply(page)
        Shell(page, registry, index).build()
    ft.run(main)
