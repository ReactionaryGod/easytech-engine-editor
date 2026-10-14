"""Code browser: function and string search, disassembly listing, cross references, assemble-and-patch."""
import flet as ft

from .. import server
from . import theme as T


class CodePage:
    def __init__(self, ctx, addr):
        self.ctx = ctx
        self.view_kind = ctx.cache.get("code:view", "base")
        self.addr = addr if addr is not None else ctx.cache.get("code:addr", 0x30a7b0 if ctx.game == "gog3" else 0x39f370)
        self.selected = None
        self.listing = ft.ListView(expand=True, spacing=0, padding=ft.Padding.only(top=4, bottom=30))
        self.side = ft.ListView(expand=True, spacing=0, padding=4)
        self.inspector = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
        self.addr_field = T.field(None, T.hexa(self.addr), width=160, mono=True)
        self.addr_field.on_submit = lambda e: self.goto_text(e.control.value)
        self.func_label = T.txt("", 12, T.MUTED, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS)
        self.query = T.field(None, "", hint="Search functions or strings")
        self.query.on_submit = lambda e: self.search(e.control.value)

    def api(self, fn, body=None, **q):
        return self.ctx.be.call(fn, body, view=self.view_kind, **q)

    # ------------------------------------------------------------------ navigation
    def goto_text(self, text):
        try:
            self.goto(int(text.strip(), 16))
        except ValueError:
            self.ctx.toast("Not a hex address: %s" % text, error=True)

    def goto(self, addr):
        self.addr = addr & ~3
        self.ctx.cache["code:addr"] = self.addr
        self.addr_field.value = T.hexa(self.addr)
        self.draw_listing()
        self.ctx.page.update()
        self.ctx.page.run_task(self.scroll_to_target)

    def set_view(self, kind):
        self.view_kind = kind
        self.ctx.cache["code:view"] = kind
        self.ctx.show("code", self.addr)

    # ------------------------------------------------------------------ listing
    def draw_listing(self):
        try:
            d = self.api(server.api_disasm, addr="%x" % self.addr, before=30, after=170)
        except Exception as e:
            self.listing.controls = [ft.Container(T.note(str(e), T.DANGER), padding=14)]
            return
        self.func_label.value = "%s–%s  %s" % (T.hexa(d["func"][0]), T.hexa(d["func"][1]), d["func_name"])
        patched = {int(p["addr"], 16) for p in self.ctx.state["project"]["asm_patches"] if p.get("enabled", True)}
        rows = []
        offset = 0
        target_offset = 0
        for ins in d["ins"]:
            a = ins["a"]
            mn_color = T.INFO if ins["m"] in ("b", "bl", "br", "blr") or ins["m"].startswith("b.") else \
                T.DANGER if ins["m"] == "ret" else "#e9c27e"
            ops = T.txt(ins["o"], 12.5, "#c9d2de", mono=True, no_wrap=True)
            if ins["t"] is not None:
                ops = ft.TextButton(content=T.txt(ins["o"], 12.5, T.INFO, mono=True),
                                    on_click=lambda e, t=ins["t"]: self.goto(t), style=ft.ButtonStyle(
                                        padding=ft.Padding.all(0)))
            cells = [T.txt("%x" % a, 12.5, T.ACCENT if a == self.addr else "#6d7b90", mono=True, width=68),
                     T.txt(ins["b"], 12, T.CUSTOM if a in patched else "#4b5768", mono=True, width=76),
                     T.txt(ins["m"], 12.5, mn_color, mono=True, width=56), ops]
            if ins["n"]:
                cells.append(T.txt("; " + ins["n"], 12, "#6a8a6a", mono=True))
            row = ft.Container(
                content=ft.Row(cells, spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding.symmetric(horizontal=14), height=22,
                bgcolor=T.soft(T.ACCENT, 0.16) if a == self.addr else None,
                on_click=lambda e, a=a: self.select(a))
            if ins["f"]:
                label = "function %x" % a + ("  " + d["func_name"] if a == d["func"][0] and d["func_name"] else "")
                rows.append(ft.Container(T.txt(label, 12, T.ACCENT, ft.FontWeight.W_600, mono=True),
                                         padding=ft.Padding.only(left=14, top=8)))
                offset += 30
            if a == self.addr:
                target_offset = offset
            offset += 22
            rows.append(row)
        self.listing.controls = rows
        self.target_offset = max(0, target_offset - 110)
        self.select(self.addr, redraw=False)

    def select(self, addr, redraw=True):
        self.addr = addr
        self.ctx.cache["code:addr"] = addr
        self.addr_field.value = T.hexa(addr)
        self.draw_inspector(addr)
        if redraw:
            self.draw_listing_marks()
            self.ctx.page.update()

    async def scroll_to_target(self):
        try:
            await self.listing.scroll_to(offset=self.target_offset, duration=0)
        except Exception:
            pass

    def draw_listing_marks(self):
        for c in self.listing.controls:
            if isinstance(c.content, ft.Row):
                first = c.content.controls[0]
                is_sel = first.value == "%x" % self.addr
                c.bgcolor = T.soft(T.ACCENT, 0.16) if is_sel else None
                first.color = T.ACCENT if is_sel else "#6d7b90"

    # ------------------------------------------------------------------ inspector
    def draw_inspector(self, addr):
        c = self.inspector.controls
        c.clear()
        c.append(T.h2("Instruction at %s" % T.hexa(addr)))
        try:
            h = self.api(server.api_hex, addr="%x" % addr, len=4)
            c.append(T.txt(h["hex"], 12.5, T.MUTED, mono=True))
        except Exception:
            pass
        asm = T.field("Replacement assembly (use ; for several instructions)", "", mono=True, multiline=True)
        note = T.field("Note", "")
        result = ft.Column(spacing=6)

        def preview(e=None):
            result.controls.clear()
            if not asm.value.strip():
                return None
            try:
                r = self.ctx.be.call(server.api_assemble, dict(addr="%x" % addr, asm=asm.value))
            except Exception as ex:
                result.controls.append(T.txt(str(ex), 12, T.DANGER))
                result.update()
                return None
            lines = [T.txt("%x  %s %s" % (o["a"], o["m"], o["o"]), 12, T.DANGER, mono=True) for o in r["old"]]
            lines += [T.txt("%x  %s %s" % (n["a"], n["m"], n["o"]), 12, T.OK, mono=True) for n in r["new"]]
            result.controls.extend(lines)
            result.update()
            return r

        def add(e):
            if preview() is None:
                return
            if self.ctx.guard(lambda: self.ctx.be.call(server.api_patch_add, dict(
                    addr="%x" % addr, asm=asm.value, note=note.value)), "Patch added to the project") is not None:
                self.ctx.refresh_state()
                self.ctx.mark_unbuilt()
                self.draw_listing()
                self.ctx.page.update()

        c.append(asm)
        c.append(note)
        c.append(ft.Row([T.button("Preview", preview), T.primary("Add to project", add)], spacing=8))
        c.append(result)
        c.append(T.section("Cross references"))
        try:
            x = self.api(server.api_xrefs, addr="%x" % addr)
            f0 = None
            try:
                f0 = self.api(server.api_disasm, addr="%x" % addr, before=0, after=1)["func"][0]
            except Exception:
                pass
            target = f0 if f0 == addr else addr
            if target != addr:
                x = self.api(server.api_xrefs, addr="%x" % target)
            lst = [("call", r["a"], r["f"]) for r in x["callers"]] + [("data", r["a"], r["f"]) for r in x["data"]]
            if not lst:
                c.append(T.muted("None found."))
            for kind, a, f in lst[:80]:
                c.append(ft.TextButton(
                    content=ft.Row([T.chip(kind, T.INFO if kind == "call" else T.CUSTOM),
                                    T.txt("%x" % a, 12, T.TEXT, mono=True),
                                    T.txt("in %x" % f, 11.5, T.FAINT, mono=True)], spacing=8),
                    on_click=lambda e, a=a: self.goto(a)))
        except Exception as e:
            c.append(T.muted(str(e)))

    # ------------------------------------------------------------------ search / side list
    def search(self, text):
        self.side.controls.clear()
        text = text.strip()
        if text:
            fs = self.api(server.api_funcs, q=text)["funcs"]
            ss = self.api(server.api_strings, q=text)["strings"]
            for f in fs[:200]:
                self.side.controls.append(self.sym(f["a"], f["n"]))
            for s in ss[:200]:
                self.side.controls.append(self.sym(s["a"], '"%s" (%d refs)' % (s["s"], s["refs"]), data=True))
        else:
            for f in self.api(server.api_funcs, q="")["funcs"]:
                self.side.controls.append(self.sym(f["a"], f["n"]))
        self.ctx.page.update()

    def sym(self, addr, label, data=False):
        def click(e):
            if data:
                refs = self.api(server.api_xrefs, addr="%x" % addr)["data"]
                if refs:
                    self.goto(refs[0]["a"])
                else:
                    self.ctx.toast("No code references this string")
            else:
                self.goto(addr)
        return ft.Container(ft.Row([T.txt("%x" % addr, 11.5, T.ACCENT, mono=True),
                                    T.txt(label, 12.5, T.MUTED, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS,
                                          expand=True)], spacing=8),
                            padding=ft.Padding.symmetric(horizontal=8, vertical=5), border_radius=5, ink=True,
                            on_click=click)

    # ------------------------------------------------------------------ layout
    def build(self):
        seg = ft.SegmentedButton(
            segments=[ft.Segment(value="base", label="Original"), ft.Segment(value="built", label="Built")],
            selected=[self.view_kind], allow_empty_selection=False,
            on_change=lambda e: self.set_view(list(e.control.selected)[0]))
        self.search("")
        self.draw_listing()
        left = ft.Container(ft.Column([ft.Container(seg, padding=12), ft.Container(self.query, padding=ft.Padding.symmetric(horizontal=12)),
                                       self.side], expand=True, spacing=8),
                            width=260, bgcolor=T.SURFACE, border=ft.Border.only(right=ft.BorderSide(1, T.BORDER)))
        bar = ft.Container(ft.Row([self.addr_field, T.button("Go", lambda e: self.goto_text(self.addr_field.value)),
                                   ft.Container(self.func_label, expand=True)], spacing=8),
                           padding=ft.Padding.symmetric(horizontal=14, vertical=10), bgcolor=T.SURFACE,
                           border=ft.Border.only(bottom=ft.BorderSide(1, T.BORDER)))
        center = ft.Column([bar, ft.Container(self.listing, expand=True, bgcolor="#0b0e12")], expand=True, spacing=0)
        right = ft.Container(self.inspector, width=340, bgcolor=T.SURFACE, padding=14,
                             border=ft.Border.only(left=ft.BorderSide(1, T.BORDER)))
        self.ctx.page.run_task(self._later_scroll)
        return ft.Row([left, center, right], expand=True, spacing=0,
                      vertical_alignment=ft.CrossAxisAlignment.STRETCH)

    async def _later_scroll(self):
        import asyncio
        await asyncio.sleep(0.5)
        await self.scroll_to_target()


def view(ctx, arg):
    return CodePage(ctx, arg if isinstance(arg, int) else None).build()
