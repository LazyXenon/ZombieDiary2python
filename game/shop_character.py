"""士兵页 / 机甲页的中央角色大图。

原版 SoldierShopLayer::init（sub_140964 @0x140964）：

  聚光灯  pic/ui/shop/soldier_light.png  anchor(0.5,1.0) scale 0.5
          pos = (W * 0.5, H * 0.92)
  角色容器 CCNode  anchor(0.5,0.5)
          pos = (W * 0.84, H * 0.55)
          里面放 SoldierActor（骨骼动画），scale = 该士兵自己的 scale
  名字    SoldierTitle 贴图 anchor(0.5,0.5) pos = (W*0.5, H*0.66)
  天赋技能 talent_skill.png  anchor(0.5,1.0) pos = (W*0.15, H*0.54)
  士兵描述 pos = (W*0.08, H*0.47)

角色本身用骨骼引擎渲染：每个士兵的 stand 动画来自 soldier_actors.xml：
  soldier_1  config/soldier/01/de_sheets.xml      + de_stand_animations.xml
  soldier_2  pic/soldier/girl_02/saw_sheets.xml   + saw_stand_animations.xml
  soldier_3  pic/soldier/rarger_suit/m4_sheets.xml+ m4_stand_animations.xml
  soldier_4  pic/soldier/death_suit/m870_sheets.xml+m870_stand_animations.xml
  soldier_5  pic/soldier/robocop_suit/laser_sword_sheets.xml + laser_sword_stand_animations.xml
  soldier_6  pic/soldier/ninjia/laser_sword_sheets.xml      + laser_sword_stand_animations.xml
  soldier_7  pic/soldier/mech_dog/ak47_sheets.xml + ak47_stand_animations.xml
"""

import pygame

from engine import res
from engine.skel import Skeleton


W, H = 854, 480

LIGHT_TEX = "pic/ui/shop/soldier_light.png"
MASK_TEX = "pic/ui/shop/soldier_mask.png"
TALENT_TEX = "pic/ui/shop/talent_skill.png"

# 士兵 → (sheets 列表, stand 动画)
SOLDIER_SKEL = {
    "soldier_1": (["config/soldier/01/de_sheets.xml"], "config/soldier/01/de_stand_animations.xml"),
    "soldier_2": (
        ["pic/soldier/girl_02/saw_sheets.xml"],
        "config/soldier/01/saw_stand_animations.xml",
    ),
    "soldier_3": (
        ["pic/soldier/rarger_suit/m4_sheets.xml"],
        "config/soldier/01/m4_stand_animations.xml",
    ),
    "soldier_4": (
        ["pic/soldier/death_suit/m870_sheets.xml"],
        "config/soldier/01/m870_stand_animations.xml",
    ),
    "soldier_5": (
        ["pic/soldier/robocop_suit/laser_sword_sheets.xml"],
        "config/soldier/01/laser_sword_stand_animations.xml",
    ),
    "soldier_6": (
        ["pic/soldier/ninjia/laser_sword_sheets.xml"],
        "config/soldier/01/laser_sword_stand_animations.xml",
    ),
    "soldier_7": (
        ["pic/soldier/mech_dog/ak47_sheets.xml"],
        "config/soldier/01/ak47_stand_animations.xml",
    ),
}

# 士兵 scale（soldier_actors.xml 的 scale 属性）
SOLDIER_SCALE = {
    "soldier_1": 1.3,
    "soldier_2": 1.3,
    "soldier_3": 1.3,
    "soldier_4": 1.33,
    "soldier_5": 1.3,
    "soldier_6": 1.3,
    "soldier_7": 1.3,
}

# 原版 SoldierShopLayer::init 的成员偏移：
#   this+544 (偏移136) = W * 0.5 + LOGIC * 32  → 角色中心 x = 458.7
#   this+548 (偏移137) = H * 0.59               → 角色中心 y = 283.2
LOGIC = 1.0
CHAR_POS = (854 * 0.5 + LOGIC * 32, 480 * 0.59)

_skels = {}


def get_skeleton(name, gun=None):
    """按需加载骨骼（缓存）。

    「角色换不了武器 / 角色选择界面也有贴图错误」）。原版
    SoldierShopLayer 的 SoldierActor 同样用当前武器的 upper_sheets
    覆盖通用骨架；soldier_2..7 有专属造型，保持自己的贴图不动。
    """
    key = (name, gun or "")
    if key in _skels:
        return _skels[key]
    spec = SOLDIER_SKEL.get(name)
    if not spec:
        _skels[key] = None
        return None
    sk = None
    if gun:
        try:
            from game.soldier_sprite import SoldierSprite

            sp = SoldierSprite(gun, name, 0)
            sk = sp.anims.get("stand") or sp.anims.get("walk")
        except Exception:
            sk = None
    if sk is None:
        try:
            sk = Skeleton(spec[0], spec[1])
        except Exception:
            sk = None
    _skels[key] = sk
    return sk


def draw_spotlight(s, pos=None):
    """聚光灯。原版 anchor(0.5,1.0) scale 0.5，pos = (W*0.5, H*0.92)。"""
    im = res.load_img(LIGHT_TEX)
    if not im:
        return
    w = int(im.get_width() * 0.5)
    h = int(im.get_height() * 0.5)
    im = pygame.transform.smoothscale(im, (w, h))
    x = int(W * 0.5 - w / 2)
    y = int(H - H * 0.92 - h)  # anchor y=1 → 底边在 pos
    s.blit(im, (x, y))


def draw_soldier_character(s, name, frame=0, scale=None, pos=None, gun=None):
    """渲染士兵骨骼动画（gun 决定 soldier_1 手上那把武器）。

    原版 SoldierShopLayer::init（sub_140964）里的成员偏移：
      this+544 (偏移136) = W * 0.5 + LOGIC * 32   ← 角色中心 x
      this+552 (偏移138) = H * 0.52                ← 角色中心 y
    showSoldier 里选中士兵 pos = (this+136, this+137)，左/右各偏移 ±this+139。

    骨骼渲染器 render() 以「脚底」为锚点；原版容器是中心锚点，
    所以脚底 = 中心 + 半个身高 * scale（角色高约 160px）。
    """
    sk = get_skeleton(name, gun)
    if not sk:
        return False
    sc = SOLDIER_SCALE.get(name, 1.3) if scale is None else scale
    cx, cy = pos if pos else (CHAR_POS[0], CHAR_POS[1])
    half_h = 80 * sc
    ground_y = int(cy + half_h)
    #   原版 SoldierShopLayer 的 SoldierActor 一直播 stand 循环（16 帧，
    #   weapon XML 里 duration 0.6s ⇒ 26.7fps）。这里按**真实时长**采样，
    #   不再按 ticks/100 推帧号（那样一秒播 6 圈，看着是抖不是动）。
    nf = max(1, int(getattr(sk, "frame_count", 1) or 1))
    dur = 0.6
    # 帧号用小数交给 Skeleton 插值（60fps 下 26.7fps 的关键帧之间补中间动作）
    if frame:
        idx = float(frame) % nf
    else:
        idx = (pygame.time.get_ticks() / 1000.0 % dur) / dur * nf
    sk.render(s, idx, int(cx), ground_y, sc)
    return True
