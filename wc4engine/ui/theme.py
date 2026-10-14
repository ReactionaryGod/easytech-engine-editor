"""Colours, text styles and small reusable building blocks for the Flet UI."""
import flet as ft

BG = "#0d1015"
SURFACE = "#141920"
SURFACE2 = "#1a2029"
SURFACE3 = "#212935"
BORDER = "#283241"
TEXT = "#dbe2ec"
MUTED = "#8c99ad"
FAINT = "#5f6b7e"
ACCENT = "#e3ab4f"
ACCENT_INK = "#1b1306"
CUSTOM = "#52c1b4"
DANGER = "#ec6f62"
OK = "#74c98f"
INFO = "#7aa7f0"
MONO = "Cascadia Mono, Consolas"


def soft(color, alpha=0.15):
    return ft.Colors.with_opacity(alpha, color)


def apply(page):
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG
    page.padding = 0
    page.theme = ft.Theme(color_scheme_seed=ACCENT, font_family="Segoe UI")
    page.dark_theme = ft.Theme(color_scheme_seed=ACCENT, font_family="Segoe UI")


def txt(value, size=13, color=TEXT, weight=None, mono=False, selectable=False, **kw):
    return ft.Text(str(value), size=size, color=color, weight=weight,
                   font_family=MONO if mono else None, selectable=selectable, **kw)


def h1(value):
    return txt(value, 21, weight=ft.FontWeight.W_600)


def h2(value):
    return txt(value, 15, weight=ft.FontWeight.W_600)


def muted(value, size=12.5, **kw):
    return txt(value, size, MUTED, **kw)


def card(*controls, padding=16, expand=None, spacing=8):
    return ft.Container(
        content=ft.Column([c for c in controls if c is not None], spacing=spacing, tight=True),
        bgcolor=SURFACE, border=ft.Border.all(1, BORDER), border_radius=8, padding=padding, expand=expand)


def chip(label, color=MUTED, filled=True, mono=False):
    return ft.Container(
        content=txt(label, 11.5, color, ft.FontWeight.W_500, mono=mono),
        bgcolor=soft(color, 0.14) if filled else None,
        border=None if filled else ft.Border.all(1, BORDER),
        border_radius=11, padding=ft.Padding.symmetric(horizontal=8, vertical=2))


def note(text, color=INFO):
    return ft.Container(
        content=txt(text, 12.5, TEXT), bgcolor=soft(color, 0.12),
        border=ft.Border.only(left=ft.BorderSide(3, color)),
        border_radius=ft.BorderRadius.only(top_right=6, bottom_right=6),
        padding=ft.Padding.symmetric(horizontal=12, vertical=9))


def section(title, *right):
    return ft.Row([h2(title), ft.Container(height=1, bgcolor=BORDER, expand=True), *right],
                  vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=10)


def page_header(title, subtitle=None, actions=None):
    left = [h1(title)]
    if subtitle:
        left.append(muted(subtitle, 13))
    return ft.Row([ft.Column(left, spacing=4, expand=True), *(actions or [])],
                  vertical_alignment=ft.CrossAxisAlignment.END)


def primary(label, on_click, icon=None, disabled=False):
    return ft.Button(content=label, icon=icon, on_click=on_click, disabled=disabled, bgcolor=ACCENT, color=ACCENT_INK)


def button(label, on_click, icon=None, disabled=False, color=None):
    return ft.OutlinedButton(content=label, icon=icon, on_click=on_click, disabled=disabled,
                             style=ft.ButtonStyle(color=color or TEXT,
                                                  side=ft.BorderSide(1, color or "#354255")))


def icon_button(icon, on_click, tooltip=None, color=MUTED):
    return ft.IconButton(icon=icon, on_click=on_click, tooltip=tooltip, icon_color=color, icon_size=18)


def field(label, value="", on_change=None, width=None, mono=False, multiline=False, hint=None, expand=None,
          number=False):
    return ft.TextField(
        label=label, value="" if value is None else str(value), on_change=on_change, width=width, expand=expand,
        multiline=multiline, min_lines=2 if multiline else None, max_lines=4 if multiline else 1, hint_text=hint,
        text_size=13, dense=True, border_color="#354255", focused_border_color=ACCENT,
        keyboard_type=ft.KeyboardType.NUMBER if number else None,
        text_style=ft.TextStyle(font_family=MONO) if mono else None)


def num_cell(value, on_change, width=78):
    """Compact numeric input for tables; on_change receives an int."""
    def changed(e):
        try:
            on_change(int(e.control.value or 0))
            e.control.border_color = "#2c3747"
        except ValueError:
            e.control.border_color = DANGER
        e.control.update()
    return ft.TextField(value=str(value), width=width, dense=True, text_size=12.5, on_change=changed,
                        content_padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                        border_color="#2c3747", focused_border_color=ACCENT,
                        text_style=ft.TextStyle(font_family=MONO))


def dropdown(options, value, on_change, width=None, label=None):
    """options: [(key, text)]"""
    return ft.Dropdown(options=[ft.DropdownOption(key=str(k), text=t) for k, t in options], value=str(value),
                       on_select=lambda e: on_change(e.control.value), width=width, label=label, dense=True,
                       text_size=13, border_color="#354255")


def toggle(value, on_change, label=None):
    return ft.Switch(value=bool(value), label=label, active_color=ACCENT,
                     on_change=lambda e: on_change(e.control.value))


def scroll_page(*controls):
    return ft.Container(
        content=ft.Column([c for c in controls if c is not None], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True),
        padding=ft.Padding.only(left=26, right=26, top=22, bottom=30), expand=True)


def hexa(n):
    return "0x%x" % n
