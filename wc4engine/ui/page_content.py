"""Generic list + detail screen (skills, perks, buffs...). A provider supplies the items and the editor."""
import flet as ft

from . import editors
from . import theme as T


class Item:
    """One row of the list."""
    def __init__(self, key, title, subtitle="", icon=None, chips=(), side="", search="", tags=()):
        self.key, self.title, self.subtitle, self.icon = key, title, subtitle, icon
        self.chips, self.side, self.search, self.tags = list(chips), side, search.lower(), set(tags)


class Provider:
    """Subclass: items() -> [Item]; detail(key, refresh) -> Control; new(refresh) -> (key, Control) | None."""
    kind = ""
    new_label = "New"
    filters = [("all", "All")]
    search_hint = "Search"

    def __init__(self, ctx):
        self.ctx = ctx

    def items(self):
        raise NotImplementedError

    def detail(self, key, refresh):
        raise NotImplementedError

    def new(self, refresh):
        return None

    def placeholder(self):
        return "Select an entry on the left."


class ContentPage:
    def __init__(self, ctx, provider, selected):
        self.ctx, self.p = ctx, provider
        self.selected = selected
        self.query = ""
        self.filter = ctx.cache.get(provider.kind + ":filter", "all")
        self.items = []
        self.list_view = ft.ListView(expand=True, spacing=2, padding=6)
        self.count = T.txt("", 11.5, T.FAINT)
        self.detail = ft.Container(expand=True)

    def visible(self):
        out = []
        for it in self.items:
            if self.filter != "all" and self.filter not in it.tags:
                continue
            if self.query and self.query not in it.search:
                continue
            out.append(it)
        return out

    def fill(self):
        vis = self.visible()
        ctrls = []
        for it in vis[:600]:
            on = it.key == self.selected
            side = [T.chip(t, c) for t, c in it.chips]
            if it.side:
                side.append(T.txt(it.side, 11, T.FAINT))
            lead = [it.icon] if it.icon is not None else []
            ctrls.append(ft.Container(
                content=ft.Row([*lead,
                                ft.Column([T.txt(it.title, 13.5, weight=ft.FontWeight.W_500, no_wrap=True,
                                                 overflow=ft.TextOverflow.ELLIPSIS),
                                           T.txt(it.subtitle, 11.5, T.MUTED, no_wrap=True,
                                                 overflow=ft.TextOverflow.ELLIPSIS)], spacing=0, expand=True),
                                *side], spacing=10),
                padding=ft.Padding.symmetric(horizontal=8, vertical=5), border_radius=7, ink=True,
                bgcolor=T.soft(T.ACCENT, 0.14) if on else None,
                on_click=lambda e, k=it.key: self.select(k)))
        self.list_view.controls = ctrls
        self.count.value = "%d of %d shown" % (min(len(vis), 600), len(self.items))

    def reload(self):
        self.items = self.p.items()

    def select(self, key):
        self.selected = key
        self.ctx.cache[self.p.kind + ":sel"] = key
        self.fill()
        self.detail.content = self.p.detail(key, self.refresh)
        self.ctx.page.update()

    def refresh(self, selected=None):
        """Called by editors after a save/delete."""
        self.reload()
        self.selected = selected
        self.ctx.cache[self.p.kind + ":sel"] = selected
        self.fill()
        self.detail.content = self.p.detail(selected, self.refresh) if selected is not None else self.placeholder()
        self.ctx.page.update()

    def placeholder(self):
        return ft.Container(T.muted(self.p.placeholder()), alignment=ft.Alignment.CENTER, expand=True)

    def new(self, e):
        res = self.p.new(self.refresh)
        if res is None:
            return
        key, control = res
        self.selected = None
        self.detail.content = control
        self.fill()
        self.ctx.page.update()

    def build(self):
        self.reload()
        search = T.field(None, "", hint=self.p.search_hint)
        search.on_change = lambda e: (setattr(self, "query", e.control.value.strip().lower()), self.fill(),
                                      self.list_view.update(), self.count.update())
        top = [search]
        if len(self.p.filters) > 1:
            top.append(ft.SegmentedButton(
                segments=[ft.Segment(value=k, label=l) for k, l in self.p.filters], selected=[self.filter],
                allow_empty_selection=False,
                on_change=lambda e: (setattr(self, "filter", list(e.control.selected)[0]),
                                     self.ctx.cache.__setitem__(self.p.kind + ":filter", self.filter), self.fill(),
                                     self.ctx.page.update())))
        if self.p.new_label:
            top.append(T.primary(self.p.new_label, self.new, ft.Icons.ADD))
        left = ft.Container(
            ft.Column([ft.Container(ft.Column(top, spacing=10), padding=14), self.list_view,
                       ft.Container(self.count, padding=ft.Padding.symmetric(horizontal=14, vertical=8))],
                      expand=True, spacing=0),
            width=350, bgcolor=T.SURFACE, border=ft.Border.only(right=ft.BorderSide(1, T.BORDER)))
        self.fill()
        sel = self.selected if self.selected is not None else self.ctx.cache.get(self.p.kind + ":sel")
        if sel is not None and any(i.key == sel for i in self.items):
            self.selected = sel
            self.fill()
            self.detail.content = self.p.detail(sel, self.refresh)
        else:
            self.detail.content = self.placeholder()
        return ft.Row([left, self.detail], expand=True, spacing=0, vertical_alignment=ft.CrossAxisAlignment.STRETCH)


# ====================================================================== World Conqueror 4 provider
class Wc4Provider(Provider):
    def __init__(self, ctx, kind):
        super().__init__(ctx)
        self.kind = kind
        self.new_label = "New " + kind
        self.filters = [("all", "All"), ("custom", "Custom"), ("engine", "Engine"), ("extended", "Added")]
        self.search_hint = "Search by name or Type"

    def items(self):
        raw = self.ctx.be.skills() if self.kind == "skill" else self.ctx.be.perks()
        out = []
        for it in raw:
            tags = set()
            if it["custom"]:
                tags.add("custom")
            if it["usage"]:
                tags.add("engine")
            if it["extras"]:
                tags.add("extended")
            out.append(Item(it["type"], it["name"] or it["cn"],
                            "Type %d · %d level%s" % (it["type"], it["levels"], "" if it["levels"] == 1 else "s"),
                            icon=self.ctx.icon(self.kind, it["type"], size=34),
                            chips=[("custom", T.CUSTOM)] if it["custom"] else [],
                            side=str(it["usage"]) if it["usage"] else "",
                            search="%s %s %s" % (it["name"], it["cn"], it["type"]), tags=tags))
        return out

    def detail(self, key, refresh):
        return editors.build(self.ctx, self.kind, key, refresh)

    def new(self, refresh):
        free = self.ctx.be.free_type(self.kind)
        self.ctx.cache[self.kind + ":draft"] = editors.blank(self.kind, free)
        return free, editors.build(self.ctx, self.kind, free, refresh, draft=True)

    def placeholder(self):
        return "Select a %s on the left, or create a new one." % self.kind


def view(ctx, kind, arg):
    """WC4 skills/perks screen (kept for the shell)."""
    sel = arg if isinstance(arg, int) else None
    return ContentPage(ctx, Wc4Provider(ctx, kind), sel).build()


def page(ctx, provider, arg):
    sel = arg if isinstance(arg, int) else None
    return ContentPage(ctx, provider, sel).build()
