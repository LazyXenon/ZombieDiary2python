"""音频子系统：BGM 切换 + 音效池。

素材路径（原版卷内命名，交接文档 §4.5）：
* assets/raw/music/  — menu.mp3 / battle.mp3 / game_win.mp3 / game_lose.mp3 / reels_spin.mp3
* assets/raw/sounds/ — 83 个 ogg（武器/僵尸/UI）

pygame.mixer 预初始化所有 83+5 个通道避免运行时卡顿；BGM 单通道循环，音效
随机池（death_soldier_1..5 等）用随机挑选。
"""

import contextlib
import os
import random

import pygame


ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "raw")

# ---------------------------------------------------------------- 角色专属音效
# 反编译 GameSound::init（all_merged.c:105940-106230）里四张
# 「角色名 → 音效文件」映射表，逐条抄下来：
#   攻击音 / 受伤音 / 台词 / 死亡音。
SOLDIER_FIRE_SFX = {
    "soldier_1": "desert_eagle",
    "soldier_2": "saw",
    "soldier_3": "m4",
    "soldier_4": "rifle",
    "soldier_5": "sword",
    "soldier_6": "sword",
    "soldier_7": "ak47",
}
SOLDIER_HURT_SFX = {
    "soldier_1": "hurt_soldier_1",
    "soldier_2": "hurt_soldier_3",
    "soldier_3": "hurt_soldier_1",
    "soldier_4": "hurt_soldier_1",
    "soldier_5": "hurt_soldier_1",
    "soldier_6": "hurt_soldier_1",
    "soldier_7": "hurt_soldier_1",
}
SOLDIER_TALK_SFX = {"soldier_%d" % i: "talk_soldier_%d" % i for i in range(1, 8)}
SOLDIER_DEATH_SFX = {
    "soldier_1": "death_soldier_1",
    "soldier_2": "death_soldier_2",
    "soldier_3": "death_soldier_3",
    "soldier_4": "death_soldier_4",
    "soldier_5": "death_soldier_5",
    "soldier_6": "death_soldier_3",  # 忍者复用 3 号
    "soldier_7": "death_soldier_5",  # 机甲狗复用 5 号
}


class Audio:
    def __init__(self):
        self._bgm = None
        self._bgm_name = None
        self._sfx_cache = {}
        self._music_cache = {}
        self.enabled_music = True
        self.enabled_sfx = True
        self._ok = False

    def ensure(self):
        """惰性初始化 mixer（headless 模式下 mixer 可能启动失败，要兜底）。"""
        if self._ok:
            return True
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            self._ok = True
        except pygame.error:
            return False
        return True

    # ------------------------------------------------------------ BGM
    def bgm(self, name):
        """切换 BGM；同名跳过。name ∈ menu/battle/game_win/game_lose。"""
        if not self.ensure() or not self.enabled_music:
            return
        if self._bgm_name == name:
            return
        path = os.path.join(ROOT, "music", name + ".mp3")
        if not os.path.exists(path):
            return
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(0.6)
            pygame.mixer.music.play(-1)
            self._bgm_name = name
        except pygame.error as e:
            print("bgm err:", e)

    def stop_bgm(self):
        if self.ensure():
            pygame.mixer.music.stop()
            self._bgm_name = None

    def set_music(self, on):
        """音乐开关（原版 EzGameData::setMusic）。"""
        self.enabled_music = bool(on)
        if not on:
            if self.ensure():
                pygame.mixer.music.pause()
        else:
            if self.ensure() and self._bgm_name:
                with contextlib.suppress(pygame.error):
                    pygame.mixer.music.unpause()

    def set_sound(self, on):
        """音效开关（原版 EzGameData::setSound）。"""
        self.enabled_sfx = bool(on)

    # ------------------------------------------------------------ SFX
    def _load(self, fname):
        key = fname
        if key not in self._sfx_cache:
            path = os.path.join(ROOT, "sounds", fname)
            if not os.path.exists(path):
                self._sfx_cache[key] = None
                return None
            try:
                self._sfx_cache[key] = pygame.mixer.Sound(path)
            except pygame.error:
                self._sfx_cache[key] = None
        return self._sfx_cache[key]

    def sfx(self, names, volume=0.8):
        """播放音效；names 可以是单名或列表（随机挑一个，死亡音效池用）。"""
        if not self.ensure() or not self.enabled_sfx:
            return
        if isinstance(names, str):
            names = [names]
        pool = [n for n in names if n]
        if not pool:
            return
        name = random.choice(pool)
        snd = self._load(name + ".ogg" if not name.endswith(".ogg") else name)
        if snd:
            snd.set_volume(volume)
            snd.play()

    # 常用事件快捷方式
    def ui_click(self):
        self.sfx("bn_pressed", 0.7)

    def ui_press(self):
        """按下音：比 click 轻，避免按住拖动时噪音。"""
        self.sfx("bn_pressed", 0.35)

    def error(self):
        """无效操作：金币不足 / 槽位已满 / 未解锁。"""
        self.sfx("lose_life", 0.6)

    def upgrade(self):
        """升级成功。"""
        self.sfx("upgrade_gun", 0.9)

    def coin(self):
        self.sfx("coin_added", 0.8)

    def buy(self):
        self.sfx("buy_bullet_1", 0.8)

    def zombie_die(self):
        self.sfx(["zombie_die0", "zombie_die1", "zombie_die2", "zombie_die3"], 0.6)

    def soldier_hurt(self, soldier=None):
        """受伤音：按当前角色取专属音效。"""
        name = SOLDIER_HURT_SFX.get(soldier or "")
        if name:
            self.sfx(name, 0.6)
        else:
            self.sfx(["hurt_soldier_1", "hurt_soldier_3"], 0.6)

    def soldier_talk(self, soldier=None):
        """台词：点角色时播（商店 / 战斗开始）。"""
        name = SOLDIER_TALK_SFX.get(soldier or "")
        if name:
            self.sfx(name, 0.7)

    def soldier_death(self, soldier=None):
        name = SOLDIER_DEATH_SFX.get(soldier or "")
        if name:
            self.sfx(name, 0.7)

    def fire(self, weapon="ak47", soldier=None):
        """开火音：优先用角色的专属枪声（GameSound 第一张表）。"""
        name = SOLDIER_FIRE_SFX.get(soldier or "")
        self.sfx(name or weapon, 0.5)

    def win_jingle(self):
        """胜利：切结算 BGM 一次性。"""
        if not self.ensure() or not self.enabled_music:
            return
        path = os.path.join(ROOT, "music", "game_win.mp3")
        if os.path.exists(path):
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.play(0)
                self._bgm_name = "game_win"
            except pygame.error:
                pass

    def lose_jingle(self):
        if not self.ensure() or not self.enabled_music:
            return
        path = os.path.join(ROOT, "music", "game_lose.mp3")
        if os.path.exists(path):
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.play(0)
                self._bgm_name = "scene_win_lose"
            except pygame.error:
                pass

    def star(self):
        self.sfx("final_star", 0.9)
