"""装备上限提醒 —— 原版 DialogEquipRemind。

反编译依据：
  DialogEquipRemind::init          @0x153b30
  DialogEquipRemind::setEquipType  @0x153cdc
  DialogEquipRemind::onScreenBack  @0x153c7e
  DialogEquipRemind::ccTouchEnded  @0x153ca0
  DialogEquipRemind::onKeyBack     @0x153ca8

════════════════════════════════════════════════════════════════════
结构
════════════════════════════════════════════════════════════════════
DialogEquipRemind（EzBaseDialog 子类）
  ├─ CCLayerColor  颜色 (0,0,0,0x80)  W×H     ← 全屏 50% 黑遮罩
  └─ EzNode 容器    contentSize = (W, H)  anchor(0.5,0.5)  pos(W*0.5, H*0.5)
       → 内容左下角正好在屏幕 (0,0)，子节点坐标即屏幕 cocos 坐标
       ├─ equip_remind_text_1.png       anchor(0,0.5)  tag 203
       ├─ equip_remind_weapon_1.png     tag 204   （武器版）
       │  或 equip_remind_ability_1.png          （道具版）
       ├─ equip_remind_text_2.png       tag 205
       ├─ equip_remind_text_3.png       tag 206
       └─ equip_remind_weapon_2.png     tag 207
          或 equip_remind_ability_2.png

setEquipType 的推进链（两行）：
  x = W*0.2, y = H*0.5
  行 1：text_1            (x, y)                x += 147
        weapon_1/ability_1 (x, y)               x += 207
        text_2             (x, y)               ← 同一行继续右排
  行 2：x 重置为 text_1 的 pos.x
        y = text_1.pos.y - text_1 内容高 - 2*LOGIC
        text_3             (x, y)               x += 351
        weapon_2/ability_2 (x, y)
  全部 anchor(0,0.5)。
  最后 setScale(0) → CCScaleTo(0.3s, 1.0) 弹出。

点击任意处 / 返回键 → onScreenBack。
"""

import pygame

from engine import res
from game.dialog import H, W, bg_dim, default_close_rect, draw_close_icon


LOGIC = 1.0

DIM_COLOR = (0, 0, 0, 0x80)

TEXT1 = "pic/ui/dialog/equip_remind_text_1.png"
TEXT2 = "pic/ui/dialog/equip_remind_text_2.png"
TEXT3 = "pic/ui/dialog/equip_remind_text_3.png"
WEAPON1 = "pic/ui/dialog/equip_remind_weapon_1.png"
WEAPON2 = "pic/ui/dialog/equip_remind_weapon_2.png"
ABILITY1 = "pic/ui/dialog/equip_remind_ability_1.png"
ABILITY2 = "pic/ui/dialog/equip_remind_ability_2.png"

X0 = 0.2  # 起始 x = W*0.2
Y0 = 0.5  # 首行 y = H*0.5
ROW_GAP = 2 * LOGIC
POP_TIME = 0.3  # CCScaleTo(0x3E99999A = 0.3, 1.0)


class EquipRemindDialog:
    """equip_type: 1 = 武器，2 = 道具。done 置 True 表示关闭。"""

    def __init__(self, app, equip_type=1):
        self.app = app
        self.equip_type = int(equip_type)
        self.t = 0.0
        self.done = False
        self.close_rect = default_close_rect(True)

    def update(self, dt):
        self.t += dt

    # ---------------------------------------------------------- 交互
    def click(self, pos):
        self.done = True
        return True

    def on_key_back(self):
        self.done = True
        return True

    # ---------------------------------------------------------- 布局
    def _runs(self):
        """返回 [(贴图, cocos_x, cocos_y)]，全部 anchor(0,0.5)。"""
        t1 = res.load_img(TEXT1)
        if not t1:
            return []
        pair1 = WEAPON1 if self.equip_type == 1 else ABILITY1
        pair2 = WEAPON2 if self.equip_type == 1 else ABILITY2

        x = W * X0
        y = H * Y0
        out = [(TEXT1, x, y)]
        w1 = t1.get_width()
        x += w1
        im = res.load_img(pair1)
        if im:
            out.append((pair1, x, y))
            x += im.get_width()
        im = res.load_img(TEXT2)
        if im:
            out.append((TEXT2, x, y))

        # 第二行：x 回到 text_1 的 pos.x，y = text_1.y - text_1 高 - 2*LOGIC
        x = W * X0
        y = (H * Y0 - t1.get_height()) - ROW_GAP
        im = res.load_img(TEXT3)
        if im:
            out.append((TEXT3, x, y))
            x += im.get_width()
        if res.load_img(pair2):
            out.append((pair2, x, y))
        return out

    # ---------------------------------------------------------- 绘制
    def draw(self, s):
        bg_dim(s, 140)
        # 遮罩：CCLayerColor (0,0,0,0x80) 全屏
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill(DIM_COLOR)
        s.blit(dim, (0, 0))
        draw_close_icon(s, self.close_rect)

        # 弹出：setScale(0) → CCScaleTo(0.3s, 1.0)
        k = min(1.0, self.t / POP_TIME) if POP_TIME > 0 else 1.0
        if k <= 0:
            return

        runs = self._runs()
        if not runs:
            return
        # 容器 anchor(0.5,0.5) pos(W*0.5, H*0.5)，缩放绕锚点
        ccx = W * 0.5
        ccy = H * 0.5
        for path, cx, cy in runs:
            im = res.load_img(path)
            if not im:
                continue
            iw = max(1, int(im.get_width() * k))
            ih = max(1, int(im.get_height() * k))
            # 局部坐标 → 以容器中心为轴的缩放 → 屏幕
            sx = ccx + ((cx - 0.0) - ccx) * k
            sy = ccy + (cy - ccy) * k
            # anchor(0,0.5)：左缘在 sx，纵向中心在屏幕 y = H - sy
            s.blit(pygame.transform.smoothscale(im, (iw, ih)), (int(sx), int(H - sy - ih * 0.5)))
