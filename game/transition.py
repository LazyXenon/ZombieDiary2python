"""场景切换过场动画。

原版 cocos2d-x 的 replaceScene 是瞬切的，没有任何转场 —— 复刻里做了增强：
切场景时把旧画面快照下来，用 0.28 秒做「横向推移 + 淡出」，新场景
从反方向推进来。玩家点「开始战斗」不会硬跳一帧。

设计要点：
  · 快照只在 goto() 时拍一次，过渡期间不重绘旧场景（省性能）；
  · 过渡层盖在所有东西之上，但不吃点击（过渡期间 press/click 直接忽略）；
  · 过渡非常短（0.28s），不打断操作节奏，也不能让玩家以为卡住了。
"""

import pygame

from game.dialog import H, W


DURATION = 0.28  # 总时长
SLIDE_PX = 90  # 新场景推入的水平位移


class Transition:
    """一次过场。start(scene_frame) 拍快照，然后自己跑完。"""

    def __init__(self):
        self.t = 0.0
        self.old = None  # 旧画面快照
        self.active = False

    def start(self, frame):
        """用当前帧做旧画面快照，开始过渡。"""
        try:
            old = frame.copy()
            # 快照必须不透明：alpha=0 的空帧 blit 回去会全透明，露出纯黑。
            if old.get_flags() & pygame.SRCALPHA:
                old = old.convert()
            old.set_alpha(None)
            self.old = old
        except Exception:
            self.old = None
        self.t = 0.0
        self.active = True

    def update(self, dt):
        if not self.active:
            return
        self.t += dt
        if self.t >= DURATION:
            self.active = False
            self.old = None
            self.t = 0.0

    def blocks_input(self):
        return self.active

    def draw(self, s):
        """画在最终画面上：旧图淡出 + 整体轻微横移。"""
        if not self.active or self.old is None:
            return
        k = min(1.0, self.t / DURATION)
        # 缓出，末段快
        e = 1.0 - (1.0 - k) ** 2

        # 旧画面：向左滑出 + 淡出
        old = self.old
        a = int(255 * (1.0 - e))
        if a > 0:
            dx = int(-SLIDE_PX * e)
            try:
                old2 = old.copy()
                old2.set_alpha(a)
                s.blit(old2, (dx, 0))
            except Exception:
                pass

        # 新画面已经从下往上「浮」一点（在 render 里由 _scene_offset 提供），
        # 这里再补一层从黑到透明的压暗，避免生硬
        dark = int(90 * (1.0 - e))
        if dark > 0:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, dark))
            s.blit(veil, (0, 0))

    def scene_offset(self):
        """新场景相对最终位置的偏移（未偏移=0）。"""
        if not self.active or self.old is None:
            return 0, 0
        k = min(1.0, self.t / DURATION)
        e = 1.0 - (1.0 - k) ** 2
        return int(SLIDE_PX * (1.0 - e)), 0
