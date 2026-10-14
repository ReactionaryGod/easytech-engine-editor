"""Sprite atlases addressed by frame name (xml of <Image name x y w h refx refy> plus one image)."""
import io
import os
import re

from . import gamedata


class NamedAtlas:
    def __init__(self, gd, xml_rel, img_rel, writable=True):
        from PIL import Image
        self.gd, self.xml_rel, self.img_rel = gd, xml_rel, img_rel
        self.frames = {}
        self.nl = "\r\n"
        xml = gd.find_asset(xml_rel)
        self.image = None
        if xml:
            with open(xml, "rb") as f:
                text = f.read().decode("utf-8-sig")
            self.nl = "\r\n" if "\r\n" in text else "\n"
            pat = (r'<Image name="([^"]+)" x="(\d+)" y="(\d+)" w="(\d+)" h="(\d+)" '
                   r'refx="(-?\d+)" refy="(-?\d+)"')
            for m in re.finditer(pat, text):
                self.frames[m.group(1)] = tuple(int(m.group(i)) for i in range(2, 8))
            img = gd.find_asset(img_rel)
            if img:
                self.image = Image.open(img).convert("RGBA")
        if self.image is None:
            self.image = Image.new("RGBA", (1024, 256), (0, 0, 0, 0))
        self.texture = os.path.basename(img_rel)
        self._cursor = None

    def png(self, name):
        f = self.frames.get(name)
        if not f:
            return None
        x, y, w, h = f[:4]
        buf = io.BytesIO()
        self.image.crop((x, y, x + w, y + h)).save(buf, "PNG")
        return buf.getvalue()

    def set(self, name, png, size):
        from PIL import Image
        icon = Image.open(io.BytesIO(png)).convert("RGBA").resize(size, Image.LANCZOS)
        if name in self.frames:
            x, y, w, h = self.frames[name][:4]
            self.image.paste(icon.resize((w, h)), (x, y))
            return
        if self._cursor is None:
            bottom = max((fy + fh for _x, fy, _w, fh, _a, _b in self.frames.values()), default=0)
            self._cursor = [1, bottom + 1, 0]
        x, y, row_h = self._cursor
        if x + icon.width + 1 > self.image.width:
            x, y, row_h = 1, y + row_h + 1, 0
        need = (y + icon.height + 1 + 3) & ~3
        if need > self.image.height:
            grown = Image.new("RGBA", (self.image.width, need), (0, 0, 0, 0))
            grown.paste(self.image, (0, 0))
            self.image = grown
        self.image.paste(icon, (x, y))
        self.frames[name] = (x, y, icon.width, icon.height, 0, 0)
        self._cursor = [x + icon.width + 1, y, max(row_h, icon.height)]

    def save(self, backup_dir=None):
        xml_dst, img_dst = self.gd._pkg_asset(self.xml_rel), self.gd._pkg_asset(self.img_rel)
        for p in (xml_dst, img_dst):
            gamedata._backup(p, self.gd.package, backup_dir)
        os.makedirs(os.path.dirname(xml_dst), exist_ok=True)
        lines = ['<Texture name="%s" />' % self.texture, "<Images>"]
        for name, (x, y, w, h, rx, ry) in self.frames.items():
            lines.append('    <Image name="%s" x="%d" y="%d" w="%d" h="%d" refx="%d" refy="%d" />'
                         % (name, x, y, w, h, rx, ry))
        lines.append("</Images>")
        with open(xml_dst, "wb") as f:
            f.write((self.nl.join(lines) + self.nl).encode("utf-8"))
        self.image.save(img_dst, "PNG")
        return [xml_dst, img_dst]
