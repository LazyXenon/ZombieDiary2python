"""击杀僵尸的赏金 —— 原版 KillBonusEffect。

反编译依据：
  * KillBonusEffect::getKillBonus @0x17ff90
      查 KillBonusDef 表（<zombie name=".." bonus="N" />），
      表里没有的名字**默认给 30**。
  * KillBonusEffect::onKillZombie @0x17ff90
      在僵尸死亡位置显示「+N」（金色 EzScoreText，getTexFont(1)=score_gold，
      scale 1.2），然后 MoveTo(0, 240) 2 秒 + FadeOut 2 秒飘上去消失。
  * BattleField::addCoinBonus @0x16f0ac
      给存档 user_coin 加 N、播星星特效
      （pic/effect/star/star_sheets.xml + star_animations.xml，scale 0.12）、
      播 sounds/coin_added.ogg。

数据源：assets/raw/level/zombie_bonus.xml
"""

import os

import pygame

from engine import res
from engine.skel import Skeleton


BONUS_XML = "level/zombie_bonus.xml"
DEFAULT_BONUS = 30  # 原版 getKillBonus 找不到时的默认值

STAR_SHEET = "pic/effect/star/star_sheets.xml"
STAR_ANIM = "pic/effect/star/star_animations.xml"
STAR_SCALE = 0.12  # 原版 setScale(0.12)
STAR_DX = -70.0 * 0.12  # 原版位置偏移 (-70, +95) × 0.12
STAR_DY = 95.0 * 0.12

_bonus_cache = None
_star_skel = None
_star_failed = False


def load_kill_bonus():
    """zombie_bonus.xml → {僵尸名: 赏金}。"""
    global _bonus_cache
    if _bonus_cache is not None:
        return _bonus_cache
    out = {}
    txt = res.load_xml(BONUS_XML)
    if txt:
        try:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(txt)
            for z in root.iter("zombie"):
                nm = z.get("name")
                if not nm:
                    continue
                try:
                    out[nm] = int(z.get("bonus", DEFAULT_BONUS))
                except (TypeError, ValueError):
                    out[nm] = DEFAULT_BONUS
        except Exception:
            pass
    _bonus_cache = out
    return out


def kill_bonus(zombie_name):
    """杀一只这种僵尸给多少金币（默认 30）。"""
    return load_kill_bonus().get(zombie_name, DEFAULT_BONUS)


def _star_skeleton():
    global _star_skel, _star_failed
    if _star_skel is None and not _star_failed:
        try:
            sk = Skeleton([STAR_SHEET], STAR_ANIM)
            if sk and sk.frame_count > 0:
                _star_skel = sk
            else:
                _star_failed = True
        except Exception:
            _star_failed = True
    return _star_skel


class StarPop:
    """击杀时冒出的星星（原版 addCoinBonus 的星星特效）。"""

    LIFE = 0.7

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        return self.t < self.LIFE

    def draw(self, s):
        sk = _star_skeleton()
        if sk is None:
            return
        k = min(1.0, self.t / self.LIFE)
        frame = int(k * (sk.frame_count - 1))
        sk.render(s, frame, int(self.x + STAR_DX), int(self.y - STAR_DY), STAR_SCALE, flip=False)


class KillBonusLayer:
    """战斗里的击杀赏金特效集合。"""

    def __init__(self):
        self.stars = []

    def add(self, x, y):
        self.stars.append(StarPop(x, y))

    def update(self, dt):
        self.stars = [s for s in self.stars if s.update(dt)]

    def draw(self, s):
        for st in self.stars:
            st.draw(s)

    def clear(self):
        self.stars.clear()
