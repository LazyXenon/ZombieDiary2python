"""游戏介绍与全键盘操作指南。

左侧保留原版滑入动画，但玩法文字改为本地排版，不显示旧贴图中的
公司、电话和邮箱；右侧是桌面版键位速查。快捷键由 app.input 统一分发。
"""

import math

import pygame

from engine import res
from game.dialog import H, W, bg_dim
from game.save import key_display_name


INTRO_TEX = "pic/ui/mainmenu/text_game_intro.png"
CLOSE_TEX = "pic/ui/mainmenu/button_close.png"

INTRO_X_RATIO = 0.05
CLOSE_SCALE = 1.1
CLOSE_X_RATIO = 0.77
CLOSE_Y_RATIO = 0.02
SLIDE_TIME = 0.5

GUIDE_RECT = pygame.Rect(438, 20, 396, 440)


def draw_keycap(s, rect, text, size=18):
    """灰黑金属立体键帽，带拉丝纹理、倒角与循环扫光。"""
    r = pygame.Rect(rect)
    if r.w < 12 or r.h < 10:
        return
    depth = max(2, min(5, r.h // 8))
    body = pygame.Rect(r.x, r.y, r.w, r.h - depth)

    pygame.draw.rect(s, (4, 6, 10), r.move(2, 2), border_radius=7)
    pygame.draw.rect(s, (11, 14, 20), r, border_radius=7)
    pygame.draw.rect(
        s, (31, 36, 45), (r.x + 2, body.bottom - 1, r.w - 4, depth + 2), border_radius=3
    )

    face = pygame.Surface(body.size, pygame.SRCALPHA)
    for y in range(body.h):
        t = y / max(1, body.h - 1)
        pygame.draw.line(
            face, (int(80 - 52 * t), int(87 - 57 * t), int(101 - 66 * t), 255), (0, y), (body.w, y)
        )
    for x in range(-body.h, body.w + body.h, 6):
        pygame.draw.line(face, (255, 255, 255, 7), (x, 0), (x + body.h, body.h), 1)
    pygame.draw.rect(
        face, (188, 205, 225, 38), (2, 1, body.w - 4, max(3, body.h // 2 - 1)), border_radius=5
    )

    now = pygame.time.get_ticks() / 1000.0
    phase = (now * 0.62 + r.x * 0.011 + r.y * 0.017) % 1.0
    gx = int(-body.w * 0.45 + phase * body.w * 2.1)
    gw = max(5, body.w // 7)
    shine = pygame.Surface(body.size, pygame.SRCALPHA)
    pygame.draw.polygon(
        shine,
        (235, 248, 255, 42),
        [(gx, 0), (gx + gw, 0), (gx + gw - body.h // 3, body.h), (gx - body.h // 3, body.h)],
    )
    pygame.draw.line(
        shine, (255, 255, 255, 105), (gx + gw // 2, 0), (gx + gw // 2 - body.h // 3, body.h), 1
    )
    mask = pygame.Surface(body.size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=7)
    shine.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    face.blit(shine, (0, 0))

    pygame.draw.rect(face, (150, 166, 187, 145), face.get_rect(), width=2, border_radius=7)
    pygame.draw.line(face, (225, 238, 255, 125), (6, 3), (body.w - 7, 3), 2)
    pygame.draw.line(face, (5, 7, 12, 205), (5, body.h - 3), (body.w - 6, body.h - 3), 2)
    sparkle = (math.sin(now * 3.4 + r.x * 0.09 + r.y * 0.05) + 1.0) * 0.5
    if sparkle > 0.86:
        a = int(210 * (sparkle - 0.86) / 0.14)
        sx, sy = body.right - 5, body.y + 4
        pygame.draw.line(face, (245, 252, 255, a), (sx - 3, sy), (sx + 3, sy), 1)
        pygame.draw.line(face, (245, 252, 255, a), (sx, sy - 3), (sx, sy + 3), 1)
    s.blit(face, body.topleft)

    fs = size
    while fs > 8:
        font = pygame.font.SysFont("Microsoft YaHei", fs, bold=True)
        ink = font.render(text, True, (226, 235, 247))
        if ink.get_width() <= body.w - 7:
            break
        fs -= 1
    glow = font.render(text, True, (8, 11, 17))
    tx = body.centerx - ink.get_width() // 2
    ty = body.centery - ink.get_height() // 2
    s.blit(glow, (tx + 1, ty + 1))
    s.blit(ink, (tx, ty))


def _guide_text(s, text, pos, size=16, color=(244, 232, 203)):
    font = pygame.font.SysFont("Microsoft YaHei", size, bold=True)
    shadow = font.render(text, True, (20, 13, 10))
    image = font.render(text, True, color)
    s.blit(shadow, (pos[0] + 1, pos[1] + 2))
    s.blit(image, pos)


class GameIntroduceDialog:
    """首次进游戏弹一次键盘教程；任意键或关闭按钮均可收起。"""

    any_key_close = True

    def __init__(self, app):
        self.app = app
        self.t = 0.0
        self.done = False
        self.close_rect = None
        self._im = res.load_img(INTRO_TEX)
        self._close = res.load_img(CLOSE_TEX)

    def update(self, dt):
        self.t += dt

    def _intro_target(self):
        if not self._im:
            return None
        w, h = self._im.get_size()
        return pygame.Rect(int(round(W * INTRO_X_RATIO)), int(round(H * 0.5 - h * 0.5)), w, h)

    def _intro_rect(self):
        tgt = self._intro_target()
        if not tgt:
            return None
        if self.t >= SLIDE_TIME:
            return tgt
        k = self.t / SLIDE_TIME
        eased = 1.0 - math.exp(-5.0 * k) * math.cos(7.5 * k)
        x = -tgt.w + (tgt.x + tgt.w) * eased
        return pygame.Rect(int(round(x)), tgt.y, tgt.w, tgt.h)

    def _close_rect(self, intro):
        if not self._close or not intro:
            return None
        pw, ph = self._close.get_size()
        w = max(1, int(round(pw * CLOSE_SCALE)))
        h = max(1, int(round(ph * CLOSE_SCALE)))
        cx = intro.x + intro.w * CLOSE_X_RATIO
        # 整个按钮收进介绍面板，底边留 10px，不再压住外框。
        return pygame.Rect(int(round(cx - w / 2)), intro.bottom - h - 10, w, h)

    def click(self, pos):
        if self.close_rect and self.close_rect.collidepoint(pos):
            self.done = True
            self.app.audio.ui_click()
            return True
        return False

    def key(self, _key):
        """任意键关闭首次引导，输入层会吞掉该按键避免穿透。"""
        self.done = True
        self.app.audio.ui_click()
        return True

    def key_items(self):
        return [(self.close_rect, "关闭")] if self.close_rect else []

    @staticmethod
    def _row(s, y, keys, title, subtitle, label_x):
        x = 454
        for text, width in keys:
            draw_keycap(s, pygame.Rect(x, y, width, 34), text, size=15 if len(text) > 2 else 18)
            x += width + 7
        _guide_text(s, title, (label_x, y - 1), 16, (255, 222, 137))
        _guide_text(s, subtitle, (label_x, y + 20), 12, (194, 187, 177))

    def _draw_guide(self, s):
        r = GUIDE_RECT
        pygame.draw.rect(s, (10, 9, 15), r.move(5, 7), border_radius=16)
        pygame.draw.rect(s, (40, 32, 35), r, border_radius=15)
        inner = r.inflate(-12, -12)
        pygame.draw.rect(s, (28, 29, 38), inner, border_radius=11)
        pygame.draw.rect(s, (190, 139, 59), r, width=2, border_radius=15)
        pygame.draw.line(s, (255, 220, 132), (r.x + 18, r.y + 3), (r.right - 18, r.y + 3), 2)

        title = pygame.font.SysFont("Microsoft YaHei", 25, bold=True).render(
            "键盘操作指南", True, (255, 225, 147)
        )
        s.blit(title, (r.centerx - title.get_width() // 2, 34))
        _guide_text(s, "无需触屏，也能完成全部操作", (493, 68), 13, (184, 180, 180))

        self._row(
            s, 91, [("↑", 32), ("↓", 32), ("←", 32), ("→", 32)], "功能导航", "上下左右选择", 620
        )
        self._row(s, 135, [("Enter", 72), ("Esc", 54)], "确认 / 返回", "也可点击按钮", 620)
        kb = self.app.keybinds()

        def key_name(field):
            return key_display_name(pygame.key.name(kb[field]))

        cycle = "Shift" if kb["cycle"] in (pygame.K_LSHIFT, pygame.K_RSHIFT) else key_name("cycle")
        self._row(
            s,
            179,
            [(key_name("left"), 34), (key_name("right"), 34), (key_name("fire"), 82)],
            "移动 / 攻击",
            "左右移动，攻击键开火",
            646,
        )
        self._row(
            s,
            223,
            [(key_name("weapon_%d" % i), 32) for i in range(1, 5)],
            "切换武器",
            "对应四个武器槽",
            620,
        )
        self._row(s, 267, [(cycle, 76)], "顺序换枪", "循环切换下一把武器", 550)
        self._row(
            s,
            311,
            [(key_name("ability_%d" % i), 34) for i in range(1, 4)],
            "使用道具",
            "依次使用三个道具",
            580,
        )
        self._row(s, 355, [(key_name("armor"), 38)], "装备护甲", "使用已装备的护盾道具", 512)

        pygame.draw.line(s, (92, 75, 49), (458, 398), (814, 398), 1)
        prompt = "按任意键关闭弹窗"
        pf = pygame.font.SysFont("Microsoft YaHei", 15, bold=True)
        prompt_x = r.centerx - pf.size(prompt)[0] // 2
        _guide_text(s, prompt, (prompt_x, 404), 15, (255, 225, 147))
        _guide_text(s, "默认隐藏触屏移动与攻击按钮", (478, 426), 12, (164, 207, 156))
        _guide_text(s, "设置 → 键位设置，可改键或重新显示", (464, 444), 11, (183, 177, 169))

    def _draw_intro(self, s, r):
        pygame.draw.rect(s, (10, 9, 15), r.move(5, 7), border_radius=18)
        pygame.draw.rect(s, (25, 25, 33), r, border_radius=17)
        pygame.draw.rect(s, (205, 204, 202), r, width=3, border_radius=17)
        pygame.draw.rect(s, (91, 73, 45), r.inflate(-12, -12), width=1, border_radius=12)
        title = pygame.font.SysFont("Microsoft YaHei", 26, bold=True).render(
            "游 戏 介 绍", True, (255, 225, 147)
        )
        s.blit(title, (r.centerx - title.get_width() // 2, r.y + 23))
        lines = (
            ("游戏类型：射击", 16, (255, 224, 151)),
            ("", 12, (0, 0, 0)),
            ("病毒席卷世界，城市被僵尸占领。", 16, (235, 232, 225)),
            ("拿起武器，守住最后的生存阵地！", 16, (235, 232, 225)),
            ("", 12, (0, 0, 0)),
            ("玩法目标", 18, (255, 218, 128)),
            ("· 消灭来袭僵尸，完成关卡任务", 16, (225, 222, 216)),
            ("· 收集金币钻石，购买更强武器", 16, (225, 222, 216)),
            ("· 搭配三种道具，合理使用护甲", 16, (225, 222, 216)),
            ("· 挑战不同僵尸与强力首领", 16, (225, 222, 216)),
            ("· 解锁角色、机甲和更多关卡", 16, (225, 222, 216)),
        )
        y = r.y + 79
        for text, size, color in lines:
            if text:
                _guide_text(s, text, (r.x + 31, y), size, color)
            y += 29 if text else 12

    def draw(self, s):
        bg_dim(s, 140)
        intro = self._intro_rect()
        if intro:
            self._draw_intro(s, intro)
        self._draw_guide(s)
        cr = self._close_rect(intro) if intro else None
        if cr and self._close:
            s.blit(pygame.transform.smoothscale(self._close, cr.size), cr.topleft)
        self.close_rect = cr
