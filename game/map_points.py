"""地图任务点 —— 对齐 MapLayer::initMissionCandidatePositions @0x122884。

坐标全部来自反编译的 s_fLogicUnitLen 公式：
    x = s_fLogicUnitLen * logicX
    y = 480 − s_fLogicUnitLen * logicY
在 854x480 设计分辨率下 s_fLogicUnitLen = 1（zone_positions.json 实测一致）。

每个 zone 一组「图标位」，按完成进度（Day）阈值挑选：
    country / drainage / lab  有 3 个位（阈值 1.66 / 1.499 / 0）
    cemetery                  2 个位（阈值 1.499 / 0）
    其余 zone                 1 个位

阈值来自反编译 addIconPosition 的 float 参数：
    1070889697 = 1.66f · 1069539131 = 1.499f · 0 = 0.0f

MissionPosInfo::getIconPos @0x12053c：遍历图标位，
**第一个满足「阈值 >= 该位权重」的返回它的坐标**；都不满足则返回最后一个。

zone 名牌用 zone_<name>.png，锚点同 zone 锚点。
"""

import os

import pygame

from engine import res


LOGIC = 1.0
W, H = 854, 480

# zone → (锚点 logicX, 锚点 logicY)
# zone 名牌：MissionPosInfo 的 zone 锚点，anchor(0,1)（左上角对齐），scale 1.25
ZONE_ANCHOR = {
    "country": (32, 271),
    "cemetery": (25, 116),
    "prison": (235, 171),
    "jailbreak": (235, 171),
    "forest": (275, 311),
    "bridge": (304, 44),
    "bankside": (304, 44),
    "hospital": (423, 179),
    "drainage": (621, 339),
    "lab": (698, 70),
    "metro": (501, 293),
}

# zone 名牌 scale —— 反编译 initLevelMissions 里
#   EzSprite::setScale(v53, 1067450368) = 1.25
ZONE_LABEL_SCALE = 1.25

# 任务气泡 scale —— 反编译 initLevelMissions：
#   气泡本体不缩放（scale 1.0）；
#   this[134] 是「屏幕宽/高」= 853.33/480 = 1.778，
#   所以那段 if (ratio>=1.66) 只是**不缩放**的分支，与进度无关。
#   真正的 0.92/0.85 缩放是历史遗留分支，本复刻按实测用 1.0。
BUBBLE_SCALE = 1.0

# 气泡 anchor = (0,1)：贴图左上角落在图标位坐标上
BUBBLE_ANCHOR = (0.0, 1.0)

# zone → [(图标位 logicX, logicY, 权重), ...]
# 权重 = 反编译 addIconPosition 的第一个 float 参数
#   1.66 → 1070889697 · 1.499 → 1069539131 · 0 → 0
ZONE_SLOTS = {
    "country": [(70, 296, 1.66), (85, 296, 1.499), (115, 296, 0.0)],
    "cemetery": [(75, 97, 1.499), (115, 97, 0.0)],
    "prison": [(265, 172, 0.0)],
    "jailbreak": [(265, 172, 0.0)],
    "forest": [(330, 345, 0.0)],
    "bridge": [(495, 64, 0.0)],
    "bankside": [(495, 64, 0.0)],
    "hospital": [(455, 190, 0.0)],
    "drainage": [(684, 362, 1.66), (658, 370, 1.499), (655, 375, 0.0)],
    "lab": [(710, 80, 1.66), (686, 80, 1.499), (670, 90, 0.0)],
    "metro": [(511, 275, 0.0)],
}

# 气泡缩放（反编译 MapLayer 任务点循环）：
#   进度阈值 >= 1.66 → 不缩放；>= 1.499 → 0.92；否则 → 0.85
SCALE_166 = 1.0
SCALE_1499 = 0.92
SCALE_DEFAULT = 0.85


def bubble_scale(threshold):
    """反编译里的气泡缩放：>=1.66 不缩放 / >=1.499 用 0.92 / 否则 0.85。

    注意：这段分支在原版里判断的其实是**屏幕宽高比**（853.33/480 = 1.778），
    不是任务进度，所以实际永远走「不缩放」。保留此函数用于对照反编译。
    """
    if threshold >= 1.66:
        return SCALE_166
    if threshold >= 1.499:
        return SCALE_1499
    return SCALE_DEFAULT


# 气泡贴图 map_bg_mission.png 的原始尺寸（节点树实测 sz=[109,59]）
BUBBLE_W, BUBBLE_H = 109, 59

# zone 名牌贴图
ZONE_BG = {
    "hospital": "zone_hospital.png",
    "bridge": "zone_bridge.png",
    "cemetery": "zone_cemetery.png",
    "country": "zone_country.png",
    "jailbreak": "zone_prison.png",
    "prison": "zone_prison.png",
    "forest": "zone_forest.png",
    "metro": "zone_metro.png",
    "drainage": "zone_drainage.png",
    "lab": "zone_lab.png",
    "bankside": "zone_bridge.png",
}

# 图标贴图：任务类型 → map_mission_*.png
ICON = {
    "kill": "map_mission_kill.png",
    "kill_time": "map_mission_kill_time.png",
    "distance": "map_mission_distance.png",
    "distance_time": "map_mission_distance_time.png",
    "guard": "map_mission_guard.png",
    "hostage": "map_mission_hostage.png",
    "hostage_time": "map_mission_hostage_time.png",
    "collect": "map_mission_collect.png",
    "collect_time": "map_mission_collect_time.png",
    "time": "map_mission_time.png",
    "training": "map_mission_training.png",
}


def mission_icon(mtype):
    """任务类型 → 图标贴图名。"""
    if mtype == "training_mission":
        return ICON["training"]
    if mtype.endswith("_time_mission"):
        base = mtype[: -len("_time_mission")]
        if base in ("kill", "distance", "hostage", "collect"):
            return ICON[base + "_time"]
        return ICON["time"]
    base = mtype[: -len("_mission")] if mtype.endswith("_mission") else mtype
    return ICON.get(base, ICON["kill"])


def _sx(lx):
    """反编译：MissionPosInfo 的图标位 = CCPoint(logicX, 480 − logicY)。

    这里存的是**屏幕坐标**（pygame y 向下）。
    反编译把 logicY 转成 cocos y（480 − logicY），cocos→屏幕再翻回来
    正好抵消，所以屏幕 y 就是 logicY 本身。
    """
    return LOGIC * lx


def _sy(ly):
    """同 _sx：屏幕 y = logicY（见模块注释的坐标推导）。"""
    return LOGIC * ly


def icon_slot(zone, threshold):
    """MissionPosInfo::getIconPos：选图标位。

    遍历该 zone 的图标位，**第一个满足「threshold >= 该位权重」**的返回；
    都不满足则返回最后一个（反编译的 LABEL_7 兜底分支）。
    """
    slots = ZONE_SLOTS.get(zone)
    if not slots:
        return None
    for lx, ly, w in slots:
        if threshold >= w:
            return (lx, ly, w)
    lx, ly, w = slots[-1]
    return (lx, ly, w)


def button_scale(threshold):
    """兼容旧接口：现在恒为 1.0（原版该分支判断的是屏幕宽高比）。"""
    return BUBBLE_SCALE


class MapPoint:
    """一个可点击的任务点。"""

    __slots__ = ("icon", "locked", "mission_id", "scale", "x", "y", "zone")

    def __init__(self, mission_id, zone, x, y, icon, locked=False, scale=SCALE_DEFAULT):
        self.mission_id = mission_id
        self.zone = zone
        self.x = x
        self.y = y
        self.icon = icon
        self.locked = locked
        self.scale = scale

    @property
    def rect(self):
        """命中框 —— 必须罩住**画出来的图标**，不是气泡的左上角。

        draw_points 的几何（反编译 initLevelMissions + 节点树实测）：
          气泡 map_bg_mission.png anchor(0,1)、sz=[109,59]，
          贴图**左上角**落在 (x, y) ⇒ 气泡占 x..x+109、屏幕 y..y+59。
          任务类型图标 anchor(0.5,0.5)，中心在按钮局部 (w*0.48, h*0.63)
          ⇒ 屏幕中心 = (x + 109*0.48, y + 59*(1-0.63)) = (x+52, y+22)。

        原来这里返回 (x-29, y-35, x+29, y) —— 整个框在气泡**上方**，
        点气泡本体反而点不到，玩家看到的和能点的完全对不上。
        """
        iw = int(round(BUBBLE_W * self.scale))
        ih = int(round(BUBBLE_H * self.scale))
        cx = self.x + iw * 0.48
        cy = self.y + ih * (1.0 - 0.63)
        # 命中区取图标大小（58x35）并向外扩一点，方便手指点
        hw, hh = 34, 24
        return (int(cx - hw), int(cy - hh), int(cx + hw), int(cy + hh))


def current_level(save, level_db=None):
    """存档的 "level" 键 = 第几天（原版默认 1，通关后 +1）。

    反编译 MapLayer::onMissionPassed：
        level = getKeyValue("level", 1) + 1
    —— 但那是「**当天全部任务完成**」后才推进：
    MapLayer::initLevelMissions 会把**当天所有 mission** 都建成气泡，
    已通关的 disable 掉。所以一天的几个任务可以任意顺序打，
    全部打完后才进下一天。

    本复刻没有独立的 level 键时，从 passed_missions 反推：
    **已通关任务里最大的 level**（不是通关数！）。
    打完第 1 个就直接跳下一天，剩下的任务永远看不到。
    """
    passed = set(save.d.get("passed_missions") or [])
    if not level_db:
        return len(passed) + 1
    # 「当前天」= 还有未通关任务的最小 level。
    # 反编译 MapLayer::initLevelMissions 建的是**当天全部任务**的气泡，
    # 已通关的 disable 掉 —— 同一天的几个任务要一起显示，全部打完才推进。
    by_level = {}
    for mid, info in level_db.items():
        by_level.setdefault(int(info.get("level", 1)), []).append(mid)
    for lvl in sorted(by_level):
        if any(mid not in passed for mid in by_level[lvl]):
            return lvl
    return max(by_level) if by_level else 1


def missions_of_level(level_db, level):
    """某一天（第 level 天）的所有 mission，按 mission_id 排序。

    反编译 MapLayer::updateLevel：
        LevelList::getLevelDef(level) → LevelDef（含该天的 mission_desc 列表）
        → MapLayer::initLevelMissions 遍历这些 mission 逐个建气泡 + zone 名牌
    """
    out = []
    for mid, info in level_db.items():
        if info.get("level") == level:
            out.append((mid, info))
    out.sort(key=lambda t: t[0])
    return out


def unlocked_zones(level_db, save):
    """当前这一天涉及的 zone 集合（每个 mission 一个 zone 名牌）。

    反编译 initLevelMissions：每个 mission 都会建一个
    "pic/ui/map/zone_<zone>.png" 节点（jailbreak→zone_prison、bankside→zone_bridge），
    位置 = 该 zone 的锚点，anchor(0,1)，scale 1.25。
    实机验证（emu_map7.png）：新号第 1 天只有 hospital 一个 zone 名牌。
    """
    out = set()
    for _mid, info in missions_of_level(level_db, current_level(save, level_db)):
        z = info.get("zone")
        if z:
            out.add(z)
    return out


def build_points(level_db, save):
    """地图上当前可见的任务点（气泡）。

    反编译 MapLayer::initLevelMissions：
      遍历当前 LevelDef 的每个 mission，建一个 map_bg_mission.png 气泡按钮：
        按钮 anchor(0,1)、scale 1.0（那段 0.85/0.92 判断的其实是屏幕宽高比）
        按钮位置 = MissionPosInfo::getIconPos(zone, 阈值)，
              阈值实参是 this[134] = 屏幕宽/高 = 853.33/480 = 1.778
              ⇒ 恒命中该 zone 第一个（权重最高）的图标位
      结尾把 passed_missions 里的气泡 disable + 透明度 0 + 摘出父节点
        ⇒ 已通关的关卡气泡不显示
    """
    passed = set(save.d.get("passed_missions") or [])
    out = []
    # ★ 同一天里同一 zone 常有多个 mission。原版 MissionPosInfo 给
    #   country / drainage / lab 准备了 **3 个图标位**、cemetery 2 个，
    #   恒取第 1 个槽 ⇒ 同 zone 的气泡完全重叠，玩家只看到一个任务
    #   依次占槽，仍严格用反编译出来的那组坐标。
    used = {}
    for mid, info in missions_of_level(level_db, current_level(save, level_db)):
        if mid in passed:
            continue
        zone = info.get("zone")
        slots = ZONE_SLOTS.get(zone)
        if not slots:
            continue
        idx = used.get(zone, 0)
        used[zone] = idx + 1
        if idx == 0:
            lx, ly, _w = icon_slot(zone, 1.778)
        else:
            lx, ly, _w = slots[min(idx, len(slots) - 1)]
        out.append(
            MapPoint(mid, zone, _sx(lx), _sy(ly), mission_icon(info["type"]), False, BUBBLE_SCALE)
        )
    return out


def draw_points(s, points, save, font=None):
    """画任务点：底板 + 任务类型图标 + 星级。

    反编译 initLevelMissions + 节点树实测：
      气泡按钮 map_bg_mission.png
        anchor(0,1)、scale 1.0、sz=[109,59]
        位置 = 该 zone 的图标位（屏幕坐标，logicY 就是屏幕 y）
        ⇒ 贴图**左上角**落在 (x, y)
        （节点树实测 pos=[455,287.49] ap=[0,1]；
          287.49 是浮动动画的中间相位，基准值 290 = 480−190）
      底板子节点 map_bg_mission.png anchor(0.5,0.5)，中心在按钮局部 (54.5,29.5)
      任务类型图标 anchor(0.5,0.5)，中心在按钮局部 (w*0.48, h*0.63)
        （节点树实测 map_mission_kill.png sz=[58,35] pos=[52.32,37.17]）
        按钮局部原点在**左下角**（cocos y 向上），所以屏幕 y = y + h − h*0.63
    """
    bg = res.load_img("pic/ui/map/map_bg_mission.png")
    cnt = res.load_img("pic/ui/map/count_bg.png")
    for p in points:
        bw, bh = (0, 0)
        if bg:
            bw, bh = bg.get_size()
            sc = p.scale
            bw = int(round(bw * sc))
            bh = int(round(bh * sc))
            plate = pygame.transform.smoothscale(bg, (bw, bh))
            if p.locked:
                plate = plate.copy()
                plate.fill((110, 110, 130, 255), special_flags=pygame.BLEND_RGBA_MULT)
            # anchor(0,1)：左上角落在图标位坐标
            s.blit(plate, (int(p.x), int(p.y)))
        im = res.load_img("pic/ui/map/" + p.icon)
        if im:
            icon = im
            if p.locked:
                icon = im.copy()
                icon.fill((120, 120, 140, 255), special_flags=pygame.BLEND_RGBA_MULT)
            # 图标 anchor(0.5,0.5)，中心在按钮局部 (w*0.48, h*0.63)，
            # 局部原点在左下角 → 屏幕 y = 顶 + h − h*0.63
            icx = p.x + bw * 0.48
            icy = p.y + bh * (1.0 - 0.63)
            s.blit(icon, (int(icx - icon.get_width() / 2), int(icy - icon.get_height() / 2)))
        star = save.get_level_star(p.mission_id)
        if cnt and star:
            s.blit(pygame.transform.smoothscale(cnt, (21, 22)), (int(p.x + 12), int(p.y - 28)))
        if font and star:
            font.draw(s, str(star), int(p.x + 22), int(p.y - 17), 0.4, align=0.5)


def draw_zone_labels(s, zones=None):
    """zone 名牌（zone_*.png）。

    反编译 initLevelMissions：
      贴图 "pic/ui/map/" + zone + ".png"（jailbreak→zone_prison、bankside→zone_bridge）
      anchor(0,1)，scale 1.25，位置 = MissionPosInfo 的 zone 锚点
      （节点树实测 zone_hospital.png pos=[423,301] sz=[111,98] ap=[0,1] sc=[1.25,1.25]；
        301 = 480 − 179，即 cocos y，屏幕 y = 179）
    ⇒ 屏幕位置 = (logicX, logicY)，左上角对齐
    """
    for zone, tex in ZONE_BG.items():
        if zones is not None and zone not in zones:
            continue
        im = res.load_img("pic/ui/map/" + tex)
        anchor = ZONE_ANCHOR.get(zone)
        if not im or not anchor:
            continue
        x = _sx(anchor[0])
        y = _sy(anchor[1])
        w = int(round(im.get_width() * ZONE_LABEL_SCALE))
        h = int(round(im.get_height() * ZONE_LABEL_SCALE))
        img = pygame.transform.smoothscale(im, (w, h))
        # anchor(0,1)：左上角贴锚点
        s.blit(img, (int(x), int(y)))
