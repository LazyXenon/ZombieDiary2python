"""士兵升级对话框 —— 原版 DialogSoldierUpgrade。

反编译照抄（sub_14D530 @0x14d530，即 DialogSoldierUpgrade::init 的实现）：

  底图  pic/ui/shop/upgrade_bg.png  (493 x 315)
        anchor(0.5,0.5) at (W * 0.52, H * 0.38)
  内部属性条容器 n255 = upgrade_bg.png 的尺寸

  三条属性标签（text_blood / text_speed / text_armor）
        anchor(1.0, 0.5)  scale 0.9
        x = n255.w * 0.28
        y = n255.h * 0.55  /  0.55 - 0.155  /  0.55 - 0.31
  三条属性格容器（PropertyCells）
        x = n255.w * 0.28 + n255.w * 0.01
        y 同上三行
  三个升级按钮 button_blank.png (139x45)  anchor(0.5,0.5) scale 0.95
        x = n255.w * 0.78
        y = n255.h * 0.54  /  0.54 - 0.155  /  0.54 - 0.31
  「lv.N」文本（fonts/captuer_it_1.fnt, scale 0.48, anchor(0,0.5)）
        x = n255.w * 0.3
        y = 按钮行 y + n255.h * 0.062
  药水消耗（enhance_potion.png + "x%d"）
        挂在按钮上：pos = (btn.w * 0.54, (btn.h + 4) * 0.63)

  关掉按钮 pic/ui/dialog/button_close.png  anchor(0.5,0.5)
        pos = (n255.w * 0.91, n255.h * 0.96)

升级消耗表来自 assets/raw/level/upgrade.xml：
  <blood_level id="0" blood="250" pval="1.0" next_potion="3" />   升血 3 瓶
  <speed_level id="0" speed="150" pval="2.0" next_potion="1" />   升速 1 瓶
  <armor_level id="0" armor="0.03" pval="1.0" next_potion="2" />  升甲 2 瓶
"""

import pygame

from engine import res
from engine.bmpfont import BitmapText
from game.dialog import DButton, Dialog, H, W, bg_dim, draw_bg, text
from game.ninecell import draw_9cell_atlas, fill_panel
from game.shop_extra import load_soldier_actors, load_soldier_upgrades


BG_TEX = "pic/ui/shop/upgrade_bg.png"
BG_TEX9 = "pic/ui/dialog/9cell_bg.png"
BLANK_TEX = "pic/ui/shop/button_blank.png"
CLOSE_TEX = "pic/ui/dialog/button_close.png"
POTION_TEX = "pic/ui/shop/enhance_potion.png"
ARROW_TEX = "pic/ui/shop/upgrade_arrow.png"
LABEL_TEX = {
    "blood": "pic/ui/shop/text_blood.png",
    "speed": "pic/ui/shop/text_speed.png",
    "armor": "pic/ui/shop/text_armor.png",
}
CELL_NOW = "pic/ui/common/cell_now.png"
CELL_NEXT = "pic/ui/common/cell_next.png"
CELL_BG = "pic/ui/common/cell_bg.png"

ROWS = (("blood", "生 命"), ("speed", "速 度"), ("armor", "装 甲"))
ROW_GAP = 0.155  # n255.h * 0.155 行距
LABEL_SCALE = 0.9

PANEL_SCALE = 1.28

# --- 版面常量（相对面板左上角，单位屏幕像素；已乘 PANEL_SCALE）---
# 底图 upgrade_bg.png 是 493×315 的圆角托盘，可见内容区约 local x 40..470、
# y 20..295。所有元素都排在这个框里，别贴着贴图的阴影边。
#   660×400 在 854×480 的画布上占了 77%×83%，三行内容被 72px 行距拉得很空，
#   像工具窗。收小到 600×336（70%×70%），行距压到 58，格子 18→16 宽、
#   间距 22→17，右边按钮同步缩到 0.62，整块内容贴合 9 宫格内框。
PANEL_W, PANEL_H = 600, 336

ROW_TOP = 110  # 第一行中线（局部 y）
ROW_STEP = 58  # 行距：三行收在 110..226
LABEL_CX = 118  # 属性标签列中心
CELL_X0 = 208  # 第一格左缘（「Lv.N」在标签与格子之间）
CELL_PITCH = 17  # 格间距（12 格 208..411，不压右侧按钮）
CELL_W = 16  # 格子尺寸（cell 原图 25×17）
CELL_H = 12
CELL_N = 12
LV_X = 196  # 「Lv.N」右缘（紧贴第一格）
BTN_CX = 482  # 升级按钮中心 x
BTN_SCALE = 0.62  # 139×45 的底按钮
ROW_BAND_X = 78  # 行底衬左缘（局部 x）
ROW_BAND_W = 446  # 行底衬宽
ICON_X = 28  # 头像左缘（面板内左下角）
ICON_SIZE = 72  # 头像显示边长


_FIT_CACHE = {}


def _fit(name):
    """按固定尺寸缩放格子贴图（带缓存，避免每帧 smoothscale）。"""
    im = res.load_img(name)
    if not im:
        return None
    key = (name, CELL_W, CELL_H)
    got = _FIT_CACHE.get(key)
    if got is None:
        got = pygame.transform.smoothscale(im, (CELL_W, CELL_H))
        _FIT_CACHE[key] = got
    return got


class SoldierUpgradeDialog(Dialog):
    """士兵升级。result: 'close'"""

    def build(self):
        # 升的是**商店里当前预览**的角色（原版 SoldierShopLayer::onUpgradeSoldier
        # 用选中下标 setSoldierInfo 后才 openDialog）；没传就退回当前装备的角色。
        self.soldier = getattr(self.app, "dialog_soldier", None) or self.app.save.soldier_name()
        self.ups = load_soldier_upgrades()
        self.lv = self.app.save.soldier_levels_of(self.soldier)

        # 底板交给 9 宫格描边现画（尺寸自由，风格和设置弹窗一致）
        self.bg = None
        self.bw = PANEL_W
        self.bh = PANEL_H
        bw, bh = self.bw, self.bh

        # 原版：所有坐标都是「底图左上角 + 比例」的局部坐标，
        # 底图 anchor(0.5,0.5) 落在 (W*0.52, H*0.38)。
        # 局部 x 从左边缘起，y 从上边缘往下。
        self.ox = 0.0
        self.oy = 0.0
        # 面板居中（放大后放 0.38H 会顶上边）
        self.bg_pos = (W * 0.50, H * 0.50)

        # 属性标签 x = bw*0.28，三行 y = bh*0.55 / -0.155 / -0.31
        self.lab_x = bw * 0.28
        self.bar_x = bw * 0.28 + bw * 0.01
        self.row_y = (bh * 0.55, bh * 0.55 - bh * ROW_GAP, bh * 0.55 - bh * 2 * ROW_GAP)
        # 升级按钮 x = bw*0.78，y = bh*0.54 / -0.155 / -0.31
        self.btn_x = bw * 0.78

        self.up_btns = {}
        for (kind, _), _y in zip(ROWS, self.row_y):
            b = self.add(
                DButton(
                    BLANK_TEX,
                    (0, 0),
                    anchor=(0.5, 0.5),
                    scale=BTN_SCALE,
                    name="up_" + kind,
                    callback=self._make_up_handler(kind),
                )
            )
            self.up_btns[kind] = b

        self.add(
            DButton(
                CLOSE_TEX, (0, 0), anchor=(0.5, 0.5), scale=0.7, name="close", callback=self._close
            )
        )

        self._layout()
        self._refresh()

    def _panel_rect(self):
        """底图在屏幕上的矩形（面板本体）。"""
        bw, bh = self.bw, self.bh
        return pygame.Rect(int(W * 0.50 - bw / 2), int(H * 0.50 - bh / 2), bw, bh)

    def _layout(self):
        """三个升级按钮 + 关闭按钮的屏幕位置。

        ★ DButton.pos 是 **cocos 坐标（y 从屏幕底部往上量）**，
          而这里的 pr.y / ROW_TOP 都是屏幕坐标（从上往下）⇒ 必须换算成
          `H - 屏幕y`，否则按钮会跑到屏幕上半部分去（这一段早先写
          `H - (pr.y + ...)` 是对的，后来改成屏幕坐标时漏了换算，
          结果三颗按钮飘在面板上方、和属性行完全错开）。
        """
        pr = self._panel_rect()
        self.pr = pr
        for (kind, _), i in zip(ROWS, range(3)):
            btn = self.up_btns[kind]
            cy = pr.y + ROW_TOP + i * ROW_STEP
            btn.pos = (pr.x + BTN_CX, H - cy)
            btn._compute_rect()
        cl = self.buttons[-1]
        cl.pos = (pr.right - 30, H - (pr.y + 30))
        cl._compute_rect()

    def _row_screen_y(self, i):
        return self.pr.y + ROW_TOP + i * ROW_STEP

    def _sx(self, lx):
        """局部 x → 屏幕 x"""
        return int(self.pr.x + lx)

    def _sy(self, ly):
        """局部 y → 屏幕 y（从面板顶往下量）"""
        return int(self.pr.y + ly)

    # ---- 升级逻辑 ----
    def _potion_cost(self, kind):
        table = self.ups.get(self.soldier, {}).get(kind, [])
        cur = int(self.lv.get(kind, 0))
        if cur >= len(table):
            return 0
        return int(table[cur].get("potion", 0))

    def _make_up_handler(self, kind):
        def handler(btn):
            self._upgrade(kind)

        return handler

    def _upgrade(self, kind):
        cost = self._potion_cost(kind)
        if cost <= 0:
            return
        if not self.app.save.spend_potions(cost):
            self.app.open_potion_shop()  # 原版：药水不够 → 药水商店
            return
        self.app.save.upgrade_soldier(kind, self.soldier)
        self.lv = self.app.save.soldier_levels_of(self.soldier)
        self._refresh()
        self.app.audio.sfx("unlock")

    def _close(self, btn):
        self.result = "close"
        self.done = True

    def _refresh(self):
        for kind, b in self.up_btns.items():
            b.enabled = self._potion_cost(kind) > 0

    # ---- 渲染 ----
    def draw(self, s):
        # ★ 面板必须**不透底色**：早先是 (40,30,58,208)，底下的军火库卡片
        #   从弹窗里透上来，枪名/价格和弹窗自己的属性行叠成一片
        bg_dim(s, 195)
        pr = self.pr
        # 设置弹窗同款底板：深紫 + 银白描边 + 四角蓝块
        fill_panel(s, BG_TEX9, pr, (40, 30, 58, 255), 1.0)
        draw_9cell_atlas(s, BG_TEX9, pr, 1.0)

        title = ""
        for a in load_soldier_actors():
            if a["name"] == self.soldier:
                title = a["title"]
                break
        f_t = pygame.font.SysFont("Microsoft YaHei", 21, bold=True)
        t_main = f_t.render("角色升级", True, (255, 244, 214))
        t_sh = f_t.render("角色升级", True, (36, 20, 52))
        tx = pr.centerx - t_main.get_width() // 2
        ty = pr.y + 14
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1), (-1, -1)):
            s.blit(t_sh, (tx + dx, ty + dy))
        s.blit(t_main, (tx, ty))

        if title:
            f2 = pygame.font.SysFont("Microsoft YaHei", 15, bold=True)
            nm = f2.render(title.title(), True, (250, 214, 128))
            s.blit(nm, (pr.centerx - nm.get_width() // 2, ty + 27))

        # 标题与属性行之间一道极淡的分隔线：把「标题区」和「内容区」分开，
        # 三行内容不再像悬在半空（纯装饰，不加任何底色块）。
        sep_y = pr.y + 74
        sep = pygame.Surface((ROW_BAND_W, 1), pygame.SRCALPHA)
        sep.fill((255, 236, 200, 40))
        s.blit(sep, (pr.x + ROW_BAND_X, sep_y))

        # 药水余量：左上（贴着第一行上方，避开标题与分隔线）
        pot_n = int(self.app.save.d.get("en_potion_count", 0) or 0)
        pot = res.load_img(POTION_TEX)
        if pot:
            pw = int(pot.get_width() * 0.40)
            ph = int(pot.get_height() * 0.40)
            f3 = pygame.font.SysFont("Microsoft YaHei", 17, bold=True)
            t3 = f3.render("×%d" % pot_n, True, (255, 236, 170))
            px = pr.x + 96
            py = pr.y + 13
            # 药水余量做成左上角一枚小徽章：深底圆角托住图标+数量，
            # 否则图标直接压在九宫格银边上，看着像漏出来的。
            chip = pygame.Surface((pw + 10 + t3.get_width(), ph + 10), pygame.SRCALPHA)
            pygame.draw.rect(chip, (26, 18, 46, 190), chip.get_rect(), border_radius=9)
            pygame.draw.rect(chip, (255, 255, 255, 26), chip.get_rect(), 1, border_radius=9)
            s.blit(chip, (px - 5, py - 5))
            s.blit(pygame.transform.smoothscale(pot, (pw, ph)), (px, py))
            s.blit(t3, (px + pw + 5, py + ph // 2 - t3.get_height() // 2))

        self._draw_rows(s)
        for b in self.buttons:
            b.draw(s, self._is_pressed(b))
        self._draw_costs(s)

    def _draw_rows(self, s):
        cell_now = _fit(CELL_NOW)
        cell_next = _fit(CELL_NEXT)
        cell_bg = _fit(CELL_BG)
        pr = self.pr
        f_lv = pygame.font.SysFont("Consolas", 17, bold=True)
        for i, (kind, _cn) in enumerate(ROWS):
            cy = self._row_screen_y(i)

            # 行底衬：一条极淡的圆角横带，把「标签 + 格子 + 按钮」绑成一行，
            # 三行不再浮在紫色底上（只叠 8/255 的白，不加边框不加黑底）。
            band = pygame.Surface((ROW_BAND_W, 34), pygame.SRCALPHA)
            pygame.draw.rect(band, (255, 255, 255, 9), band.get_rect(), border_radius=17)
            s.blit(band, (pr.x + ROW_BAND_X, cy - 17))

            # 属性标签：格子左侧居中
            lab = res.load_img(LABEL_TEX[kind])
            if lab:
                im = pygame.transform.smoothscale(
                    lab, (int(lab.get_width() * 0.92), int(lab.get_height() * 0.92))
                )
                s.blit(im, (pr.x + LABEL_CX - im.get_width() // 2, cy - im.get_height() // 2))

            # 12 格属性：格数 = pval（和商店页同一把尺子）
            table = self.ups.get(self.soldier, {}).get(kind, [])
            cur = int(self.lv.get(kind, 0))
            cur_p = nxt_p = 0.0
            if table:
                cur_p = float(table[min(cur, len(table) - 1)].get("pval", 0) or 0)
                if cur + 1 < len(table):
                    nxt_p = float(table[cur + 1].get("pval", 0) or 0)
            n_lit = max(0, min(CELL_N, int(cur_p)))
            n_next = max(0, min(CELL_N, int(nxt_p)) - n_lit)
            for k in range(CELL_N):
                gx = pr.x + CELL_X0 + k * CELL_PITCH
                if k < n_lit:
                    im = cell_now
                elif k < n_lit + n_next:
                    im = cell_next
                else:
                    im = cell_bg
                if im:
                    s.blit(im, (gx, cy - im.get_height() // 2))

            # Lv.N：原版写在标签和格子**之间**（upgrade_dlg.png 参考帧），
            # 不是塞在标签下面 —— 塞下面会和下一行的标签挤在一起。
            lvtxt = "MAX" if cur >= len(table) else "Lv.%d" % cur
            lt = f_lv.render(lvtxt, True, (24, 14, 36))
            lt2 = f_lv.render(lvtxt, True, (255, 250, 220))
            lx = pr.x + LV_X - lt2.get_width()
            ly = cy - lt2.get_height() // 2
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1)):
                s.blit(lt, (lx + dx, ly + dy))
            s.blit(lt2, (lx, ly))

    def _draw_costs(self, s):
        """药水消耗叠在按钮**之上**（先画按钮再画它，否则被盖住）。

        现在只在按钮画完之后画这一次。
        """
        pot = res.load_img(POTION_TEX)
        f_ct = pygame.font.SysFont("Microsoft YaHei", 19, bold=True)
        for kind, _cn in ROWS:
            cost = self._potion_cost(kind)
            btn = self.up_btns[kind]
            if cost > 0:
                ct = f_ct.render("×%d" % cost, True, (255, 255, 255))
                if pot:
                    pw = int(pot.get_width() * 0.46)
                    ph = int(pot.get_height() * 0.46)
                else:
                    pw = ph = 0
                total = pw + (6 if pw else 0) + ct.get_width()
                nx = btn.rect.centerx - total // 2
                if pot:
                    s.blit(
                        pygame.transform.smoothscale(pot, (pw, ph)),
                        (nx, btn.rect.centery - ph // 2),
                    )
                s.blit(ct, (nx + pw + (6 if pw else 0), btn.rect.centery - ct.get_height() // 2))
            else:
                f4 = pygame.font.SysFont("Microsoft YaHei", 17, bold=True)
                mx = f4.render("已满级", True, (255, 220, 140))
                s.blit(
                    mx,
                    (
                        btn.rect.centerx - mx.get_width() // 2,
                        btn.rect.centery - mx.get_height() // 2,
                    ),
                )
