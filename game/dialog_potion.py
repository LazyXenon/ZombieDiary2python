"""药水商店 —— 原版 DialogPotion。

反编译照抄（DialogPotion::initButton @0x14f5c8）：
  按钮上挂 enhance_potion.png 图标
      图标 anchor(0,0.65) scale 0.9
      数量文本 "x%d"  anchor(0,0.65)
  价格图标 crystal.png  anchor(0,0.54)
      价格文本 "%d"    anchor(0,0.5) scale 0.8

价格表（dword_48F73C，DialogSettings 静态初始化 @0x150xxxx）：
    dword_48F73C[0] = 1;   dword_48F73C[1] = 5;     档0: 1 瓶 / 5 钻石
    dword_48F73C[2] = 10;  dword_48F73C[3] = 45;    档1: 10 瓶 / 45 钻石

购买后 en_potion_count += 数量（DialogPotion::onButtonPotion @0x14fda8）。

★ 原版底图 pic/ui/dialog/potion_bg.png 没导出到 assets（和 setting_bg 一样），
  浮在战斗画面上，看不出这是商店。改用 9cell_bg 九宫格当底 + 自绘标题。
"""

import pygame

from engine import res
from game.dialog import DButton, Dialog, H, W, bg_dim
from game.ninecell import inner_panel


BG9 = "pic/ui/dialog/9cell_bg.png"
PLATE_TEX = "pic/ui/shop/button_blank.png"
POTION_TEX = "pic/ui/shop/enhance_potion.png"
CRYSTAL_TEX = "pic/ui/common/crystal.png"
CANCEL_TEX = "pic/ui/dialog/button_close.png"

# 原版 dword_48F73C：(数量, 价格) 两档
POTION_TIERS = ((1, 5), (10, 45))

PANEL_SCALE = 2.0  # 9cell_bg 244×183 → 488×366
PANEL_W, PANEL_H = 488, 366
ROW_W, ROW_H = 250, 81  # 每档的橙色底板（139×45 ×1.8）
ROW_DY = 96
ROW_Y0 = 150  # 相对面板顶


class PotionDialog(Dialog):
    """药水商店。result: 'close'"""

    def build(self):
        self.tiers = POTION_TIERS
        top = H / 2.0 - PANEL_H / 2.0
        for i, (_num, _price) in enumerate(self.tiers):
            self.add(
                DButton(
                    PLATE_TEX,
                    (W * 0.5, H - (top + ROW_Y0 + i * ROW_DY)),
                    anchor=(0.5, 0.5),
                    scale=1.8,
                    name="tier%d" % i,
                    callback=self._make_buy(i),
                )
            )
        self.add(
            DButton(
                CANCEL_TEX,
                (W * 0.5 + PANEL_W / 2.0 - 56, H - (top + 64)),
                anchor=(0.5, 0.5),
                scale=0.8,
                name="close",
                callback=self._close,
            )
        )

    def _make_buy(self, i):
        def handler(btn):
            num, price = self.tiers[i]
            if not self.app.save.spend_crystals(price):
                self.app.toast("钻石不足")
                return
            self.app.save.add_potions(num)
            self.app.toast("药水 +%d" % num)
            self.app.audio.buy()

        return handler

    def _close(self, btn):
        self.result = "close"
        self.done = True

    def on_key(self, key):
        if key == pygame.K_ESCAPE:
            self.result = "close"
            self.done = True

    def _row_rects(self):
        top = H / 2.0 - PANEL_H / 2.0
        out = []
        for i in range(len(self.tiers)):
            r = pygame.Rect(0, 0, ROW_W, ROW_H)
            r.center = (int(W * 0.5), int(top + ROW_Y0 + i * ROW_DY))
            out.append(r)
        return out

    def draw(self, s):
        bg_dim(s, 180)
        pr = pygame.Rect(0, 0, PANEL_W, PANEL_H)
        pr.center = (int(W * 0.5), int(H * 0.5))
        inner_panel_rect = inner_panel(BG9, pr, PANEL_SCALE)
        layer = pygame.Surface(inner_panel_rect.size, pygame.SRCALPHA)
        layer.fill((46, 34, 66, 255))
        s.blit(layer, inner_panel_rect.topleft)
        bg = res.load_img(BG9)
        if bg:
            s.blit(pygame.transform.smoothscale(bg, (PANEL_W, PANEL_H)), pr.topleft)
        # 标题
        ft = pygame.font.SysFont("Microsoft YaHei", 22, bold=True)
        t = ft.render("药水商店", True, (255, 236, 170))
        sh = ft.render("药水商店", True, (60, 30, 10))
        s.blit(sh, (pr.centerx - t.get_width() // 2 + 1, pr.y + 65))
        s.blit(t, (pr.centerx - t.get_width() // 2, pr.y + 64))
        # 钻石余额
        cr = int(self.app.save.d.get("crystal", 0) or 0)
        cim = res.load_img(CRYSTAL_TEX)
        f2 = pygame.font.SysFont("Arial", 18, bold=True)
        bt = f2.render(str(cr), True, (150, 225, 255))
        if cim:
            ic = pygame.transform.smoothscale(cim, (22, 17))
            bx = pr.centerx - (22 + 6 + bt.get_width()) // 2
            s.blit(ic, (bx, pr.y + 97))
            s.blit(bt, (bx + 28, pr.y + 96))
        else:
            s.blit(bt, (pr.centerx - bt.get_width() // 2, pr.y + 96))

        pot = res.load_img(POTION_TEX)
        f = pygame.font.SysFont("Arial", 22, bold=True)
        for i, (num, price) in enumerate(self.tiers):
            r = self._row_rects()[i]
            plate = res.load_img(PLATE_TEX)
            if plate:
                s.blit(pygame.transform.smoothscale(plate, (r.w, r.h)), r.topleft)
            if pot:
                im = pygame.transform.smoothscale(pot, (46, 50))
                s.blit(im, (r.x + 16, r.centery - 25))
            t = f.render("×%d" % num, True, (255, 255, 255))
            s.blit(t, (r.x + 68, r.centery - t.get_height() // 2))
            if cim:
                ic = pygame.transform.smoothscale(cim, (26, 20))
                px = r.right - 16 - ic.get_width() - 6 - 44
                s.blit(ic, (px, r.centery - ic.get_height() // 2))
                t = f.render(str(price), True, (150, 225, 255))
                s.blit(t, (px + ic.get_width() + 6, r.centery - t.get_height() // 2))

        # 两档底板已按 250×81 手绘，这里只补画关闭键
        for b in self.buttons:
            if str(b.name).startswith("tier"):
                continue
            b.draw(s, self._is_pressed(b))
