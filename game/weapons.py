"""武器系统：weapon/*.xml（战斗数值）+ level/upgrade.xml（升级/购买/外观）。"""

import os
import xml.etree.ElementTree as ET

from engine import res


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def load_weapons():
    """weapon/*.xml → {name: {damage, shoot_distance, area_damage, bomb_radius,
    interval, multi_shot, delay, mech_blood, speed}}"""
    out = {}
    rawdir = os.path.join(res.RAW, "weapon")
    if not os.path.isdir(rawdir):
        return out
    for f in sorted(os.listdir(rawdir)):
        if not f.endswith(".xml"):
            continue
        name = f[:-4]
        try:
            t = ET.fromstring(res.load_xml("weapon/" + f))
        except ET.ParseError:
            continue
        root = (
            t if t.tag == "soldier" else (t.find("soldier") if t.find("soldier") is not None else t)
        )
        we = root.find("weapon_effect")
        if we is None:
            continue
        out[name] = dict(
            damage=int(_f(we.get("damage"), 0)),
            shoot_distance=_f(we.get("shoot_distance"), 900),
            area_damage=_f(we.get("area_damage"), 0),
            bomb_radius=_f(we.get("bomb_radius"), 0),
            interval=_f(root.get("min_interval"), 0.2),
            multi_shot=int(_f(root.get("multi_shot"), 1)),
            delay=_f(we.get("delay"), 0),
            # 机甲专属：<soldier mech_blood="1250" speed="180">。
            # 这是原版机甲形态的**绝对血量**和移速（Soldier::onChange2Mech
            # @0x188e8c 把 CharacterDef+56 直接写进 this+67/68）。
            # 跟 level/mech_actors.xml 里的 blood/speed 档位（1..12）是两套数据，
            # 档位只给军火库的「威力/速度/装甲」展示条用。
            mech_blood=int(_f(root.get("mech_blood"), 0)),
            speed=_f(root.get("speed"), 0),
        )
    return out


_UPGRADE_CACHE = {}


def load_upgrade_table():
    """level/upgrade.xml → {name: [ {level fields...} x4 ]}

    对应 GunUpgradeDef（反编译 DialogExpWeapon::setGunInfo 引用）。
    next_coin/next_crystal 是「升到下一级」的花费（当前级里存的）。
    """
    if _UPGRADE_CACHE:
        return _UPGRADE_CACHE
    out = _UPGRADE_CACHE
    txt = res.load_xml("level/upgrade.xml")
    if not txt:
        return out
    try:
        t = ET.fromstring(txt)
    except ET.ParseError:
        return out
    for g in t.iter("gun"):
        name = g.get("name")
        if not name:
            continue
        lvls = []
        for lv in g.findall("level"):
            lvls.append(
                dict(
                    id=int(_f(lv.get("id"), 0)),
                    damage=int(_f(lv.get("damage"), 0)),
                    min_interval=_f(lv.get("min_interval"), 0.2),
                    crit_rate=_f(lv.get("crit_rate"), 0.06),
                    power=_f(lv.get("power"), 0),
                    speed=_f(lv.get("speed"), 0),
                    crit=_f(lv.get("crit"), 0),
                    next_coin=int(_f(lv.get("next_coin"), 0)),
                    next_crystal=int(_f(lv.get("next_crystal"), 0)),
                )
            )
        lvls.sort(key=lambda x: x["id"])
        looks = []
        for cl in g.findall("change_look"):
            looks.append(
                dict(
                    min_lv=int(_f(cl.get("min_lv"), 0)), look_index=int(_f(cl.get("look_index"), 0))
                )
            )
        out[name] = dict(levels=lvls, looks=looks)
    return out


def load_soldiers():
    """level/upgrade.xml 的 <soldier> 段 → {name: {blood:[], speed:[], armor:[]}}。

    士兵的血量、移动速度、护甲减免按升级等级配（原版 upgrade.xml 的
    blood_level / speed_level / armor_level），与枪的 upgrade 表同文件。
    armor 是受伤减免比例（0.02 ~ 0.25）。
    """
    out = {}
    txt = res.load_xml("level/upgrade.xml")
    if not txt:
        return out
    try:
        t = ET.fromstring(txt)
    except ET.ParseError:
        return out
    for s in t.iter("soldier"):
        name = s.get("name")
        if not name:
            continue
        blood = []
        for b in s.findall("blood_level"):
            blood.append(int(_f(b.get("blood"), 250)))
        speed = []
        for sp in s.findall("speed_level"):
            speed.append(int(_f(sp.get("speed"), 150)))
        armor = []
        for a in s.findall("armor_level"):
            armor.append(_f(a.get("armor"), 0.0))
        out[name] = dict(blood=blood, speed=speed, armor=armor)
    return out


SFX_ALIAS = {
    "p220": "pistol",
    "m4": "rifle",
    "mp5": "rifle",
    "spas12": "rifle",
    "m200": "sniper",
    "katana": "sword",
    "wrench": "block",
    "guitar": "sword",
}


def load_fire_sparks():
    """weapon/*.xml 的 <FireSpark> → {name: [spark_def, ...]}。

    FireSparkDef（SoldierActorDef::addFireSpark @0x18af3c）结构 0x38 字节：
      [0] offset_x (int, × LOGIC)   [1] offset_y (int, × LOGIC)
      [2] row_count   [3] col_count   [4] duration(float)   [5] scale(默认 1.0)
      [6] random_pos(默认 0)        [7] delay(默认 -1.0)   [8] tex(string)

    WeaponEffect::addFireSparkEffect @0x19f508：
      帧宽 = texW / col_count，帧高 = texH / row_count（EzSprite::animationWithResName）
      精灵位置 x = offset_x + 精灵宽*0.5，y = 基准y − (offset_y + (精灵高+4)*0.5)
      Direction==0 → setFlipX(true) 并把 x 镜像到基准另一侧
    """
    out = {}
    rawdir = os.path.join(res.RAW, "weapon")
    if not os.path.isdir(rawdir):
        return out
    for f in sorted(os.listdir(rawdir)):
        if not f.endswith(".xml"):
            continue
        name = f[:-4]
        try:
            t = ET.fromstring(res.load_xml("weapon/" + f))
        except ET.ParseError:
            continue
        root = (
            t if t.tag == "soldier" else (t.find("soldier") if t.find("soldier") is not None else t)
        )
        we = root.find("weapon_effect")
        if we is None:
            continue
        sparks = []
        for fs in we.findall("FireSpark"):
            sparks.append(
                dict(
                    offset_x=int(_f(fs.get("offset_x"), 0)),
                    offset_y=int(_f(fs.get("offset_y"), 0)),
                    row_count=int(_f(fs.get("row_count"), 1)),
                    col_count=int(_f(fs.get("col_count"), 1)),
                    duration=_f(fs.get("duration"), 0.1),
                    scale=_f(fs.get("scale"), 1.0),
                    random_pos=int(_f(fs.get("random_pos"), 0)),
                    delay=_f(fs.get("delay"), -1.0),
                    tex=fs.get("tex", ""),
                )
            )
        if sparks:
            out[name] = sparks
    return out


def weapon_sfx(name):
    return SFX_ALIAS.get(name, name)


def look_index(name, lv, uptab=None):
    """当前等级用第几套外观（upgrade.xml 的 change_look）。

    min_lv=1 → 1、min_lv=3 → 2，都没到就是 0（原始贴图）。
    """
    tab = (uptab if uptab is not None else load_upgrade_table()).get(name) or {}
    pick = 0
    for lk in tab.get("looks") or []:
        if int(lv) >= int(lk.get("min_lv", 0) or 0):
            pick = int(lk.get("look_index", 0) or 0)
    return pick


def gun_icon(name, lv):
    """gun_<name>[_look].png —— change_look min_lv 决定 _1/_2 后缀。"""
    look = look_index(name, lv)
    if look:
        alt = "pic/ui/shop/gun_%s_%d.png" % (name, look)
        if res.load_img(alt):
            return alt
    return "pic/ui/shop/gun_%s.png" % name
