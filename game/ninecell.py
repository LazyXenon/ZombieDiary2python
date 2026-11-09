"""九宫格图集渲染 —— 对应原版 Combined9Cells。

原版 Combined9Cells（@0x1c2b6a update）不是简单拉伸，而是把一张贴图按
**3×3 图集**切成 9 帧，再按九宫格布局摆放：

  帧号 → 图集位置：f → (row = 2 - f//3, col = f%3)
  （图集第 0 行在贴图顶部，帧号 0 对应左下角）

  槽位 → 帧号：
    左上=6  上中=7  右上=8
    左中=3  中心=4  右中=5
    左下=0  下中=1  右下=2

  布局（目标尺寸 w×h，边框尺寸 bw×bh，即中心格尺寸）：
    四角    原尺寸绘制，中心在边框四角
    上中/下中  横向拉伸到 w-2bw，高 bh
    左中/右中  纵向拉伸到 h-2bh，宽 bw
    中心    双向拉伸到 (w-2bw)×(h-2bh)

边框尺寸取自中心格（帧4）的尺寸，并被目标尺寸夹住。
"""

import pygame

from engine import res


_FRAME_SRC = {}
_FRAME_SCALED = {}


def _frame_src(im, tw, th, f):
    """图集帧的切片（同一张贴图的同一帧只切一次）。"""
    key = (id(im), f)
    hit = _FRAME_SRC.get(key)
    if hit is not None and hit[0] is im:
        return hit[1]
    out = im.subsurface(_frame_rect(tw, th, f)).copy()
    _FRAME_SRC[key] = (im, out)
    return out


def _frame_scaled(im, tw, th, f, w, h):
    """帧切片 + 目标尺寸的缩放结果（同帧同尺寸每帧都一样，缓存掉）。"""
    key = (id(im), f, w, h)
    hit = _FRAME_SCALED.get(key)
    if hit is not None and hit[0] is im:
        return hit[1]
    out = pygame.transform.smoothscale(_frame_src(im, tw, th, f), (w, h))
    if len(_FRAME_SCALED) > 256:
        _FRAME_SCALED.clear()
    _FRAME_SCALED[key] = (im, out)
    return out


def _frame_rect(tw, th, f):
    """帧号 f → 贴图内矩形。"""
    cw = tw / 3.0
    ch = th / 3.0
    col = f % 3
    row = 2 - f // 3
    x = int(round(col * cw))
    y = int(round(row * ch))
    x1 = int(round((col + 1) * cw))
    y1 = int(round((row + 1) * ch))
    return pygame.Rect(x, y, x1 - x, y1 - y)


def border_size(tex, scale=1.0):
    """九宫格边框尺寸（= 图集单个中心格的尺寸 × scale）。"""
    im = res.load_img(tex)
    if not im:
        return 0, 0
    tw, th = im.get_size()
    return (max(1, int(round(tw / 3.0 * scale))), max(1, int(round(th / 3.0 * scale))))


def inner_rect(tex, rect, scale=1.0):
    """九宫格边框内部的可用区域（去掉四周边框）。"""
    bw, bh = border_size(tex, scale)
    return pygame.Rect(rect.x + bw, rect.y + bh, max(1, rect.w - 2 * bw), max(1, rect.h - 2 * bh))


_BOUNDS = {}
_LINES = {}


def visible_bounds(tex, scale=1.0):
    """九宫格贴图里**真正画出来**的边框，相对贴图四边各内缩多少像素。

    3×3 图集的边条并不是满格的：9cell_bg.png 是 244×183，每格 81×61，
    但左中格的不透明部分从 x=26 才开始、右中格到 x=231 就结束。所以直接
    超过边框，所有背景都不能超过边框」）。这里按像素采样量一次并缓存。
    """
    key = (tex, round(float(scale), 3))
    if key in _BOUNDS:
        return _BOUNDS[key]
    im = res.load_img(tex)
    if not im:
        _BOUNDS[key] = (0, 0, 0, 0)
        return _BOUNDS[key]
    w, h = im.get_size()
    cw, ch = max(1, w // 3), max(1, h // 3)

    def col_has(x, y0, y1):
        return any(im.get_at((x, y))[3] > 8 for y in range(y0, y1, 2))

    def row_has(y, x0, x1):
        return any(im.get_at((x, y))[3] > 8 for x in range(x0, x1, 2))

    left = next((x for x in range(cw) if col_has(x, ch, h - ch)), 0)
    right = next((x for x in range(w - 1, 2 * cw, -1) if col_has(x, ch, h - ch)), w - 1)
    top = next((y for y in range(ch) if row_has(y, cw, w - cw)), 0)
    bottom = next((y for y in range(h - 1, 2 * ch, -1) if row_has(y, cw, w - cw)), h - 1)
    out = (
        int(left * scale),
        int(top * scale),
        int((w - 1 - right) * scale),
        int((h - 1 - bottom) * scale),
    )
    _BOUNDS[key] = out
    return out


def inner_panel(tex, rect, scale=1.0):
    """框线以内、可以放心铺底色的矩形。"""
    left, top, right, bottom = visible_bounds(tex, scale)
    return pygame.Rect(
        rect.x + left,
        rect.y + top,
        max(1, rect.w - left - right),
        max(1, rect.h - top - bottom),
    )


def frame_line(tex):
    """九宫格里那圈**白描边**相对贴图四边的位置 (l, t, r, b)。

    visible_bounds() 是按 alpha 找边界的，可边带里除了描边还有投影和装饰：
    9cell_bg.png 底部白线在 y=156~158，线下面还有 27px 半透明黑影。
    按 alpha 算出来的「内框」会一路顶到黑影里，内容（按钮/文字）就会压在
    描边上——金手指的「确认入账」正是这样掉出下边框的
    （用户：「贴图必须在框框里面」）。
    这里改成找中带里那一圈亮白描边，取描边的**内侧**。
    """
    if tex in _LINES:
        return _LINES[tex]
    im = res.load_img(tex)
    if not im:
        _LINES[tex] = (0, 0, 0, 0)
        return _LINES[tex]
    tw, th = im.get_size()
    cw, ch = max(1, tw // 3), max(1, th // 3)

    def bright(p):
        return p[3] > 200 and p[0] + p[1] + p[2] > 430

    top_rows, bot_rows, left_cols, right_cols = [], [], [], []
    for y in range(ch):
        if sum(1 for x in range(cw + 4, 2 * cw - 4, 4) if bright(im.get_at((x, y)))) >= 3:
            top_rows.append(y)
    for y in range(2 * ch, th):
        if sum(1 for x in range(cw + 4, 2 * cw - 4, 4) if bright(im.get_at((x, y)))) >= 3:
            bot_rows.append(y)
    for x in range(cw):
        if sum(1 for y in range(ch + 4, 2 * ch - 4, 4) if bright(im.get_at((x, y)))) >= 3:
            left_cols.append(x)
    for x in range(2 * cw, tw):
        if sum(1 for y in range(ch + 4, 2 * ch - 4, 4) if bright(im.get_at((x, y)))) >= 3:
            right_cols.append(x)

    left = left_cols[-1] + 1 if left_cols else 0
    top = top_rows[-1] + 1 if top_rows else 0
    right = tw - right_cols[0] if right_cols else 0
    bottom = th - bot_rows[0] if bot_rows else 0
    _LINES[tex] = (int(left), int(top), int(right), int(bottom))
    return _LINES[tex]


def frame_inner(tex, rect, scale=1.0):
    """描边以内的内容区（按钮、文字都放这里面）。

    和 inner_panel 的区别：inner_panel 只保证底色不溢出框线，
    frame_inner 保证内容不压到描边上。
    """
    left, top, right, bottom = frame_line(tex)
    return pygame.Rect(
        rect.x + int(left * scale),
        rect.y + int(top * scale),
        max(1, rect.w - int((left + right) * scale)),
        max(1, rect.h - int((top + bottom) * scale)),
    )


def fill_panel(s, tex, rect, color, scale=1.0):
    """在九宫格框线**以内**铺底色（再做 draw_9cell_atlas）。

    替代「往整个 rect 里 fill」的写法 —— 那样颜色会溢出到框线外面。
    """
    inner = inner_panel(tex, rect, scale)
    if len(color) == 4:
        layer = pygame.Surface(inner.size, pygame.SRCALPHA)
        layer.fill(color)
        s.blit(layer, inner.topleft)
    else:
        s.fill(color, inner)
    return inner


def draw_9cell_atlas(s, tex, rect, scale=1.0):
    """按 Combined9Cells 的布局绘制 3×3 图集九宫格。

    rect: 目标矩形（屏幕坐标，左上角原点）。
    scale: DialogBg 的整体缩放（边框尺寸随之缩放）。
    """
    im = res.load_img(tex)
    if not im:
        return
    tw, th = im.get_size()
    cw = tw / 3.0
    ch = th / 3.0
    bw = max(1, int(round(cw * scale)))
    bh = max(1, int(round(ch * scale)))
    w, h = rect.w, rect.h
    if w <= 2 * bw or h <= 2 * bh:
        # 目标太小，直接整块拉伸
        s.blit(pygame.transform.smoothscale(im, (w, h)), rect.topleft)
        return

    # 中心（帧4）双向拉伸
    s.blit(_frame_scaled(im, tw, th, 4, w - 2 * bw, h - 2 * bh), (rect.x + bw, rect.y + bh))
    # 上中（帧7）/ 下中（帧1）横向拉伸
    for f, dy in ((7, rect.y), (1, rect.bottom - bh)):
        s.blit(_frame_scaled(im, tw, th, f, w - 2 * bw, bh), (rect.x + bw, dy))
    # 左中（帧3）/ 右中（帧5）纵向拉伸
    for f, dx in ((3, rect.x), (5, rect.right - bw)):
        s.blit(_frame_scaled(im, tw, th, f, bw, h - 2 * bh), (dx, rect.y + bh))
    # 四角原尺寸
    for f, (dx, dy) in (
        (6, (rect.x, rect.y)),
        (8, (rect.right - bw, rect.y)),
        (0, (rect.x, rect.bottom - bh)),
        (2, (rect.right - bw, rect.bottom - bh)),
    ):
        s.blit(_frame_src(im, tw, th, f), (dx, dy))
