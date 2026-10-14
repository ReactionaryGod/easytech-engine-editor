"""Build screen: preview the layout, then build the package."""
import flet as ft

from .. import server
from . import theme as T


def _log_box(lines):
    controls = []
    for ln in lines:
        color = T.DANGER if ln.startswith("ERROR") else T.OK if ln.startswith("wrote") else T.TEXT
        controls.append(T.txt(ln, 12, color, mono=True, selectable=True))
    return ft.Container(ft.Column(controls, spacing=2, scroll=ft.ScrollMode.AUTO, height=360, expand=True),
                        bgcolor="#0b0e12", border=ft.Border.all(1, T.BORDER), border_radius=8, padding=14)


def view(ctx, arg):
    st = ctx.refresh_state()
    pr = st["project"]
    out = ft.Column(spacing=12)
    write_data = {"v": True}

    patches_on = len([p for p in pr["asm_patches"] if p.get("enabled", True)])
    if ctx.game == "gog3":
        summary = [("Assembly patches", patches_on)]
        opts_line = ("Skills, perks, buffs and conditions are already written into the package. "
                     "A build only re-applies the assembly patches to libiron.so.")
    else:
        summary = [
            ("Custom skills", len(pr["custom_skills"])), ("Custom perks", len(pr["custom_perks"])),
            ("Extended skill types", len(pr["skill_extras"])), ("Extended perk types", len(pr["perk_extras"])),
            ("Assembly patches", patches_on),
        ]
        opts = pr["options"]
        opts_line = "Challenge caps: %s · Mysterious Forces picker: %s · Engine extension: %s" % (
            opts["challenge"], "on" if opts["mf_picker"] else "off", "on" if opts["engine_ext"] else "off")

    def finish(res):
        ok, lines = res["ok"], res["log"]
        out.controls.clear()
        out.controls.append(T.note("Build finished." if ok else "Build failed; nothing was left half written for "
                                   "the library.", T.OK if ok else T.DANGER))
        out.controls.append(_log_box(lines))
        if ok:
            ctx.mark_unbuilt(False)
            ctx.cache.clear()
            ctx.refresh_state()

    def run_build(e=None):
        ctx.background(lambda: ctx.be.build(write_data["v"]), finish,
                       "Building the package…")

    def preview(res):
        out.controls.clear()
        ext = res.get("ext")
        lines = ["library size: %d bytes" % res["size"]]
        d = res["detect"]
        if ctx.game == "wc4":
            lines += ["challenge caps: %s" % d["challenge"], "MF picker: %s" % d["mf_picker"],
                      "General Bank: %s" % d["general_bank"], "extension: %s" % d["engine_ext"]]
        else:
            lines += ["enabled assembly patches: %s" % res.get("patches")]
        if ext:
            lines.append("extension code: %d bytes at 0xa15000" % ext["code_size"])
            lines.append("hook sites: %d" % len(ext["sites"]))
            lines += ["  %-14s %s" % (g, T.hexa(a)) for a, g in [(s["a"], s["g"]) for s in ext["sites"]]]
        out.controls.append(_log_box(lines))

    def run_preview(e):
        ctx.background(lambda: ctx.be.preview(), preview, "Assembling in memory…")

    if arg == "run":
        ctx.page.run_thread(run_build)

    return T.scroll_page(
        T.page_header("Build", "Builds the library from the APK original and writes it, with the json rows, "
                      "stringtable entries and icons, into the mod package."),
        ft.Row([T.card(T.txt(v, 24, weight=ft.FontWeight.W_600), T.muted(l), expand=True) for l, v in summary],
               spacing=14),
        T.card(T.h2("Options in effect"),
               T.txt(opts_line, 12.5),
               ft.Row([T.toggle(True, lambda v: write_data.update(v=v)),
                       T.txt("Also write json rows, stringtables and icons", 12.5)])),
        ft.Row([T.button("Preview (no files written)", run_preview, ft.Icons.VISIBILITY_OUTLINED),
                T.primary("Build package", run_build, ft.Icons.PLAY_ARROW)], spacing=10),
        out)
