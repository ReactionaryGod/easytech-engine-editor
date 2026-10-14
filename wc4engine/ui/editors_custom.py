"""Editor for custom skills and perks (new Types added by the engine extension)."""
import flet as ft

from .. import server
from . import theme as T
from . import widgets as W
from .editors import header, tab_view, _wrap

SKILL_LEVEL_FIELDS = [("Chance %", "chance"), ("Effect", "effect"), ("Cost", "cost"), ("Score", "score")]
PERK_LEVEL_FIELDS = [("Chance %", "chance"), ("Effect", "effect"), ("Second", "second"), ("Range", "range"),
                     ("Round", "round"), ("CD", "cd"), ("Condition", "condition"), ("Buff", "buff"),
                     ("Buff rnd", "buff_round"), ("Related", "related"), ("AA", "antiair"), ("Aura", "auras")]


def _picker(ctx):
    p = ctx.cache.get("file_picker")
    if p is None:
        p = ft.FilePicker()
        ctx.page.services.append(p)
        ctx.cache["file_picker"] = p
    return p


def build_custom(ctx, kind, item, refresh, is_new):
    old_type = None if is_new else int(item["type"])
    names, descs = item.setdefault("names", {}), item.setdefault("descs", {})
    fields = SKILL_LEVEL_FIELDS if kind == "skill" else PERK_LEVEL_FIELDS
    state = {"dirty": False}
    ref = {}

    def touch():
        state["dirty"] = True

    # ------------------------------------------------------------------ general tab
    def general_tab():
        type_f = T.num_cell(item["type"], lambda v: (item.__setitem__("type", v), touch()), 100)
        parts = [ft.Row([ft.Column([T.muted("Type"), type_f], spacing=4),
                         T.muted("Pick a Type that does not exist in the game data. The editor refuses used ones.")],
                        spacing=14, vertical_alignment=ft.CrossAxisAlignment.END)]
        if kind == "skill":
            series = T.num_cell(item.get("series", 0), lambda v: (item.__setitem__("series", v), touch()), 80)
            pct = T.toggle(item.get("if_percent", 0), lambda v: (item.__setitem__("if_percent", int(v)), touch()),
                           "Effect is a percentage")
            opn = T.toggle(item.get("open_default", 0), lambda v: (item.__setitem__("open_default", int(v)), touch()),
                           "Unlocked from the start")
            parts += [ft.Row([ft.Column([T.muted("Series (UI group 0-5)"), series], spacing=4), pct, opn], spacing=24),
                      T.h2("Behaves like"),
                      T.muted("The skill also triggers every hard-coded effect of the listed skills. The first one "
                              "also decides which branch the damage code takes for this skill. Leave empty for a "
                              "skill that only uses the stat effects below."),
                      _bases_row()]
        else:
            base = item.get("base", 0)
            base_f = T.num_cell(base, lambda v: (item.__setitem__("base", v), touch()), 100)
            ref["base_f"] = base_f
            parts += [T.h2("Behaves like"),
                      T.muted("The unit gets the hard-coded behaviour of this perk Type, with this perk's numbers. "
                              "Tooltips and icons still show this perk. 0 = no engine behaviour, stat effects only."),
                      ft.Row([base_f,
                              T.button("Choose…", lambda e: W.pick_type_dialog(ctx, "perk", "Behaves like…", set_base))])]
        parts += [T.h2("Icon"), W.icon_chooser(ctx, kind, int(item["type"]), item.setdefault("icon", {}), touch,
                                                 _picker(ctx))]
        return ft.Column(parts, spacing=12)

    def set_base(b):
        item["base"] = b
        touch()
        ref["base_f"].value = str(b)
        ctx.page.update()

    def _bases_row():
        row = ft.Row(wrap=True, spacing=6)

        def draw():
            row.controls.clear()
            for b in item.setdefault("bases", []):
                row.controls.append(ft.Chip(label=T.txt("Type %d" % b, 12), on_delete=lambda e, b=b: (
                    item["bases"].remove(b), touch(), draw(), row.update())))
            row.controls.append(T.button("Add", lambda e: W.pick_type_dialog(
                ctx, "skill", "Behaves like…", lambda b: (item["bases"].append(b), touch(), draw(), ctx.page.update())),
                ft.Icons.ADD))
        draw()
        return row

    # ------------------------------------------------------------------ levels tab
    def levels_tab():
        box = ft.Column(spacing=10)

        def draw():
            box.controls.clear()
            heads = [ft.DataColumn(T.muted("Lv"))] + [ft.DataColumn(T.muted(c)) for c, _ in fields] + \
                    [ft.DataColumn(T.muted(""))]
            body = []
            for i, lv in enumerate(item["levels"]):
                cells = [ft.DataCell(T.txt(i + 1, 12.5, mono=True))]
                for _, key in fields:
                    cells.append(ft.DataCell(T.num_cell(lv.get(key, 0), lambda v, lv=lv, key=key: (
                        lv.__setitem__(key, v), touch()), 72)))
                cells.append(ft.DataCell(T.icon_button(ft.Icons.DELETE_OUTLINE, lambda e, i=i: remove(i), "Remove level",
                                                       T.DANGER)))
                body.append(ft.DataRow(cells=cells))
            box.controls.append(ft.Container(ft.Row([ft.DataTable(columns=heads, rows=body, heading_row_height=34,
                                                                  data_row_min_height=46, data_row_max_height=52,
                                                                  column_spacing=14)], scroll=ft.ScrollMode.AUTO),
                                             bgcolor=T.SURFACE, border=ft.Border.all(1, T.BORDER), border_radius=8))
            box.controls.append(ft.Row([T.button("Add level", add, ft.Icons.ADD)]))

        def add(e):
            item["levels"].append(dict(item["levels"][-1]) if item["levels"] else {"chance": 100, "effect": 0})
            touch()
            draw()
            box.update()

        def remove(i):
            if len(item["levels"]) <= 1:
                ctx.toast("A %s needs at least one level" % kind, error=True)
                return
            item["levels"].pop(i)
            touch()
            draw()
            box.update()
        draw()
        notes = {"skill": "Each level is one row of SkillSettings. Upgrade ids are chained automatically; the "
                          "Effect column is the value the hard-coded behaviours read (percent when the skill is "
                          "a percentage skill).",
                 "perk": "Each level is one row of ArmyFeatureSettings. Fields beyond Effect/Second are only "
                         "meaningful for the base perk's behaviour (see the base perk in the list)."}
        return ft.Column([T.muted(notes[kind]), box], spacing=10)

    # ------------------------------------------------------------------ effects tab
    def effects_tab():
        return ft.Column([T.muted("Stat bonuses applied to the commanded unit by this %s, on top of the behaviour "
                                  "above." % kind),
                          W.effects_editor(ctx, item.setdefault("effects", []), touch,
                                           "Level effect value")], spacing=10)

    # ------------------------------------------------------------------ assignments tab
    def assign_tab():
        box = ft.Column(spacing=6)
        key = "generals" if kind == "skill" else "units"
        lst = item.setdefault(key, [])
        pool = ctx.be.generals() if kind == "skill" else ctx.be.units()
        label_of = (lambda r: r["name"]) if kind == "skill" else (lambda r: "%s (army %d)" % (r["name"], r["army"]))
        by_id = {r["id"]: r for r in pool}

        def draw():
            box.controls.clear()
            for a in lst:
                r = by_id.get(int(a["id"]))
                box.controls.append(ft.Row([
                    T.txt("%s  (%s)" % (label_of(r) if r else "unknown", a["id"]), 13, expand=True),
                    T.muted("level"), T.num_cell(a.get("level", 1), lambda v, a=a: (a.__setitem__("level", v), touch()), 64),
                    T.icon_button(ft.Icons.CLOSE, lambda e, a=a: (lst.remove(a), touch(), draw(), box.update()),
                                  "Remove", T.DANGER)], spacing=10))
            if not lst:
                box.controls.append(T.muted("None assigned."))

        def add(e):
            W.pick_dialog(ctx, "Add " + ("general" if kind == "skill" else "unit"), pool, label_of,
                          lambda r, lv: (lst.append({"id": r["id"], "level": lv if lv else 1}), touch(), draw(),
                                         ctx.page.update()),
                          with_level="Starting level")
        draw()
        what = "Generals that get this skill" if kind == "skill" else "Units that get this perk"
        extra = T.muted("Written into GeneralSettings.Skills at the chosen skill level." if kind == "skill" else
                        "Written into ArmySettings.Feature / FeatureLevel.")
        return ft.Column([T.h2(what), extra, box, ft.Row([T.button("Add", add, ft.Icons.ADD)])], spacing=10)

    # ------------------------------------------------------------------ names tab
    def names_tab():
        return W.texts_editor(ctx, names, descs)

    # ------------------------------------------------------------------ save / delete
    def save(e):
        for lang in list(names):
            if not names[lang]:
                names.pop(lang)
        for lang in list(descs):
            if not descs[lang]:
                descs.pop(lang)
        if not names.get("en"):
            ctx.toast("Give the %s an English name" % kind, error=True)
            return
        if kind == "skill" and "cn" not in names:
            pass
        r = ctx.guard(lambda: ctx.be.call(server.api_custom_save, {"kind": kind, "item": item,
                                                                   "old_type": old_type}), "Saved to the project")
        if r is not None:
            ctx.cache.pop(kind + ":draft", None)
            ctx.refresh_state()
            ctx.mark_unbuilt()
            ctx.drop("skills", "perks")
            refresh(int(item["type"]))

    def delete(e):
        def yes():
            if ctx.guard(lambda: ctx.be.call(server.api_custom_delete, {"kind": kind, "type": old_type}),
                         "Removed") is not None:
                ctx.refresh_state()
                ctx.mark_unbuilt()
                ctx.drop("skills", "perks")
                refresh(None)
        ctx.confirm("Delete %s" % kind, "Remove custom %s %s from the project? Its json rows and texts are "
                    "removed on the next build." % (kind, old_type), "Delete", yes)

    tabs = [("General", general_tab), ("Levels", levels_tab), ("Stat effects", effects_tab),
            ("Assigned to", assign_tab), ("Names & text", names_tab)]
    actions = [T.primary("Save", save, ft.Icons.SAVE_OUTLINED)]
    if not is_new:
        actions.append(T.button("Delete", delete, ft.Icons.DELETE_OUTLINE, color=T.DANGER))
    chips = [T.chip("custom", T.CUSTOM), T.chip("Type %s" % item["type"], T.MUTED, mono=True)]
    if is_new:
        chips.append(T.chip("not saved yet", T.ACCENT))
    title = names.get("en") or "Unnamed %s" % kind
    return _wrap(ft.Row([ft.Container(header(ctx, kind, int(item["type"]), title, chips), expand=True), *actions],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER),
                 tab_view(tabs))
