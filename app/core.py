"""App 主体：初始化、场景切换、主循环 step / render。"""

import contextlib
import os
from typing import Any

import pygame

from app.constants import (
    DATA,
    SCREENS,
    UI,
    H,
    W,
    _scan_zone_bgs,
)
from app.dialogs import DialogFlowMixin
from app.input import InputMixin
from app.key_items import KeyItemsMixin
from app.keynav import KeyNav
from app.scene_battle import BattleSceneMixin
from app.scene_map import MapSceneMixin
from app.scene_shop import ShopSceneMixin
from engine import scene as SC
from engine.audio import Audio
from engine.feedback import FeedbackBus
from engine.skel import Skeleton
from game import (
    map_points as MP,
)
from game import (
    shopui as SU,
)
from game import (
    transition as TR,
)
from game.battle import (
    load_level_list,
    load_zombie_stats,
)
from game.hud_fx import HudFx
from game.result import ResultPanel
from game.revive import RevivePanel
from game.reward_fly import RewardFly
from game.save import Save
from game.splash import SplashScene
from game.weapons import (
    load_upgrade_table,
    load_weapons,
)


class App(
    KeyItemsMixin, MapSceneMixin, ShopSceneMixin, BattleSceneMixin, DialogFlowMixin, InputMixin
):
    """游戏主对象。各场景的渲染/输入拆在同目录的 mixin 里。"""

    # 这些属性会按场景动态换成不同类型的面板/战斗对象。显式声明为 Any，
    # 否则类型检查器会把 __init__ 里的 None 当成唯一类型，在 main.py 的
    # 截图入口里把「赋实例 / 访问属性」误报成一排红错。
    splash: Any
    guide: Any
    battle: Any
    result_panel: Any
    revive_panel: Any
    dialog: Any
    main_menu: Any
    level_dialog: Any
    map_buttons: Any
    weapon_slots: Any
    ability_bar: Any
    mech_slot: Any
    achievement_panel: Any
    slot_panel: Any
    failed_weapon: Any
    shop_drag: Any
    _fullscreen_callback: Any

    def __init__(self, save_path=None):
        self.trees = {}
        self.texs = {}
        for name, (tf, xf) in SCREENS.items():
            rows = SC.load_jsonl(os.path.join(DATA, tf))
            tex = SC.load_tex(os.path.join(DATA, xf))
            roots = SC.build_tree(rows)
            for r in roots:
                r["sc"] = [1.0, 1.0]
                r["pos"] = [0.0, 0.0]
                r["ap"] = [0.0, 0.0]
                r["rot"] = 0.0
            self.trees[name] = roots
            self.texs[name] = tex

        self.save = Save(save_path) if save_path else Save()
        self.audio = Audio()
        self.feedback = FeedbackBus(self.audio)
        self.zone_bgs = _scan_zone_bgs()
        self._sb_key = None
        self._sb = None

        self.level_db = load_level_list()
        self.zstats = load_zombie_stats()
        self.weapons = load_weapons()
        self.uptab = load_upgrade_table()

        # 士兵骨骼：本体用 de_sheets，只有 gun02（手持武器）按当前武器的
        # upper_sheets 覆盖 —— 原版 SoldierCharacter::initCharacter 就是把
        # 当前武器的 upper 贴图盖到通用 lower 上，角色其余部件不变。
        _gun = self.save.equipped_weapons()[0] if self.save.equipped_weapons() else "p220"
        self.soldier = Skeleton(
            ["config/soldier/01/de_sheets.xml"],
            "config/soldier/01/de_stand_animations.xml",
            override_parts={"gun02": "config/soldier/01/%s_upper_sheets.xml" % _gun},
        )
        self.zombie = Skeleton(
            ["pic/zombies/09/upper_sheets.xml", "pic/zombies/09/lower_sheets.xml"],
            "pic/zombies/01/walk_animations_1.xml",
        )

        self.scene = "menu"
        self.splash = SplashScene(self)  # 启动 Logo → 1s 后进主菜单
        self.transition = TR.Transition()  # 场景切换过场
        self.guide = None  # 新手引导（MapLayer::initUserGuide）
        self.t = 0.0
        self.frame = pygame.Surface((W, H))
        self._fullscreen_callback = None  # 主窗口注册的显示模式切换回调

        # 游戏状态
        self.mission_id = self.save.next_mission()
        self.battle = None
        self.result_panel = None
        self.shop_tab = "gun"  # 当前页签：soldier/gun/money/ability/mech
        self.money_rects = {}
        self.shop_sel = "p220"
        self.shop_ability = 0
        self.shop_ability_scroll = 0.0  # 技能页滚动偏移（像素）
        self.shop_drag = None  # 拖拽滚动状态：dict(y0, row0)
        # scrollToCell：选中项滚到第二行，上方保留一格上下文
        idx = next((i for i, g in enumerate(SU.SHOP_GUNS) if g["name"] == self.shop_sel), 0)
        self.shop_row = max(0, idx - SU.SCROLL_LEAD)
        self.shop_rects = {}
        self.shop_btn_rects = {}
        self.shop_slot_rects = []
        self.shop_tab_rects = {}
        self.equip_rect = None
        self.revive_panel = None
        self.dialog = None  # 当前弹出的对话框（暂停/设置/升级…）
        self.main_menu = None  # 主菜单层（MainMenuScene）
        self.level_dialog = None  # 关卡选择框（DialogLevelSelect）
        self.map_buttons = None  # 地图按钮层（MapLayer::initUI）
        self.weapon_slots = None  # 战斗武器槽（UIBoard::addWeaponItemButton）
        self.ability_bar = None  # 战斗技能条（UIBoard::addAbilityItemButton）
        self.mech_slot = None  # 战斗机甲道具槽
        self.hud_fx = HudFx()  # 连击 / 奖励浮动字（ComboKillEffect）
        self.reward_fly = RewardFly()  # 领奖飞行动画（签到 / 成就）
        self.keynav = KeyNav()  # 全键盘导航的焦点（金色呼吸框）
        self.money_font = SU.ScoreFont("pic/fonts/score_gold.png", 1.0)
        self.money_big = SU.ScoreFont("pic/fonts/score_gold.png", 1.0)
        self.shop_font = SU.ScoreFont("pic/fonts/score_gold.png", 0.62)
        self.shop_font_big = SU.ScoreFont("pic/fonts/score_white.png", 1.0)
        # 地图任务点（133 关按 zone 铺开）
        self.map_points = MP.build_points(self.level_db, self.save)

    # ------------------------------------------------------------ 显示模式
    def bind_fullscreen(self, callback):
        """注册主窗口的显示模式切换回调；截图/测试入口可不注册。"""
        self._fullscreen_callback = callback

    def set_fullscreen(self, enabled):
        """切换全屏并落盘；实际生效状态以主窗口回调的返回值为准。"""
        on = bool(enabled)
        cb = getattr(self, "_fullscreen_callback", None)
        if callable(cb):
            applied = cb(on)
            if applied is not None:
                on = bool(applied)
        self.save.d.setdefault("settings", {})["fullscreen"] = on
        self.save.save()
        return on

    def note_window_scale(self, scale):
        """记录拖动窗口得到的等比倍率；变化不明显时不重复落盘。"""
        try:
            s = float(scale)
        except (TypeError, ValueError):
            return 1.0
        s = round(max(0.5, min(4.0, s)), 3)
        st = self.save.d.setdefault("settings", {})
        try:
            old = float(st.get("window_scale", 1.0) or 1.0)
        except (TypeError, ValueError):
            old = 1.0
        if abs(old - s) >= 0.001:
            st["window_scale"] = s
            self.save.save()
        return s

    # ------------------------------------------------------------ 场景切换

    def _maybe_key_intro(self):
        """首次进游戏弹一次键盘操作指南；任意键关闭后不再自动弹。"""
        if getattr(self, "splash", None) is not None or self.dialog is not None:
            return
        st = self.save.d.setdefault("settings", {})
        if bool(st.get("key_intro_shown", False)):
            return
        st["key_intro_shown"] = True
        self.save.save()
        self.open_dialog("game_intro")

    def goto(self, scene):
        # 切场景前把当前画面拍成快照，做 0.28s 过场（原版是瞬切，这里增强）。
        # 从 splash 切出来时不拍 —— 那时画面还是 logo 白底，做转场很怪。
        if scene != self.scene and getattr(self, "splash", None) is None:
            with contextlib.suppress(Exception):
                self.transition.start(self.frame)
        self.scene = scene
        if scene != "map":
            self.dialog = None
        # 引导属于地图层。离开地图（去军火库/回主菜单）必须清掉，
        # 否则气泡和女孩会一直盖在商店界面上，把武器列表挡住。
        if scene != "map":
            self.guide = None
        # ★ 成就面板 / 老虎机面板同样是地图层的全屏浮层，且它们不吃
        #   `self.dialog` 那条分支（input 里各自单列）。切场景时不清会一直
        #   画在新场景之上 —— 巡检时就看到过「进地图后老虎机还挂着，
        #   点僵尸商店没反应」。
        if scene != "map":
            self.achievement_panel = None
            self.slot_panel = None
        if scene == "menu":
            self.audio.bgm("menu")
            self._maybe_key_intro()
        elif scene == "map":
            self.audio.bgm("menu")
            # 任务点依赖通关进度，进地图时重建
            self.map_points = MP.build_points(self.level_db, self.save)
            self._maybe_user_guide()
        elif scene == "battle":
            self.audio.bgm("battle")

    def step(self, dt):
        self.t += dt
        if getattr(self, "feedback", None) is not None:
            self.feedback.update(dt)
        # 领奖飞行动画：独立推进，不受场景 / 弹窗影响
        if getattr(self, "reward_fly", None) is not None:
            self.reward_fly.update(dt)
        # 场景过场推进（不吃操作，纯视觉）
        if getattr(self, "transition", None) is not None:
            self.transition.update(dt)
        self._tick_toast(dt)
        # SplashLogoScene：停留满 1s 后 replaceScene(MainMenuScene)
        if getattr(self, "splash", None) is not None:
            self.splash.update(dt)
            if self.splash.done:
                self.splash = None
                self.goto("menu")
            return
        # 关卡选择框的入场动画（DialogLevelSelect::enterAnimation）。
        #   slide = (1 - anim*3) * 20
        # 就恒等于 20，对话框整体永久下移 20 像素，滑入动画也从不播放。
        if self.scene == "level" and self.level_dialog is not None:
            self.level_dialog.update(dt)
        # 主菜单进场动画（背景推近 / 开始按钮回弹 / 粒子光斑）
        if self.scene == "menu" and self.main_menu is not None:
            self.main_menu.update(dt)
        if self.scene == "battle":
            paused = self.dialog is not None and type(self.dialog).__name__ in (
                "PauseDialog",
                "SettingsDialog",
            )
            if self.battle and not paused:
                if self.revive_panel:
                    # 续天面板弹着的时候，死亡特效 / 断肢照样播完
                    # （原版 BattleScene 的 CCAction 不受 UI 面板阻挡）。
                    self.battle.tick_effects(dt)
                    self.revive_panel.update(dt)
                    if self.revive_panel.done:
                        if not self.revive_panel.revived:
                            # 放弃续天 → 失败结算（原版 DialogLevelSaveMe 放弃后
                            # 直接进 DialogLevelFailed）
                            self.battle.over = "lose"
                            if not self.battle.result:
                                self.battle.finish()
                            self.revive_panel = None
                            self.audio.lose_jingle()
                            res_data = dict(self.battle.result)
                            res_data["mission_id"] = self.mission_id
                            res_data["quota"] = self.battle.quota
                            self.result_panel = ResultPanel(res_data, self.save, self.audio)
                        else:
                            self.revive_panel = None
                else:
                    # ★ 不能写成 `elif not self.battle.over:` —— 那样一旦
                    # battle.over 置位，下面生成结果面板的分支永远进不去，
                    # 战斗就卡死在「已结束但没有结算页」。
                    # tick() 内部自己判断 over：正常时跑完整逻辑，
                    # 结束后只推进表现层（断肢 / 喷血 / 死亡淡出）。
                    was = self.battle.kills
                    was_shots = self.battle.shots
                    was_hp = self.battle.hp
                    self.battle.tick(dt)
                    if self.battle.shots > was_shots:
                        # ComboKillEffect::onWeaponFire —— 每次开火重置 2s 清连击定时
                        self.hud_fx.on_fire()
                        # ★ 开火音：按**角色**取专属枪声（GameSound 第一张表）
                        with contextlib.suppress(Exception):
                            self.audio.fire(
                                getattr(self.battle, "weapon", "ak47"),
                                getattr(self.battle, "soldier", None),
                            )
                    if self.battle.hp < was_hp:
                        # ★ 受伤音：按角色取专属（soldier_2 用 hurt_soldier_3）
                        with contextlib.suppress(Exception):
                            self.audio.soldier_hurt(getattr(self.battle, "soldier", None))
                    if self.battle.kills > was:
                        self.audio.zombie_die()
                        # ★ 击杀赏金（原版 KillBonusEffect::onKillZombie
                        #   @0x17ff90 + BattleField::addCoinBonus @0x16f0ac）：
                        #   杀一只僵尸给多少金币，查 zombie_bonus.xml
                        #   （zombie_1=300、zombie_9=12…，查不到默认 30），
                        #   在僵尸死亡位置飘「+N」+ 冒星星 + 播 coin_added 音效。
                        _kb = int(getattr(self.battle, "last_kill_bonus", 0) or 0)
                        if _kb > 0:
                            self.save.add_coins(_kb)
                            self.save.save()
                            # ★ BonusFloat 用的是 **cocos 坐标**（y 向上），
                            #   而 battle.last_kill_y 是屏幕 y（向下），
                            #   这里要换算，否则飘字会跑到屏幕顶上。
                            #   battle.last_kill_x / last_kill_y 已经是**屏幕坐标**
                            #   （bx 里减过 cam），这里只把 y 从「向下」换成
                            #   BonusFloat 用的 cocos 坐标（向上）。
                            _fx = getattr(self.battle, "last_kill_x", 0)
                            # 僵尸可能在屏幕右边缘外被打死 ⇒ 飘字 clamp 进屏内，
                            #   不然玩家只看到星星看不到「+N」。
                            _fx = max(40.0, min(854.0 - 40.0, float(_fx)))
                            self.hud_fx.add_kill_bonus_float(
                                _kb, _fx, H - getattr(self.battle, "last_kill_y", 0)
                            )
                            with contextlib.suppress(Exception):
                                self.audio.coin()
                        gained = self.hud_fx.on_kill(self.battle.kills)
                        if gained > 0:
                            self.save.add_coins(gained)
                            self.save.save()
                    if self.battle.over == "revive":
                        self.revive_panel = RevivePanel(self.battle, self.save, self.audio)
                        # ★ 阵亡音：按角色取专属（GameSound 第四张表）
                        with contextlib.suppress(Exception):
                            self.audio.soldier_death(getattr(self.battle, "soldier", None))
                        self.audio.lose_jingle()
                    elif self.battle.over and not self.result_panel:
                        if self.battle.over == "win":
                            self.audio.win_jingle()
                        else:
                            self.audio.lose_jingle()
                        if not self.battle.result:
                            self.battle.finish()
                        res_data = dict(self.battle.result)
                        res_data["mission_id"] = self.mission_id
                        res_data["quota"] = self.battle.quota
                        self.result_panel = ResultPanel(res_data, self.save, self.audio)
            # 结算面板独立于 battle 推进（战斗已结束，动画/发奖仍要跑）
            if self.result_panel:
                self.result_panel.update(dt)
            # ★ 暂停时这些 UI 计时器必须**一起冻结**。原版
            #   DialogLevelPaused 调的是 pauseSchedulerAndActions，战场和
            #   hud_fx 的 update 写在 `not paused` 分支**外面** ⇒ 暂停面板
            #   开着，机甲持续时间 / 技能冷却 / 连击计时照走，返回游戏时
            #   机甲倒计时已经归零、直接「消失」
            if not paused:
                if self.ability_bar is not None:
                    self.ability_bar.update(dt)
                if self.mech_slot is not None:
                    self.mech_slot.update(dt)
                self.hud_fx.update(dt)
        if getattr(self, "guide", None) is not None:
            self.guide.update(dt)
        if getattr(self, "achievement_panel", None) is not None:
            self.achievement_panel.update(dt)
        if getattr(self, "slot_panel", None) is not None:
            self.slot_panel.update(dt)
        if getattr(self, "failed_weapon", None) is not None:
            self._tick_failed_weapon(dt)
        if self.dialog is not None:
            self.dialog.update(dt)
            if self.dialog.done:
                self._after_dialog()
        if getattr(self, "keynav", None) is not None:
            self.keynav.update(dt)
            self.keynav.set_items(self.key_items(), self.key_signature())

    def render(self):
        s = self.frame
        s.fill((0, 0, 0))
        if getattr(self, "splash", None) is not None:
            # SplashLogoScene 铺满全屏白底 + logo，不叠任何其它场景
            self.splash.draw(s)
            return s
        # 过场期间新场景整体偏移一点，配合旧画面滑出
        ox, oy = self.transition.scene_offset() if getattr(self, "transition", None) else (0, 0)
        if ox or oy:
            # ★ 过场时整个场景先画到 tmp 再整体偏移贴回来。
            #   tmp 必须**先铺满不透明底色**：原来新建的 SRCALPHA 面是
            #   全透明的，draw_map / draw_battle 的地图背景本身带 alpha，
            #   叠在弹窗 / HUD 底下就是「背景穿帮、面板发糊」。
            tmp = pygame.Surface((W, H), pygame.SRCALPHA)
            tmp.fill((0, 0, 0, 255))
            {
                "menu": self.draw_menu,
                "map": self.draw_map,
                "level": self.draw_level,
                "shop": self.draw_shop,
                "battle": self.draw_battle,
            }[self.scene](tmp)
            s.blit(tmp, (ox, oy))
            # ★ 过场层必须画在**场景之上、UI 之下**。
            #   弹窗上，「每日任务」面板看着像半透明、地图的人物立绘从
            #   面板里透出来。UI 永远该在过场之上。
            self.transition.draw(s)
        else:
            {
                "menu": self.draw_menu,
                "map": self.draw_map,
                "level": self.draw_level,
                "shop": self.draw_shop,
                "battle": self.draw_battle,
            }[self.scene](s)
        if getattr(self, "achievement_panel", None) is not None:
            self.achievement_panel.draw(s)
        if getattr(self, "slot_panel", None) is not None:
            self.slot_panel.draw(s)
        if getattr(self, "guide", None) is not None:
            self.guide.draw(s)
        if self.dialog is not None:
            self.dialog.draw(s)
        # 全键盘焦点框：压在弹窗之上，一眼能看出「回车会点哪一个」
        if getattr(self, "keynav", None) is not None:
            self.keynav.draw(s)
        # 领奖飞行图标压在最上层（原版 UI 特效渲染层级高于弹窗内容）
        if getattr(self, "reward_fly", None) is not None:
            self.reward_fly.draw(s)
        if getattr(self, "_toast", None):
            msg, _t = self._toast
            f = pygame.font.SysFont("Microsoft YaHei", 18, bold=True)
            tw = f.render(msg, True, (255, 220, 120)).get_width()
            s.blit(f.render(msg, True, (255, 220, 120)), ((W - tw) // 2, H - 90))
        self._draw_feedback(s)
        return s

    def _draw_feedback(self, s):
        """按键反馈的整屏层：闪白 / 闪红 / 抖动。

        永远画在所有内容之上（包括弹窗），但只是叠加色块，
        不遮挡交互 —— 反馈本来就是「看到发生了什么」。
        """
        fb = getattr(self, "feedback", None)
        if fb is None:
            return
        # 点击涟漪：自绘按钮（地图、页签、设置项…）没有统一控件，
        # 靠这一层给「按下去有反应」的即时视觉。
        for rp in getattr(fb, "ripples", ()):
            x, y, t, dur, col = rp
            k = t / dur if dur > 0 else 1.0
            if k >= 1.0:
                continue
            rad = int(8 + 30 * k)
            a = int(230 * (1.0 - k) ** 1.15)
            if a <= 0:
                continue
            layer = pygame.Surface((rad * 2 + 10, rad * 2 + 10), pygame.SRCALPHA)
            c = (rad + 5, rad + 5)
            # 外圈扩散环
            pygame.draw.circle(
                layer, (col[0], col[1], col[2], a), c, rad, max(2, int(4 * (1.0 - k)) + 1)
            )
            # 起手的小亮点（0.12s 内收掉），保证「一按就亮」
            if k < 0.4:
                kk = 1.0 - k / 0.4
                pygame.draw.circle(layer, (255, 255, 255, int(170 * kk)), c, max(2, int(7 * kk)))
            s.blit(layer, (int(x) - c[0], int(y) - c[1]))
        a = fb.flash_alpha()
        if a <= 0:
            return
        ox, oy = fb.shake_offset()
        r, g, b = fb.flash_color()
        layer = pygame.Surface((W, H), pygame.SRCALPHA)
        layer.fill((r, g, b, a))
        s.blit(layer, (ox, oy))
