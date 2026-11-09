"""军火库其余页签的数据：士兵 / 技能 / 机甲。

来源（assets/raw，全部原版表）：
  * level/soldier_actors.xml  士兵：name / title / cost_coin / cost_crystal
  * level/mech_actors.xml     机甲：blood / speed / power / cost_coin
                              name_tex / head_tex
  * level/upgrade.xml        士兵三条升级线 blood_level / speed_level / armor_level
                              （含 next_potion 与 pval 消耗系数）
  * 技能：pic/ui/shop/ability_* 资源名与文案
"""

import json
import os
import xml.etree.ElementTree as ET

from engine import res


DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# 原版 Name2IconTex 的资源映射表（从反编译里抽出的 124 条）
# key: "soldier_1_title" / "mech_3_title" / "soldier_1_desc" / "kill_mission" ...
# value: 贴图路径
_NAME2ICON = None


def name2icon(key):
    """查原版资源映射。查不到返回空串。"""
    global _NAME2ICON
    if _NAME2ICON is None:
        path = os.path.join(DATA, "name2icon.json")
        try:
            with open(path, encoding="utf-8") as f:
                _NAME2ICON = dict(json.load(f))
        except (OSError, ValueError):
            try:
                from engine.name2icon import NAME2ICON

                _NAME2ICON = dict(NAME2ICON)
            except ImportError:
                _NAME2ICON = {}
    return _NAME2ICON.get(key, "")


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def load_soldier_actors():
    """level/soldier_actors.xml → [{name, title, cost_coin, cost_crystal}]"""
    txt = res.load_xml("level/soldier_actors.xml")
    if not txt:
        return []
    try:
        t = ET.fromstring(txt)
    except ET.ParseError:
        return []
    out = []
    for s in t.iter("soldier"):
        name = s.get("name")
        if not name:
            continue
        out.append(
            dict(
                name=name,
                title=s.get("title", name),
                cost_coin=int(_f(s.get("cost_coin"), 0)),
                cost_crystal=int(_f(s.get("cost_crystal"), 0)),
            )
        )
    return out


def load_mech_actors():
    """level/mech_actors.xml → [{name, blood, speed, power, cost_coin,
    name_tex, head_tex}]"""
    txt = res.load_xml("level/mech_actors.xml")
    if not txt:
        return []
    try:
        t = ET.fromstring(txt)
    except ET.ParseError:
        return []
    out = []
    for s in t.iter("soldier"):
        name = s.get("name")
        if not name:
            continue
        out.append(
            dict(
                name=name,
                blood=int(_f(s.get("blood"), 0)),
                speed=int(_f(s.get("speed"), 0)),
                power=int(_f(s.get("power"), 0)),
                cost_coin=int(_f(s.get("cost_coin"), 0)),
                cost_crystal=int(_f(s.get("cost_crystal"), 0)),
                name_tex=s.get("name_tex", ""),
                head_tex=s.get("head_tex", ""),
                # ★ 机甲的专属开火特效（SoldierActorParser 里每台机甲自带）
                spark=_mech_el(s, "FireSpark"),
                case=_mech_el(s, "BulletCase"),
                # 多组版本：mech_4 有 2 个 FireSpark / 2 个 BulletCase，
                # mech_7 有 2 个 BulletCase（原版是 vector，逐个生成）
                sparks=_mech_els(s, "FireSpark"),
                cases=_mech_els(s, "BulletCase"),
            )
        )
    return out


def _mech_el(node, tag):
    """机甲 XML 里的 FireSpark / BulletCase 子节点 → dict（没有就 None）。"""
    e = node.find(tag)
    if e is None:
        return None
    return _mech_el_dict(e)


def _mech_el_dict(e):
    out = dict(e.attrib)
    for k in ("duration", "scale", "offset_x", "offset_y", "rot_speed", "delay"):
        if k in out:
            out[k] = _f(out[k], 0.0)
    for k in ("row_count", "col_count"):
        if k in out:
            out[k] = int(_f(out[k], 1))
    return out


def _mech_els(node, tag):
    return [_mech_el_dict(e) for e in node.findall(tag)]


def load_soldier_upgrades():
    """level/upgrade.xml 的 <soldier> 段 → {name: {blood:[], speed:[], armor:[]}}

    每条升级线记录：血量 / 速度 / 护甲数值、消耗药水数（next_potion）、
    消耗系数（pval，原版用它换算金币花费）。
    """
    txt = res.load_xml("level/upgrade.xml")
    if not txt:
        return {}
    try:
        t = ET.fromstring(txt)
    except ET.ParseError:
        return {}
    out = {}
    for s in t.iter("soldier"):
        name = s.get("name")
        if not name:
            continue
        rec = {}
        for kind, tag in (
            ("blood", "blood_level"),
            ("speed", "speed_level"),
            ("armor", "armor_level"),
        ):
            lvls = []
            for lv in s.findall(tag):
                lvls.append(
                    dict(
                        id=int(_f(lv.get("id"), 0)),
                        value=_f(lv.get(kind) if kind != "armor" else lv.get("armor"), 0),
                        potion=int(_f(lv.get("next_potion"), 0)),
                        pval=_f(lv.get("pval"), 1.0),
                    )
                )
            lvls.sort(key=lambda x: x["id"])
            rec[kind] = lvls
        out[name] = rec
    return out


# 技能（原版 AbilityShopLayer 的资源名 pic/ui/shop/ability_<name>.png）
# 文案用 pic/ui/shop/ability_num_1 / ability_num_2 拼，图标取 ability_<name>.png
ABILITIES = [
    # (name, title, icon_name, num, coin, crystal)
    # 全部逐条来自 assets/raw/level/shop_config.xml 的 <ability> 段；
    # AbilityItemDef::setAbilityItemDef 只认 name / title / cost_coin / cost_crystal。
    ("hp_1", "hp potion i", "hp_1", 1, 1000, 0),
    ("hp_2", "hp potion ii", "hp_2", 2, 0, 4),
    ("shield_1", "defense shield i", "shield_1", 1, 1500, 0),
    ("shield_2", "defense shield ii", "shield_2", 2, 0, 6),
    ("power_1", "power potion i", "power_1", 1, 1250, 0),
    ("power_2", "power potion ii", "power_2", 2, 0, 5),
    ("speed_1", "speed potion i", "speed_1", 1, 1000, 0),
    ("speed_2", "speed potion ii", "speed_2", 2, 0, 4),
    ("airstrike", "air strike", "airstrike", 0, 0, 3),
    ("mech_7", "mark 7 gun turret", "mech_7", 0, 0, 6),
    ("fly_1", "redswift-b", "fly_1", 0, 2000, 0),
    ("fly_2", "white knight-ii", "fly_2", 0, 0, 8),
]
