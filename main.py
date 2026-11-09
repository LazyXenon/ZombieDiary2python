# pyright: basic
import contextlib
import json  # 历史入口重导出，外部截图/回归脚本会写 main.xxx
import os
import sys


sys.dont_write_bytecode = True  # 游戏目录只留源码，不落 __pycache__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame

from app import App
from app.constants import HP_BAR_X, HP_BAR_Y, H, W
from engine import res
from engine import scene as SC
from engine.audio import Audio
from engine.skel import Skeleton
from game import map_points as MP
from game import shop_money as SM
from game import shop_tabs as ST
from game import shopui as SU
from game import soldier_sprite as ssprite
from game import transition as TR
from game import zombie_sprite as zsprite
from game.achievement import AchievementPanel
from game.battle import (
    GROUND_Y,
    SOLDIER_BASE,
    SOLDIER_FOOT_Y,
    SOLDIER_SCALE,
    Battle,
    load_level_list,
    load_zombie_stats,
)
from game.battle_abilities import AbilityBar
from game.battle_bg import ScrollBackground, load_scroll_background, pick_bg_config
from game.battle_weapons import WeaponSlots
from game.dialog_daily import DailyTaskDialog
from game.dialog_daily_reward import DailyRewardDialog
from game.dialog_equip_remind import EquipRemindDialog
from game.dialog_exp_weapon import ExpWeaponDialog
from game.dialog_failed_weapon import FailedWeaponDialog
from game.dialog_game_intro import GameIntroduceDialog
from game.dialog_gun_upgrade import GunUpgradeDialog
from game.dialog_level_select import LevelSelectDialog
from game.dialog_pause import PauseDialog
from game.dialog_potion import PotionDialog
from game.dialog_settings import SettingsDialog
from game.dialog_soldier_upgrade import SoldierUpgradeDialog
from game.dialog_zombie_shop import ZombieShopDialog
from game.hud_fx import HudFx
from game.main_menu import MainMenu
from game.map_buttons import MapButtons
from game.result import ResultPanel
from game.revive import RevivePanel
from game.save import Save
from game.shop_table import BY_NAME as SU_BY_NAME
from game.slot import SlotPanel
from game.splash import SplashScene
from game.user_guide import UserGuide
from game.weapons import load_upgrade_table, load_weapons, weapon_sfx


CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")


class AspectWindow:
    """854×480 等比拉伸窗口；逻辑帧居中缩放，鼠标坐标反映射。"""

    MIN_SCALE = 0.5
    MAX_SCALE = 4.0

    def __init__(self, app, icon=None):
        self.app = app
        self.icon = icon
        st = app.save.d.setdefault("settings", {})
        try:
            scale = float(st.get("window_scale", 1.0) or 1.0)
        except (TypeError, ValueError):
            scale = 1.0
        self.window_size = self._size_from_scale(scale)
        self.fullscreen = bool(st.get("fullscreen", False))
        self.screen = pygame.Surface((1, 1))
        self._set_mode()

    def _size_from_scale(self, scale):
        scale = max(self.MIN_SCALE, min(self.MAX_SCALE, float(scale)))
        return max(1, int(round(W * scale))), max(1, int(round(H * scale)))

    def _set_mode(self):
        if self.fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
        if self.icon is not None:
            with contextlib.suppress(Exception):
                pygame.display.set_icon(self.icon)

    def handle_resize(self, event):
        """拖动窗口时只保留一个方向的变化，另一边按 854:480 补齐。"""
        if self.fullscreen:
            return False
        old_w, old_h = self.screen.get_size()
        ew, eh = max(1, int(event.w)), max(1, int(event.h))
        dw = abs(ew - old_w) / float(max(1, old_w))
        dh = abs(eh - old_h) / float(max(1, old_h))
        if dh > dw:
            lo, hi = int(H * self.MIN_SCALE), int(H * self.MAX_SCALE)
            h = max(lo, min(hi, eh))
            w = int(round(h * W / float(H)))
        else:
            lo, hi = int(W * self.MIN_SCALE), int(W * self.MAX_SCALE)
            w = max(lo, min(hi, ew))
            h = int(round(w * H / float(W)))
        size = (max(1, w), max(1, h))
        if size == (old_w, old_h):
            return False
        self.window_size = size
        self._set_mode()
        cb = getattr(self.app, "note_window_scale", None)
        if callable(cb):
            cb(size[0] / float(W))
        return True

    def toggle_fullscreen(self, enabled):
        on = bool(enabled)
        if on == self.fullscreen:
            return on
        if on:
            self.window_size = self.screen.get_size()
        self.fullscreen = on
        self._set_mode()
        return on

    def _view(self):
        sw, sh = self.screen.get_size()
        scale = min(sw / float(W), sh / float(H))
        dw = max(1, int(round(W * scale)))
        dh = max(1, int(round(H * scale)))
        return (sw - dw) // 2, (sh - dh) // 2, dw, dh

    def logical_pos(self, pos):
        ox, oy, dw, dh = self._view()
        x = int((pos[0] - ox) * W / float(dw))
        y = int((pos[1] - oy) * H / float(dh))
        return max(0, min(W - 1, x)), max(0, min(H - 1, y))

    def present(self, frame):
        ox, oy, dw, dh = self._view()
        self.screen.fill((0, 0, 0))
        if (dw, dh) == (W, H):
            self.screen.blit(frame, (ox, oy))
        else:
            self.screen.blit(pygame.transform.smoothscale(frame, (dw, dh)), (ox, oy))
        pygame.display.flip()


def _log_crash():
    # 崩溃日志：写到项目相邻的 cache 目录，不在游戏目录里留文件
    import datetime
    import traceback

    out_dir = CACHE_DIR
    name = "crash_%s.log" % datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, name)
    tb = traceback.format_exc()
    print(tb)
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(tb)
    except OSError:
        pass
    return path


def _crash_screen(screen, last, msg):
    """定格上一帧 + 压暗 + 报错文字（顺手把 traceback 落盘）。"""
    import traceback

    path = _log_crash()
    surf = pygame.Surface(screen.get_size())
    if last is not None:
        surf.blit(last, (0, 0))
    else:
        surf.fill((24, 18, 14))
    dim = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 190))
    surf.blit(dim, (0, 0))
    font = pygame.font.SysFont("Microsoft YaHei", 20, bold=True)
    lines = [msg, "日志：%s" % path]
    # 异常类型 + 最后一行（真正的原因），够玩家反馈用
    exc_line = traceback.format_exception_only(*sys.exc_info()[:2])[-1].strip()
    lines.append(exc_line[:90])
    y = surf.get_height() // 2 - len(lines) * 16
    for ln in lines:
        t = font.render(ln, True, (255, 226, 190))
        surf.blit(t, ((surf.get_width() - t.get_width()) // 2, y))
        y += 32
    return surf


def main():
    pygame.init()
    app = App()
    app.goto("menu")
    # 窗口图标：取原版 APK 的启动图标（res/drawable-480dpi/icon.png）。
    try:
        _icon = res.load_img("pic/ui/app/icon.png")
    except Exception:
        _icon = None
    win = AspectWindow(app, _icon)
    app.bind_fullscreen(win.toggle_fullscreen)
    _root = os.path.dirname(os.path.abspath(__file__))
    pygame.display.set_caption("萌僵尸大战2 - Python 复刻  [%s]" % _root)
    print("[BUILD] entry = %s" % os.path.abspath(__file__))
    print("[BUILD] game  = %s" % getattr(sys.modules.get("game"), "__file__", "?"))
    clock = pygame.time.Clock()
    running = True
    crash_surf = None
    last_good = None
    while running:
        dt = min(clock.tick(60) / 1000.0, 0.05)
        if crash_surf is not None:
            win.screen.blit(crash_surf, (0, 0))
            for e in pygame.event.get():
                if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                    running = False
            pygame.display.flip()
            continue
        try:
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                elif e.type == pygame.VIDEORESIZE:
                    win.handle_resize(e)
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                    if not app.escape():
                        running = False
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    pos = win.logical_pos(e.pos)
                    app.press(pos)
                    app.click(pos)
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 3:
                    app.right_click(win.logical_pos(e.pos))
                elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                    app.release()
                elif e.type == pygame.MOUSEWHEEL:
                    app.wheel(e.y or 0)
                elif e.type == pygame.MOUSEMOTION:
                    app.drag_to(win.logical_pos(e.pos))
                elif e.type == pygame.KEYDOWN:
                    if not app.key_down(e.key) and e.key == pygame.K_p and app.scene == "battle":
                        app.goto("map")
                elif e.type == pygame.KEYUP:
                    app.key_up(e.key)
            app.step(dt)
            win.present(app.render())
            last_good = win.screen.copy()
        except Exception:
            crash_surf = _crash_screen(
                win.screen, last_good, "发生错误，日志已写入 cache\n按 ESC 退出"
            )
    pygame.quit()


def shot(scene="menu", path=None, t=0.0, mission=None):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    if not pygame.get_init():
        pygame.init()
    if not pygame.display.get_init():
        pygame.display.set_mode((1, 1))
    app = App()
    app.audio.enabled_music = False
    app.audio.enabled_sfx = False
    app.scene = scene
    # 截图默认跳过启动 Logo（splash 分支会把它单独装回来）
    app.splash = None
    if mission is not None:
        app.mission_id = int(mission)
    if scene == "battle":
        app.start_mission(app.mission_id)
        app.t = t
        steps = max(1, int(round((t if t > 0 else 3.0) / 0.016)))
        app.battle.hold_fire = True
        for _ in range(steps):
            app.step(0.016)
    elif scene == "daily_reward":
        app.scene = "map"
        d = DailyRewardDialog(app)
        d.day = 2
        d.claimed = set(range(1, 2))
        d.page = d._page_of(2)
        d.t = 1.0
        app.dialog = d
    elif scene == "achievement":
        app.scene = "map"
        p = AchievementPanel(app)
        p.progress[0] = 1
        p.claimed.add(1)
        app.achievement_panel = p
    elif scene == "level_select":
        app.scene = "level"
        d = LevelSelectDialog(app, app.mission_id)
        d.anim = 1.0
        app.level_dialog = d
    elif scene == "user_guide":
        app.scene = "map"
        app.save.d.pop("level", None)  # 别再写这个键（current_level 不读它了）
        app.save.d["ug_day_1"] = 0
        app.guide = UserGuide(app, "hello")
    elif scene == "splash":
        app.scene = "menu"
        app.splash = SplashScene(app)
        app.splash.t = 1.0
    elif scene == "exp_weapon":
        app.scene = "map"
        d = ExpWeaponDialog(app, "ak47")
        d.anim = 1.0
        app.dialog = d
    elif scene == "failed_weapon":
        app.scene = "map"
        d = FailedWeaponDialog(app, "ak47", 0.75, 300)
        d.anim = 1.0
        app.dialog = d
    elif scene == "zombie_shop":
        app.scene = "map"
        app.save.d["zombie_skull_0_count"] = 12
        app.save.d["zombie_skull_1_count"] = 4
        app.save.d["zombie_skull_2_count"] = 2
        d = ZombieShopDialog(app)
        app.dialog = d
    elif scene == "equip_remind":
        app.scene = "shop"
        d = EquipRemindDialog(app, 1)
        d.t = 1.0
        app.dialog = d
    elif scene == "equip_remind_ability":
        app.scene = "shop"
        d = EquipRemindDialog(app, 2)
        d.t = 1.0
        app.dialog = d
    elif scene == "slot":
        app.scene = "map"
        p = SlotPanel(app)
        p.free_spins[1] = 1
        app.slot_panel = p
    elif scene == "result_lose":
        app.start_mission(app.mission_id)
        app.battle.over = "lose"
        app.battle.finish()
        res_data = dict(app.battle.result)
        res_data["mission_id"] = app.mission_id
        res_data["quota"] = app.battle.quota
        app.result_panel = ResultPanel(res_data, app.save, None)
        app.scene = "battle"
        app.result_panel.t = 2.5
        app.result_panel.update(0.01)
    elif scene == "result_win":
        app.start_mission(app.mission_id)
        app.battle.over = "win"
        app.battle.finish()
        res_data = dict(app.battle.result)
        res_data["mission_id"] = app.mission_id
        res_data["quota"] = app.battle.quota
        app.result_panel = ResultPanel(res_data, app.save, None)
        app.scene = "battle"
        app.result_panel.t = 1.5
        app.result_panel.update(0.01)
    surf = app.render()
    if path:
        pygame.image.save(surf, path)
    return surf


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--shot":
        sc = sys.argv[2] if len(sys.argv) > 2 else "menu"
        out = sys.argv[3] if len(sys.argv) > 3 else ("py_%s.png" % sc)
        shot(sc, out)
        print("saved", out)
    else:
        main()
