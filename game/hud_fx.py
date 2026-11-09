"""战斗 HUD 特效 —— ComboKillEffect / KillCounter / KillBonusEffect。

全部几何与时长取自反编译：
  ComboKillEffect::init        @0x180bf0
  ComboKillEffect::onKillZombie@0x180b4c
  ComboKillEffect::addBonusEffect1 @0x18049c
  ComboKillEffect::addBonusEffect2 @0x180780
  ComboKillEffect::onWeaponFire@0x17ef04
  KillCounter::init            @0x181320

原版语义（逐条对上）：
  · combo.png 缩放 1.1，锚点 = 图宽高 * 0.5
  · 数字用 EzTexText(getTexFont(2))，锚点 (1.0, 0.0)，位置 (w*0.8, h)
  · 连击数 > 2 才显示；每次 +1 做 1.2 → 1.0 的 ScaleTo（各 0.1s）
  · 开火后 2.0s 无击杀 → clear（约掉 ComboKillEffect::onWeaponFire 的 DelayTime）
  · 超过 combo_max → clear
  · 奖励浮动字 "+N"：getTexFont(1)，锚点 (0, 0.5)，2.0s 上移到 240 LU 后淡出

坐标语义：雷击特效挂在 BattleField 上、位置按 s_fLogicUnitLen 算。
本机 LOGIC = 1.0（与 shop_character.CHAR_POS 一致），故 LU 数值直接当像素。
父节点位置：ComboKillEffect 挂在 (W*0.1, H*0.3)（cocos y，从 BattleField 底边算）。
"""

import math

import pygame

from engine import res
from engine.bmpfont import BitmapText


LOGIC = 1.0

# ComboKillEffect 在 BattleField 里的父位置（cocos y 向上）
PARENT_POS = (854 * 0.1, 480 * 0.3)
# 数字相对本节点的偏移（init 里 w*0.8, h）
NUM_ANCHOR = (0.8, 1.0)
# 开火后多久清连击（onWeaponFire 的 DelayTime 2.0f）
FIRE_CLEAR_DELAY = 2.0


# ComboKillDef 表（原版 ComboKillEffect::init @0x180bf0 / all_merged.c:14988）
# (连击数, 奖励金币, 横幅贴图)
COMBO_BONUS = (
    (5, 50, "pic/ui/battlefield/killing_spree.png"),
    (10, 50, "pic/ui/battlefield/dominating.png"),
    (20, 100, "pic/ui/battlefield/mega_kill.png"),
    (30, 150, "pic/ui/battlefield/unstoppedable.png"),
    (45, 200, "pic/ui/battlefield/wicked_sick.png"),
    (60, 250, "pic/ui/battlefield/ultra_kill.png"),
    (80, 300, "pic/ui/battlefield/monster_kill.png"),
    (100, 450, "pic/ui/battlefield/god_like.png"),
    (150, 700, "pic/ui/battlefield/holy_shit.png"),
)


def combo_bonus(combo):
    """连击数恰好达到某一档时返回 (金币, 横幅路径)，否则 None。

    原版 ComboKillEffect::addBonusEffect @0x182d80 反向遍历 9 个
    ComboKillDef，找**连击数恰好相等**的那一档 ⇒ 每档只在达到时发一次。
    """
    for need, coin, tex in COMBO_BONUS:
        if combo == need:
            return coin, tex
    return None


class ComboEffect:
    """连击数字。对应 ComboKillEffect。"""

    def __init__(self):
        self.sprite = res.load_img("pic/ui/battlefield/combo.png")
        self.count = 0
        self.scale = 1.0
        self.t = 0.0
        self.visible = False
        self.since_fire = 0.0
        self._anim_t = 0.0
        # 连击横幅（原版 addBonusEffect 播的那张图）
        self.banner = None
        self.banner_t = 0.0

    def reset(self):
        self.count = 0
        self.visible = False
        self.scale = 1.0
        self.since_fire = 0.0
        self.banner = None
        self.banner_t = 0.0

    def on_fire(self):
        """开火。原版：若当前可见，先清掉 2s 定时再重排。"""
        self.since_fire = 0.0
        if self.visible:
            # 重新计时（等价 stopActionByTag(100) + DelayTime(2.0) + clear）
            self.since_fire = 0.0

    def on_kill(self, max_combo=999):
        """连击 +1；恰好达到某一档时返回奖励金币数（否则 0）。"""
        if self.count >= max_combo:
            self.reset()
            return 0
        self.count += 1
        if self.count > max_combo:
            self.reset()
            return 0
        if self.count > 2:
            self.visible = True
            self.scale = 1.2
            self._anim_t = 0.1  # ScaleTo 1.2→1.0 各 0.1s
        # 恰好达到某一档 ⇒ 播横幅 + 发金币
        b = combo_bonus(self.count)
        if b:
            coin, tex = b
            img = res.load_img(tex)
            if img is not None:
                self.banner = img
                self.banner_t = 1.6
            return coin
        return 0

    def update(self, dt):
        if self.banner_t > 0:
            self.banner_t -= dt
            if self.banner_t <= 0:
                self.banner = None
        if self.visible:
            self.since_fire += dt
            if self.since_fire >= FIRE_CLEAR_DELAY:
                self.reset()
                return
            if self._anim_t > 0:
                self._anim_t -= dt
                p = 1.0 - max(0.0, self._anim_t) / 0.1
                self.scale = 1.2 + (1.0 - 1.2) * p

    def draw(self, s, design_h=480):
        # 连击横幅（原版 addBonusEffect 播的那张图）——
        # 原版将它放在 ComboKillEffect 节点下方、缓慢上移后消失。
        if self.banner is not None:
            bx, by = PARENT_POS
            k = 1.0 - self.banner_t / 1.6
            a = int(255 * min(1.0, (1.0 - k) * 3.0))
            if a > 0:
                im = self.banner.copy()
                im.fill((255, 255, 255, a), special_flags=pygame.BLEND_RGBA_MULT)
                y = int(design_h - (by - 40.0) - k * 30.0)
                s.blit(im, (int(bx - im.get_width() / 2), y - im.get_height()))
        if not self.visible or not self.sprite or self.count <= 2:
            return
        bx, by = PARENT_POS
        # 本节点锚点 (0.5, 0.5) → 左上角 = pos - 半宽高
        sw = self.sprite.get_width()
        sh = self.sprite.get_height()
        # 缩放作用于节点（含背景图与数字）
        dw, dh = int(sw * self.scale), int(sh * self.scale)
        # cocos: 节点左上角（局部 0,0 在 y=+h 处）
        left = bx - sw * 0.5
        top_c = by + sh * 0.5
        sx = left
        sy = design_h - top_c
        im = self.sprite
        if (dw, dh) != (sw, sh):
            im = pygame.transform.smoothscale(im, (dw, dh))
        s.blit(im, (int(sx), int(sy)))
        # 数字独立放在「连杀」左侧，避免叠住“杀”字笔画。
        nx = left - 5 * self.scale
        ny = design_h - (by - sh * 0.5)
        BitmapText(str(self.count), int(28 * self.scale), (255, 255, 255, 255)).draw(
            s, int(nx), int(ny), anchor=(1, 1)
        )


class BonusFloat:
    """ "+N" 奖励浮动字。对应 ComboKillEffect::addBonusEffect2。"""

    RISE = 240.0 * LOGIC  # 上移 240 LU
    LIFE = 2.0  # MoveTo / FadeOut 各 2.0s

    def __init__(self, text, x, y):
        self.text = str(text)
        self.x0 = x
        self.y0 = y
        self.t = 0.0
        self.dead = False

    def update(self, dt):
        self.t += dt
        if self.t >= self.LIFE:
            self.dead = True

    def draw(self, s, design_h=480):
        if self.dead:
            return
        p = min(1.0, self.t / self.LIFE)
        x = self.x0
        y = self.y0 + self.RISE * p  # cocos 上移
        a = int(255 * (1.0 - p))
        BitmapText(self.text, 24, (255, 220, 90, a)).draw(
            s, int(x), int(design_h - y), anchor=(0, 1)
        )


class HudFx:
    """战斗 HUD 特效总装。挂一个实例在 App 上。"""

    def __init__(self):
        self.combo = ComboEffect()
        self.floats = []
        self._last_kills = 0

    def reset(self):
        self.combo.reset()
        self.floats = []
        self._last_kills = 0

    def on_fire(self):
        self.combo.on_fire()

    def on_kill(self, kills_total, coin_bonus=0, max_combo=999):
        """连击 +1。返回本次获得的金币数（连击达标时发钱）。

        ComboKillEffect::addBonusEffect @0x182d80 逆向遍历 9 个 ComboKillDef，
        找**连击数恰好相等**的那一档 ⇒ 发金币 + 播横幅。
        """
        gained = self.combo.on_kill(max_combo)
        coin_bonus += gained or 0
        if coin_bonus > 0:
            bx, by = PARENT_POS
            self.floats.append(BonusFloat("+%d" % coin_bonus, bx, by + 270.0 * LOGIC))
        return gained or 0

    def add_kill_bonus_float(self, amount, x, y):
        """在僵尸死亡位置飘「+N」（原版 KillBonusEffect::onKillZombie）。

        原版：EzScoreText(getTexFont(1)=score_gold) scale 1.2，文本 "+N"，
        出现在僵尸位置，然后 MoveTo(0,240) 2 秒 + FadeOut 2 秒飘上去消失。
        """
        if amount <= 0:
            return
        self.floats.append(BonusFloat("+%d" % amount, x, y))

    def update(self, dt):
        self.combo.update(dt)
        for f in self.floats:
            f.update(dt)
        self.floats = [f for f in self.floats if not f.dead]

    def draw(self, s, design_h=480):
        for f in self.floats:
            f.draw(s, design_h)
        self.combo.draw(s, design_h)
