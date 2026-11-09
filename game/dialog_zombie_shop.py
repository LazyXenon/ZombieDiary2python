"""僵尸兑换商店 —— 原版 DialogZombieShop。

反编译依据：
  DialogZombieShop::init              @0x159320
  DialogZombieShop::getShopBar        @0x157a70
  DialogZombieShop::getShopLight      @0x15794c
  DialogZombieShop::getDialogBg       @0x157bd0
  DialogZombieShop::initZombieItems   @0x1580bc
  DialogZombieShop::initExchange      @0x158efc
  DialogZombieShop::getExchangeNode   @0x158444
  DialogZombieShop::getCCPANode       @0x158444 附近
  DialogZombieShop::isValidExchange   @0x157090
  DialogZombieShop::updateExButtons   @0x1573e8
  DialogZombieShop::onButtonExchange  @0x1595ac
  ZombieItemExDef 表初始化            @0x159b70

════════════════════════════════════════════════════════════════════
缩放分支（init）
════════════════════════════════════════════════════════════════════
  ratio = W / H
  ratio < 1.4 → scale 0.73，shop_bar 上移 H*0.10
  ratio < 1.6 → scale 0.81（1062165545），上移 H*0.07
  ratio < 1.7 → scale 0.85，上移 H*0.03
  否则        → scale 0.90（1063675494），不位移
  本机 854/480 = 1.779 → 0.90 / 0

════════════════════════════════════════════════════════════════════
布局（全部在 DialogBg，contentSize 780×420 scale 0.90）
════════════════════════════════════════════════════════════════════
DialogBg pos(W*0.5, H*0.42 + dy)
  9cell_bg.png           pos(390, 210)
  9cell_bg_1.png         setScaleX((780-80)/图宽) setScaleY((420-70)/图高) pos(390,210)
  9cell_line.png         setScaleX(780/650) anchor(0.5,1.0) pos(390, 18)
  facebook/9cell_bg_2    contentSize (780-95, 420*0.65-75) anchor(0,0) pos(50,45)
  兑换滚动区 EzNode       contentSize (780-95, 420*0.65-80) pos(50,49) clip
      └─ 内容节点 contentSize (宽, 60*9+30)
           每 3 项一组，按钮 pos x = 宽*0.395 / 0.78（首组 0.785）
  button_close.png       anchor(0.5,0.5) pos(780*0.93, 420*0.91)

shop_bar（顶栏）anchor(0.5,1.4) pos(W*0.5, H) scale 0.90
  chain.png  ×2  pos(w*0.15, h*1.08) / (w*0.81, h*1.08)
  text_zombie_shop.png  pos(w*0.5, h*0.48)

僵尸头颅（initZombieItems，3 个）
  x0 = DialogBg.w * 0.14，y = DialogBg.h * 0.76，每项 x += DialogBg.w * 0.29
    shadow.png      anchor(0,0.5)  scale 1.2  pos(x + 20, y)
    item_panel.png  scale 1.2  pos(x, y)
      zombie_skull_<i>.png  scale 0.70  pos(w*0.48, h*0.52)
      "x<count>"  EzScoreText(getTexFont(0)) anchor(0,0.5) scale 1.2 pos(x+50, y)

兑换项表（ZombieItemExDef：(coin, crystal, type?, name, req[3])）
  0: ("",        (30,30,30))          ← 特效券（type=0 货币兑换）
  1: hp_1       (5,0,0)
  2: shield_1   (0,5,0)
  3: speed_1    (0,0,5)
  4: power_1    (3,3,0)
  5: airstrike  (0,4,4)
  6: fly_1      (5,0,5)
  7: ""  type 1 (5,5,5)
  8: ""  crystal 10 (10,10,10)

isValidExchange：逐项比较 zombie_skull_<i>_count >= req[i]，全满足才可换。
"""

import math

import pygame

from engine import gridfont, res
from game.dialog import H, W, bg_dim
from game.ninecell import draw_9cell_atlas, inner_rect


LOGIC = 1.0

SHOP_BAR = "pic/ui/zk_shop/shop_bar.png"
CHAIN = "pic/ui/zk_shop/chain.png"
TITLE = "pic/ui/zk_shop/text_zombie_shop.png"
LIGHT1 = "pic/ui/zk_shop/light_1.png"
LIGHT2 = "pic/ui/zk_shop/light_2.png"
EX_BTN = "pic/ui/zk_shop/button_ex.png"
PLUS = "pic/ui/zk_shop/plus.png"
EQUAL = "pic/ui/zk_shop/equal.png"
SHADOW = "pic/ui/zk_shop/shadow.png"
PANEL = "pic/ui/shop/item_panel.png"
CLOSE_TEX = "pic/ui/dialog/button_close.png"
BG9 = "pic/ui/dialog/9cell_bg.png"
BG9_1 = "pic/ui/dialog/9cell_bg_1.png"
BG9_LINE = "pic/ui/dialog/9cell_line.png"
BG9_2 = "pic/ui/facebook/9cell_bg_2.png"
TASK_BG = "pic/ui/daily_task/task_bg.png"
TASK_BG_SPECIAL = "pic/ui/daily_task/task_bg_special.png"
GIFT_TICKET = "pic/ui/shop/gift_ticket.png"

FONT_SCORE = 0

BG_W = 780.0
BG_H = 420.0
SKULL_N = 3

EXCHANGES = [
    (0, 0, 0, "hp_1", (5, 0, 0)),
    (0, 0, 0, "shield_1", (0, 5, 0)),
    (0, 0, 0, "speed_1", (0, 0, 5)),
    (0, 0, 0, "power_1", (3, 3, 0)),
    (0, 0, 0, "airstrike", (0, 4, 4)),
    (0, 0, 0, "fly_1", (5, 0, 5)),
]


def _scale_and_dy():
    """init 的缩放分支：返回 (scale, shop_bar 的 y 偏移)。"""
    r = W / float(H) if H else 1.0
    if r < 1.4:
        return 0.73, H * 0.10
    if r < 1.6:
        return 0.81, H * 0.07
    if r < 1.7:
        return 0.85, H * 0.03
    return 0.90, 0.0


class ZombieShopDialog:
    """僵尸商店。done = True 表示关闭。"""

    def __init__(self, app):
        self.app = app
        self.t = 0.0
        self.done = False
        self.scale, self.dy = _scale_and_dy()
        self.skull_rects = []
        self.ex_rects = []
        self.close_rect = None
        self.sub_rect = None  # 兑换区九宫格外框（屏幕矩形）
        self.scroll = 0.0

    # ---------------------------------------------------------- 存档
    def skull_count(self, i):
        save = getattr(self.app, "save", None)
        d = getattr(save, "d", {}) if save else {}
        return int(d.get("zombie_skull_%d_count" % i, 0))

    def can_exchange(self, idx):
        req = EXCHANGES[idx][4]
        return all(self.skull_count(i) >= req[i] for i in range(SKULL_N))

    def do_exchange(self, idx):
        """isValidExchange → 扣头颅 → 发奖。"""
        if not self.can_exchange(idx):
            return False
        req = EXCHANGES[idx][4]
        save = getattr(self.app, "save", None)
        if not save:
            return False
        for i in range(SKULL_N):
            k = "zombie_skull_%d_count" % i
            save.d[k] = int(save.d.get(k, 0)) - req[i]
        coin, crystal, _typ, name, _req = EXCHANGES[idx]
        if coin:
            save.add_coins(coin)
        if crystal:
            save.add_crystals(crystal)
        if name:
            # type 0 的道具按「拥有数量」记
            ab = save.d.setdefault("abilities", {})
            ab[name] = int(ab.get(name, 0)) + 1
        save.save()
        # 兑换所得金币/钻石同样飞进账户
        fly = getattr(self.app, "reward_fly", None)
        if fly is not None and (coin or crystal):
            fly.spawn(427, 260, int(coin), int(crystal))
        return True

    # ---------------------------------------------------------- 交互
    def update(self, dt):
        self.t += dt

    def click(self, pos):
        if self.close_rect and self.close_rect.collidepoint(pos):
            self.done = True
            return True
        for i, r in self.ex_rects:
            if r.collidepoint(pos):
                return self.do_exchange(i)
        return False

    def wheel(self, dy):
        """dy 是**滚轮档数**（pygame MOUSEWHEEL 的 e.y，向上为 +1）。

        ★ 两个坑：
          2. 早先按「像素」理解 dy，一档滚 6000px 直接顶到底 —— 这里统一
             约定 dy 为档数，乘行高换算成像素。
        """
        step = 60.0 * self.scale
        _tops, total = self._row_tops()
        if self.sub_rect is not None:
            view = float(inner_rect(BG9_2, self.sub_rect, self.scale).h)
        else:
            view = (BG_H * 0.65 - 80.0) * self.scale
        span = max(0.0, total - view)
        self.scroll = max(0.0, min(span, self.scroll - dy * step))

    # ---------------------------------------------------------- 几何
    def _bg_origin(self):
        """DialogBg 内容左下角（屏幕 x, 顶部 y）。"""
        bw = BG_W * self.scale
        bh = BG_H * self.scale
        cx = W * 0.5
        cy = H * (0.42 + self.dy / float(H)) if H else H * 0.42
        # cocos: pos(W*0.5, H*0.42 + dy)，anchor(0.5,0.5)
        cy = H * 0.42 + self.dy
        return cx - bw / 2.0, cy - bh / 2.0, bw, bh

    # ---------------------------------------------------------- 绘制
    def draw(self, s):
        bg_dim(s, 140)
        self._draw_light(s)
        self._draw_shop_bar(s)
        self._draw_bg(s)
        self._draw_skulls(s)
        self._draw_exchanges(s)
        self._draw_close(s)

    def _draw_light(self, s):
        """getShopLight：anchor(0.5,0.0)，pos = DialogBg.pos - (w*0.3*s, -(h*0.4*s))。"""
        im = res.load_img(LIGHT1)
        if not im:
            return
        bx, by, bw, bh = self._bg_origin()
        # DialogBg pos（cocos）
        px = bx + bw / 2.0
        py = by + bh / 2.0
        lx = px - BG_W * 0.3 * self.scale
        ly = py - BG_H * 0.4 * self.scale
        iw = max(1, int(im.get_width() * self.scale))
        ih = max(1, int(im.get_height() * self.scale))
        s.blit(pygame.transform.smoothscale(im, (iw, ih)), (int(lx - iw / 2), int(H - ly)))

    def _draw_shop_bar(self, s):
        bar = res.load_img(SHOP_BAR)
        if not bar:
            return
        bw, bh = bar.get_size()
        sc = self.scale
        w = max(1, int(bw * sc))
        h = max(1, int(bh * sc))
        # anchor(0.5,1.4) pos(W*0.5, H)
        bx = W * 0.5
        by = H
        left = bx - w / 2.0
        top = H - by + (1.4 - 1.0) * h
        s.blit(pygame.transform.smoothscale(bar, (w, h)), (int(left), int(top)))

        # 内容左下角（屏幕）
        cx0 = left
        cy0 = top + h

        def blit_child(path, cx_ratio, cy_ratio):
            im = res.load_img(path)
            if not im:
                return
            iw = max(1, int(im.get_width() * sc))
            ih = max(1, int(im.get_height() * sc))
            x = cx0 + bw * cx_ratio * sc
            y = cy0 - bh * cy_ratio * sc
            s.blit(pygame.transform.smoothscale(im, (iw, ih)), (int(x - iw / 2), int(y - ih / 2)))

        blit_child(CHAIN, 0.15, 1.08)
        blit_child(CHAIN, 0.81, 1.08)
        blit_child(TITLE, 0.50, 0.48)

    def _draw_bg(self, s):
        bx, by, bw, bh = self._bg_origin()
        rect = pygame.Rect(int(bx), int(H - by - bh), int(bw), int(bh))
        draw_9cell_atlas(s, BG9, rect, self.scale)

        inner = res.load_img(BG9_1)
        if inner:
            iw = max(1, int((BG_W - 80.0) * self.scale))
            ih = max(1, int((BG_H - 70.0) * self.scale))
            ix = bx + BG_W * 0.5 * self.scale
            iy = by + BG_H * 0.5 * self.scale
            s.blit(
                pygame.transform.smoothscale(inner, (iw, ih)),
                (int(ix - iw / 2), int(H - iy - ih / 2)),
            )

        line = res.load_img(BG9_LINE)
        if line:
            lw = max(1, int(line.get_width() * (BG_W / 650.0) * self.scale))
            lh = max(1, int(line.get_height() * self.scale))
            lx = bx + BG_W * 0.5 * self.scale
            ly = by + 18.0 * self.scale
            s.blit(
                pygame.transform.smoothscale(line, (lw, lh)), (int(lx - lw / 2), int(H - ly - lh))
            )

        # 兑换区外框：contentSize (780-95, 420*0.65-75) anchor(0,0) pos(50,45)
        sub = res.load_img(BG9_2)
        if sub:
            sw = max(1, int((BG_W - 95.0) * self.scale))
            sh = max(1, int((BG_H * 0.65 - 75.0) * self.scale))
            sx = bx + 50.0 * self.scale
            sy = by + 45.0 * self.scale
            rect2 = pygame.Rect(int(sx), int(H - sy - sh), sw, sh)
            draw_9cell_atlas(s, BG9_2, rect2, self.scale)
            self.sub_rect = rect2

    def _draw_skulls(self, s):
        """initZombieItems：3 个头颅格 + 数量。"""
        bx, by, _bw, _bh = self._bg_origin()
        sc = self.scale
        shadow = res.load_img(SHADOW)
        panel = res.load_img(PANEL)
        if not panel:
            return
        font = gridfont.get_font(FONT_SCORE)
        lx = bx + BG_W * 0.14 * sc
        ly = by + BG_H * 0.76 * sc
        self.skull_rects = []
        for i in range(SKULL_N):
            if shadow:
                iw = max(1, int(shadow.get_width() * 1.2 * sc))
                ih = max(1, int(shadow.get_height() * 1.2 * sc))
                # pos(x + 20, y)，anchor(0,0.5)
                sx = lx + 20.0 * sc
                s.blit(
                    pygame.transform.smoothscale(shadow, (iw, ih)), (int(sx), int(H - ly - ih / 2))
                )

            pw = max(1, int(panel.get_width() * 1.2 * sc))
            ph = max(1, int(panel.get_height() * 1.2 * sc))
            s.blit(
                pygame.transform.smoothscale(panel, (pw, ph)),
                (int(lx - pw / 2), int(H - ly - ph / 2)),
            )
            self.skull_rects.append(pygame.Rect(int(lx - pw / 2), int(H - ly - ph / 2), pw, ph))

            skull = res.load_img("pic/items/zombie_skull_%d.png" % i)
            if skull:
                kw = max(1, int(skull.get_width() * 0.7 * sc))
                kh = max(1, int(skull.get_height() * 0.7 * sc))
                kx = lx + panel.get_width() * 1.2 * sc * 0.48
                ky = ly - panel.get_height() * 1.2 * sc * 0.52
                # 该 skull 是 item_panel 的子节点，坐标相对 panel 左下
                kx = (lx - pw / 2) + pw * 0.48
                ky = (ly - ph / 2) + ph * 0.52
                s.blit(
                    pygame.transform.smoothscale(skull, (kw, kh)),
                    (int(kx - kw / 2), int(H - ky - kh / 2)),
                )

            if font:
                font.draw(
                    s,
                    "x%d" % self.skull_count(i),
                    lx + 50.0 * sc,
                    H - ly,
                    1.2 * sc,
                    align=(0.0, 0.5),
                )

            lx += BG_W * 0.29 * sc

    def _draw_exchanges(self, s):
        """initExchange：EzNode 滚动区，每项一张 task_bg + 材质串 + 等号 + 奖励。

        反编译：EzNode contentSize (780-95, 420*0.65-80)，pos(50,49)（cocos 左下）。
        内容节点 contentSize (vw, 60*9+30)，每项按钮 anchor(0.5,1.0)，
        y 从内容高往下递减（v39 -= 90 / 60）。
        """
        bx, by, _bw, _bh = self._bg_origin()
        sc = self.scale
        if self.sub_rect is not None:
            clip = inner_rect(BG9_2, self.sub_rect, sc)
        else:
            vw = (BG_W - 95.0) * sc
            vh = (BG_H * 0.65 - 80.0) * sc
            vbottom = by + 49.0 * sc
            clip = pygame.Rect(int(bx + 50.0 * sc), int(H - (vbottom + vh)), int(vw), int(vh))
        vw = float(clip.w)

        s.set_clip(clip)
        self.ex_rects = []
        tops, _total = self._row_tops()
        # 列表从内框顶边开始往下排，滚动量整体**向上**平移。
        # ★ 这里原本是 `clip.top + self.scroll`：向下滚动会让整列往下走，
        #   第 0 行一眨眼就掉出裁剪区，`break` 立刻触发 ⇒ 滚到底时列表整个空白
        #   （只剩骷髅头那行没被裁掉）。方向必须是减。
        base = clip.top - self.scroll
        for idx in range(len(EXCHANGES)):
            top_y = base + tops[idx]
            if top_y > clip.bottom:
                break
            self._draw_exchange(s, idx, clip.x + vw * 0.5, top_y, sc, clip)
        s.set_clip(None)

    def _row_tops(self):
        """每行顶端偏移与内容总高。

        ★ 固定 60 的步进只对普通行（task_bg 512×40）成立；
          需要 30 个首领头颅的「special」行用的是 task_bg_special（511×77），
          看起来像「图标浮在蓝条上方」。改成按实际贴图高度推进。
        """
        sc = self.scale
        step = 60.0 * sc
        tops = []
        y = 0.0
        for idx in range(len(EXCHANGES)):
            tops.append(y)
            path = TASK_BG_SPECIAL if EXCHANGES[idx][4][0] == 30 else TASK_BG
            im = res.load_img(path)
            h = float(im.get_height()) if im else 40.0
            y += max(step, h * sc * 0.94)
        return tops, y

    def _draw_exchange(self, s, idx, cx, top_y, sc, clip):
        bg = res.load_img(TASK_BG)
        req = EXCHANGES[idx][4]
        if req[0] == 30:
            bg = res.load_img(TASK_BG_SPECIAL) or bg
        if not bg:
            return
        bw, bh = bg.get_size()
        tw = max(1, int(bw * sc))
        th = max(1, int(bh * sc))
        # task_bg 是按钮容器的一部分，按 button_ex 的宽度对齐
        btn = res.load_img(EX_BTN)
        ah = max(1, int((btn.get_height() if btn else th) * sc))
        if top_y + ah < clip.top or top_y > clip.bottom:
            return

        s.blit(pygame.transform.smoothscale(bg, (tw, th)), (int(cx - tw / 2), int(top_y)))

        # 材质串：逐个头颅图标 + 数量，从容器左侧往右排
        x = cx - tw / 2 + 8.0 * sc
        my = top_y + th * 0.45
        need = sum(1 for v in req if v > 0)
        font = gridfont.get_font(FONT_SCORE)
        drawn = 0
        for i in range(SKULL_N):
            if req[i] <= 0:
                continue
            sk = res.load_img("pic/items/zombie_skull_%d.png" % i)
            if sk:
                kw = max(1, int(sk.get_width() * 0.6 * sc))
                kh = max(1, int(sk.get_height() * 0.6 * sc))
                s.blit(pygame.transform.smoothscale(sk, (kw, kh)), (int(x), int(my - kh / 2)))
                x += kw + 5.0 * sc
            if font:
                txt = "x%d" % req[i]
                tw2, _ = font.text_size(txt, 0.8 * sc)
                font.draw(s, txt, x, my, 0.8 * sc, align=(0.0, 0.5))
                x += tw2 + 6.0 * sc
            drawn += 1
            if drawn < need:
                pl = res.load_img(PLUS)
                if pl:
                    pw = max(1, int(pl.get_width() * 0.9 * sc))
                    ph = max(1, int(pl.get_height() * 0.9 * sc))
                    s.blit(pygame.transform.smoothscale(pl, (pw, ph)), (int(x), int(my - ph / 2)))
                    x += pw + 6.0 * sc

        cap = th * 0.92  # 奖励图标不许顶出蓝条
        rw, _rh = self._reward_span(idx, sc, cap)
        rx = cx + tw * 0.5 - 12.0 * sc - rw  # 奖励图标左沿
        eq = res.load_img(EQUAL)
        ew = eh = 0
        if eq:
            ew = max(1, int(eq.get_width() * sc))
            eh = max(1, int(eq.get_height() * sc))
            s.blit(
                pygame.transform.smoothscale(eq, (ew, eh)),
                (int(rx - ew - 8.0 * sc), int(my - eh / 2)),
            )

        # 奖励图标
        self._draw_reward(s, idx, rx, my, sc, cap)

        ok = self.can_exchange(idx)
        if not ok:
            dim = pygame.Surface((tw, th), pygame.SRCALPHA)
            dim.fill((26, 34, 56, 70))
            s.blit(dim, (int(cx - tw / 2), int(top_y)))
        self.ex_rects.append((idx, pygame.Rect(int(cx - tw / 2), int(top_y), tw, th)))

    def _reward_icon(self, idx):
        """返回奖励图标 (path, 图标缩放, 是否带数量文字)。"""
        coin, crystal, _typ, name, _req = EXCHANGES[idx]
        if name:
            return "pic/ui/shop/ability_%s.png" % name, 0.85, ""
        if coin > 0:
            return "pic/ui/common/coin.png", 0.85, str(coin)
        if crystal > 0:
            return "pic/ui/common/crystal.png", 0.85, str(crystal)
        return GIFT_TICKET, 1.0, ""

    def _reward_span(self, idx, sc, max_h=0.0):
        """奖励簇的外形尺寸（图标 + 可能跟着的数量文字）。"""
        path, k, txt = self._reward_icon(idx)
        im = res.load_img(path)
        if not im:
            return 0.0, 0.0
        iw = max(1.0, im.get_width() * k * sc)
        ih = max(1.0, im.get_height() * k * sc)
        if max_h > 0 and ih > max_h:
            f = max_h / ih
            iw *= f
            ih = max_h
        w = iw
        if txt:
            font = gridfont.get_font(FONT_SCORE)
            if font:
                w += 2.0 * sc + font.text_size(txt, 0.8 * sc)[0]
        return w, ih

    def _draw_reward(self, s, idx, cx, cy, sc, max_h=0.0):
        path, k, txt = self._reward_icon(idx)
        im = res.load_img(path)
        if not im:
            return
        iw = max(1.0, im.get_width() * k * sc)
        ih = max(1.0, im.get_height() * k * sc)
        if max_h > 0 and ih > max_h:
            f = max_h / ih
            iw *= f
            ih = max_h
        iw, ih = max(1, int(iw)), max(1, int(ih))
        s.blit(pygame.transform.smoothscale(im, (iw, ih)), (int(cx), int(cy - ih / 2)))
        if txt:
            font = gridfont.get_font(FONT_SCORE)
            if font:
                font.draw(s, txt, cx + iw + 2.0 * sc, cy, 0.8 * sc, align=(0.0, 0.5))

    def _draw_currency(self, s, cx, cy, sc, val, path, fi):
        icon = res.load_img(path)
        if not icon:
            return
        iw = max(1, int(icon.get_width() * 0.85 * sc))
        ih = max(1, int(icon.get_height() * 0.85 * sc))
        s.blit(pygame.transform.smoothscale(icon, (iw, ih)), (int(cx), int(cy - ih / 2)))
        font = gridfont.get_font(fi)
        if font:
            font.draw(s, str(val), cx + iw + 2.0 * sc, cy, 0.8 * sc, align=(0.0, 0.5))

    def _draw_close(self, s):
        im = res.load_img(CLOSE_TEX)
        if not im:
            return
        bx, by, _bw, _bh = self._bg_origin()
        sc = self.scale
        iw = max(1, int(im.get_width() * sc))
        ih = max(1, int(im.get_height() * sc))
        x = bx + BG_W * 0.93 * sc
        y = by + BG_H * 0.91 * sc
        rect = pygame.Rect(int(x - iw / 2), int(H - y - ih / 2), iw, ih)
        s.blit(pygame.transform.smoothscale(im, (iw, ih)), rect.topleft)
        self.close_rect = rect
