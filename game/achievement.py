"""成就面板 —— 原版 AchievementLayer + AchievementItem + ScrollNode。

反编译依据：
  AchievementLayer::init             @0x130018
  AchievementLayer::addAchievementItems @0x12ffa0
  AchievementLayer::initCoinAndCrystal  @0x12e33c 附近
  AchievementItem::init              @0x12f4f0
  AchievementItem::getCoinOrCrystalNode @0x12df08
  AchievementItem::getReward         @0x13049c
  AchievementManager::AchievementManager @0x12e5f0（26 条成就表）
  AchievementManager::getAchievementProgress @0x????
  ScrollNode::init / addCell / scrollToCell @0x1358b0 / 0x135974 / 0x135???

════════════════════════════════════════════════════════════════════
层结构（cocos y 向上，屏幕 y = H - y）
════════════════════════════════════════════════════════════════════
AchievementLayer
  ├─ ScrollNode  contentSize (W*0.6, H*0.8)  pos (W*0.49, H*0.43)  anchor(0.5,0.5)
  │    └─ content  anchor(0,1)  pos(0, 容器高)     ← addCell 里建的内容节点
  │         └─ AchievementItem × 26  anchor(0,1)
  │              y = -(cellH + 10) * index
  ├─ 背景 pic_bg_1/shop_bg.jpg  pos(W*0.5, H*0.5)  setScale(H / 图高)   ← 356 = setScale
  ├─ 顶栏 pic/ui/shop/up_bar.png  anchor(0.5,1.0)  pos(W*0.5, H)
  │    setScale(W/854)（<1.4 → W*1.08/854，<1.6 → W*1.06/854）
  │    ├─ 标题 achivement_title.png  pos(854*0.31, 98*0.66)
  │    └─ 金币/钻石节点  anchor(0,0.5)  pos(854*0.53, 98*0.64)  scale 0.7
  └─ 返回 button_back.png  anchor(0,0)  pos(0, H*0.03)
       scale = 0.64 / 0.73 / 0.80 / 0.85（按比例 1.4/1.6/1.7 分支）

════════════════════════════════════════════════════════════════════
AchievementItem（bg_2 = achievement_bg_2.png 516×120，**只有它**被 setScale(a3)）
════════════════════════════════════════════════════════════════════
contentSize = (516*a3, 120*a3)；anchor 由 addCell 改成 (0,1)。
其余子节点全部**不缩放**，坐标也全部以原始 516×120 为单位：

  bg_2   anchor(0,1)   pos(0, 120*a3)      scale a3
  bg_1   anchor(0.5,0.5) pos(516*0.11, 120*0.54)     仅 state>0
  标题图 anchor(0,0.5) pos(516*0.25, 120*0.69)       即 <icon>.png（中文标题）
  前缀图 anchor(0,0.5) pos(516*0.25, 120*0.48)
  数字   anchor(0,0.5) pos(前缀x + 3 + 前缀宽, 120*0.48)  scale 0.5  字库 7
  后缀图 anchor(0,0.5) pos(数字x + 数字宽*0.5 + 2, 120*0.48)
  进度   anchor(0,0.5) pos(516*0.25, 120*0.27)  scale 0.5  字库 7  "%d/%d"
  奖励   anchor(1,0.5) pos(516*0.85, 120*0.30)  scale 0.52
  按钮   anchor(0.1,0.5) pos(516*a3, 120*a3*0.5) scale a3  仅 state==1

ScrollNode::addCell 的行距常量来自构造：this[66] = this[67] = 10.0。
"""

import pygame

from engine import gridfont, res
from game.dialog import H, W, default_close_rect, draw_close_icon
from game.map_points import current_level


LOGIC = 1.0

BG_TEX = "pic_bg_1/shop_bg.jpg"
TOP_BAR_TEX = "pic/ui/shop/up_bar.png"
TITLE_TEX = "pic/ui/achievment/achivement_title.png"
BACK_TEX = "pic/ui/shop/button_back.png"
ITEM_BG_TEX = "pic/ui/achievment/achievement_bg_2.png"
ITEM_DONE_TEX = "pic/ui/achievment/achievement_bg_1.png"
ITEM_REWARD_BTN = "pic/ui/achievment/button_get_reward.png"
COIN_TEX = "pic/ui/common/coin.png"
CRYSTAL_TEX = "pic/ui/common/crystal.png"

FONT_NUM = 7  # getTexFont(7) = achivement_number.png
FONT_COIN = 1  # getTexFont(1) = score_gold.png
FONT_CRYSTAL = 3  # getTexFont(3) = score_blue.png

ITEM_W = 516.0  # 原始底图尺寸；子节点坐标单位
ITEM_H = 120.0
CELL_GAP = 10.0  # ScrollNode 构造 this[66]/this[67] = 10.0f

_SCALE_14 = 0.78  # 1061662228 = 0.78f
_SCALE_16 = 0.84  # 1062668861 = 0.84f
_SCALE_DEFAULT = 0.92  # 1064011039 = 0.92f

_BACK_14 = 0.64
_BACK_16 = 0.73
_BACK_17 = 0.80
_BACK_DEFAULT = 0.85

# ---------------------------------------------------------------- 成就表
# AchievementManager::AchievementManager @0x12e5f0 逐条
#   AchievementDef::AchievementDef(icon, title, desc, kind, coin, crystal, target)
ACHIEVEMENTS = [
    ("first_blood.png", "KILL THE FIRST ZOMBIE", "kills", 500, 0, 1),
    ("newbie.png", "KILL 100 ZOMBIES", "kills", 1000, 0, 100),
    ("unstoppeable.png", "KILL 500 ZOMBIES", "kills", 2500, 0, 500),
    ("boss_killer.png", "KILL 10 BOSSES", "boss_kills", 5000, 0, 10),
    ("killing_machine.png", "KILL 1000 ZOMBIES", "kills", 5000, 0, 1000),
    ("boss_terminator.png", "KILL 50 BOSSES", "boss_kills", 0, 50, 50),
    ("monster_killer.png", "KILL 5000 ZOMBIES", "kills", 20000, 0, 5000),
    ("zombie_terminator.png", "KILL 10000 ZOMBIES", "kills", 0, 25, 10000),
    ("king_of_world.png", "KILL 50000 ZOMBIES", "kills", 50000, 0, 50000),
    ("god_like.png", "KILL 100000 ZOMBIES", "kills", 0, 100, 100000),
    ("zombie_beginner.png", "SPEND 10 MINS KILLING ZOMBIES", "times", 500, 0, 10),
    ("zombie_fan.png", "SPEND 30 MINS KILLING ZOMBIES", "times", 1000, 0, 30),
    ("zombie_fanatic.png", "SPEND 1 HOUR KILLING ZOMBIES", "times", 5000, 0, 60),
    ("zombie_expert.png", "SPEND 2 HOURS KILLING ZOMBIES", "times", 0, 25, 120),
    ("zombie_scientist.png", "SPEND 5 HOURS KILLING ZOMBIES", "times", 30000, 0, 300),
    ("zombie_artist.png", "SPEND 10 HOURS KILLING ZOMBIES", "times", 0, 50, 600),
    ("second_lieutenant.png", "STAY ALIVE FOR 5 DAYS", "levels", 1000, 0, 5),
    ("lieutenant.png", "STAY ALIVE FOR 10 DAYS", "levels", 2500, 0, 10),
    ("captain.png", "STAY ALIVE FOR 15 DAYS", "levels", 5000, 0, 15),
    ("major.png", "STAY ALIVE FOR 20 DAYS", "levels", 10000, 0, 20),
    ("lieutenant_colonel.png", "STAY ALIVE FOR 25 DAYS", "levels", 0, 25, 25),
    ("colonel.png", "STAY ALIVE FOR 30 DAYS", "levels", 20000, 0, 30),
    ("brigadier_general.png", "STAY ALIVE FOR 40 DAYS", "levels", 30000, 0, 40),
    ("major_general.png", "STAY ALIVE FOR 60 DAYS", "levels", 0, 100, 60),
    ("weapon_collector.png", "COLLECT 10 WEAPONS", "weapons", 10000, 0, 10),
    ("arms_dealer.png", "COLLECT ALL WEAPONS", "weapons", 0, 100, 30),
]

# kind → (前缀图, 后缀图)，AchievementItem::init 的 5 个分支
_KIND_TEX = {
    "levels": ("text_survive.png", "text_day.png"),
    "kills": ("text_kill.png", "text_zombie.png"),
    "boss_kills": ("text_kill.png", "text_boss_zombie.png"),
    "times": ("text_survive.png", "text_minute.png"),
    "weapons": ("text_collect.png", "text_weapon.png"),
}


def _ratio():
    return (W / float(H)) if H else 1.0


def _item_scale():
    """this[95]：item 缩放，按 W/H 分支（默认 0.92）。"""
    r = _ratio()
    if r < 1.4:
        return _SCALE_14
    if r < 1.6:
        return _SCALE_16
    return _SCALE_DEFAULT


def _back_scale():
    r = _ratio()
    if r < 1.4:
        return _BACK_14
    if r < 1.6:
        return _BACK_16
    if r < 1.7:
        return _BACK_17
    return _BACK_DEFAULT


def _topbar_scale():
    bar = res.load_img(TOP_BAR_TEX)
    if not bar:
        return 1.0
    r = _ratio()
    if r < 1.4:
        return (W * 1.08) / bar.get_width()
    if r < 1.6:
        return (W * 1.06) / bar.get_width()
    return W / float(bar.get_width())


class AchievementPanel:
    """成就面板（原版 AchievementLayer）。"""

    def __init__(self, app):
        self.app = app
        self.t = 0.0
        self.scroll = 0.0  # 列表已滚动的像素（cocos 单位）
        self.done = False
        self.back_rect = None
        self.close_rect = default_close_rect(True)
        self.reward_rects = []  # [(index, screen_rect)]
        self.progress = {}
        save = getattr(app, "save", None)
        d = getattr(save, "d", {}) if save else {}
        self.claimed = set(int(i) for i in (d.get("achievement_claimed") or []))
        self._sync_progress()

    # ------------------------------------------------------------ 数据
    def _sync_progress(self):
        """AchievementManager::getAchievementProgress 的 5 个分支。"""
        save = getattr(self.app, "save", None)
        d = getattr(save, "d", {}) if save else {}
        self.progress = {}
        for i, (_icon, _title, kind, _c, _cr, target) in enumerate(ACHIEVEMENTS):
            if kind == "kills":
                v = int(d.get("total_kills", 0))
            elif kind == "boss_kills":
                v = int(d.get("total_boss_kills", 0))
            elif kind == "times":
                v = int(d.get("total_times", 0)) // 60  # 秒 → 分钟
            elif kind == "levels":
                try:
                    level_db = getattr(self.app, "level_db", None)
                    level_no = max(0, current_level(save, level_db) - 1)
                except Exception:
                    level_no = max(0, len(d.get("passed_missions", []) or []) - 1)
                v = level_no
            elif kind == "weapons":
                # 原版 AchievementManager::getAchievementProgress @0x128274
                # （all_merged.c:4279）的 weapons 分支：遍历 ShopItemParser
                # 里的**所有枪定义**，统计「存档里该枪的值 > 0」的个数
                # ⇒ 统计的是**已拥有的枪**，不是升级过的枪。
                # 「COLLECT 10 WEAPONS」永远凑不齐。
                v = len(d.get("owned_weapons", []) or [])
            else:
                v = 0
            self.progress[i] = min(int(v), target)

    def state(self, i):
        """0 = 未达成，1 = 可领取，2 = 已领取。"""
        _icon, _title, _kind, _c, _cr, target = ACHIEVEMENTS[i]
        if i in self.claimed:
            return 2
        return 1 if self.progress.get(i, 0) >= target else 0

    def first_new_index(self):
        """getFirstNewAchievementIndex：可领取的第一条，没有则 -1。"""
        for i in range(len(ACHIEVEMENTS)):
            if self.state(i) == 1:
                return i
        return -1

    # ------------------------------------------------------------ 交互
    def update(self, dt):
        self.t += dt

    def click(self, pos):
        if self.close_rect and self.close_rect.collidepoint(pos):
            self.done = True
            return True
        if self.back_rect and self.back_rect.collidepoint(pos):
            self.done = True
            return True
        for i, r in self.reward_rects:
            if r.collidepoint(pos):
                self._claim(i)
                return True
        return False

    def _claim(self, i):
        if self.state(i) != 1:
            return
        self.claimed.add(i)
        _icon, _title, _kind, coin, crystal, _t = ACHIEVEMENTS[i]
        save = getattr(self.app, "save", None)
        if save:
            if coin:
                save.add_coins(coin)
            if crystal:
                save.add_crystals(crystal)
            save.d["achievement_claimed"] = sorted(self.claimed)
            save.save()
        fly = getattr(self.app, "reward_fly", None)
        if fly is not None and (coin or crystal):
            r = next((rr for idx, rr in self.reward_rects if idx == i), None)
            x0, y0 = (r.centerx, r.centery) if r else (427, 240)
            fly.spawn(x0, y0, int(coin), int(crystal))

    def wheel(self, dy):
        """dy = 滚轮档数（向上 +1）。

        ★ 早先直接 `scroll + dy` 当成像素，一档只挪 1px，滚轮等于没用；
        现在一档 = 一行（ITEM_H + 间距），方向也统一成「向上滚 = 回到前面」。
        """
        step = ITEM_H * _item_scale() + CELL_GAP
        total = step * len(ACHIEVEMENTS) - CELL_GAP
        limit = max(0.0, total - H * 0.8)
        self.scroll = max(0.0, min(limit, self.scroll - dy * step))

    # ------------------------------------------------------------ 几何
    def _view(self):
        """ScrollNode 视口：返回屏幕矩形。

        ★ 视口左缘从原版参考帧（feat/achievement.png，854×480）反推：
          卡片底图 516 宽 × a3(0.92) = 474.7，实测紫色卡片 x 从 **183** 起，
          整体比原版左移 21px —— 卡片压到返回按钮上，右侧按钮也偏左。
        """
        left = W * 0.214  # 183 / 854
        vw = W * 0.6
        top = H * 0.16  # 视口顶；实测卡片亮紫行从 101 起（与原版一致）
        vh = H * 0.80
        return pygame.Rect(int(left), int(top), int(vw), int(vh))

    # ------------------------------------------------------------ 绘制
    def draw(self, s):
        self._draw_bg(s)
        self._draw_items(s)
        self._draw_topbar(s)
        self._draw_back(s)
        draw_close_icon(s, self.close_rect)

    def _draw_bg(self, s):
        bg = res.load_img(BG_TEX)
        if not bg:
            return
        bw, bh = bg.get_size()
        sc = H / float(bh)  # 427×240 × 2 = 854×480，正好铺满
        w = max(1, int(bw * sc))
        h = max(1, int(bh * sc))
        im = pygame.transform.smoothscale(bg, (w, h))
        s.blit(im, (int(W * 0.5 - w / 2), int(H * 0.5 - h / 2)))

    def _draw_topbar(self, s):
        bar = res.load_img(TOP_BAR_TEX)
        if not bar:
            return
        bw, bh = bar.get_size()
        sc = _topbar_scale()
        w = max(1, int(bw * sc))
        h = max(1, int(bh * sc))
        bx = int(W * 0.5 - w / 2)
        by = 0  # anchor(0.5,1.0) pos y = H → 贴屏幕顶
        s.blit(pygame.transform.smoothscale(bar, (w, h)), (bx, by))

        # 标题：pos(854*0.31, 98*0.66)，坐标相对顶栏内容左下角
        title = res.load_img(TITLE_TEX)
        if title:
            tx = bx + bw * 0.31 * sc
            ty = by + h - bh * 0.66 * sc
            s.blit(title, (int(tx - title.get_width() / 2), int(ty - title.get_height() / 2)))

        self._draw_currency(s, bx, by, bw, bh, sc)

    def _draw_currency(self, s, bx, by, bw, bh, sc):
        """initCoinAndCrystal，逐像素照抄反编译的推进链。

        容器 anchor(0,0.5) scale 0.7 pos(顶栏.w*0.53, 顶栏.h*0.64)，
        contentSize = (总宽, 图标高=50)。
          金币图标 anchor(0.5,0.5) pos(cw*0.5, ch*0.5)
          金币数字 anchor(0,0.5) scale 1.6 pos(cw + cw*0.1, ch*0.5) = (55, 25)
          v48 = 55 + 数字宽*1.6 + cw                       ← 钻石图标左缘
          钻石图标 anchor(0.5,0.5) pos(v48 + cw2*0.5, ch*0.5)
          v49 = v48 + cw2 + cw*0.1                          ← 钻石数字左缘
          钻石数字 anchor(0,0.5) scale 1.6 pos(v49, ch*0.5)
        """
        coin = res.load_img(COIN_TEX)
        crystal = res.load_img(CRYSTAL_TEX)
        if not coin or not crystal:
            return
        save = getattr(self.app, "save", None)
        d = getattr(save, "d", {}) if save else {}
        n_coin = int(d.get("coins", 0))
        n_crys = int(d.get("crystals", 0))

        k = 0.7
        cw, ch = coin.get_size()
        xw, _xh = crystal.get_size()
        f_coin = gridfont.get_font(FONT_COIN)
        f_crys = gridfont.get_font(FONT_CRYSTAL)
        t_coin = str(n_coin)
        t_crys = str(n_crys)
        n1 = f_coin.text_size(t_coin, 1.6)[0] if f_coin else 0
        n2 = f_crys.text_size(t_crys, 1.6)[0] if f_crys else 0

        gap = cw * 0.1
        x_coin_num = cw + gap  # 55
        x48 = x_coin_num + n1 + cw  # 105 + n1
        x49 = x48 + xw + gap
        total_w = x49 + n2

        # 容器 contentSize=(total_w, ch)，anchor(0,0.5) → 内容左下 = pos - (0, ch*0.5)
        pos_cx = bw * 0.53
        pos_cy = bh * 0.64  # cocos 向上，相对顶栏内容左下
        left_cocos = pos_cx
        bottom_cocos = pos_cy - ch * 0.5

        # 顶栏内容左下 → 屏幕
        bar_left = bx
        bar_bottom_screen = by + bh * sc
        ox = bar_left + left_cocos * sc
        oy = bar_bottom_screen - bottom_cocos * sc

        def img_at(img, cx_local, cy_local):
            iw = max(1, int(img.get_width() * k))
            ih = max(1, int(img.get_height() * k))
            im = pygame.transform.smoothscale(img, (iw, ih))
            s.blit(im, (int(ox + cx_local * k - iw / 2), int(oy - cy_local * k - ih / 2)))

        def txt_at(font, txt, x_local, cy_local, w_local=None):
            if font:
                font.draw(s, txt, ox + x_local * k, oy - cy_local * k, 1.6 * k, align=(0.0, 0.5))

        img_at(coin, cw * 0.5, ch * 0.5)
        txt_at(f_coin, t_coin, x_coin_num, ch * 0.5, n1)
        img_at(crystal, x48 + xw * 0.5, ch * 0.5)
        txt_at(f_crys, t_crys, x49, ch * 0.5, n2)
        del total_w

    def _draw_back(self, s):
        im = res.load_img(BACK_TEX)
        if not im:
            return
        sc = _back_scale()
        w = max(1, int(im.get_width() * sc))
        h = max(1, int(im.get_height() * sc))
        x = 0
        y = int(H - H * 0.03 - h)
        s.blit(pygame.transform.smoothscale(im, (w, h)), (x, y))
        self.back_rect = pygame.Rect(x, y, w, h)

    def _draw_items(self, s):
        a3 = _item_scale()
        cell_h = ITEM_H * a3
        step = cell_h + CELL_GAP
        view = self._view()
        # 原版没有 ClippingNode（dump 里无任何 clip 符号），按钮会溢出视口，照做
        self.reward_rects = []
        y = view.top - self.scroll
        for i in range(len(ACHIEVEMENTS)):
            if y > view.bottom:
                break
            if y + cell_h > view.top:
                self._draw_item(s, i, view.left, y, a3)
            y += step

    def _draw_item(self, s, i, ix, iy, a3):
        icon, _title, kind, coin, crystal, target = ACHIEVEMENTS[i]
        cell_h = ITEM_H * a3
        st = self.state(i)

        # bg_2 anchor(0,1) pos(0, 120*a3)，scale a3
        bg = res.load_img(ITEM_BG_TEX)
        if not bg:
            return
        s.blit(
            pygame.transform.smoothscale(bg, (int(ITEM_W * a3), int(cell_h))), (int(ix), int(iy))
        )

        # ★ 子节点坐标全部要乘 a3 —— 反编译里 these 坐标是**父节点内容坐标**，
        # 文字/图标却没乘 ⇒ 0.92 倍下文字相对底图偏左上约 (16, 4)，
        # 成就名压在左边徽章上、进度条和数字对不齐。

        # 已达成：bg_1 anchor(0.5,0.5) pos(516*0.11, 120*0.54)
        if st >= 1:
            seal = res.load_img(ITEM_DONE_TEX)
            if seal:
                s.blit(
                    seal,
                    (
                        int(ix + ITEM_W * 0.11 * a3 - seal.get_width() / 2),
                        int(iy + cell_h - ITEM_H * 0.54 * a3 - seal.get_height() / 2),
                    ),
                )

        # 标题图 anchor(0,0.5) pos(516*0.25, 120*0.69)
        ic = res.load_img("pic/ui/achievment/" + icon)
        if ic:
            s.blit(
                ic,
                (
                    int(ix + ITEM_W * 0.25 * a3),
                    int(iy + cell_h - ITEM_H * 0.69 * a3 - ic.get_height() / 2),
                ),
            )

        # 文本行 y = 120*0.48
        row_y = iy + cell_h - ITEM_H * 0.48 * a3
        x = ix + ITEM_W * 0.25 * a3
        pair = _KIND_TEX.get(kind)
        if pair:
            pre = res.load_img("pic/ui/achievment/" + pair[0])
            if pre:
                s.blit(pre, (int(x), int(row_y - pre.get_height() / 2)))
                x += LOGIC * 3.0 + pre.get_width()

        num_font = gridfont.get_font(FONT_NUM)
        if num_font:
            txt = str(target)
            gw, _gh = num_font.text_size(txt, 0.5)
            num_font.draw(s, txt, x, row_y, 0.5, align=(0.0, 0.5))
            x += gw + LOGIC * 2.0
        if pair:
            suf = res.load_img("pic/ui/achievment/" + pair[1])
            if suf:
                s.blit(suf, (int(x), int(row_y - suf.get_height() / 2)))

        # 进度 "%d/%d" anchor(0,0.5) pos(516*0.25, 120*0.27) scale 0.5
        if num_font:
            cur = target if st >= 1 else min(self.progress.get(i, 0), target)
            num_font.draw(
                s,
                "%d/%d" % (cur, target),
                ix + ITEM_W * 0.25 * a3,
                iy + cell_h - ITEM_H * 0.27 * a3,
                0.5,
                align=(0.0, 0.5),
            )

        # 奖励节点 anchor(1,0.5)，scale 0.52。
        # ★ 横向比例从原版参考帧反推：金币右缘在屏幕 x≈565，
        #   底图左缘约 200 ⇒ 内容坐标 (565-200)/0.92 = 397 = 516*0.769。
        self._draw_reward(
            s, ix + ITEM_W * 0.77 * a3, iy + cell_h - ITEM_H * 0.30 * a3, coin, crystal
        )

        # 领取按钮 anchor(0.1,0.5) pos(516*a3, 120*a3*0.5) scale a3
        if st == 1:
            btn = res.load_img(ITEM_REWARD_BTN)
            if btn:
                bw = max(1, int(btn.get_width() * a3))
                bh = max(1, int(btn.get_height() * a3))
                # ★ 领取按钮位置也从参考帧反推：按钮左缘在屏幕 x≈630，
                #   底图左缘 200 ⇒ 内容坐标 (630-200)/0.92 = 467 = 516*0.905。
                bx = ix + ITEM_W * 0.905 * a3
                by = iy + cell_h * 0.5
                rect = pygame.Rect(int(bx), int(by - bh / 2), bw, bh)
                s.blit(pygame.transform.smoothscale(btn, (bw, bh)), rect.topleft)
                self.reward_rects.append((i, rect))

    def _draw_reward(self, s, ax, ay, coin, crystal):
        """getCoinOrCrystalNode @0x12df08。

        节点 contentSize = (图标宽 + 数字宽*1.6, 图标高)，整体 setScale(0.52)，
        anchor(1,0.5)。图标 anchor(0.5,0.5) 在 (w/2, h/2)；
        数字 anchor(0,0.5) setScale(1.6) 在 (w, h/2)。文字就是纯数字。
        """
        sc = 0.52
        if coin > 0:
            tex, val, fi = COIN_TEX, coin, FONT_COIN
        elif crystal > 0:
            tex, val, fi = CRYSTAL_TEX, crystal, FONT_CRYSTAL
        else:
            return
        icon = res.load_img(tex)
        if not icon:
            return
        font = gridfont.get_font(fi)
        txt = str(val)
        nw = font.text_size(txt, 1.6)[0] if font else 0
        iw_raw, ih_raw = icon.get_size()
        total = (iw_raw + nw) * sc
        left = ax - total
        iw = max(1, int(iw_raw * sc))
        ih = max(1, int(ih_raw * sc))
        s.blit(pygame.transform.smoothscale(icon, (iw, ih)), (int(left), int(ay - ih / 2)))
        if font:
            font.draw(s, txt, left + iw_raw * sc, ay, 1.6 * sc, align=(0.0, 0.5))


def claimable_count(app):
    """还能领取的成就条数 —— 地图「荣誉殿堂」按钮上的红点数字。

    原版 MapLayer::checkAchievementEffect 硬编码传 0，角标永远是个「0」；
    这里按真实进度算，一条都没有就返回 0（调用方不画角标）。
    """
    try:
        p = AchievementPanel(app)
        return sum(1 for i in range(len(ACHIEVEMENTS)) if p.state(i) == 1)
    except Exception:
        return 0
