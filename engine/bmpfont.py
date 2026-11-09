"""位图字体渲染（BMFont .fnt）—— 对齐原版 GameFonts::getTexFont。

fnt 在 assets/raw/fonts/；字形图在 assets/raw/pic/font/（page file 引用相对路径）。
GameFonts 按尺寸选择字体（原版按 pt 大小挑 captuer_it_1/2/3 或 ezad_white）。
"""

import os
import re

import pygame

from engine import res


RAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "raw")
FONTS = os.path.join(RAW, "fonts")

_cache = {}


def _load(fnt_name):
    if fnt_name in _cache:
        return _cache[fnt_name]
    path = os.path.join(FONTS, fnt_name)
    if not os.path.exists(path):
        _cache[fnt_name] = None
        return None
    info = dict(chars={}, line_height=36, size=36, page=None)
    with open(path, encoding="utf-8", errors="replace") as f:
        txt = f.read()
    m = re.search(r'lineHeight=(\d+)', txt)
    if m:
        info["line_height"] = int(m.group(1))
    m = re.search(r'size=(\d+)', txt)
    if m:
        info["size"] = int(m.group(1))
    m = re.search(r'file="([^"]+)"', txt)
    page_file = m.group(1) if m else None
    # page 图：assets/images/fonts/ 下同名 png（原版卷内路径 fonts/<name>.png）
    img = None
    if page_file:
        p = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets",
            "images",
            "fonts",
            page_file,
        )
        if os.path.exists(p):
            img = pygame.image.load(p).convert_alpha()
    info["page"] = img
    for cm in re.finditer(
        r'char id=(\d+)\s+x=(\d+)\s+y=(\d+)\s+width=(\d+)\s+'
        r'height=(\d+)\s+xoffset=(-?\d+)\s+yoffset=(-?\d+)\s+'
        r'xadvance=(-?\d+)',
        txt,
    ):
        cid, x, y, w, h, xo, yo, xa = map(int, cm.groups())
        info["chars"][cid] = (x, y, w, h, xo, yo, xa)
    _cache[fnt_name] = info
    return info


# GameFonts 字号→fnt 映射（原版按 getTexFont(int size) 选，实测顺序）
_FNTS_BY_SIZE = ["captuer_it.fnt", "captuer_it_1.fnt", "captuer_it_2.fnt", "captuer_it_3.fnt"]


def pick_font(pt):
    """对齐 GameFonts::instance(size)→getTexFont(type) 的选择：pt 越大字越大。
    captuer_it.fnt 基准 size≈36，缩放渲染。"""
    return "captuer_it.fnt"


class BitmapText:
    """一行位图字体文本。size 参数 = 原版 GameFonts pt。"""

    def __init__(self, text, size=36, color=(255, 255, 255, 255)):
        self.text = text
        self.pt = size
        self.color = color
        self.info = _load(pick_font(size))
        self.surf = self._render()

    def _render(self):
        info = self.info
        if not info or not info["page"]:
            return None
        scale = self.pt / float(info["size"]) if info["size"] else 1.0
        pieces = []
        x = 0
        for ch in self.text:
            cid = ord(ch)
            c = info["chars"].get(cid)
            if not c:
                x += int(10 * scale)
                continue
            gx, gy, gw, gh, xo, yo, xa = c
            glyph = info["page"].subsurface((gx, gy, gw, gh)).copy()
            if scale != 1.0:
                glyph = pygame.transform.smoothscale(
                    glyph, (max(1, int(gw * scale)), max(1, int(gh * scale)))
                )
            if self.color != (255, 255, 255, 255):
                tint = pygame.Surface(glyph.get_size(), pygame.SRCALPHA)
                tint.fill(self.color)
                glyph = glyph.copy()
                glyph.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            pieces.append((glyph, x + xo * scale, yo * scale))
            x += xa * scale
        if not pieces:
            return None
        w = int(max(px + g.get_width() for g, px, py in pieces)) + 2
        h = int(max(py + g.get_height() for g, px, py in pieces)) + 2
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for g, px, py in pieces:
            surf.blit(g, (px, py))
        return surf

    def draw(self, s, x, y, anchor=(0.0, 0.5)):
        if self.surf:
            s.blit(
                self.surf,
                (x - self.surf.get_width() * anchor[0], y - self.surf.get_height() * anchor[1]),
            )
