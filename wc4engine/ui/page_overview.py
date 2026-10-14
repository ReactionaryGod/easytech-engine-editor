"""Overview: library status, paths, counts, what a build does."""
import flet as ft

from . import theme as T


def _lib_rows(info):
    if not info:
        return [T.muted("No library in the package yet. Build to create one.")]
    if info.get("error"):
        return [T.note(info["error"], T.DANGER)]

    def state_chip(good, label, color=None):
        return T.chip(label, color or (T.OK if good else T.MUTED), filled=good or bool(color))
    ext = info["engine_ext"]
    rows = [
        ("SHA-1", T.txt(info["sha1"][:20] + "…", 12, mono=True)),
        ("Size", T.txt("%.2f MiB%s" % (info["size"] / 1048576, " · code area grown" if info["grown"] else ""), 12.5)),
        ("Challenge caps", state_chip(info["challenge"] != "vanilla", info["challenge"])),
        ("MF picker", state_chip(info["mf_picker"] == "unlocked", info["mf_picker"])),
        ("General Bank", state_chip(info["general_bank"] == "patched", info["general_bank"])),
        ("Extension", state_chip(ext != "none", ext, T.CUSTOM if "this editor" in ext else None)),
    ]
    return [ft.Row([ft.Container(T.muted(k), width=130), v]) for k, v in rows]


def _lib_card(ctx, title, info, path, key=None):
    head = ft.Row([ft.Icon(ft.Icons.MEMORY, color=T.MUTED, size=18), T.h2(title), ft.Container(expand=True)]
                  + ([T.chip("APK original", T.OK)] if info and info.get("is_base") else []))
    if key:
        path_ctl = T.field("Path", path, mono=True, expand=True)
        path_ctl.on_blur = lambda e: _save_path(ctx, key, e.control.value)
        path_ctl.on_submit = lambda e: _save_path(ctx, key, e.control.value)
    else:
        path_ctl = T.txt(path, 12, T.MUTED, mono=True, selectable=True)
    return T.card(head, path_ctl, *_lib_rows(info), expand=True)


def _save_path(ctx, key, value):
    if value == ctx.state["project"]["paths"].get(key):
        return
    if ctx.guard(lambda: ctx.be.save_project(paths={key: value}), "Path saved") is not None:
        ctx.cache.clear()
        ctx.refresh_state()
        ctx.show("overview")


def _view_gog3(ctx):
    st = ctx.refresh_state()
    pr = st["project"]
    store = ctx.be.store
    groups = len(store.skill_groups())
    conds = [c for c in store.conditions() if c["custom"]]
    counts = [(groups, "skills"), (len(store.rows("ArmyFeatureSettings")), "perks"),
              (len(store.rows("BuffSettings")), "buffs"), (len(conds), "custom conditions"),
              (len([p for p in pr["asm_patches"] if p.get("enabled", True)]), "assembly patches")]
    stats = ft.Row([T.card(T.txt(v, 26, weight=ft.FontWeight.W_600), T.muted(l), expand=True) for v, l in counts],
                   spacing=14)

    def lib_card(title, info, path, key=None):
        head = ft.Row([ft.Icon(ft.Icons.MEMORY, color=T.MUTED, size=18), T.h2(title)])
        if key:
            ctl = T.field("Path", path, mono=True, expand=True)
            ctl.on_blur = lambda e: _save_path(ctx, key, e.control.value)
            ctl.on_submit = lambda e: _save_path(ctx, key, e.control.value)
        else:
            ctl = T.txt(path, 12, T.MUTED, mono=True, selectable=True)
        if info:
            rows = [ft.Row([ft.Container(T.muted("SHA-1"), width=110), T.txt(info["sha1"][:20] + "...", 12, mono=True)]),
                    ft.Row([ft.Container(T.muted("Size"), width=110), T.txt("%.2f MiB" % (info["size"] / 1048576), 12.5)])]
            if info.get("note"):
                rows.append(T.muted(info["note"]))
        else:
            rows = [T.muted("Not built yet: the library is only written when you add assembly patches.")]
        return T.card(head, ctl, *rows, expand=True)

    def path_card(title, text, key):
        f = T.field("Folder", pr["paths"].get(key, ""), mono=True)
        f.on_blur = lambda e: _save_path(ctx, key, e.control.value)
        f.on_submit = lambda e: _save_path(ctx, key, e.control.value)
        return T.card(T.h2(title), T.muted(text), f, expand=True)

    out_lib = st["package"] + "\\lib\\arm64-v8a\\libiron.so"
    return T.scroll_page(
        T.page_header("Glory of Generals 3", "Skills and perks are lists of buffs (condition, chance, effect Type, "
                      "value). Conditions live in config/def_buff.xml; only each effect Type is hard-coded in "
                      "libiron.so. Edits to skills, perks, buffs and conditions are written straight into the package."),
        stats,
        ft.Row([lib_card("libiron.so (input)", st.get("base"), pr["paths"]["base_so"], "base_so"),
                lib_card("libiron.so (package output)", st.get("package_lib"), out_lib)],
               spacing=14, vertical_alignment=ft.CrossAxisAlignment.START),
        T.section("Game data"),
        ft.Row([path_card("Extracted game assets", "Original json, stringtables, config and images. Files in the "
                          "package take priority.", "assets"),
                path_card("Backups folder", "Files replaced by the editor are copied to a dated folder once.",
                          "backups")], spacing=14),
        T.section("How GoG3 buffs work"),
        T.card(T.txt("Skill row  ->  Buff  (Condition, PR, Type, Value, Range, chained BuffId)  ->  engine case for that Type",
                     13),
               T.muted("Most new skills and perks need no code: combine existing Types, add conditions with AND / OR / "
                       "NOT, chain buffs through the aura Types (98/99). The Buff types screen lists every Type the "
                       "engine implements, including some no game data uses yet. A brand-new Type needs an assembly "
                       "patch.")))


def view(ctx, arg):
    if ctx.game == "gog3":
        return _view_gog3(ctx)
    st = ctx.refresh_state()
    pr = st["project"]
    counts = [(len(pr["custom_skills"]), "custom skills"), (len(pr["custom_perks"]), "custom perks"),
              (len(pr["skill_extras"]) + len(pr["perk_extras"]), "types with added behaviour"),
              (len(pr["asm_patches"]), "assembly patches")]
    stats = ft.Row([T.card(T.txt(v, 26, weight=ft.FontWeight.W_600), T.muted(l), expand=True) for v, l in counts],
                   spacing=14)

    def path_card(title, text, key):
        f = T.field("Folder", pr["paths"].get(key, ""), mono=True)
        f.on_blur = lambda e: _save_path(ctx, key, e.control.value)
        f.on_submit = lambda e: _save_path(ctx, key, e.control.value)
        return T.card(T.h2(title), T.muted(text), f, expand=True)

    steps = ["APK libworld-conqueror-4.so", "simple patches", "engine extension (+64 KiB code, new .bss tables)",
             "your asm patches", "package lib/arm64-v8a + json rows, stringtables, icons"]
    pipe = []
    for i, s in enumerate(steps):
        if i:
            pipe.append(T.txt("→", 14, T.FAINT))
        pipe.append(ft.Container(T.txt(s, 12.5), bgcolor=T.SURFACE2, border=ft.Border.all(1, T.BORDER),
                                 border_radius=6, padding=ft.Padding.symmetric(horizontal=10, vertical=6)))
    return T.scroll_page(
        T.page_header("Overview", "Edit the hard-coded engine of World Conqueror 4 without hex editing: toggle known "
                      "patches, add general skills and unit perks that the engine really runs, and patch any "
                      "instruction in the code browser."),
        None if st["project_exists"] else T.note(
            "New project. Paths were guessed from the folder layout; check them below. The project file is "
            "created on the first save or build.", T.ACCENT),
        stats,
        ft.Row([_lib_card(ctx, "Base library (input)", st.get("base") or (
                    {"error": st["base_error"]} if st.get("base_error") else None), pr["paths"]["base_so"], "base_so"),
                _lib_card(ctx, "Package library (output)", st.get("package_lib"),
                          st["package"] + "\\lib\\arm64-v8a\\libworld-conqueror-4.so")],
               spacing=14, vertical_alignment=ft.CrossAxisAlignment.START),
        T.section("Game data"),
        ft.Row([path_card("Extracted game assets", "Original json, stringtables and images. Files in the package "
                          "take priority.", "assets"),
                path_card("Backups folder", "Files replaced by the editor are copied to <backups>\\<date>_engine_editor "
                          "once.", "backups")], spacing=14),
        T.section("What a build does"),
        T.card(ft.Row(pipe, wrap=True, spacing=8, run_spacing=8),
               T.muted("Every patch site is compared with the expected original instruction before anything is "
                       "written, so a wrong base library is refused instead of producing a broken game.")))
