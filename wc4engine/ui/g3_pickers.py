"""GoG3 dialogs: choose a buff, quickly create a buff."""
import flet as ft

from . import g3_common as C
from . import theme as T


def pick_buff(ctx, title, on_pick, exclude=None, allow_none=False, allow_new=True):
    store = ctx.be.store
    rows = [dict(id=b["Id"], label=C.buff_label(ctx, b["Id"])) for b in store.rows("BuffSettings") if b["Id"] != exclude]
    state = {"q": "", "chosen": None}
    lv = ft.ListView(height=340, spacing=2)

    def fill():
        lv.controls.clear()
        for r in rows:
            if state["q"] and state["q"] not in r["label"].lower():
                continue
            on = state["chosen"] == r["id"]
            lv.controls.append(ft.Container(
                T.txt(r["label"], 12.5, mono=True), padding=ft.Padding.symmetric(horizontal=10, vertical=5),
                border_radius=5, ink=True, bgcolor=T.soft(T.ACCENT, 0.16) if on else None,
                on_click=lambda e, i=r["id"]: (state.__setitem__("chosen", i), fill(), lv.update())))
            if len(lv.controls) >= 300:
                break

    search = T.field(None, "", hint="Search by Id, type, value")
    search.on_change = lambda e: (state.__setitem__("q", e.control.value.strip().lower()), fill(), lv.update())
    fill()

    def done():
        if state["chosen"] is not None:
            on_pick(state["chosen"])

    def make_new():
        quick_buff(ctx, lambda b: on_pick(b))
    actions = [("Cancel", None, None)]
    if allow_none:
        actions.append(("No buff", lambda: on_pick(0), None))
    if allow_new:
        actions.append(("New buff…", make_new, None))
    actions.append(("Choose", done, "primary"))
    ctx.dialog(title, ft.Column([search, lv], spacing=10, tight=True), actions, width=640)


def quick_buff(ctx, on_done):
    """Create a buff row and return its id through on_done(id)."""
    store = ctx.be.store
    row = dict(Id=store.new_buff_id(), Condition=0, PR=100, Type=37, Key=0, Value=10, BuffId=0, Range=0, Round=0,
               EffectId=0)

    def save():
        if ctx.guard(lambda: store.save_buff(row, create=True), "Buff %d created" % row["Id"]) is not None:
            C.drop_cache(ctx)
            on_done(row["Id"])
    form = C.buff_form(ctx, row, lambda: None)
    ctx.dialog("New buff", ft.Column([form], scroll=ft.ScrollMode.AUTO, height=520), [
        ("Cancel", None, None), ("Create", save, "primary")], width=760)
