"""战斗中的召唤物：机甲（CallMechAbility）与飞行武器（FlyWeaponAbility）。

反编译依据：
  CallMechAbility::onMechLanding  @0x1a3f5c
      落地动画 + 爆炸 + Soldier::killZombiesOnExplosion
      之后 Soldier::onMechGetup → 士兵换成机甲形态（change2MechHead 换头像）
  BattleField::createFlyWeapon    @0x16e0a4
      FlyWeapon::node(name) → FlyWeapon::flyIn() → addChild(z=2)
      飞行武器从屏幕右侧飞进来，悬在士兵旁边持续射击
  FlyWeaponAbility::onAction      @0x1a45dc
      createFlyWeapon 后 DelayTime(持续秒 + 0.5) 再 onFlyOver（移除）

本模块只负责「看得见的那部分」：
  · 机甲：站在士兵左侧，播放 stand/walk/fire，自己开火
  · 飞行武器：从右边飞入，悬停在士兵头顶偏右，自己开火
"""

import contextlib
import math
import xml.etree.ElementTree as ET

import pygame

from engine import res
from engine.skel import Skeleton, parse_sheet


# 机甲名 → config/mech/<NN>/ 目录号。
#   原版每台机甲是**多层叠加**：
#     weapon/mech_9.xml 的 <Flash> 列表写死 z2=upper_b / z4=upper_c / z6=upper_f
#     / z3=lower_b / z5=lower_f
#   SoldierCharacter::init @0x18d504 逐条 initFromDef，把每个 <Flash> 生成
#   一个独立的 F2CAnimation 挂到各自的 zorder 上。
#   只加载 _b ⇒ mech_9 只剩一个脑袋（部件名对不上），mech_1 丢头/身/右臂
MECH_SKEL = {
    "mech_1": "01",
    "mech_3": "03",
    "mech_4": "04",
    "mech_5": "05",
    "mech_7": "07",
    "mech_8": "08",
    "mech_9": "09",
    "mech_10": "10",
}

FLY_SKEL = {
    "fly_1": "11",
    "fly_2": "12",
}

# ★ 机甲和飞行武器共用一套装配逻辑（都是 weapon/<name>.xml 的 <Flash> 列表），
#   这里合成一张表给 _mech_state_skeleton 用。
_ALL_SKEL = dict(MECH_SKEL)
_ALL_SKEL.update(FLY_SKEL)

MECH_SCALE = 0.62  # 机甲比士兵大一点，但别顶满屏
MECH_FORM_SCALE = 0.78  # 机甲形态（士兵换装）相对士兵骨骼的比例
MECH_OFFSET_X = -150.0  # 站在士兵左边（createAttackWeapon 的 -150）
MECH_FIRE_INTERVAL = 0.45
MECH_RANGE = 900.0
# stand 只有 19 帧 ⇒ 一秒才换 19 张图，看上是「幻灯片」。
# 提到 30fps 后同样 19 帧循环 0.63 秒，动作连续得多。
MECH_ANIM_FPS = 30.0

MECH_ACTOR_H = {
    "mech_1": 350,
    "mech_3": 350,
    "mech_4": 350,
    "mech_5": 267,
    "mech_8": 310,
    "mech_9": 310,
    "mech_10": 310,
}
MECH_FIRE_DUR = {
    "mech_1": 0.40,
    "mech_3": 0.25,
    "mech_4": 0.50,
    "mech_5": 0.25,
    "mech_8": 1.30,
    "mech_9": 1.30,
    "mech_10": 0.80,
}


def mech_form_scale(name):
    """机甲绘制系数：按画布高归一到 350，保证屏幕上高矮一致。"""
    h = MECH_ACTOR_H.get(name, 350)
    return MECH_FORM_SCALE * 350.0 / float(h or 350)


def mech_fire_interval(name):
    """机甲开火间隔（秒），来自 mech_actors.xml 的 fire duration。"""
    return float(MECH_FIRE_DUR.get(name, MECH_FIRE_INTERVAL))


FLY_SCALE = 0.9
FLY_HOVER_DX = 70.0  # 悬停在士兵右上方
FLY_HOVER_DY = 190.0
FLY_FIRE_INTERVAL = 0.22
FLY_RANGE = 900.0
FLY_ENTER_TIME = 0.6  # 飞入时间

_skel_cache = {}
_flash_cache = {}


def mech_flash_layers(name, state):
    key = (name, state)
    if key in _flash_cache:
        return _flash_cache[key]
    out = []
    txt = res.load_xml("weapon/%s.xml" % name)
    if txt:
        try:
            root = ET.fromstring(txt)
        except ET.ParseError:
            root = None
        if root is not None:
            wanted = state + "_"
            for an in root.iter("animation"):
                if not (an.get("name") or "").startswith(wanted):
                    continue
                for fl in an.iter("Flash"):
                    sx = fl.get("sheet_xml")
                    ax = fl.get("animatioin_xml")  # 原版就是这个拼写（少个 i）
                    zo = int(float(fl.get("zorder") or 0))
                    if sx and ax:
                        out.append((sx, ax, zo))
                # 不 break：同一状态还有 <state>_lower（腿），要一起收齐
    out.sort(key=lambda t: t[2])
    _flash_cache[key] = out
    return out


def _layer_parts(layers):
    """[(sheet, anim, zorder)] → (去重 sheets, 去重 anims)，保持 zorder 顺序。"""
    sheets, anims = [], []
    for sx, ax, _zo in layers:
        if sx not in sheets:
            sheets.append(sx)
        if ax not in anims:
            anims.append(ax)
    return sheets, anims


def _lower_leg_spec(name, state_sheets):
    """给只列 *_upper 的状态（fire）补回 stand/walk 的腿层。

    weapon/mech_N.xml 的 fire 段通常只有 fire_upper，腿层只写在 stand/walk
    缩到 290.5 —— 开火瞬间腿消失、整个人上跳 56px。

    返回 (额外 sheets, 腿部件名, 腿动画 xml)。腿部件名是从补进来的
    lower sheets 里读出来的，交给 Skeleton 的 (anim, names) 源，让腿沿用
    站立帧、上半身继续用 fire 帧。
    """
    for base_state in ("stand", "walk"):
        layers = mech_flash_layers(name, base_state)
        if not layers:
            continue
        sheets, anims = _layer_parts(layers)
        extra = [s for s in sheets if s not in state_sheets]
        if not extra or not anims:
            continue
        leg_names = set()
        for sx in extra:
            txt = res.load_xml(sx)
            if txt:
                with contextlib.suppress(ET.ParseError):
                    leg_names |= set(parse_sheet(txt).keys())
        if leg_names:
            return extra, leg_names, anims[0]
    return [], set(), None


def _merged_skeleton(sheet_xmls, anim_xml):
    try:
        sk = Skeleton(list(sheet_xmls), anim_xml)
    except Exception:
        return None
    if sk is None or sk.frame_count <= 0 or not sk.bbox:
        return None
    return sk


def _mech_skeleton(name):
    if name in _skel_cache:
        return _skel_cache[name]
    nn = MECH_SKEL.get(name)
    sk = None
    if nn:
        # 优先走原版 Flash 列表（完整装配）
        for state in ("stand", "walk", "fire"):
            layers = mech_flash_layers(name, state)
            if not layers:
                continue
            sheets, anims = _layer_parts(layers)
            sk = _merged_skeleton(sheets, list(anims))
            if sk is not None:
                break
        # 兜底：目录里的 sheets.xml（只有极少数机体缺 weapon XML 时才会走到）
        if sk is None:
            base = "config/mech/%s/" % nn
            for sh, an in (
                ([base + "sheets.xml"], base + "stand_animations.xml"),
                (
                    [base + "upper_sheets.xml", base + "lower_sheets.xml"],
                    base + "stand_animations.xml",
                ),
            ):
                sk = _merged_skeleton(sh, an)
                if sk is not None:
                    break
    _skel_cache[name] = sk
    return sk


def _mech_state_skeleton(name, state):
    # 机甲某个状态（stand / walk / fire）的骨骼。
    # 原版机甲是士兵换装（Soldier::onMechGetup @0x187534），玩家照常
    # 左右移动 + 开火，只是外观换成机甲骨骼。装配方式见 mech_flash_layers：
    # 读 weapon/mech_N.xml 的 <Flash> 列表，把所有 sheet 层合并成完整机体。
    # ★ fire 段只有 fire_upper：腿层要从 stand/walk 的 *_lower 补进来，
    #   并且所有状态共用 stand 的 bbox / 脚底基准，否则切到开火那一帧
    #   腿没了、整个人还会往上跳几十像素。
    key = "__mechstate_%s_%s" % (name, state)
    if key in _skel_cache:
        return _skel_cache[key]
    sk = None
    nn = _ALL_SKEL.get(name)
    if nn:
        layers = mech_flash_layers(name, state)
        if not layers and state != "stand":
            layers = mech_flash_layers(name, "stand")
        if layers:
            sheets, anims = _layer_parts(layers)
            anim_specs = list(anims)
            if state != "stand":
                extra, leg_names, leg_anim = _lower_leg_spec(name, sheets)
                if extra and leg_names and leg_anim:
                    sheets = sheets + extra
                    # (anim, 部件名) 源只覆盖腿：上半身仍用本状态的帧
                    anim_specs = [*anim_specs, (leg_anim, leg_names)]
            sk = _merged_skeleton(sheets, anim_specs)
        # 兜底：目录里的 sheets.xml
        if sk is None:
            base = "config/mech/%s/" % nn
            for sh, an in (
                ([base + "sheets.xml"], base + "stand_animations.xml"),
                (
                    [base + "upper_sheets.xml", base + "lower_sheets.xml"],
                    base + "stand_animations.xml",
                ),
            ):
                sk = _merged_skeleton(sh, an)
                if sk is not None:
                    break
        # 共用 stand 基准（stand 自己是基准，不递归）
        if sk is not None and state != "stand":
            stand_sk = _mech_state_skeleton(name, "stand")
            if stand_sk is not None:
                sk.set_bbox(stand_sk.bbox)
                sk.set_ground(stand_sk.ground_flash)
    _skel_cache[key] = sk
    return sk


def _fly_skeleton(name):
    return _mech_state_skeleton(name, "stand")


def mech_fx_bbox(name):
    """供开火特效换算用的机甲骨骼包围盒（stand/fire 已共用一份基准）。"""
    sk = _mech_state_skeleton(name, "stand")
    return sk.bbox if sk is not None else None


_PILOT_CACHE = {}


# 挂在头上的部件前缀（不属于「身体」也不属于「手里的武器」）。
# girl_02 的头发本体分在 bian01 / bian02 两个部件里，tou.png 只是一颗短发脑袋。
HEAD_EXTRA_PREFIX = ("bian",)


def _head_composite(sk, with_body=True):
    """把 tou 和头上配件（马尾 bian01/bian02 等）合成一张紧凑贴图。

    ★ 原版驾驶舱里的头是 SoldierCharacter 整个头（含发型），早先这里只
      取 sk.images["tou"] —— girl_02 的马尾在马尾部件里，于是驾驶舱里只剩
      会丢掉挂在头上的东西。
      这里直接让骨骼把这几个部件按真实旋转/层级画到临时画布上，再裁到
      非透明区域，得到「头 + 马尾」的完整贴图。
    """
    names = [nm for nm in sk.parts if nm == "tou" or nm.startswith(HEAD_EXTRA_PREFIX)]
    if with_body and "qungan" in sk.parts:
        names.append("qungan")
    if "tou" not in names or not sk.bbox:
        return None
    min_x, min_y, max_x, max_y = sk.bbox
    cw = int(max_x - min_x) + 8
    ch = int(max_y - min_y) + 8
    if cw <= 0 or ch <= 0:
        return None
    canvas = pygame.Surface((cw, ch), pygame.SRCALPHA)
    gf = sk.ground_flash if sk.ground_flash is not None else max_y
    # 让 bbox 左上角落在画布 (4,4)：屏幕 y = ground_y - (gf - flash_y)
    cx = cw / 2.0
    gy = 4 + gf - min_y
    try:
        sk.render(canvas, 0, cx, gy, 1.0, only=set(names))
    except Exception:
        return None
    box = canvas.get_bounding_rect()
    if box.width <= 0 or box.height <= 0:
        return None
    out = pygame.Surface((box.width, box.height), pygame.SRCALPHA)
    out.blit(canvas, (0, 0), box)
    return out


def _pilot_head(soldier, look):
    """取当前角色（玩家自己）的头部贴图 —— 塞进机甲驾驶舱用。

    优先用「头 + 头上配件」的合成图；合成失败再退回单张 tou。
    """
    key = (soldier, look)
    if key in _PILOT_CACHE:
        return _PILOT_CACHE[key]
    img = None
    try:
        from game import soldier_sprite as ss

        sp = ss.get("p220", soldier, look)
        sk = sp.anims.get("stand") or next(iter(sp.anims.values()))
        img = _head_composite(sk) or (sk.images or {}).get("tou")
    except Exception:
        img = None
    _PILOT_CACHE[key] = img
    return img


def _fit_img(img, w, h, dx=0.0, dy=0.0, k_scale=1.0):
    """等比缩放并居中到 w×h 的透明画布（dx/dy 是额外像素偏移）。"""
    try:
        iw, ih = img.get_size()
    except Exception:
        return None
    if iw <= 0 or ih <= 0:
        return None
    k = min(w / float(iw), h / float(ih)) * k_scale
    nw, nh = max(1, int(iw * k)), max(1, int(ih * k))
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    out.blit(
        pygame.transform.smoothscale(img, (nw, nh)),
        (int((w - nw) / 2 + dx), int((h - nh) / 2 + dy)),
    )
    return out


class MechForm:
    """玩家操控的机甲形态（替代 SoldierSprite 用于渲染）。

    只提供和 SoldierSprite 一样的 render/draw_shadow 接口，
    逻辑（移动、开火、受伤）全部还走 Battle，玩家完全操控。
    """

    def __init__(self, name, soldier=None, look=0):
        self.name = name
        self.sk = {}
        for st in ("stand", "walk", "fire"):
            self.sk[st] = _mech_state_skeleton(name, st)
        # ★ 美洲狮（mech_3）是**骑乘**机甲：ren 部件在机体上方，要把玩家画回去。
        #   其余机甲仍是变形形态，ren 保持全透明占位。
        self._has_rider = name == "mech_3"
        for sk in self.sk.values():
            if sk is None or sk.images.get("ren") is None:
                continue
            if self._has_rider:
                continue
            w, h = sk.images["ren"].get_size()
            sk.images["ren"] = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
        if self._has_rider:
            self.set_pilot(soldier, look)

    def set_pilot(self, soldier=None, look=0):
        """把当前玩家的「头 + 肩」贴图填进骑乘机甲的 ren 部件。"""
        if not getattr(self, "_has_rider", False):
            return
        head = _pilot_head(soldier, look)
        if head is None:
            return
        for sk in self.sk.values():
            if sk is None or "ren" not in (sk.images or {}):
                continue
            w, h = sk.images["ren"].get_size()
            img = _fit_img(head, w, h, k_scale=0.95)
            if img is not None:
                sk.images["ren"] = img

    def render(self, s, state, t, screen_x, foot_y, scale, flip=False):
        # 机甲骨骼自带的 scale 已经是「相对士兵」的比例，这里只做微调
        sk = self.sk.get(state) or self.sk.get("stand") or self.sk.get("walk")
        if sk is None or sk.frame_count <= 0:
            return
        frame = (t * MECH_ANIM_FPS) % sk.frame_count
        sk.render(
            s, frame, int(screen_x), int(foot_y), scale * mech_form_scale(self.name), flip=flip
        )

    def draw_shadow(self, s, screen_x, foot_y, scale):
        im = res.load_img("pic/soldier/yinying.png")
        if not im:
            return
        _sc = scale * mech_form_scale(self.name)
        w = int(im.get_width() * _sc)
        h = int(im.get_height() * _sc)
        s.blit(
            pygame.transform.smoothscale(im, (w, h)), (int(screen_x - w / 2), int(foot_y - h / 2))
        )


def _fly_skeleton(name):
    key = "__fly_" + name
    if key in _skel_cache:
        return _skel_cache[key]
    nn = FLY_SKEL.get(name)
    sk = None
    if nn:
        base = "config/mech/%s/" % nn
        try:
            sk = Skeleton(
                [base + "upper_sheets.xml", base + "lower_sheets.xml"],
                base + "stand_animations.xml",
            )
        except Exception:
            sk = None
    _skel_cache[key] = sk
    return sk


def mech_fire_dur(name):
    """机甲开火动画的自然时长（帧数 / MECH_ANIM_FPS，至少 0.22 秒）。"""
    sk = _mech_state_skeleton(name, "fire")
    if sk is None or sk.frame_count <= 0:
        return 0.22
    return max(0.22, sk.frame_count / MECH_ANIM_FPS)


class AttackWeapon:
    """mech_7 的炮塔（BattleField::createAttackWeapon @0x16db30）。

    与 MechUnit 的区别：
      · **士兵不变身**（这是独立实体，玩家照常操控自己）
      · 位置固定 = 士兵 x − 150（`CCPoint(-150.0, 0.0)`），z = 2
      · 进来就开火，没有"飞入"动画（onGetup 直接启动）

    骨骼用机甲那套（mech_7 = config/mech/07/）。
    """

    def __init__(self, name, sx, ground_y, interval=None):
        self.name = name
        self.sk = _mech_skeleton(name)
        self.x = sx + MECH_OFFSET_X
        self.ground_y = ground_y
        self.t = 0.0
        self.fire_cd = 0.0
        self.muzzle = 0.0
        self.fire_t = 0.0
        self.fire_left = 0.0
        self.entered = True
        self.interval = MECH_FIRE_INTERVAL if interval is None else float(interval)

    def update(self, dt, sx):
        self.t += dt
        # ★ 落地位置在 __init__ 里就定死了：炮塔是**架在地上**的固定火力点，
        #   玩家跑开它也不能跟着平移（原来每帧 self.x = sx + OFFSET，
        #   等于一门会滑的炮）。
        if self.muzzle > 0:
            self.muzzle = max(0.0, self.muzzle - dt)
        # 开火动画进度：连射时连续循环，停止后归零
        self.fire_t += dt
        if self.fire_left > 0.0:
            self.fire_left = max(0.0, self.fire_left - dt)
            if self.fire_left <= 0.0:
                self.fire_t = 0.0
        if self.fire_cd > 0:
            self.fire_cd -= dt
        return self

    def can_fire(self):
        return self.fire_cd <= 0

    def on_fire(self):
        self.fire_cd = self.interval
        if self.fire_left <= 0.0:
            self.fire_t = 0.0
        self.fire_left = max(self.fire_left, mech_fire_dur(self.name))
        self.muzzle = 0.22

    def pose(self):
        if self.fire_left > 0.0:
            return "fire", self.fire_t
        return "stand", self.t

    def render(self, s, cam):
        if not self.sk:
            return 0, 0
        st, t = self.pose()
        sk = self.sk
        if st == "fire":
            sk = _mech_state_skeleton(self.name, "fire") or self.sk
        frame = (t * MECH_ANIM_FPS) % max(1, sk.frame_count)
        sk.render(s, frame, int(self.x - cam), int(self.ground_y), MECH_SCALE, flip=False)
        return int(self.x - cam), int(self.ground_y)


class MechUnit:
    """一台被召唤出来的机甲。"""

    def __init__(self, name, sx, ground_y, interval=None):
        self.name = name
        self.sk = _mech_skeleton(name)
        self.x = sx + MECH_OFFSET_X
        self.ground_y = ground_y
        self.t = 0.0
        self.fire_cd = 0.0
        self.muzzle = 0.0
        self.fire_t = 0.0
        self.fire_left = 0.0
        self.dead = False
        # 同上：射速按 weapon/<name>.xml 的 min_interval
        self.interval = MECH_FIRE_INTERVAL if interval is None else float(interval)

    def update(self, dt, sx):
        """跟着士兵走，自己按射速开火。"""
        self.t += dt
        target_x = sx + MECH_OFFSET_X
        # 平滑跟随（机甲笨重，不做瞬移）
        self.x += (target_x - self.x) * min(1.0, dt * 6.0)
        if self.muzzle > 0:
            self.muzzle = max(0.0, self.muzzle - dt)
        self.fire_t += dt
        if self.fire_left > 0.0:
            self.fire_left = max(0.0, self.fire_left - dt)
            if self.fire_left <= 0.0:
                self.fire_t = 0.0
        if self.fire_cd > 0:
            self.fire_cd -= dt
        return self

    def can_fire(self):
        return self.fire_cd <= 0

    def on_fire(self):
        self.fire_cd = self.interval
        if self.fire_left <= 0.0:
            self.fire_t = 0.0
        self.fire_left = max(self.fire_left, mech_fire_dur(self.name))
        self.muzzle = 0.22

    def pose(self):
        if self.fire_left > 0.0:
            return "fire", self.fire_t
        return "stand", self.t

    def render(self, s, cam):
        if not self.sk:
            return
        # 同上：随姿态/时间推进帧，开机甲时不再是静止图
        st, t = self.pose()
        sk = self.sk
        if st == "fire":
            sk = _mech_state_skeleton(self.name, "fire") or self.sk
        frame = (t * MECH_ANIM_FPS) % max(1, sk.frame_count)
        sk.render(s, frame, int(self.x - cam), int(self.ground_y), MECH_SCALE, flip=False)


class FlyWeapon:
    """一件飞行武器：从右侧飞入，悬停后持续射击。

    hover_dx 可改悬停相对位置 —— mech_7 炮塔用 −150（士兵左边），
    飞行武器用默认的 FLY_HOVER_DX（士兵右上）。
    """

    def __init__(self, name, sx, ground_y, hover_dx=None, scale=None, interval=None):
        self.name = name
        self.sk = _fly_skeleton(name)
        self.ground_y = ground_y
        self.t = 0.0
        self.hover_dx = FLY_HOVER_DX if hover_dx is None else float(hover_dx)
        self.scale = FLY_SCALE if scale is None else float(scale)
        # 从屏幕右侧外飞入；起终点都在**召唤这一刻**定死（世界坐标）
        self.start_x = sx + 520.0
        self.start_y = ground_y - FLY_HOVER_DY - 120.0
        self.anchor_x = sx + self.hover_dx
        self.x = self.start_x
        self.y = self.start_y
        self.fire_cd = 0.0
        self.muzzle = 0.0
        self.entered = False
        # 射速同样取 weapon/<name>.xml 的 min_interval（fly_1 0.4 / fly_2 0.5）
        self.interval = FLY_FIRE_INTERVAL if interval is None else float(interval)

    def update(self, dt, sx):
        self.t += dt
        k = min(1.0, self.t / FLY_ENTER_TIME)
        # ★ 悬停点用召唤时记下的 anchor_x，不再每帧取 sx：
        #   无人机是**定点自动炮台**，玩家跑图它不该一直吊在头顶跟。
        tx = self.anchor_x
        ty = self.ground_y - FLY_HOVER_DY
        if k < 1.0:
            e = 1.0 - (1.0 - k) ** 3
            self.x = self.start_x + (tx - self.start_x) * e
            self.y = self.start_y + (ty - self.start_y) * e
        else:
            self.entered = True
            # 悬停小幅上下浮动
            self.x += (tx - self.x) * min(1.0, dt * 8.0)
            self.y = ty + math.sin(self.t * 3.2) * 8.0
        if self.muzzle > 0:
            self.muzzle = max(0.0, self.muzzle - dt)
        if self.fire_cd > 0:
            self.fire_cd -= dt
        return self

    def can_fire(self):
        return self.entered and self.fire_cd <= 0

    def on_fire(self):
        self.fire_cd = self.interval
        self.muzzle = 0.18

    def pose(self):
        if self.muzzle > 0:
            return "fire", max(0.0, 0.18 - self.muzzle)
        return "stand", self.t

    def render(self, s, cam):
        if not self.sk:
            return 0, 0
        # 飞行武器也按时间推进帧（原版是循环播放的 idle 动画）
        t = self.t
        frame = (t * MECH_ANIM_FPS) % max(1, self.sk.frame_count)
        self.sk.render(s, frame, int(self.x - cam), int(self.y), self.scale, flip=False)
        return int(self.x - cam), int(self.y)
