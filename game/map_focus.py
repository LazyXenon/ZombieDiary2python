"""地图当前关卡的聚焦高亮 —— 原版 MapLayer 的 focus_level_effect。

反编译依据（all_merged.c:78766 附近）：
  ZoneColorType = MapLayer::getZoneColorType(zone)      @0x120…
      从服务器下发的 zone 颜色表查（本地没这份配置），
      查不到**默认 1** ⇒ 用 sheets_1.xml。
  Animation = createAnimation(
      "pic/effect/focus_level_effect/sheets_%d.xml",
      "pic/effect/focus_level_effect/animations.xml",
      循环播放)
  Animation.setScale(0.25)
  位置 = zone 锚点 + (-280*scale, +230*scale)

动画 b01，30 帧，3 个部件（b01/b02/b03）。
四套配色：1=b(蓝) 2=g(绿) 3=r(红) 4=y(黄)。
"""

import pygame

from engine.skel import Skeleton


SHEET_BASE = "pic/effect/focus_level_effect/sheets_%d.xml"
ANIM_TEX = "pic/effect/focus_level_effect/animations.xml"

SCALE = 0.25
OFF_X = -280.0 * SCALE
OFF_Y = 230.0 * SCALE
# 原版 createAnimation 的 delay 参数 0x3FB33333 = 1.4 秒/帧
# （all_merged.c:78778）。30 帧转一圈 = 42 秒，慢呼吸而不是快闪。
FPS = 1 / 1.4

# zone → 颜色类型（1=b蓝 2=g绿 3=r红 4=y黄）。
# 原版 MapLayer::initZoneInfoDefs @0x1241b4 硬编码的 ZoneInfoDef 表：
#   ZoneInfoDef(zone名, id, 图标位索引, 颜色类型)
#     hospital  1 2 3      bridge    2 2 4      cemetery 3 0 1
#     country   4 0 3      jailbreak 5 1 1     forest    6 1 4
#     metro     7 2 3      drainage  8 3 2     lab       9 3 1
#     bankside 10 2 4      prison   11 1 1
# 最后一位就是 getZoneColorType 返回的颜色类型。
ZONE_COLOR = {
    "hospital": 3,
    "bridge": 4,
    "cemetery": 1,
    "country": 3,
    "jailbreak": 1,
    "forest": 4,
    "metro": 3,
    "drainage": 2,
    "lab": 1,
    "bankside": 4,
    "prison": 1,
}

_cache = {}


def zone_color(zone):
    return ZONE_COLOR.get(zone, 1)


def _skeleton(color_type):
    key = int(color_type)
    if key in _cache:
        return _cache[key]
    sk = None
    try:
        sk = Skeleton([SHEET_BASE % key], ANIM_TEX)
        if sk and sk.frame_count <= 0:
            sk = None
    except Exception:
        sk = None
    _cache[key] = sk
    return sk


class FocusEffect:
    """当前关卡的聚焦高亮（循环播放）。"""

    def __init__(self, zone, x, y, color_type=None):
        self.zone = zone
        self.x = x
        self.y = y
        self.color_type = color_type or zone_color(zone)
        self.sk = _skeleton(self.color_type)
        self.t = 0.0

    def update(self, dt):
        self.t += dt

    def draw(self, s):
        if self.sk is None:
            return
        frame = int((self.t * FPS) % self.sk.frame_count)
        # 原版位置 = zone 锚点 + (-280, +230) × 0.25（节点空间）。
        #   本复刻没有 zone 节点，只有 zone 的**屏幕图标位**，
        #   所以直接把发光圈**居中**画在那个位置上（视觉等价）。
        #   Skeleton.render 的 screen_x = 包围盒中心，ground_y = 脚底线。
        bb = getattr(self.sk, "bbox", None)
        if bb:
            half_h = (bb[3] - bb[1]) * 0.5 * SCALE
        else:
            half_h = 0.0
        px = int(self.x)
        py = int(self.y + half_h)
        self.sk.render(s, frame, px, py, SCALE, flip=False)
