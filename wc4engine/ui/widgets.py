"""Widgets shared by the skill and perk editors."""
import base64

import flet as ft

from .. import server
from . import theme as T


def effects_editor(ctx, effects, on_change, row_label):
    """effects: list of dicts {category, classes, from_row, value}, edited in place."""
    st = ctx.state
    box = ft.Column(spacing=8)

    def redraw():
        box.controls.clear()
        for fx in effects:
            box.controls.append(_effect_row(ctx, st, fx, effects, on_change, row_label, redraw))
        box.controls.append(ft.Row([T.button("Add stat effect", lambda e: (
            effects.append({"category": 5, "classes": [], "from_row": True, "value": 0}), on_change(), redraw(),
            box.update()), ft.Icons.ADD)]))

    redraw()
    return box


def _effect_row(ctx, st, fx, effects, on_change, row_label, redraw):
    cats = [(k, v["name"]) for k, v in st["categories"].items()]

    def upd():
        on_change()
        redraw()
        ctx.page.update()

    def set_cat(v):
        fx["category"] = int(v)
        upd()

    def set_src(v):
        fx["from_row"] = v == "row"
        upd()

    def toggle_class(c, on):
        classes = fx["classes"]
        if on and c not in classes:
            classes.append(c)
        if not on and c in classes:
            classes.remove(c)
        upd()

    chips = ft.Row([ft.Chip(label=T.txt(name, 11.5), selected=int(c) in fx["classes"],
                            on_select=lambda e, c=int(c): toggle_class(c, e.control.selected))
                    for c, name in st["unit_classes"].items()], wrap=True, spacing=4, run_spacing=4)
    cat = st["categories"][str(fx["category"])] if str(fx["category"]) in st["categories"] else \
        st["categories"][fx["category"]]
    summary = cat["desc"].replace("{v}", "N" if fx["from_row"] else str(fx["value"]))
    summary += " — " + (", ".join(st["unit_classes"][str(c)] if str(c) in st["unit_classes"] else str(c)
                                  for c in fx["classes"]) or "every unit")
    value_ctl = T.txt("per level", 12, T.FAINT) if fx["from_row"] else T.num_cell(
        fx["value"], lambda v: (fx.__setitem__("value", v), on_change()), 70)
    return ft.Container(
        ft.Column([ft.Row([T.dropdown(cats, fx["category"], set_cat, 170),
                           T.dropdown([("row", row_label), ("fixed", "Fixed value")],
                                      "row" if fx["from_row"] else "fixed", set_src, 190), value_ctl,
                           ft.Container(expand=True),
                           T.icon_button(ft.Icons.DELETE_OUTLINE, lambda e: (effects.remove(fx), upd()),
                                         "Remove effect", T.DANGER)], spacing=10),
                   chips, T.txt(summary, 11.5, T.FAINT)], spacing=6),
        bgcolor=T.SURFACE, border=ft.Border.all(1, T.BORDER), border_radius=7, padding=12)


def texts_editor(ctx, names, descs):
    """names/descs: {lang: text}, edited in place."""
    st = ctx.state
    rows = []
    for lang in st["langs"]:
        n = T.field("Name", names.get(lang, ""), width=230)
        n.on_change = lambda e, l=lang: names.__setitem__(l, e.control.value)
        d = T.field("Description", descs.get(lang, ""), multiline=True, expand=True)
        d.on_change = lambda e, l=lang: descs.__setitem__(l, e.control.value)
        rows.append(ft.Row([ft.Container(ft.Column([T.txt(lang, 13, weight=ft.FontWeight.W_600),
                                                    T.txt(st["lang_names"][lang], 11, T.FAINT)], spacing=0),
                                         width=110), n, d], spacing=10, vertical_alignment=ft.CrossAxisAlignment.START))
    rows.append(T.muted("Empty languages fall back to English when the package is built."))
    return ft.Column(rows, spacing=10)


def pick_dialog(ctx, title, rows, label, on_pick, with_level=None):
    """rows: [{id,...}]; label(row)->str; on_pick(row, level)"""
    state = {"q": "", "chosen": None, "level": 1}
    lv = ft.ListView(height=320, spacing=2)

    def fill():
        lv.controls.clear()
        for r in rows:
            text = "%s  (%s)" % (label(r), r.get("id", r.get("type")))
            if state["q"] and state["q"] not in text.lower():
                continue
            on = state["chosen"] is r
            lv.controls.append(ft.Container(T.txt(text, 13), padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                                            border_radius=5, ink=True, bgcolor=T.soft(T.ACCENT, 0.16) if on else None,
                                            on_click=lambda e, r=r: (state.__setitem__("chosen", r), fill(), lv.update())))
            if len(lv.controls) >= 250:
                break

    search = T.field(None, "", hint="Search")
    search.on_change = lambda e: (state.__setitem__("q", e.control.value.strip().lower()), fill(), lv.update())
    parts = [search, lv]
    if with_level:
        lvl = T.num_cell(1, lambda v: state.__setitem__("level", v), 70)
        parts.append(ft.Row([T.muted(with_level), lvl]))
    fill()

    def done():
        if state["chosen"] is not None:
            on_pick(state["chosen"], state["level"])
    ctx.dialog(title, ft.Column(parts, spacing=10, tight=True), [("Cancel", None, None), ("Add", done, "primary")])


def pick_type_dialog(ctx, kind, title, on_pick):
    items = [i for i in (ctx.be.skills() if kind == "skill" else ctx.be.perks()) if not i["custom"]]
    rows = [{"id": i["type"], "name": i["name"] or i["cn"], "type": i["type"]} for i in items]
    pick_dialog(ctx, title, rows, lambda r: r["name"], lambda r, lv: on_pick(r["type"]))


def icon_chooser(ctx, kind, t, icon, on_change, picker):
    """icon: dict ({} | {from_type} | {png_b64}); picker: a shared ft.FilePicker service."""
    holder = ft.Container()

    def show():
        data = None
        if icon.get("png_b64"):
            data = base64.b64decode(icon["png_b64"])
        elif icon.get("from_type") is not None:
            data = ctx.be.icon(kind, int(icon["from_type"]))
        else:
            data = ctx.be.icon(kind, t)
        holder.content = ft.Image(src=data, width=64, height=64, fit=ft.BoxFit.CONTAIN) if data else \
            ft.Icon(ft.Icons.HIDE_IMAGE_OUTLINED, size=32, color=T.FAINT)
        holder.width = holder.height = 64
        holder.bgcolor = "#0f1419"
        holder.border = ft.Border.all(1, T.BORDER)
        holder.border_radius = 10
        holder.alignment = ft.Alignment.CENTER

    def chosen(base):
        icon.clear()
        icon["from_type"] = base
        on_change()
        show()
        holder.update()

    async def upload(e):
        files = await picker.pick_files(allowed_extensions=["png", "webp", "jpg", "jpeg"], with_data=True)
        if files:
            f = files[0]
            data = f.bytes
            if data is None:
                with open(f.path, "rb") as fh:
                    data = fh.read()
            icon.clear()
            icon["png_b64"] = base64.b64encode(data).decode("ascii")
            on_change()
            show()
            holder.update()

    show()
    return ft.Row([holder, ft.Column([
        ft.Row([T.button("Copy from type", lambda e: pick_type_dialog(ctx, kind, "Copy icon from…", chosen),
                         ft.Icons.COPY),
                T.button("Upload image", upload, ft.Icons.UPLOAD_FILE)], spacing=8),
        T.txt("Uploaded images are scaled to the game's icon size.", 11.5, T.FAINT)], spacing=6)], spacing=14)
