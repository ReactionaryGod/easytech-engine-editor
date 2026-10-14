"""GoG3 skills (SkillSettings) and perks (ArmyFeatureSettings)."""
import copy

import flet as ft

from . import g3_common as C
from . import g3_pickers as P
from . import theme as T
from . import widgets as W
from .editors import tab_view
from .page_content import Item, Provider


def _picker(ctx):
    p = ctx.cache.get("file_picker")
    if p is None:
        p = ft.FilePicker()
        ctx.page.services.append(p)
        ctx.cache["file_picker"] = p
    return p


def _header(ctx, kind, rid, title, chips, actions):
    return ft.Row([ctx.icon(kind, rid, size=60, radius=12),
                   ft.Column([T.h1(title), ft.Row(chips, spacing=6)], spacing=6, expand=True), *actions], spacing=16,
                  vertical_alignment=ft.CrossAxisAlignment.CENTER)


def _wrap(*controls):
    return ft.Container(ft.Column([c for c in controls if c is not None], spacing=14, expand=True),
                        padding=ft.Padding.only(left=26, right=26, top=20, bottom=10), expand=True)


def _icon_row(ctx, kind, rid, on_png):
    """Preview + upload button; on_png(bytes) receives the chosen image."""
    holder = ft.Container(width=64, height=64, bgcolor="#0f1419", border=ft.Border.all(1, T.BORDER), border_radius=10,
                          alignment=ft.Alignment.CENTER)

    def show(data):
        holder.content = ft.Image(src=data, width=64, height=64, fit=ft.BoxFit.CONTAIN) if data else \
            ft.Icon(ft.Icons.HIDE_IMAGE_OUTLINED, size=30, color=T.FAINT)

    show(ctx.be.icon(kind, rid) if rid else None)
    picker = _picker(ctx)

    async def upload(e):
        files = await picker.pick_files(allowed_extensions=["png", "webp", "jpg", "jpeg"], with_data=True)
        if not files:
            return
        data = files[0].bytes
        if data is None:
            with open(files[0].path, "rb") as fh:
                data = fh.read()
        on_png(data)
        show(data)
        holder.update()
    return ft.Row([holder, T.button("Upload image", upload, ft.Icons.UPLOAD_FILE),
                   T.muted("Saved with the entry. Skills use an 80x80 icon, perks 60x60.")], spacing=14)


# ====================================================================== skills
class SkillProvider(Provider):
    kind = "g3skill"
    new_label = "New skill"
    search_hint = "Search by name, Type or Id"
    filters = [("all", "All"), ("used", "Given to generals")]

    def items(self):
        out = []
        for g in self.ctx.be.store.skill_groups():
            out.append(Item(g["type"], g["name"] or g["cn"], "Type %d · %d level%s · ids %s" % (
                g["type"], g["levels"], "" if g["levels"] == 1 else "s", ", ".join(map(str, g["ids"]))),
                icon=self.ctx.icon("skill", g["ids"][0], size=34), side="%d gen." % g["generals"] if g["generals"] else "",
                search="%s %s %s %s" % (g["name"], g["cn"], g["type"], g["ids"]),
                tags=["used"] if g["generals"] else []))
        return out

    def detail(self, key, refresh):
        d = self.ctx.be.store.skill_detail(key)
        return skill_editor(self.ctx, d, refresh, is_new=False)

    def new(self, refresh):
        store = self.ctx.be.store
        t = store.new_skill_type()
        d = dict(type=t, rows=[dict(Id=None, Level=1, ArmyType=0, BuffId=0, Name="", names={"en": "New skill"},
                                    descs={"en": "Describe the skill. {1} = buff value, {2} = range, {0} = chance."},
                                    summary="")])
        return t, skill_editor(self.ctx, d, refresh, is_new=True)

    def placeholder(self):
        return "Select a skill, or create a new one. Each skill is a list of levels; each level points at one buff."


def skill_editor(ctx, d, refresh, is_new):
    store = ctx.be.store
    rows = copy.deepcopy(d["rows"])
    t = d["type"]
    icons = {}                                  # row index -> png bytes

    def title():
        return (rows[0]["names"].get("en") or rows[0]["Name"] or "Skill %d" % t) if rows else "Skill %d" % t

    # ------------------------------------------------------------------ levels
    def levels_tab():
        box = ft.Column(spacing=10)

        def draw():
            box.controls.clear()
            body = []
            for i, r in enumerate(rows):
                buff_txt = T.txt(C.buff_label(ctx, r["BuffId"]) if r["BuffId"] else "no buff", 12, T.MUTED, mono=True,
                                 width=330, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS)

                def choose(e, r=r, buff_txt=buff_txt):
                    P.pick_buff(ctx, "Buff for level %d" % r["Level"], lambda b: (r.__setitem__("BuffId", b),
                                                                                  draw(), box.update()), allow_none=True)
                body.append(ft.DataRow(cells=[
                    ft.DataCell(T.num_cell(r["Level"], lambda v, r=r: r.__setitem__("Level", v), 60)),
                    ft.DataCell(T.dropdown(list(C.ARMY_TYPES.items()), r["ArmyType"], lambda v, r=r: r.__setitem__(
                        "ArmyType", int(v)), 190)),
                    ft.DataCell(ft.Row([buff_txt, T.button("Choose…", choose)], spacing=8)),
                    ft.DataCell(T.icon_button(ft.Icons.DELETE_OUTLINE, lambda e, i=i: remove(i), "Remove level", T.DANGER))]))
            box.controls.append(ft.Container(ft.Row([ft.DataTable(
                columns=[ft.DataColumn(T.muted(c)) for c in ("Level", "Applies to unit class", "Buff", "")], rows=body,
                heading_row_height=34, data_row_min_height=52, data_row_max_height=56, column_spacing=18)],
                scroll=ft.ScrollMode.AUTO), bgcolor=T.SURFACE, border=ft.Border.all(1, T.BORDER), border_radius=8))
            box.controls.append(ft.Row([T.button("Add level", add, ft.Icons.ADD)]))

        def add(e):
            last = rows[-1] if rows else {}
            rows.append(dict(Id=None, Level=(last.get("Level", 0) + 1), ArmyType=last.get("ArmyType", 0),
                             BuffId=last.get("BuffId", 0), Name="", names=dict(last.get("names", {})),
                             descs=dict(last.get("descs", {})), summary=""))
            draw()
            box.update()

        def remove(i):
            if len(rows) <= 1:
                ctx.toast("A skill needs at least one level", error=True)
                return
            rows.pop(i)
            draw()
            box.update()
        draw()
        return ft.Column([T.muted("Each level is one SkillSettings row. 'Applies to unit class' filters which units "
                                  "the skill's description and effects target (0 = any)."), box], spacing=10)

    # ------------------------------------------------------------------ texts
    def texts_tab():
        parts = [T.muted("Placeholders in descriptions: {1} is the buff Value, {2} the Range, {0} the chance (PR).")]
        for r in rows:
            parts.append(T.h2("Level %s%s" % (r["Level"], "" if r["Id"] is None else "  (id %d)" % r["Id"])))
            parts.append(W.texts_editor(ctx, r["names"], r["descs"]))
        return ft.Column(parts, spacing=12)

    # ------------------------------------------------------------------ generals
    def generals_tab():
        if is_new:
            return T.muted("Save the skill first, then give it to generals here.")
        ids = {r["Id"] for r in rows if r["Id"]}
        box = ft.Column(spacing=6)

        def draw():
            box.controls.clear()
            have = store.generals_with(ids)
            for g in have:
                box.controls.append(ft.Row([
                    T.txt("%s  (id %s)  — level rows %s" % (g["name"], g["id"], g["rows"]), 13, expand=True),
                    T.icon_button(ft.Icons.CLOSE, lambda e, g=g: (
                        [store.set_general_skill(g["id"], x, False) for x in g["rows"]], draw(), box.update()),
                        "Take away", T.DANGER)], spacing=10))
            if not have:
                box.controls.append(T.muted("No general has this skill."))

        def add(e):
            pool = [dict(id=g["id"], name=g["name"]) for g in store.general_list()]
            W.pick_dialog(ctx, "Give skill to a general", pool, lambda r: r["name"], lambda r, lv: (
                store.set_general_skill(r["id"], sorted(ids, key=lambda i: next(x["Level"] for x in rows if x["Id"] == i))
                                        [max(0, min(lv, len(ids)) - 1)], True,
                                        drop_group=ids), draw(), ctx.page.update()), with_level="Skill level")
        draw()
        return ft.Column([T.h2("Generals that have this skill"),
                          T.muted("A general holds one level of a skill (GeneralSettings.Skills lists row Ids)."), box,
                          ft.Row([T.button("Give to a general", add, ft.Icons.ADD)])], spacing=10)

    # ------------------------------------------------------------------ icons
    def icons_tab():
        parts = [T.muted("Icons are looked up by skill row Id (skill_<Id>.png). New icons go into their own atlas "
                         "image_custom, so the game's atlases stay untouched.")]
        for i, r in enumerate(rows):
            parts.append(T.txt("Level %s" % r["Level"] + ("" if r["Id"] else "  (new row; saved with the skill)"), 13))
            parts.append(_icon_row(ctx, "skill", r["Id"], lambda png, i=i: icons.__setitem__(i, png)))
        return ft.Column(parts, spacing=10)

    # ------------------------------------------------------------------ save / delete
    def save(e):
        spec = dict(type=t, rows=[dict(id=r["Id"], level=r["Level"], armytype=r["ArmyType"], buff=r["BuffId"],
                                       name=r.get("Name"), names=r["names"], descs=r["descs"]) for r in rows])
        for s in spec["rows"]:
            if not s["names"].get("en"):
                ctx.toast("Every level needs an English name", error=True)
                return
        ids = ctx.guard(lambda: store.save_skill(spec), "Skill saved")
        if ids is None:
            return
        for i, png in icons.items():
            ctx.guard(lambda i=i, png=png: store.set_icon("skill", ids[i], png))
        ctx.drop("g3:skills")
        refresh(t)

    def delete(e):
        def yes():
            if ctx.guard(lambda: store.delete_skill(t), "Skill deleted") is not None:
                refresh(None)
        ctx.confirm("Delete skill", "Delete skill Type %d with all its levels? Generals lose it." % t, "Delete", yes)

    actions = [T.primary("Save", save, ft.Icons.SAVE_OUTLINED)]
    if not is_new:
        actions.append(T.button("Delete", delete, ft.Icons.DELETE_OUTLINE, color=T.DANGER))
    chips = [T.chip("Type %d" % t, T.MUTED, mono=True), T.chip("%d level%s" % (len(rows), "" if len(rows) == 1 else "s"))]
    if is_new:
        chips.append(T.chip("not saved yet", T.ACCENT))
    first_id = rows[0]["Id"] if rows and rows[0]["Id"] else None
    tabs = [("Levels", levels_tab), ("Names & text", texts_tab), ("Generals", generals_tab), ("Icons", icons_tab)]
    return _wrap(_header(ctx, "skill", first_id, title(), chips, actions), tab_view(tabs))


# ====================================================================== perks
class PerkProvider(Provider):
    kind = "g3perk"
    new_label = "New perk"
    search_hint = "Search by name or Id"
    filters = [("all", "All"), ("used", "On units")]

    def items(self):
        out = []
        for p in self.ctx.be.store.perk_list():
            out.append(Item(p["id"], p["name"], "Id %d · %d buff%s" % (p["id"], len(p["buffs"]),
                                                                       "" if len(p["buffs"]) == 1 else "s"),
                            icon=self.ctx.icon("perk", p["id"], size=34), side="%d units" % p["units"] if p["units"] else "",
                            search="%s %s" % (p["name"], p["id"]), tags=["used"] if p["units"] else []))
        return out

    def detail(self, key, refresh):
        return perk_editor(self.ctx, self.ctx.be.store.perk_detail(key), refresh, is_new=False)

    def new(self, refresh):
        d = dict(id=None, buffs=[], pic=None, names={"en": "New perk"}, descs={"en": "Describe the perk."}, units=[],
                 summaries=[])
        return -1, perk_editor(self.ctx, d, refresh, is_new=True)

    def placeholder(self):
        return "Select a perk, or create a new one. A perk is a list of buffs given to units."


def perk_editor(ctx, d, refresh, is_new):
    store = ctx.be.store
    pid = d["id"]
    buffs = list(d["buffs"])
    names, descs = dict(d["names"]), dict(d["descs"])
    icon = {}

    def buffs_tab():
        box = ft.Column(spacing=6)

        def draw():
            box.controls.clear()
            for b in buffs:
                box.controls.append(ft.Row([
                    T.txt(C.buff_label(ctx, b), 12.5, mono=True, expand=True),
                    T.icon_button(ft.Icons.CLOSE, lambda e, b=b: (buffs.remove(b), draw(), box.update()), "Remove",
                                  T.DANGER)], spacing=10))
            if not buffs:
                box.controls.append(T.muted("No buffs: the perk does nothing."))
        draw()

        def add(e):
            P.pick_buff(ctx, "Add buff", lambda b: (buffs.append(b), draw(), ctx.page.update()))
        return ft.Column([T.muted("The perk applies every listed buff to a unit that has it."), box,
                          ft.Row([T.button("Add buff", add, ft.Icons.ADD)])], spacing=10)

    def texts_tab():
        return ft.Column([T.muted("Placeholders: {1} buff value, {2} range, {0} chance."), W.texts_editor(ctx, names, descs)],
                         spacing=10)

    def units_tab():
        if is_new:
            return T.muted("Save the perk first, then add it to units here.")
        box = ft.Column(spacing=6)

        def draw():
            box.controls.clear()
            for u in store.perk_detail(pid)["units"]:
                box.controls.append(ft.Row([
                    T.txt("%s  (id %d)" % (u["name"], u["id"]), 13, expand=True),
                    T.icon_button(ft.Icons.CLOSE, lambda e, u=u: (store.set_unit_perk(u["id"], pid, False), draw(),
                                                                  box.update()), "Remove", T.DANGER)], spacing=10))

        def add(e):
            W.pick_dialog(ctx, "Give perk to a unit", store.unit_list(), lambda r: r["name"], lambda r, lv: (
                store.set_unit_perk(r["id"], pid, True), draw(), ctx.page.update()))
        draw()
        return ft.Column([T.h2("Units with this perk"), box, ft.Row([T.button("Add to a unit", add, ft.Icons.ADD)])],
                         spacing=10)

    def icon_tab():
        return ft.Column([T.muted("Perk icons are looked up as army_feature<Id>.png (60x60)."),
                          _icon_row(ctx, "perk", pid, lambda png: icon.__setitem__("png", png))], spacing=10)

    def save(e):
        if not names.get("en"):
            ctx.toast("Give the perk an English name", error=True)
            return
        new_id = ctx.guard(lambda: store.save_perk(dict(id=pid, buffs=buffs, names=names, descs=descs)), "Perk saved")
        if new_id is None:
            return
        if icon.get("png"):
            ctx.guard(lambda: store.set_icon("perk", new_id, icon["png"]))
        refresh(new_id)

    def delete(e):
        def yes():
            if ctx.guard(lambda: store.delete_perk(pid), "Perk deleted") is not None:
                refresh(None)
        ctx.confirm("Delete perk", "Delete perk %d? Units lose it." % pid, "Delete", yes)

    actions = [T.primary("Save", save, ft.Icons.SAVE_OUTLINED)]
    if not is_new:
        actions.append(T.button("Delete", delete, ft.Icons.DELETE_OUTLINE, color=T.DANGER))
    chips = [T.chip("Id %s" % (pid if pid else "new"), T.MUTED, mono=True)]
    tabs = [("Buffs", buffs_tab), ("Names & text", texts_tab), ("Units", units_tab), ("Icon", icon_tab)]
    return _wrap(_header(ctx, "perk", pid, names.get("en") or "Perk", chips, actions), tab_view(tabs))
