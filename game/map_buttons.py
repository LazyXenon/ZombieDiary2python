"""世界地图的按钮层 —— 原版 MapLayer::initUI。

反编译依据（D:\\Code\\dsh\\full_dump\\all_merged.c，MapLayer::initUI）：
  button_shop          pic/ui/map/button_shop.png          anchor(0.5,0.5) pos(bgW*0.83, bgH*0.28)
  button_achivement    pic/ui/map/button_achivement.png    anchor(0.5,0.5) pos(bgW*0.15, bgH*0.28)
  button_setting       pic/ui/map/button_setting.png       anchor(0.5,0.5) pos(bgW*0.27, bgH*0.28)
  每日任务             v180                                 anchor(0.5,0.5) pos(W*0.06, H*0.5)    scale 1.2
  僵尸商店             v177                                 anchor(0.5,0.5) pos(W*0.15, H*0.5)    scale 0.6
  button_slots         pic/ui/map/button_slots.png          anchor(1.0,0.5) pos(W, H*0.6)      scale v131
  button_reward_notify pic/ui/map/button_reward_notify.png anchor(1.0,0.5) pos(W, H*0.4)      scale v131

v131 是按宽高比分段选的缩放：
    ratio < 1.4        → 0.75
    ratio < 1.6        → 0.83
    ratio >= 1.67      → 1.0
    其余               → 0.9
854/480 = 1.779 → 1.0

v122 是地图背景 pic/map_bg01.jpg 的 contentSize = (854, 480)，
所以 v132 = bgH * 0.28 = 134.4（cocos y 向上）。
"""

import pygame

from app.constants import MAP_PLUS_SIZE, MAP_PLUS_X, MAP_PLUS_Y
from engine import res
from game.dialog import H, W


BG_TEX = "pic_bg_1/map_bg01.jpg"
UP_BAR_TEX = "pic/ui/map/map_up_bar.png"

SHOP_TEX = "pic/ui/map/button_shop.png"
ACHIEV_TEX = "pic/ui/map/button_achivement.png"
SETTING_TEX = "pic/ui/map/button_setting.png"
SLOTS_TEX = "pic/ui/map/button_slots.png"
# 原版 MapLayer::initUI 的右侧通知按钮。原版帧上写的是「签到」金字，
# 另一版素材写成「兑奖公告」让人认不出这是签到入口；这里沿用同一张
# 蓝色梯形底 + 银边 + 喇叭，只把文字换回原版「签到」金字。
REWARD_NOTIFY_TEX = "pic/ui/map/button_signin.png"

DAILY_SCALE = 1.2
ZOMBIE_SHOP_SCALE = 0.6

# 每日任务 / 僵尸商店的原版贴图名（反编译里 v180 / v177）
DAILY_TEX = "pic/ui/daily_task/task.png"
ZOMBIE_SHOP_TEX = "pic/ui/zk_shop/icon.png"


def _edge_scale(ratio):
    """v131 的分段缩放。"""
    if ratio < 1.4:
        return 0.75
    if ratio < 1.6:
        return 0.83
    if ratio >= 1.67:
        return 1.0
    return 0.9


def _anchored(w, h, px, py, ax, ay, scale):
    """cocos anchor → pygame Rect。cocos y 向上，屏幕 y = H - cocosY。

    px/py 是**锚点**的世界坐标（cocos），矩形中心落在锚点上。
    """
    sw, sh = w * scale, h * scale
    left = px - ax * sw
    bottom = py - ay * sh
    return pygame.Rect(
        int(round(left)), int(round(H - bottom - sh)), int(round(sw)), int(round(sh))
    )


class MapButtons:
    """地图上的 7 个按钮，位置全部由反编译公式算出。"""

    def __init__(self, app):
        self.app = app
        self.rects = {}
        self._geo()

    def _geo(self):
        bar = res.load_img(UP_BAR_TEX)
        bw, bh = bar.get_size() if bar else (W, 58)
        # map_up_bar：anchor(0.5,1.0) 在 (W*0.5, H) → 顶边贴屏幕顶，
        # 局部原点在 (0, H-bh) = (0, 422)。
        bar_ox, bar_oy = 0.0, H - bh
        v132 = bh * 0.28
        edge = _edge_scale(W / float(H))

        shop = res.load_img(SHOP_TEX)
        if shop:
            self.rects["shop"] = _anchored(
                shop.get_width(),
                shop.get_height(),
                bar_ox + bw * 0.83,
                bar_oy + v132,
                0.5,
                0.5,
                1.0,
            )

        ach = res.load_img(ACHIEV_TEX)
        if ach:
            self.rects["achivement"] = _anchored(
                ach.get_width(), ach.get_height(), bar_ox + bw * 0.15, bar_oy + v132, 0.5, 0.5, 1.0
            )

        st = res.load_img(SETTING_TEX)
        if st:
            self.rects["setting"] = _anchored(
                st.get_width(), st.get_height(), bar_ox + bw * 0.27, bar_oy + v132, 0.5, 0.5, 1.0
            )

        daily = res.load_img(DAILY_TEX)
        if daily:
            self.rects["daily"] = _anchored(
                daily.get_width(), daily.get_height(), W * 0.06, H * 0.5, 0.5, 0.5, DAILY_SCALE
            )

        zs = res.load_img(ZOMBIE_SHOP_TEX)
        if zs:
            self.rects["zombie_shop"] = _anchored(
                zs.get_width(), zs.get_height(), W * 0.15, H * 0.5, 0.5, 0.5, ZOMBIE_SHOP_SCALE
            )

        slots = res.load_img(SLOTS_TEX)
        if slots:
            self.rects["slots"] = _anchored(
                slots.get_width(), slots.get_height(), W, H * 0.6, 1.0, 0.5, edge
            )

        notify = res.load_img(REWARD_NOTIFY_TEX)
        if notify:
            self.rects["reward_notify"] = _anchored(
                notify.get_width(), notify.get_height(), W, H * 0.4, 1.0, 0.5, edge
            )

        self.rects["add_crystal"] = pygame.Rect(
            int(MAP_PLUS_X), int(MAP_PLUS_Y), MAP_PLUS_SIZE, MAP_PLUS_SIZE
        )

    # ------------------------------------------------------------ 命中
    def hit(self, pos):
        """返回命中的按钮名或 None。后加的按钮在上层。"""
        for name in (
            "shop",
            "achivement",
            "setting",
            "daily",
            "zombie_shop",
            "slots",
            "add_crystal",
            "reward_notify",
        ):
            r = self.rects.get(name)
            if r and r.collidepoint(pos):
                return name
        return None

    def get(self, name):
        return self.rects.get(name)
