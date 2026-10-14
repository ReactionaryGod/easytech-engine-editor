"""Engine patches: named patch options and the project's assembly patches."""
import flet as ft

from .. import server
from . import theme as T

CHALLENGE_LABELS = {"vanilla": "Vanilla caps", "removed": "Caps removed", "tier12": "Removed + tier-12 elites"}


def _set(ctx, key, value):
    if ctx.guard(lambda: ctx.be.save_project(options={key: value})) is not None:
        ctx.mark_unbuilt()
        ctx.show("patches")


def _sites(ctx, sites):
    return ft.Row([ft.Container(T.chip(T.hexa(a), T.ACCENT, mono=True), on_click=lambda e, a=a: ctx.show("code", a),
                                tooltip="Open in code browser") for a in sites], wrap=True, spacing=6)


def _patch_table(ctx, patches):
    if not patches:
        return T.card(T.muted("No assembly patches yet. In the code browser, select an instruction, type the "
                              "replacement and press “Add to project”."))

    def edit(i, **kw):
        return ctx.guard(lambda: ctx.be.call(server.api_patch_edit, dict(index=i, **kw)))

    def delete(i, p):
        def yes():
            if edit(i, delete=True) is not None:
                ctx.mark_unbuilt()
                ctx.refresh_state()
                ctx.show("patches")
        ctx.confirm("Delete patch", "Remove the patch at %s from the project?" % p["addr"], "Delete", yes)

    rows = []
    for i, p in enumerate(patches):
        note = T.field(None, p.get("note", ""), width=220, hint="note")
        note.on_blur = lambda e, i=i: edit(i, note=e.control.value)
        rows.append(ft.DataRow(cells=[
            ft.DataCell(T.toggle(p.get("enabled", True), lambda v, i=i: (edit(i, enabled=v), ctx.mark_unbuilt()))),
            ft.DataCell(ft.TextButton(content=p["addr"], on_click=lambda e, a=p["addr"]: ctx.show("code", int(a, 16)))),
            ft.DataCell(T.txt("%s → %s" % (p["orig"], p["hex"]), 12, mono=True)),
            ft.DataCell(T.txt(p.get("asm", ""), 12, mono=True)),
            ft.DataCell(note),
            ft.DataCell(T.icon_button(ft.Icons.DELETE_OUTLINE, lambda e, i=i, p=p: delete(i, p), "Delete",
                                      T.DANGER)),
        ]))
    return ft.Container(ft.DataTable(columns=[ft.DataColumn(T.muted(c)) for c in
                                              ("On", "Address", "Bytes", "Assembly", "Note", "")],
                                     rows=rows, heading_row_height=36, data_row_min_height=44,
                                     data_row_max_height=52, column_spacing=18),
                        bgcolor=T.SURFACE, border=ft.Border.all(1, T.BORDER), border_radius=8)


def view(ctx, arg):
    st = ctx.refresh_state()
    if ctx.game == "gog3":
        return T.scroll_page(
            T.page_header("Assembly patches", "Instruction-level changes to libiron.so. Add them from the code browser; "
                          "they are applied to the input library when you build."),
            T.note("libiron.so of this game is already a modified build (lib.so credited to a third party), so no "
                   "known-patch list exists: use the code browser to read and change what you need.", T.INFO),
            T.section("Assembly patches", T.button("Open code browser", lambda e: ctx.show("code"), ft.Icons.CODE)),
            _patch_table(ctx, st["project"]["asm_patches"]))
    opt = st["project"]["options"]
    info = {p["id"]: p for p in st["patch_info"]}

    seg = ft.SegmentedButton(
        segments=[ft.Segment(value=k, label=CHALLENGE_LABELS[k], disabled=(k == "tier12" and not opt["engine_ext"]))
                  for k in st["challenge_states"]],
        selected=[opt["challenge"]], allow_empty_selection=False, allow_multiple_selection=False,
        on_change=lambda e: _set(ctx, "challenge", list(e.control.selected)[0]))
    challenge = T.card(T.h2(info["challenge"]["name"]), T.muted(info["challenge"]["desc"]), seg,
                       T.txt(st["challenge_states"][opt["challenge"]], 12.5, T.TEXT), _sites(ctx, info["challenge"]["sites"]))

    def toggled_card(pid, key):
        return T.card(ft.Row([T.h2(info[pid]["name"]), ft.Container(expand=True),
                              T.toggle(opt[key], lambda v: _set(ctx, key, v))]),
                      T.muted(info[pid]["desc"]), _sites(ctx, info[pid]["sites"]) if info[pid]["sites"] else None)

    ext = toggled_card("engine_ext", "engine_ext")
    ext.content.controls.append(ft.Row([T.toggle(opt["legacy_skins"], lambda v: _set(ctx, "legacy_skins", v)),
                                        T.txt("Keep the built-in BM-21 (crit chance) and Hawkeye (crit damage) skin "
                                              "bonuses for EliteSkinSettings.Effect below 1000", 12.5)]))
    if not opt["engine_ext"]:
        ext.content.controls.append(T.note("Custom skills and perks, stat effects and the data-driven elite-skin "
                                           "effects need the extension. With it off their json rows are still "
                                           "written but the engine ignores them.", T.ACCENT))
    bank = T.card(ft.Row([T.h2(info["general_bank"]["name"]), ft.Container(expand=True),
                          T.chip("built into the base", T.OK)]),
                  T.muted(info["general_bank"]["desc"]), _sites(ctx, info["general_bank"]["sites"]))
    return T.scroll_page(
        T.page_header("Engine patches", "Known changes to the engine code. Choices are saved in the project and "
                      "applied on the next build."),
        challenge, toggled_card("mf_picker", "mf_picker"), ext, bank,
        T.section("Assembly patches", T.button("Open code browser", lambda e: ctx.show("code"), ft.Icons.CODE)),
        _patch_table(ctx, st["project"]["asm_patches"]))
