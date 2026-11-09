"""金手指 —— 复刻新增的调试面板。

原版顶栏钻石旁的「+」是充值入口（渠道 SDK）。服务器早已下线，这里改成
一个本地金手指：直接输入金币 / 钻石数量，输多少得多少，点「确认」入账。

输入方式：数字键 0-9（含小键盘）、Backspace 删除、Tab 切换金币/钻石、
Enter 确认、Esc 关闭。也支持鼠标点输入框。
"""

import pygame

from engine import res
from game.dialog import Dialog, H, W, bg_dim
from game.ninecell import draw_9cell_atlas, fill_panel, frame_inner


BG_TEX = "pic/ui/dialog/9cell_bg.png"
BG_RECT = (167, 66, 520, 348)
MAX_DIGITS = 9  # 单次最多输入 9 位数（≈ 10 亿）

# 快捷补给：点一下就入账，不用记键盘操作
QUICK = (
    ("coin", 10000, "金币 +1万", (255, 214, 90)),
    ("coin", 100000, "金币 +10万", (255, 214, 90)),
    ("crystal", 1000, "钻石 +1000", (130, 215, 255)),
    ("crystal", 10000, "钻石 +1万", (130, 215, 255)),
)


class CheatDialog(Dialog):
    """金手指面板。result: 'close'"""

    CLOSE_CUSTOM = True  # 顶部已有自绘 X，不再叠加公共叉号

    def __init__(self, app):
        self.coin_text = ""
        self.crystal_text = ""
        self.focus = "coin"  # coin / crystal
        self._msg = ""
        self._msg_t = 0.0
        Dialog.__init__(self, app)

    def build(self):
        pass

    # ------------------------------------------------------------ 输入
    def on_key(self, key):
        if key == pygame.K_ESCAPE:
            self.done = "close"
            return
        if key == pygame.K_TAB:
            self.focus = "crystal" if self.focus == "coin" else "coin"
            return
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._apply()
            return
        if key in (pygame.K_BACKSPACE, pygame.K_DELETE):
            if self.focus == "coin":
                self.coin_text = self.coin_text[:-1]
            else:
                self.crystal_text = self.crystal_text[:-1]
            return
        digit = self._digit_of(key)
        if digit is not None:
            if self.focus == "coin":
                if len(self.coin_text) < MAX_DIGITS:
                    self.coin_text += digit
            else:
                if len(self.crystal_text) < MAX_DIGITS:
                    self.crystal_text += digit

    @staticmethod
    def _digit_of(key):
        if pygame.K_0 <= key <= pygame.K_9:
            return chr(ord("0") + key - pygame.K_0)
        if pygame.K_KP0 <= key <= pygame.K_KP9:
            return chr(ord("0") + key - pygame.K_KP0)
        return None

    # ------------------------------------------------------------ 执行
    def _apply(self):
        coin = int(self.coin_text or 0)
        crystal = int(self.crystal_text or 0)
        if coin <= 0 and crystal <= 0:
            self._msg = "先输入数量"
            self._msg_t = 1.5
            return
        save = getattr(self.app, "save", None)
        if save is None:
            return
        if coin > 0:
            save.add_coins(coin)
        if crystal > 0:
            save.add_crystals(crystal)
        save.save()
        self._msg = "已获得 %s 金币 / %s 钻石" % (f"{coin:,}", f"{crystal:,}")
        self._msg_t = 2.0
        self.coin_text = ""
        self.crystal_text = ""

    def _grant(self, kind, amount):
        """快捷补给：直接入账一笔。"""
        save = getattr(self.app, "save", None)
        if save is None:
            return
        if kind == "coin":
            save.add_coins(amount)
            self._msg = "已获得 %s 金币" % f"{amount:,}"
        else:
            save.add_crystals(amount)
            self._msg = "已获得 %s 钻石" % f"{amount:,}"
        save.save()
        self._msg_t = 1.6
        self.app.audio.ui_click()

    # ------------------------------------------------------------ 更新
    def update(self, dt):
        super().update(dt)
        if self._msg_t > 0:
            self._msg_t -= dt

    # ------------------------------------------------------------ 命中
    def click(self, pos):
        if self.closing():
            return False
        cr = self._field_rect("coin")
        kr = self._field_rect("crystal")
        if cr.collidepoint(pos):
            self.focus = "coin"
            return True
        if kr.collidepoint(pos):
            self.focus = "crystal"
            return True
        for i, (_kind, amount, _lab, _c) in enumerate(QUICK):
            if self._quick_rect(i).collidepoint(pos):
                self._grant(_kind, amount)
                return True
        br = self._ok_rect()
        if br.collidepoint(pos):
            self._apply()
            return True
        xr = self._close_rect()
        if xr.collidepoint(pos):
            self.done = "close"
            return True
        return True  # 模态：点面板外也别穿透到地图

    # ------------------------------------------------------------ 几何
    # ★ 所有控件一律由**九宫格真实内框**推算，不再用 BG_RECT + 魔法常量。
    #   9cell_bg 的描边不是满格的（左 26px / 上 34px / 右 13px / 下 21px 才有
    #   「金币 +1万」正好压在白色描边上、「确认入账」又掉出下边框 ——
    #   用户反复说「贴图必须在框框里面」。
    @staticmethod
    def _panel():
        return pygame.Rect(*BG_RECT)

    @classmethod
    def _inner(cls):
        # ★ 用 frame_inner（白描边内侧）而不是 inner_panel（alpha 边界）：
        #   9cell_bg 底边白线下面还有 27px 黑影，按 alpha 算出来的内框会一路
        #   顶到黑影里，「确认入账」就压在下边框上了。
        return frame_inner(BG_TEX, cls._panel())

    def _field_rect(self, which):
        r = self._inner()
        h = 44
        y = r.y + 64 + (0 if which == "coin" else h + 9)
        return pygame.Rect(r.x + 12, y, r.w - 24, h)

    def _quick_rect(self, i):
        r = self._inner()
        gap = 8
        w = (r.w - 24 - gap * 3) // 4
        y = r.y + 64 + 44 * 2 + 9 + 12
        return pygame.Rect(r.x + 12 + i * (w + gap), y, w, 32)

    def _ok_rect(self):
        r = self._inner()
        return pygame.Rect(r.centerx - 70, r.bottom - 56, 140, 44)

    def _close_rect(self):
        # 和其他弹窗统一用原版 button_close.png，收在描边里面
        r = self._inner()
        return pygame.Rect(r.right - 52, r.y + 2, 50, 32)

    # ------------------------------------------------------------ 绘制
    def draw(self, s):
        bg_dim(s, 170)
        rect = self._panel()
        # 底色只铺在**描边以内**（fill_panel），否则紫色会从框线外面漏出来
        fill_panel(s, BG_TEX, rect, (38, 30, 58, 255), 1.0)
        draw_9cell_atlas(s, BG_TEX, rect, 1.0)

        ft = pygame.font.SysFont("Microsoft YaHei", 26, bold=True)
        fs = pygame.font.SysFont("Microsoft YaHei", 19, bold=True)
        fv = pygame.font.SysFont("Consolas", 24, bold=True)

        inner = self._inner()
        # 标题
        t = ft.render("金 手 指", True, (255, 236, 170))
        s.blit(t, (rect.centerx - t.get_width() // 2, inner.y + 6))
        sub = pygame.font.SysFont("Microsoft YaHei", 13, bold=True).render(
            "输入多少得多少 · Tab 切换 · Enter 确认 · Esc 关闭", True, (186, 170, 206)
        )
        s.blit(sub, (rect.centerx - sub.get_width() // 2, inner.y + 42))

        # 两个输入行
        coin_icon = res.load_img("pic/ui/common/coin.png")
        crystal_icon = res.load_img("pic/ui/common/crystal.png")
        rows = (
            ("coin", "金币", "coin.png", coin_icon, self.coin_text, (255, 214, 90)),
            ("crystal", "钻石", "crystal.png", crystal_icon, self.crystal_text, (130, 215, 255)),
        )
        for which, label, _t, icon, text, color in rows:
            r = self._field_rect(which)
            active = self.focus == which
            plate = pygame.Surface(r.size, pygame.SRCALPHA)
            plate.fill((22, 18, 34, 255))
            s.blit(plate, r.topleft)
            pygame.draw.rect(s, (255, 236, 170) if active else (90, 78, 120), r, 3 if active else 1)
            if icon:
                iw = 26 if which == "coin" else 30
                ih = 26 if which == "coin" else 22
                s.blit(
                    pygame.transform.smoothscale(icon, (iw, ih)), (r.x + 12, r.centery - ih // 2)
                )
            lab = fs.render(label, True, color)
            s.blit(lab, (r.right - lab.get_width() - 14, r.centery - lab.get_height() // 2))
            shown = text if text else "0"
            vt = fv.render(
                shown + ("_" if active and (self.app.t * 2) % 2 < 1 else ""),
                True,
                color if text else (110, 100, 130),
            )
            s.blit(vt, (r.x + 52, r.centery - vt.get_height() // 2))

        # 快捷补给
        fq = pygame.font.SysFont("Microsoft YaHei", 15, bold=True)
        for i, (_kind, _amount, lab, color) in enumerate(QUICK):
            r = self._quick_rect(i)
            chip = pygame.Surface(r.size, pygame.SRCALPHA)
            chip.fill((48, 40, 66, 255))
            s.blit(chip, r.topleft)
            pygame.draw.rect(s, tuple(min(255, c // 2 + 60) for c in color), r, 1)
            t = fq.render(lab, True, color)
            s.blit(t, (r.centerx - t.get_width() // 2, r.centery - t.get_height() // 2))

        # 确认按钮
        br = self._ok_rect()
        ok_plate = pygame.Surface(br.size, pygame.SRCALPHA)
        ok_plate.fill((150, 96, 40, 255))
        s.blit(ok_plate, br.topleft)
        pygame.draw.rect(s, (255, 236, 170), br, 2)
        ot = fs.render("确认入账", True, (255, 255, 255))
        s.blit(ot, (br.centerx - ot.get_width() // 2, br.centery - ot.get_height() // 2))

        # 关闭
        xr = self._close_rect()
        ctex = res.load_img("pic/ui/dialog/button_close.png")
        if ctex:
            s.blit(pygame.transform.smoothscale(ctex, xr.size), xr.topleft)
        else:
            ct = ft.render("×", True, (255, 150, 150))
            s.blit(ct, (xr.centerx - ct.get_width() // 2, xr.centery - ct.get_height() // 2))

        # 提示
        if self._msg and self._msg_t > 0:
            a = min(1.0, self._msg_t / 0.4)
            # 文本渲染有缓存，改 alpha 前 copy 一份，别污染缓存里那张
            mt = (
                pygame.font.SysFont("Microsoft YaHei", 16, bold=True)
                .render(self._msg, True, (150, 255, 170))
                .copy()
            )
            mt.set_alpha(int(255 * a))
            s.blit(
                mt, (rect.centerx - mt.get_width() // 2, self._ok_rect().y - mt.get_height() - 4)
            )
