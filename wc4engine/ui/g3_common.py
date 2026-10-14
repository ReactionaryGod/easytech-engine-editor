"""Glory of Generals 3 UI helpers: buff form, buff picker, type info."""
import flet as ft

from ..gog3 import buff_types
from . import theme as T

ARMY_TYPES = {0: "any unit", 1: "infantry", 2: "armor", 3: "artillery", 4: "navy", 5: "air force", 6: "armor (anti-armor)"}


def engine_catalog(ctx):
    return ctx.cached("g3:catalog", ctx.be.app.catalog)


def type_options(ctx):
    cat = engine_catalog(ctx)
    types = sorted(set(cat) | set(buff_types.BUFF_TYPES))
    return [(t, "T%d  %s" % (t, buff_types.label_of(t))) for t in types if t]


def condition_options(ctx):
    conds = ctx.cached("g3:conds", ctx.be.store.conditions)
    return [(0, "0  no condition")] + [(c["id"], "%d  %s%s" % (c["id"], c["english"], "  (custom)" if c["custom"] else ""))
                                       for c in conds]


def drop_cache(ctx):
    ctx.drop("g3:conds", "g3:buffs")


def buff_label(ctx, bid):
    return "%d  %s" % (bid, ctx.be.store.buff_summary(bid))


def type_panel(ctx, t, on_open_code=None):
    """Explains one buff Type: phase, meaning of Value, and what the engine does."""
    label, value_means, notes = buff_types.BUFF_TYPES.get(t, ("Type %d" % t, "?", ""))
    _key, phase, classes = buff_types.phase_of(t)
    sites = engine_catalog(ctx).get(t, [])
    rows = [T.txt("%s" % label, 13.5, weight=ft.FontWeight.W_600),
            T.txt("Phase: %s  (%s)" % (phase, classes), 12, T.MUTED),
            T.txt("Value means: %s" % value_means, 12, T.MUTED)]
    if notes:
        rows.append(T.txt(notes, 12, T.MUTED))
    for u in sites[:6]:
        rows.append(ft.Row([
            ft.TextButton(content=T.txt(T.hexa(u["addr"]), 12, T.ACCENT, mono=True),
                          on_click=lambda e, a=u["addr"]: ctx.show("code", a)),
            T.txt("%s %s" % (u["func_name"] or T.hexa(u["func"]), u["note"]), 11.5, T.FAINT)], spacing=6))
    if not sites:
        rows.append(T.txt("The engine has no case for this Type: the buff would do nothing.", 12, T.DANGER))
    return ft.Container(ft.Column(rows, spacing=3, tight=True), bgcolor=T.SURFACE2, border_radius=8, padding=12,
                        border=ft.Border.all(1, T.BORDER))


def buff_form(ctx, row, on_change, id_editable=False):
    """Editable form for one BuffSettings row (dict, edited in place). Returns a Control."""
    panel = ft.Container()

    def refresh_panel():
        panel.content = type_panel(ctx, row["Type"])

    def num(label, key, w=110, hint=None):
        f = T.field(label, row[key], width=w, number=True, hint=hint)
        f.on_change = lambda e: (_set(key, e.control.value), on_change())
        return f

    def _set(key, v):
        try:
            row[key] = int(v or 0)
        except ValueError:
            pass

    type_dd = T.dropdown(type_options(ctx), row["Type"], lambda v: (row.__setitem__("Type", int(v)), refresh_panel(),
                                                                   panel.update(), on_change()), 360, "Type (what it does)")
    cond_dd = T.dropdown(condition_options(ctx), row["Condition"], lambda v: (row.__setitem__("Condition", int(v)),
                                                                              on_change()), 360, "Condition (when it applies)")
    refresh_panel()
    id_f = T.field("Id", row["Id"], width=110, number=True)
    id_f.read_only = not id_editable
    id_f.on_change = lambda e: (_set("Id", e.control.value), on_change())

    chain_label = T.txt(buff_label(ctx, row["BuffId"]) if row["BuffId"] else "none", 12, T.MUTED)

    def pick_chain(e):
        from .g3_pickers import pick_buff
        pick_buff(ctx, "Chained buff", lambda b: (row.__setitem__("BuffId", b), setattr(chain_label, "value",
                                                  buff_label(ctx, b) if b else "none"), chain_label.update(), on_change()),
                  exclude=row["Id"], allow_none=True)

    return ft.Column([
        ft.Row([id_f, type_dd], spacing=12),
        panel,
        cond_dd,
        ft.Row([num("PR (chance %)", "PR", hint="0-100"), num("Value", "Value"), num("Key", "Key"),
                num("Range", "Range"), num("Round", "Round"), num("EffectId", "EffectId")], spacing=12, wrap=True),
        ft.Row([T.txt("Chained buff:", 12.5, T.MUTED), chain_label, T.button("Choose…", pick_chain),
                T.muted("(an aura buff applies it to nearby units)")], spacing=10),
    ], spacing=12)
