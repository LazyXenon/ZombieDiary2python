"""对话框基类 —— 对齐原版 EzBaseDialog / EzFunctionButton 语义。

原版约定（从反编译照抄）：
  * 按钮 = EzFunctionButton，贴图两态（选中/未选中）上下两半
  * 按钮 anchor 用 CCPoint 构造器显式设置，不是默认值
  * 位置一律是「父节点尺寸 × 比例」，没有魔法数字
  * cocos y 向上 → 屏幕 y 向下

本模块提供：
  Dialog       基类：背景 + 按钮 + 点击命中
  DButton      按钮：贴图 / anchor / pos / scale / on_off 两态
"""

import math

import pygame

from engine import res


W, H = 854, 480
CLOSE_W, CLOSE_H = 50, 32
CLOSE_TEX = "pic/ui/dialog/button_close.png"


def close_rect_for(panel, right=10, top=10):
    """把官方叉号贴在面板右上角内侧。"""
    p = pygame.Rect(panel)
    return pygame.Rect(p.right - CLOSE_W - right, p.top + top, CLOSE_W, CLOSE_H)


def default_close_rect(full=False):
    """全屏层贴屏幕右上角；普通弹窗贴设置面板规格的右上角。"""
    if full:
        return pygame.Rect(W - CLOSE_W - 8, 8, CLOSE_W, CLOSE_H)
    return pygame.Rect(W - CLOSE_W - 58, 66, CLOSE_W, CLOSE_H)


def draw_close_icon(s, rect):
    im = res.load_img(CLOSE_TEX)
    if not im or rect is None:
        return
    s.blit(pygame.transform.smoothscale(im, (rect.w, rect.h)), rect.topleft)


# 按钮表面的斜向扫光（按尺寸缓存，避免每帧重画）。
_SHEEN_CACHE = {}


def _sheen_band(w, h):
    """斜向扫光条。

    注意这里是**不带 alpha 的灰度图**，贴上去时用 BLEND_RGB_ADD：
    会把 alpha 也加满，按钮上直接糊一块死白。
    """
    key = (w, h)
    band = _SHEEN_CACHE.get(key)
    if band is not None:
        return band
    bw = max(8, int(w * 0.17))
    band = pygame.Surface((bw, h * 2 + 24))
    band.fill((0, 0, 0))
    for i in range(bw):
        a = int(64 * math.sin(math.pi * (i + 0.5) / bw) ** 1.5)
        pygame.draw.line(band, (a, a, a), (i, 0), (i, band.get_height()))
    band = pygame.transform.rotate(band, 16)
    _SHEEN_CACHE[key] = band
    return band


def _img(name):
    return res.load_img(name)


class DButton:
    """原版 EzFunctionButton 的最小复刻。

    tex    贴图路径
    anchor (ax, ay)  cocos anchor
    pos    (x, y)    cocos 坐标（y 向上）
    scale  缩放
    on_off 双态贴图：选中时画上半张，否则画下半张
    """

    def __init__(
        self, tex, pos, anchor=(0.5, 0.5), scale=1.0, on_off=False, callback=None, name=""
    ):
        self.tex = tex
        self.pos = pos
        self.anchor = anchor
        self.scale = scale
        self.on_off = on_off
        self.callback = callback
        self.name = name
        self.checked = False
        self.enabled = True
        self.rect = pygame.Rect(0, 0, 0, 0)
        self._compute_rect()

    def _compute_rect(self):
        """按贴图尺寸和 anchor 算出屏幕矩形（不依赖是否已绘制过）。"""
        im = _img(self.tex)
        if not im:
            return
        w = int(im.get_width() * self.scale)
        h = int(im.get_height() * self.scale)
        if self.on_off:
            h = h // 2
        x = int(self.pos[0] - self.anchor[0] * w)
        y = int(H - self.pos[1] - (1.0 - self.anchor[1]) * h)
        self.rect = pygame.Rect(x, y, w, h)

    def image(self):
        """取贴图。

        on_off=True 时贴图是「上下两态」纵向拼接（212x92 = 两个 212x46）：
          上半 = 开 / 选中，下半 = 关 / 未选中。
        原版实现是四个独立 CCSprite 切可见性（walker dump：
          Block_12 内 rect [300,407]=[音乐开] [300,453]=[音乐关]
                              [300,315]=[音效开] [300,361]=[音效关]），
        效果等价。
        """
        im = _img(self.tex)
        if not im:
            return None
        if self.on_off:
            w, h = im.get_size()
            row = 0 if self.checked else h // 2
            if h >= row * 2 + 1:
                return im.subsurface(pygame.Rect(0, row, w, h // 2)).copy()
        return im

    def draw(self, s, pressed=False):
        """画按钮。

        pressed=True 时按 0.94 倍缩小 + 下移 2px 模拟按压，
        这是 EzFunctionButton 的按下态（原版切 pressed 贴图，
        我们没有那套贴图，用几何形变等效）。
        """
        im = self.image()
        if not im:
            return
        w = int(im.get_width() * self.scale)
        h = int(im.get_height() * self.scale)
        if (w, h) != im.get_size():
            im = pygame.transform.smoothscale(im, (w, h))
        # cocos anchor(0,0) 是左下；转换到屏幕像素
        x = int(self.pos[0] - self.anchor[0] * w)
        y = int(H - self.pos[1] - (1.0 - self.anchor[1]) * h)
        if pressed:
            pw = max(1, int(w * 0.94))
            ph = max(1, int(h * 0.94))
            im = pygame.transform.smoothscale(im, (pw, ph))
            x += (w - pw) // 2
            y += (h - ph) // 2 + 2
            w, h = pw, ph
        tick = pygame.time.get_ticks() % 5600
        if tick < 2200 and w > 24 and h > 12:
            ph_t = tick / 2200.0
            if ph_t < 0.75:
                band = _sheen_band(w, h)
                im = im.copy()
                bx = int(-band.get_width() + (w + band.get_width() * 2) * (ph_t / 0.75))
                im.blit(band, (bx, -10), special_flags=pygame.BLEND_RGB_ADD)
        s.blit(im, (x, y))
        self.rect = pygame.Rect(x, y, w, h)

    def hit(self, p):
        return self.enabled and self.rect.collidepoint(p)


class Dialog:
    """对话框基类。子类覆盖 build() 建按钮，on_click 分派。"""

    # 弹出动画：cocos EzBaseDialog 的 open 用 CCScaleTo + CCFadeIn，
    # 从 0.6 倍弹到 1.0，用时 0.18s（含一个短促的过冲）。
    POP_TIME = 0.18
    POP_FROM = 0.62

    CLOSE_FULL = False
    CLOSE_CUSTOM = False

    def __init__(self, app):
        self.app = app
        self.buttons = []
        self.t = 0.0
        self.done = False
        self.result = None
        self.close_rect = None
        self._draw_close = False
        self.build()
        self._init_close_button()

    def pop_scale(self):
        """0 → 1 的弹出进度换算成缩放。"""
        if self.t >= self.POP_TIME:
            return 1.0
        k = self.t / self.POP_TIME
        if k <= 0:
            return self.POP_FROM
        # ease-out-back（只保留尾巴的过冲）。标准 EaseBackOut 在 k≈0.05 会先
        # 往回沉一点（0.62→0.58），视觉上是「抖一下」；把负段夹掉。
        c1 = 1.70158
        c3 = c1 + 1.0
        e = c3 * k * k * k - c1 * k * k
        if e < 0:
            e = 0.0
        return self.POP_FROM + (1.0 - self.POP_FROM) * e

    def close_button_rect(self):
        return default_close_rect(self.CLOSE_FULL)

    def _init_close_button(self):
        if self.CLOSE_CUSTOM:
            return
        for b in self.buttons:
            if str(getattr(b, "tex", "")).endswith("button_close.png"):
                self.close_rect = b.rect.copy()
                return
        self.close_rect = self.close_button_rect()
        self._draw_close = True

    def request_close(self):
        name = type(self).__name__
        if name == "PauseDialog":
            self.result = "resume"
        elif name in ("GameWinDialog", "GameLoseDialog", "LevelFailedDialog"):
            self.result = "quit"
        else:
            self.result = "close"
        self.done = True
        return True

    # ---- 子类实现 ----
    def build(self):
        pass

    def on_click(self, btn):
        pass

    def on_key(self, key):
        pass

    # ---- 通用 ----
    def add(self, btn):
        self.buttons.append(btn)
        return btn

    def update(self, dt):
        self.t += dt
        # 子类把 done 置 True 就表示「该关了」——但不立刻结束，
        # 先播 0.12s 收起动画。用 _wanted_done 记住请求，
        # 不篡改 done（子类可能在 done 之后还要读它）。
        if self.done and not self.closing():
            self._wanted_done = True
            self.close()
        if self.closing():
            self._close_t += dt
            if self._close_t >= self.CLOSE_TIME:
                self.done = True
            else:
                self.done = False

    def draw(self, s):
        sc = self.pop_scale()
        csc, calpha = self.close_scale()
        if calpha <= 0.0:
            return
        sc *= csc
        if abs(sc - 1.0) < 0.002 and calpha >= 0.999:
            for b in self.buttons:
                b.draw(s)
            self._draw_close_button(s)
            return
        # 整层缩放：先画到临时层再缩放贴回（弹出动画期间才会走到）
        lay = pygame.Surface((W, H), pygame.SRCALPHA)
        for b in self.buttons:
            b.draw(lay)
        self._draw_close_button(lay)
        w, h = int(W * sc), int(H * sc)
        if w < 2 or h < 2:
            return
        z = pygame.transform.smoothscale(lay, (w, h))
        if calpha < 0.999:
            z.set_alpha(int(255 * calpha))
        s.blit(z, ((W - w) // 2, (H - h) // 2))

    def _draw_close_button(self, s):
        if not self._draw_close or self.close_rect is None:
            return
        draw_close_icon(s, self.close_rect)

    CLOSE_TIME = 0.12

    def close(self):
        """开始收起动画；动画播完 done 才置 True。"""
        if getattr(self, "_closing", False):
            return
        self._closing = True
        self._close_t = 0.0

    def closing(self):
        return getattr(self, "_closing", False)

    def close_scale(self):
        """收起进度 → 缩放（1 → 0.7，同时淡出）。"""
        if not self.closing():
            return 1.0, 1.0
        k = min(1.0, self._close_t / self.CLOSE_TIME)
        return (1.0 - 0.3 * k), (1.0 - k)

    def click(self, pos):
        if self.closing():
            return False
        if self.close_rect is not None and self.close_rect.collidepoint(pos):
            return self.request_close()
        for b in reversed(self.buttons):
            if b.hit(pos):
                # 按钮自己的回调优先（对应原版 EzFunctionButton::onTouchEnd）
                if b.callback:
                    b.callback(b)
                self.on_click(b)
                return True
        return False

    def press(self, pos):
        """按下：记住哪个按钮被按住，draw 时画按下态。

        返回 True 表示吃掉了这次按下（有按钮命中）。
        """
        if self.closing():
            return False
        for b in reversed(self.buttons):
            if b.hit(pos):
                self._pressed_btn = b
                return True
        self._pressed_btn = None
        return False

    def release(self):
        """松手：清掉按下态。"""
        self._pressed_btn = None

    def _is_pressed(self, btn):
        return getattr(self, "_pressed_btn", None) is btn

    def key(self, k):
        self.on_key(k)


def bg_dim(s, alpha=170):
    """原版对话框弹出时背景会压暗一层。"""
    d = pygame.Surface((W, H), pygame.SRCALPHA)
    d.fill((0, 0, 0, alpha))
    s.blit(d, (0, 0))


def draw_bg(s, tex, pos=(W * 0.5, H * 0.5), anchor=(0.5, 0.5), scale=1.0):
    """画一张居中背景图，返回屏幕矩形。"""
    im = _img(tex)
    if not im:
        return pygame.Rect(0, 0, 0, 0)
    w = int(im.get_width() * scale)
    h = int(im.get_height() * scale)
    if (w, h) != im.get_size():
        im = pygame.transform.smoothscale(im, (w, h))
    x = int(pos[0] - anchor[0] * w)
    y = int(H - pos[1] - (1.0 - anchor[1]) * h)
    s.blit(im, (x, y))
    return pygame.Rect(x, y, w, h)


def text(
    s,
    txt,
    pos,
    size=16,
    color=(255, 255, 255),
    anchor=(0.5, 0.5),
    bold=True,
    font_name="Microsoft YaHei",
):
    """按 cocos 坐标画文字。pos 是 cocos 坐标（y 向上）。"""
    f = pygame.font.SysFont(font_name, size, bold=bold)
    t = f.render(txt, True, color)
    x = int(pos[0] - anchor[0] * t.get_width())
    y = int(H - pos[1] - (1.0 - anchor[1]) * t.get_height())
    s.blit(t, (x, y))
    return pygame.Rect(x, y, t.get_width(), t.get_height())


# ---------------------------------------------------------------- 通用弹出动画
POP_TIME = 0.18
POP_FROM = 0.62
CLOSE_TIME = 0.12


def pop_scale(t):
    """0→1 弹出进度换成缩放（ease-out-back，负段夹掉）。"""
    if t >= POP_TIME:
        return 1.0
    k = max(0.0, t / POP_TIME)
    if k <= 0:
        return POP_FROM
    c1 = 1.70158
    c3 = c1 + 1.0
    e = c3 * k * k * k - c1 * k * k
    if e < 0:
        e = 0.0
    return POP_FROM + (1.0 - POP_FROM) * e


def draw_scaled(s, layer, scale):
    """把整层按 scale 居中贴回 s。scale≈1 时直接贴。"""
    if abs(scale - 1.0) < 0.002:
        s.blit(layer, (0, 0))
        return
    w = max(2, int(W * scale))
    h = max(2, int(H * scale))
    z = pygame.transform.smoothscale(layer, (w, h))
    s.blit(z, ((W - w) // 2, (H - h) // 2))
