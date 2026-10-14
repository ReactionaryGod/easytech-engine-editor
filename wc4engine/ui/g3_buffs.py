"""GoG3 buffs (BuffSettings), engine buff-type reference, and conditions (def_buff.xml)."""
import flet as ft

from ..gog3 import buff_types
from ..gog3 import conditions as cond
from . import g3_common as C
from . import theme as T
from . import widgets as W
from .page_content import Item, Provider


def _wrap(*controls):
    return ft.Container(ft.Column([c for c in controls if c is not None], spacing=14, scroll=ft.ScrollMode.AUTO,
                                  expand=True), padding=ft.Padding.only(left=26, right=26, top=20, bottom=20),
                        expand=True)


# ====================================================================== buffs
class BuffProvider(Provider):
    kind = "g3buff"
    new_label = "New buff"
    search_hint = "Search by Id, type, condition"
    filters = [("all", "All"), ("new", "New"), ("unused", "Unused")]

    def items(self):
        store = self.ctx.be.store
        used = set()
        for s in store.rows("SkillSettings"):
            used.add(s["BuffId"])
        for f in store.rows("ArmyFeatureSettings"):
            used.update(f["BuffId"])
        for b in store.rows("BuffSettings"):
            if b["BuffId"]:
                used.add(b["BuffId"])
        out = []
        for b in store.rows("BuffSettings"):
            tags = []
            if b["Id"] >= 7001:
                tags.append("new")
            if b["Id"] not in used:
                tags.append("unused")
            out.append(Item(b["Id"], "%d  %s" % (b["Id"], buff_types.label_of(b["Type"])),
                            "T%d · value %d · PR %d%% · cond %d%s" % (b["Type"], b["Value"], b["PR"], b["Condition"],
                                                                      " · chain %d" % b["BuffId"] if b["BuffId"] else ""),
                            chips=[("new", T.CUSTOM)] if "new" in tags else [],
                            search="%d %s %d %d" % (b["Id"], buff_types.label_of(b["Type"]), b["Type"], b["Condition"]),
                            tags=tags))
        return out

    def detail(self, key, refresh):
        row = dict(next(b for b in self.ctx.be.store.rows("BuffSettings") if b["Id"] == key))
        return buff_editor(self.ctx, row, refresh, is_new=False)

    def new(self, refresh):
        store = self.ctx.be.store
        row = dict(Id=store.new_buff_id(), Condition=0, PR=100, Type=37, Key=0, Value=10, BuffId=0, Range=0, Round=0,
                   EffectId=0)
        return row["Id"], buff_editor(self.ctx, row, refresh, is_new=True)

    def placeholder(self):
        return "Select a buff, or create one. Skills and perks are lists of buffs."


def buff_editor(ctx, row, refresh, is_new):
    store = ctx.be.store

    def save(e):
        if ctx.guard(lambda: store.save_buff(row, create=is_new), "Buff saved") is not None:
            C.drop_cache(ctx)
            refresh(row["Id"])

    def clone(e):
        copy = dict(row, Id=store.new_buff_id())
        if ctx.guard(lambda: store.save_buff(copy, create=True), "Cloned as %d" % copy["Id"]) is not None:
            refresh(copy["Id"])

    def delete(e):
        def yes():
            if ctx.guard(lambda: store.delete_buff(row["Id"]), "Buff deleted") is not None:
                refresh(None)
        ctx.confirm("Delete buff", "Delete buff %d?" % row["Id"], "Delete", yes)

    use = [] if is_new else store.buff_usage(row["Id"])
    use_rows = [T.txt("%s %s  %s" % (k, i, n), 12.5) for k, i, n in use] or [T.muted("Nothing uses this buff.")]
    acts = [T.primary("Save", save, ft.Icons.SAVE_OUTLINED)]
    if not is_new:
        acts += [T.button("Clone", clone, ft.Icons.COPY), T.button("Delete", delete, ft.Icons.DELETE_OUTLINE, color=T.DANGER)]
    return _wrap(ft.Row([T.h1("Buff %d%s" % (row["Id"], "  (new)" if is_new else "")), ft.Container(expand=True), *acts],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER),
                 C.buff_form(ctx, row, lambda: None, id_editable=is_new),
                 T.section("Used by"), *use_rows)


# ====================================================================== buff types (reference)
class TypeProvider(Provider):
    kind = "g3type"
    new_label = ""
    search_hint = "Search by Type or meaning"
    filters = [("all", "All"), ("used", "Used in game data"), ("unused", "Engine only")]

    def items(self):
        store = self.ctx.be.store
        cat = C.engine_catalog(self.ctx)
        counts = {}
        for b in store.rows("BuffSettings"):
            counts[b["Type"]] = counts.get(b["Type"], 0) + 1
        out = []
        for t in sorted(set(cat) | set(buff_types.BUFF_TYPES) | set(counts)):
            if t == 0:
                continue
            _k, phase, _c = buff_types.phase_of(t)
            tags = ["used"] if counts.get(t) else ["unused"]
            out.append(Item(t, "T%d  %s" % (t, buff_types.label_of(t)), phase,
                            side="%d buffs" % counts[t] if counts.get(t) else "engine only",
                            search="%d %s %s" % (t, buff_types.label_of(t), phase), tags=tags))
        return out

    def detail(self, key, refresh):
        store = self.ctx.be.store
        buffs = [b for b in store.rows("BuffSettings") if b["Type"] == key]
        rows = []
        for b in buffs[:80]:
            rows.append(ft.Row([T.txt(C.buff_label(self.ctx, b["Id"]), 12, mono=True, expand=True),
                                T.txt("cond %d" % b["Condition"], 11.5, T.FAINT)], spacing=10))
        sites = C.engine_catalog(self.ctx).get(key, [])
        srows = [ft.Row([ft.TextButton(content=T.txt(T.hexa(u["addr"]), 12, T.ACCENT, mono=True),
                                       on_click=lambda e, a=u["addr"]: self.ctx.show("code", a)),
                         T.txt("%s  %s  %s" % (u["kind"], u["func_name"] or T.hexa(u["func"]), u["note"]), 12, T.MUTED)])
                 for u in sites]
        return _wrap(T.h1("Type %d" % key), C.type_panel(self.ctx, key), T.section("Engine implementation (%d)" % len(sites)),
                     *(srows or [T.muted("Not implemented.")]),
                     T.section("Buffs in the game data using it (%d)" % len(buffs)), *(rows or [T.muted("None.")]),
                     T.note("Adding a brand-new Type means writing code in libiron.so (use the code browser). "
                            "Everything else can be built from the existing Types, conditions and chained buffs.", T.INFO))


# ====================================================================== conditions
class ConditionProvider(Provider):
    kind = "g3cond"
    new_label = "New condition"
    search_hint = "Search by id or text"
    filters = [("all", "All"), ("custom", "Custom")]

    def items(self):
        out = []
        for c in self.ctx.be.store.conditions():
            out.append(Item(c["id"], "%d  %s" % (c["id"], c["english"]), "%s · %s" % (c["op"], c["desc"]),
                            chips=[("custom", T.CUSTOM)] if c["custom"] else [],
                            search="%d %s %s" % (c["id"], c["english"], c["desc"]), tags=["custom"] if c["custom"] else []))
        return out

    def detail(self, key, refresh):
        cs = {c["id"]: c for c in self.ctx.be.store.conditions()}
        return condition_editor(self.ctx, dict(cs[key]), refresh, is_new=False)

    def new(self, refresh):
        c = dict(id=self.ctx.be.store.next_condition_id(), scope="army", op="comp", compare="equal", desc="", custom=True,
                 params=[dict(origin="self", proptype=1, value=None), dict(origin="constant", proptype=None, value="1")],
                 children=[])
        return c["id"], condition_editor(self.ctx, c, refresh, is_new=True)

    def placeholder(self):
        return "Select a condition. Conditions decide when a buff applies; you can combine them with AND / OR / NOT."


def condition_editor(ctx, c, refresh, is_new):
    store = ctx.be.store
    editable = c["custom"] or is_new
    box = ft.Column(spacing=12)

    def draw():
        box.controls.clear()
        by = {x["id"]: x for x in store.conditions()}
        by[c["id"]] = c
        box.controls.append(T.txt(cond.describe(c, by), 13.5, weight=ft.FontWeight.W_500))
        if not editable:
            box.controls.append(T.note("Original game conditions are read-only here. Make a new one that combines them.",
                                       T.INFO))
            if c["op"] == "comp":
                for p in c["params"]:
                    box.controls.append(T.txt("param: %s" % p, 12, T.MUTED, mono=True))
            else:
                box.controls.append(T.txt("%s of %s" % (c["op"], c["children"]), 12, T.MUTED, mono=True))
            return
        desc = T.field("Description (free text, shown in the file)", c["desc"], expand=True)
        desc.on_change = lambda e: c.__setitem__("desc", e.control.value)
        op = T.dropdown([(o, o) for o in cond.OPS], c["op"], lambda v: (c.__setitem__("op", v), reshape(), draw(),
                                                                         ctx.page.update()), 140, "Kind")
        box.controls.append(ft.Row([op, desc], spacing=12))
        if c["op"] == "comp":
            a = c["params"][0] if c["params"] else dict(origin="self", proptype=1, value=None)
            b = c["params"][1] if len(c["params"]) > 1 else dict(origin="constant", proptype=None, value="1")
            c["params"] = [a, b]
            who = T.dropdown([("self", "the unit"), ("target", "the target")], a["origin"],
                             lambda v: a.__setitem__("origin", v), 150, "Whose")
            prop = T.dropdown(list(cond.ARMY_PROPS.items()), a["proptype"] or 1,
                              lambda v: a.__setitem__("proptype", int(v)), 260, "Property")
            cmp_ = T.dropdown([(x, x) for x in cond.COMPARES], c["compare"] or "equal",
                              lambda v: c.__setitem__("compare", v), 150, "Compare")
            val = T.field("Value (number, or 1,2,3 for several)", b["value"] or "1", width=240)
            val.on_change = lambda e: (b.__setitem__("value", e.control.value),
                                       b.__setitem__("origin", "array" if "," in e.control.value else "constant"))
            box.controls.append(ft.Row([who, prop, cmp_, val], spacing=12, wrap=True))
            box.controls.append(T.muted("Unit classes: 1 infantry, 2 armor, 3 artillery, 4 navy, 5 air force."))
        else:
            kids = ft.Column(spacing=4)

            def draw_kids():
                kids.controls.clear()
                for k in c["children"]:
                    kids.controls.append(ft.Row([T.txt(cond.describe(by[k], by) if k in by else "#%d" % k, 12.5,
                                                       expand=True),
                                                 T.txt(str(k), 11.5, T.FAINT, mono=True),
                                                 T.icon_button(ft.Icons.CLOSE, lambda e, k=k: (c["children"].remove(k),
                                                                                                draw(), ctx.page.update()),
                                                               "Remove", T.DANGER)], spacing=10))

            def add(e):
                pool = [dict(id=x["id"], name=x["english"]) for x in by.values() if x["id"] != c["id"]]
                W.pick_dialog(ctx, "Add condition", pool, lambda r: r["name"], lambda r, lv: (
                    c["children"].append(r["id"]), draw(), ctx.page.update()))
            draw_kids()
            box.controls += [T.txt({"and": "All of these must be true:", "or": "Any of these must be true:",
                                    "not": "None of these may be true:"}[c["op"]], 12.5, T.MUTED), kids,
                             ft.Row([T.button("Add condition", add, ft.Icons.ADD)])]

    def reshape():
        if c["op"] == "comp" and len(c["params"]) < 2:
            c["params"] = [dict(origin="self", proptype=1, value=None), dict(origin="constant", proptype=None, value="1")]
        if c["op"] != "comp" and not c["children"]:
            c["children"] = []

    def customs():
        return [dict(x, scope="army") for x in store.conditions() if x["custom"] and x["id"] != c["id"]]

    def save(e):
        if not c["desc"]:
            ctx.toast("Add a short description", error=True)
            return
        if c["op"] != "comp" and not c["children"]:
            ctx.toast("Add at least one condition to combine", error=True)
            return
        if ctx.guard(lambda: store.save_custom_conditions(customs() + [c]), "Condition saved") is not None:
            C.drop_cache(ctx)
            refresh(c["id"])

    def delete(e):
        def yes():
            use = [b["Id"] for b in store.rows("BuffSettings") if b["Condition"] == c["id"]]
            if use:
                ctx.toast("Still used by buffs %s" % use[:6], error=True)
                return
            if ctx.guard(lambda: store.save_custom_conditions(customs()), "Condition deleted") is not None:
                C.drop_cache(ctx)
                refresh(None)
        ctx.confirm("Delete condition", "Delete condition %d?" % c["id"], "Delete", yes)

    draw()
    acts = []
    if editable:
        acts.append(T.primary("Save", save, ft.Icons.SAVE_OUTLINED))
        if not is_new:
            acts.append(T.button("Delete", delete, ft.Icons.DELETE_OUTLINE, color=T.DANGER))
    return _wrap(ft.Row([T.h1("Condition %d%s" % (c["id"], "  (new)" if is_new else "")), ft.Container(expand=True),
                         *acts], vertical_alignment=ft.CrossAxisAlignment.CENTER), box)
