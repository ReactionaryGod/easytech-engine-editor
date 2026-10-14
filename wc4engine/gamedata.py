"""Game data I/O for the mod package: json tables, stringtables and icons, format-preserving.

Lookup order for every file: the mod package first, then the extracted game. Writes always go to the package.
- json tables: one record per line; the newline style (CRLF or LF) and BOM of the source file are kept.
- stringtables: `key=value`; each file keeps its own BOM and newline style. They live at the package root.
"""
import io
import json
import os
import re
import shutil

LANGS = ["en", "cn", "tw", "de", "es", "ja", "ko"]
LANG_NAMES = {"en": "English", "cn": "Chinese (simplified)", "tw": "Chinese (traditional)", "de": "German",
              "es": "Spanish", "ja": "Japanese", "ko": "Korean"}


class JsonTable:
    """A json array of records. Unchanged records are written back byte-for-byte (some tables contain blank
    lines or other irregular spacing); changed or new records are written compactly, one per line."""
    def __init__(self, raw):
        self.bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw[3:].decode("utf-8") if self.bom else raw.decode("utf-8")
        self.nl = "\r\n" if "\r\n" in text[:4096] else "\n"
        dec = json.JSONDecoder()
        pos = text.index("[") + 1
        self.rows, self._spans = [], []
        ws = re.compile(r"[\s,]*")
        while True:
            pos = ws.match(text, pos).end()
            if text[pos] == "]":
                break
            obj, end = dec.raw_decode(text, pos)
            self.rows.append(obj)
            self._spans.append((pos, end))
            pos = end
        self._text = text
        self._orig = [(id(r), json.dumps(r, sort_keys=True)) for r in self.rows]

    def dump(self):
        text, spans = self._text, self._spans
        orig_index = {oid: i for i, (oid, _) in enumerate(self._orig)}
        out = [text[:spans[0][0]] if spans else "[" + self.nl]
        prev = None
        for k, r in enumerate(self.rows):
            i = orig_index.get(id(r))
            if k:
                if i is not None and prev is not None and i == prev + 1:
                    out.append(text[spans[prev][1]:spans[i][0]])
                else:
                    out.append("," + self.nl)
            if i is not None and json.dumps(r, sort_keys=True) == self._orig[i][1]:
                out.append(text[spans[i][0]:spans[i][1]])
            else:
                out.append(json.dumps(r, ensure_ascii=False, separators=(",", ":")))
            prev = i
        out.append(text[spans[-1][1]:] if spans else self.nl + "]")
        data = "".join(out).encode("utf-8")
        return (b"\xef\xbb\xbf" + data) if self.bom else data


class StringTable:
    """Keeps every original line; set() replaces a key's value in place or appends."""
    def __init__(self, raw):
        self.bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw[3:].decode("utf-8") if self.bom else raw.decode("utf-8")
        self.nl = "\r\n" if "\r\n" in text[:8192] else "\n"
        self.lines = text.splitlines(keepends=True)
        self.index = {}
        for i, ln in enumerate(self.lines):
            if "=" in ln and not ln.startswith(";"):
                k = ln.split("=", 1)[0]
                self.index.setdefault(k, i)

    def get(self, key, default=None):
        i = self.index.get(key)
        if i is None:
            return default
        return self.lines[i].split("=", 1)[1].rstrip("\r\n")

    def set(self, key, value):
        value = value.replace("\r", "").replace("\n", "\\n")
        i = self.index.get(key)
        if i is not None:
            ln = self.lines[i]
            end = ln[len(ln.rstrip("\r\n")):] or self.nl
            self.lines[i] = "%s=%s%s" % (key, value, end)
        else:
            if self.lines and not self.lines[-1].endswith("\n"):
                self.lines[-1] += self.nl
            self.index[key] = len(self.lines)
            self.lines.append("%s=%s%s" % (key, value, self.nl))

    def delete(self, key):
        i = self.index.pop(key, None)
        if i is not None:
            self.lines[i] = ""

    def dump(self):
        data = "".join(self.lines).encode("utf-8")
        return (b"\xef\xbb\xbf" + data) if self.bom else data


class GameData:
    def __init__(self, assets_dir, package_dir, strings_in_assets=False, langs=None):
        self.assets = assets_dir
        self.package = package_dir
        self.strings_in_assets = strings_in_assets      # GoG3 keeps stringtables inside assets/
        self.langs = langs or LANGS
        self._tables = {}
        self._strings = {}
        self.dirty_tables = set()
        self.dirty_strings = set()

    # ------------------------------------------------------------------ paths
    def _pkg_asset(self, rel):
        return os.path.join(self.package, "assets", rel)

    def find_asset(self, rel):
        for p in (self._pkg_asset(rel), os.path.join(self.assets, rel)):
            if os.path.exists(p):
                return p
        return None

    def string_path(self, lang):
        name = "stringtable_%s.ini" % lang
        for p in (os.path.join(self.package, name), self._pkg_asset(name), os.path.join(self.assets, name)):
            if os.path.exists(p):
                return p
        return None

    def string_target(self, lang):
        """Where a changed stringtable is written: wherever the package already keeps it (root by default)."""
        name = "stringtable_%s.ini" % lang
        if self.strings_in_assets:
            return self._pkg_asset(name)
        if os.path.exists(self._pkg_asset(name)) and not os.path.exists(os.path.join(self.package, name)):
            return self._pkg_asset(name)
        return os.path.join(self.package, name)

    # ------------------------------------------------------------------ tables
    def table(self, name):
        if name not in self._tables:
            p = self.find_asset("json/%s.json" % name)
            if p is None:
                raise FileNotFoundError("json/%s.json not found" % name)
            with open(p, "rb") as f:
                self._tables[name] = JsonTable(f.read())
        return self._tables[name]

    def rows(self, name):
        return self.table(name).rows

    def mark(self, name):
        self.dirty_tables.add(name)

    # ------------------------------------------------------------------ strings
    def strings(self, lang):
        if lang not in self._strings:
            p = self.string_path(lang)
            if p is None:
                self._strings[lang] = StringTable(b"")
            else:
                with open(p, "rb") as f:
                    self._strings[lang] = StringTable(f.read())
        return self._strings[lang]

    def text(self, key, lang="en", default=""):
        return self.strings(lang).get(key, default)

    def set_text(self, lang, key, value):
        st = self.strings(lang)
        if st.get(key) != value:
            st.set(key, value)
            self.dirty_strings.add(lang)

    def delete_text(self, lang, key):
        st = self.strings(lang)
        if st.get(key) is not None:
            st.delete(key)
            self.dirty_strings.add(lang)

    # ------------------------------------------------------------------ save
    def pending(self):
        out = ["assets/json/%s.json" % n for n in sorted(self.dirty_tables)]
        out += [os.path.relpath(self.string_target(l), self.package) for l in sorted(self.dirty_strings)]
        return out

    def save(self, backup_dir=None, log=print):
        written = []
        for name in sorted(self.dirty_tables):
            dst = self._pkg_asset("json/%s.json" % name)
            data = self._tables[name].dump()
            if _same(dst, data) or (not os.path.exists(dst) and self._same_as_source(name, data)):
                continue
            _backup(dst, self.package, backup_dir)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(data)
            written.append(dst)
        for lang in sorted(self.dirty_strings):
            dst = self.string_target(lang)
            data = self._strings[lang].dump()
            if _same(dst, data):
                continue
            _backup(dst, self.package, backup_dir)
            with open(dst, "wb") as f:
                f.write(data)
            written.append(dst)
        for p in written:
            log("wrote %s" % os.path.relpath(p, self.package))
        self.dirty_tables.clear()
        self.dirty_strings.clear()
        return written

    def _same_as_source(self, name, data):
        p = os.path.join(self.assets, "json", "%s.json" % name)
        return _same(p, data)

    def reload(self):
        self._tables.clear()
        self._strings.clear()
        self.dirty_tables.clear()
        self.dirty_strings.clear()


def _same(path, data):
    try:
        with open(path, "rb") as f:
            return f.read() == data
    except OSError:
        return False


def _backup(dst, package, backup_dir):
    """Copy a package file into backup_dir once (keeps the first, pre-editor version)."""
    if not backup_dir or not os.path.exists(dst):
        return
    rel = os.path.relpath(dst, package)
    b = os.path.join(backup_dir, rel)
    if not os.path.exists(b):
        os.makedirs(os.path.dirname(b), exist_ok=True)
        shutil.copy2(dst, b)


# ---------------------------------------------------------------------- icons
def _pil():
    from PIL import Image
    return Image


def skill_icon_png(gd, type_):
    p = gd.find_asset("image/general_skill/general_skill_%d.webp" % type_) or \
        gd.find_asset("image/general_skill/general_skill_%d.png" % type_)
    if not p:
        return None
    Image = _pil()
    im = Image.open(p).convert("RGBA")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def write_skill_icon(gd, type_, src_png=None, from_type=None, backup_dir=None):
    Image = _pil()
    if src_png:
        im = Image.open(io.BytesIO(src_png) if isinstance(src_png, bytes) else src_png).convert("RGBA")
    else:
        p = gd.find_asset("image/general_skill/general_skill_%d.webp" % from_type)
        if not p:
            raise FileNotFoundError("no icon for skill type %s" % from_type)
        im = Image.open(p).convert("RGBA")
    ref = gd.find_asset("image/general_skill/general_skill_100.webp")
    if ref:
        size = Image.open(ref).size
        if im.size != size:
            im = im.resize(size, Image.LANCZOS)
    dst = gd._pkg_asset("image/general_skill/general_skill_%d.webp" % type_)
    _backup(dst, gd.package, backup_dir)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    im.save(dst, "WEBP", lossless=True)
    return dst


class FeatAtlas:
    """image/image_feats_hd.{xml,webp}: frames named feat_<Type>_<Level>.png."""
    XML = "image/image_feats_hd.xml"

    def __init__(self, gd):
        self.gd = gd
        p = gd.find_asset(self.XML)
        with open(p, "rb") as f:
            self.xml_raw = f.read()
        text = self.xml_raw.decode("utf-8")
        self.nl = "\r\n" if "\r\n" in text else "\n"
        self.texture = re.search(r'<Texture name="([^"]+)"', text).group(1)
        self.frames = {}
        for m in re.finditer(r'<Image name="([^"]+)" x="(\d+)" y="(\d+)" w="(\d+)" h="(\d+)" refx="(-?\d+)" '
                             r'refy="(-?\d+)" />', text):
            self.frames[m.group(1)] = tuple(int(m.group(i)) for i in range(2, 8))
        self.text = text
        self._img = None

    def image(self):
        if self._img is None:
            Image = _pil()
            stem = os.path.splitext(self.texture)[0]
            p = self.gd.find_asset("image/%s.webp" % stem) or self.gd.find_asset("image/%s" % self.texture)
            self._img = Image.open(p).convert("RGBA")
        return self._img

    def icon_png(self, type_, level):
        f = self.frames.get("feat_%d_%d.png" % (type_, level)) or self.frames.get("feat_%d_1.png" % type_)
        if not f:
            return None
        x, y, w, h = f[:4]
        buf = io.BytesIO()
        self.image().crop((x, y, x + w, y + h)).save(buf, "PNG")
        return buf.getvalue()

    def add(self, type_, level, png=None, from_type=None, from_level=1):
        """Append (or replace) frame feat_<type>_<level>, copying another frame or a given image."""
        Image = _pil()
        if png is not None:
            icon = Image.open(io.BytesIO(png)).convert("RGBA").resize((60, 70), Image.LANCZOS)
        else:
            f = self.frames.get("feat_%d_%d.png" % (from_type, from_level)) or self.frames["feat_%d_1.png" % from_type]
            x, y, w, h = f[:4]
            icon = self.image().crop((x, y, x + w, y + h))
        name = "feat_%d_%d.png" % (type_, level)
        img = self.image()
        if name in self.frames:
            x, y, w, h = self.frames[name][:4]
            img.paste(icon.resize((w, h)), (x, y))
            return
        # new frames go on rows below the existing content; the sheet grows downwards when needed
        if not hasattr(self, "_cursor"):
            bottom = max(fy + fh for fx, fy, fw, fh, _, _ in self.frames.values())
            self._cursor = [1, bottom + 1, 0]          # x, y, row height
        x, y, rh = self._cursor
        if x + icon.width + 1 > img.width:
            x, y, rh = 1, y + rh + 1, 0
        need = (y + icon.height + 1 + 3) & ~3
        if need > img.height:
            grown = Image.new("RGBA", (img.width, need), (0, 0, 0, 0))
            grown.paste(img, (0, 0))
            self._img = img = grown
        img.paste(icon, (x, y))
        self.frames[name] = (x, y, icon.width, icon.height, 0, 0)
        self._cursor = [x + icon.width + 1, y, max(rh, icon.height)]

    def save(self, backup_dir=None):
        stem = os.path.splitext(self.texture)[0]
        xml_dst = self.gd._pkg_asset(self.XML)
        img_dst = self.gd._pkg_asset("image/%s.webp" % stem)
        for p in (xml_dst, img_dst):
            _backup(p, self.gd.package, backup_dir)
        os.makedirs(os.path.dirname(xml_dst), exist_ok=True)
        lines = ['<Texture name="%s" />' % self.texture, "<Images>"]
        for name, (x, y, w, h, rx, ry) in self.frames.items():
            lines.append('    <Image name="%s" x="%d" y="%d" w="%d" h="%d" refx="%d" refy="%d" />'
                         % (name, x, y, w, h, rx, ry))
        lines.append("</Images>")
        body = self.nl.join(lines) + self.nl
        with open(xml_dst, "wb") as f:
            f.write(body.encode("utf-8"))
        self.image().save(img_dst, "WEBP", lossless=True)
        return [xml_dst, img_dst]
