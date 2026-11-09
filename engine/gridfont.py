"""EzTexFont 网格位图字体 —— 对应原版 ezjoy::EzTexFont。

原版 GameFonts::init（@0x11d740）建立的字体表：
  0 score_white.png      "1234567890,x+-:/%"  1×17
  1 score_gold.png       "1234567890,x+-:/"    1×16
  2 score_blue.png       "1234567890,x+-:/"    1×16
  3 number_blood.png     "1234567890"          1×10
  4 shop_gun_number.png  "0123456789"          1×10
  5 shop_ability_number.png "0123456789"       1×10
  6 shop_bank_number.png "0123456789.$"        1×12
  7 achivement_number.png "0123456789/"        1×11
  8 daily_task_num.png   "01235"               1×5
  9 day_reward_num.png   "12345"               1×5

EzTexFont::node(png, rows, cols, chars, ...) 把一张图按 rows×cols 网格切成
若干帧，每帧对应 chars 里的一个字符（按行优先）。

本模块提供 GridFont：按网格切帧 + 按字符查表 + 缩放绘制。
"""

import pygame

from engine import res


class GridFont:
    """网格位图字体。sheet 为贴图，cols 为列数，order 为字符顺序。

    对应原版 ezjoy::EzTexFont（@0x1b9d78 init）：
      · 贴图按 rows×cols 网格切帧，每帧对应 order 里的一个字符
      · 帧内字形用 get_bounding_rect 裁出
      · **字号 size**：字形最终高度 = 字号，缩放比 = size / 帧高
        （原版 this[81] = 字号，this[84] = 字号 / 帧高）
      · 字符步进 = 帧宽 × 缩放比
    渲染时再乘调用方的 scale（对应原版 CCNode::setScale）。
    """

    def __init__(self, sheet, cols, order, rows=1, size=0.0, spacing=0.8):
        self.sheet = sheet
        self.order = order
        self.cols = cols
        self.rows = rows
        self.size = float(size)
        self.spacing = float(spacing)
        self.cell_w = 0
        self.cell_h = 0
        self.glyphs = {}
        # (字, 宽, 高) -> 缩放好的字形；同一段文字每帧的缩放结果完全一样
        self._sc = {}
        if not sheet:
            return
        sw, sh = sheet.get_size()
        cw = sw // cols
        ch = sh // rows
        self.cell_w = cw
        self.cell_h = ch
        for i, c in enumerate(order):
            if i >= rows * cols:
                break
            r = i // cols
            cix = i % cols
            rect = pygame.Rect(cix * cw, r * ch, cw, ch)
            if not sheet.get_rect().contains(rect):
                break
            cell = sheet.subsurface(rect).copy()
            bb = cell.get_bounding_rect()
            self.glyphs[c] = (cell, bb)

    def _ratio(self, k=1.0):
        """字形缩放比 = 字号/帧高 × k（字号为 0 时退化为 1）。

        原版 EzTexFont::init（@0x1b9d78）：
          this[84] = this[81] / 帧高        ← 字符节点的 scale
          this[83] = 帧高 × this[84] = 字号  ← 字高
          this[82] = (2×spacing+1) × 帧宽 × this[84]  ← 字符步进
        """
        if self.size and self.cell_h:
            return (self.size / float(self.cell_h)) * k
        return k

    def _advance(self, r):
        """单个字符的步进宽度。"""
        if self.size and self.cell_h:
            return (2.0 * self.spacing + 1.0) * self.cell_w * r
        return self.cell_w * r

    def text_size(self, text, k=1.0):
        """返回 (宽, 高)。

        宽 = 最后一个字符的起点 + 其宽度（去掉尾部留白）；
        高 = 字号 × k（原版 this[83] × 节点 scale）。
        """
        r = self._ratio(k)
        text = str(text)
        if not text:
            return 0, 0
        f = ((self.size if self.size else self.cell_h) * k) / max(1.0, self.cell_h)
        w = 0.0
        for _c in text:
            w += self._advance(r)
        # 末尾字符只占自身墨迹宽
        last = self.glyphs.get(text[-1])
        if last:
            w -= self._advance(r) - last[1].width * f
        h = (self.size if self.size else self.cell_h) * k
        return int(round(w)), int(round(h))

    def draw(self, surf, text, x, y, k=1.0, align=(0.0, 0.0)):
        """在 (x, y) 绘制文本。

        align: (ax, ay) ∈ [0,1]，0=左/上，0.5=居中，1=右/下。
        """
        text = str(text)
        r = self._ratio(k)
        tw, th = self.text_size(text, k)
        sx = x - tw * align[0]
        sy = y - th * align[1]
        # 字形缩放到「字号 × k」高，垂直居中于字行
        target_h = (self.size if self.size else self.cell_h) * k
        # 墨迹缩放比 = 目标字高 / 帧高（= 字号/帧高 × k = ratio）
        f = target_h / max(1.0, self.cell_h)
        for c in text:
            g = self.glyphs.get(c)
            if not g:
                sx += self._advance(r)
                continue
            cell, bb = g
            if bb.width and bb.height:
                w = max(1, int(round(bb.width * f)))
                h = max(1, int(round(bb.height * f)))
                im = self._sc.get((c, w, h))
                if im is None:
                    im = pygame.transform.smoothscale(cell.subsurface(bb).copy(), (w, h))
                    self._sc[(c, w, h)] = im
                # ★ 按**字格**定位，不按墨迹居中对齐。
                #   每个数字的墨迹高度不同（"1" 没有下伸部、"9" 有），
                #   逐个居中会把同一行数字拉成高低不齐的斜行 ——
                #   战斗 HUD 的钻石数就有这个毛病。
                #   整格高 = cell_h*f = target_h，格顶就在 sy，
                #   墨迹在格内的偏移 = bb.top*f。
                surf.blit(im, (int(round(sx)), int(round(sy + bb.top * f))))
            sx += self._advance(r)
        return tw, th


# ---- 原版 GameFonts 字体表 ----
# (贴图, 列数, 字符表, 字号, 步进系数)
# 原版 GameFonts::init（@0x11d740）逐个调 ezjoy::EzTexFont::node(png, rows, cols,
# chars, size, spacing)：
#   size    = 第 5 参数（字号）：score_* = 25.0，其余 = 26.0
#   spacing = 第 6 参数：-1110651699 = -0.1f（大部分）或 0
#   字符步进 = (2*spacing + 1) * 帧宽 * (字号/帧高)
# 注意数组下标 ≠ 构造顺序：init 里 v5(score_blue) 写到 offset 12、v6(number_blood)
# 写到 offset 8，所以 fonts[2] = number_blood、fonts[3] = score_blue。
_FONT_SPECS = {
    0: ("pic/fonts/score_white.png", 17, "1234567890,x+-:/%", 25.0, -0.1),
    1: ("pic/fonts/score_gold.png", 16, "1234567890,x+-:/", 25.0, -0.1),
    2: ("pic/fonts/number_blood.png", 10, "1234567890", 26.0, 0.0),
    3: ("pic/fonts/score_blue.png", 16, "1234567890,x+-:/", 25.0, -0.1),
    4: ("pic/fonts/shop_gun_number.png", 10, "0123456789", 26.0, -0.1),
    5: ("pic/fonts/shop_ability_number.png", 10, "0123456789", 26.0, -0.1),
    6: ("pic/fonts/shop_bank_number.png", 12, "0123456789.$", 26.0, 0.0),
    7: ("pic/fonts/achivement_number.png", 11, "0123456789/", 26.0, -0.1),
    8: ("pic/fonts/daily_task_num.png", 5, "01235", 26.0, -0.1),
    9: ("pic/fonts/day_reward_num.png", 5, "12345", 26.0, -0.1),
}

_cache = {}


def get_font(index):
    """按原版 GameFonts 的 type 索引取字体对象（带缓存）。"""
    if index in _cache:
        return _cache[index]
    spec = _FONT_SPECS.get(index)
    if not spec:
        _cache[index] = None
        return None
    path, cols, order, size, spacing = spec
    sheet = res.load_img(path)
    f = GridFont(sheet, cols, order, size=size, spacing=spacing) if sheet else None
    _cache[index] = f
    return f
