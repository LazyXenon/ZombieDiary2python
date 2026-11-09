"""全键盘导航：方向键在界面控件之间移动焦点，回车 / 空格触发。

设计（为什么这样做）：
  * 不复刻「每个控件自己实现键盘交互」——那样要改十几个类，且很容易
    和鼠标逻辑走岔。这里只维护一份**可点矩形清单**，回车时把焦点矩形
    的中心喂给现成的 `App.click(pos)`，于是音效、冷却、二次确认、购买
    失败提示全部原样复用，键盘和鼠标走的是同一条代码路径。
  * 矩形清单由 `app/key_items.py` 按界面收集（各界面本来就有 rect 字段，
    是绘制时算出来的），没有列进清单的界面就没有键盘导航，不会误伤。
"""

import pygame


# 焦点框颜色：金色，和游戏 UI 的高亮一致
FOCUS_COLOR = (255, 226, 120)

# 操作提示：只有「刚用键盘接管」的那几秒才显示，之后自动淡出 ——
# 一直挂着会挡住商店底部卡片和地图任务点。
HINT_TEXT = "方向键 选择 · 回车 确认 · Tab 切换"
HINT_TIME = 4.0  # 焦点建立后显示多久
_HINT_FONT = None


def _hint_font():
    global _HINT_FONT
    if _HINT_FONT is None:
        _HINT_FONT = pygame.font.SysFont("Microsoft YaHei", 15, bold=True)
    return _HINT_FONT


def as_rect(r):
    """把 Rect / 四元组 / None 统一成 pygame.Rect（无效则 None）。

    MapPoint.rect 返回的是 `(x0, y0, x1, y1)` 四元组，其它界面多是
    pygame.Rect —— 这里两种都吃，免得每个收集点各写一遍转换。
    """
    if r is None:
        return None
    if isinstance(r, pygame.Rect):
        return r if r.w > 0 and r.h > 0 else None
    # 界面里的 rects 容器有各种形状：(x0,y0,x1,y1) / [rect, idx] /
    # 甚至 (rect, kind, keys)。只要是「四个数」就当矩形，其余一律丢弃，
    # 绝不让一个畸形元素把整帧渲染搞崩（这里用宽 except 兜底）。
    try:
        x0, y0, x1, y1 = r
        box = pygame.Rect(int(x0), int(y0), int(x1 - x0), int(y1 - y0))
    except Exception:
        return None
    return box if box.w > 0 and box.h > 0 else None


class KeyNav:
    """焦点管理：只管「现在选中哪个矩形」+「框画在哪」。"""

    def __init__(self):
        self.items = []  # [(pygame.Rect, label)]
        self.idx = -1
        self.t = 0.0
        self._sig = None  # 界面签名：界面变了就重置焦点
        self.hint_t = 0.0  # 焦点建立后的计时（控制操作提示淡出）

    # ---------------------------------------------------------- 同步

    def clear(self):
        """丢掉焦点（玩家改用鼠标时调用，焦点框随之消失）。"""
        self.idx = -1
        self.hint_t = 0.0

    def set_items(self, items, sig=None):
        """更新候选清单。sig 变化（换界面）时把焦点清掉。"""
        if sig is not None and sig != self._sig:
            self._sig = sig
            self.idx = -1
            self.hint_t = 0.0
        out = []
        for it in items or ():
            if isinstance(it, (tuple, list)) and len(it) == 2:
                rect, label = it
            else:
                rect, label = it, ""
            r = as_rect(rect)
            if r is not None:
                out.append((r, label))
        self.items = out
        if not out:
            self.idx = -1
        elif self.idx >= len(out):
            self.idx = len(out) - 1
        return out

    def current(self):
        if 0 <= self.idx < len(self.items):
            return self.items[self.idx]
        return None

    def current_rect(self):
        cur = self.current()
        return cur[0] if cur else None

    # ---------------------------------------------------------- 移动

    def move(self, dx, dy):
        """朝 (dx, dy) 方向找最近的一个候选。返回是否有变化。"""
        if not self.items:
            return False
        if self.idx < 0:
            # 还没有焦点：落在最靠左上的一项（视觉上最自然）
            self.idx = min(
                range(len(self.items)), key=lambda i: (self.items[i][0].y, self.items[i][0].x)
            )
            return True
        cx, cy = self.items[self.idx][0].center
        best, best_score = None, None
        for i, (r, _label) in enumerate(self.items):
            if i == self.idx:
                continue
            vx = r.centerx - cx
            vy = r.centery - cy
            along = vx * dx + vy * dy
            if along <= 0:
                continue
            # 垂直偏移的惩罚系数：优先同一行 / 同一列，避免斜着乱跳
            across = abs(vx * dy) + abs(vy * dx)
            score = along + across * 2.5
            if best_score is None or score < best_score:
                best, best_score = i, score
        if best is None:
            return False
        self.idx = best
        return True

    def step_next(self, step=1):
        """Tab / Shift+Tab：按清单顺序轮换。"""
        if not self.items:
            return False
        if self.idx < 0:
            self.idx = 0
        else:
            self.idx = (self.idx + step) % len(self.items)
        return True

    # ---------------------------------------------------------- 绘制

    def update(self, dt):
        self.t += dt
        if self.idx >= 0:
            self.hint_t += dt

    def draw(self, s):
        r = self.current_rect()
        if r is None:
            return
        # 呼吸：0.9s 一个来回，1.0 → 0.55 透明度
        k = abs(((self.t * 2.2) % 2.0) - 1.0)
        a = int(90 + 120 * (1.0 - abs(k - 0.5) * 2.0 * 0.5))
        pad = 3
        rr = r.inflate(pad * 2, pad * 2)
        layer = pygame.Surface((rr.w, rr.h), pygame.SRCALPHA)
        rad = max(4, min(12, rr.h // 4))
        # 外圈柔光 + 内圈实线，缩到 1px 也能看清
        pygame.draw.rect(
            layer,
            (*FOCUS_COLOR, max(24, a // 3)),
            pygame.Rect(0, 0, rr.w, rr.h),
            4,
            border_radius=rad,
        )
        pygame.draw.rect(
            layer, (*FOCUS_COLOR, a), pygame.Rect(1, 1, rr.w - 2, rr.h - 2), 2, border_radius=rad
        )
        s.blit(layer, rr.topleft)
        self._draw_hint(s)

    def _draw_hint(self, s):
        """底部操作提示：只在刚接管键盘的几秒里出现。"""
        if self.hint_t >= HINT_TIME:
            return
        # 淡入 0.15s / 淡出最后 0.6s
        fade_in = min(1.0, self.hint_t / 0.15)
        fade_out = min(1.0, max(0.0, (HINT_TIME - self.hint_t) / 0.6))
        k = min(fade_in, fade_out)
        if k <= 0.02:
            return
        # 字号缓存返回的是共享 Surface，改 alpha 前必须先 copy
        txt = _hint_font().render(HINT_TEXT, True, (255, 236, 190)).copy()
        pad_x, pad_y = 14, 6
        w = txt.get_width() + pad_x * 2
        h = txt.get_height() + pad_y * 2
        x = (s.get_width() - w) // 2
        y = s.get_height() - h - 16
        pill = pygame.Surface((w, h), pygame.SRCALPHA)
        rad = h // 2
        pygame.draw.rect(
            pill, (18, 14, 26, int(150 * k)), pygame.Rect(0, 0, w, h), border_radius=rad
        )
        pygame.draw.rect(
            pill, (*FOCUS_COLOR, int(90 * k)), pygame.Rect(0, 0, w, h), 1, border_radius=rad
        )
        txt.set_alpha(int(255 * k))
        pill.blit(txt, (pad_x, pad_y))
        s.blit(pill, (x, y))
