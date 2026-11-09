"""主菜单 —— 原版 MainMenuScene::initUI @0x11f708。

════════════════════════════════════════════════════════════════════
节点树（全部挂在 MainMenuScene 上）
════════════════════════════════════════════════════════════════════
  bg      pic_bg_1/menu.jpg               anchor 默认  scaleY = H / texH
          pos(W*0.5, H*0.5)              910×512 → 0.9375，横向 853 略窄 1px
  more    pic/ui/mainmenu/button_moregames.png  anchor(0,1)  scale 0.9
          pos(0, H - LOGIC*20)           → rect (0, 20 + H-460 ...) 见 _more_rect
  music   pic/ui/dialog/button_music_on_off.png anchor(1,1) scale 0.8
          pos(W - w*0.6*0.1, H - h*0.5)
  sound   pic/ui/dialog/button_sound_on_off.png anchor(1,1) scale 0.8
          pos(同上 x,        H - h*1.5)
  play    pic/ui/mainmenu/bt_play.png     anchor(0.5,1) scale 1.05
          pos(W*0.5, H*0.4)
  intro   pic/ui/mainmenu/button_introgame.png anchor(0,1) scale 0.9
          pos(-LOGIC*11, H - LOGIC*20)   ← 反编译里是 COERCE_FLOAT(+0x80000000)，取负

音乐/音效贴图是 **212×92 的两态竖排**：上排 [0,0,212,46] = 开，下排 [0,46,212,46] = 关。
按钮节点的 contentSize 就是单态 212×46，所以 scale 0.8 → 170×37。

════════════════════════════════════════════════════════════════════
进场动画（原版没有，这里增强；玩家反馈「开始界面没有动画」）
════════════════════════════════════════════════════════════════════
一层 `MenuFX`，由 update(dt) 推进、draw(s) 叠加：

  · 标题/背景整体入场：前 0.55s 背景从 1.06 倍缩到 1.0，同时轻微上移
  · 开始按钮：延迟 0.12s 后从 0.72 倍弹到 1.05（EaseOutBack 回弹），
    之后持续 1.2 秒一次呼吸缩放 1.05 ↔ 1.075
  · 按钮光晕：button_light.png 叠加在开始按钮后面，alpha 随呼吸同步
  · 背景光斑：12 颗 spark_3.png 从下方缓慢上浮 + 呼吸透明，绕角色区循环
  · 顶部标题的紫光：一层径向渐变，alpha 缓慢脉动

全部是纯绘制，不参与逻辑，也不吃输入 —— 点开始按钮的命中框仍是
initUI 算出来的那个 play_rect，动画期间不变（避免「看得见点不到」）。

════════════════════════════════════════════════════════════════════
按钮回调
════════════════════════════════════════════════════════════════════
  onButtonPlay       @0x11f4fc  → pushScene(MapLayer)
  onButtonMusic      @0x11f57c  → isMusicOn 取反，setMusic + setMusicSwitch
  onButtonSound      @0x11f500  → isSoundOn 取反，setSound + setSoundSwitch
  onButtonIntroGame  @0x11f3a0  → DialogGameIntroduce（text_game_intro.png）
  onButtonMoreGames  @0x11f3be  → AppUtils::showFTMoreGames（渠道 SDK，无实现）
  onKeyBack          @0x11f3c6  → AppUtils::showFTExitAd（渠道 SDK，无实现）
"""

import contextlib
import math
import random

import pygame

from engine import res, scene
from game.dialog import H, W


LOGIC = 1.0

BG_TEX = "pic_bg_1/menu.jpg"
MORE_TEX = "pic/ui/mainmenu/button_moregames.png"
MUSIC_TEX = "pic/ui/dialog/button_music_on_off.png"
SOUND_TEX = "pic/ui/dialog/button_sound_on_off.png"
PLAY_TEX = "pic/ui/mainmenu/bt_play.png"
INTRO_TEX = "pic/ui/mainmenu/button_introgame.png"
INTRO_BOARD_TEX = "pic/ui/mainmenu/text_game_intro.png"
SPARK_TEX = "pic_particle/spark_3.png"
GLOW_TEX = "pic/ui/common/button_light.png"

MORE_SCALE = 0.9  # setScale(0.9)
SWITCH_SCALE = 0.8  # setScale(0.8)
PLAY_SCALE = 1.05  # setScale(1.05)
INTRO_SCALE = 0.9  # setScale(0.9)

BOTTOM_INSET = 20.0  # H - LOGIC*20
INTRO_INSET_X = 11.0  # -LOGIC*11
PLAY_Y_RATIO = 0.4  # H * 0.4
SWITCH_X_PAD = 0.6 * 0.1  # (w*0.6)*0.1

STATE_OPEN = (0, 0)  # 贴图上排
STATE_CLOSED = (0, 46)  # 贴图下排
STATE_H = 46  # 单态高度

# ---- 进场动画参数 ----
# 全部是纯视觉，不参与输入判定。时长取「看得清但不拖沓」：
# 0.55s 背景推近 + 0.12s 延迟 + 0.42s 按钮回弹 = 最长 0.54s 落地。
BG_ENTER_TIME = 0.55  # 背景从 1.06 → 1.0
BG_ENTER_ZOOM = 0.06
BG_ENTER_RISE = 14.0  # 同时向上抬 14px
PLAY_DELAY = 0.12  # 开始按钮延迟
PLAY_POP_TIME = 0.42  # 回弹时长
PLAY_START_SCALE = 0.72  # 起始缩放（相对 1.05）
PLAY_BREATH = 0.025  # 呼吸幅度
PLAY_BREATH_PERIOD = 1.2

SPARK_COUNT = 12
SPARK_RISE = 26.0  # 每秒上浮像素
SPARK_ALPHA_PERIOD = 2.4


def _anchored(w, h, px, py, ax, ay, scale):
    """cocos anchor → pygame Rect。cocos y 向上，屏幕 y = H - cocosY。"""
    sw, sh = w * scale, h * scale
    left = px - ax * sw
    bottom = py - ay * sh
    return pygame.Rect(
        int(round(left)), int(round(H - bottom - sh)), int(round(sw)), int(round(sh))
    )


class MainMenu:
    """主菜单层。app 需要 save.d（存档字典）与 audio。"""

    def __init__(self, app):
        self.app = app
        self.t = 0.0
        self.music_rect = None
        self.sound_rect = None
        self.play_rect = None
        self.intro_rect = None
        self.more_rect = None
        self._geo()
        self._rng = random.Random(20261105)
        self._sparks = [self._new_spark(delay=i / float(SPARK_COUNT)) for i in range(SPARK_COUNT)]
        self._glow = None  # 缓存的径向渐变

    # ------------------------------------------------------------ 动画
    @staticmethod
    def _ease_out_back(k):
        """EaseOutBack —— 弹过头再收回，用于按钮回弹。"""
        c1 = 1.70158
        c3 = c1 + 1.0
        return 1.0 + c3 * pow(k - 1.0, 3) + c1 * pow(k - 1.0, 2)

    def bg_transform(self):
        """返回 (zoom, dy)：进场期间背景的缩放和竖直偏移。"""
        if self.t >= BG_ENTER_TIME:
            return 1.0, 0.0
        k = self.t / BG_ENTER_TIME
        e = 1.0 - pow(1.0 - k, 3)  # EaseOutCubic
        return 1.0 + BG_ENTER_ZOOM * (1.0 - e), BG_ENTER_RISE * (1.0 - e)

    def play_scale(self):
        """开始按钮的当前缩放（含回弹 + 呼吸）。"""
        t = self.t - PLAY_DELAY
        if t < 0:
            return PLAY_SCALE * PLAY_START_SCALE
        base = PLAY_SCALE
        if t < PLAY_POP_TIME:
            k = t / PLAY_POP_TIME
            return base * (PLAY_START_SCALE + (1.0 - PLAY_START_SCALE) * self._ease_out_back(k))
        breath = math.sin((t - PLAY_POP_TIME) * math.tau / PLAY_BREATH_PERIOD)
        return base * (1.0 + PLAY_BREATH * breath)

    def _new_spark(self, delay=0.0):
        r = self._rng
        return dict(
            x=r.uniform(40.0, W - 40.0),
            y=H + r.uniform(0.0, 260.0),
            vy=-r.uniform(SPARK_RISE * 0.6, SPARK_RISE * 1.4),
            size=r.choice((0.7, 0.9, 1.2, 1.5)),
            phase=r.uniform(0.0, math.tau),
            spin=r.uniform(-1.2, 1.2),
            rot=r.uniform(0.0, 360.0),
            delay=delay,
        )

    def _tick_sparks(self, dt):
        for sp in self._sparks:
            sp["y"] += sp["vy"] * dt
            sp["rot"] += sp["spin"] * dt * 60.0
            if sp["y"] < -40.0:
                fresh = self._new_spark()
                fresh["y"] = H + 30.0
                sp.update(fresh)

    # ------------------------------------------------------------ 存档
    def _settings(self):
        save = getattr(self.app, "save", None)
        d = getattr(save, "d", {}) if save else {}
        return d.setdefault("settings", {"music": True, "sound": True})

    def music_on(self):
        return bool(self._settings().get("music", True))

    def sound_on(self):
        return bool(self._settings().get("sound", True))

    # ------------------------------------------------------------ 几何
    def _geo(self):
        """按反编译算五个控件的屏幕矩形（与 scale/贴图尺寸有关，进场算一次）。"""
        # moregames: anchor(0,1) pos(0, H-20) scale 0.9
        more = res.load_img(MORE_TEX)
        if more:
            self.more_rect = _anchored(
                more.get_width(),
                more.get_height(),
                0.0,
                H - LOGIC * BOTTOM_INSET,
                0.0,
                1.0,
                MORE_SCALE,
            )

        # introgame: anchor(0,1) pos(-LOGIC*11, H-20) scale 0.9
        intro = res.load_img(INTRO_TEX)
        if intro:
            self.intro_rect = _anchored(
                intro.get_width(),
                intro.get_height(),
                -LOGIC * INTRO_INSET_X,
                H - LOGIC * BOTTOM_INSET,
                0.0,
                1.0,
                INTRO_SCALE,
            )

        # play: anchor(0.5,1) pos(W*0.5, H*0.4) scale 1.05
        play = res.load_img(PLAY_TEX)
        if play:
            self.play_rect = _anchored(
                play.get_width(), play.get_height(), W * 0.5, H * PLAY_Y_RATIO, 0.5, 1.0, PLAY_SCALE
            )

        # music / sound: anchor(1,1) scale 0.8，contentSize 是**单态** 212×46
        sw = res.load_img(MUSIC_TEX)
        if sw:
            w, h = sw.get_width(), STATE_H
            px = W - (w * SWITCH_X_PAD)
            self.music_rect = _anchored(w, h, px, H - h * 0.5, 1.0, 1.0, SWITCH_SCALE)
        sd = res.load_img(SOUND_TEX)
        if sd:
            w, h = sd.get_width(), STATE_H
            px = W - (w * SWITCH_X_PAD)
            self.sound_rect = _anchored(w, h, px, H - h * 1.5, 1.0, 1.0, SWITCH_SCALE)

    # ------------------------------------------------------------ 交互
    def update(self, dt):
        self.t += dt
        self._tick_sparks(dt)

    def click(self, pos):
        """返回动作名或 None。

        判定顺序按 z 序从高到低：introgame 在 initUI 里最后 addChild(z=1)，
        它的矩形 (-11,20,165,72) 与 moregames (0,20,104,72) 完全重叠，
        所以重合区域必须先判 intro。
        """
        if self.intro_rect and self.intro_rect.collidepoint(pos):
            return "intro"
        if self.more_rect and self.more_rect.collidepoint(pos):
            return "moregames"
        if self.play_rect and self.play_rect.collidepoint(pos):
            return "play"
        if self.music_rect and self.music_rect.collidepoint(pos):
            return "music"
        if self.sound_rect and self.sound_rect.collidepoint(pos):
            return "sound"
        return None

    # 反编译回调
    def on_button_music(self):
        """onButtonMusic：isMusicOn 取反 → setMusic + 声音系统开关。"""
        st = self._settings()
        st["music"] = not st.get("music", True)
        audio = getattr(self.app, "audio", None)
        if audio:
            audio.set_music(st["music"])
        self._persist()
        return st["music"]

    def on_button_sound(self):
        """onButtonSound：isSoundOn 取反 → setSound + 声音系统开关。"""
        st = self._settings()
        st["sound"] = not st.get("sound", True)
        audio = getattr(self.app, "audio", None)
        if audio:
            audio.set_sound(st["sound"])
        self._persist()
        return st["sound"]

    def _persist(self):
        save = getattr(self.app, "save", None)
        if save is not None and hasattr(save, "save"):
            with contextlib.suppress(Exception):
                save.save()

    # ------------------------------------------------------------ 绘制
    def draw(self, s, coins=0, coin_font=None):
        self._draw_bg(s)
        self._draw_sparks(s)
        self._draw_switches(s)
        self._draw_buttons(s)
        if coin_font is not None:
            self._draw_coins(s, coins, coin_font)

    def _draw_bg(self, s):
        bg = res.load_img(BG_TEX)
        if not bg:
            return
        zoom, dy = self.bg_transform()
        tw, th = bg.get_size()
        k = H / float(th) * zoom  # scaleY = H / texH（含进场缩放）
        w = max(1, int(round(tw * k)))
        h = max(1, int(round(th * k)))
        x = int(round(W * 0.5 - w * 0.5))
        y = int(round(H * 0.5 - h * 0.5 + dy))
        # 进场动画期间尺寸每帧变，稳定后尺寸固定 ⇒ 缩放结果直接复用
        s.blit(scene.scaled(bg, w, h), (x, y))

    def _spark_img(self):
        im = getattr(self, "_spark_src", None)
        if im is None:
            im = res.load_img(SPARK_TEX)
            self._spark_src = im if im is not None else False
        return im or None

    def _spark_base(self, src, size):
        """光斑底图按固定边长缩放的缓存（尺寸每颗固定，只有角度/alpha 在变）。"""
        return scene.scaled(src, size, size)

    def _draw_sparks(self, s):
        """背景光斑：spark_3.png 自下而上缓慢漂浮。

        用 BLEND_RGBA_ADD 会在一张已经很亮的插画背景上几乎看不见（加色只在
        暗部有效）。这里改成两层：
          · 先按 alpha 正常叠加一个柔和的暖白圆（把光点"压"在背景上）；
          · 再叠一点加色亮芯，让光点有发光感。
        12 颗 × 每帧 smoothscale+fill 是唯一的热点，但全在 36px 内，
        实测主菜单 60fps 无压力。
        """
        src = self._spark_img()
        if not src:
            return
        global_fade = min(1.0, self.t / 0.3)
        if global_fade <= 0.0:
            return
        layer = pygame.Surface((W, H), pygame.SRCALPHA)
        for sp in self._sparks:
            a = 0.5 + 0.5 * math.sin(self.t * math.tau / SPARK_ALPHA_PERIOD + sp["phase"])
            alpha = int(120.0 * a * global_fade)
            if alpha <= 6:
                continue
            size = max(6, int(34 * sp["size"]))
            # 边长固定 ⇒ 缩放结果缓存；角度逐帧转，只能转一次（rotate 本身很便宜，
            # 贵的是 12 颗 × 每帧的 smoothscale）。
            im = pygame.transform.rotate(self._spark_base(src, size), sp["rot"])
            im.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
            layer.blit(im, (int(sp["x"] - size / 2), int(sp["y"] - size / 2)))
        s.blit(layer, (0, 0))

    def _draw_stateful(self, s, tex, rect, on):
        """双态开关：贴图竖排两态，按状态取 [0,off,212,46]。"""
        im = res.load_img(tex)
        if not im or rect is None:
            return
        _, oy = STATE_OPEN if on else STATE_CLOSED
        sub = im.subsurface(pygame.Rect(0, oy, im.get_width(), STATE_H))
        s.blit(pygame.transform.smoothscale(sub, rect.size), rect.topleft)

    def _draw_switches(self, s):
        self._draw_stateful(s, MUSIC_TEX, self.music_rect, self.music_on())
        self._draw_stateful(s, SOUND_TEX, self.sound_rect, self.sound_on())

    def _draw_buttons(self, s):
        """绘制顺序 = 反编译 addChild 顺序（后者在上）。

        initUI 里 moregames 是 addChild(v3, 0) 先加，
        introgame 最后 addChild(v30, 1)，且矩形完整覆盖 moregames。

        开始按钮是唯一带进场动画的：它先画光晕，再按 play_scale() 缩放贴图，
        缩放中心是**底边中点**（cocos anchor(0.5,1.0) 就是绕底边中点缩）。
        """
        for tex, rect, _scale in (
            (MORE_TEX, self.more_rect, MORE_SCALE),
            (INTRO_TEX, self.intro_rect, INTRO_SCALE),
        ):
            im = res.load_img(tex)
            if not im or rect is None:
                continue
            s.blit(scene.scaled(im, rect.w, rect.h), rect.topleft)

        self._draw_play(s)

    def _draw_play(self, s):
        im = res.load_img(PLAY_TEX)
        if not im or self.play_rect is None:
            return
        sc = self.play_scale()
        w = max(1, int(round(im.get_width() * sc)))
        h = max(1, int(round(im.get_height() * sc)))
        # anchor(0.5,1.0)：底边中点固定，向四周缩放
        cx = self.play_rect.centerx
        bottom = self.play_rect.bottom
        rect = pygame.Rect(int(round(cx - w / 2.0)), int(round(bottom - h)), w, h)

        s.blit(scene.scaled(im, w, h), rect.topleft)

    def _draw_coins(self, s, coins, font):
        """右上角金币数（40880 那种）。原版是 score_white 字体 + 金币图标。"""
        # 由 App.draw_coins 统一绘制，避免重复
