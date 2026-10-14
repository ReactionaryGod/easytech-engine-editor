"""Right-hand editors for skills and perks: existing types and custom types."""
import copy

import flet as ft

from .. import server
from . import theme as T
from . import widgets as W

SKILL_COLS = [("Id", None), ("Lv", None), ("Chance %", "ActivatesChance"), ("Effect", "SkillEffect"),
              ("Is %", "IfPercent"), ("Cost", "CostMedal"), ("Score", "Score"), ("Open", "OpenDefault"),
              ("Buff", "ArmyBuff"), ("Aura", "AurasRange")]
PERK_COLS = [("Id", None), ("Lv", None), ("Chance %", "ActivatesChance"), ("Effect", "FeatureEffect"),
             ("Second", "SecondEffect"), ("Range", "Range"), ("Round", "Round"), ("CD", "CD"),
             ("Cond", "Condition"), ("Buff", "ArmyBuff"), ("Buff rnd", "ArmyBuffRound"),
             ("Related", "RelatedArmyId"), ("AA", "AntiairId"), ("Aura", "Auras")]


def blank(kind, t):
    if kind == "skill":
        return {"type": t, "names": {"en": "New skill"}, "descs": {"en": "Effect +[#00FF00#%d]"}, "series": 0,
                "if_percent": 0, "open_default": 0, "army_buff": 0, "auras_range": 0, "bases": [], "effects": [],
                "levels": [{"chance": 100, "effect": 5, "cost": 100, "score": 100}], "icon": {}, "generals": []}
    return {"type": t, "base": 0, "names": {"en": "New perk"}, "descs": {"en": "Describe the perk."},
            "levels": [{"chance": 100, "effect": 0}], "effects": [], "icon": {}, "units": []}


def tab_view(defs, start=0):
    """defs: [(label, builder)]; builder() -> control. Returns a Column with a tab bar and swapped body."""
    body = ft.Container(expand=True)
    bar = ft.Row(spacing=4)

    def show(i):
        for j, b in enumerate(bar.controls):
            on = j == i
            b.content.color = T.ACCENT if on else T.MUTED
            b.border = ft.Border.only(bottom=ft.BorderSide(2, T.ACCENT if on else "transparent"))
        body.content = ft.Column([defs[i][1]()], scroll=ft.ScrollMode.AUTO, expand=True)
        bar.update() if bar.page else None
        body.update() if body.page else None

    for i, (label, _) in enumerate(defs):
        bar.controls.append(ft.Container(T.txt(label, 13, T.MUTED, ft.FontWeight.W_500),
                                         padding=ft.Padding.symmetric(horizontal=12, vertical=9), ink=True,
                                         on_click=lambda e, i=i: show(i)))
    show_initial = lambda: show(start)  # noqa: E731
    col = ft.Column([ft.Container(bar, border=ft.Border.only(bottom=ft.BorderSide(1, T.BORDER))),
                     ft.Container(body, padding=ft.Padding.only(top=14), expand=True)], expand=True, spacing=0)
    # prime the first tab without update() (controls are not on a page yet)
    for j, b in enumerate(bar.controls):
        on = j == start
        b.content.color = T.ACCENT if on else T.MUTED
        b.border = ft.Border.only(bottom=ft.BorderSide(2, T.ACCENT if on else "transparent"))
    body.content = ft.Column([defs[start][1]()], scroll=ft.ScrollMode.AUTO, expand=True)
    return col


def header(ctx, kind, t, title, chips):
    return ft.Row([ctx.icon(kind, t, size=60, radius=12),
                   ft.Column([T.h1(title), ft.Row(chips, spacing=6)], spacing=6, expand=True)], spacing=16)


def build(ctx, kind, t, refresh, draft=False):
    proj = ctx.state["project"]["custom_skills" if kind == "skill" else "custom_perks"]
    custom = ctx.cache.get(kind + ":draft") if draft else next((c for c in proj if int(c["type"]) == t), None)
    if custom is not None:
        return custom_editor(ctx, kind, copy.deepcopy(custom), refresh, is_new=draft)
    return existing_editor(ctx, kind, t, refresh)


def _wrap(*controls):
    return ft.Container(ft.Column([c for c in controls if c is not None], spacing=14, expand=True),
                        padding=ft.Padding.only(left=26, right=26, top=20, bottom=10), expand=True)


# ====================================================================== existing types
def existing_editor(ctx, kind, t, refresh):
    d = ctx.be.skill(t) if kind == "skill" else ctx.be.perk(t)
    names, descs = dict(d["names"]), dict(d["descs"])
    rows = d["rows"]
    changes = {}
    cols = SKILL_COLS if kind == "skill" else PERK_COLS
    title = names.get("en") or (rows[0]["Name"] if rows else "Type %d" % t)

    def levels_tab():
        if not rows:
            return T.muted("This Type has no rows in the json table.")
        head = [ft.DataColumn(T.muted(c)) for c, _ in cols]
        body = []
        for r in rows:
            cells = []
            for c, key in cols:
                if key is None:
                    cells.append(ft.DataCell(T.txt(r["Id"] if c == "Id" else r["Level"], 12.5, mono=True)))
                else:
                    cells.append(ft.DataCell(T.num_cell(r[key], lambda v, r=r, key=key: changes.setdefault(
                        r["Id"], {"Id": r["Id"]}).__setitem__(key, v), 74)))
            body.append(ft.DataRow(cells=cells))

        def save(e):
            if not changes:
                ctx.toast("Nothing changed")
                return
            fn = server.api_skill_rows if kind == "skill" else server.api_perk_rows
            if ctx.guard(lambda: ctx.be.call(fn, {"type": t, "rows": list(changes.values())}),
                         "Rows saved to the package json") is not None:
                changes.clear()
                ctx.mark_unbuilt()
                ctx.drop("skills", "perks")
        return ft.Column([
            ft.Container(ft.Row([ft.DataTable(columns=head, rows=body, heading_row_height=34, data_row_min_height=46,
                                              data_row_max_height=52, column_spacing=16)], scroll=ft.ScrollMode.AUTO),
                         bgcolor=T.SURFACE, border=ft.Border.all(1, T.BORDER), border_radius=8),
            ft.Row([T.primary("Save rows", save)]),
            T.muted("Saved straight into the package json. The engine reads these on startup; numbers only "
                    "change behaviour where the hard-coded code uses them (see Engine usage).")], spacing=12)

    def names_tab():
        def save(e):
            ctx.guard(lambda: ctx.be.call(server.api_texts, {"kind": kind, "type": t, "names": names,
                                                             "descs": descs}), "Texts saved")
            ctx.drop("skills", "perks")
        return ft.Column([W.texts_editor(ctx, names, descs), ft.Row([T.primary("Save texts", save)])], spacing=12)

    extras = d.get("extras") or {"also": [], "effects": []}

    def behaviour_tab():
        parts = []
        dirty = {"v": False}
        if kind == "skill":
            chips = ft.Row(wrap=True, spacing=6)

            def draw_chips():
                chips.controls.clear()
                for b in extras.setdefault("also", []):
                    chips.controls.append(ft.Chip(label=T.txt("also counts as Type %d" % b, 12), on_delete=lambda e, b=b: (
                        extras["also"].remove(b), draw_chips(), chips.update(), dirty.update(v=True))))
                chips.controls.append(T.button("Add", lambda e: W.pick_type_dialog(
                    ctx, "skill", "Also counts as…", lambda b: (extras["also"].append(b), draw_chips(),
                                                                 ctx.page.update())), ft.Icons.ADD))
            draw_chips()
            parts += [T.h2("Also counts as"),
                      T.muted("A general with this skill also gets the hard-coded behaviour of the listed skill "
                              "Types (their chances and effects come from this skill's rows)."), chips]
        parts += [T.h2("Added stat effects"),
                  T.muted("Extra bonuses applied to the commanded unit by this %s." % kind),
                  W.effects_editor(ctx, extras.setdefault("effects", []), lambda: dirty.update(v=True),
                                   "Row effect value")]

        def save(e):
            body = {"kind": kind, "type": t, "effects": extras["effects"]}
            if kind == "skill":
                body["also"] = extras.get("also", [])
            if ctx.guard(lambda: ctx.be.call(server.api_extras, body), "Saved to the project") is not None:
                ctx.refresh_state()
                ctx.mark_unbuilt()
                ctx.drop("skills", "perks")
        parts.append(ft.Row([T.primary("Save behaviour", save)]))
        return ft.Column(parts, spacing=12)

    def usage_tab():
        if not d["usage"]:
            return T.muted("No hard-coded check for this Type was recognised.")
        rows_ = []
        for u in d["usage"]:
            rows_.append(ft.DataRow(cells=[
                ft.DataCell(T.chip(u["kind"], {"query": T.INFO, "switch": T.ACCENT}.get(u["kind"], T.CUSTOM))),
                ft.DataCell(ft.TextButton(content=T.hexa(u["addr"]), on_click=lambda e, a=u["addr"]: ctx.show("code", a))),
                ft.DataCell(T.txt("%s %s" % (T.hexa(u["func"]), u["func_name"]), 12, T.MUTED, mono=True)),
                ft.DataCell(T.txt(u["note"], 12, T.MUTED))]))
        return ft.Column([T.note("Where the engine checks this Type. Open one in the code browser to read or patch "
                                 "the numbers next to it (chances, percentages, unit classes)."),
                          ft.Container(ft.DataTable(columns=[ft.DataColumn(T.muted(c)) for c in
                                                             ("Kind", "Address", "Function", "What")],
                                                    rows=rows_, heading_row_height=34, data_row_min_height=40),
                                       bgcolor=T.SURFACE, border=ft.Border.all(1, T.BORDER), border_radius=8)], spacing=12)

    def units_tab():
        us = d.get("units", [])
        if not us:
            return T.muted("No unit uses this perk.")
        return ft.Column([T.txt("%s (id %d, army %d, level %d)" % (u["name"], u["id"], u["army"], u["level"]), 12.5)
                          for u in us[:300]], spacing=3)

    tabs = [("Levels", levels_tab), ("Names & text", names_tab), ("Behaviour", behaviour_tab),
            ("Engine usage (%d)" % len(d["usage"]), usage_tab)]
    if kind == "perk":
        tabs.append(("Units (%d)" % len(d.get("units", [])), units_tab))
    chips = [T.chip("Type %d" % t, T.MUTED, mono=True), T.chip("%d level%s" % (len(rows), "" if len(rows) == 1 else "s"))]
    if extras.get("effects") or extras.get("also"):
        chips.append(T.chip("extended", T.CUSTOM))
    if d["original"] is False:
        chips.append(T.chip("not in game data", T.DANGER))
    return _wrap(header(ctx, kind, t, title, chips), tab_view(tabs))


# ====================================================================== custom types
def custom_editor(ctx, kind, item, refresh, is_new):
    from .editors_custom import build_custom
    return build_custom(ctx, kind, item, refresh, is_new)
