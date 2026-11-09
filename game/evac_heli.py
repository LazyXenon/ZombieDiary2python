"""护送关的撤离点 —— 直升机。

原版没有单独的「撤离点」贴图（pic/ui/battlefield/ 里只有医疗箱 / 虫洞），
但资源里有一架完整的直升机：`pic/mech/13/feiji01.png`（机甲 13 号就是
让玩家开直升机的那台），配合 `assets/raw/sounds/helicopter_fly.ogg`。
护送关的台词是「护送幸存者到 N 公里外的**撤离点**」，用医疗箱当终点

  儿童走到舱门 → 沿舱门方向平移 → 缩小并抬升 = 钻进机舱 → 播完才结算。
"""

import math

import pygame

from engine import res
from engine.skel import Skeleton


HELI_TEX = "pic/mech/13/feiji01.png"
RING_SHEET = "pic/effect/add_time/sheets.xml"
RING_ANIM = "pic/effect/add_time/animations.xml"

SCALE = 1.85
FPS = 20.0

# 舱门在图上的相对位置（0..1，左上角为原点）。feiji01.png 是 226×126，
# 机身下部那块深色开口在 x≈0.50、y≈0.88 处，就是幸存者钻进去的地方。
DOOR_U = 0.50
DOOR_V = 0.62

# 登机动画：走到舱门 0.55s + 钻进机舱 0.65s
BOARD_WALK = 0.55
BOARD_TOTAL = 1.20

_ring = None
_ring_failed = False


def _ring_skeleton():
    global _ring, _ring_failed
    if _ring is None and not _ring_failed:
        try:
            sk = Skeleton([RING_SHEET], RING_ANIM)
            if sk and sk.frame_count > 0:
                _ring = sk
            else:
                _ring_failed = True
        except Exception:
            _ring_failed = True
    return _ring


class EvacHeli:
    """直升机的位姿 + 登机点。x 是**世界坐标**（机身中心）。"""

    def __init__(self, x, ground_y):
        self.x = float(x)
        self.ground_y = float(ground_y)
        self.t = 0.0
        self.img = res.load_img(HELI_TEX)
        self.sk = _ring_skeleton()
        if self.img:
            self.w = int(self.img.get_width() * SCALE)
            self.h = int(self.img.get_height() * SCALE)
        else:
            self.w = self.h = 0

    # ---------------------------------------------------------- 几何
    @property
    def door_x(self):
        """舱门的世界 x（幸存者要走到这里）。"""
        return self.x + (DOOR_U - 0.5) * self.w

    @property
    def door_y(self):
        """舱门的屏幕 y（机身底边贴地后，按 DOOR_V 往上量）。"""
        return self.ground_y - (1.0 - DOOR_V) * self.h

    def update(self, dt):
        self.t += dt

    # ---------------------------------------------------------- 绘制
    def draw(self, s, cam=0.0):
        if not self.img:
            return
        sx = self.x - cam
        # 待机：轻微上下浮动（悬停感），1.6s 一个来回
        bob = math.sin(self.t * 3.9) * 3.0
        bx = int(sx - self.w / 2)
        by = int(self.ground_y - self.h + bob)
        # 光效（add_time 的循环光环）画在机身后面
        sk = self.sk
        if sk is not None:
            frame = int((self.t * FPS) % sk.frame_count)
            bb = getattr(sk, "bbox", None)
            half = ((bb[3] - bb[1]) * 0.5 * 0.9) if bb else 0.0
            sk.render(s, frame, int(sx), int(self.ground_y + half), 0.9, flip=False)
        im = self.img
        if self.w != im.get_width():
            im = pygame.transform.smoothscale(im, (self.w, self.h))
        # 机腹阴影
        sh = pygame.Surface((max(8, int(self.w * 0.7)), 10), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 70), sh.get_rect())
        s.blit(sh, (int(sx - self.w * 0.35), int(self.ground_y - 8)))
        s.blit(im, (bx, by))
