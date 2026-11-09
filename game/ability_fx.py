"""技能（道具）生效特效 —— 原版 pic/effect/ability/。

反编译依据：
  * RecoverHPAbility（治疗药水）@0x1a4214 / node @0x1a500c
      createAnimationDef("pic/effect/ability/sheets.xml",
                         "pic/effect/ability/animations.xml")
      startAnimation(..., false, 1.0, 1)   ← 播放**一次**
      setScale(0.7)
      位置 = (士兵局部中心x + 士兵宽*0.1, 士兵宽*0.5)
  * TemporaryAbility（护盾 / 加速 / 力量）@0x1a3ce0
      addAbilityStartEffect：同样播一次，位置同上
      addAbilityEffect：持续期间**循环**播放
      挂在机甲身上时额外再挂一个 scale 0.7 的副本

素材：pic/effect/ability/sheets.xml + animations.xml
      部件 light01（hp_light01.png，旋转上升的光团）
            light02（hp_light02.png，垂直光柱）
      动画 light0104，35 帧。

本模块只负责「看得见的那部分」：在士兵身上叠一层会动的光。
"""

import pygame

from engine.skel import Skeleton


ABILITY_SHEET = "pic/effect/ability/sheets.xml"
ABILITY_ANIM = "pic/effect/ability/animations.xml"

SCALE_ONCE = 0.7  # 触发瞬间播一次
SCALE_LOOP = 0.6  # 持续期间循环
LOOP_FPS = 20.0

_skel = None
_skel_failed = False
_layers = {}


def _layer(w, h):
    """按尺寸复用染色用的临时面，避免每帧重新分配。"""
    key = (w, h)
    lay = _layers.get(key)
    if lay is None:
        lay = pygame.Surface((w, h), pygame.SRCALPHA)
        if len(_layers) > 24:
            _layers.clear()
        _layers[key] = lay
    else:
        lay.fill((0, 0, 0, 0))
    return lay


def _skeleton():
    global _skel, _skel_failed
    if _skel is None and not _skel_failed:
        try:
            sk = Skeleton([ABILITY_SHEET], ABILITY_ANIM)
            if sk and sk.frame_count > 0:
                _skel = sk
            else:
                _skel_failed = True
        except Exception:
            _skel_failed = True
    return _skel


class AbilityFx:
    """一个技能特效实例。

    kind:
      "once" —— 触发瞬间播一遍（治疗药水）
      "loop" —— 持续期间循环（护盾 / 加速 / 力量）
    """

    def __init__(
        self,
        kind="once",
        duration=1.2,
        scale=None,
        offset_x=0.0,
        color=(190, 240, 255),
        ability=None,
    ):
        self.kind = kind
        self.t = 0.0
        self.duration = duration
        self.scale = scale if scale is not None else (SCALE_ONCE if kind == "once" else SCALE_LOOP)
        self.offset_x = offset_x
        self.color = color
        self.done = False
        self.ability = ability or (kind if kind not in {"once", "loop"} else None)
        self.icon_img = None
        if self.ability:
            from engine import res
            from game.battle_abilities import ability_icon

            self.icon_img = res.load_img(ability_icon(self.ability))

    def update(self, dt):
        self.t += dt
        if self.t >= self.duration:
            self.done = True
        return not self.done

    def draw(self, s, soldier_x, foot_y):
        """在士兵身上画特效。

        soldier_x / foot_y 是士兵在屏幕上的位置（脚底 y）。
        原版位置 = (士兵局部中心x + 宽*0.1, 宽*0.5)，这里按脚底往上取。
        """
        sk = _skeleton()
        if sk is None:
            return
        if self.kind == "once":
            # 35 帧 / 20fps ≈ 1.75s 播完；这里按 duration 缩放播放速度
            k = min(1.0, self.t / max(0.05, self.duration))
            frame = int(k * (sk.frame_count - 1))
        else:
            frame = int((self.t * LOOP_FPS) % sk.frame_count)
        x = soldier_x + self.offset_x
        y = foot_y
        # ★ Skeleton.render 把**包围盒中心**对齐 screen_x。
        #   这套特效的坐标是相对士兵原点的（x 范围 -102..32，中心在 -35），
        #   直接传士兵屏幕 x 会让光柱整体偏到左边 35*scale。
        #   这里把包围盒中心的偏移补回去，让特效以士兵原点为准。
        bb = getattr(sk, "bbox", None)
        if bb:
            cx_off = (bb[0] + bb[2]) * 0.5
            x = soldier_x + self.offset_x - cx_off * self.scale
        # 染色：素材本身是金色的，四类技能要一眼能分开
        #   （治疗=绿、护盾=蓝、加速=青、力量=橙）。
        #   先画到临时面再乘色，比逐帧改贴图便宜得多。
        if self.color is None:
            sk.render(s, frame, int(x), int(y), self.scale, flip=False)
            return
        # 只染特效覆盖到的小面：若每个特效都建整屏 Surface 再做全屏
        # BLEND_RGBA_MULT，每帧的分配与逐像素乘色就是卡顿主因。
        # 竖直锚点是**脚底**（Skeleton.render 把 ground_flash 贴 ground_y），
        # 所以窗口上沿要按「接地线到包围盒顶」的高度算，不能以 y 居中。
        pad = 24
        bw = (bb[2] - bb[0]) if bb else 160
        if bb:
            gf = sk.ground_flash if sk.ground_flash is not None else bb[3]
            up = max(0.0, gf - bb[1])
            down = max(0.0, bb[3] - gf)
        else:
            up, down = 200.0, 0.0
        w = int(bw * self.scale) + pad * 2
        h = int((up + down) * self.scale) + pad * 2
        left = int(x) - w // 2
        top = int(y - up * self.scale) - pad
        sl, st = max(0, left), max(0, top)
        sr = min(s.get_width(), left + w)
        sb = min(s.get_height(), top + h)
        if sr > sl and sb > st:
            lay = _layer(sr - sl, sb - st)
            sk.render(lay, frame, int(x) - sl, int(y) - st, self.scale, flip=False)
            lay.fill((*self.color, 255), special_flags=pygame.BLEND_RGBA_MULT)
            s.blit(lay, (sl, st))
        if self.icon_img is not None:
            # 共用原版光柱只负责能量感，官方图标明确道具身份。
            icon = pygame.transform.smoothscale(self.icon_img, (34, 34))
            s.blit(icon, (int(soldier_x - 17), int(foot_y - 174)))


class AbilityFxLayer:
    """战斗里的技能特效集合。"""

    def __init__(self):
        self.items = []

    def add(self, kind="once", duration=1.2, **kw):
        ability = kw.get("ability")
        if ability:
            self.items = [
                f
                for f in self.items
                if not (f.ability == ability and f.kind == kind)
            ]
        fx = AbilityFx(kind=kind, duration=duration, **kw)
        self.items.append(fx)
        return fx

    def update(self, dt):
        self.items = [f for f in self.items if f.update(dt)]

    def draw(self, s, soldier_x, foot_y):
        for f in self.items:
            f.draw(s, soldier_x, foot_y)

    def clear(self):
        self.items.clear()
