"""战斗结算面板 —— 布局全部来自反编译常量（RE_NOTES.md「结算面板几何」节）。

DialogLevelPassed::init @0x1ac330 / InitCoinAndCrystal @0x1ac754 /
onScoreAnimation2 @0x1abed0 / DialogLevelFailed::init @0x1adde8 /
onFailedAnimation0 @0x1adca0 / onFailedAnimation2 @0x1ad0a0

文本用原版位图字体（EzScoreText → GameFonts/captuer_it），非系统 TTF。
cocos 语义：anchor/pos 为比例 × 面板尺寸；cocos y 向上，渲染时取 (1-y)。
"""

import math

import pygame

from engine import res
from engine.bmpfont import BitmapText
from game.dialog import (
    POP_TIME,
    close_rect_for,
    default_close_rect,
    draw_close_icon,
    draw_scaled,
    pop_scale,
)
from game.dialog import (
    H as DH,
)
from game.dialog import (
    W as DW,
)


GOLD = (255, 214, 90)
WHITE = (255, 255, 255)


def _draw_9cell(s, tex, rect, border=24):
    """九宫格拉伸 —— 对应原版 EzBaseDialog::getDialogBg / CCScale9Sprite。

    四角不拉伸，四边单向拉伸，中心双向拉伸。
    244x183 的原图按 border=24 切角。
    """
    im = res.load_img(tex)
    if not im:
        return
    iw, ih = im.get_size()
    b = min(border, iw // 3, ih // 3)
    w, h = rect.w, rect.h
    # 四角
    src = [(0, 0), (iw - b, 0), (0, ih - b), (iw - b, ih - b)]
    dst = [
        (rect.x, rect.y),
        (rect.right - b, rect.y),
        (rect.x, rect.bottom - b),
        (rect.right - b, rect.bottom - b),
    ]
    for (sx, sy), (dx, dy) in zip(src, dst):
        s.blit(im, (dx, dy), pygame.Rect(sx, sy, b, b))
    # 上下边（横向拉伸）
    for sy, dy in ((0, rect.y), (ih - b, rect.bottom - b)):
        strip = pygame.transform.smoothscale(
            im.subsurface(pygame.Rect(b, sy, iw - 2 * b, b)), (w - 2 * b, b)
        )
        s.blit(strip, (rect.x + b, dy))
    # 左右边（纵向拉伸）
    for sx, dx in ((0, rect.x), (iw - b, rect.right - b)):
        strip = pygame.transform.smoothscale(
            im.subsurface(pygame.Rect(sx, b, b, ih - 2 * b)), (b, h - 2 * b)
        )
        s.blit(strip, (dx, rect.y + b))
    # 中心
    s.blit(
        pygame.transform.smoothscale(
            im.subsurface(pygame.Rect(b, b, iw - 2 * b, ih - 2 * b)), (w - 2 * b, h - 2 * b)
        ),
        (rect.x + b, rect.y + b),
    )


class ResultPanel:
    """win=DialogLevelPassed / lose=DialogLevelFailed。"""

    def __init__(self, result, save, audio=None):
        self.r = result
        self.save = save
        self.audio = audio
        self.t = 0.0
        self.done = False
        self.applied = False
        self._star_played = False
        self.retry_rect = None
        self.menu_rect = None
        self.close_rect = None
        self.recommend_rects = []  # [(kind, name, rect)] 底部推荐条的可点区域
        # 金币飞行（E5 flyCoinOrCrystal / BonusCoinAnimation）
        self.coin_fly = []

    def _compute_close_rect(self):
        if self.close_rect is not None:
            return
        tex = (
            "pic/ui/dialog/victory_bg.png"
            if self.r.get("win")
            else "pic/ui/dialog/failed_bg.png"
        )
        bg = res.load_img(tex)
        if not bg:
            self.close_rect = default_close_rect(True)
            return
        bw, bh = bg.get_size()
        if self.r.get("win"):
            panel = pygame.Rect(
                int(DW * 0.5 - bw // 2), int(DH * (1 - 0.55) - bh // 2), bw, bh
            )
        else:
            panel = pygame.Rect(
                int(DW * 0.5 - bw // 2), int(DH - DH * 0.54 - bh // 2), bw, bh
            )
        self.close_rect = close_rect_for(panel, right=10, top=8)

    def _score_anim(self, target, idx):
        """DialogLevelPassed::onScoreAnimation1 —— 逐行 0 → target 计数。

        原版：setScore(0) + addScore(target)，EzScoreText 内部按 0.5f 速度滚动，
        onScoreAnimation1 用 DelayTime(0.8f) 才排下一段，因此这里按行错峰。
        """
        if not self._anim_started:
            return target
        t = self.t - 0.35 - idx * 0.22
        if t <= 0:
            return 0
        p = min(1.0, t / 0.55)
        # EaseElasticOut 收尾，对应 onScoreAnimation2 的 CCEaseElasticOut
        return int(round(target * p))

    _anim_started = False

    def _apply_reward(self):
        """写通关奖励。抽出来是因为玩家可能在第一帧就点掉结算面板，
        那时 update() 还没跑到 t>0.4，进度会整个丢掉。
        """
        if self.applied:
            return
        self.applied = True
        if self.r["win"]:
            self.save.add_coins(self.r["coin"])
            # 钻石奖励：原版 DialogLevelPassed::InitCoinAndCrystal @0x1ac754
            # 把 mission_reward_crystal 加进 user_crystal。
            cry = int(self.r.get("crystal", 0) or 0)
            if cry > 0:
                self.save.add_crystals(cry)
            self.save.update_level_data(self.r["mission_id"], self.r["score"], self.r["star"])
            self._spawn_coin_fly()
        else:
            self.save.save()

    def update(self, dt):
        self.t += dt
        if self.t > 0.35:
            self._anim_started = True
        if self.t > 0.8 and not self._star_played and self.r["win"]:
            self._star_played = True
            if self.audio:
                self.audio.star()
        if self.t > 0.4:
            self._apply_reward()
        self._tick_coin_fly(dt)

    # ---- 金币飞行 ----
    # HUD 金币图标中心（节点 battle_coin_icon = 104.0, 70.8, 30x30）。
    #   计数器上，看起来就像「没做动画」。
    _COIN_TARGET = (119.0, 86.0)

    def _spawn_coin_fly(self):
        """BonusCoinAnimation：金币从结算面板「奖金」行飞向左上计数器。"""
        coin = res.load_img("pic/ui/common/coin.png")
        if not coin:
            return
        # 起点 = 面板奖金行左侧；终点 = 屏幕左上角 HUD 金币图标 (119, 86)
        start = self._coin_row_pos()
        if start is None:
            return
        n = max(1, min(12, self.r["coin"] // 50 or 1))
        for i in range(n):
            self.coin_fly.append(
                {
                    "x": start[0],
                    "y": start[1],
                    "t": -i * 0.06,  # 错峰起飞
                    "life": 0.55,
                    "done": False,
                }
            )

    def _coin_row_pos(self):
        bg = res.load_img("pic/ui/dialog/victory_bg.png")
        if not bg:
            return None
        px, py = 854 * 0.5, 480 * (1 - 0.55)
        bw, bh = bg.get_size()
        x0 = px - bw // 2
        y0 = py - bh // 2
        return (x0 + bw * 0.36, y0 + bh * (1 - (0.755 - 0.108 * 3)))

    def _tick_coin_fly(self, dt):
        if not self.coin_fly:
            return
        for c in self.coin_fly:
            c["t"] += dt
            if c["t"] >= c["life"]:
                c["done"] = True
        self.coin_fly = [c for c in self.coin_fly if not c["done"]]

    def _draw_coin_fly(self, s):
        if not self.coin_fly:
            return
        coin = res.load_img("pic/ui/common/coin.png")
        if not coin:
            return
        im = pygame.transform.smoothscale(coin, (22, 22))
        x1, y1 = self._COIN_TARGET
        cache = {22: im}
        for c in self.coin_fly:
            if c["t"] < 0:
                continue
            p = min(1.0, c["t"] / c["life"])
            # 二次贝塞尔：起点 → 中间抬升 → 金币计数器
            x0, y0 = c["x"], c["y"]
            mx, my = (x0 + x1) * 0.5, min(y0, y1) - 90
            x = (1 - p) ** 2 * x0 + 2 * (1 - p) * p * mx + p**2 * x1
            y = (1 - p) ** 2 * y0 + 2 * (1 - p) * p * my + p**2 * y1
            # 末段吸气：越接近图标越小，视觉上像「被收进去」（按 2px 挡缓存）
            w = max(8, int(22 * (1.0 - 0.32 * p)) // 2 * 2)
            if w not in cache:
                cache[w] = pygame.transform.smoothscale(coin, (w, w))
            s.blit(cache[w], (int(x) - w // 2, int(y) - w // 2))

    def _compute_failed_rects(self, W=None, H=None):
        """不依赖 draw 就能算出失败面板的按钮点击区。

        retry_rect / menu_rect 原本只在 draw() 里赋值，
        玩家在第一次绘制之前点击就点不到。
        """
        if self.retry_rect is not None and self.menu_rect is not None:
            return
        from game.dialog import H as DH
        from game.dialog import W as DW

        W = W if W is not None else DW
        H = H if H is not None else DH
        bg = res.load_img("pic/ui/dialog/failed_bg.png")
        if not bg:
            return
        bw, bh = bg.get_size()
        px = int(W * 0.5)
        panel_cy = H * 0.54
        panel = pygame.Rect(px - bw // 2, int(H - panel_cy - bh // 2), bw, bh)
        by = int(panel.y + bh - bh * 0.25)
        retry = res.load_img("pic/ui/shop/button_retry.png")
        if retry and self.retry_rect is None:
            rx = px - bw // 2 + int(bw * 0.27)
            self.retry_rect = pygame.Rect(
                rx - retry.get_width() // 2,
                by - retry.get_height() // 2,
                retry.get_width(),
                retry.get_height(),
            )
        menu = res.load_img("pic/ui/shop/button_menu.png")
        if menu and self.menu_rect is None:
            mx = px - bw // 2 + int(bw * 0.73)
            self.menu_rect = pygame.Rect(
                mx - menu.get_width() // 2,
                by - menu.get_height() // 2,
                menu.get_width(),
                menu.get_height(),
            )

    def key_items(self):
        """全键盘：结算面板上方向键能选中的东西。

        失败面板有「重试 / 菜单」两个按钮 + 底部推荐条；胜利面板**没有任何
        按钮**（原版是「点击任意处继续」），纯键盘玩家打完一关就再也走不动了。
        所以胜利面板补一个虚拟的「继续」焦点区，正好压在
        text_touch_continue 提示上 —— 回车 = 点提示 = 继续。
        """
        self._compute_close_rect()
        out = []
        if self.close_rect is not None:
            out.append((self.close_rect, "关闭"))
        if self.r.get("win"):
            out.append((self._continue_rect(), "继续"))
            return out
        self._compute_failed_rects()
        for r, label in ((self.retry_rect, "重试"), (self.menu_rect, "菜单")):
            if r is not None:
                out.append((r, label))
        for _kind, name, rect in getattr(self, "recommend_rects", ()):
            out.append((rect, name or "推荐"))
        return out

    def _continue_rect(self):
        """胜利面板「点击继续」提示的屏幕矩形（焦点框画在这上面）。"""
        from game.dialog import H as DH
        from game.dialog import W as DW

        tip = res.load_img("pic/ui/battlefield/text_touch_continue.png")
        w = tip.get_width() if tip else 220
        h = tip.get_height() if tip else 26
        return pygame.Rect(int(DW * 0.5 - w // 2), int(DH * 0.85 - h // 2), w, h)

    def click(self, pos=None):
        self._apply_reward()
        self._compute_close_rect()
        if pos and self.close_rect and self.close_rect.collidepoint(pos):
            self.done = True if self.r.get("win") else "menu"
            return
        if pos:
            for kind, name, rect in getattr(self, "recommend_rects", []):
                if kind == "gun" and rect.collidepoint(pos):
                    self.done = "buy_gun"
                    self.done_arg = name
                    return
        # 失败面板按钮命中（rect 还没算过就先算一次）
        if not self.r["win"] and pos:
            if self.retry_rect is None or self.menu_rect is None:
                self._compute_failed_rects()
        if not self.r["win"] and pos:
            if self.retry_rect and self.retry_rect.collidepoint(pos):
                self.done = "retry"
                return
            if self.menu_rect and self.menu_rect.collidepoint(pos):
                self.done = "menu"
                return
        self.done = True

    # ------------------------------------------------------------ 绘制
    def draw(self, s, W, H):
        """整层缩放弹出（只有失败面板走弹出；胜利面板本来就是逐项动画）。"""
        self._compute_close_rect()
        if self.r.get("win"):
            self._draw_impl(s, W, H)
            draw_close_icon(s, self.close_rect)
            return
        sc = pop_scale(self.t)
        if abs(sc - 1.0) < 0.002:
            self._draw_impl(s, W, H)
            draw_close_icon(s, self.close_rect)
            return
        lay = pygame.Surface((W, H), pygame.SRCALPHA)
        self._draw_impl(lay, W, H)
        draw_scaled(s, lay, sc)
        draw_close_icon(s, self.close_rect)

    def _draw_impl(self, s, W, H):
        if self.r["win"]:
            self._draw_passed(s, W, H)
        else:
            self._draw_failed(s, W, H)
        # 触碰继续：只在胜利面板有（原版 text_touch_continue.png 仅 DialogLevelPassed 使用，
        # 反编译 24909 行；失败面板无此提示）
        if self.t > 1.2 and self.r["win"]:
            tip = res.load_img("pic/ui/battlefield/text_touch_continue.png")
            a = int(160 + 95 * (0.5 + 0.5 * math.sin(self.t * 4)))
            if tip:
                tw = tip.get_width()
                im = tip.copy()
                im.set_alpha(a)
                s.blit(im, (int(W * 0.5) - tw // 2, int(H * 0.85) - im.get_height() // 2))

    def _rating_img(self, grade, gs):
        g = res.load_img("pic/ui/dialog/result_rating_%s.png" % grade)
        if not g:
            return None
        if gs != 1.0:
            gw = max(1, int(g.get_width() * gs))
            gh = max(1, int(g.get_height() * gs))
            return pygame.transform.smoothscale(g, (gw, gh))
        return g

    def _rating_scale(self):
        # 原版 scale 15→1.0 是「印章从远处砸下来」的入场动画，但 15 倍
        # 贴图会把整块结算面板连同按钮全糊住 1.8 秒，玩家看不见也点不到。
        # 压到 2.5 倍起、0.35 秒收完，保留冲击感又不挡内容。
        if self.t < 0.35:
            return 2.5 - 1.5 * (self.t / 0.35)
        if self.t < 0.8:
            p = min(1.0, (self.t - 0.35) / 0.45)
            return 1.0 + 0.12 * (1 - p) * math.sin(p * 11)
        return 1.0

    # ---- DialogLevelPassed @0x1ac330 ----
    def _draw_passed(self, s, W, H):
        bg = res.load_img("pic/ui/dialog/victory_bg.png")
        if not bg:
            return
        px, py = int(W * 0.5), int(H * (1 - 0.55))
        bw, bh = bg.get_size()
        panel = pygame.Rect(px - bw // 2, py - bh // 2, bw, bh)
        s.blit(bg, panel.topleft)

        # 4 行数字：x=W_bg*0.36（anchor(0,0.5)），y0=0.755，dy=0.108（相对 bg，cocos y 上）
        # 行序（onScoreAnimation1 @0x1ab88c）：+100=评分 ←a5*100；+99=血量 ←a4*100；
        # +101=用时(TimeAnim)；+102=击杀 —— 与 bg 内标签[生命/击杀/时间/奖金]对位。
        rows = [
            "%d%%" % self._score_anim(int(self.r.get("blood", 0)), 0),
            "%d" % self._score_anim(int(self.r.get("kills", 0)), 1),
            "%.1fs" % min(self.r.get("time", 0), self.r.get("time", 0) * (self.t / 1.5)),
        ]
        x = panel.x + int(bw * 0.36)
        for i, txt in enumerate(rows):
            yy = panel.y + bh * (1 - (0.755 - 0.108 * i))
            BitmapText(txt, 30, WHITE).draw(s, x, yy, anchor=(0, 0.5))

        # 评级图 (0.77, 0.6) z=3
        gname = {"S": "s", "A": "a", "B": "b"}.get(self.r["grade"], "c")
        g = self._rating_img(gname, self._rating_scale())
        if g:
            s.blit(
                g,
                (
                    panel.x + int(bw * 0.77) - g.get_width() // 2,
                    panel.y + int(bh * (1 - 0.60)) - g.get_height() // 2,
                ),
            )

        # 金币行：对齐 bg 内「奖金」标签（行4）；decomp InitCoinAndCrystal 顺序 = coin 图 → 数字
        coin = res.load_img("pic/ui/common/coin.png")
        cy = panel.y + bh * (1 - (0.755 - 0.108 * 3))
        cw = 22
        cx = panel.x + int(bw * 0.36)
        if coin:
            cm = pygame.transform.smoothscale(coin, (cw, cw))
            s.blit(cm, (cx, int(cy) - cw // 2))
            cx += cw + 4
        BitmapText("+%d" % self._score_anim(self.r["coin"], 3), 30, GOLD).draw(
            s, cx, cy, anchor=(0, 0.5)
        )
        self._draw_coin_fly(s)

    # ---- DialogLevelFailed @0x1adde8 (sub_1ADDE8) ----
    def _draw_failed(self, s, W, H):
        """失败面板 —— 逐条照抄 sub_1ADDE8 @0x1adde8。

        原版结构（cocos y 向上，屏幕 y = H - cocos_y）：
          · 主面板 pic/ui/dialog/failed_bg.png（462x280，不拉伸）
            anchor(0.5,0.5)，位置 (W*0.5, H*0.47)，z=3
          · 「失败」标题 pic/ui/dialog/mission_failed.png
            位置 (W*0.5, H*0.6)，z=2，scale 200→1.2 (0.2s) →1.4 (0.1s)，旋转 -8°
          · 三行数据 EzScoreText / TimeAnimationText，anchor(0,0.5)
            x = bg.w*0.355；y = bg.h*0.73 / 0.597 / 0.464
          · 评级 pic/ui/dialog/result_rating_c.png
            位置 (bg.w*0.77, bg.h*0.58)，scale 15→1.0 (0.7s) →1.0 (1.1s elastic)
          · 按钮 pic/ui/shop/button_retry.png 在 (bg.w*0.27, bg.h*0.25)
            pic/ui/shop/button_menu.png 在 (bg.w*0.73, bg.h*0.25)
          · 底部推荐条 pic/ui/dialog/recommend_bg_2.png
            anchor(0.5,0)，位置 (W*0.5, 0)，z=4，opacity 0.9
        """
        bg = res.load_img("pic/ui/dialog/failed_bg.png")
        if not bg:
            return
        bw, bh = bg.get_size()
        px = int(W * 0.5)
        panel_cx = px
        # init 时面板在 (W*0.5, H*0.47)，但 onFailedAnimation4 末尾把它
        # MoveTo 到 (W*0.5, H*0.54)（0.4s 缓动）—— 动画结束后的静止位置是 H*0.54。
        # 模拟器 854 尺度实测：面板顶 80、底 360、中心 220 = 480 - 0.54*480 ✓
        panel_cy = H * 0.54
        panel = pygame.Rect(px - bw // 2, int(H - panel_cy - bh // 2), bw, bh)
        s.blit(bg, panel.topleft)

        # 标题：「失败」二字已烘死在 failed_bg.png 顶部（x 168..262, y 2..45）。
        # 反编译里另有 pic/ui/dialog/mission_failed.png（=「任务失败」四字），
        # 但它 z=2 低于面板 z=3，且 scale 200→1.4 是「任务失败」压在「失败」上，
        # 模拟器参考帧中并未出现 —— 原版这条路径实际不画，故不绘制。

        # 三行数据：x = bg.w*0.355，y = bg.h*0.73 / 0.597 / 0.464
        t = self.r.get("time", 0)
        mm, ss = int(t) // 60, int(t) % 60
        rows = [
            ("%d%%" % int(self.r.get("blood", 0)), 0.73),
            ("%d" % int(self.r.get("kills", 0)), 0.597),
            ("%02d:%02d" % (mm, ss), 0.464),
        ]
        # fy 是面板局部 cocos y（相对面板底边），anchor(0,0.5)
        # 面板局部 (x,y) → 屏幕 x = 面板左 + x，屏幕 y = 面板顶 + (bh - y)
        # 字号：sub_1ADDE8 里 GameFonts::getTexFont(v8, 0) → score_white，
        # 该字体 size = 25.0（GameFonts::init @0x11d740 第 5 参数）。
        dx = panel.x + int(bw * 0.355)
        for txt, fy in rows:
            yy = int(panel.y + bh - bh * fy)
            BitmapText(txt, 25, WHITE).draw(s, dx, yy, anchor=(0, 0.5))

        # 评级 C：(bg.w*0.77, bg.h*0.58)，anchor(0.5,0.5)
        # 反编译 sub_1ADDE8：CCNode::setScale(v1, 15.0) → CCMoveTo...
        #   onFailedAnimation4：CCScaleTo(0.7) → 1.1，再 EaseElasticOut 收尾
        # 所以静止状态的 scale 是 **1.1**（不是 1.0）。
        # 早先按「模拟器轮廓 80x59」倒推成 0.9×0.74，把 C 压小了 20%。
        g = self._rating_img("c", self._rating_scale() * 1.1)
        if g:
            gw, gh = g.get_size()
            s.blit(g, (panel.x + int(bw * 0.77) - gw // 2, int(panel.y + bh - bh * 0.58) - gh // 2))

        # 按钮：retry (bg.w*0.27, bg.h*0.25)、menu (bg.w*0.73, bg.h*0.25)
        by = int(panel.y + bh - bh * 0.25)
        retry = res.load_img("pic/ui/shop/button_retry.png")
        if retry:
            rx = panel_cx - bw // 2 + int(bw * 0.27)
            self.retry_rect = pygame.Rect(
                rx - retry.get_width() // 2,
                by - retry.get_height() // 2,
                retry.get_width(),
                retry.get_height(),
            )
            s.blit(retry, self.retry_rect.topleft)
        menu = res.load_img("pic/ui/shop/button_menu.png")
        if menu:
            mx = panel_cx - bw // 2 + int(bw * 0.73)
            self.menu_rect = pygame.Rect(
                mx - menu.get_width() // 2,
                by - menu.get_height() // 2,
                menu.get_width(),
                menu.get_height(),
            )
            s.blit(menu, self.menu_rect.topleft)

        self._draw_recommend_bar(s, W, H)

    def _failed_title_scale(self):
        """onFailedAnimation0：scale 200 → 1.2 (0.2s) → 1.4 (0.1s)。"""
        if self.t < 0.2:
            return 200.0 + (1.2 - 200.0) * (self.t / 0.2)
        if self.t < 0.3:
            return 1.2 + (1.4 - 1.2) * ((self.t - 0.2) / 0.1)
        return 1.4

    def _draw_recommend_bar(self, s, W, H):
        """底部推荐条 —— sub_1ADDE8 尾段 + addRecommendGun/Ability/Mech。

        条：pic/ui/dialog/recommend_bg_2.png，anchor(0.5,0)，位置 (W*0.5, 0)，opacity 0.9
        商品槽 x = bg.w*0.21 / 0.5 / 0.78，y = bg.h*0.44；
        购买按钮 button_buy.png scale 5.0。
        """
        bar = res.load_img("pic/ui/dialog/recommend_bg_2.png")
        if not bar:
            return
        # 原版对这条 setScale(0.9)（sub_1ADDE8 里 1063675494 = 0.9f）。
        # 模拟器实测：贴图 672 宽 → 屏幕 605 宽（854 尺度），橙区 528 → 476，同样 0.902。
        BAR_SCALE = 0.9
        bw = int(bar.get_width() * BAR_SCALE)
        bh = int(bar.get_height() * BAR_SCALE)
        im = pygame.transform.smoothscale(bar, (bw, bh))
        if self.t > 0.3:
            im = im.copy()
            im.set_alpha(230)  # 原版 opacity 0.9
        bx = int(W * 0.5 - bw // 2)
        by = int(H - bh)
        s.blit(im, (bx, by))
        self.recommend_rects = []  # 每帧重建（这是 emulation 的可点区域）

        # 槽位 x（相对推荐条宽）：
        #   枪 addRecommendGun(a3=0)  → bg.w*0.21
        #   技能/机械 addRecommendAbility/Mech(a3=1) → bg.w*0.76
        #   广告墙 addOfferWall        → bg.w*0.5（中槽）
        # y 统一 bg.h*0.44；购买按钮 button_buy.png scale 5.0 在 bg.h*0.4。
        cw = bw * 0.2
        ch = bh * 0.68
        slots = (0.21, 0.76, 0.5)
        for i, (kind, keys) in enumerate(self._recommend_items()):
            icon = self._recommend_icon(kind, keys)
            if not icon:
                continue
            iw, ih = icon.get_size()
            cx = bx + int(bw * slots[i])
            cy = int(H - bh * 0.44)
            if kind == "offer":
                # genOfferWall 不缩放，贴图原尺寸居中
                dw, dh = iw, ih
                im2 = icon
            else:
                sc = min(ch / ih, (cw * 1.06) / iw)
                dw, dh = max(1, int(iw * sc)), max(1, int(ih * sc))
                im2 = pygame.transform.smoothscale(icon, (dw, dh))
            if kind == "gun":
                # genRecommendGun：setRotation(-15.0f)
                im2 = pygame.transform.rotate(im2, 15)
            dest = pygame.Rect(
                cx - im2.get_width() // 2,
                cy - im2.get_height() // 2,
                im2.get_width(),
                im2.get_height(),
            )
            s.blit(im2, dest.topleft)
            # 记录可点区域：失败后点推荐枪 → 原版弹 DialogFailedWeapon 的折扣窗
            self.recommend_rects.append((kind, (keys[0] if keys else ""), dest))
            buy = res.load_img("pic/ui/recommend/button_buy.png")
            if buy:
                bw2 = max(1, int(buy.get_width() * 5.0))
                bh2 = max(1, int(buy.get_height() * 5.0))
                bim = pygame.transform.smoothscale(buy, (bw2, bh2))
                s.blit(bim, (cx - bw2 // 2, int(H - bh * 0.4) - bh2 // 2))

    def _recommend_items(self):
        """原版 Recommender::getRecommendItems：枪 + 技能 + 机械，各一件。

        数据在原版来自运行时，本地取仓库中真实存在的资源名，顺序与原版一致。

        ★ **已经拥有的不能再推荐**（原版 Recommender 只推没买过的商品）。
        """
        # 槽位 0 = 枪，槽位 1 = offer_wall（广告墙，见 genOfferWall / addOfferWall），
        # 槽位 2 = 技能 / 机械。原版 addRecommendItems 里 3 件商品按 Recommender 结果，
        # 中间槽在只有 2 件时用 offer_wall 补位。
        # 枪：模拟器参考帧弹的是「沙漠之鹰」折扣购买窗（emu_s3.png：
        # 4000 → 3000，限时 75 折）。原版 Recommender 会推一把玩家买得起
        # 且 DPS 明显更高的枪，所以优先沙漠之鹰，其次 uzi / ak47。
        owned = set()
        try:
            owned = set(self.save.d.get("owned_weapons") or [])
        except Exception:
            owned = set()
        guns = [
            g
            for g in (
                "desert_eagle",
                "uzi",
                "ak47",
                "m4",
                "m16",
                "mp5",
                "p90",
                "spas12",
                "m870",
                "m200",
                "colt_anaconda",
            )
            if g not in owned
        ]
        if not guns:
            # 全买过了 → 这一格不推荐枪（用 offer_wall 补位）
            return [("offer", ["offer_wall"]), ("mech", ["mech_10", "mech_9", "mech_8"])]
        mechs = [
            m
            for m in ("mech_10", "mech_9", "mech_8")
            if m not in set(self.save.d.get("owned_mechs") or [])
        ]
        out = [("gun", guns)]
        out.append(("mech", mechs) if mechs else ("offer", ["offer_wall"]))
        out.append(("offer", ["offer_wall"]))
        return out

    def _recommend_icon(self, kind, keys):
        """按类别取推荐商品图标，取第一个真实存在的资源。"""
        if kind == "gun":
            prefix, root = "gun_", "pic/ui/upgrade/"
        elif kind == "offer":
            prefix, root = "", "pic/ui/recommend/"
        elif kind == "ability":
            prefix, root = "ability_", "pic/ui/shop/"
        else:
            prefix, root = "", "pic/mech/"
        for k in keys:
            p = root + prefix + k + ".png"
            if res.exists_img(p):
                return res.load_img(p)
        return None
