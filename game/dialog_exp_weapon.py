"""过关后的「新武器体验」弹窗 —— 原版 DialogExpWeapon。

反编译依据：
  DialogExpWeapon::init              @0x15a240
  DialogExpWeapon::setGunInfo        @0x15a6d0
  DialogExpWeapon::setWeaponInfo     @0x15af48（mech 走 setMechInfo 分支）
  DialogExpWeapon::enterAnimation    @0x159f58
  DialogExpWeapon::quitAnimation     @0x159fe4
  DialogExpWeapon::onButtonBuy       @0x15a150
  DialogExpWeapon::onButtonClose     @0x159f8a
  DialogLevelPassed::showExpWeaponDialog @0x1aba88

════════════════════════════════════════════════════════════════════
结构（DialogBg = upgrade_bg.png 493×315，anchor(0.5,0.5) pos(W*0.5, H*0.52)）
════════════════════════════════════════════════════════════════════
容器 EzNode contentSize = bg 尺寸, anchor(0.5,0.5) pos(w*0.5, h*0.5)
  ├─ text_power.png   anchor(1,0.5)  pos(w*0.375,       h*0.38)
  ├─ PropertyCells    pos(w*0.395,     h*0.38)          ← power
  ├─ text_frate.png   anchor(1,0.5)  pos(w*0.375,       h*0.29)
  ├─ PropertyCells    pos(w*0.395,     h*0.29)          ← speed
  ├─ text_crit.png    anchor(1,0.5)  pos(w*0.375,       h*0.20)
  ├─ PropertyCells    pos(w*0.395,     h*0.20)          ← crit
  ├─ 枪名图           pos(w*0.5, h*0.905)
  ├─ text_dlg_weapon_like.png anchor(0,0.5) pos(w*0.25, h*0.79)
  │    └─ text_dlg_weapon.png anchor(0,0.5) pos(like.w, like.h*0.5)
  └─ gun_<name>.png   pos(w*0.35, h*0.58)  scale 1.4

  button_buy.png    anchor(0.5,0.5) scale 0.9  pos(w*0.74, h*0.57)
  button_close.png  anchor(0.5,0.5) scale 0.8  pos(w*0.91, h*0.96)

进入动画：pos y 从 h*0.6 + H 滑到 H*0.52（CCMoveTo 0.2s）
退出动画：滑到 -h（CCMoveTo 0.2s）
"""

import pygame

from engine import gridfont, res
from game.dialog import H, W, bg_dim


LOGIC = 1.0

BG_TEX = "pic/ui/shop/upgrade_bg.png"
BUY_TEX = "pic/ui/dialog/button_buy.png"
CLOSE_TEX = "pic/ui/dialog/button_close.png"
TEXT_POWER = "pic/ui/shop/text_power.png"
TEXT_FRATE = "pic/ui/shop/text_frate.png"
TEXT_CRIT = "pic/ui/shop/text_crit.png"
TEXT_LIKE = "pic/ui/dialog/text_dlg_weapon_like.png"
TEXT_WEAPON = "pic/ui/dialog/text_dlg_weapon.png"

BUY_SCALE = 0.9
CLOSE_SCALE = 0.8
GUN_SCALE = 1.4  # 1068708659
CELL_SCALE = 0.75
ANIM_TIME = 0.2

ROW_Y = (0.38, 0.29, 0.20)  # power / speed / crit 的 y 比例
LABEL_X = 0.375
CELL_X = 0.395
ROW_GAP = 0.09  # v48 = h*0.09


class ExpWeaponDialog:
    """新武器体验弹窗。done = True 表示关闭。"""

    def __init__(self, app, gun="ak47"):
        self.app = app
        self.gun = gun
        self.t = 0.0
        self.anim = 0.0
        self.closing = 0.0
        self.done = False
        self.buy_rect = None
        self.close_rect = None

    # ---------------------------------------------------------- 数据
    def gun_title(self):
        from game.shop_table import SHOP_GUNS

        for g in SHOP_GUNS:
            if g["name"] == self.gun:
                return g["title"]
        return "pic/ui/shop/%s.png" % self.gun

    def attrs(self):
        """power / speed / crit（GunUpgradeDef::getLevelDef(level 0)）。"""
        try:
            from game.weapons import load_upgrade_table

            rec = load_upgrade_table().get(self.gun) or {}
            lv = (rec.get("levels") or [{}])[0]
            return (float(lv.get("power", 0)), float(lv.get("speed", 0)), float(lv.get("crit", 0)))
        except Exception:
            return (0.0, 0.0, 0.0)

    # ---------------------------------------------------------- 交互
    def update(self, dt):
        self.t += dt
        if self.closing > 0:
            self.closing += dt
            if self.closing >= ANIM_TIME:
                self.done = True
            return
        if self.anim < 1.0:
            self.anim = min(1.0, self.anim + dt / ANIM_TIME)

    def close(self):
        if self.closing <= 0:
            self.closing = 0.0001

    def click(self, pos):
        if self.close_rect and self.close_rect.collidepoint(pos):
            self.close()
            return True
        if self.buy_rect and self.buy_rect.collidepoint(pos):
            # onButtonBuy：进商店并选中这把枪
            app = self.app
            if hasattr(app, "goto"):
                app.goto("shop")
            # ★ 只有军火库列表里有的枪才能塞给 shop_sel。奖励武器可能是
            #   fly_1 / mech_3 这类特殊武器，写进去会让 draw_shop 的
            #   SU_BY_NAME[shop_sel] 抛 KeyError（整个游戏闪退）。
            from game.shop_table import BY_NAME as _GUN_BY_NAME

            if self.gun in _GUN_BY_NAME:
                app.shop_sel = self.gun
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
        target_y = H * 0.52
        start_y = bg.get_height() * 0.6 + H
        if self.closing > 0:
            cy = target_y + (0.0 - target_y) * min(1.0, self.closing / ANIM_TIME)
        else:
            cy = start_y + (target_y - start_y) * self.anim

        left = W * 0.5 - bw / 2.0
        top = H - cy - bh / 2.0
        s.blit(bg, (int(left), int(top)))

        cx0 = left
        cy0 = top + bh
        self._draw_contents(s, cx0, cy0, bw, bh)
        self._draw_buttons(s, cx0, cy0, bw, bh)

    def _draw_contents(self, s, cx0, cy0, bw, bh):
        def blit(path, rx, ry, ax=0.5, ay=0.5, scale=1.0):
            im = res.load_img(path)
            if not im:
                return None, None
            iw = max(1, int(im.get_width() * scale))
            ih = max(1, int(im.get_height() * scale))
            x = cx0 + bw * rx
            y = cy0 - bh * ry
            s.blit(
                pygame.transform.smoothscale(im, (iw, ih)),
                (int(x - iw * ax), int(y - ih * (1.0 - ay))),
            )
            return x, y

        blit(TEXT_POWER, LABEL_X, ROW_Y[0], ax=1.0)
        blit(TEXT_FRATE, LABEL_X, ROW_Y[1], ax=1.0)
        blit(TEXT_CRIT, LABEL_X, ROW_Y[2], ax=1.0)

        for i, ry in enumerate(ROW_Y):
            self._draw_cells(s, cx0, cy0, bw, bh, i, ry)

        blit(self.gun_title(), 0.5, 0.905)

        # 「你是否喜欢这把武器？」两张拼贴，后者挂在前者右侧
        lx, ly = blit(TEXT_LIKE, 0.25, 0.79, ax=0.0, ay=0.0)
        if lx is not None:
            like = res.load_img(TEXT_LIKE)
            if like:
                wep = res.load_img(TEXT_WEAPON)
                if wep:
                    s.blit(
                        wep,
                        (
                            int(lx + like.get_width()),
                            int(ly - like.get_height() * 0.5 - wep.get_height() * 0.5),
                        ),
                    )

        # 枪械大图
        art = "pic/ui/upgrade/gun_%s.png" % self.gun
        blit(art, 0.35, 0.58, scale=GUN_SCALE)

    def _draw_cells(self, s, cx0, cy0, bw, bh, which, ry):
        vals = self.attrs()
        v = vals[which] if which < len(vals) else 0.0
        n_lit = max(0, min(12, int(v)))
        frac = v - int(v)
        cell_l = res.load_img("pic/ui/common/cell_now_l.png")
        cell_r = res.load_img("pic/ui/common/cell_now_r.png") or cell_l
        cell_bg = res.load_img("pic/ui/common/cell_bg.png")
        x0 = cx0 + bw * CELL_X
        y0 = cy0 - bh * ry
        for j in range(12):
            if j < n_lit:
                im = cell_r if (frac > 0.1 and j == n_lit - 1) else cell_l
            else:
                im = cell_bg
            if not im:
                continue
            cw = max(1, int(im.get_width() * CELL_SCALE))
            ch = max(1, int(im.get_height() * CELL_SCALE))
            s.blit(
                pygame.transform.smoothscale(im, (cw, ch)),
                (int(x0 + j * 15.0 * CELL_SCALE), int(y0 - ch / 2)),
            )

    def _draw_buttons(self, s, cx0, cy0, bw, bh):
        buy = res.load_img(BUY_TEX)
        if buy:
            iw = max(1, int(buy.get_width() * BUY_SCALE))
            ih = max(1, int(buy.get_height() * BUY_SCALE))
            x = cx0 + bw * 0.74
            y = cy0 - bh * 0.57
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
