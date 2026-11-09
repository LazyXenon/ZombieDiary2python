"""远行任务的终点目标 —— 原版 BattleField::addDistanceTarget @0x16e13c。

反编译（all_merged.c:8882）：
  容器节点 this+112
  子节点 1  pic/ui/battlefield/medical_box.png（医疗箱 = 要送到的地方）
            anchor(0.5, 0.5)，pos = (a2 + a3, 屏幕高 * 0.54)
  子节点 2  骨骼动画 pic/effect/add_time/sheets.xml + animations.xml
            （动画 ring，21 帧，循环）
            startAnimation(loop=true)，setScale(0.8)
            pos = (容器宽 * 0.7, 60)

"""

import math

import pygame

from engine import res
from engine.skel import Skeleton


BOX_TEX = "pic/ui/battlefield/medical_box.png"
ADD_TIME_SHEET = "pic/effect/add_time/sheets.xml"
ADD_TIME_ANIM = "pic/effect/add_time/animations.xml"

RING_TEX = "pic/items/item_ring.png"
RING_FRAMES = 8
RING_COLS = 4
RING_CELL = 100
RING_SIZE = (168, 104)  # 比道具法阵大一号，终点要够醒目
RING_CYCLE = 1.6  # 8 帧一轮的秒数
_RING_CACHE = []

FX_SCALE = 0.8
FX_DX = 0.7  # × 容器宽
FX_DY = 60.0
BOX_Y_RATIO = 0.54  # × 屏幕高
FPS = 20.0

_skel = None
_skel_failed = False


def _skeleton():
    global _skel, _skel_failed
    if _skel is None and not _skel_failed:
        try:
            sk = Skeleton([ADD_TIME_SHEET], ADD_TIME_ANIM)
            if sk and sk.frame_count > 0:
                _skel = sk
            else:
                _skel_failed = True
        except Exception:
            _skel_failed = True
    return _skel


class DistanceTarget:
    """远行任务的终点：医疗箱 + 循环光效。"""

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.t = 0.0
        self.box = res.load_img(BOX_TEX)
        self.sk = _skeleton()

    def update(self, dt):
        self.t += dt

    def _ring(self):
        """8 帧法阵按展示尺寸预缩放好（只算一次，之后每帧 blit）。"""
        if not _RING_CACHE:
            sheet = res.load_img(RING_TEX)
            if not sheet:
                return None
            for f in range(RING_FRAMES):
                cell = sheet.subsurface(
                    (
                        (f % RING_COLS) * RING_CELL,
                        (f // RING_COLS) * RING_CELL,
                        RING_CELL,
                        RING_CELL,
                    )
                )
                _RING_CACHE.append(pygame.transform.smoothscale(cell, RING_SIZE))
        return _RING_CACHE

    def draw(self, s, cam=0.0):
        # 目标是**世界坐标**，屏幕上要减掉镜头偏移。
        sx = self.x - cam
        # 法阵贴在箱底的地面上，先画（被医疗箱压住一点边缘更自然），
        # 透明度缓慢呼吸，避免一直满亮晃眼。
        rings = self._ring()
        if rings:
            gy = self.y + (self.box.get_height() / 2 if self.box else 40.0)
            a = int(150 + 70 * math.sin(self.t * math.tau / 2.4))
            im = rings[int(self.t / RING_CYCLE * RING_FRAMES) % RING_FRAMES].copy()
            im.fill((255, 255, 255, max(0, min(255, a))), special_flags=pygame.BLEND_RGBA_MULT)
            # 法阵中心放在箱脚**前方**的地面上：太靠上会被医疗箱压住，
            # 只剩一团光看不见符文环（截图目检发现）。
            s.blit(im, (int(sx - RING_SIZE[0] / 2), int(gy - RING_SIZE[1] * 0.30)))
        # 医疗箱（anchor 0.5, 0.5）
        if self.box:
            s.blit(
                self.box,
                (int(sx - self.box.get_width() / 2), int(self.y - self.box.get_height() / 2)),
            )
        # 光效（骨骼动画 ring，循环）
        #   原版位置是相对「容器」的偏移（容器宽*0.7, 60），而本复刻没有
        #   那个容器节点 —— 直接把特效**居中**在医疗箱上，视觉等价。
        sk = self.sk
        if sk is not None:
            frame = int((self.t * FPS) % sk.frame_count)
            bb = getattr(sk, "bbox", None)
            half = 0.0
            if bb:
                half = (bb[3] - bb[1]) * 0.5 * FX_SCALE
            sk.render(s, frame, int(sx), int(self.y + half), FX_SCALE, flip=False)
