"""失败弹窗的推荐枪械（打折）—— 原版 DialogFailedWeapon。

反编译依据：
  DialogFailedWeapon::init              @0x15f934
  DialogFailedWeapon::getCoinOrCrystalNode @0x15f5e0
  DialogFailedWeapon::setGunInfo        @0x15fdd4（+ 续体 sub_15FEAE @0x15feae）
  DialogFailedWeapon::updateDiscountTime @0x15fc7c
  DialogFailedWeapon::onUpdate          @0x15fd68
  DialogFailedWeapon::enterAnimation    @0x15f3c0
  DialogFailedWeapon::quitAnimation     @0x15f44c
  DialogFailedWeapon::onButtonBuy       @0x15f880
  DialogFailedWeapon::onButtonClose     @0x15f498

════════════════════════════════════════════════════════════════════
结构
════════════════════════════════════════════════════════════════════
DialogFailedWeapon
  ├─ upgrade_bg.png  anchor(0.5,0.5)  pos(W*0.5, H*0.52)
  │    └─ 容器 EzNode  contentSize = upgrade_bg 尺寸 (493×315)
  │         anchor(0.5,0.5)  pos(w*0.5, h*0.5)
  │           ├─ text_power.png       anchor(1,0.5) scale 0.75 pos(w*0.57, h*0.47)
  │           ├─ PropertyCells       scale 0.75 pos(w*0.59, h*0.47)
  │           ├─ text_frate.png      anchor(1,0.5) scale 0.75 pos(w*0.57, h*0.40)
  │           ├─ PropertyCells       scale 0.75 pos(w*0.59, h*0.40)
  │           ├─ text_crit.png       anchor(1,0.5) scale 0.75 pos(w*0.57, h*0.33)
  │           ├─ PropertyCells       scale 0.75 pos(w*0.59, h*0.33)
  │           ├─ 枪名图              pos(w*0.5, h*0.905) scale 1.1
  │           ├─ text_powerful.png   pos(w*0.5, h*0.80)  scale 1.1
  │           ├─ text_discount_left  pos(w*0.4, h*0.70)  anchor(0.5,0.5)
  │           ├─ 倒计时 EzTexText(font 0) pos(w*0.57, h*0.70) anchor(0,0.5) scale 0.85
  │           ├─ 原价节点            pos(w*0.18, h*0.59) anchor(0,0.5) scale 0.57
  │           │    └─ delete_line    scaleX = 原价宽*1.05/线宽, scaleY 2.0
  │           │                      pos(原价宽*0.5, 原价高*0.5)
  │           ├─ 折扣价节点          pos(w*0.55, h*0.59) anchor(0,0.5) scale 0.57
  │           ├─ upgrade_arrow.png   pos(w*0.5, h*0.59)  scale 0.60
  │           └─ gun_<name>.png      pos(w*0.27, h*0.40) scale 1.3
  ├─ button_buy.png   anchor(0.5,0.5) scale 0.9 pos(w*0.5, h*0.20)
  └─ button_close.png anchor(0.5,0.5) scale 0.8 pos(w*0.91, h*0.96)

getCoinOrCrystalNode(a2, a3)：
  金币分支：coin.png anchor(0.0,0.54) pos(0, h*0.5)；
            数字 font 1 anchor(0,0.5) scale 1.6 pos(w*1.1, h*0.5)
  钻石分支：crystal.png anchor(0.0,0.5) pos(0, h*0.5)；其余同上（font 3）
  最后整节点 setScale(0.57)。

倒计时文本：`"0%d:0%d" % (sec//60 % 60, sec % 60)`（原版就是两段 "0%d"）。
onUpdate：累计 dt ≥ 1 时扣 1 秒并刷新文本；剩余 ≤ 0 时关闭。
"""

import contextlib

import pygame

from engine import gridfont, res
from game.dialog import H, W, bg_dim


LOGIC = 1.0

BG_TEX = "pic/ui/shop/upgrade_bg.png"
BUY_TEX = "pic/ui/dialog/button_buy.png"
CLOSE_TEX = "pic/ui/dialog/button_close.png"
COIN_TEX = "pic/ui/common/coin.png"
CRYSTAL_TEX = "pic/ui/common/crystal.png"
DEL_LINE_TEX = "pic/ui/bank/delete_line.png"
ARROW_TEX = "pic/ui/shop/upgrade_arrow.png"
TEXT_POWER = "pic/ui/shop/text_power.png"
TEXT_FRATE = "pic/ui/shop/text_frate.png"
TEXT_CRIT = "pic/ui/shop/text_crit.png"
TEXT_POWERFUL = "pic/ui/dialog/text_powerful.png"
TEXT_DISCOUNT = "pic/ui/dialog/text_discount_left.png"

FONT_SCORE = 0
FONT_COIN = 1
FONT_CRYSTAL = 3

NODE_SCALE = 0.57  # getCoinOrCrystalNode 末尾 setScale
BUY_SCALE = 0.9
CLOSE_SCALE = 0.8
DEFAULT_SECONDS = 300  # gun_discount_second 缺省由存档提供；此处给可玩默认


def _gun_art(name):
    return "pic/ui/upgrade/gun_%s.png" % name


def _gun_title(name):
    from game.shop_table import SHOP_GUNS

    for g in SHOP_GUNS:
        if g["name"] == name:
            return g["title"]
    return "pic/ui/shop/%s.png" % name


class FailedWeaponDialog:
    """推荐枪械弹窗。done = True 表示关闭。"""

    def __init__(self, app, gun="ak47", discount=0.75, seconds=DEFAULT_SECONDS):
        self.app = app
        self.gun = gun
        self.rate = discount
        self.remaining = int(seconds)
        self.t = 0.0
        self.done = False
        self.anim = 0.0  # enterAnimation 进度
        self.closing = 0.0
        self.buy_rect = None
        self.close_rect = None
        self._bg = None

    # ---------------------------------------------------------- 数据
    def price(self):
        """原价来自 SHOP_GUNS 的 coin/crystal 字段（= GunItemDef）。"""
        from game.shop_table import SHOP_GUNS

        for g in SHOP_GUNS:
            if g["name"] == self.gun:
                return int(g.get("coin", 0)), int(g.get("crystal", 0))
        return 0, 0

    def discounted(self):
        coin, crystal = self.price()
        return int(float(coin) * self.rate), int(float(crystal) * self.rate)

    def timer_text(self):
        s = max(0, self.remaining)
        return "0%d:0%d" % (s // 60 % 60, s % 60)

    # ---------------------------------------------------------- 交互
    def update(self, dt):
        self.t += dt
        if self.anim < 1.0:
            self.anim = min(1.0, self.anim + dt / 0.2)  # CCMoveTo 0.2s
        if self.closing > 0:
            self.closing += dt
            if self.closing >= 0.2:
                self.done = True
            return
        if self.remaining <= 0:
            self.close()
            return
        self.t_acc = getattr(self, "t_acc", 0.0) + dt
        if self.t_acc >= 1.0:
            self.t_acc -= 1.0
            self.remaining -= 1
            if self.remaining <= 0:
                self.close()

    def close(self):
        if self.closing <= 0:
            self.closing = 0.0001

    def click(self, pos):
        if self.close_rect and self.close_rect.collidepoint(pos):
            self.close()
            return True
        if self.buy_rect and self.buy_rect.collidepoint(pos):
            save = getattr(self.app, "save", None)
            if save is not None:
                coin, crystal = self.discounted()
                if coin and not save.spend_coins(coin):
                    return False
                if crystal and not save.spend_crystals(crystal):
                    if coin:
                        save.add_coins(coin)
                    return False
                if self.gun not in save.d["owned_weapons"]:
                    save.d["owned_weapons"].append(self.gun)
                # 原版 onButtonBuy → Soldier::onChangeWeapon：买完立刻换上，
                # 不然玩家买了一把枪还得自己回军火库装备，体验断裂。
                with contextlib.suppress(Exception):
                    save.equip(self.gun)
                g = {}
                try:
                    from game.shop_table import BY_NAME

                    g = BY_NAME.get(self.gun) or {}
                except Exception:
                    g = {}
                if not g.get("inf"):
                    key = "%s_bullet" % self.gun
                    save.d[key] = max(int(save.d.get(key) or 0), int(g.get("bullet_count") or 0))
                save.save()
            self.close()
            return True
        return False

    # ---------------------------------------------------------- 绘制
    def draw(self, s):
        bg_dim(s, 140)
        bg = res.load_img(BG_TEX)
        if not bg:
            return
        bw, bh = bg.get_size()
        self._bg = bg
        # enterAnimation：从 H*0.52 + h*0.6 滑到 H*0.52
        target_y = H * 0.52
        start_y = target_y + bh * 0.6
        k = self.anim
        if self.closing > 0:
            k = max(0.0, 1.0 - self.closing / 0.2)
        cy = target_y + (start_y - target_y) * (1.0 - k)

        left = W * 0.5 - bw / 2.0
        top = H - cy - bh / 2.0
        s.blit(bg, (int(left), int(top)))

        # 容器：contentSize = bg 尺寸，anchor(0.5,0.5) pos(w*0.5,h*0.5)
        cx0 = left
        cy0 = top + bh  # 屏幕 y（内容底边）
        self._draw_contents(s, cx0, cy0, bw, bh)
        self._draw_buttons(s, cx0, cy0, bw, bh)

    def _draw_contents(self, s, cx0, cy0, bw, bh):
        def blit(path, rx, ry, ax=0.5, ay=0.5, scale=1.0):
            im = res.load_img(path)
            if not im:
                return None
            iw = max(1, int(im.get_width() * scale))
            ih = max(1, int(im.get_height() * scale))
            x = cx0 + bw * rx
            y = cy0 - bh * ry
            sub = pygame.transform.smoothscale(im, (iw, ih))
            s.blit(sub, (int(x - iw * ax), int(y - ih * (1.0 - ay))))
            return im

        blit(TEXT_POWER, 0.57, 0.47, ax=1.0, scale=0.75)
        blit(TEXT_FRATE, 0.57, 0.40, ax=1.0, scale=0.75)
        blit(TEXT_CRIT, 0.57, 0.33, ax=1.0, scale=0.75)
        for k, ry in enumerate((0.47, 0.40, 0.33)):
            self._draw_cells(s, cx0, cy0, bw, bh, k, ry)

        blit(_gun_title(self.gun), 0.5, 0.905, scale=1.1)
        blit(TEXT_POWERFUL, 0.5, 0.80, scale=1.1)
        blit(TEXT_DISCOUNT, 0.4, 0.70, scale=1.0)

        font = gridfont.get_font(FONT_SCORE)
        if font:
            font.draw(
                s, self.timer_text(), cx0 + bw * 0.57, cy0 - bh * 0.70, 0.85, align=(0.0, 0.5)
            )

        # 原价 + 删除线
        coin, crystal = self.price()
        base = self._draw_price(s, cx0, cy0, bw, bh, 0.18, 0.59, coin, crystal)
        if base:
            self._draw_strike(s, base)

        # 折扣价
        coin2, crystal2 = self.discounted()
        self._draw_price(s, cx0, cy0, bw, bh, 0.55, 0.59, coin2, crystal2)

        blit(ARROW_TEX, 0.5, 0.59, scale=0.6)

        # 枪械大图
        blit(_gun_art(self.gun), 0.27, 0.40, scale=1.3)

    def _attr_values(self):
        """三条属性当前值：power / speed / crit（GunUpgradeDef::getLevelDef(level 0)）。"""
        try:
            from game.weapons import load_upgrade_table

            tbl = load_upgrade_table()
            rec = tbl.get(self.gun) or {}
            lv = (rec.get("levels") or [{}])[0]
            return (float(lv.get("power", 0)), float(lv.get("speed", 0)), float(lv.get("crit", 0)))
        except Exception:
            return (0.0, 0.0, 0.0)

    def _draw_cells(self, s, cx0, cy0, bw, bh, which, ry):
        """PropertyCells::setProperty：12 格，格子步进 15、尺寸 14×16，scale 0.75。

        整值部分用 cell_now_l，小数部分用 cell_now_r。
        """
        vals = self._attr_values()
        v = vals[which] if which < len(vals) else 0.0
        n_lit = max(0, min(12, int(v)))
        frac = v - int(v)
        cell_l = res.load_img("pic/ui/common/cell_now_l.png")
        cell_r = res.load_img("pic/ui/common/cell_now_r.png") or cell_l
        cell_bg = res.load_img("pic/ui/common/cell_bg.png")
        sc = 0.75
        x0 = cx0 + bw * 0.59
        y0 = cy0 - bh * ry
        for j in range(12):
            if j < n_lit:
                im = cell_r if (frac > 0.1 and j == n_lit - 1) else cell_l
            else:
                im = cell_bg
            if not im:
                continue
            cw = max(1, int(im.get_width() * sc))
            ch = max(1, int(im.get_height() * sc))
            s.blit(
                pygame.transform.smoothscale(im, (cw, ch)),
                (int(x0 + j * 15.0 * sc), int(y0 - ch / 2)),
            )

    def _draw_price(self, s, cx0, cy0, bw, bh, rx, ry, coin, crystal):
        """getCoinOrCrystalNode：anchor(0,0.5)，整节点 scale 0.57。"""
        if coin <= 0 and crystal <= 0:
            return None
        if coin > 0:
            path, val, fi = COIN_TEX, coin, FONT_COIN
            ay = 0.54
        else:
            path, val, fi = CRYSTAL_TEX, crystal, FONT_CRYSTAL
            ay = 0.50
        icon = res.load_img(path)
        if not icon:
            return None
        iw_raw, ih_raw = icon.get_size()
        nw = 0
        font = gridfont.get_font(fi)
        if font:
            nw = font.text_size(str(val), 1.6)[0]

        # 节点 contentSize = (图标宽 + 数字宽*1.6, 图标高)
        node_w = iw_raw + nw
        node_h = ih_raw
        nx = cx0 + bw * rx
        ny = cy0 - bh * ry

        sc = NODE_SCALE
        iw = max(1, int(iw_raw * sc))
        ih = max(1, int(ih_raw * sc))
        # 图标 anchor(0,ay)，pos(0, h*0.5)（节点局部）
        ix = nx
        iy = (ny - node_h * 0.5 * sc) + ih_raw * sc * ay
        s.blit(pygame.transform.smoothscale(icon, (iw, ih)), (int(ix), int(iy - ih)))
        if font:
            font.draw(
                s,
                str(val),
                nx + iw_raw * 1.1 * sc,
                ny - node_h * 0.5 * sc,
                1.6 * sc,
                align=(0.0, 0.5),
            )

        return (nx, ny, node_w * sc, node_h * sc)

    def _draw_strike(self, s, base):
        """delete_line：scaleX = 节点宽*1.05/线宽，scaleY 2.0，居中在节点上。"""
        nx, ny, nw, nh = base
        line = res.load_img(DEL_LINE_TEX)
        if not line:
            return
        lw_raw = line.get_width()
        target_w = nw * 1.05
        sx = (target_w / lw_raw) if lw_raw else 1.0
        w = max(1, int(lw_raw * sx))
        h = max(1, int(line.get_height() * 2.0))
        im = pygame.transform.smoothscale(line, (w, h))
        cx = nx + nw * 0.5
        cy = ny - nh * 0.5
        s.blit(im, (int(cx - w / 2), int(cy - h / 2)))

    def _draw_buttons(self, s, cx0, cy0, bw, bh):
        buy = res.load_img(BUY_TEX)
        if buy:
            iw = max(1, int(buy.get_width() * BUY_SCALE))
            ih = max(1, int(buy.get_height() * BUY_SCALE))
            x = cx0 + bw * 0.5
            y = cy0 - bh * 0.20
            rect = pygame.Rect(int(x - iw / 2), int(y - ih / 2), iw, ih)
            s.blit(pygame.transform.smoothscale(buy, (iw, ih)), rect.topleft)
            self.buy_rect = rect

        close = res.load_img(CLOSE_TEX)
        if close:
            iw = max(1, int(close.get_width() * CLOSE_SCALE))
            ih = max(1, int(close.get_height() * CLOSE_SCALE))
            x = cx0 + bw * 0.91
            y = cy0 - bh * 0.96
            rect = pygame.Rect(int(x - iw / 2), int(y - ih / 2), iw, ih)
            s.blit(pygame.transform.smoothscale(close, (iw, ih)), rect.topleft)
            self.close_rect = rect
