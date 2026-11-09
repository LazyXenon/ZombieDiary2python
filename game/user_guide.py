"""新手引导 —— 原版 MapLayer 里的 UserGuide 系列。

反编译依据：
  MapLayer::initUserGuide      @0x125a90   ← 总调度
  MapLayer::onUserGuide10      @0x125750   ← 第 1 步：欢迎
  MapLayer::onUserGuide11      @0x124a44   ← 第 2 步：指第一个关卡
  MapLayer::onUserGuide20      @0x124c??   ← 第 3 步：枪械升级
  MapLayer::onUserGuide30      @0x124d??   ← 第 4 步：用掉药水
  MapLayer::onUserGuideZK      @0x1245d4   ← 第 5 步：僵尸商店
  MapLayer::onUserGuideSlot    @0x124f07   ← 第 6 步：老虎机

════════════════════════════════════════════════════════════════════
调度（initUserGuide）
════════════════════════════════════════════════════════════════════
  level      = getKeyValue("level", 1)          ← 当前第几天
  ug_day_1/2/3, ug_zombie_shop, ug_slots          ← 各步是否已完成

  ug_day_1 == 0 且 level == 1                       → 步骤 10（欢迎，只播一次）
  ug_day_2 == 0 且 level == 2 且 have_gun_upgrade==0 → 步骤 20（枪械升级）
  ug_day_3 == 0 且 level == 3 且 have_used_potions==0→ 步骤 30（药水）
  ug_slots  == 0 且 level == 2 且 have_spin == 0     → 步骤 Slot（老虎机）
  ug_zombie_shop == 0 且 level > 2 且 get_zk_in_mission > 0 → 步骤 ZK

════════════════════════════════════════════════════════════════════
对话框通用几何（chat_dialog.png 九宫格）
════════════════════════════════════════════════════════════════════
  文本           CCLabelTTF，字号 21.0（1101529088），GBK→UTF8
  文本框 size    每步不同（见 STEPS 的 text_ratio）
  气泡          Combined9Cells，size = (文本宽*1.5, 文本高*bubble_y)
  女孩          girl.png  scale 0.55（1057803469），锚点在气泡局部 (w*0.1, h*girl_y)
  文字          锚点(0,0.5)，pos 气泡局部 (气泡宽*0.25, 气泡高*0.5)
  确定按钮      anchor(1,0)，scale 0.8，pos 气泡局部 (w*0.97, -h*0.07)
  手指          press_hand.png，锚点(0.55, 1.6)，在目标点上下 20px 循环
                （CCMoveTo 0.5s 往返，CCRepeatForever）

各步几何（全部取自反编译的 onUserGuideXX）：

  步   文本框(W,H)      气泡×(宽,高)   气泡anchor  pos(W,H)        女孩y
  10   0.40, 0.15       1.5, 1.7      (0.5,0.0)  (0.52, 0.04)    0.58
  20   0.42, 0.10       1.5, 2.0      (1.0,0.0)  (0.95, 0.50)    —
  30   0.38, 0.15       1.5, 1.7      (1.0,0.0)  (0.95, 0.50)    —
  ZK   0.42, 0.10       1.5, 2.0      (0.5,0.0)  (0.55, 0.07)    —
  Slot 0.37, 0.10       1.5, 1.9      (1.0,0.0)  (1.00, 0.13)    0.65
"""

import pygame

from engine import res
from game.dialog import H, W
from game.ninecell import draw_9cell_atlas


LOGIC = 1.0

CHAT_TEX = "pic/ui/battlefield/chat_dialog.png"
GIRL_TEX = "pic/ui/common/girl.png"
HAND_TEX = "pic/ui/user_guide/press_hand.png"
OK_TEX = "pic/ui/user_guide/bt_ok.png"

GIRL_SCALE = 0.55  # 1057803469
FONT_SIZE = 21  # 1101529088 = 21.0
HAND_SCALE = 1.0
OK_SCALE = 0.8
HAND_BOB = 20.0  # 手指上下摆幅（LOGIC*20）
HAND_PERIOD = 0.5  # CCMoveTo 0.5s
DIM_ALPHA = 0x82  # 步骤 10 的遮罩 v22[3] = -126 = 0x82
# CCLabelTTF 默认颜色是白色；反编译的 onUserGuideXX 里没有 setColor 调用
TEXT_COLOR = (255, 255, 255)

# ---------------------------------------------------------------- 引导文案
# 全部从 libezjoygame.so 的 .rodata 直接读出（GBK），见 byte_34Axxx
TEXT_HELLO = "你好，士兵。我是丽萨，将是你的助理。欢迎来到僵尸世界，期待你在僵尸世界的表现。。。"
TEXT_DAY10 = "这是你的第一次任务，记住他们只是行尸走肉，绝不要心慈手软！"
TEXT_DAY20 = "你第一次的战斗怎么样？我觉得你需要威力更强的枪。让我们升级你的武器。"
TEXT_DAY30 = "收集特殊的基因材料有助于研究僵尸，也能提升你的技能。让我们尝试一下吧。"
TEXT_ZK = "恭喜！你已经收集了一些僵尸材料，你可以使用它们交换一些有用的道具。"
TEXT_SLOT = "不要忘了每天免费使用老虎机的机会。祝你好运！"

# 步骤 id
STEP_HELLO = "hello"
STEP_FIRST = "first_mission"
STEP_GUN = "gun_upgrade"
STEP_POTION = "potion"
STEP_ZK = "zk_shop"
STEP_SLOT = "slot"


class GuideStep:
    """一步引导的静态描述。"""

    def __init__(
        self,
        sid,
        text,
        anchor,
        pos_ratio,
        bubble_y=1.7,
        text_ratio=(0.42, 0.1),
        girl_y=0.65,
        dim=False,
        ok_button=False,
        hand_target=None,
        hand_to_mission=False,
    ):
        self.sid = sid
        self.text = text
        self.anchor = anchor  # (ax, ay)
        self.pos_ratio = pos_ratio  # (rx, ry) → 屏幕比例
        self.bubble_y = bubble_y  # 气泡高 = 文本高 × bubble_y
        self.text_ratio = text_ratio  # 文本框 = (W*rx, H*ry)
        self.girl_y = girl_y  # 女孩 pos 气泡局部 (w*0.1, h*girl_y)
        self.dim = dim  # 是否铺半透明遮罩
        self.ok_button = ok_button  # 是否带「确定」按钮
        self.hand_target = hand_target
        # 手指指向地图上的任务点按钮（反编译 onUserGuide11：手指锚在
        # 任务点按钮中心，anchor(0.55,1.35)，上下 20px 往返）
        self.hand_to_mission = hand_to_mission


STEPS = {
    STEP_HELLO: GuideStep(
        STEP_HELLO,
        TEXT_HELLO,
        (0.5, 0.0),
        (0.52, 0.04),
        bubble_y=1.7,
        text_ratio=(0.40, 0.15),
        girl_y=0.58,
        dim=True,
        ok_button=True,
    ),
    STEP_FIRST: GuideStep(
        STEP_FIRST,
        TEXT_DAY10,
        (0.5, 0.0),
        (0.50, 0.03),
        bubble_y=2.0,
        text_ratio=(0.42, 0.10),
        girl_y=0.65,
        hand_to_mission=True,
    ),
    STEP_GUN: GuideStep(
        STEP_GUN,
        TEXT_DAY20,
        (1.0, 0.0),
        (0.95, 0.50),
        bubble_y=2.0,
        text_ratio=(0.42, 0.10),
        girl_y=0.65,
    ),
    STEP_POTION: GuideStep(
        STEP_POTION,
        TEXT_DAY30,
        (1.0, 0.0),
        (0.95, 0.50),
        bubble_y=1.7,
        text_ratio=(0.38, 0.15),
        girl_y=0.65,
    ),
    STEP_ZK: GuideStep(
        STEP_ZK,
        TEXT_ZK,
        (0.5, 0.0),
        (0.55, 0.07),
        bubble_y=2.0,
        text_ratio=(0.42, 0.10),
        girl_y=0.65,
    ),
    # 老虎机引导（SlotLayer::onUserGuideSlot @0x144a04）：
    #   文本框 contentSize = (W*0.5, H*0.12)，气泡 = 文本框 × (1.0, 1.2)
    #   气泡 anchor(0.5, 0.0)，pos(W*0.4, H*0.2)
    #   ⇒ 气泡屏幕底边 y = 480 - 0.2*480 = 384，高 0.144*480 = 69
    # 而且尺寸也不对（0.37W × 1.9 高）。
    STEP_SLOT: GuideStep(
        STEP_SLOT,
        TEXT_SLOT,
        (0.5, 0.0),
        (0.40, 0.20),
        bubble_y=1.2,
        text_ratio=(0.50, 0.12),
        girl_y=0.8,
    ),
}


def _gbk_to_utf8(text):
    """原版 StringUtil::GBKToUTF8 的等价物：源串本身就是 UTF-8 时原样返回。"""
    return text


class UserGuide:
    """新手引导层。

    app 需要提供 save.d（存档字典）；完成后会写对应的 ug_* 标记。
    """

    def __init__(self, app, step):
        self.app = app
        # step 可以是 id 字符串，也可以是 GuideStep / 任意带 text 的对象
        if isinstance(step, str):
            step = STEPS[step]
        self.step = step
        self.t = 0.0
        self.done = False
        self.ok_rect = None
        self._font = None

    # ---------------------------------------------------------- 存档
    def _d(self):
        save = getattr(self.app, "save", None)
        return getattr(save, "d", {}) if save else {}

    def finish(self):
        """把本步标记写进存档（原版 setKeyValue 后由 onUserGuideXx 推进）。"""
        key = {
            STEP_HELLO: "ug_day_1",
            STEP_FIRST: "ug_day_1",
            STEP_GUN: "ug_day_2",
            STEP_POTION: "ug_day_3",
            STEP_ZK: "ug_zombie_shop",
            STEP_SLOT: "ug_slots",
        }.get(self.step.sid)
        save = getattr(self.app, "save", None)
        if key and save is not None:
            self._d()[key] = 1
            if hasattr(save, "save"):
                save.save()
        self.done = True

    # ---------------------------------------------------------- 交互
    def update(self, dt):
        self.t += dt

    def click(self, pos):
        # 步骤 10 有「确定」按钮；其余步骤点任意处都推进
        if self.step.ok_button:
            self.step = STEPS[STEP_FIRST]
            self.t = 0.0
            save = getattr(self.app, "save", None)
            if save is not None:
                self._d()["ug_day_1"] = 1
                if hasattr(save, "save"):
                    save.save()
            return False
        # 指任务点的步骤：点击要穿透到任务点本身（原版手指锚定的就是
        # 任务点按钮，玩家点手指=点按钮，一次点击同时推进引导并打开关卡）
        if self.step.hand_to_mission:
            self.finish()
            return False
        self.finish()
        return False

    def key_items(self):
        """全键盘：引导是模态的，没有这一条纯键盘玩家会卡死在气泡上。

        原版引导「点任意处推进」，所以焦点框就挂在气泡 / 手指指的位置上，
        回车等于鼠标点那里，行为完全一致。
        """
        if self.ok_rect is not None:
            return [(self.ok_rect, "确定")]
        if self.step.hand_to_mission:
            tgt = self._hand_target()
            if tgt:
                x, y = int(tgt[0]), int(tgt[1])
                return [(pygame.Rect(x - 30, y - 30, 60, 60), "关卡")]
        r = self._bubble_rect()
        return [(pygame.Rect(r.centerx - 70, r.bottom - 46, 140, 36), "继续")]

    # ---------------------------------------------------------- 绘制
    def _text_font(self):
        if self._font is None:
            self._font = pygame.font.SysFont("Microsoft YaHei", FONT_SIZE)
        return self._font

    def _wrap(self, text, max_w):
        """CCLabelTTF(labelWithString, dims) 会自动换行：按字符贪心折行。"""
        font = self._text_font()
        lines, cur = [], ""
        for ch in text:
            if ch == "\n":
                lines.append(cur)
                cur = ""
                continue
            trial = cur + ch
            if font.size(trial)[0] > max_w and cur:
                lines.append(cur)
                cur = ch
            else:
                cur = trial
        if cur:
            lines.append(cur)
        return lines

    def _text_surface(self):
        """文本按 STEPS.text_ratio 的宽度折行（原版 CCLabelTTF 的 dimensions 参数）。

        行距按字号 ×1.15（CCLabelTTF 的行距比 pygame 的 get_linesize 紧），
        否则三行会撑出 1.7× 高的气泡。
        """
        font = self._text_font()
        max_w = W * self.step.text_ratio[0]
        lines = self._wrap(self.step.text, max_w)
        rendered = [font.render(ln, True, TEXT_COLOR) for ln in lines]
        w = max((r.get_width() for r in rendered), default=0)
        step = int(round(FONT_SIZE * 1.15))
        h = step * len(rendered)
        surf = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
        for i, r in enumerate(rendered):
            surf.blit(r, (0, int(step * i + (step - r.get_height()) / 2)))
        return surf

    def _bubble_rect(self):
        """气泡屏幕矩形。

        反编译（onUserGuideXX）：
          文本 contentSize = (W*tx, H*ty)
          气泡 contentSize = (文本宽*1.5, 文本高*bubble_y)
          气泡 anchor/pos 见 STEPS
        cocos: 锚点落在 (px, py)，内容左下 = 锚点 - (ax*bw, ay*bh)
        """
        tw = W * self.step.text_ratio[0]
        th = H * self.step.text_ratio[1]
        bw = tw * 1.5
        bh = th * self.step.bubble_y
        ax, ay = self.step.anchor
        rx, ry = self.step.pos_ratio
        px = W * rx
        py = H * ry
        # cocos: 锚点落在 (px, py)，内容左下 = 锚点 - (ax*bw, ay*bh)
        left = px - ax * bw
        bottom = py - ay * bh
        return pygame.Rect(int(left), int(H - bottom - bh), int(bw), int(bh))

    def draw(self, s):
        # 步骤 10 的 CCLayerColor 遮罩（反编译 v22[3] = 0x82 黑色 51%）：
        # 原版把它挂在**背景容器**下，只压背景。
        # 但模拟器参考帧（emu_map7 / emu_map_noguide / emu_map_step3）显示
        # 三张截图的背景亮度**完全一致** ⇒ 这层遮罩在运行时不可见，
        # 本复刻不画（照抄可见效果）。
        rect = self._bubble_rect()
        draw_9cell_atlas(s, CHAT_TEX, rect, 1.0)

        # 女孩：锚点默认 (0.5,0.5)，pos 气泡局部 (w*0.1, h*0.65)，scale 0.55
        girl = res.load_img(GIRL_TEX)
        if girl:
            gw = max(1, int(girl.get_width() * GIRL_SCALE))
            gh = max(1, int(girl.get_height() * GIRL_SCALE))
            # ★ 左移 22px：girl.png 是 279×256（0.55 ⇒ 153 宽），比原版立绘宽，
            #   按原版 w*0.1 落点她的右沿会顶到 w*0.25 起的正文，
            #   截图里「你第一次的战斗……」首个字被头发压住。
            gx = rect.x + rect.w * 0.1 - 22
            gy = rect.bottom - rect.h * self.step.girl_y
            s.blit(
                pygame.transform.smoothscale(girl, (gw, gh)), (int(gx - gw / 2), int(gy - gh / 2))
            )

        # 文字：anchor(0,0.5)，pos 气泡局部 (w*0.25, h*0.5)
        # 原版 CCLabelTTF 的 dimensions 只是折行宽度上限，高度由内容决定；
        # 文字块超高时以锚点为中心向上下溢出，气泡不裁切。
        txt = self._text_surface()
        tx = rect.x + rect.w * 0.25
        ty = rect.bottom - rect.h * 0.5
        s.blit(txt, (int(tx), int(ty - txt.get_height() / 2)))

        # 步骤 10 的「确定」按钮：anchor(1,0)，pos(气泡宽*0.97, -气泡高*0.07)
        # anchor(1,0) = 贴图**左下角**；cocos y=-h*0.07 在气泡底边下方 7%
        self.ok_rect = None
        if self.step.ok_button:
            ok = res.load_img(OK_TEX)
            if ok:
                ow = max(1, int(ok.get_width() * OK_SCALE))
                oh = max(1, int(ok.get_height() * OK_SCALE))
                ax = rect.x + rect.w * 0.97
                ay = rect.bottom + rect.h * 0.07  # 锚点（屏幕 y，向下）
                r = pygame.Rect(int(ax - ow), int(ay - oh), ow, oh)
                s.blit(pygame.transform.smoothscale(ok, (ow, oh)), r.topleft)
                self.ok_rect = r

        self._draw_hand(s)

    def _hand_target(self):
        """手指目标点。STEP_FIRST 指向地图上的任务点命中框中心。"""
        if self.step.hand_to_mission:
            pts = getattr(self.app, "map_points", None) or []
            if pts:
                p = pts[0]
                x0, y0, x1, y1 = p.rect
                return ((x0 + x1) * 0.5, (y0 + y1) * 0.5)
        return self.step.hand_target

    def _draw_hand(self, s):
        """手指：目标点上下 20px 往返（CCMoveTo 0.5s + RepeatForever）。"""
        tgt = self._hand_target()
        if not tgt:
            return
        hand = res.load_img(HAND_TEX)
        if not hand:
            return
        phase = (self.t % (HAND_PERIOD * 2)) / HAND_PERIOD
        k = phase if phase <= 1.0 else (2.0 - phase)  # 0→1→0 三角波
        hx = tgt[0]
        hy = tgt[1] - HAND_BOB * k
        hw = max(1, int(hand.get_width() * HAND_SCALE))
        hh = max(1, int(hand.get_height() * HAND_SCALE))
        # anchor(0.55, 1.35)：cocos 的 anchor y 向上 ⇒ 参考点在图形底部上方
        # 1.35×高 处，换到屏幕（y 向下）图形顶 = hy + 0.35×高
        s.blit(
            pygame.transform.smoothscale(hand, (hw, hh)), (int(hx - hw * 0.55), int(hy + hh * 0.35))
        )


# ---------------------------------------------------------------- 调度
def pick_step(d):
    """MapLayer::initUserGuide 的分支顺序，返回值或 None。"""
    try:
        level = int(d.get("__guide_level") or 1)
    except (TypeError, ValueError):
        level = 1
    ug1 = int(d.get("ug_day_1", 0))
    ug2 = int(d.get("ug_day_2", 0))
    ug3 = int(d.get("ug_day_3", 0))
    ug_zk = int(d.get("ug_zombie_shop", 0))
    ug_slot = int(d.get("ug_slots", 0))

    if ug1 == 0 and level == 1:
        return STEP_HELLO
    if ug2 == 0 and level == 2 and int(d.get("have_gun_upgrade", 0)) == 0:
        return STEP_GUN
    if ug3 == 0 and level == 3 and int(d.get("have_used_potions", 0)) == 0:
        return STEP_POTION
    if ug_slot == 0 and level == 2 and int(d.get("have_spin", 0)) == 0:
        return STEP_SLOT
    if ug_zk == 0 and level > 2 and int(d.get("get_zk_in_mission", 0)) > 0:
        return STEP_ZK
    return None
