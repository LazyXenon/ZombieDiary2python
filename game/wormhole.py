"""虫洞（传送门）—— 原版 BattleField::addWormholeEffect @0x16df74。

反编译（all_merged.c:8804）：
  容器节点 anchor(0.2, 0.5)，pos = (0, 屏幕高 * 0.42)
  子节点 1  pic/ui/battlefield/wormhole.png
            anchor(0.5, 0.5)，内容尺寸 = 贴图尺寸
            **RotateBy(0.5s, 450°) 循环**（一直在转）
            setOpacity(1053609165 = 0.2f)   ← 半透明
            setScale(0x40000000 = 2.0f)
  子节点 2  pic/ui/battlefield/wormhole_ring.png   anchor(0.5, 0.5)
            循环：FadeTo(255) + ScaleTo(0.6) → FadeOut(0.8) + ScaleTo(3.0)
            ⇒ 一圈扩散淡出的光环

★ 虫洞只在 **guard_mission**（守卫虫洞）任务里出现
  （all_merged.c:149594 —— LeakCounter 节点建好后就 addWormholeEffect）。
"""

import math

import pygame

from engine import res


WORMHOLE_TEX = "pic/ui/battlefield/wormhole.png"
RING_TEX = "pic/ui/battlefield/wormhole_ring.png"

SCALE = 0.62
WIDE = 0.58  # 横向系数（相对名义直径）
TALL = 1.65  # 纵向系数
OPACITY = 0.2
ROT_PERIOD = 0.5  # 秒 / 450°
ROT_DEG = 450.0
Y_RATIO = 0.42  # 屏幕高 * 0.42
X_ANCHOR = 0.2  # 容器 anchor(0.2, 0.5)

RING_PERIOD = 1.4  # 光环一轮的秒数


class Wormhole:
    """虫洞（守卫任务里的传送门）。"""

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.t = 0.0
        self.img = res.load_img(WORMHOLE_TEX)
        self.ring = res.load_img(RING_TEX)

    def update(self, dt):
        self.t += dt

    def draw(self, s):
        if self.img:
            d = self.img.get_width() * SCALE  # 名义直径
            w = max(8, int(d * WIDE))
            h = max(8, int(d * TALL))
            # RotateBy(0.5s, 450°) 先在正方形上转，转完再压成窄高椭圆，
            # 这样漩涡在门里转，门的轮廓是稳的（不会一帧宽一帧窄）。
            ang = (self.t / ROT_PERIOD) * ROT_DEG
            im = pygame.transform.rotate(self.img, -ang)
            im = pygame.transform.smoothscale(im, (w, h))
            im = im.copy()
            im.set_alpha(int(255 * OPACITY))
            # 旋转后的包围盒每帧都在变（450°/0.5s 转得很快），
            # 若用 im.get_size() 定位，整张图会持续「抖」。改用定时缩放后
            # 的 (w, h) 算中心点，再把结果按中心对齐。
            cx = self.x + (0.5 - X_ANCHOR) * w
            cy = self.y
            s.blit(im, (int(cx - w / 2), int(cy - h / 2)))
        if self.ring:
            # 光环：淡入 + 缩到 0.5 → 淡出 + 放大到 1.6，循环。
            # （原版 ScaleTo 3.0 是按原版光环贴图算的；这里的 ring 贴图
            #   128px，×3 会扩散到 384px，比虫洞本体大三四倍，糊满左半屏。）
            k = (self.t % RING_PERIOD) / RING_PERIOD
            if k < 0.42:
                a = int(255 * (k / 0.42))
                sc = 0.5 + (0.9 - 0.5) * (k / 0.42)
            else:
                k2 = (k - 0.42) / 0.58
                a = int(255 * (1.0 - k2))
                sc = 0.9 + (1.6 - 0.9) * k2
            # 光环也跟着压窄拉高，和门框同形，否则一圈圆环套一个窄椭圆很怪
            w = max(1, int(self.ring.get_width() * sc * 0.62))
            h = max(1, int(self.ring.get_height() * sc * 1.35))
            im = pygame.transform.smoothscale(self.ring, (w, h))
            im = im.copy()
            im.set_alpha(max(0, a))
            s.blit(im, (int(self.x - w / 2), int(self.y - h / 2)))
