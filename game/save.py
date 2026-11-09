"""存档系统 —— 对齐 EzGameData（libezjoygame.so 0x1c7bc9 单例）语义。

证据（RE_NOTES.md）：
* LevelData{int best; int last; u8 star} 按 mission_id(1..133) 存 map
* updateLevelData(id, last, star)：best=max, last=覆盖, star=max
* 金币 addCoin/spendCoin/setCoinCount；user_coin 默认 2000
* 通过关另写 key-value：passed_missions(逗号串)、ref_level、day
"""

import contextlib
import json
import os
from typing import ClassVar


# 存档外置：游戏目录只保留运行文件，进度写到项目相邻的 save_data。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVE_PATH = os.path.join(os.path.dirname(_ROOT), "save_data", "save.json")

# 武器槽数量 —— 原版 UIBoard 有 4 个武器槽（equipped_gun_0..3），
# 军火库页面的格子也是 4 个（game/shopui.py SLOT_N = 4）。
WEAPON_SLOTS = 4

# 武器等级上限。upgrade.xml 每把枪 4 档（levels[0..3]），
# 即 lv 取值 0..3 —— 与 weapon_levels 注释、upgrade_weapon 的单调递增一致。
# 注意：levels[] 的长度是 4，但最高**等级号**是 3。
WEAPON_MAX_LEVEL = 3

DEFAULT_KEYBINDS = dict(
    left="a",
    right="d",
    fire="space",
    cycle="left shift",
    weapon_1="1",
    weapon_2="2",
    weapon_3="3",
    weapon_4="4",
    ability_1="q",
    ability_2="e",
    ability_3="r",
    armor="x",
    mech="c",
)

# 长键名缩写：玩家可把任意键绑到动作上，pygame.key.name() 的全名
# （如 scroll lock / print screen）直接大写在键帽/键值底板里会溢出。
KEY_NAME_ALIAS = {
    "left shift": "LShift",
    "right shift": "RShift",
    "left ctrl": "LCtrl",
    "right ctrl": "RCtrl",
    "left alt": "LAlt",
    "right alt": "RAlt",
    "left windows": "LWin",
    "right windows": "RWin",
    "left super": "LWin",
    "right super": "RWin",
    "space": "Space",
    "return": "Enter",
    "backspace": "Bksp",
    "caps lock": "CapsLk",
    "scroll lock": "ScrLk",
    "num lock": "NumLk",
    "print screen": "PrtScr",
    "page up": "PgUp",
    "page down": "PgDn",
}


def key_display_name(name):
    """键名的界面显示形式：常见长名用缩写，其余大写。

    设置页、教程页、战斗内键位提示共用，避免三处各写一份映射而漂移。
    """
    return KEY_NAME_ALIAS.get(name, name.upper())


DEFAULT = dict(
    coins=2000,  # getKeyValue("user_coin", 2000) 默认值
    crystals=5,  # getKeyValue("user_crystal", 5) 默认值
    levels={},  # {"1": {"best": 0, "last": 0, "star": 0}}  key = mission_id
    weapon_levels={},  # {"ak47": 0..3}  upgrade.xml 的 level id
    owned_weapons=["ak47", "p220"],
    # equipped_gun_0：反编译 Soldier::init 附近（all_merged.c:77883）首次进游戏时
    # 写 "equipped_gun_0" = "p220"，同时 p220 = 3（弹匣满）、p220_bullet = -1（无限子弹）。
    equipped=["p220"],
    p220=3,
    p220_bullet=-1,
    soldier_levels={},  # {"soldier_1": {"blood":0,"speed":0,"armor":0}} 三条独立
    owned_soldiers=["soldier_1"],
    owned_abilities=[],  # 已装备技能名
    abilities={},  # {"<name>": 拥有数量}
    owned_mechs=[],
    # ★ 机甲数量：原版 MechShopLayer::onBuyMech 把数量写在**机甲名**这个
    #   存档键上（getKeyValue(机甲名) +1）。这里统一收进 mech_count 字典
    #   {"mech_5": 2}，owned_mechs 列表保留作为旧档兼容。
    mech_count={},
    equipped_mech=None,
    en_potion_count=0,  # 士兵升级消耗品（原版存档键名）
    passed_missions=[],  # mission_id 列表（对应 passed_missions 逗号串）
    soldier=1,  # soldier_1..7
    settings=dict(
        music=True,
        sound=True,
        # 全屏显示：设置页按钮或 F11 切换，重开游戏沿用上次状态。
        fullscreen=False,
        # 窗口化尺寸相对 854×480 的倍率；拖动窗口时保持同宽高比。
        window_scale=1.0,
        # 首次进游戏只弹一次键盘操作指南；任意键关闭后写入 true。
        key_intro_shown=False,
        # 键位模式：开 = 键盘操作（A 左 / D 右 / 空格攻击），
        # 关 = 触屏摇杆。默认开。
        keyboard=True,
        # 默认值迁移标记：老存档里写着 keyboard=False，
        # 不重新写一次的话改了默认值也永远不生效。
        kb_default=1,
        # 键盘模式默认隐藏触屏虚拟键；设置页仍可重新打开。
        hide_buttons=True,
        hide_default=1,
        # 战斗桌面显示武器、道具和基础操作键帽，可在设置中关闭。
        key_hints=True,
    ),
    # 键盘键位映射（pygame.K_* 的名字）。玩家在设置里改键时写这里。
    keybinds=dict(DEFAULT_KEYBINDS),
    # ---- 每日任务 / 统计 / 成就（原版存档键）----
    # Save.load 只接受 DEFAULT 里出现过的键（白名单），所以原版用到的每个
    # 存档键都必须在这里声明，否则读档时被丢弃。
    last_login_day=0,  # 上次登录是一年中的第几天（每日重置判据）
    reward_day=1,  # 连续签到第几天（1..30 循环）
    daily_kills=0,  # 今日击杀数
    daily_done_missions=0,  # 今日完成关卡数
    daily_use_potions=0,  # 今日使用药水数
    daily_vungles=0,  # 今日漏过传送门的僵尸数
    daily={},  # 每日任务面板进度 {kills, missions, potions}
    total_kills=0,  # 累计击杀（成就）
    total_boss_kills=0,  # 累计 boss 击杀（成就）
    total_times=0,  # 累计游戏秒数（成就）
    have_used_potions=0,  # 是否用过药水（新手引导第 30 步）
    play_one_level=0,  # 是否玩过一关
)

# 每日任务领取标记（原版键名 task_reward_0..7，见 DailyTaskManager::
# getLeftTaskCount @0x150ff4）。这些键是动态的，不能直接放进 DEFAULT，
# 用 _EXTRA_KEYS 声明让 load() 放行。
_EXTRA_INT_KEYS = ("task_reward_%d" % i for i in range(8))
_EXTRA_INT_KEYS = tuple(
    list(_EXTRA_INT_KEYS)
    + ["reward_day_%d" % i for i in range(1, 31)]
    # 老虎机免费次数（原版 SlotLayer::onButtonSpin 读
    # free_spin_<i>；DialogRemind::resetData 会写回 1）
    + ["free_spin_%d" % i for i in range(3)]
)


def _default_level():
    return dict(best=0, last=0, star=0)


class Save:
    """EzGameData 的 Python 对应物。mission_id 是 1..133 的整数（level_list.xml）。"""

    def __init__(self, path=SAVE_PATH):
        self.path = path
        self.d = json.loads(json.dumps(DEFAULT))
        self.load()
        self._migrate_kb_default()
        self.set_init_bullet()
        self.clear_daily_task_info()

    def _migrate_kb_default(self):
        """把老存档的 keyboard=False 升成默认开（只做一次）。"""
        st = self.d.get("settings")
        if not isinstance(st, dict):
            st = self.d["settings"] = {}
        if st.get("kb_default"):
            return
        st["keyboard"] = True
        st["kb_default"] = 1
        self.save()

    # ---- 每日任务重置（MainMenuScene::clearDailyTaskInfo @0x11fbac）----
    def clear_daily_task_info(self):
        """跨天重置每日任务。

        原版 MainMenuScene::clearDailyTaskInfo（all_merged.c:74488）：
            YearDays = AppUtils::getYearDays();          ← 一年中的第几天
            if (YearDays != 存档["last_login_day"]) {
                存档["last_login_day"] = YearDays;
                存档["daily_kills"] = 0;
                存档["daily_done_missions"] = 0;
                存档["daily_use_potions"] = 0;
                存档["daily_vungles"] = 0;
                for (i < 8) 存档["task_reward_<i>"] = 0;
                if (YearDays - last_login_day == 1) {    ← 连续登录
                    存档["reward_day"] = (旧 reward_day + 1) % 31 或 1;
                    存档["reward_day_<n>"] = 0;
                } else {
                    存档["reward_day"] = 1;
                    存档["reward_day_1"] = 0;
                }
            }

        领一次之后第二天再打开还是「已领取」，进度也不会归零。
        """
        import datetime

        today = datetime.date.today().timetuple().tm_yday
        last = int(self.d.get("last_login_day", 0) or 0)
        if last == today:
            return
        self.d["last_login_day"] = today
        for k in ("daily_kills", "daily_done_missions", "daily_use_potions", "daily_vungles"):
            self.d[k] = 0
        for i in range(8):
            self.d["task_reward_%d" % i] = 0
        if last and today - last == 1:
            rd = int(self.d.get("reward_day", 1) or 1) + 1
            if rd > 30:
                rd = 1
            self.d["reward_day"] = rd
        else:
            self.d["reward_day"] = 1
        self.d["reward_day_%d" % int(self.d["reward_day"])] = 0
        for i in range(3):
            self.d["free_spin_%d" % i] = 1
        # 自造的旧键同步清掉
        self.d.pop("daily_claimed", None)
        self.d["daily"] = {}
        self.save()

    # ---- 弹药初始化 ----
    def reset_all(self):
        """清空存档（原版 EzGameData::clearAll → DialogRemind::resetData）。

        把 self.d 重置成 DEFAULT 的深拷贝，删掉动态键（task_reward_*、
        reward_day_*、<gun>_bullet 之类），重新写初始子弹，然后落盘。
        """
        self.d = json.loads(json.dumps(DEFAULT))
        self.set_init_bullet()
        self.save()
        return self.d

    def set_init_bullet(self):
        """ShopItemParser::setInitBulletInGameData @0x138050。

        原版：遍历已拥有的枪，若存档里**没有** <name>_bullet 键，
        就写入 shop_config.xml 的 init_bullet 值（GunItemDef + 80）。

        ★ 关键语义（反编译 all_merged.c:62310 GunItemDef::setGunItemDef）：
          GunItemDef 构造时把 +80/+84/+88 三个 int 全部初始化为 **-1**，
          只有 XML 里显式写了 init_bullet 才会覆盖。
          ⇒ 没写 init_bullet 的枪（**全部近战武器**：wrench/guitar/katana/
            axe/saw/laser_sword，还有 p220）拿到的初值就是 -1。

          存档里 <name>_bullet = -1 表示**无限子弹**（p220 就是这么存的，
          见本文件 DEFAULT 里的 p220_bullet=-1）。
          近战武器同理：init_bullet 缺省 ⇒ 存 -1 ⇒ 无限子弹。

            consume_bullet() 立刻返回 False → next_weapon() 自动弹回原枪
            ⇒ 表现为「近战武器根本切不上，切过去又跳回来」

        另：原版 setInitBulletInGameData 用 getKeyValue(name, **-1**)
        判断「键不存在」，本复刻等价地用 `key in self.d`。
        """
        from game.shop_table import BY_NAME

        owned = list(self.d.get("owned_weapons") or [])
        for slot in self.d.get("equipped") or []:
            if slot and slot not in owned:
                owned.append(slot)
        changed = False
        for name in owned:
            key = "%s_bullet" % name
            if key in self.d:
                continue
            g = BY_NAME.get(name)
            if not g:
                continue
            # 缺省 = -1（无限子弹）；只有 XML 里显式配了 init_bullet 才是实数。
            self.d[key] = int(g.get("init_bullet", -1))
            changed = True
        if changed:
            self.save()
        return self.d

    # ---- IO ----
    # 每个键期望的类型；类型对不上就丢掉这个键，用默认值。
    # 表现就是「游戏进不去」。
    _TYPES: ClassVar[dict] = {
        "coins": (int,),
        "crystals": (int,),
        "levels": (dict,),
        "weapon_levels": (dict,),
        "owned_weapons": (list,),
        "equipped": (list,),
        "soldier_levels": (dict,),
        "owned_soldiers": (list,),
        "owned_abilities": (list,),
        "abilities": (dict,),
        "owned_mechs": (list,),
        "mech_count": (dict,),
        "en_potion_count": (int,),
        "passed_missions": (list,),
        "soldier": (int,),
        "settings": (dict,),
        "keybinds": (dict,),
    }

    def _valid(self, key, value):
        want = self._TYPES.get(key)
        if want is None:
            return True
        if not isinstance(value, want):
            return False
        # bool 是 int 的子类，但游戏里没有布尔字段，排除掉
        if isinstance(value, bool):
            return False
        if key == "passed_missions":
            return all(isinstance(x, int) and not isinstance(x, bool) for x in value)
        if key == "equipped":
            return all(x is None or isinstance(x, str) for x in value)
        if key == "owned_weapons":
            return all(isinstance(x, str) for x in value)
        if key == "levels":
            return all(isinstance(x, dict) for x in value.values())
        return True

    def load(self):
        if not os.path.exists(self.path):
            return self.d
        try:
            with open(self.path, encoding="utf-8") as f:
                stored = json.load(f)
        except (OSError, ValueError):
            # 文件读坏：留一份 .bad 备份，然后用默认值继续
            with contextlib.suppress(OSError):
                os.replace(self.path, self.path + ".bad")
            return self.d
        if not isinstance(stored, dict):
            with contextlib.suppress(OSError):
                os.replace(self.path, self.path + ".bad")
            return self.d
        for k, v in stored.items():
            if k not in self.d:
                # 动态键（task_reward_0..7 / reward_day_1..30）不在 DEFAULT 里，
                # 但它们是原版存档的一部分，必须放行，否则读档时被丢掉。
                if k in _EXTRA_INT_KEYS and isinstance(v, int):
                    self.d[k] = v
                continue
            if not self._valid(k, v):
                continue
            if isinstance(self.d[k], dict) and isinstance(v, dict):
                if k == "settings" and "hide_default" not in v:
                    v = dict(v)
                    v["hide_buttons"] = True
                    v["hide_default"] = 1
                self.d[k].update(v)
            else:
                self.d[k] = v
        return self.d

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.d, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    # ---- LevelData map（对齐 updateLevelData @0x1c7c7d）----
    def _lv(self, mid):
        if not isinstance(self.d.get("levels"), dict):
            self.d["levels"] = {}
        key = str(int(mid))
        rec = self.d["levels"].get(key)
        if not isinstance(rec, dict):
            rec = _default_level()
            self.d["levels"][key] = rec
        for f in ("best", "last", "star"):
            rec.setdefault(f, 0)
        return rec

    def update_level_data(self, mid, last_score, star):
        """best=max / last=覆盖 / star=max(u8) —— 与原版逐字段一致。"""
        rec = self._lv(mid)
        rec["best"] = max(int(rec["best"]), int(last_score))
        rec["last"] = int(last_score)
        rec["star"] = max(int(rec["star"]), int(star))
        mid = int(mid)
        if mid not in self.d["passed_missions"]:
            self.d["passed_missions"].append(mid)
        self.save()

    # ---- 战斗统计（UIBoard::onGameOver @0x16c218）----
    def add_battle_stats(self, kills, boss_kills, seconds, missions_done, vungles=0):
        """一局战斗结束时累加全局统计。

        原版 UIBoard::onGameOver（all_merged.c:111778）在一局结束时写这些键：
            total_kills       += 本关击杀数
            daily_kills       += 本关击杀数        ← 每日任务「击杀 N 只」
            total_boss_kills  += 本关 boss 击杀数
            total_times       += 本关时长（秒）     ← 成就「累计游戏 N 分钟」用
            daily_done_missions += 本关通关数      ← 每日任务「完成 N 个任务」
            daily_vungles     += 本关漏过传送门的僵尸数  ← 每日任务「漏怪」
            play_one_level    = 1

        total_boss_kills / total_times）和每日任务系统（读 daily_kills /
        daily_done_missions / daily_vungles / daily_use_potions）
        永远无法达成条件。

        seconds 用整数秒（原版写的是 int）。
        """
        d = self.d

        def add(key, n):
            n = int(n)
            if n:
                d[key] = int(d.get(key, 0) or 0) + n

        add("total_kills", kills)
        add("daily_kills", kills)
        add("total_boss_kills", boss_kills)
        add("total_times", int(seconds))
        add("daily_done_missions", missions_done)
        add("daily_vungles", vungles)
        d["play_one_level"] = 1
        self.save()

    def has_level_data(self, mid):
        return str(int(mid)) in self.d["levels"]

    def get_level_star(self, mid):
        rec = self.d["levels"].get(str(int(mid)))
        return rec["star"] if rec else 0

    def get_level_best(self, mid):
        rec = self.d["levels"].get(str(int(mid)))
        return rec["best"] if rec else 0

    def is_level_unlocked(self, mid):
        """按顺序解锁：第 1 关恒开放，其余要求前一关有通过记录。"""
        mid = int(mid)
        return mid == 1 or (mid - 1) in self.d["passed_missions"]

    def next_mission(self):
        """下一个该打的关卡。

        关卡在地图上是一条跨 zone 的连续路线（见 game/map_points.py 的
        zone 顺序），所以下一个关卡 = 已通过的最大 mission_id + 1。
        """
        pm = self.d.get("passed_missions")
        if not isinstance(pm, list):
            return 1
        nums = [x for x in pm if isinstance(x, int) and not isinstance(x, bool)]
        return (max(nums) + 1) if nums else 1

    # ---- 金币（对齐 addCoin/spendCoin）----
    def add_coins(self, n):
        n = int(n)
        if n < 0:
            # 负数「加钱」= 扣钱，必须走 spend_coins 才有余额校验。
            raise ValueError("add_coins 不接受负数，扣钱请用 spend_coins")
        self.d["coins"] = int(self.d["coins"]) + n
        self.save()
        return self.d["coins"]

    def add_coins_lazy(self, n):
        """只改内存、**不落盘**地加钱。

        原版 BattleField::addCoinBonus @0x172ea4 就是这么干的：
            KeyValue = getKeyValue("user_coin", 2000);
            map["user_coin"] = KeyValue + bonus;      ← 只写内存
        落盘由关卡结束时的 EzGameData::save() 统一做。

        战斗里每杀一只僵尸都要加赏金，用 add_coins 会每只写一次
        存档文件（一关 60 只 = 60 次 IO），帧率会明显掉。
        """
        n = int(n)
        if n < 0:
            raise ValueError("add_coins_lazy 不接受负数")
        self.d["coins"] = int(self.d["coins"]) + n
        return self.d["coins"]

    def spend_coins(self, n):
        n = int(n)
        if n < 0:
            raise ValueError("spend_coins 不接受负数")
        if self.d["coins"] < n:
            return False
        self.d["coins"] = int(self.d["coins"]) - n
        self.save()
        return True

    def add_crystals(self, n):
        n = int(n)
        if n < 0:
            raise ValueError("add_crystals 不接受负数，扣钱请用 spend_crystals")
        self.d["crystals"] = int(self.d["crystals"]) + n
        self.save()
        return self.d["crystals"]

    def spend_crystals(self, n):
        n = int(n)
        if n < 0:
            raise ValueError("spend_crystals 不接受负数")
        if self.d["crystals"] < n:
            return False
        self.d["crystals"] = int(self.d["crystals"]) - n
        self.save()
        return True

    # ---- 武器 ----
    def weapon_level(self, name):
        return int(self.d["weapon_levels"].get(name, 0))

    def weapon_maxed(self, name):
        return self.weapon_level(name) >= WEAPON_MAX_LEVEL

    def upgrade_weapon(self, name, coin_cost, crystal_cost):
        """升一级。返回 True = 真的升级了。

        满级（lv == WEAPON_MAX_LEVEL）直接返回 False，**不扣任何钱**。
        玩家点一次白掉 20000 金币（用户实测确认）。
        """
        if self.weapon_maxed(name):
            return False
        coin_cost = max(0, int(coin_cost or 0))
        crystal_cost = max(0, int(crystal_cost or 0))
        if coin_cost and not self.spend_coins(coin_cost):
            return False
        if crystal_cost and not self.spend_crystals(crystal_cost):
            if coin_cost:
                self.add_coins(coin_cost)  # 回滚
            return False
        self.d["weapon_levels"][name] = min(WEAPON_MAX_LEVEL, self.weapon_level(name) + 1)
        self.save()
        return True

    def buy_weapon(self, name, coin_cost):
        if name in self.d["owned_weapons"]:
            return True
        if not self.spend_coins(coin_cost):
            return False
        self.d["owned_weapons"].append(name)
        self.save()
        return True

    def unlock_guns(self):
        """钻石解锁过的枪械名列表（原版存档键 unlock_guns）。

        原版 GunShopLayer::onUnlockGun @0x134bcc 就是
        `unlock_guns 里 append(枪名)` —— 之后 showGun 认定它「已解锁」，
        即使通关等级不够也能正常购买。
        """
        v = self.d.get("unlock_guns")
        if not isinstance(v, list):
            v = []
            self.d["unlock_guns"] = v
        return v

    def weapon_locked(self, gun):
        """武器是否被「通关等级」锁着。

        GunShopLayer::onSelectGun @0x130b44：
            if (def->locked)
                if (unlock_guns 含此枪) → 视为已解锁
                else if (getKeyValue("level",1) < def->unlock_level) → 锁定
        """
        need = int(gun.get("unlock_level") or 0)
        lvl = int(self.d.get("level", 1) or 1)
        return need > 0 and lvl < need and gun["name"] not in self.unlock_guns()

    def unlock_weapon(self, name, crystal_cost):
        """花钻石解开购买条件（不解锁拥有权），成功后返回 True。"""
        if name in self.unlock_guns():
            return True
        if not self.spend_crystals(int(crystal_cost or 0)):
            return False
        self.unlock_guns().append(name)
        self.save()
        return True

    def buy_weapon_crystal(self, name, crystal_cost):
        if name in self.d["owned_weapons"]:
            return True
        if not self.spend_crystals(crystal_cost):
            return False
        self.d["owned_weapons"].append(name)
        self.save()
        return True

    def own_weapon(self, name):
        return name in self.d["owned_weapons"]

    def equip(self, name, slot=0):
        """把武器装到第 slot 个槽（0..3）。

        原版 UIBoard 有 4 个武器槽（equipped_gun_0..3），
        军火库页面也是 4 个格子（ShopItemPanel SLOT_N = 4）。

        同时写 equipped_gun_N：战斗界面 WeaponSlots 读的就是这组键，
        两边不同步的话，玩家在军火库换了枪，进战斗还是老的。
        """
        # 槽位索引必须落在 0..WEAPON_SLOTS-1。
        # slot=99 直接 IndexError 崩在 UI 点击回调里。
        try:
            slot = int(slot)
        except (TypeError, ValueError):
            return False
        if not 0 <= slot < WEAPON_SLOTS:
            return False
        while len(self.d["equipped"]) < WEAPON_SLOTS:
            self.d["equipped"].append(None)
        # 同一把枪已经在别的槽上 → 先把它摘掉（避免一把枪占两格）
        for i in range(WEAPON_SLOTS):
            if i != slot and self.d["equipped"][i] == name:
                self.d["equipped"][i] = None
        self.d["equipped"][slot] = name
        self._sync_equipped_gun_keys()
        self.save()

    def _sync_equipped_gun_keys(self):
        """把 equipped 列表同步成 equipped_gun_0..N（战斗界面读这组键）。

        原版存档就是 equipped_gun_0 起的一串，空的槽不写。
        """
        for i in range(WEAPON_SLOTS):
            key = "equipped_gun_%d" % i
            nm = self.d["equipped"][i] if i < len(self.d["equipped"]) else None
            if nm:
                self.d[key] = nm
            else:
                self.d.pop(key, None)

    def equipped_weapons(self):
        """已装备的武器名（**只含非空**，压缩后的顺序）。

        槽位位置另见 equipped_slots()。
        """
        eq = self.d.get("equipped")
        if not isinstance(eq, list):
            return []
        return [w for w in eq if isinstance(w, str) and w]

    def equipped_slots(self):
        """四个槽的完整视图（空槽是 None，不压缩）。

        军火库页面要按槽号显示（槽 1..4），所以需要保持空位。
        """
        eq = self.d.get("equipped")
        if not isinstance(eq, list):
            eq = []
        out = []
        for i in range(WEAPON_SLOTS):
            v = eq[i] if i < len(eq) else None
            out.append(v if (isinstance(v, str) and v) else None)
        return out

    # ---- 机甲 ----
    def mech_count(self, name):
        """某台机甲拥有几台。

        原版 MechShopLayer::onBuyMech 把数量写在**机甲名**这个存档键上；
        本复刻统一收进 mech_count 字典。旧档的 owned_mechs 列表
        （只表示「有」不表示「几台」）按 1 台算。
        """
        cnt = self.d.get("mech_count")
        if isinstance(cnt, dict) and name in cnt:
            try:
                return max(0, int(cnt[name]))
            except (TypeError, ValueError):
                return 0
        own = self.d.get("owned_mechs")
        if isinstance(own, list) and name in own:
            return 1
        return 0

    def add_mech(self, name, n=1):
        """买机甲：数量 +n（并把名字补进 owned_mechs 兼容列表）。"""
        cnt = self.d.setdefault("mech_count", {})
        cnt[name] = self.mech_count(name) + n
        own = self.d.setdefault("owned_mechs", [])
        if name not in own:
            own.append(name)
        self.save()

    def use_mech(self, name):
        """用掉一台机甲：数量 -1。返回 True = 确实用掉了。"""
        c = self.mech_count(name)
        if c <= 0:
            return False
        cnt = self.d.setdefault("mech_count", {})
        cnt[name] = c - 1
        if cnt[name] <= 0:
            cnt.pop(name, None)
            own = self.d.get("owned_mechs")
            if isinstance(own, list) and name in own and cnt.get(name, 0) <= 0:
                # 数量归零 → 从兼容列表里摘掉（对应原版 cleanZeroCountMech）
                with contextlib.suppress(ValueError):
                    own.remove(name)
        self.save()
        return True

    # ---- 士兵 ----
    def soldier_name(self):
        """当前士兵（soldier_1..7）。"""
        return "soldier_%d" % int(self.d.get("soldier", 1))

    # ---- 药水（en_potion_count）----
    # 原版存档键就是 "en_potion_count"（all_merged.c 里 DialogPotion /
    # 与原版存档不兼容 —— 读原版存档看不到药水。
    # 保留 "potions" 作为旧档回退。
    POTION_KEY = "en_potion_count"

    def potion_count(self):
        v = self.d.get(self.POTION_KEY)
        if v is None:
            v = self.d.get("potions", 0)
        return int(v)

    def add_potions(self, n):
        self.d[self.POTION_KEY] = self.potion_count() + int(n)
        self.save()
        return self.d[self.POTION_KEY]

    def spend_potions(self, n):
        """原版：不够就直接弹药水商店（DialogSoldierUpgrade::showDialogPotion）。"""
        if self.potion_count() < n:
            return False
        self.d[self.POTION_KEY] = self.potion_count() - int(n)
        self.save()
        return True

    def soldier_levels_of(self, name=None):
        """士兵的三条独立等级：blood / speed / armor。

        原版存 <soldier>_blood_lv / _speed_lv / _armor_lv（见
        SoldierShopLayer 升级逻辑）。
        """
        n = name or self.soldier_name()
        rec = self.d["soldier_levels"].get(n)
        if not rec:
            rec = {"blood": 0, "speed": 0, "armor": 0}
            self.d["soldier_levels"][n] = rec
        for k in ("blood", "speed", "armor"):
            rec.setdefault(k, 0)
        return rec

    def soldier_level(self, kind="blood"):
        """当前士兵某条属性的等级（0..3）。"""
        return int(self.soldier_levels_of().get(kind, 0))

    def upgrade_soldier(self, kind="blood", name=None):
        """升级士兵某条属性，返回新等级（-1 = 已满级）。

        name：要升级哪个角色。原版 DialogSoldierUpgrade 是
        `setSoldierInfo(选中角色)` 后才开窗，升的是**弹窗里那个角色**，

        原版 DialogSoldierUpgrade::onButtonUpgrade @0x14ede4（all_merged.c:31671）
        在扣完药水、升完级之后还会写两个存档键：
            daily_use_potions = 旧值 + 1     ← 每日任务「使用药水」计数
            have_used_potions = 1            ← 新手引导第 30 步的判定
        新手引导也卡在第 30 步。
        """
        rec = self.soldier_levels_of(name)
        lv = int(rec.get(kind, 0))
        if lv >= 3:
            return -1
        rec[kind] = lv + 1
        # 原版 DialogSoldierUpgrade::upgradeSoldier（all_merged.c:31671）
        # 升级士兵时 daily_use_potions 自增 1 —— 这就是每日任务
        # 「角色升级 N 次」的计数来源。
        self.d["daily_use_potions"] = int(self.d.get("daily_use_potions", 0) or 0) + 1
        self.d["have_used_potions"] = 1
        self.save()
        return lv + 1

    def own_soldier(self, name):
        return name in self.d["owned_soldiers"]

    def buy_soldier(self, name, coin_cost=0, crystal_cost=0):
        """购买士兵：原版 cost_coin / cost_crystal（soldier_actors.xml）。"""
        if name in self.d["owned_soldiers"]:
            return True
        if coin_cost and not self.spend_coins(coin_cost):
            return False
        if crystal_cost and not self.spend_crystals(crystal_cost):
            if coin_cost:
                self.add_coins(coin_cost)
            return False
        self.d["owned_soldiers"].append(name)
        self.save()
        return True
