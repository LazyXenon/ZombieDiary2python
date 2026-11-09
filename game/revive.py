"""续天对话框 —— 士兵阵亡后弹「续天(N)」，花 ¥2.0 复活。

原版对应：
  * DialogLevelSaveMe::init @0x147a48 / addSaveMeContent @0x147d10
  * BattleField::onReviveSoldier @0x16d61c

几何（反编译）：
  底图  pic/ui/shop/property_bg.png（391x238）
        anchor(0.5,0.5) at (W*0.5, H*0.5)，内容缩放 0.7，anchor(0.5,0.45)
  标题  text_revive_child / text_revive_immediately，anchor(0,0.5) at (w*0.14, h*0.42)
  文案  save_me_text_2 / save_me_text_3
  确认  saveme_ok.png     anchor(1,0) at (w*0.88, h*0.18)
  取消  saveme_cancel.png anchor(0,0) at (w*0.12, h*0.18)
"""

import math

import pygame

from engine import res
from game.dialog import (
    close_rect_for,
    draw_close_icon,
    draw_scaled,
    pop_scale,
)


W, H = 854, 480

BG_TEX = "pic/ui/shop/property_bg.png"
TITLE_TEX = "pic/ui/dialog/text_revive_child.png"
IMMEDIATE_TEX = "pic/ui/dialog/text_revive_immediately.png"
TEXT2_TEX = "pic/ui/dialog/save_me_text_2.png"
TEXT3_TEX = "pic/ui/dialog/save_me_text_3.png"
OK_TEX = "pic/ui/dialog/saveme_ok.png"
CANCEL_TEX = "pic/ui/dialog/saveme_cancel.png"
# 续天消耗的货币：原版 DialogLevelSaveMe::getCrystalNode 用的是钻石
CRYSTAL_TEX = "pic/ui/common/crystal.png"

BG_SCALE = 1.0
CONTENT_SCALE = 0.7
BG_ANCHOR_Y = 0.45
# cocos y 向上 → 屏幕 y = 1 - y
TITLE_POS = (0.10, 0.76)  # 续天(N)
IMMEDIATE_POS = (0.10, 0.62)  # 立即复活这个孩子
COST_POS = (0.10, 0.47)  # 需要花费 + 否则将失去今天获得的：
ITEM_POS = (0.44, 0.26)  # 奖励图标
OK_POS = (0.90, 0.16)  # 确认（anchor 1,0）
CANCEL_POS = (0.10, 0.16)  # 取消（anchor 0,0）


class RevivePanel:
    """续天对话框。确认付费复活，取消则失败结算。"""

    def __init__(self, battle, save, audio=None):
        self.battle = battle
        self.save = save
        self.audio = audio
        self.t = 0.0
        self.done = False
        self.revived = False
        self.ok_rect = None
        self.cancel_rect = None
        self.close_rect = None
        self._bg_rect = None

    def _compute_close_rect(self):
        if self.close_rect is not None:
            return
        bg = res.load_img(BG_TEX)
        if bg:
            bw, bh = bg.get_size()
            r = pygame.Rect(
                int(W * 0.5 - bw * BG_SCALE * 0.5),
                int(H * 0.5 - bh * BG_SCALE * BG_ANCHOR_Y),
                int(bw * BG_SCALE),
                int(bh * BG_SCALE),
            )
        else:
            r = pygame.Rect(int(W * 0.5 - 137), int(H * 0.5 - 84), 274, 167)
        self.close_rect = close_rect_for(r, right=8, top=6)

    def update(self, dt):
        self.t += dt

    def can_afford(self):
        """钻石够不够续天。

        ★ 原版 DialogLevelSaveMe::getCrystalNode @0x14759c 里画的是
          **钻石图标 + 数字**（原文写死 "5"），所以续天消耗的是钻石。
        """
        return int(self.save.d.get("crystals", 0) or 0) >= self.battle.revive_cost

    def _compute_button_rects(self):
        """不依赖 draw 就能算出续天面板的按钮点击区。

        ok_rect / cancel_rect 原本只在 draw() 里赋值，
        玩家在第一次绘制之前点击就点不到。
        """
        if self.ok_rect is not None and self.cancel_rect is not None:
            return
        bg = res.load_img(BG_TEX)
        if bg:
            bw, bh = bg.get_size()
            r = pygame.Rect(
                int(W * 0.5 - bw * BG_SCALE * 0.5),
                int(H * 0.5 - bh * BG_SCALE * BG_ANCHOR_Y),
                int(bw * BG_SCALE),
                int(bh * BG_SCALE),
            )
        else:
            r = pygame.Rect(int(W * 0.5 - 195), int(H * 0.5 - 107), 391, 238)
        ok = res.load_img(OK_TEX)
        if ok and self.ok_rect is None:
            px = r.x + r.w * OK_POS[0]
            py = r.y + r.h * (1 - OK_POS[1])
            self.ok_rect = pygame.Rect(
                int(px - ok.get_width()), int(py), ok.get_width(), ok.get_height()
            )
        cancel = res.load_img(CANCEL_TEX)
        if cancel and self.cancel_rect is None:
            px = r.x + r.w * CANCEL_POS[0]
            py = r.y + r.h * (1 - CANCEL_POS[1])
            self.cancel_rect = pygame.Rect(
                int(px), int(py), cancel.get_width(), cancel.get_height()
            )

    def click(self, pos):
        self._compute_close_rect()
        if self.close_rect and self.close_rect.collidepoint(pos):
            self.done = True  # 与取消一致：不复活，进入失败结算
            return
        if self.ok_rect is None or self.cancel_rect is None:
            self._compute_button_rects()
        if self.ok_rect and self.ok_rect.collidepoint(pos):
            if self.can_afford():
                # ★ 扣**钻石**（原版 getCrystalNode：续天消耗的是钻石）
                self.save.spend_crystals(self.battle.revive_cost)
                if self.battle.revive():
                    self.revived = True
                    self.done = True
                    if self.audio:
                        self.audio.sfx("tab")
                else:
                    # 续天次数用尽（Battle::revive 里已经 over=lose 并 finish）。
                    # 这里必须同样收尾 —— 否则 done 永远 False，面板关不掉，
                    # App.step 卡在 revive 分支不再 tick 战斗，点什么都没反应，
                    # 整个游戏死在这一帧。
                    self.done = True
            else:
                self.done = True
            return
        if self.cancel_rect and self.cancel_rect.collidepoint(pos):
            self.done = True

    # ------------------------------------------------------------ 绘制
    def draw(self, s):
        """整层缩放弹出：前 0.18s 从 0.62 弹到 1.0。"""
        self._compute_close_rect()
        sc = pop_scale(self.t)
        if abs(sc - 1.0) < 0.002:
            self._draw_impl(s)
            draw_close_icon(s, self.close_rect)
            return
        lay = pygame.Surface((W, H), pygame.SRCALPHA)
        self._draw_impl(lay)
        draw_scaled(s, lay, sc)
        draw_close_icon(s, self.close_rect)

    def _draw_impl(self, s):
        bg = res.load_img(BG_TEX)
        if bg:
            bw, bh = bg.get_size()
            w, h = bw * BG_SCALE, bh * BG_SCALE
            x = W * 0.5 - w * 0.5
            y = H * 0.5 - h * BG_ANCHOR_Y
            r = pygame.Rect(int(x), int(y), int(w), int(h))
            self._bg_rect = r
            s.blit(pygame.transform.smoothscale(bg, r.size), r.topleft)
        else:
            r = pygame.Rect(int(W * 0.5 - 137), int(H * 0.5 - 84), 274, 167)
            self._bg_rect = r
            panel = pygame.Surface(r.size, pygame.SRCALPHA)
            panel.fill((120, 96, 175, 235))
            s.blit(panel, r.topleft)

        def put(tex, pos, anchor=(0.0, 0.5)):
            im = res.load_img(tex)
            if not im:
                return None
            px = r.x + r.w * pos[0]
            py = r.y + r.h * pos[1]
            px -= im.get_width() * anchor[0]
            py -= im.get_height() * anchor[1]
            s.blit(im, (int(px), int(py)))
            return pygame.Rect(int(px), int(py), im.get_width(), im.get_height())

        # 标题「续天(N)」用字体渲染（N = 剩余续命次数）
        ftitle = pygame.font.SysFont("Microsoft YaHei", 22, bold=True)
        t = ftitle.render("续天(%d)" % self.battle.revive_left, True, (255, 255, 255))
        s.blit(
            t,
            (
                int(r.x + r.w * TITLE_POS[0]),
                int(r.y + r.h * (1 - TITLE_POS[1]) - t.get_height() / 2),
            ),
        )
        put(IMMEDIATE_TEX, (IMMEDIATE_POS[0], 1 - IMMEDIATE_POS[1]))
        # 「需要花费」+「否则将失去今天获得的：」是接续的半句，同一行左对齐拼
        # ★ 中间夹的是**钻石图标 + 数量**（原版 DialogLevelSaveMe::getCrystalNode
        #   @0x14759c：crystal.png + EzTexText(getTexFont(3)=score_blue)，scale 1.6）。
        t2 = res.load_img(TEXT2_TEX)
        t3 = res.load_img(TEXT3_TEX)
        fcost = pygame.font.SysFont("Arial", 15, bold=True)
        cost = fcost.render(" %d " % self.battle.revive_cost, True, (120, 210, 255))
        if t2 and t3:
            # 原版内容缩放 0.7 ⇒ 两段文案按 0.7 缩小，正好排进 391 宽的面板。
            k = CONTENT_SCALE
            t2s = pygame.transform.smoothscale(
                t2, (max(1, int(t2.get_width() * k)), max(1, int(t2.get_height() * k)))
            )
            t3s = pygame.transform.smoothscale(
                t3, (max(1, int(t3.get_width() * k)), max(1, int(t3.get_height() * k)))
            )
            x = r.x + r.w * COST_POS[0]
            y = r.y + r.h * (1 - COST_POS[1]) - t2s.get_height() / 2
            s.blit(t2s, (int(x), int(y)))
            x += t2s.get_width()
            # 钻石图标（pic/ui/common/crystal.png）
            cry = res.load_img(CRYSTAL_TEX)
            if cry:
                cw = max(8, int(cry.get_width() * 0.42))
                ch = max(8, int(cry.get_height() * 0.42))
                cim = pygame.transform.smoothscale(cry, (cw, ch))
                s.blit(cim, (int(x), int(y + (t2s.get_height() - ch) / 2)))
                x += cw + 2
            s.blit(cost, (int(x), int(y + (t2s.get_height() - cost.get_height()) / 2)))
            x += cost.get_width()
            s.blit(t3s, (int(x), int(y)))

        # 奖励预览：金币图标 + 数量（anchor 0.5,0.5 at w*0.49, h*0.27）
        coin = res.load_img("pic/ui/common/coin.png")
        if coin:
            im = pygame.transform.smoothscale(coin, (26, 26))
            cx = r.x + r.w * ITEM_POS[0]
            cy = r.y + r.h * (1 - ITEM_POS[1])
            s.blit(im, (int(cx - 13), int(cy - 13)))
        f = pygame.font.SysFont("Arial", 18, bold=True)
        n = f.render(str(self.battle.reward_coin), True, (255, 214, 90))
        s.blit(n, (int(r.x + r.w * ITEM_POS[0] + 16), int(r.y + r.h * (1 - ITEM_POS[1]) - 9)))

        ok = res.load_img(OK_TEX)
        if ok:
            px = r.x + r.w * OK_POS[0]
            py = r.y + r.h * (1 - OK_POS[1])
            self.ok_rect = pygame.Rect(
                int(px - ok.get_width()), int(py), ok.get_width(), ok.get_height()
            )
            s.blit(ok, self.ok_rect.topleft)
        cancel = res.load_img(CANCEL_TEX)
        if cancel:
            px = r.x + r.w * CANCEL_POS[0]
            py = r.y + r.h * (1 - CANCEL_POS[1])
            self.cancel_rect = pygame.Rect(
                int(px), int(py), cancel.get_width(), cancel.get_height()
            )
            s.blit(cancel, self.cancel_rect.topleft)

        if not self.can_afford() and self.ok_rect:
            k = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.006)
            rr = self.ok_rect
            pygame.draw.rect(s, (150 + int(60 * k), 40, 40), rr, 3, border_radius=8)
            veil = pygame.Surface(rr.size, pygame.SRCALPHA)
            veil.fill((70, 16, 16, 90))
            s.blit(veil, rr.topleft)
