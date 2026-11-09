"""弹窗打开 / 结算 / 任务推进等流程控制。"""

import pygame

from game import map_points as MP
from game.battle import Battle
from game.dialog_cheat import CheatDialog
from game.dialog_daily import DailyTaskDialog
from game.dialog_daily_reward import DailyRewardDialog
from game.dialog_failed_weapon import FailedWeaponDialog
from game.dialog_game_intro import GameIntroduceDialog
from game.dialog_gun_upgrade import GunUpgradeDialog
from game.dialog_pause import PauseDialog
from game.dialog_potion import PotionDialog
from game.dialog_settings import SettingsDialog
from game.dialog_soldier_upgrade import SoldierUpgradeDialog
from game.dialog_zombie_shop import ZombieShopDialog
from game.hud_fx import HudFx


class DialogFlowMixin:
    """弹窗打开 / 结算 / 任务推进等流程控制。"""

    def open_dialog(self, kind):
        """打开一个模态对话框。kind: pause/settings/soldier_up/gun_up/game_intro"""
        self.dialog = {
            "pause": PauseDialog,
            "settings": SettingsDialog,
            "soldier_up": SoldierUpgradeDialog,
            "gun_up": GunUpgradeDialog,
            "potion": PotionDialog,
            "daily": DailyTaskDialog,
            "daily_reward": DailyRewardDialog,
            "zombie_shop": ZombieShopDialog,
            "cheat": CheatDialog,
            "game_intro": GameIntroduceDialog,
        }[kind](self)
        return self.dialog

    def open_potion_shop(self):
        """原版：士兵升级时药水不够 → 弹药水商店（DialogPotion）。"""
        self.open_dialog("potion")

    def toast(self, msg):
        self._toast = (msg, 1.6)

    def cheat_grant(self, coins=None, crystals=None):
        """顶栏「+」：打开金手指面板，由玩家**手动输入**要多少金币 / 钻石。

        原版这里是渠道充值 SDK 的入口（服务器早已下线）。离线复刻按用户
        要求保留「点 + → 手动输入数量」的最初行为，绝不是点一下就固定
        就像开始那样 你这个有问题」）。

        coins / crystals 只给脚本 / 自动化调用点留一条直接入账的口子；
        地图层与军火库层的点击都不传参数，一律走 CheatDialog。
        """
        if coins is None and crystals is None:
            self.audio.ui_click()
            self.open_dialog("cheat")
            return
        coins = int(coins or 0)
        crystals = int(crystals or 0)
        if coins:
            self.save.add_coins(coins)
        if crystals:
            self.save.add_crystals(crystals)
        self.save.save()
        self.audio.coin()
        self.toast("金手指 金币+%s 钻石+%s" % (f"{coins:,}", f"{crystals:,}"))

    def _tick_toast(self, dt):
        if not getattr(self, "_toast", None):
            return
        msg, t = self._toast
        t -= dt
        self._toast = (msg, t) if t > 0 else None

    def _after_dialog(self):
        """对话框关闭后的处理。"""
        d = self.dialog
        if d is None or not d.done:
            return
        # 不是所有弹窗都有 result（GameIntroduceDialog 只有 done）
        r = getattr(d, "result", None)
        self.dialog = None
        if r == "resume":
            pass
        elif r == "restart":
            self.start_mission(self.mission_id)
        elif r == "quit":
            self.goto("map")
        elif r == "reset":
            # 设置里的「初始设置」（清档重来）。存档已由 SettingsDialog 重置，
            # 这里把内存里的所有状态重建一遍再回主菜单 —— 等价原版
            # MapLayer::onReset 之后整场景重建。
            self._reload_after_reset()
        elif r == "close":
            pass

    def _reload_after_reset(self):
        """清档后重载游戏状态（不重启进程）。"""
        self.battle = None
        self.result_panel = None
        self.revive_panel = None
        self.level_dialog = None
        self.achievement_panel = None
        self.slot_panel = None
        self.failed_weapon = None
        self.guide = None
        self.ability_bar = None
        self.weapon_slots = None
        self.main_menu = None
        self.map_buttons = None
        self.hud_fx = HudFx()
        self.mission_id = self.save.next_mission()
        self.map_points = MP.build_points(self.level_db, self.save)
        self.shop_sel = "p220"
        self.shop_tab = "gun"
        self.shop_row = 0
        self.shop_ability = 0
        self.shop_ability_scroll = 0.0
        self.shop_drag = None
        self.goto("menu")  # goto 内部会拍快照做过场
        self.toast("数据已清除")
        self.audio.bgm("menu")

    def after_result(self):
        """结算面板关闭后的处理。

        DialogLevelFailed::onButtonRetry @0x1ae1ac → BattleSceneLayer::restart
        DialogLevelFailed::onButtonMenu  @0x1ae5b4 → 存档 + 回地图（菜单音乐）
        胜利结算点任意处 → 进下一关
        """
        panel = self.result_panel
        r = panel.r if panel else None
        act = panel.done if panel else None
        arg = getattr(panel, "done_arg", None) if panel else None
        self.result_panel = None
        if act == "retry":
            self.start_mission(self.mission_id)
            return
        if act == "buy_gun":
            # 原版：失败面板底部点推荐枪 → DialogFailedWeapon（限时折扣）
            self._open_failed_weapon(arg or "desert_eagle")
            return
        if r and r["win"]:
            self.mission_id = min(133, self.mission_id + 1)
        self.goto("map")

    # 原版失败推荐枪的折扣力度（模拟器实测：沙漠之鹰 4000 → 3000 = 75 折）
    FAILED_GUN_RATE = 0.75
    FAILED_GUN_SECONDS = 300

    def _open_failed_weapon(self, gun):
        """DialogFailedWeapon：限时 75 折买一把更强的枪，买完继续打。"""
        self.scene = "battle"
        try:
            d = FailedWeaponDialog(self, gun, self.FAILED_GUN_RATE, self.FAILED_GUN_SECONDS)
        except Exception:
            self.goto("map")
            return
        d.anim = 1.0
        # 复用 dialog 槽：FailedWeaponDialog 自带 update/draw/click，接口一致
        self.failed_weapon = d

    def _tick_failed_weapon(self, dt):
        d = getattr(self, "failed_weapon", None)
        if d is None:
            return
        d.update(dt)
        if d.done:
            self.failed_weapon = None
            self.goto("map")

    def start_mission(self, mid):
        self.mission_id = mid
        # 引导只属于地图层。玩家若在引导未结束时进关（点任务点穿透、
        # 结算面板回关等路径），不清会整块盖到战斗摇杆/开火键上。
        self.guide = None
        eq = self.save.equipped_weapons()
        weapon = eq[0] if eq else "ak47"
        self.battle = Battle(
            mid,
            self.level_db,
            self.zstats,
            self.weapons,
            self.uptab,
            weapon=weapon,
            weapon_lv=self.save.weapon_level(weapon),
            soldier=self.save.soldier_name(),
            soldier_lv=self.save.soldier_level("blood"),
            save=self.save,
        )
        # 战斗内提示（如「机甲状态无法拾取武器」）走顶层 toast，暂停/结算上都看得见
        self.battle.toast_cb = self.toast
        self.result_panel = None
        self.hud_fx.reset()
        self.weapon_slots = None
        self.ability_bar = None
        self.mech_slot = None
        self.goto("battle")

    # ------------------------------------------------------------ 绘制
