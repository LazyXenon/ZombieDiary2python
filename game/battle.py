"""战斗玩法核心。

证据链（RE_NOTES.md）：
* 任务在 level_list.xml 按 mission_id(1..133) 声明：type/zone/number/number2/reward_coin
* 波次在 level/<id>_<n>.xml：zombie_type 的 update_time / capacity / add_blood / add_speed
* 僵尸数值 zombies/*.xml：blood / speed / attack_damage / attack_distance /
  stand_distance / attack_delay / scale
* 士兵数值 level/upgrade.xml 的 blood_level / speed_level / armor_level
* 结算：UIBoard::onGameOver → DialogLevelPassed::setResult
  评分% = 血量剩余比，>99 星S / >84 星A / 否则星B
"""

import contextlib
import os
import random
import xml.etree.ElementTree as ET

from engine import res
from game import gun_fx as gfx
from game import zombie_fx as zfx
from game.ability_fx import AbilityFxLayer
from game.battle_summons import (
    FLY_RANGE,
    MECH_FORM_SCALE,
    MECH_RANGE,
    mech_fire_interval,
    mech_fx_bbox,
)
from game.constants import GUARD_LINE_X
from game.distance_target import DistanceTarget
from game.evac_heli import EvacHeli
from game.kill_bonus import KillBonusLayer, kill_bonus
from game.weapons import load_soldiers
from game.wormhole import Wormhole


# 无人机 / 机枪塔都是自动开火的挂机输出，直接按官方 weapon/*.xml 的数值跑
# 会盖过玩家主武器。不改官方资源，只在召唤物这一层统一削弱。
# damage：子弹伤害倍率；range：索敌半径上限；interval：开火间隔倍率。
FLY_NERF = dict(damage=0.45, range=430.0, interval=1.6)
TURRET_NERF = dict(damage=0.55, range=380.0, interval=1.45)


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def load_level_list():
    """level_list.xml → {mission_id(int): {...}}

    mission_id 是全表 mission_desc 的顺序号 1..133（原版 EzGameData 的
    LevelData map 按 1..133 存），不是 level id。level id 另存为 level 字段。
    """
    txt = res.load_xml("level/level_list.xml")
    if not txt:
        return {}
    t = ET.fromstring(txt)
    out = {}
    mid = 0
    for lv in t.iter("level"):
        try:
            lid = int(lv.get("id"))
        except (TypeError, ValueError):
            continue
        for m in lv.findall("mission_desc"):
            mid += 1
            waves = []
            lt = res.load_xml(m.get("zombie_config_xml", ""))
            if lt:
                lx = ET.fromstring(lt)
                for zt in lx.iter("zombie_type"):
                    waves.append(
                        dict(
                            name=zt.get("zombie_name", "zombie_9"),
                            update_time=_f(zt.get("update_time"), 3.0),
                            # capacity = 同屏存活上限（ZombieTypeDef::initType）
                            capacity=int(_f(zt.get("capacity"), 10)),
                            add_blood=_f(zt.get("add_blood"), 0),
                            add_speed=_f(zt.get("add_speed"), 0),
                            is_first=bool(int(_f(zt.get("is_first"), 0))),
                        )
                    )
            out[mid] = dict(
                level=lid,
                type=m.get("type", "kill_mission"),
                zone=m.get("zone", "hospital"),
                number=int(_f(m.get("number"), 10)),
                number2=int(_f(m.get("number2"), 0)),
                reward_coin=int(_f(m.get("reward_coin"), 800)),
                # reward_crystal：level_list.xml 里不写这个属性，
                # 但模拟器参考帧（emu_b3_s.png 第 1 关）奖励行是「🪙800 💎1 🎁」，
                # 说明原版缺省给 1，不是 0。
                reward_crystal=int(_f(m.get("reward_crystal"), 1)),
                waves=waves,
            )
    return out


def load_zombie_stats():
    """zombies/*.xml → {name: {hp,speed,atk,attack_distance,stand_distance,
    scale,attack_delay}}"""
    out = {}
    rawdir = os.path.join(res.RAW, "zombies")
    if not os.path.isdir(rawdir):
        return out
    for f in os.listdir(rawdir):
        if not f.endswith(".xml"):
            continue
        name = f[:-4]
        try:
            t = ET.fromstring(res.load_xml("zombies/" + f))
        except ET.ParseError:
            continue
        z = t if t.tag == "zombie" else t.find("zombie")
        if z is None:
            continue
        delay = z.get("attack_delay", "")
        out[name] = dict(
            hp=_f(z.get("blood"), 100),
            speed=_f(z.get("speed"), 100),
            atk=_f(z.get("attack_damage"), 40),
            attack_distance=_f(z.get("attack_distance"), 110),
            stand_distance=_f(z.get("stand_distance"), 65),
            scale=_f(z.get("scale"), 1.0),
            # attack_delay 形如 "1.2" 或 "0.9, 1.9"（连击节奏）
            attack_delay=[_f(x, 1.0) for x in delay.split(",") if x.strip()],
            # <Death last_max_damage="50" ...> 第一档的上限 = 碎片轻重分界
            death_split=_f(
                (z.find("Death").get("last_max_damage") if z.find("Death") is not None else None),
                50,
            ),
        )
    return out


GROUND_Y = 392.0


# 士兵基础（soldier_actors.xml soldier_1；血量/速度/护甲实际取自 upgrade.xml）
SOLDIER_BASE = dict(
    hp=250,
    speed=150,
    ground_y=GROUND_Y,
)

# 士兵在屏幕上的位置 —— 节点树实测（data/node_tree_battle.json）：
#   Soldier sz=[300,300] pos=[458.667, 72] anchor(0.5, 0)
#   SoldierCharacter pos=[150,150] anchor(0.5,0.5) sc=[1,1]
#   → 水平中心 458.667（≈ 屏幕 53.7%）
#   各身体部件的世界坐标（由节点树矩阵反算）：
#     头 tou.png(104x87)  中心 screen (427.3, 286.8) → 头顶 243.3
#     脚 zuotui.png      中心 screen y 375.5        → 脚底 401
#   部件显示尺寸 = 原图像素（缩放 1.0）
SOLDIER_SCREEN_X = 458.667
SOLDIER_FOOT_Y = GROUND_Y

DEATH_FADE = 0.25
# 冰冻持续秒数 —— 反编译 Zombie::onFreeze 的 DelayTime 参数 0x40600000 = 3.0f
FREEZE_DURATION = 3.0
SOLDIER_SCALE = 1.0
# Soldier::getCenterXInBattleFiled @0x18733c：
#   士兵精灵 pos.x − 精灵宽*0.5 + localCenterX
# 节点树实测：士兵头 tou.png 中心 screen x = 427.3（精灵 body 节点 x = 458.667，宽 300）
# ⇒ 士兵中心 x ≈ 427.3（相对 self.sx 偏 −31.4）
SOLDIER_CENTER_DX = -31.4
# 机甲/士兵骨骼实际渲染中心相对 self.sx 的偏移（与 app.constants.SOLDIER_DX
# 一致；game 层不反向依赖 app，故在这里同值声明）。特效换算必须用渲染中心，
# 用武器节点中心 (SOLDIER_CENTER_DX) 会再偏 21px。
SOLDIER_RENDER_DX = -10.0
# 士兵包围盒的半宽（屏幕像素）。ak47 平端时最宽 208（x 22..230），
# 手枪约 194。取 106 作边界留白，保证任何武器都不会被屏幕裁掉。
SOLDIER_HALF_W = 106.0
# 僵尸之间不重叠的最小间距（原版用 Box2D 物理碰撞）
# 僵尸之间的最小间距（逻辑像素）。僵尸骨骼宽约 230（scale 1.0），
# 僵尸排队中心间距（逻辑像素）。
# 原版参考帧 b4.png：最前两只中心相距 254 屏幕像素 = 380 逻辑像素，
# 但那包含空档；实测身体可见宽度约 190 逻辑像素。取 190：
# 既能排开（不互相压住），又不会把后队推出屏幕太远。
# 距离任务的换算：dist_m 是像素，进度单位 = 多少像素。
# 士兵 150 px/s，取 100 px/单位 ⇒ number=10 的关约 6.7 秒走完。
DIST_PX_PER_UNIT = 100

# 技能掉落物被捡走之后，到下一个可以再掉的间隔（秒）。
# 原版掉落物是「一只僵尸带一个」，正常节奏下要一只只死；本复刻扫描线
# 太快，一梭子扫死三四只带道具的僵尸，道具就一次性全冒出来。
ABILITY_DROP_GAP = 9.0

ZOMBIE_GAP = 190
# 排队区总跨度（从玩家往前这么远以内才维持 190px 不重叠）。
# 约 3.5 个身位 —— 屏幕右侧之外不必排队，否则同屏上百只时
# 级联推挤会把整条队伍推出射程。
ZOMBIE_QUEUE_SPAN = 900.0

# 召唤物参数（battle_summons 里的同名常量）


# ★ app.constants 会反过来 import game.battle（循环），
#   所以这个常量在用到的地方做成模块级默认值，不在这里 import。
GO_RIGHT_SHOW = 2.0


class Battle:
    """一场战斗。参数化武器（升级档来自 upgrade.xml）与士兵。"""

    def __init__(
        self,
        mission_id=1,
        level_db=None,
        zstats=None,
        weapons=None,
        upgrade_table=None,
        weapon="ak47",
        weapon_lv=0,
        soldier="soldier_1",
        soldier_lv=0,
        save=None,
    ):
        self.level_db = level_db or {}
        self.zstats = zstats or {}
        self.weapons = weapons or {}
        self.uptab = upgrade_table or {}
        self.mission_id = mission_id
        self.weapon = weapon
        self.weapon_lv = weapon_lv
        self.soldier = soldier
        self.soldier_lv = soldier_lv
        self.save = save
        self.reset()

    # ---- 武器档 ----
    def wstat(self):
        up = self.uptab.get(self.weapon)
        if up and 0 <= self.weapon_lv < len(up["levels"]):
            lv = up["levels"][self.weapon_lv]
            base = self.weapons.get(self.weapon, {})
            return dict(
                damage=lv["damage"],
                interval=lv["min_interval"],
                crit_rate=lv["crit_rate"],
                shoot_distance=base.get("shoot_distance", 900),
                area_damage=base.get("area_damage", 0),
                bomb_radius=base.get("bomb_radius", 0),
            )
        b = self.weapons.get(self.weapon, dict(damage=75, interval=0.2, shoot_distance=900))
        return dict(
            damage=b.get("damage", 75),
            interval=b.get("interval", 0.2),
            crit_rate=0.06,
            shoot_distance=b.get("shoot_distance", 900),
            area_damage=b.get("area_damage", 0),
            bomb_radius=b.get("bomb_radius", 0),
        )

    def soldier_stat(self, key, default, save=None):
        """士兵属性：blood / speed / armor，按当前 soldier 与等级取自 upgrade.xml。"""
        table = load_soldiers().get(self.soldier)
        if not table or not table.get(key):
            return default
        vals = table[key]
        lv = 0
        if save is not None:
            lv = save.soldier_level(key)
        return vals[min(max(0, lv), len(vals) - 1)]

    # ---- 换枪 ----
    def change_weapon(self, name):
        """Soldier::onChangeWeapon @0x1894f0：换当前武器。

        原版动作：
          1. 士兵换成对应武器外观（SoldierCharacter::initCharacter）
          2. 读存档 <name>_bullet → 子弹数（-1 = 无限子弹，0 = 没子弹）
          3. 写存档 last_equipped_gun = name
          4. 换枪口水花特效
        本复刻同样落实 1：SoldierSprite 按 (weapon, soldier, look)
        缓存骨骼，draw_battle 每帧用 b.weapon 取，换枪的下一帧手上
        就是新武器（upper_sheets 的 gun02/qiubang/fuzi 由
        override_parts 覆盖，不会再退回通用手枪贴图）。
        2/3 则是子弹数与 last_equipped_gun + 数值（伤害/射速/射程）。

        ★ 原版**换经验武器时禁止手动换枪**：
          反编译 Soldier::onChangeWeapon 第一行就是
              if (this[508] == 0) { ...换枪... }
          this[508] 是「正在用经验武器」的标志
          （Soldier::onChangeToExpWeapon @0x18978c 末尾置 1，
            子弹打完 Soldier::onWeaponFire @0x189388 置 0）。
          ⇒ 捡了地上的经验武器后，玩家**不能**切回原来的枪，
            只能用完 100 发自动换回。
          「捡了武器切换到原本的武器上面还是会有个条」）。
        """
        if not name or name == self.weapon:
            return False
        if (
            self.save is not None
            and hasattr(self.save, "own_weapon")
            and not self.save.own_weapon(name)
            and name != getattr(self, "_exp_weapon_name", None)
        ):
            return False
        # ★ 原版：持经验武器期间禁止手动换枪（this[508] != 0）
        #   _switching_exp 是复刻自己的内部标志 —— 换上/换下经验武器
        #   这两个动作本身要绕开这条限制。
        if getattr(self, "exp_weapon", None) and not getattr(self, "_switching_exp", False):
            return False
        self.weapon = name
        self.weapon_lv = self.save.weapon_level(name) if self.save is not None else 0
        w = self.wstat()
        self.wdamage = w["damage"]
        self.winterval = w["interval"]
        self.wcrit = w["crit_rate"]
        self.wdist = w["shoot_distance"]
        self.warea = w["area_damage"]
        # 爆炸溅射半径（原版 WeaponEffectDef 的 bomb_radius 字段，
        # 反编译 all_merged.c:115542 写入 +12）。
        # 0 = 该武器没有爆炸半径（近战 / 直线枪），沿用默认范围。
        self.wbomb = float(w.get("bomb_radius", 0) or 0)
        if self.save is not None:
            self.save.d["last_equipped_gun"] = name
            if hasattr(self.save, "save"):
                self.save.save()
        return True

    def gun_look(self):
        """当前武器等级对应的皮肤序号（upgrade.xml 的 change_look）。"""
        pick = 0
        for lk in (self.uptab.get(self.weapon) or {}).get("looks") or []:
            if int(self.weapon_lv or 0) >= int(lk.get("min_lv", 0) or 0):
                pick = int(lk.get("look_index", 0) or 0)
        return pick

    def bullet_count(self, name=None):
        """存档里的 <name>_bullet（Soldier::onChangeWeapon 读的就是它）。

        ★ 原版语义（反编译 all_merged.c:62310 GunItemDef::setGunItemDef）：
          GunItemDef 构造时把 +80/+84/+88 初始化成 **-1**，只有 XML 显式写了
          init_bullet 才覆盖。所以没写 init_bullet 的枪（全部近战武器、
          p220 等无限弹款）存档里是 **-1 = 无限子弹**。
          0 才是「子弹打空了」。
        """
        if self.save is None:
            return 0
        return int(self.save.d.get("%s_bullet" % (name or self.weapon), 0))

    def gun_def(self, name=None):
        """shop_config.xml 里的 GunItemDef（子弹相关的四个字段）。"""
        from game.shop_table import BY_NAME as GUN_BY_NAME

        return GUN_BY_NAME.get(name or self.weapon) or {}

    def infinite_bullet(self, name=None):
        """该枪是否无限子弹。

        判据取**配置层**（shop_config 的 init_bullet），不是存档里的运行值。

        反编译 all_merged.c:62310 GunItemDef::setGunItemDef：
          构造时把 +80/+84/+88 初始化成 **-1**，只有 XML 显式写了
          init_bullet 才覆盖。
          ⇒ 没写 init_bullet 的枪（全部近战武器 wrench/guitar/katana/axe/
            saw/laser_sword，以及 p220/ak47_gold 等无限弹款）
            配置里的 init_bullet 就是 -1 ⇒ 无限子弹。
          0 才是「子弹打空了」。

        ★ 为什么不看存档值：旧存档里 katana_bullet 被写成了 0
          （老版本 set_init_bullet 的缺省是 0），键已存在就不会被重写。
          只看存档值的话，玩家永远切不上近战武器。
          配置层是稳定的，改代码即修好所有存档。

        XML 的 infinite_bullet="1" 只影响军火库里的显示
        （GunShopLayer 里决定显不显示子弹价），战斗中的无限子弹
        靠的就是 init_bullet 缺省 = -1。
        """
        g = self.gun_def(name)
        if int(g.get("init_bullet", -1)) < 0:
            return True
        return bool(g.get("inf"))

    def consume_bullet(self):
        """WeaponItemButton::onFire @0x183ab0：开火扣 1 发弹。

        反编译：
          v2 = 本按钮当前子弹数（this+300）
          if (v2 > 0) { v2--; 显示 v2; 存档[<name>_bullet] = v2;
                        if (子弹节点为空) 置「没子弹」标志(451)=1 }
          ⇒ **子弹数为 0 或负数时 onFire 什么都不做**，
            既不扣弹也不自动换枪。

        原版「没子弹」的表现：Soldier::onStartFire @0x1872bc 检查 451 标志，
        非 0 就播 "sounds/block.ogg" 并**挡住开火**。
        """
        if self.infinite_bullet():
            return True
        n = self.bullet_count()
        if n <= 0:
            return False
        n -= 1
        if self.save is not None:
            self.save.d["%s_bullet" % self.weapon] = n
        return True

    def buy_bullet(self, name=None):
        """WeaponItemButton::onBuyBullet：花 bullet_cost_coin 金币买 bullet_count 发弹。

        BattleField::buyBullet：金币不够就返回 0（原版弹金币商店）。
        """
        name = name or self.weapon
        d = self.gun_def(name)
        count = int(d.get("bullet_count", 0))
        cost = int(d.get("bullet_cost", 0))
        if count <= 0 or cost <= 0:
            return False
        if self.save is None:
            return False
        coins = int(self.save.d.get("coins", 0))
        if coins < cost:
            return False
        self.save.d["coins"] = coins - cost
        self.save.d["%s_bullet" % name] = self.bullet_count(name) + count
        if hasattr(self.save, "save"):
            self.save.save()
        return True

    def next_weapon(self):
        """Soldier::onChangeNextWeapon：子弹打空后循环切到下一把已装备的枪。"""
        names = [w for w in (getattr(self.save, "d", {}) or {}).get("equipped") or [] if w]
        if len(names) < 2:
            return False
        try:
            i = names.index(self.weapon)
        except ValueError:
            i = 0
        nxt = names[(i + 1) % len(names)]
        return self.change_weapon(nxt)

    # ---- 技能效果 ----
    def airstrike(self, duration=3.0):
        """AirStrikeAbility：半径 285 内造成 500 伤害。

        反编译：AirStrikeAbility::AirStrikeAbility 设 radius = LOGIC*285、
        damage = 500；onBombLanding 调 Soldier::killZombiesOnExplosion。
        炸弹本体从天上落到士兵前方 → 落地爆炸（bomb_sheet 动画）。
        """
        # 一**串**炸弹依次从天上砸下来，落地那一刻才结算伤害
        # （原版 OnBombLanding 逐枚触发，不是按下去就立刻掉血）。
        # 步进写死，不用随机数，方便对拍复现。
        for i in range(5):
            self.airstrike_units.append(
                {
                    "x": self.sx + 40.0 + i * 95.0,
                    "y": SOLDIER_BASE["ground_y"],
                    "t": -i * 0.12,
                    "hit": False,
                    # 主弹负责结算原版那一次范围伤害，其余只是覆盖式轰炸的表现
                    "main": i == 2,
                }
            )

    def _airstrike_boom(self, b):
        """炸弹落地：主弹按 AirStrikeAbility 的半径/伤害结算一次。"""
        if b.get("main"):
            cx = self.sx + 200.0
            for z in self.zombies:
                if z["dead"]:
                    continue
                if abs(z["x"] - cx) <= 285.0:
                    z["hp"] -= 500
                    z["hurt"] = 0.3
                    if z["hp"] <= 0:
                        z["dead"] = True
                        self.kills += 1
        self.airstrike_fx = 0.4

    def _spawn_attack_weapon(self, name):
        """BattleField::createAttackWeapon @0x16db30：放一台自动炮塔。

        位置 = 士兵中心 x − 150（`cocos2d::CCPoint(-150.0, 0.0)` 加士兵坐标），
        z = 2（画在士兵下面）。炮塔自动找最近的僵尸开火，玩家不参与。

        用 **机甲骨骼**（`_mech_skeleton`，mech_7 = config/mech/07/），
        不是飞行武器那套（FLY_SKEL 只有 fly_1/fly_2）。
        """
        try:
            from game.battle_summons import AttackWeapon

            _w = self.weapons.get(name) or {}
            _iv = _w.get("interval")
            self.attack_unit = AttackWeapon(
                name,
                self.sx,
                SOLDIER_BASE["ground_y"],
                interval=None if _iv is None else float(_iv) * TURRET_NERF["interval"],
            )
            self.attack_until = self.time + 45.0
            self.buff_dur["attack"] = 45.0
        except Exception:
            self.attack_unit = None

    def _tick_summons(self, dt):
        """飞行武器的更新与开火。

        ★ 机甲**不在这里** —— 原版机甲是士兵换装（Soldier::onMechGetup），
          玩家的移动/开火指令照常作用在同一个士兵上，
          没有独立实体、也没有自动开火。
        """
        # 机甲到期（Soldier::onMechOver @0x1894a8）
        if self.mech_name is not None and self.time >= self.mech_until:
            self._mech_over()
        if self.fly_unit is not None and self.time >= self.fly_until:
            self.fly_unit = None
            self.fly_name = None
        # mech_7 炮塔到期移除（原版 AttackWeapon 到时 onGetupFinished 移除）
        if getattr(self, "attack_unit", None) is not None and self.time >= self.attack_until:
            self.attack_unit = None

        for unit in (self.fly_unit, getattr(self, "attack_unit", None)):
            if unit is None:
                continue
            unit.update(dt, self.sx)
            if unit.can_fire():
                spec = self._summon_spec(unit)
                # 自动开火只够补刀：索敌半径压回一屏以内，伤害也打折；
                # 无人机仍可双向索敌，但不再全屏追着打。
                is_fly = unit is self.fly_unit
                nerf = FLY_NERF if is_fly else TURRET_NERF
                dist = min(spec["dist"], nerf["range"])
                tgt = self._nearest_zombie(unit.x, dist, any_dir=is_fly)
                if tgt is not None:
                    unit.on_fire()
                    sx = unit.x - self.cam
                    sy = unit.y if is_fly else SOLDIER_BASE["ground_y"] - 70.0
                    distance = abs(tgt["x"] - unit.x) + 36.0
                    self.gunfx.add_bullet(
                        sx,
                        sy,
                        speed=1500.0,
                        flip=tgt["x"] < unit.x,
                        damage=spec["damage"] * nerf["damage"],
                        on_hit=self._on_bullet_hit,
                        color=(150, 226, 255) if is_fly else (255, 220, 140),
                        scale=0.9,
                        max_dist=distance,
                        target_y=SOLDIER_BASE["ground_y"] - 90.0,
                    )
                else:
                    unit.on_fire()

        # 空袭炸弹：落 0.5 秒落地爆炸，再留 0.55 秒播爆炸动画
        for b in self.airstrike_units:
            b["t"] += dt
            if not b["hit"] and b["t"] >= 0.5:
                b["hit"] = True
                self._airstrike_boom(b)
        self.airstrike_units = [b for b in self.airstrike_units if b["t"] < 1.05]

    def _summon_spec(self, unit):
        # 召唤物的战斗数值（来自 weapon/<name>.xml）
        name = getattr(unit, "name", "")
        w = self.weapons.get(name) or {}
        return dict(
            damage=float(w.get("damage") or 60),
            dist=float(w.get("shoot_distance") or FLY_RANGE),
        )

    def _mech_over(self):
        # Soldier::onMechOver @0x1894a8 —— 机甲结束，逐项还原。
        # 原版顺序：退出机甲态 → 还原血量上限/当前血量/护盾 →
        # updatHPBar → recoverSoldierHead → onChangeWeapon(this+424) 换回原武器。
        # 还是 mech_N 的数值（射速 1.3 秒/发那种）。
        self.mech_name = None
        self.mech_unit = None
        sv = getattr(self, "_mech_saved", None)
        if sv:
            self.move_speed = sv["speed"]
            self.maxhp = sv["maxhp"]
            self.hp = max(1, int(sv.get("hp") or self.maxhp))
            self.wdamage = sv["wdamage"]
            self.winterval = sv["winterval"]
            self.wdist = sv["wdist"]
            self.warea = sv["warea"]
            self.wbomb = sv["wbomb"]
            self.wcrit = sv["wcrit"]
            # 换回原武器（原版 Soldier::onChangeWeapon(this, this+424)）
            old = sv.get("weapon")
            if old and old != self.weapon:
                self.weapon = old
            self._mech_saved = None
        self.mech_damage_mult = 1.0

    MECH_BOOM_RADIUS = 300.0
    MECH_BOOM_DAMAGE = 1500.0

    def _mech_explode(self):
        """机甲血量见底 → 机甲爆炸 → 溅射伤害 → 退回角色形态。

        对周围有伤害，然后才能开始扣血条」。
        所以顺序是：血条清零的是**机甲**那一根 → 在原地炸开、把半径内
        僵尸清掉 → `_mech_over()` 把角色血条原样顶回来 →
        给 1 秒余波保护，之后僵尸才接着扣角色血。
        """
        if self.mech_name is None:
            return
        x = self.sx - self.cam + SOLDIER_RENDER_DX
        y = SOLDIER_FOOT_Y - 92.0
        self.gunfx.add_boom(x, y, dict(scale=0.62, duration=0.55))
        # 爆炸溅射：半径内所有僵尸吃全额伤害（原版 killZombiesOnExplosion
        # 的同类结算：半径 200 / 伤害 800，机甲自爆给得更高一些）
        for z in self.zombies:
            if z.get("dead") or z.get("dying") or z.get("hp", 0) <= 0:
                continue
            if abs(z["x"] - self.sx) <= self.MECH_BOOM_RADIUS:
                z["hp"] -= self.MECH_BOOM_DAMAGE
                z["hurt"] = 0.4
                z["last_dmg"] = self.MECH_BOOM_DAMAGE
                self.shot_back(z)
        # 机甲血条 → 角色血条（角色血条在机甲期间一丝没动）
        self._mech_over()
        self.invuln_until = self.time + 1.0
        with contextlib.suppress(Exception):
            if hasattr(self, "audio") and self.audio is not None:
                self.audio.mech_land()

    def _nearest_zombie(self, x, max_dist, any_dir=False):
        best, bd = None, max_dist
        for z in self.zombies:
            if z["dead"] or z.get("dying") or z["hp"] <= 0:
                continue
            d = abs(z["x"] - x)
            # 僵尸贴身站在士兵左侧 12px 时也必须可锁定。
            if d <= bd and (any_dir or z["x"] >= x):
                best, bd = z, d
        return best

    def _call_equipped_mech(self):
        """召唤存档里装备的机甲（进关卡时）。

        原版 PictureFactory::loadCurrentTexAsync @0x17a7b4 把 equipped_mech
        加进可用装备集合，士兵进关卡就是机甲形态。
        只有**真的拥有**（数量 > 0）才召唤 —— 否则 equipped_mech 是脏数据
        时会召唤出一台不存在的机甲。
        """
        save = getattr(self, "save", None)
        if save is None:
            return
        nm = save.d.get("equipped_mech")
        if not nm:
            return
        try:
            if hasattr(save, "mech_count") and save.mech_count(nm) <= 0:
                return
        except Exception:
            return
        from game.battle_abilities import ABILITY_DEFS

        self.call_mech(nm, float(ABILITY_DEFS.get(nm, (0.0, 45.0))[1]))
        try:
            if hasattr(save, "use_mech"):
                save.use_mech(nm)
                # 库存归零 → 同时卸下，别让军火库继续显示「已装备 ×0」
                if save.mech_count(nm) <= 0 and save.d.get("equipped_mech") == nm:
                    save.d["equipped_mech"] = None
                    save.save()
        except Exception:
            pass

    def call_mech(self, name, duration=45.0):
        """CallMechAbility：召唤机甲。

        反编译依据（all_merged.c:96042 Soldier::onMechGetup）：
            Soldier::onMechGetup { this[82] = 3; this[84] = 1;
                                   DelayTime(duration) → onCallMechFinished }
            Soldier::onCallMechFinished { this[448] = 1; this[252+19*4] = 0; }
        ⇒ **机甲不是独立实体，是士兵换装**：
          · this[82]=3 = 机甲状态
          · this[84]=1 = 立正（不能立刻走）
          · 到时后 onCallMechFinished 把 448（可操控）恢复成 1
        期间玩家操控的仍然是**同一个士兵**：左右移动、开火全都照常，
        只是外观变成机甲（BattleField::change2MechHead 换头像/骨骼）。

          「机甲是用来操控的，不是自动的」）。
          现在改成士兵换装：mech_name 存名字，渲染层换骨骼，
          移动/开火仍走玩家输入。
        """
        # ★ mech_7 是**炮塔**，不是换装。
        #   反编译 CallMechAbility::onMechGetup @0x1a4660：
        #       if (name == "mech_7") {
        #           BattleField::createAttackWeapon(field, "mech_7");
        #           return;                    ← 直接返回，不换装
        #       } else {
        #           Soldier::onChange2Mech(...);  ← 士兵变成机甲
        #       }
        #   createAttackWeapon @0x16db30：
        #       AttackWeapon::node(name) 放在 (士兵x - 150, 士兵y)，
        #       z = 2，然后 onGetup() 启动自动开火。
        #   ⇒ mech_7 玩家**不变身**，场上多一台自动炮塔；
        #     移速/血量/伤害都不变（不接管属性、不清药水 buff、不回血）。
        #   玩家自己变身，完全不是原版行为。
        if name == "mech_7":
            self._spawn_attack_weapon(name)
            return

        self.mech_name = name
        self.mech_until = self.time + duration
        self.buff_dur["mech"] = duration
        self.mech_power = True

        # ★ 机甲属性接管（Soldier::onChange2Mech @0x188e8c / 0x97385）：
        #     CharacterDef+56 = mech_blood   → this+67 = this+68（血量上限 + 当前血量）
        #     this+65        = speed         → 移速
        #     this+114       = 0.1f          → 护盾值（**不是**伤害倍率）
        #     removeAllAbilityFlag()         → 清掉身上所有药水增益
        #     updatHPBar(1.0)                → 血条回满
        #   数据源是 assets/raw/weapon/mech_N.xml 的
        #     <soldier mech_blood="1250" speed="180" min_interval="0.31">
        #     <weapon_effect damage="120" shoot_distance="330">
        #   —— **不是** level/mech_actors.xml 里的血/速/威力**档位**（1..12），
        #   那套档位只给军火库的属性展示条用。
        #   买 6000 金币的 mech_1 血量只有 250（原版 1250），
        #   而 mech_10 反而叠到 2.5 倍伤害（原版 160 比 ak47 的 75 只高 2 倍）。
        self._mech_saved = dict(
            weapon=self.weapon,
            speed=self.move_speed,
            maxhp=self.maxhp,
            hp=self.hp,
            wdamage=self.wdamage,
            winterval=self.winterval,
            wdist=self.wdist,
            warea=self.warea,
            wbomb=self.wbomb,
            wcrit=self.wcrit,
        )
        mw = self.weapons.get(name) or {}
        # 移速：机甲自己的 speed（原版 this+65）
        spd = float(mw.get("speed") or 0)
        if spd > 0:
            self.move_speed = spd
        # 血量上限：mech_blood 是绝对值
        blood = int(mw.get("mech_blood") or 0)
        if blood > 0:
            self.maxhp = blood
        # 武器数值：换成机甲自己的（原版 Soldier 的 weapon 就是 mech_N）
        if mw:
            self.wdamage = mw["damage"]
            self.winterval = mw["interval"]
            self.wdist = mw["shoot_distance"]
            self.warea = mw["area_damage"]
            self.wbomb = float(mw.get("bomb_radius", 0) or 0)
            # 机甲武器的命中判定/特效都按 mech_N 取
            self.weapon = name
        self.mech_damage_mult = 1.0
        # 血条回满（updatHPBar(1.0)）
        self.hp = self.maxhp
        # 清掉所有药水增益（removeAllAbilityFlag）
        self.speed_mult = 1.0
        self.power_mult = 1.0
        self.shield = 0.1
        self.speed_until = 0.0
        self.power_until = 0.0
        self.shield_until = 0.0
        # 落地爆炸（原版 killZombiesOnExplosion：半径 200、伤害 800）
        for z in self.zombies:
            if z["dead"] or z.get("dying"):
                continue
            if abs(z["x"] - self.sx) <= 220:
                z["hp"] -= 800
                z["hurt"] = 0.3
        with contextlib.suppress(Exception):
            self.audio.mech_land() if hasattr(self, "audio") else None

    def fly_weapon(self, name, duration=45.0):
        """FlyWeaponAbility：飞行武器。

        原版 createFlyWeapon → FlyWeapon::flyIn（从右侧飞入并持续射击），
        DelayTime(持续秒 + 0.5) 后 onFlyOver 移除。
        复刻：一件看得见的飞行武器悬在士兵右上方，持续开火。
        """
        self.fly_name = name
        self.fly_until = self.time + duration
        self.buff_dur["fly"] = duration
        try:
            from game.battle_summons import FlyWeapon

            _w = self.weapons.get(name) or {}
            _iv = _w.get("interval")
            self.fly_unit = FlyWeapon(
                name,
                self.sx,
                SOLDIER_BASE["ground_y"],
                interval=None if _iv is None else float(_iv) * FLY_NERF["interval"],
            )
        except Exception:
            self.fly_unit = None

    def skill_factors(self):
        return self.power_mult

    # ---- 随机技能掉落（RandomAbilityManager）----
    def is_firing(self):
        """触屏按住开火 或 键盘按住开火。两条通道分开记，互不清零。"""
        return bool(self.hold_fire or getattr(self, "key_fire", False))

    def is_moving(self):
        return bool(self.move_dir != 0 or self.key_left or self.key_right)

    def soldier_pose(self):
        """返回 (状态名, 动画时间)，与 draw_battle 的判定保持一致。

        开火 > 走路 > 站立。主循环 draw_battle 也用这个方法，
        两边不会再算出不同的姿势（之前 draw_battle 自己判一遍、
        特效这边猜一遍，枪口位置就对不上）。
        """
        # 机甲（装甲）形态：开火动画长度 = 机甲骨骼自己的 fire 帧数 / 20fps，
        # 由 mech_fire_left 控制，和士兵那条 0.30 秒的 muzzle 完全解耦。
        if getattr(self, "mech_name", None) and self.mech_fire_left > 0.0:
            return "fire", self.mech_fire_t
        if self.fire_hold > 0.0:
            # 连射时 fire_t 一直往前跑（动画自然循环），不每发归零
            return "fire", self.fire_t
        if self.is_moving():
            return "walk", self.time
        return "stand", self.time

    def soldier_pose2(self):
        """(上半身状态, t, 下半身状态, t) —— 支持「边跑边打」。

        原版 Soldier 的骨骼是 upper / lower 两层动画同时播的：
        上半身 fire_upper、下半身 walk_lower。我们只有一套 pose，
        完全盖住，位移却照旧执行 —— 玩家看到的就是「贴着地面滑步」。
        这里在「正在开火且正在移动」时把腿单独交给 walk，上身仍用 fire。
        """
        st, t = self.soldier_pose()
        if st == "fire" and not getattr(self, "mech_name", None) and self.is_moving():
            return st, t, "walk", self.time
        return st, t, None, None

    def mech_fire_anim_dur(self):
        """机甲开火动画的自然时长（帧数 / MECH_ANIM_FPS）。"""
        try:
            from game.battle_summons import MECH_ANIM_FPS, _mech_state_skeleton

            sk = _mech_state_skeleton(self.mech_name, "fire")
        except Exception:
            sk = None
            MECH_ANIM_FPS = 30.0
        if sk is None or sk.frame_count <= 0:
            return 0.30
        return max(0.12, sk.frame_count / MECH_ANIM_FPS)

    def fire_window(self):
        # 开火的命中窗口 (lo, hi)，世界坐标。
        # 反编译 WeaponEffect::onStartFire @0x1a1a30：
        #   朝右 → [中心+半宽, 中心+射程]；朝左 → [中心−射程, 中心−半宽]
        # 窗口是单向的，和 fire_target 共用同一套边界。
        # 贴近身体的僵尸仍在可射击窗口内，不能以角色半宽制造近战盲区。
        half_w = 0.0
        dist = self.wdist if self.wdist > 0 else 1e9
        if self.facing != 0:
            return self.sx + half_w, self.sx + dist
        return self.sx - dist, self.sx - half_w

    def fire_target(self):
        """当前能打到的目标（没有就 None）。

        反编译 WeaponEffect::onStartFire @0x1a1a30：
            if (a2 == 1) {  // Direction_Status = 1（右）
                v73 = centerX + v24;          // v24 = soldierWidth/2
                v26 = centerX + v25;          // v25 = shoot_distance
            } else {                          // 朝左
                v73 = centerX - v25;
                v26 = centerX - v24;
            }
        窗口是**单向**的：朝左时只打左边的僵尸，朝右时只打右边的。
        一枪都打不出去（身后的僵尸全部被排除）。

        目标还要「活着、没在播死亡动画」：hp<=0 之后还有 1.8 秒死亡动画，
        这期间它仍被当成目标，后面 3~4 枪全打在尸体上（实测 DPS 腰斩）。

        这个判定同时被开火逻辑和「开火键没有目标就变暗」的提示共用，
        保证两边的「有目标」永远是同一个标准。
        """
        lo, hi = self.fire_window()
        alive = [
            z
            for z in self.zombies
            if not z["dead"] and not z.get("dying") and z["hp"] > 0 and lo <= z["x"] <= hi
        ]
        if not alive:
            return None
        return min(alive, key=lambda z: abs(z["x"] - self.sx))

    def _spawn_gun_fx(self, tgt, state="stand", stime=0.0):
        """开火特效：枪口火光 + 弹道拖尾 + 弹壳。

        原版 WeaponEffect::addFireSparkEffect @0x19f508 用武器 XML 里的
        <FireSpark offset_x=".." offset_y=".." duration=".." tex="..">，
        位置是**武器节点局部坐标**（cocos，y 向上）。

        但我们居中绘制的精灵与原版的武器节点不在同一个坐标系，
        直接套 XML 的 offset 会差几十像素（实测火光落在枪口右边 90px）。
        所以枪口位置**从骨骼的枪部件直接算**（SoldierSprite.muzzle_point），
        保证和画出来的枪永远对得上。

        弹道拖尾：pic/gun/bullet_light.png（223×31，anchor(1.0,0.5)，
        opacity 0.45），从枪口水平飞向目标。

        弹壳：<BulletCase offset_x=".." offset_y=".." tex="..">，抛出后落地弹跳。

        ★ 近战武器（katana / axe / wrench / guitar / laser_sword / saw）：
          原版它们的 <weapon_effect> 是**空的** —— 既没有 <FireSpark>
          也没有 <BulletCase>，所以既不喷枪口火光、也不扔弹壳，
          挥砍的视觉完全靠上半身骨骼的 fire_upper 动画
          （<Flash animatioin_xml=".../laser_sword_fire_animations.xml">）。
        """
        if gfx.is_melee(self.weapon):
            self._spawn_melee_fx(tgt)
            return
        if getattr(self, "mech_name", None):
            self._spawn_mech_fx(tgt)
            return
        flip = self.facing == 0
        foot = SOLDIER_FOOT_Y
        # ★ 基准点必须是**渲染中心**（SOLDIER_RENDER_DX = app.constants
        #   SOLDIER_DX），不是武器节点中心：Skeleton.render 是按并集 bbox
        #   水平居中在 screen_x 上画的，用 SOLDIER_CENTER_DX 会整体偏 21px。
        base_x = self.sx - self.cam + SOLDIER_RENDER_DX
        d = -1.0 if flip else 1.0
        cfg = gfx.gun_effect_config(self.weapon) or {}
        sp_cfg = cfg.get("spark") or {}
        fx_off_x = float(sp_cfg.get("offset_x") or 0)
        fx_off_y = float(sp_cfg.get("offset_y") or 0)
        from game import soldier_sprite as ssprite

        sp = ssprite.get(self.weapon, getattr(self, "soldier", None), self.gun_look())
        # ★ 火光/弹壳/专属特效应统一钉在**画出来的枪口**上。
        #   offset_x，脚底 − offset_y），理由是「原版 WeaponEffectDef 把特效
        #   addChild 到武器节点」。但本复刻的士兵是**居中重排**的骨骼，武器
        #   节点坐标和 XML 的 300×300 画布不是一套坐标系 —— 实测 28 把枪
        #   的火光整体落在枪口**右上 100~120px 的空白里**（有的甚至飘到墙上
        #   的装饰枪上），弹壳也从半空往下掉，这就是「大部分武器特效诡异」。
        #   XML offset 现在只作为拿不到骨骼枪口时的兜底。
        mx = my = None
        gun_box = None
        if sp is not None:
            pt = sp.muzzle_point(state, stime, base_x, foot, 1.0, flip)
            if pt:
                mx, my = pt
            gun_box = sp.gun_box(state, stime, base_x, foot, 1.0, flip)
        if mx is None:
            mx = base_x + d * (fx_off_x or 100.0)
            my = foot - (fx_off_y or 150.0)
        # 稍微推出枪口一点，火药光才不会只盖住枪管半截
        mx += d * 8.0
        # 火光
        self.gunfx.add_muzzle_at(self.weapon, mx, my)
        # 弹壳：从枪膛（枪身后段、管线上方）抛出，而不是从脚底/半空
        cx, cy = mx, my
        if gun_box:
            cx = gun_box["left"] + gun_box["w"] * (0.30 if not flip else 0.70)
            cy = gun_box["top"] + gun_box["h"] * 0.40
        self.gunfx.add_case_at(self.weapon, cx, cy, flip)
        # ★ 每把武器**专属**的特效（原版 WeaponEffect::onStartFire
        #   @0x1a1a30 / all_merged.c:114790 逐类 addXXXEffect）：
        #   喷火枪 FireFlame、冰冻枪 FreezerWave、激光 laser_light、
        #   音波 SubsonicWave、雷击 ThunderFlash、火箭 Warhead。
        reach = float(self.wdist or 0)
        if reach <= 0:
            reach = 900.0
        _tgt_x = (tgt["x"] - self.cam) if tgt is not None else None
        self.gunfx.add_weapon_special(
            self.weapon,
            mx,
            my,
            base_x,
            foot,
            reach,
            flip,
            _tgt_x,
            damage=getattr(self, "_shot_damage", None),
            on_hit=self._on_warhead_hit,
            on_boom=self._on_warhead_boom,
        )
        if not self._has_own_projectile(cfg):
            ex = _tgt_x if _tgt_x is not None else mx + d * reach
            dist = max(60.0, abs(ex - mx))
            spd = 2600.0
            self.gunfx.add_trail(
                mx,
                my,
                vx=d * spd,
                life=max(0.07, min(0.16, dist / spd)),
                flip=flip,
                color=(255, 238, 168),
                scale=(0.14, 0.46),
                alpha0=0.85,
            )

    @staticmethod
    def _has_own_projectile(cfg):
        """该武器是否自带专属飞行物 / 光束（有则不再画白色弹道）。"""
        if not cfg:
            return False
        return any(cfg.get(k) for k in ("warhead", "laser", "sonic", "thunder", "flame", "freezer"))

    def _spawn_mech_fx(self, tgt):
        """机甲形态的开火特效（mech_actors.xml 的 FireSpark / BulletCase）。

        1) 位置：XML offset 是 350×350 机甲节点的局部坐标，本复刻的机甲
           骨骼只有 ~260×250、还要再乘 MECH_FORM_SCALE(0.78)。用
           mech_fx_point 换算后仍差 50~60px（原版节点原点和 bbox 中心不
           重合），所以现在直接取机甲骨骼里**炮管部件的前端**当炮口。
        2) 尺寸：FireSpark 的 scale 是按 350px 高的机甲调的（rocket
           spark 140px 帧 × 1.84 = 258px），套在只有 193px 高的机甲身上
           就是一团盖住半个身子的火球。统一乘 mech_k（机甲实际高度/350）。
        3) 缺失：mech_2/6/7 不在 mech_actors.xml 表里，mech_8/9/10 没有
           独立 FireSpark —— 退回 weapon/mech_N.xml，再兜底一张。
        """
        try:
            from game.shop_extra import load_mech_actors

            mdef = next((m for m in load_mech_actors() if m["name"] == self.mech_name), None)
        except Exception:
            mdef = None
        if not mdef:
            mdef = {}
        flip = self.facing == 0
        foot = SOLDIER_FOOT_Y
        d = -1.0 if flip else 1.0
        render_x = self.sx - self.cam + SOLDIER_RENDER_DX
        mech_bbox = mech_fx_bbox(self.mech_name)
        form_scale = SOLDIER_SCALE * MECH_FORM_SCALE

        # 机甲实际渲染高度 / 原版 350 节点高度：贴图尺寸的统一缩放系数
        mech_k = 1.0
        if mech_bbox:
            mech_k = (mech_bbox[3] - mech_bbox[1]) * form_scale / gfx.MECH_NODE_SIZE
        mech_k = max(0.35, min(1.0, mech_k))

        def fx_pos(off_x, off_y):
            return gfx.mech_fx_point(off_x, off_y, render_x, foot, mech_bbox, form_scale, d)

        # ★ level/mech_actors.xml 只给 7 台机甲写了独立 FireSpark，
        #   mech_8 / mech_9 / mech_10 一个都没有。
        sparks = mdef.get("sparks") or [mdef.get("spark")]
        own_fx = any(sp and sp.get("tex") for sp in sparks)
        cfg = gfx.gun_effect_config(self.weapon) or {}
        if not own_fx:
            own_sparks = cfg.get("sparks") or []
            sp_cfg = cfg.get("spark") or {}
            if own_sparks:
                sparks = [dict(sp) for sp in own_sparks]
            elif sp_cfg.get("tex"):
                sparks = [dict(sp_cfg)]
            else:
                sparks = [
                    {
                        "tex": "pic/gun/m134_fire_spark.png",
                        "offset_x": 270.0,
                        "offset_y": 250.0,
                        "duration": 0.10,
                        "row_count": 1,
                        "col_count": 1,
                        "scale": 1.0,
                    }
                ]

        # ★ 锚点：
        #   有原版 FireSpark 的机甲 —— 直接用 XML offset 经 mech_fx_point
        #   换算（原版就是按这套局部坐标挂特效的，换算后与炮口只差
        #   20~30px，比按部件名猜可靠：mech_3 的 "pao" 其实是腿部装甲，
        #   mech_7 的炮管还被拼成了 qianggaun）。
        #   没有 FireSpark 的（mech_8/9/10 徒手/臂炮）—— 退回骨骼里
        #   炮管/手部部件的前端。
        muzzle = None
        if own_fx:
            first = next(sp for sp in sparks if sp and sp.get("tex"))
            muzzle = fx_pos(float(first.get("offset_x") or 0), float(first.get("offset_y") or 0))
        if muzzle is None:
            try:
                from game.battle_summons import _mech_state_skeleton

                KEY = ("qiangguan", "qianggaun", "qiang", "pao", "gun", "wuqi", "shou")
                for st in ("fire", "stand", "walk"):
                    sk = _mech_state_skeleton(self.mech_name, st)
                    if sk is None or not sk.frame_count:
                        continue
                    cands = [
                        (nm, p)
                        for nm, p in sk.parts.items()
                        if p["w"] >= 18 and any(k in nm.lower() for k in KEY)
                    ]
                    if not cands:
                        continue
                    # 炮管取「最宽」的那块（横置的管子一定比枪机宽）
                    nm = max(cands, key=lambda kv: kv[1]["w"])[0]
                    pt = sk.part_point(
                        nm, 0, render_x, foot, 0.0 if flip else 1.0, 0.5, form_scale, flip
                    )
                    if pt:
                        muzzle = (pt[0] + d * 4.0, pt[1])
                        break
            except Exception:
                muzzle = None
        if muzzle is None:
            muzzle = fx_pos(270.0, 250.0)

        # 多组 FireSpark 的**相对**位置（同一台机甲的几个炮口/枪口）保留，
        # 但整体锚到炮口上；单组时就是炮口本身。
        offs = [
            (float(sp.get("offset_x") or 0), float(sp.get("offset_y") or 0))
            for sp in sparks
            if sp and sp.get("tex")
        ]
        bo_x, bo_y = offs[0] if offs else (270.0, 250.0)
        for sp in sparks:
            if not sp or not sp.get("tex"):
                continue
            img = res.load_img(sp["tex"])
            if not img:
                continue
            sx = muzzle[0] + (float(sp.get("offset_x") or 0) - bo_x) * mech_k
            sy = muzzle[1] - (float(sp.get("offset_y") or 0) - bo_y) * mech_k
            rows = int(sp.get("row_count", 1) or 1)
            cols = int(sp.get("col_count", 1) or 1)
            # ★ 机甲火花必须收敛：
            #   rocket_fire_spark.png 是整段「火箭发射」（爆闪 → 浓烟 →
            #   扩散黑烟）的 6 帧动画，XML 里 scale 2.6 是给 350px 机甲
            #   的倍率，直接乘出来是一根比机甲还高的黄烟柱，画面上就是
            #   「机甲在原地被轰炸」。机甲只播前半段（爆闪 + 小烟），
            #   缩放压到炮口尺寸。
            k = min(float(sp.get("scale", 1.0) or 1.0), 1.15) * mech_k
            dur = min(float(sp.get("duration", 0.3)), 0.18)
            self.gunfx.grids.append(
                gfx.GridAnim(
                    img, rows, cols, sx, sy, dur, k, flip, max_frames=max(1, (rows * cols) // 2)
                )
            )
        case_items = mdef.get("cases") or ([mdef.get("case")] if mdef.get("case") else [])
        if not case_items:
            case_items = cfg.get("cases") or []
        for bc in case_items:
            if not bc or not bc.get("tex"):
                continue
            img = res.load_img(bc["tex"])
            if not img:
                continue
            # 弹壳从炮膛后段抛出（炮口往回收 45px）
            cx = muzzle[0] - d * 45.0
            cy = muzzle[1] + 8.0
            vx = (-1.0 if not flip else 1.0) * random.uniform(120.0, 220.0)
            self.gunfx.cases.append(
                gfx.BulletCase(img, cx, cy, vx, -random.uniform(200.0, 320.0), flip)
            )
        _tx = (tgt["x"] - self.cam) if tgt is not None else None
        if _tx is None:
            _tx = muzzle[0] + d * max(140.0, float(self.wdist or 330))
        _dist = max(60.0, abs(_tx - muzzle[0]))
        _spark_tex = next((sp.get("tex") or "" for sp in sparks if sp and sp.get("tex")), "")
        # ★ 命中才结算：这一发的伤害挂在飞行物上（见 _on_bullet_hit）
        _dmg = float(getattr(self, "_shot_damage", 0.0) or 0.0)
        # 子弹最远飞到「射程边界」为止（屏幕坐标）：
        #   弹丸会越过射程窗口继续飞，看着就是「打得很远却打不到」。
        _range = float(self.wdist or 0) or 900.0
        _edge = self.sx - self.cam + (d * _range)
        _max_dist = max(60.0, abs(_edge - muzzle[0]) + 24.0)
        if "rocket" in _spark_tex:
            self._shot_bullet = self.gunfx.add_rocket_visual(
                muzzle[0] + d * 12.0,
                muzzle[1],
                flip=flip,
                scale=max(0.45, min(1.0, mech_k * 1.5)),
                speed=920.0,
                boom_cfg=dict(scale=0.52, duration=0.5),
                damage=_dmg,
                on_hit=self._on_warhead_hit,
            )
        else:
            if self.mech_name in ("mech_8", "mech_9", "mech_10"):
                _color = (150, 226, 255)
            elif self.mech_name == "mech_3":
                _color = (255, 232, 160)
            else:
                _color = (255, 220, 140)
            # 霰弹（mech_3）三颗：只有中间那颗带伤害，其余是散开的曳光，
            # 免得同一发把伤害算三遍。
            _pellets = (
                ((-9.0, 0.8, 0.0), (2.0, 1.0, 1.0), (13.0, 0.75, 0.0))
                if self.mech_name == "mech_3"
                else ((0.0, 1.0, 1.0),)
            )
            _speed = max(1500.0, _dist / 0.14)
            self._shot_bullet = None
            for _dy, _sc, _dm in _pellets:
                b = self.gunfx.add_bullet(
                    muzzle[0] + d * 6.0,
                    muzzle[1] + _dy * mech_k,
                    speed=_speed,
                    flip=flip,
                    damage=(_dmg * _dm),
                    on_hit=self._on_bullet_hit,
                    color=_color,
                    scale=_sc,
                    max_dist=_max_dist,
                )
                if _dm > 0:
                    self._shot_bullet = b
        _ = tgt

    def _on_warhead_hit(self, w, z):
        """弹头真的撞上僵尸才扣血（Bubble::onUpdate / Rocket::onExplosion）。

        开火瞬间只生成弹头，命中这一帧才走 Zombie::onDamage。
        """
        if z.get("dead") or z.get("dying") or z.get("hp", 0) <= 0:
            return
        dmg = float(getattr(w, "damage", 0.0) or 0.0)
        if dmg <= 0:
            return
        z["hp"] -= dmg
        z["hurt"] = 0.25
        z["last_dmg"] = dmg
        self.shot_back(z)
        if self.freeze_weapon():
            self.freeze_zombie(z)
        self.fx.add_blood(z["x"] - self.cam, SOLDIER_BASE["ground_y"] - 90)

    def _on_bullet_hit(self, b, z):
        """实体子弹命中僵尸：只结算被撞上的这一只（不做 range 溅射）。

        ★ 伤害在**开火那一帧**就锁定挂在子弹上（b.damage），
          落地时才结算 —— 中途换枪/机甲结束都不会改这一发。
        """
        self._apply_hit(z, float(getattr(b, "damage", 0.0) or 0.0), area=False)

    def _on_warhead_boom(self, w):
        """弹头爆炸的**溅射**（weapon_effect area_damage / bomb_radius）。

        原版 Rocket::onExplosion / Grenade 落地都对半径内所有僵尸结算。
        一个，看起来「爆炸是假的」。被直接命中的那只已在 _on_warhead_hit
        里吃了全额伤害，这里跳过它，避免同一发算两次。
        """
        radius = float(getattr(w, "radius", 0.0) or 0.0)
        dmg = float(getattr(w, "damage", 0.0) or 0.0)
        if radius <= 0 or dmg <= 0:
            return
        wx = w.x + self.cam
        for zz in self.zombies:
            if zz is getattr(w, "direct", None):
                continue
            if zz.get("dead") or zz.get("dying") or zz["hp"] <= 0:
                continue
            if abs(zz["x"] - wx) > radius:
                continue
            zz["hp"] -= dmg * 0.55
            zz["hurt"] = 0.25
            zz["last_dmg"] = dmg * 0.55
            self.shot_back(zz)
            self.fx.add_blood(zz["x"] - self.cam, SOLDIER_BASE["ground_y"] - 90)

    def _spawn_melee_fx(self, tgt):
        """近战挥砍 —— 原版**没有**独立特效，挥砍就是骨骼的 fire_upper 动画。

        反编译 WeaponEffect::onStartFire 里近战武器（katana / axe / wrench /
        guitar / laser_sword / saw）的 <weapon_effect> 是空的：既不 addFireSpark
        也不 addBulletCase，砍中的反馈只有两处 ——

          1. `<Flash animatioin_xml=".../<gun>_fire_animations.xml">`：
             28 帧里武器部件（axe 的 fuzi / katana 的 qiubang）自己从
             −26° 甩到 −126° 再回到 +12°，就是那一刀；
          2. 命中僵尸时的血光（_hurt_zombie → fx.add_blood）。

        结果画面里同时有两把刀/斧：手里一把不动的、空中一把乱转的
        现在只留骨骼动画那一把。
        """
        return

    def _clear_ability_drops(self):
        """地图/关卡切换（reset 里 zone 变化）时清掉上一关残留的掉落物。"""
        self.ability_drops = []

    def _dedup_ability_drops(self):
        """按 (技能名, 落点) 去重：连续击杀 / 换图时不叠两个一样的瓶子。"""
        seen, out = set(), []
        for d in self.ability_drops:
            key = (d.name, round(d.x / 48.0))
            if key in seen:
                continue
            seen.add(key)
            out.append(d)
        self.ability_drops = out

    def _maybe_drop_ability(self, z):
        """RandomAbilityManager::onZombieDead @0x18359c：携带道具的僵尸才掉。

        原版三个条件（all_merged.c:87485）：
          · this+5 < this+3   —— 已掉落数未达上限（this+3 = randInt(2,3)，每关 2~3 个）
          · this+6 == 0       —— 场上没有待拾取的掉落物
          · 士兵身上没有生效技能（Soldier::isInAbility）

        ★ 最前面还要判 Zombie::hasItem / carryAbility：道具在**出生**时
          挂到具体僵尸身上（见 _spawn），不是每只僵尸死了都掷一次骰子。
        """
        if not z.get("has_item") or not z.get("carry_ability"):
            return
        # 先判环境，再消耗 has_item —— 否则被拦下的那一次会白白吃掉道具
        if self.ability_drops:
            return  # 场上已有掉落物就不再掉
        if getattr(self, "ability_drop_cd", 0.0) > 0:
            return  # 上一个刚被捡走，隔一会儿再掉
        if getattr(self, "exp_weapon_item", None):
            return  # 场上已经有经验武器道具了
        if self.shield > 0 or self.power_mult > 1.0 or self.speed_mult > 1.0:
            return  # 士兵正在生效技能
        if self.ability_dropped >= self.ability_drop_max:
            return  # 本关掉落数已达上限
        z["has_item"] = False  # 一次性，死亡只触发一次
        from game.random_abilities import AbilityDrop

        name = z["carry_ability"]
        self.ability_drops.append(AbilityDrop(name, z["x"], SOLDIER_BASE["ground_y"]))
        self._dedup_ability_drops()
        self.ability_dropped += 1

    def _tick_ability_drops(self, dt):
        """掉落物向士兵移动，进入范围即拾取并触发技能。

        ★ 拾取后给一个间隔（ABILITY_DROP_GAP 秒）：不这样的话，一条命里
          连续几只携带道具的僵尸死掉，药水一个接一个往地上冒，玩家看到
        """
        if getattr(self, "ability_drop_cd", 0.0) > 0:
            self.ability_drop_cd = max(0.0, self.ability_drop_cd - dt)
        if not self.ability_drops:
            return
        alive = []
        for d in self.ability_drops:
            if d.update(dt, self.sx):
                self._trigger_dropped_ability(d.name)
                self.ability_drop_cd = ABILITY_DROP_GAP
            else:
                alive.append(d)
        self.ability_drops = alive

    def _trigger_dropped_ability(self, name):
        """UIBoard::onTriggerRandomAbility：触发掉落的技能。"""
        self.apply_ability(name)
        self.msg = name
        self.msg_t = 2.0

    def apply_ability(self, name):
        """施加一个技能并播它的特效。

        掉落拾取（_trigger_dropped_ability）和玩家按键
        （AbilityBar.trigger）走的是同一套效果，所以统一在这里做。

        ★ 特效（原版 pic/effect/ability/）：
          · 治疗（hp）    → RecoverHPAbility：播**一次**上升光柱，scale 0.7
          · 护盾 / 加速 / 力量 → TemporaryAbility：触发瞬间播一次，
            持续期间**循环**播放，scale 0.6
        """
        from game.battle_abilities import ABILITY_DEFS, ability_kind

        p1, p2 = ABILITY_DEFS.get(name, (0.0, 0.0))
        kind = ability_kind(name)
        if kind == "hp":
            self.hp = min(self.maxhp, self.hp + self.maxhp * p1)
            self._ability_fx_once(p2, (150, 255, 170), ability=name)
        elif kind == "speed":
            self.speed_mult = p1 + 1.0
            self.speed_until = self.time + p2
            self.buff_dur["speed"] = p2
            self._ability_fx_loop(p2, (150, 255, 235), ability=name)
        elif kind == "power":
            self.power_mult = p1 + 1.0
            self.power_until = self.time + p2
            self.buff_dur["power"] = p2
            self._ability_fx_loop(p2, (255, 190, 110), ability=name)
        elif kind == "shield":
            self.shield = p1
            self.shield_until = self.time + p2
            self.buff_dur["shield"] = p2
            self._ability_fx_loop(p2, (150, 200, 255), ability=name)
        elif kind == "airstrike":
            self._ability_fx_once(1.2, (255, 220, 150), ability=name)
            self.airstrike(p2)
        return kind

    def _ability_fx_once(self, duration=1.2, color=(150, 255, 170), ability=None):
        """一次性技能特效；ability 决定官方图标，而非由播放方式猜测。"""
        if self.ability_fx is None:
            return
        self.ability_fx.add(
            "once", duration=max(0.5, min(1.6, duration)), color=color, ability=ability
        )

    def _ability_fx_loop(self, duration=15.0, color=(180, 220, 255), ability=None):
        """护盾 / 加速 / 力量：持续期间循环的光罩。"""
        if self.ability_fx is None:
            return
        d = max(0.5, float(duration))
        # 触发瞬间的一次 + 持续循环，两者保持同一道具身份。
        self.ability_fx.add("once", duration=0.9, color=color, ability=ability)
        self.ability_fx.add("loop", duration=d, color=color, ability=ability)

    def day(self):
        """当前关卡所在的天数（level_list.xml 的 level 字段）。"""
        info = self.level_db.get(self.mission_id, {})
        return int(info.get("level", 1))

    # ---- 提示 ----
    def notify(self, msg):
        """战斗内的一次性提示（App 在创建 Battle 时把 toast 挂到 toast_cb 上）。"""
        cb = getattr(self, "toast_cb", None)
        if callable(cb) and msg:
            cb(msg)

    # ---- 经验武器（ExpWeaponItemManager）----
    def _tick_exp_weapon(self, dt):
        """经验武器道具：生成 → 随镜头右移 → 靠近士兵即拾取。

        ExpWeaponItemManager::checkAndCreatItem：按关卡 level 决定掉哪把枪，
        位置 (士兵x + LOGIC*180, LOGIC*100)。
        ExpWeaponNode::onUpdate @0x186c1c：
            item.x += dt（跟相机同速右移，不追着士兵跑）
            |士兵中心x - item.x| / 2 <= 道具宽*0.5 ⇒ hitAnimation → hitItemNode
        """
        from game.exp_weapon import EXP_BULLETS, ITEM_OFFSET_X, ITEM_W, ITEM_Y, pick_exp_weapon

        if self.exp_weapon_cd > 0.0:
            self.exp_weapon_cd = max(0.0, self.exp_weapon_cd - dt)
            return
        if self.exp_weapon_item is None:
            if self.save is None:
                return
            pick = pick_exp_weapon(self.save.d, self.day())
            if not pick:
                return
            key, gun = pick
            # 生成位置：士兵中心 x + LOGIC*180
            self.exp_weapon_item = dict(
                key=key,
                gun=gun,
                x=self.sx + SOLDIER_CENTER_DX + ITEM_OFFSET_X,
                y=ITEM_Y,
                taken=False,
            )
            return
        it = self.exp_weapon_item
        # 道具不追着士兵跑，只随镜头右移（屏幕 x = 世界 x - cam）
        # ExpWeaponNode::onUpdate @0x186c1c：
        #   道具世界 x += dt（每秒 +1 逻辑像素，相对背景缓慢右移）
        #   命中判定：|士兵中心x - 道具x| <= 道具宽 * 0.5
        #     （反编译里那个 COERCE_FLOAT((2*diff)>>1) 是整数右移，值就是 |diff|）
        # 「道具宽」是枪图标精灵的 contentSize 宽（gun_uzi = 69），
        # 不是节点 contentSize（150）：用 150 会让判定恒成立、道具一出现就被拾走
        # （实测原版道具一直留在场上）。
        it["x"] += dt
        from game.exp_weapon import gun_icon_width

        if abs(self.sx + SOLDIER_CENTER_DX - it["x"]) <= gun_icon_width(it["gun"]) * 0.5:
            if getattr(self, "mech_name", None):
                if getattr(self, "exp_hint_cd", 0.0) <= 0.0:
                    self.exp_hint_cd = 2.5
                    self.notify("机甲状态无法拾取武器")
            else:
                it["taken"] = True
                self._take_exp_weapon(it)
        self.exp_weapon_item = None if it["taken"] else it

    def _take_exp_weapon(self, it):
        """ExpWeaponItemManager::hitItemNode：机甲直接召唤，其余换成经验武器。

        反编译 @0x186acc：拾取后把存档标记 <key> 置 1 并 save，
        记录当前经验武器名（UIBoard+492），然后移除节点。
        没有额外的「last_exp_weapon」存档项 —— 那个字段不存在。
        """
        gun = it["gun"]
        # 兜底：机甲形态一律不换枪（拾取入口已经在 _update_exp_weapon 挡掉了，
        # 这里再挡一次，免得别的调用路径又把机甲顶掉）。
        if getattr(self, "mech_name", None):
            return
        if gun.startswith("mech"):
            from game.battle_abilities import ABILITY_DEFS

            self.call_mech(gun, float(ABILITY_DEFS.get(gun, (0.0, 45.0))[1]))
        else:
            self.use_exp_weapon(gun)
        if self.save is not None:
            self.save.d[it["key"]] = 1
            if hasattr(self.save, "save"):
                self.save.save()
        self.exp_weapon_item = None
        self.exp_weapon_cd = 8.0  # 8 秒后才刷下一把

    def use_exp_weapon(self, name):
        """Soldier::onChangeToExpWeapon：换上一把限时经验武器（100 发）。

        原来的枪记在 normal_weapon 里，子弹打完自动换回。

        ★ 原版顺序（反编译 @0x18978c）：
            换枪（ Soldier::onChangeWeapon 风格的初始化）
            → 写 <name>_bullet = 100
            → 置 this[508] = 1（进入「经验武器模式」，此后禁止手动换枪）
          所以这里先置 exp_weapon 再换枪会被自己的禁止逻辑挡住，
          必须用一个内部标志绕开。
        """
        if not getattr(self, "exp_weapon", None):
            self.normal_weapon = self.weapon
            self.normal_weapon_bullets = self.bullet_count()
        self.exp_weapon = name
        self._exp_weapon_name = name  # 放行「未购买」检查
        self.exp_bullets_left = 100
        if self.save is not None:
            self.save.d["%s_bullet" % name] = 100
        # 绕过「经验武器期间禁止手动换枪」的限制来换上这把枪
        self._switching_exp = True
        try:
            self.change_weapon(name)
        finally:
            self._switching_exp = False
        self.exp_bullets_left = 100
        return True

    def end_exp_weapon(self):
        """Soldier::onWeaponFire：经验武器打完 → 换回原枪。

        原版这里才把 this[508] 置 0（解除禁切），再 onChangeWeapon 回原枪。
        """
        if not getattr(self, "exp_weapon", None):
            return
        old = getattr(self, "normal_weapon", None)
        # 先解除限制，再换回原枪（换回动作本身不受禁切影响）
        self.exp_weapon = None
        self._exp_weapon_name = None
        if old:
            self.change_weapon(old)
            if self.save is not None:
                self.save.d["%s_bullet" % old] = int(getattr(self, "normal_weapon_bullets", 0) or 0)

    # ---- 初始化 ----
    def reset(self):
        info = self.level_db.get(self.mission_id, {})
        self.zone = info.get("zone", "hospital")
        self.waves = info.get("waves") or [dict(name="zombie_9", update_time=3.0, capacity=10)]
        self.mtype = info.get("type", "kill_mission")
        self.quota = info.get("number", 10)
        self.quota2 = info.get("number2", 0)
        self.reward_coin = info.get("reward_coin", 800)
        self.reward_crystal = info.get("reward_crystal", 1)
        # 任务构成：前缀决定计数器，"_time" 后缀追加倒计时限制
        #   kill / distance / guard / hostage / collect
        self.base_type = self.mtype.split("_time_mission")[0].split("_mission")[0]
        self.timed = self.mtype.endswith("_time_mission")
        self.time_limit = float(self.quota2) if self.timed and self.quota2 else 0.0

        w = self.wstat()
        self.wdamage = w["damage"]
        self.winterval = w["interval"]
        self.wcrit = w["crit_rate"]
        self.wdist = w["shoot_distance"]
        self.warea = w["area_damage"]
        # 爆炸溅射半径（原版 WeaponEffectDef 的 bomb_radius 字段，
        # 反编译 all_merged.c:115542 写入 +12）。
        # 0 = 该武器没有爆炸半径（近战 / 直线枪），沿用默认范围。
        self.wbomb = float(w.get("bomb_radius", 0) or 0)

        # 士兵属性（upgrade.xml 的 blood_level / speed_level / armor_level）
        self.maxhp = self.soldier_stat("blood", SOLDIER_BASE["hp"], self.save)
        self.move_speed = self.soldier_stat("speed", SOLDIER_BASE["speed"], self.save)
        self.armor = self.soldier_stat("armor", 0.0, self.save)  # 受伤减免比例
        # ★ 角色天赋（Soldier::applySoldierTalent @0x1879fc）：
        #     soldier_2  speed  *= 1.2
        #     soldier_3  atk_dist += 0.2
        #     soldier_4  damage *= 1.2
        #   花钱买个贵角色只多了点血，天赋（差异化卖点）形同不存在。
        self.talent_speed = 1.0
        self.talent_damage = 1.0
        self.talent_atk_dist = 0.0
        self._apply_soldier_talent()
        self.move_speed *= self.talent_speed
        self.hp = self.maxhp
        # 技能状态（Soldier::speedUp / powerUp / shieldUp 的字段）
        self.speed_mult = 1.0
        self.power_mult = 1.0
        self.shield = 0.0
        self.speed_until = 0.0
        self.power_until = 0.0
        self.shield_until = 0.0
        self.mech_until = 0.0
        # 每种临时增益的总时长（HUD 画剩余进度条要用：总时长 → 剩余比例）
        self.buff_dur = {}
        self.fly_until = 0.0
        self.mech_name = None
        self.fly_name = None
        self.mech_unit = None  # 看得见的机甲实体
        self.mech_damage_mult = 1.0  # 机甲形态的伤害倍率（onChange2Mech）
        self._mech_saved = None  # 机甲期间的原始属性快照
        self.invuln_until = 0.0  # 机甲自爆后的余波保护（秒）
        self.fly_unit = None  # 看得见的飞行武器实体
        self.attack_unit = None  # mech_7 炮塔（AttackWeapon，独立自动开火）
        self.attack_until = 0.0
        self.airstrike_fx = 0.0
        self.airstrike_units = []  # 空袭炸弹（落地动画）
        # 否则换图后旧药水还挂在场景里、同一落点会叠两个瓶子。
        self._clear_ability_drops()  # RandomAbilityManager 的地面掉落物
        # ★ 技能生效特效（原版 pic/effect/ability/）
        self.ability_fx = AbilityFxLayer()
        # ★ 击杀赏金特效（原版 BattleField::addCoinBonus 的星星）
        self.kill_bonus_fx = KillBonusLayer()
        # 最近一次击杀的赏金（App 层读它来发钱 + 飘「+N」）
        self.last_kill_bonus = 0
        self.last_kill_x = 0
        self.last_kill_y = 0
        _day = self.day()
        self.ability_drop_max = 0 if _day <= 2 else (1 if _day % 2 else 2)
        self.ability_dropped = 0
        # 拾取后的掉落间隔（秒）：保证「一次只有一个道具在地上」，
        # 不会一关里噼里啪啦冒出三四个
        self.ability_drop_cd = 0.0
        self.exp_weapon_item = None  # ExpWeaponItemManager 的经验武器道具
        self.exp_weapon_cd = 0.0  # 拾取后到下一把刷出的冷却
        self.exp_weapon = None  # 当前装备的经验武器名
        self.exp_bullets_left = 0  # 经验武器剩余发数
        self.normal_weapon = None  # 换经验武器前的原枪
        self.normal_weapon_bullets = 0
        self.kills = 0
        self.boss_kills = 0  # 本关 boss 击杀数（total_boss_kills 统计用）
        self.leaked_count = 0  # 本关漏过传送门的僵尸数（daily_vungles 统计用）
        self._stats_written = False  # 防止 finish() 重复累加全局统计
        self.zombies = []
        self.fx = zfx.EffectLayer()
        self.gunfx = gfx.GunFxLayer()  # 枪口火光 / 弹道 / 弹壳
        self.fire_cd = 0.0
        self.over = None  # None / "win" / "lose"
        self.result = None  # 结算数据 dict
        self.combo = 0
        self.combo_max = 0
        self.combo_t = 0.0
        self.time = 0.0
        self.hold_fire = False
        self.move_dir = 0
        # 键盘输入（A/D）。和 move_dir 分开记：mouse 的 move_dir 是
        # 按住时由 click 设的，键盘是按下/松开成对的；两者取或。
        self.key_left = False
        self.key_right = False
        self.key_fire = False
        self.facing = 1
        self.muzzle = 0.0  # 开火枪口闪光计时
        self.fire_t = 0.0
        self.fire_hold = 0.0
        # 机甲（装甲）形态的开火动画计时：骨骼动画按自身帧数自然播放，
        # 不能被士兵那条 0.30 秒的 muzzle 截断。
        self.mech_fire_t = 0.0
        self.mech_fire_left = 0.0
        self.shots = 0  # 开火次数（ComboKillEffect::onWeaponFire 触发源）
        self._multi_queue = []  # MultipleFire 待补射的时间点（mech_8/9/10）
        self.hits = []  # 命中特效 [(x, y, t)]
        self._pending_hits = []
        # ---- 任务型专用状态 ----
        self.dist_m = 0.0  # distance：已行进距离
        # 「往右走」箭头剩余显示秒数（原版 showGoRightAnimation 播完自动移除）
        self.go_right_t = 0.0
        self.guard_left = 0.0  # guard：守卫剩余秒数
        self.leak_left = self.quota  # guard：允许漏过的僵尸数（LeakCounter）
        self.saved = 0  # hostage：已救人数
        self.collected = 0  # collect：已拾取数
        self.hostages = []  # 人质实体
        self.pickups = []  # 采集物实体
        self.msg = ""  # 开场提示（原版 chat_dialog）
        self.msg_t = 0.0
        # 「机甲状态无法拾取武器」这类一次性提示的节流冷却
        self.exp_hint_cd = 0.0
        # 续天（BattleScene::onReviveSoldier @0x16597c）：
        # 士兵死亡后弹「续天(N)」对话框，**花钻石**复活，可续多次。
        # ★ 原版 DialogLevelSaveMe::getCrystalNode @0x14759c 显示的是
        #   钻石图标 + 数字（原文写死 "5"）—— 复活消耗的是钻石不是金币。
        self.revive_left = 9
        self.revive_cost = 1  # 消耗的钻石数量
        self.dead = False
        # 世界坐标：战区横向卷动，屏幕 x = 世界 x − cam
        self.world_w = self._world_width()
        self.sx = float(SOLDIER_SCREEN_X)
        # 出发时的世界坐标：行走关的「已走距离」直接由世界位移算
        # （见 _tick 里的 dist_m），不再累加每帧位移的绝对值。
        self.start_x = self.sx
        self.cam = 0.0
        if self.base_type == "guard":
            self.guard_left = float(self.quota2 or 60)
        self._init_mission_entities()
        # ★ 虫洞（守卫任务专用，原版 BattleField::addWormholeEffect
        #   @0x16df74，all_merged.c:149594 —— guard_mission 才会建）。
        self.wormhole = None
        if self.base_type == "guard":
            # 原版 pos.y = H*0.42 是 cocos 的 y 向上，换到屏幕坐标得镜像；
            # 位置贴左边（僵尸从这里漏出去）。
            _wh = 200 * 0.62
            self.wormhole = Wormhole(0.0, GROUND_Y - _wh * 0.42)
        # ★ 远行任务的终点目标（原版 BattleField::addDistanceTarget
        #   @0x16e13c：医疗箱 + pic/effect/add_time/ 的循环光效）。
        # ★ 终点的世界 x：胜利条件是「走了 quota 公里」，起点是屏幕
        #   SOLDIER_SCREEN_X，所以终点 = 起点 + quota*100px。
        #   靠前一大截，玩家走到底时图标早就被甩到屏幕左边去了。
        self.goal_x = SOLDIER_SCREEN_X + self.quota * DIST_PX_PER_UNIT
        self.distance_target = None
        if self.base_type == "distance":
            # 终点图标必须与胜利判定点共用同一个 x，否则玩家会提前触发胜利。
            self.distance_target = DistanceTarget(self.goal_x, GROUND_Y - 127 * 0.5)
        # ★ 护送关的撤离点：直升机（详见 game/evac_heli.py）。
        self.evac = None
        if self.base_type == "hostage":
            self.evac = EvacHeli(self.goal_x + 100.0, GROUND_Y + 10.0)
        # 机甲不自动召唤：它是消耗品，由战斗界面上的机甲槽手动使用。

    def _world_width(self):
        """战区总长（世界像素）。1 公里 = 260px。"""
        bt = self.base_type
        if bt in ("distance", "hostage"):
            # ★ 战区长度要跟**真正的终点**对齐：胜利条件是走够
            #   quota 公里（1 单位 = 100px，起点 SOLDIER_SCREEN_X），
            #   玩家冲线时终点图标早被甩到屏幕左边几千像素外
            #   现在终点后面只留一屏，冲线时图标就在眼前。
            return SOLDIER_SCREEN_X + self.quota * DIST_PX_PER_UNIT + 854.0
        if bt == "collect":
            # 收集关：路线固定长度，钥匙均匀铺在前方
            return 1200.0
        return 1400.0

    def _init_mission_entities(self):
        """人质/采集物的初始布置。

        原版只有一个人质（BattleField 字段 +103 是单指针）：
        hostage_mission 的 number 是「护送到 N 公里外的撤离点」的距离。
        collect_mission 的 number 是要收集的钥匙数。
        """
        if self.base_type == "hostage":
            # ★ 人质**跟在士兵身后**（士兵开路、人质断后）。
            #   护送关全灭（实测 13 个 hostage 关全部 lose）。
            #   反编译 Hostage::onUpdate @0x1a6b5c 也是拿
            #   Soldier::getCenterXInBattleFiled 跟人质比：
            #   士兵在前（士兵 x > 人质 x）时人质才往前跟，方向位 86=1。
            self.hostages.append(
                dict(
                    x=max(0.0, self.sx - 200.0),
                    hp=500.0,
                    maxhp=500.0,
                    walk=random.random(),
                    saved=False,
                    dead=False,
                    stand=False,
                    idx=0,
                )
            )
        elif self.base_type == "collect":
            # ★ 钥匙在关卡初始化时一次铺好（预生成）；换图 / 重新初始化
            #   时若已铺过就不再追加，避免同一位置叠两把钥匙。
            if self.pickups:
                return
            self.key_spawned = 0
            self._spawn_next_key(520.0)

    def _spawn_next_key(self, x):
        """在 x 处放下一把钥匙（收集关一次只存在一把）。"""
        x = max(320.0, min(float(x), self.world_w - 200.0))
        self.pickups.append(
            dict(x=x, y=SOLDIER_BASE["ground_y"] - 18, t=random.random() * 6.28, got=False)
        )
        self.key_spawned = getattr(self, "key_spawned", 0) + 1

    # ---- 刷新 ----
    def _alive_count(self, name):
        """某种僵尸的同屏存活数（容量判定用）。"""
        return sum(1 for z in self.zombies if not z["dead"] and z["name"] == name)

    def _spawn(self, name, wave=None):
        zs = self.zstats.get(name)
        boss = name.startswith("boss_")
        if zs:
            hp, spd, atk = zs["hp"], zs["speed"], zs["atk"]
            stand, scale = zs["stand_distance"], zs["scale"]
            atk_dist = zs["attack_distance"]
            delay = zs.get("attack_delay") or [1.0]
        else:
            hp, spd, atk, stand, scale = 60, 120, 40, 65, 1.2
            atk_dist = 110
            delay = [1.0]
        # 关卡 xml 的 add_blood / add_speed 是百分比加成
        # （Zombie::addBlood / addSpeed：hp * (1 + a)）
        if wave:
            hb = wave.get("add_blood", 0)
            hs = wave.get("add_speed", 0)
            if hb > 0:
                hp *= 1.0 + hb
            if hs > 0:
                spd *= 1.0 + hs
        # 原版 Zombie::init：attack_distance / stand_distance 乘 1.1
        # （EzMathUtils::randInt(11, 11) / 10.0 —— 编译器折叠成常量）
        jitter = 1.1
        # 原版 stand_distance 从僵尸**身体左边缘**量到士兵中心；
        # 本复刻 z["x"] 是包围盒中心，所以补上半个身位（随 scale 缩放）。
        from game import zombie_sprite as _zs

        death_dur = 1.8
        atk_dur = 0.8
        try:
            sp = _zs.get(name)
            death_dur = sp.durations.get("death") or 1.8
            atk_dur = sp.durations.get("attack") or 0.8
        except Exception:
            pass
        # 原版参考帧（emu_fire0.png, 1280 宽）：士兵中心 645、僵尸左缘 767，
        # 差 122 屏幕像素 = 81 逻辑像素 ≈ stand_distance 65 × 1.1。
        # 说明 stand_distance 量的就是「士兵中心 → 僵尸可见左缘」，
        # 不要把包围盒半宽再叠上去（那样会把僵尸推远整整一个身位）。
        stand_eff = stand * jitter
        # 角色天赋 soldier_3：attack_distance += 0.2
        # （原版 v5[7] += 0.2 → 僵尸停在更远处就开咬）
        stand_eff *= 1.0 + getattr(self, "talent_atk_dist", 0.0)
        # ★ 新僵尸刷在**排队区之内的队尾之后**，不能插到队首前面，
        #   也不能把队伍推出排队区。
        #   原版僵尸从屏幕右缘走进来，物理自然压成一条队；复刻如果
        #   直接刷在 cam+860，而老僵尸已经挤到玩家跟前，排队算法会把
        #   新僵尸排到最前面 ⇒ 每刷一只就整队后退 190px。
        #   这里把 spawn 夹在 (队尾+间距) 与「排队区外缘」之间。
        near = self.sx + ZOMBIE_QUEUE_SPAN
        tail = 0.0
        for zz in self.zombies:
            if not zz["dead"] and not zz.get("dying") and zz["x"] <= near and zz["x"] > tail:
                tail = zz["x"]
        spawn_x = self.cam + 860 + random.random() * 80
        if tail + ZOMBIE_GAP > spawn_x:
            spawn_x = tail + ZOMBIE_GAP
        # 排队区外缘就是最大刷怪距离：再远就又走出射程了
        spawn_x = min(spawn_x, near + random.random() * 120)
        from game.random_abilities import drop_probability, random_ability

        pending = sum(1 for zz in self.zombies if not zz["dead"] and zz.get("has_item"))
        carry = None
        p = drop_probability(self.day())
        _room = self.ability_dropped + pending + len(self.ability_drops) < self.ability_drop_max
        if p > 0 and _room and random.random() * 1000.0 <= p * 1000.0:
            carry = random_ability(level=self.day())
        if carry is None and p > 0 and _room:
            _idx = self.ability_dropped + pending + len(self.ability_drops)
            _need = (0.45, 0.80)[min(1, _idx)]
            try:
                _cur, _goal = self.progress()
                _prog = float(_cur) / float(max(1, _goal))
            except Exception:
                _prog = 0.0
            if _prog >= _need:
                carry = random_ability(level=self.day())
        self.zombies.append(
            dict(
                x=spawn_x,
                hp=hp,
                maxhp=hp,
                spd=spd,
                atk=atk,
                stand=stand_eff,
                atk_dist=atk_dist * jitter,
                scale=scale,
                walk=random.random(),
                hurt=0.0,
                delay=delay,
                delay_i=0,
                # 攻击起手随机错开（原版各僵尸动画不同步，避免同帧集火）
                atk_t=random.random() * (delay[0] if delay else 1.0),
                boss=boss,
                name=name,
                dead=False,
                dead_t=0.0,
                dying=False,
                atk_anim=0.0,
                dead_t2=0.0,
                gone_t=0.0,
                death_dur=death_dur,
                atk_dur=atk_dur,
                # ★ 冰冻（Zombie::onFreeze @0x192e54）：
                #   freeze_t > 0 表示正被冻住，期间不走不动不开火。
                freeze_t=0.0,
                freeze_ice=None,
                # 携带的技能道具：has_item = Zombie::hasItem，
                # carry_ability = 具体技能名（None 表示没带）。
                has_item=carry is not None,
                carry_ability=carry,
            )
        )

    def freeze_weapon(self):
        """当前武器是不是冰冻枪（weapon/freezer.xml 的 fire_type="freeze"）。"""
        return (self.gun_def().get("fire") or "") == "freeze"

    def _apply_hit(self, z, dmg, lo=0.0, hi=0.0, area=True):
        """子弹真的落到僵尸身上了：Zombie::onDamage 的全部副作用。

        飙血倒下。现在由 `_pending_hits` / 实体子弹在弹道抵达时调用本方法。
        area=False 时只结算被直接命中的那只（机甲子弹不参与 range 溅射）。
        """
        if z is None or z.get("dead") or z.get("dying") or z.get("hp", 0) <= 0:
            return
        z["hp"] -= dmg
        z["hurt"] = 0.25
        z["last_dmg"] = dmg
        # 击退（Zombie::onShotBack）
        self.shot_back(z)
        # 冰冻枪：命中即冻结（Zombie::onFreeze @0x192e54）
        if self.freeze_weapon():
            self.freeze_zombie(z)
        # 中弹喷血（Zombie::onHurt → shot_blood_effect）
        self.fx.add_blood(z["x"] - self.cam, SOLDIER_BASE["ground_y"] - 90)
        if not area or not self.warea:
            return
        # 原版 WeaponEffect::onStartFire @0x1a1a30 的 area_damage 分支
        # （all_merged.c:114930-115000）：getZombies(射程窗口) 里**所有**僵尸
        # 各吃一次满伤；只有 bomb_radius > 0 的爆炸类（rocket/milor）才按
        # 命中点半径做 50% 溅射。
        if self.wbomb > 0:
            radius = self.wbomb
            for o in self.zombies:
                if o is z or o["dead"] or o.get("dying"):
                    continue
                if abs(o["x"] - z["x"]) < radius:
                    o["hp"] -= dmg * 0.5
                    o["hurt"] = 0.2
                    if self.freeze_weapon():
                        self.freeze_zombie(o)
                    self.fx.add_blood(o["x"] - self.cam, SOLDIER_BASE["ground_y"] - 90)
        else:
            for o in self.zombies:
                if o is z or o["dead"] or o.get("dying"):
                    continue
                if lo <= o["x"] <= hi:
                    o["hp"] -= dmg
                    o["hurt"] = 0.2
                    o["last_dmg"] = dmg
                    self.fx.add_blood(o["x"] - self.cam, SOLDIER_BASE["ground_y"] - 90)

    def shot_back(self, z, dist=None):
        """Zombie::onShotBack @0x192ba2：中弹的僵尸被打退 dist 像素。

        反编译：
            if (僵尸可被击退 && this[364] == 0)   ← 364 = 冰冻标志
                z.pos.x += (朝向 ? -shotback_dis : +shotback_dis)

        也就是说 shotback_dis 不是「后坐力」，而是**每发子弹把僵尸往后推多远**：
          katana/axe 40、p220 20、喷火枪 10、音波/激光/雷 20、榴弹 500。

        所有武器打出去僵尸都只是掉血、站原地不动
        """
        if z is None or z.get("dead") or z.get("dying"):
            return
        # 冰冻中的僵尸不被击退（原版 this[364] != 0 直接 return）
        if z.get("freeze_t", 0.0) > 0.0:
            return
        if dist is None:
            # shotback_dis 在 weapon/<gun>.xml 的 <weapon_effect> 上，
            # 由 gun_fx.gun_effect_config 解析
            try:
                from game.gun_fx import gun_effect_config

                dist = float(gun_effect_config(self.weapon).get("shotback_dis") or 0.0)
            except Exception:
                dist = 0.0
        if dist <= 0:
            return
        if getattr(self, "wbomb", 0) > 0:
            dist = min(float(dist), 10.0)
        else:
            dist = min(float(dist), 220.0)
        # 僵尸朝左走（原版朝向 1 = 朝左），被击退就往右推
        z["x"] = z.get("x", 0.0) + dist

    def freeze_zombie(self, z):
        """Zombie::onFreeze @0x192e54：把僵尸冻住 3 秒。

        反编译：
          · boss_1 / boss_2 **免疫**（原版明确跳过这两个）
          · DelayTime(3.0f = 0x40600000) → onFreezeEnd
          · ZombieCharacter::onFreeze @0x194bc0：
              从 ice_1.png / ice_2.png 里**随机**选一张，
              setScale(僵尸 scale × 2)，位置 (this[71], this[72])，
              FadeTo(3.0s, 60) —— 冻结层是**半透明渐隐**的，
              不是突然出现突然消失。
          · freeze_t > 0 期间僵尸**不走不动不攻击**。
        """
        if z is None or z.get("dead") or z.get("dying"):
            return
        # 原版：boss 不受冰冻影响
        if z.get("boss") or str(z.get("name", "")).startswith("boss_"):
            return
        z["freeze_t"] = FREEZE_DURATION
        z["freeze_ice"] = random.choice(("ice_1", "ice_2"))

    def _tick_freeze(self, z, dt):
        """推进冰冻计时，到点解冻（Zombie::onFreezeEnd @0x192e54）。"""
        t = z.get("freeze_t", 0.0)
        if t <= 0.0:
            return False
        t -= dt
        z["freeze_t"] = max(0.0, t)
        if t <= 0.0:
            z["freeze_ice"] = None
            return False
        return True

    def _apply_soldier_talent(self):
        """Soldier::applySoldierTalent @0x1879fc：按角色名设天赋倍率。

        反编译只有三个角色有天赋：
          soldier_2 → v3[2] *= 1.2 和 v3[3] *= 1.2   （speed，两个字段都乘）
          soldier_3 → v5[6] += 0.2 和 v5[7] += 0.2   （attack_distance）
          soldier_4 → v6[5] *= 1.2 和 v6[4] *= 1.2   （damage）
        其余角色（soldier_1/5/6/7）无天赋。
        """
        nm = getattr(self, "soldier", "soldier_1")
        if nm == "soldier_2":
            self.talent_speed = 1.2
        elif nm == "soldier_3":
            self.talent_atk_dist = 0.2
        elif nm == "soldier_4":
            self.talent_damage = 1.2

    # ---- 主循环 ----
    def tick_effects(self, dt):
        """只推进表现层：断肢 / 喷血 / 血渍 / 死亡淡出。

        战斗结束后（over 非空）不能停这些 —— 原版 UIBoard::onGameOver
        只是停刷怪和玩家输入，已经飞出去的 CCAction 照常按自己时间走。
        ⇒ 玩家看到的就是「僵尸刚倒下就定格」。
        """
        self.fx.update(dt)
        self.gunfx.update(dt, SOLDIER_BASE["ground_y"], self.zombies, self.cam)
        for z in self.zombies:
            if z.get("dying") and not z.get("dead"):
                z["dead_t"] = z.get("dead_t", 0.0) + dt
                if z["dead_t"] >= z.get("death_dur", 1.8) + DEATH_FADE:
                    z["dead"] = True
                    z["gone_t"] = 0.0
            elif z["dead"]:
                z["gone_t"] = z.get("gone_t", 0.0) + dt
        self.zombies = [z for z in self.zombies if not (z["dead"] and z.get("gone_t", 0.0) > 0.05)]

    def tick(self, dt):
        if self.over:
            self.tick_effects(dt)
            return
        self.time += dt
        self.fx.update(dt)
        self.gunfx.update(dt, SOLDIER_BASE["ground_y"], self.zombies, self.cam)

        # MultipleFire 补射：到点就再放一次特效 + 结算伤害
        if self._multi_queue:
            due = [t0 for t0 in self._multi_queue if t0 <= self.time]
            if due:
                self._multi_queue = [t0 for t0 in self._multi_queue if t0 > self.time]
                for _t0 in due:
                    _st, _sst = self.soldier_pose()
                    _tgt = self.fire_target()
                    _dmg = self.wdamage * self.skill_factors()
                    # 补射也是**实体子弹**：伤害挂在飞行物上，飞到了才扣血
                    self._shot_damage = _dmg
                    self._shot_bullet = None
                    self._spawn_gun_fx(_tgt, _st, _sst)
                    if _tgt is not None and self._shot_bullet is None:
                        self._apply_hit(_tgt, _dmg)

        # 波次刷新：每条 zombie_type 是独立定时器（update_time 秒刷 1 只），
        # capacity = 该类型的同屏存活上限（ZombieTypeDef::initType）。
        # 守卫虫洞关的僵尸不停下咬人、一路冲门，刷怪节奏要更紧才有防漏压力。
        guard = self.base_type == "guard"
        for w in self.waves:
            w.setdefault("_t", 0.0)
            cap = w["capacity"] * 2 if guard else w["capacity"]
            if self._alive_count(w["name"]) >= cap:
                continue
            interval = max(0.9, w["update_time"] * (0.6 if guard else 1.0))
            w["_t"] += dt
            if w["_t"] >= interval:
                w["_t"] = 0.0
                self._spawn(w["name"], w)

        # 士兵移动（世界坐标 sx；屏幕 x = sx - cam）
        # 士兵固定在屏幕约 48% 处（实测 620/1280）；
        # 推进类任务（distance / hostage / collect）随玩家前进，
        # 其余任务玩家也能左右闪避，但镜头不滚动。
        # 朝向随移动方向更新（Soldier::onMoveLeft → Direction=0 朝左，
        # 键盘和触屏取或：任一被按下就走。触屏是「按住移动」，键盘是
        # 按下/松开成对；两路都用同一套朝向与位移逻辑。
        move = self.move_dir
        if self.key_left:
            move -= 1
        if self.key_right:
            move += 1
        move = max(-1, min(1, move))
        if move != 0:
            self.facing = 1 if move > 0 else 0
        if self.base_type in ("distance", "hostage", "collect"):
            self.sx += move * self.move_speed * self.speed_mult * dt
            # 世界两端同样留半个身位，否则走到终点时右半边身子会出屏
            self.sx = max(SOLDIER_HALF_W, min(self.world_w - SOLDIER_HALF_W, self.sx))
            self.cam = max(0.0, min(self.world_w - 854.0, self.sx - SOLDIER_SCREEN_X))
            # ★ 到达世界右端（这一屏能走的最远处）时，短暂提示「往右走」。
            #   原版 BattleField::validMovingDistance @0x16e69c：
            #   validMovingDistance()==0（超出本屏有效范围）才调
            #   showGoRightAnimation，播有限次后 endGoRightAnimation 移除。
            #   ★ 必须只在**刚到达**的那一帧触发一次，否则贴着右边缘走路时
            #     每帧都会重置计时器，箭头永不消失（实测停在 1.8 秒不动）。
            hit_edge = self.sx >= self.world_w - SOLDIER_HALF_W - 0.5
            if hit_edge and not getattr(self, "_at_edge", False):
                self.go_right_t = GO_RIGHT_SHOW
            self._at_edge = hit_edge
            if self.go_right_t > 0.0:
                self.go_right_t = max(0.0, self.go_right_t - dt)
        else:
            # 非推进类任务：镜头不动，士兵在屏幕范围内自由移动。
            # 每帧都从基准点重算，导致最多只能移 2.4 像素就卡住，
            # 玩家根本走不到道具 / 躲不开僵尸。
            self.sx = self.sx + move * self.move_speed * self.speed_mult * dt
            # 边界要留出**半个身位**：sx 是包围盒中心，直接 clamp 到 60
            # 会让朝左走时左半边身子出屏（士兵被裁掉一条），看起来像模型
            # 撕裂。角色包围盒最宽约 208（ak47），半宽 104。
            self.sx = max(SOLDIER_HALF_W, min(854.0 - SOLDIER_HALF_W, self.sx))
            self.cam = 0.0
        if self.base_type in ("distance", "hostage"):
            # 推进计程（1 公里 = 10 计数单位）
            # ★ 必须按**世界位移**算，不能累加 |每帧位移|：
            #   现在 dist_m 恒等于「当前世界 x − 出发 x」，和终点图标、
            #   胜利判定用的是同一个坐标系。
            self.dist_m = max(0.0, self.sx - self.start_x)
        elif self.base_type == "guard":
            self.guard_left = max(0.0, self.guard_left - dt)

        # 技能到期（Soldier::speedBack / powerBack / shieldBack）
        if self.speed_until and self.time >= self.speed_until:
            self.speed_mult = 1.0
            self.speed_until = 0.0
        if self.power_until and self.time >= self.power_until:
            self.power_mult = 1.0
            self.power_until = 0.0
        if self.shield_until and self.time >= self.shield_until:
            self.shield = 0.0
            self.shield_until = 0.0
        if self.msg_t > 0:
            self.msg_t -= dt
        if self.exp_hint_cd > 0:
            self.exp_hint_cd = max(0.0, self.exp_hint_cd - dt)

        # ★ 召唤物推进：机甲跟着士兵走、飞行武器悬停 + 各自开火。
        #   原版它们都是 BattleField 的独立子节点（createAttackWeapon /
        #   createFlyWeapon），有各自的更新循环和射速。
        self._tick_summons(dt)

        # 技能特效推进（治疗的一次性光效 / 护盾的持续光罩）
        if self.ability_fx is not None:
            self.ability_fx.update(dt)
        if self.kill_bonus_fx is not None:
            self.kill_bonus_fx.update(dt)
        if getattr(self, "wormhole", None) is not None:
            self.wormhole.update(dt)
        if getattr(self, "distance_target", None) is not None:
            self.distance_target.update(dt)
        if getattr(self, "evac", None) is not None:
            self.evac.update(dt)

        # ★ 子弹飞行结算：到点了才扣血 / 击退 / 喷血（见 _apply_hit）
        if self._pending_hits:
            due = [h for h in self._pending_hits if h["t"] <= self.time]
            if due:
                self._pending_hits = [h for h in self._pending_hits if h["t"] > self.time]
                for h in due:
                    self._apply_hit(h["z"], h["dmg"], h["lo"], h["hi"])

        # 开火
        self.fire_cd -= dt
        if self.is_firing() and self.fire_cd <= 0 and self.consume_bullet():
            # 目标必须是「还活着且没在播死亡动画」的僵尸。
            # 这期间它仍被当成目标，后面 3~4 枪全打在尸体上。
            # 实测：一只 60 血的僵尸吃掉 5 枪（应该 3 枪），实际 DPS 腰斩。
            # 目标选取按**士兵朝向**开一个单向窗口。
            # 反编译 WeaponEffect::onStartFire @0x1a1a30：
            #     if (a2 == 1) {  // Direction_Status = 1（右）
            #         v73 = centerX + v24;          // v24 = soldierWidth/2
            #         v26 = centerX + v25;          // v25 = shoot_distance
            #     } else {                          // 朝左
            #         v73 = centerX - v25;
            #         v26 = centerX - v24;
            #     }
            # 窗口是单向的：朝左时只打左边的僵尸。
            # 一枪都打不出去（身后的僵尸全部被排除）。
            tgt = self.fire_target()
            # ★ 空枪（无目标）也照常开火 —— 见 114701 段反编译：
            #   onStartFire 先把 addBulletCaseEffect / addFireSparkEffect /
            #   addLaserLightEffect 等特效**全部播完**，最后才 getZombies
            #   查射程内僵尸；查到空列表就循环 0 次，**没有任何提前返回**。
            # 也就是说原版按住开火键随时能打，有怪才掉血，
            # 没怪照样扣子弹、出弹道、出枪口火焰、播音效。
            # 玩家按住红球看到的是「扣了扳机毫无反应」。
            # WeaponItemButton::onFire @0x183ab0：开火扣 1 发弹。
            # ★ 原版**子弹打空不会自动换枪**：
            #   onFire 里 `if (子弹数 > 0)` 才扣弹；为 0 时只把
            #   「没子弹」标志(451)置 1，**不做任何换枪动作**。
            #   表现是 Soldier::onStartFire @0x1872bc 检查 451 标志，
            #   非 0 就播 "sounds/block.ogg" 并**挡住开火**。
            #   换枪只能玩家手动点武器槽（或按换枪键）。
            #   于是玩家手动切到近战武器（子弹少/为 0）后，一开火
            crit = random.random() < self.wcrit
            # power 技能：伤害倍率（Soldier::powerUp）
            # 角色天赋 soldier_4：伤害 ×1.2（applySoldierTalent）
            # 机甲形态：按机甲 power 档位缩放（onChange2Mech 的 this[114]）
            dmg = (
                self.wdamage
                * self.skill_factors()
                * getattr(self, "talent_damage", 1.0)
                * getattr(self, "mech_damage_mult", 1.0)
                * (2 if crit else 1)
            )
            _warhead_cfg = gfx.gun_effect_config(self.weapon)
            self._shot_is_warhead = bool(_warhead_cfg.get("warhead"))
            self._shot_damage = dmg
            _mn = getattr(self, "mech_name", None)
            self.fire_cd = mech_fire_interval(_mn) if _mn else self.winterval
            self.muzzle = 0.30
            # ★ 开火动画要**连续**播：射速比动画短时（ak47 0.10 秒 vs 动画
            #   0.28 秒），每发都重置进度会让手臂只抖前 3 帧、永远播不完，
            #   看着就是动画卡死。只有「从没开火 → 开火」才把进度归零。
            _firing = self.fire_hold > 0.0
            self.fire_hold = max(self.fire_hold, 0.30)
            if not _firing:
                self.fire_t = 0.0
            if getattr(self, "mech_name", None):
                self.mech_fire_left = max(self.mech_fire_left, self.mech_fire_anim_dur())
            self.shots += 1
            # 开火特效（WeaponEffect::addFireSparkEffect @0x19f508 /
            # addBulletCaseEffect @0x19f808 + 子弹拖尾 bullet_light.png）
            # tgt 为 None 时只出枪口火光和弹壳，不出弹道 —— 和原版一致。
            _st, _sst = self.soldier_pose()
            # 这一发是否生成了**实体飞行物**（机甲子弹 / 火箭）：
            # 由飞行物自己负责命中结算，不再走 _pending_hits 排程。
            self._shot_bullet = None
            self._spawn_gun_fx(tgt, _st, _sst)
            # ★ MultipleFire：一次开火排 N 次补射（含完整特效）。
            #   原版 onStartFire @0x1a1a30 后面那段 isMultipleFire →
            #   getMultipleFireDelays → 对每个 delay 排 CCDelayTime + onStartFire1。
            #   声明它的武器：mech_8 / mech_9 / mech_10（delays="0.35,0.4,0.4"）。
            _multi = gfx.gun_effect_config(self.weapon).get("multi")
            if _multi:
                for _dly in _multi.get("delays") or []:
                    self._multi_queue.append(self.time + float(_dly))
            if (
                tgt is not None
                and not getattr(self, "_shot_is_warhead", False)
                and getattr(self, "_shot_bullet", None) is None
            ):
                lo, hi = self.fire_window() if self.warea else (0.0, 0.0)
                dist = abs(float(tgt["x"]) - self.sx)
                delay = min(0.26, max(0.02, dist / 2600.0))
                self._pending_hits.append(
                    {"t": self.time + delay, "z": tgt, "dmg": dmg, "lo": lo, "hi": hi}
                )
                # 经验武器：每枪递减，打完换回原枪（Soldier::onWeaponFire）
                if self.exp_weapon:
                    self.exp_bullets_left -= 1
                    if self.exp_bullets_left <= 0:
                        self.end_exp_weapon()
            else:
                # 空枪也走经验武器递减（原版是按开火次数算的）
                if self.exp_weapon:
                    self.exp_bullets_left -= 1
                    if self.exp_bullets_left <= 0:
                        self.end_exp_weapon()
        elif self.is_firing() and self.fire_cd <= 0:
            self.fire_cd = self.winterval
            self.muzzle = 0.0
            self.no_bullet = True

        # 僵尸行动
        for z in self.zombies:
            if z["dead"]:
                z["gone_t"] = z.get("gone_t", 0.0) + dt
                continue
            if z.get("dying"):
                continue
            if z["hurt"] > 0:
                z["hurt"] -= dt
            # ★ 冰冻中：不走、不攻击（Zombie::onFreeze → 冻结 3 秒）。
            #   原版把整段 onUpdate 的移动/攻击都跳过，只跑解冻计时。
            if self._tick_freeze(z, dt):
                continue
            # 守卫虫洞关：僵尸不咬人、也不停在 stand_distance 上，
            # 直接穿过玩家一路冲向门；玩家要在限时内把它们拦在底线前。
            if self.base_type == "guard":
                z["x"] -= z["spd"] * 1.25 * dt
            else:
                # 走到士兵右侧 stand_distance 处停下攻击
                # （原版 Zombie::onUpdate 用 stand_distance 判定贴近）
                reach = self.sx + z["stand"]
                if z["x"] > reach:
                    z["x"] -= z["spd"] * dt
                elif z["x"] < reach - 2.0:
                    z["x"] = min(reach, z["x"] + z["spd"] * dt)
                else:
                    z["x"] = reach
                    # 同一时刻只有排到最前面的一只僵尸能攻击（原版物理排队）
                    if z.get("in_line"):
                        z["atk_t"] += dt
                        dl = z["delay"]
                        gap = dl[z["delay_i"] % len(dl)] if dl else 1.0
                        if z["atk_t"] >= gap:
                            z["atk_t"] = 0.0
                            z["atk_anim"] = z.get("atk_dur", 0.8)  # 播放攻击动画
                            z["delay_i"] += 1
                            if self.hp > 0 and self.time >= getattr(self, "invuln_until", 0.0):
                                # 护盾减伤（Soldier::onDamage @0x189588）：
                                #     if (shield > 0) dmg = (int)(dmg * (1.0 - shield));
                                #     dmg = (int)(dmg * (1.0 - armor));
                                # 护盾值是**百分比减伤**（shield_1=0.5 减一半，
                                # shield_2=1.0 免疫），而不是「吸收固定伤害值」。
                                # 几乎没用。护盾不消耗，到期自己消失。
                                dmg = float(z["atk"])
                                if self.shield > 0:
                                    dmg = dmg * (1.0 - self.shield)
                                dmg = dmg * (1.0 - self.armor)
                                self.hp -= int(dmg)
            # 越过虫洞底线 = 漏过（Zombie::onUpdate → BattleField::onZombieLeak）。
            # 判定点与 HUD 画出的底线共用 GUARD_LINE_X，僵尸不许穿过去。
            if z["x"] - self.cam < GUARD_LINE_X:
                z["dead"] = True
                z["leaked"] = True
                self.leaked_count += 1
                if self.base_type == "guard":
                    self.leak_left -= 1
                    # 原版 LeakCounter::onLeakZombie @0x18100c：lives 减到 0 立即
                    # BattleScene::onGameOver(false, 3) → 失败。
                    if self.leak_left <= 0 and not self.over:
                        self.leak_left = 0
                        self.over = "lose"
            z["walk"] += dt
            if z.get("atk_anim", 0) > 0:
                z["atk_anim"] -= dt
            if z["hp"] <= 0 and not z.get("dying"):
                # 先播死亡动画（death_* 1.8s），播完才真正移除
                z["dying"] = True
                z["dead_t"] = 0.0
                gy = SOLDIER_BASE["ground_y"]
                zx = z["x"] - self.cam
                # ① 死亡大喷血（ZombieCharacter::onDeath @0x194204）：
                #    在 getCenterYInBattleFiled + 40 逻辑单位处炸一蓬
                #    shot_blood_2，0.4 秒播完接 0.8 秒淡出。
                self.fx.add_death_splat(zx, gy - 40.0, flip=self.facing == 0)
                # ② 血渍 xuezi04.png：randInt(-15,15) 度旋转、scale 0.3 起，
                #    0.1 秒放大、停 1 秒、1 秒淡出。
                self.fx.add_stain(
                    zfx.stain_image(),
                    zx,
                    gy - 8.0,
                    scale=0.3 * z.get("scale", 1.0),
                    target_scale=0.34 * z.get("scale", 1.0),
                )
                # ③ 断肢碎片（Death/Box2DItem）—— 按僵尸名取它**自己**的部件
                zfx.spawn_death_debris(
                    self.fx,
                    zx,
                    gy,
                    z.get("last_dmg", 0),
                    self.zstats.get(z["name"], {}).get("death_split", 50),
                    name=z.get("name"),
                )
                self.kills += 1
                # ★ 击杀赏金（原版 KillBonusEffect::onKillZombie @0x17ff90）：
                #   赏金按僵尸名查 zombie_bonus.xml（查不到默认 30），
                #   在僵尸位置飘「+N」并冒星星。
                #   ★ 原版还会通过 BattleField::addCoinBonus @0x172ea4
                #     **真的把这笔赏金加进 user_coin**：
                #       getKeyValue("user_coin", 2000) → +bonus → 写回
                #     「打怪赚钱」的核心循环整个断掉。
                _kb = kill_bonus(z.get("name") or "")
                self.last_kill_bonus = _kb
                self.last_kill_x = zx
                self.last_kill_y = gy
                if self.save is not None and _kb:
                    # 用 lazy 版：只改内存不落盘（原版 addCoinBonus 也只写内存，
                    # 落盘统一在关卡结束的 add_battle_stats → save() 里做）。
                    # 用 add_coins 会每杀一只僵尸写一次存档文件，60 只 = 60 次 IO。
                    self.save.add_coins_lazy(_kb)
                if self.kill_bonus_fx is not None:
                    self.kill_bonus_fx.add(zx, gy)
                if z.get("boss"):
                    self.boss_kills += 1
                self.combo += 1
                self.combo_max = max(self.combo_max, self.combo)
                self.combo_t = 3.0
                # RandomAbilityManager::onZombieDead：按关卡概率掉技能
                self._maybe_drop_ability(z)
        # 死亡动画播完再移除；漏过的僵尸直接移除
        # 每个僵尸的死亡时长不同（zombie_1 1.8s、boss_1 2.5s），
        # 由 spawn 时从 XML duration 记录到 z["death_dur"]。
        # ★ 死亡动画播完**不直接消失**，还要淡出 DEATH_FADE 秒：
        #   ZombieCharacter::onDeathAnimationFinished @0x194210
        #   把所有子节点 CCFadeOut(duration)，再 CCDelayTime(duration)
        #   之后才调 Zombie::onDeath 真正移除。duration 来自
        #   ZombieCharacter 构造里 `*((_DWORD *)this + 111) = 0x40000000`
        #   ⇒ **2.0 秒**。
        #   死亡感很生硬。
        for z in self.zombies:
            if z.get("dying") and not z.get("dead"):
                z["dead_t"] += dt
                if z["dead_t"] >= z.get("death_dur", 1.8) + DEATH_FADE:
                    z["dead"] = True
                    z["gone_t"] = 0.0
            elif z.get("leaked"):
                z["dead"] = True
                z["gone_t"] = 0.0
        self.zombies = [z for z in self.zombies if not (z["dead"] and z.get("gone_t", 0.0) > 0.05)]
        self._separate_zombies()
        self._tick_hostages(dt)
        self._tick_pickups(dt)
        self._tick_ability_drops(dt)
        self._tick_exp_weapon(dt)

        if self.combo_t > 0:
            self.combo_t -= dt
            if self.combo_t <= 0:
                self.combo = 0
        if self.muzzle > 0:
            self.muzzle -= dt
        # 开火动画进度：连射时连续走，停火后 fire_hold 归零退出开火姿态
        self.fire_t += dt
        if self.fire_hold > 0.0:
            self.fire_hold = max(0.0, self.fire_hold - dt)
            if self.fire_hold <= 0.0:
                self.fire_t = 0.0  # 停火：下次开火从第一帧起播
        # 机甲开火动画：按自身时长自然播完，连射时连续循环（不重置帧）
        self.mech_fire_t += dt
        if self.mech_fire_left > 0.0:
            self.mech_fire_left = max(0.0, self.mech_fire_left - dt)

        # 任务判定（语义来自 pic/ui/dialog/*_mission_text_*.png 原文）
        #   kill_mission      击杀 number 个僵尸
        #   distance_mission  前往 number 公里外的基地
        #   guard_mission     不让超过 number 个僵尸通过传送门，守住 number2 秒
        #   hostage_mission   护送幸存者到 number 公里外的撤离点
        #   collect_mission   收集 number 把钥匙
        #   time_mission      生存 number 秒
        #   *_time_mission    在 number2 秒内完成上面的目标
        bt = self.base_type
        if bt == "kill":
            self._check(self.kills >= self.quota)
        elif bt == "distance":
            # dist_m 累加的是**像素**（move_speed=150 px/s）。
            # 1 个进度单位 = DIST_PX_PER_UNIT 像素（100 px ≈ 0.67 秒），
            # number=10 的关大约走 7 秒，节奏合理。
            self._check(self.dist_m // self.DIST_PX_PER_UNIT >= self.quota)
        elif bt == "guard":
            self._check(self.guard_left <= 0)  # 守满时间即胜
        elif bt == "hostage":
            # 「护送幸存者到 N 公里外的撤离点」—— number 是**距离**，不是人数。
            # ★ 走够距离只是到了撤离点，必须等幸存者真的爬进机舱
            #   而不是直接胜利」）。
            done = self.dist_m // self.DIST_PX_PER_UNIT >= self.quota
            if done and self.hostages:
                for h in self.hostages:
                    if h["dead"]:
                        continue
                    if not h["saved"] or h.get("board", 1.0) < 1.0:
                        done = False
                        break
            self._check(done)
        elif bt == "collect":
            self._check(self.collected >= self.quota)
        elif bt == "time":
            self._check(self.time >= self.quota)
        else:
            self._check(self.kills >= self.quota)

        # 限时任务：超时即失败（time_mission 是「生存 N 秒」，不带 _time 后缀）
        if self.timed and self.time_limit > 0 and self.time >= self.time_limit and not self.over:
            self.over = "lose"
        if self.hp <= 0 and not self.over:
            if getattr(self, "mech_name", None) is not None:
                # 血条归零的是机甲 → 先爆炸、再退回角色血条（不死）
                self._mech_explode()
            else:
                self._on_player_death()
        if self.over == "win":
            self.finish()

    DIST_PX_PER_UNIT = DIST_PX_PER_UNIT

    def _check(self, ok):
        if self.over:
            return
        # *_time_mission = 在时限内完成主目标，不是任一条件独立获胜。
        # 先判截止时刻，避免超时同一帧完成目标被误记成胜利。
        if self.timed and self.time_limit > 0 and self.time >= self.time_limit:
            self.over = "lose"
        elif ok:
            self.over = "win"

    def _on_player_death(self):
        """士兵阵亡 → 进入续天流程（未付费则失败），唯一入口。

        ★ 一次性「脑子被咬出」：复用 zombie_fx 的脑花贴图与同一套抛射
          物理，只在 hp<=0 这一帧生成。over="revive" 之后 tick 走
          tick_effects 继续推进碎片，复活 / 续关都不会重播。
        """
        self.hp = 0
        self.dead = True
        self.over = "revive"
        self.fx.add_brain_bite(
            self.sx - self.cam + SOLDIER_RENDER_DX,
            SOLDIER_FOOT_Y - 150.0,  # 节点树实测头顶 ≈243（392-150=242）
            SOLDIER_BASE["ground_y"],
            flip=(self.facing == 0),
        )

    def revive(self):
        """付费续天（BattleScene::onReviveSoldier）。

        返回 True 表示复活成功，False 表示次数用尽。
        """
        if self.revive_left <= 0:
            self.over = "lose"
            self.finish()
            return False
        self.revive_left -= 1
        self.dead = False
        self.hp = self.maxhp
        self.over = None
        # 清掉贴身的僵尸，避免复活即被打死
        for z in self.zombies:
            if not z["dead"] and z["x"] - self.sx < 200:
                z["x"] = self.sx + 260
        return True

    def _separate_zombies(self):
        """僵尸之间不重叠（原版用 Box2D 物理碰撞）。

        保持至少 ZOMBIE_GAP 间距；已到攻击位的排在前面，其余依次往后，
        避免多只同时贴脸集火。
        """
        near = self.sx + ZOMBIE_QUEUE_SPAN
        live = sorted(
            (z for z in self.zombies if not z["dead"] and not z.get("dying") and z["x"] <= near),
            key=lambda z: z["x"],
        )
        prev = None
        for z in live:
            if prev is None:
                prev = z
                continue
            want = prev["x"] + ZOMBIE_GAP
            if z["x"] < want:
                z["x"] = want
            if z["x"] > near:
                # 已经顶到排队区外缘：再往后推也没意义，直接截断
                break
            prev = z
        # 攻击位：只有走到 stand 位置的那一只（队首）能出手。
        # stand + ZOMBIE_GAP，GAP 一放大第二只也跟着能打，伤害翻倍）。
        front = None
        for z in live:
            if z["x"] - self.sx <= z["stand"] + 24:
                front = z
                break
        for z in live:
            z["in_line"] = z is front

    def _tick_hostages(self, dt):
        """护送：人质跟在士兵身后，到撤离点**登机**；被僵尸咬会掉血。"""
        if not self.hostages:
            return
        evac = getattr(self, "evac", None)
        goal = evac.door_x if evac is not None else self.goal_x
        # 士兵已经走到终点线附近（或计程已满）⇒ 人质改去舱门集合
        at_goal = (
            self.sx >= self.goal_x - 200.0 or self.dist_m // self.DIST_PX_PER_UNIT >= self.quota
        )
        for h in self.hostages:
            if h["dead"]:
                continue
            if h.get("board") is not None:
                # 登机中：由场景层插值绘制，逻辑上只推进计时
                h["board"] = min(1.0, h["board"] + dt / 1.2)
                continue
            if h["saved"]:
                continue
            h["walk"] += dt
            tx = goal if at_goal else self.sx - 120
            # 集合到舱门时要贴得更紧：跟随死区 30px 会让儿童停在门前
            # 60px 处永远够不着舱门（实测卡住、关卡无法结算）。
            tol = 6.0 if at_goal else 30.0
            if abs(h["x"] - tx) > tol:
                # 人质跟着士兵走（步速同士兵）
                h["x"] += (self.move_speed if h["x"] < tx else -self.move_speed) * dt
                h["stand"] = False
            else:
                h["stand"] = True
            for z in self.zombies:
                if z["dead"]:
                    continue
                if abs(z["x"] - h["x"]) < 60:
                    h["hp"] -= z["atk"] * 0.25 * dt
            if h["hp"] <= 0:
                h["dead"] = True
                # 原版 Hostage::onDamage @0x1a6ebc：人质死亡立即
                # BattleScene::onGameOver(false, 11) → 任务失败。
                if not self.over:
                    self.over = "lose"
            elif at_goal and abs(h["x"] - goal) <= 22.0:
                # ★ 到舱门不直接胜利：先爬进机舱（board 0→1），播完才结算。
                h["saved"] = True
                h["board"] = 0.0
                h["bx"] = h["x"]
                self.saved += 1

    def _tick_pickups(self, dt):
        """收集：悬浮钥匙，靠近自动拾取。"""
        for p in self.pickups:
            if p["got"]:
                continue
            p["t"] += dt * 3
            if abs(p["x"] - self.sx) < 55:
                p["got"] = True
                self.collected += 1
                # 捡起来之后才刷下一把（收集关一次只出现一个道具）
                if self.base_type == "collect" and getattr(self, "key_spawned", 0) < max(
                    1, self.quota
                ):
                    self._spawn_next_key(self.sx + 460.0)

    # ---- 结算（对齐 setResult @0x1acc68）----
    def finish(self):
        win = self.over == "win"
        ratio = max(0.0, self.hp / float(self.maxhp)) if win else 0.0
        score = int(ratio * 100)
        if score > 99:
            grade, star = "S", 3
        elif score > 84:
            grade, star = "A", 2
        else:
            grade, star = "B", 1
        coin = 0
        if win:
            coin = self.reward_coin
            if score > 99:
                coin += int(self.reward_coin * 0.10)
            elif score > 84:
                coin += int(self.reward_coin * 0.05)
        # 钻石奖励：level_list.xml 的 reward_crystal（默认 1）。
        # 原版 DialogLevelPassed::InitCoinAndCrystal @0x1ac754 会把
        # 而 12 把枪（spas12/rocket/freezer/sonic/thunder…）只能钻石买，
        # ⇒ 货币链断裂，玩家永远攒不出钻石。
        crystal = self.reward_crystal if win else 0
        self.result = dict(
            win=win,
            score=score,
            grade=grade,
            star=star,
            coin=coin,
            crystal=crystal,
            kills=self.kills,
            combo_max=self.combo_max,
            blood=int(ratio * 100),
            time=self.time,
            mission_id=self.mission_id,
            quota=self.quota,
            saved=self.saved,
            collected=self.collected,
        )
        # 全局统计（UIBoard::onGameOver @0x16c218）：
        # 成就系统读 total_kills / total_boss_kills / total_times，
        # 每日任务系统读 daily_kills / daily_done_missions / daily_vungles。
        # 不写这些键 ⇒ 那些成就/任务永远达不成条件。
        # finish() 可能在 win 分支和 revive 放弃分支各调一次，
        # 用 _stats_written 防止统计被重复累加。
        if (
            self.save is not None
            and not self._stats_written
            and hasattr(self.save, "add_battle_stats")
        ):
            self._stats_written = True
            self.save.add_battle_stats(
                kills=self.kills,
                boss_kills=self.boss_kills,
                seconds=int(self.time),
                missions_done=1 if win else 0,
                vungles=self.leaked_count,
            )

    def time_remaining(self):
        # 原版 TimeCounter（@0x182674 / 0x1825a4）显示的是**剩余秒数**的
        # 倒计时，不是「已过时间/目标」。init 时把初值存进 this+260，
        # onUpdate 每帧减 dt，整秒变化就 updateTime 重画文本。
        #   time_mission            初值 = number（归零 → 胜利）
        #   *_time_mission          初值 = number2（归零 → 失败）
        #   guard_mission           初值 = number2（守满 → 胜利）
        if self.base_type == "time":
            return max(0.0, float(self.quota) - self.time)
        if self.timed and self.time_limit > 0:
            return max(0.0, self.time_limit - self.time)
        if self.base_type == "guard":
            return max(0.0, getattr(self, "guard_left", 0.0))
        return 0.0

    def has_extra_timer(self):
        # 只有明确配置为 *_time_mission 的关卡显示主目标 + 时限两个条件。
        # 守卫关主计数器本身就是倒计时，不再重复显示同一时间。
        return self.timed and self.base_type != "time"

    def progress(self):
        # HUD 用：当前进度 / 目标值。
        bt = self.base_type
        if bt == "kill":
            return (self.kills, self.quota)
        if bt == "distance":
            return (int(self.dist_m // self.DIST_PX_PER_UNIT), self.quota)
        if bt == "guard":
            return (int(self.guard_left), int(self.quota2 or 60))
        if bt == "hostage":
            # 同 distance：进度是已走距离，不是救出人数
            return (int(self.dist_m // self.DIST_PX_PER_UNIT), self.quota)
        if bt == "collect":
            return (self.collected, self.quota)
        if bt == "time":
            return (int(self.time), self.quota)
        return (self.kills, self.quota)
