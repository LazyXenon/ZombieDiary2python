"""人质（护送对象）—— 原版 Hostage。

原版资源：
  pic/hostage/01/  lower_sheets.xml + upper_sheets.xml
                    walk_animations.xml（zuotui 29 帧）
                    stand_animations.xml（zuotui 16 帧）
                    tou.png / tou_hurt.png（头像，受伤时换成 tou_hurt）
  pic/hostage/02/  同上（第二个人质造型）
  pic/hostage/hostage_1_sit.png / hostage_2_sit.png（被救后坐下的姿势）
  pic/hostage/hp_bar_0.png / hp_bar_1.png（血条）

  终点目标贴图，跟人质完全没关系。玩家在护送关里根本看不到要护送的人
"""

import random

import pygame

from engine import res
from engine.skel import Skeleton


HOSTAGE_DIRS = ("pic/hostage/01/", "pic/hostage/02/")
SIT_TEX = ("pic/hostage/hostage_1_sit.png", "pic/hostage/hostage_2_sit.png")
HP_BAR = ("pic/hostage/hp_bar_0.png", "pic/hostage/hp_bar_1.png")

SCALE = 1.0
FPS = 20.0

_cache = {}


def _skeleton(idx):
    """人质骨骼。idx = 0 / 1（hostage_1 / hostage_2）。"""
    if idx in _cache:
        return _cache[idx]
    sk = None
    base = HOSTAGE_DIRS[idx % len(HOSTAGE_DIRS)]
    try:
        sk = Skeleton(
            [base + "lower_sheets.xml", base + "upper_sheets.xml"], base + "walk_animations.xml"
        )
        if sk and (sk.frame_count <= 0 or not sk.images):
            sk = None
    except Exception:
        sk = None
    if sk is None:
        try:
            sk = Skeleton([base + "lower_sheets.xml"], base + "stand_animations.xml")
        except Exception:
            sk = None
    _cache[idx] = sk
    return sk


def _stand_skeleton(idx):
    """站立骨骼（跟走用同一套贴图，只换动画）。"""
    key = ("stand", idx)
    if key in _cache:
        return _cache[key]
    base = HOSTAGE_DIRS[idx % len(HOSTAGE_DIRS)]
    try:
        sk = Skeleton(
            [base + "lower_sheets.xml", base + "upper_sheets.xml"], base + "stand_animations.xml"
        )
    except Exception:
        sk = None
    _cache[key] = sk
    return sk


class HostageSprite:
    """一个人质的渲染状态。"""

    def __init__(self, idx=0):
        self.idx = idx % 2
        self.walk = _skeleton(self.idx)
        self.stand = _stand_skeleton(self.idx)
        self.sit = res.load_img(SIT_TEX[self.idx])
        self.bar_bg = res.load_img(HP_BAR[0])
        self.bar_fg = res.load_img(HP_BAR[1])

    def draw(self, s, x, ground_y, hp=1.0, moving=False, saved=False, scale=SCALE, t=0.0):
        """画人质。

        x       屏幕 x（脚底中心）
        ground_y 脚底线
        hp       0..1 血量比例
        moving   是否在走路
        saved    是否已被救（坐下）
        """
        if saved:
            if self.sit:
                w = int(self.sit.get_width() * scale)
                h = int(self.sit.get_height() * scale)
                s.blit(
                    pygame.transform.smoothscale(self.sit, (w, h)),
                    (int(x - w / 2), int(ground_y - h)),
                )
            return
        sk = self.walk if moving else (self.stand or self.walk)
        if sk is None or sk.frame_count <= 0:
            return
        frame = int((t * FPS) % sk.frame_count)
        sk.render(s, frame, int(x), int(ground_y), scale, flip=False)
        # 血条：原版 Hostage 头顶挂 hp_bar_0/1
        if self.bar_bg and self.bar_fg and 0.0 <= hp < 1.0:
            bw = int(self.bar_bg.get_width() * 0.8)
            bh = int(self.bar_bg.get_height() * 0.8)
            bx = int(x - bw / 2)
            by = int(ground_y - 250)
            s.blit(pygame.transform.smoothscale(self.bar_bg, (bw, bh)), (bx, by))
            fw = int(bw * max(0.0, min(1.0, hp)))
            if fw > 0:
                fg = pygame.transform.smoothscale(self.bar_fg, (fw, bh))
                s.blit(fg, (bx, by))
