"""老虎机 —— 原版 SlotLayer + SlotColumn + SlotItemDef。

反编译依据：
  SlotLayer::init                    @0x145698
  SlotLayer::initSlots               @0x1454a8
  SlotLayer::initCoinAndCrystal      @0x14??
  SlotLayer::onButtonSpin            @0x143ef0
  SlotLayer::updateSpinButton        @0x147060
  SlotLayer::setPriceNode            @0x144d1c
  SlotColumn::init                   @0x14469c
  SlotColumn::initSlotItems          @0x1444d8
  SlotColumn::getSlotItemNode        @0x1441ac
  SlotColumn::startSpin              @0x143cd8
  SlotColumn::onUpdate               @0x142f30
  SlotColumn::endSpin / spinEndAnimation @0x1437d0 / 0x143628
  asc_37CBF8                         列物品数 = {13, 11, 15}

════════════════════════════════════════════════════════════════════
SlotLayer
════════════════════════════════════════════════════════════════════
  ├─ 背景 pic_bg_1/shop_bg.jpg  pos(W*0.5, H*0.5)  setScale(H/图高)
  ├─ 顶栏 pic/ui/shop/up_bar.png  anchor(0.5,1.0)  pos(W*0.5, H)
  │    setScaleX = W/854（<1.4 → W*1.08/854，<1.6 → W*1.06/854）
  ├─ 根节点 pos(W*0.5,H*0.5) anchor(0.5,0.5) scale = 顶栏缩放比
  │    （1.1 / 1.0 / 1.08 / 1.06 分支，本机 854/480 → 1.0；实际上
  │     this[94] 存的是 1.11，<1.4 分支存 0.9，<1.6 分支存 1.0）
  │    ├─ 按钮 ×3  anchor(0.5,1.0)  scale 0.9
  │    │    pos( W*0.5 + 180*(i-1),  H*0.48 - 145 )
  │    └─ SlotColumn ×3  pos( 同上 x, H*0.48 )
  │         根节点 scale 也套在外层（root）
  ├─ 返回 button_back.png  anchor(0,0)  pos(0, H*0.03)
  └─ 金币/钻石（同成就顶栏）

════════════════════════════════════════════════════════════════════
SlotColumn::init（每种一列）
════════════════════════════════════════════════════════════════════
  slot_col_bg.png  anchor(0.5,0.5)  pos(w/2, h/2)   → 列底
  slot_up_bar.png  pos(w/2, h*0.51)                 → 顶部遮罩
  slot_border.png  pos(0, h*0.51) / pos(w, h*0.51) 第 0 列左贴、第 2 列右贴(flipX)
  EzNode 剪裁窗 contentSize (150, 230)  pos(14, 29)
     每个 item 高 = LOGIC*80，anchor(0.5,0.5)
     第 i 个 y = (h/2 - 一个item高*0.5) + (n-1-i)*80 - i*80 ... 见 initSlotItems

initSlotItems：itemH = LOGIC*80
  v25 = 列宽*0.5
  v24 = 列高 - itemH*0.5
  v26 = (n-1)*itemH             ← 起始偏移
  循环 i: 每个 item pos = (v25, v24 + v26)，然后 v24 -= itemH
  → 第 i 个 item 的 y = (列高 - itemH*0.5) + (n-1-i)*itemH
     n=13 时最上层的 y 最大 = 列高 - 40 + 12*80

════════════════════════════════════════════════════════════════════
getSlotItemNode（SlotItemDef = coin, crystal, name, type, weight）
════════════════════════════════════════════════════════════════════
  coin > 0:
    pic/ui/slot/slot_coin.png   anchor(0.3,0.47)  setScale(0.92)
    文字 "x%d"  getTexFont(0)  scale 0.9  pos(-cw*0.3, -ch*0.1)  anchor(0,0)
  crystal > 0:
    pic/ui/slot/slot_cystal.png anchor(0.3,0.43)  setScale(0.92)
    文字 "x%d"  getTexFont(0)  scale 0.9  pos(-cw*0.4, -ch*0.1)  anchor(0,0)
  否则:
    name == "enhance_potion" → pic/ui/shop/enhance_potion.png
    否则                     → pic/ui/shop/ability_<name>.png
    anchor(0.8,0.5)  setScale(0.8)
    文字 "x%d"(count) getTexFont(0) scale 1.1 pos(w, h*0.5) anchor(0,0.5)

════════════════════════════════════════════════════════════════════
旋转物理（startSpin + onUpdate）
════════════════════════════════════════════════════════════════════
startSpin:
  v8 = curIndex - targetIndex，取模到 ±n/2
  distance = itemH*n*4 + itemH*v8
  speed = -350          (this[81]，往负方向滚)
  accel_up  = 2100      (this[77])
  accel_dn  = -2300     (this[76])
  stopSpeed = -1500     (this[75])
  endSpeed  = 400       (this[78])
  overshoot = 25        (this[74])
  flags: this[316]=1(加速) 317=0(减速) 318=1 319=1(spinning) 320=0

onUpdate(dt):
  加速段：若 speed < accel_up，则位移 += (stopSpeed*0.5*dt)*dt，speed += stopSpeed*dt
          （stopSpeed 实际是加速率，因为它是负值 → 越滚越快）
  当 distance 走完 80% → 切换减速：位移 = speed*dt + (accel_dn*0.5*dt)*dt，
          speed += accel_dn*dt，直到 speed >= endSpeed*1.2 时停住
  总位移超过 distance + overshoot 时截断，所有 item 各跑一个
  CCMoveBy(0.15s, (0, +overshoot)) 回弹，再 CCMoveBy 0.15s，然后 endSpin
"""

import math

import pygame

from engine import gridfont, res
from game.dialog import H, W, default_close_rect, draw_close_icon


LOGIC = 1.0

BG_TEX = "pic_bg_1/shop_bg.jpg"
TOP_BAR_TEX = "pic/ui/shop/up_bar.png"
BACK_TEX = "pic/ui/shop/button_back.png"
COIN_TEX = "pic/ui/common/coin.png"
CRYSTAL_TEX = "pic/ui/common/crystal.png"

COL_BG_TEX = "pic/ui/slot/slot_col_bg.png"
COL_BAR_TEX = "pic/ui/slot/slot_up_bar.png"
COL_BORDER_TEX = "pic/ui/slot/slot_border.png"
SLOT_COIN_TEX = "pic/ui/slot/slot_coin.png"
SLOT_CRYSTAL_TEX = "pic/ui/slot/slot_cystal.png"
SPIN_BTN_TEX = "pic/ui/slot/button_spin.png"
TEXT_SPIN_TEX = "pic/ui/slot/text_spin.png"
TEXT_FREE_TEX = "pic/ui/slot/text_free_spin.png"
POTION_TEX = "pic/ui/shop/enhance_potion.png"

FONT_SCORE = 0  # getTexFont(0) = score_white.png（格子文字）
FONT_COIN = 1
FONT_CRYSTAL = 3

ITEM_H = LOGIC * 80.0  # this[72] = LOGIC*80
CLIP_W = LOGIC * 150.0  # EzNode contentSize
CLIP_H = LOGIC * 230.0
CLIP_X = LOGIC * 14.0
CLIP_Y = LOGIC * 29.0

SPEED0 = -350.0 * LOGIC  # this[81]：初速（向上，负）
ACCEL_UP = 2100.0 * LOGIC  # this[77]：加速段的目标速度
ACCEL_DN = -2300.0 * LOGIC  # this[76]：减速段的加速度
STOP_SPEED = 1500.0 * LOGIC  # this[75]：加速段的加速度（正值！）
END_SPEED = 400.0 * LOGIC  # this[78]：收尾速度
OVERSHOOT = 25.0 * LOGIC  # this[74]：过冲量

COL_COUNTS = (13, 11, 15)  # asc_37CBF8

# 根节点 contentSize = **背景图 shop_bg.jpg 的 contentSize**（反编译 SlotLayer::init
# 里 `v41(根节点, v5->getContentSize())`，v5 是 pic_bg_1/shop_bg.jpg 的 sprite）。
# 240*0.48=115 被算成 480*0.48=230，整个老虎机版面下移 115 逻辑像素，
# 三个 spin 按钮被推到屏幕最底部、被引导气泡盖住，看起来像「按钮没了」。
# 根节点 contentSize = 背景 sprite 的 contentSize。
# 反编译 SlotLayer::init 里 `root.setContentSize(bg->getContentSize())`，
# 而背景是 `shop_bg.jpg` 被 setScale(H/图高) 拉满全屏的 EzSprite ——
# EzSprite::getContentSize 返回的是**缩放后**的显示尺寸，也就是 854×480。
# 看不出问题；高度则让根原点下移 120px，整个老虎机版面被抬高 5px，
# 三列的格子行、引导气泡、按钮都和原版对不上。
ROOT_W = 854.0
ROOT_H = 480.0

# ------------------------------------------------------------------ 物品表
# SlotItemDef(coin, crystal, name, type, weight)
# type 1 = 直接进背包；type 2 = 进装备/技能（本复刻只做展示，type 存档不实现）
COIN_TABLE = [
    (500, 0, "", 0, 800),
    (600, 0, "", 0, 800),
    (800, 0, "", 0, 800),
    (1200, 0, "", 0, 800),
    (1500, 0, "", 0, 500),
    (2000, 0, "", 0, 100),
    (5000, 0, "", 0, 20),
    (10000, 0, "", 0, 10),
    (20000, 0, "", 0, 5),
    (100000, 0, "", 0, 1),
    (0, 1, "", 0, 800),
    (0, 2, "", 0, 500),
    (0, 5, "", 0, 50),
]

CRYSTAL_TABLE = [
    (0, 2, "", 0, 800),
    (0, 3, "", 0, 600),
    (0, 4, "", 0, 600),
    (0, 6, "", 0, 600),
    (0, 8, "", 0, 200),
    (0, 10, "", 0, 50),
    (0, 15, "", 0, 20),
    (0, 20, "", 0, 10),
    (0, 50, "", 0, 5),
    (0, 100, "", 0, 2),
    (0, 500, "", 0, 1),
]

ITEM_TABLE = [
    (0, 0, "enhance_potion", 1, 40),
    (0, 0, "enhance_potion", 2, 20),
    (0, 0, "airstrike", 1, 50),
    (0, 0, "airstrike", 2, 25),
    (0, 0, "hp_1", 2, 50),
    (0, 0, "hp_2", 2, 25),
    (0, 0, "shield_1", 2, 50),
    (0, 0, "shield_2", 2, 25),
    (0, 0, "power_1", 2, 40),
    (0, 0, "power_2", 2, 20),
    (0, 0, "speed_1", 2, 50),
    (0, 0, "speed_2", 2, 25),
    (0, 0, "mech_7", 2, 16),
    (0, 0, "fly_1", 2, 30),
    (0, 0, "fly_2", 2, 15),
]

TABLES = (COIN_TABLE, CRYSTAL_TABLE, ITEM_TABLE)

# 转一次的价格（反编译 SlotLayer::onButtonSpin @0x141? 读 dword_48EB34）：
#   v18 = &dword_48EB34[2 * 列号]
#   v18[0] = 金币价，v18[1] = 钻石价
# .bss 静态初值（sub_141DB0 尾部）：
#   dword_48EB34[0] = 1000   dword_48EB38 = 0
#   dword_48EB3C    = 0      dword_48EB44 = 0
# 只给第 0 列写了 1000 金币，其余保持 0 是「未初始化」的默认值 ——
# 玩家反馈「难道其他两箱酒不要钱吗？全是免费抽的」）。
# 原版正常运行显然不会免费：三列用的是同一个 button_spin.png，
# 价格由 setPriceNode 打印在按钮上（a3=金币 / a4=钻石），
# 数值必须为正才会画 —— 三列都画了价格才说明三列都有价。
# 这里按「同档位、钻石递增」的常见设计给出 1000 / 1200 / 1500 金币。
SPIN_PRICES = [(1000, 0), (1200, 0), (1500, 0)]


def _ratio():
    return (W / float(H)) if H else 1.0


def _back_scale():
    r = _ratio()
    if r < 1.4:
        return 0.64
    if r < 1.6:
        return 0.73
    if r < 1.7:
        return 0.80
    return 0.85


def _topbar_scale():
    bar = res.load_img(TOP_BAR_TEX)
    if not bar:
        return 1.0
    r = _ratio()
    if r < 1.4:
        return (W * 1.08) / bar.get_width()
    if r < 1.6:
        return (W * 1.06) / bar.get_width()
    return W / float(bar.get_width())


def _root_scale():
    """this[94]：根节点缩放。

    反编译：默认写 1066275963 = 1.11f；
    <1.4 → 1063675494 = 0.9f；<1.6 → 1065353216 = 1.0f；
    其余分支用 W/顶栏宽（= 1.0）。
    """
    r = _ratio()
    if r < 1.4:
        return 0.9
    if r < 1.6:
        return 1.0
    bar = res.load_img(TOP_BAR_TEX)
    if bar:
        return W / float(bar.get_width())
    return 1.11


def _weighted_pick(table, rng):
    """SlotColumn::getSpinToIndex(int, table, n)：按权重抽一项。"""
    total = sum(row[4] for row in table)
    r = rng.randrange(total)
    for i, row in enumerate(table):
        if r < row[4]:
            return i
        r -= row[4]
    return 1


class _Column:
    """一列（原版 SlotColumn）。"""

    def __init__(self, layer, index):
        self.layer = layer
        self.index = index
        self.n = COL_COUNTS[index]
        self.count = self.n
        self.items = TABLES[index][: self.n]
        self.offset = 0.0  # 累计向下滚动的距离 S（cocos 单位）
        self.cur = 0  # 当前停在的 item 编号（this[69]）
        self.target = 0  # 本次要停到的编号（this[70]）
        self.spinning = False
        self.dist = 0.0  # 本次要滚动的总距离（this[82]）
        self.travelled = 0.0  # 已滚距离（this[83]）
        self.speed = SPEED0
        self.accel_up = False
        self.decel = False
        self.settle = 0.0  # 回弹计时

    # ---- 开始 ----
    def start(self, rng):
        if self.spinning:
            return False
        self.target = _weighted_pick(self.items, rng)
        d = self.cur - self.target
        half = self.n >> 1
        if d > half:
            d -= self.n
        elif d < -half:
            d += self.n
        self.dist = ITEM_H * self.n * 4.0 + ITEM_H * d
        self.travelled = 0.0
        self.speed = SPEED0
        self.accel_up = True
        self.decel = False
        self.spinning = True
        self.settle = 0.0
        return True

    # ---- 帧推进（SlotColumn::onUpdate @0x142f30）----
    def update(self, dt):
        """逐帧照抄原版：

        this[81]=speed, this[82]=dist, this[83]=travelled,
        this[75]=STOP_SPEED(+1500 加速率), this[77]=ACCEL_UP(+2100 目标速度),
        this[76]=ACCEL_DN(-2300 减速率), this[78]=END_SPEED(+400 收尾),
        this[74]=OVERSHOOT(+25)
        """
        if not self.spinning:
            return
        speed = self.speed
        move = speed * dt

        # 加速段：speed < ACCEL_UP 时按 STOP_SPEED 加
        if self.accel_up:
            if speed < ACCEL_UP:
                move += (STOP_SPEED * 0.5 * dt) * dt
                speed = speed + STOP_SPEED * dt
                if speed >= ACCEL_UP:
                    self.accel_up = False
            if speed >= ACCEL_UP:
                self.accel_up = False

        # 走了 80% 就切减速
        if not self.decel and self.travelled >= self.dist * 0.8:
            self.decel = True
            self.accel_up = False

        if self.decel:
            move = speed * dt + (ACCEL_DN * 0.5 * dt) * dt
            speed = speed + ACCEL_DN * dt
            if speed < END_SPEED * 1.2:
                self.decel = False
                if speed < END_SPEED:
                    speed = END_SPEED

        self.speed = speed

        limit = self.dist + OVERSHOOT
        if self.travelled + move >= limit:
            self.offset += limit - self.travelled  # 补上本帧剩余位移
            self.travelled = limit
            self.spinning = False
            self.cur = self.target
            # 停下后对齐：让第 target 个 item 正好落在第 0 个 item 的原位
            # （item i 的屏幕 y = 基准 - i*itemH - shift，故 shift ≡ -target*itemH）
            span = ITEM_H * self.n
            want = (-self.target * ITEM_H) % span
            self.offset = want + span * round((self.offset - want) / span)
            self.settle = 0.15
            # 停下下来：发奖（原版 SlotColumn::endSpin →
            # SlotLayer → SlotColumn::setSpinResult @0x145230）
            self.layer.on_column_stopped(self)
            return
        self.travelled += move
        self.offset += move  # 累计滚动距离（正数）

    # ---- 是否已停 ----
    def idle(self):
        return not self.spinning

    # ---- 绘制 ----
    def draw(self, s, ox, oy, k=1.0):
        """ox, oy = 列内容左下角（屏幕坐标）；k = 根节点缩放。

        原版 onUpdate：每个 item 的 y 每帧减 `move`，若 < -itemH 则 +itemH*n
        循环。这里等价于把累计位移对 n*itemH 取模。
        """
        w = self.layer.col_w * k
        h = self.layer.col_h * k
        span = ITEM_H * k * self.n
        # 剪裁窗：相对列内容左下 (14, 29)，尺寸 150×230
        clip = pygame.Rect(
            int(ox + CLIP_X * k), int(oy - (CLIP_Y + CLIP_H) * k), int(CLIP_W * k), int(CLIP_H * k)
        )
        s.set_clip(clip)
        # item i 初始 y = (h - itemH/2) - i*itemH；滚动量 S 使所有 y 下移 S，
        # 低于 -itemH/2 的绕回顶部（等价对 n*itemH 取模）
        shift = (self.offset * k) % span if span else 0.0
        for i in range(self.n):
            cy = (h - ITEM_H * k * 0.5) - i * ITEM_H * k - shift
            if cy < -ITEM_H * k * 0.5:
                cy += span
            self._draw_item(s, self.items[i], ox + w * 0.5, oy - cy, k)
        s.set_clip(None)

    def _draw_item(self, s, item, cx, cy, k=1.0):
        coin, crystal, name, typ, _wt = item
        if coin > 0:
            self._draw_money(s, SLOT_COIN_TEX, coin, cx, cy, 0.3, 0.47, -0.3, k)
        elif crystal > 0:
            self._draw_money(s, SLOT_CRYSTAL_TEX, crystal, cx, cy, 0.3, 0.43, -0.4, k)
        else:
            self._draw_powerup(s, name, typ, cx, cy, k)

    def _draw_money(self, s, path, count, cx, cy, ax, ay, tx, k=1.0):
        """getSlotItemNode 的金币/钻石分支。

        图标 slot_coin / slot_cystal：EzSprite，setScale(0.92)，
        anchor 分别为 (0.3,0.47) / (0.3,0.43)，锚点落在 item 节点原点。

        数字是**该 sprite 的子节点**：anchor(0,0)、setScale(0.9)、
        pos(w*tx, -h*0.1) —— 子节点坐标以**父 sprite 的左下角**为原点，
        彻底分开；玩家看到就是「道具数量和图像不在一起」。

        数值按模拟器参考帧（emu feat/slot.png 第一格）标定：
          · 数字左边缘 = 图标左边缘 − 0.30×图标宽（金币）/ −0.40×（钻石）
          · 数字底边 ≈ 图标底边 + 0.10×图标高
        """
        img = res.load_img(path)
        if not img:
            return
        sc = 0.92 * k
        w, h = img.get_size()
        iw = max(1, int(w * sc))
        ih = max(1, int(h * sc))
        # 图标矩形（锚点在 (cx, cy)）
        sx = cx - ax * iw
        sy = cy - (1.0 - ay) * ih
        s.blit(pygame.transform.smoothscale(img, (iw, ih)), (int(round(sx)), int(round(sy))))

        font = gridfont.get_font(FONT_SCORE)
        if font:
            tlx = sx + tx * iw
            tby = sy + ih * 1.10
            font.draw(s, "x%d" % count, tlx, tby, 0.9 * k, align=(0.0, 1.0))

    def _draw_powerup(self, s, name, typ, cx, cy, k=1.0):
        """getSlotItemNode 的第三分支。

        enhance_potion → pic/ui/shop/enhance_potion.png
        其他          → pic/ui/shop/ability_<name>.png
        setScale(0.8)，anchor(0.8,0.5)。
        数字 "x%d"（数字 = SlotItemDef 的 type 字段）是 sprite 子节点：
          anchor(0,0.5)  setScale(1.1)  pos(w, h*0.5)
        """
        path = POTION_TEX if name == "enhance_potion" else "pic/ui/shop/ability_%s.png" % name
        img = res.load_img(path)
        if not img:
            return
        sc = 0.8 * k
        w, h = img.get_size()
        iw = max(1, int(w * sc))
        ih = max(1, int(h * sc))
        left = cx - w * sc * 0.8
        bottom = cy + h * sc * 0.5
        s.blit(pygame.transform.smoothscale(img, (iw, ih)), (int(left), int(bottom - ih)))

        font = gridfont.get_font(FONT_SCORE)
        if font:
            tlx = left + sc * w
            tcy = bottom - sc * (h * 0.5)
            font.draw(s, "x%d" % typ, tlx, tcy, 1.1 * k, align=(0.0, 0.5))


class SlotPanel:
    """老虎机（原版 SlotLayer）。"""

    def __init__(self, app):
        self.app = app
        self.done = False
        self.back_rect = None
        self.close_rect = default_close_rect(True)
        self.spin_rects = []
        # 老虎机引导（原版 SlotLayer::initUserGuide @0x144ecc）：
        # 读存档 "ug_slots"，值为 1 时在**老虎机界面内**弹引导。
        # 地图层 MapLayer::initUserGuide @0x125a90 里的引导是 ug_slots == 0 时弹，
        # 两者不同（原版就是这样）。我们开老虎机时先把地图层的引导收起来。
        self.guide = None
        d = getattr(getattr(app, "save", None), "d", {}) or {}
        if int(d.get("ug_slots", 0) or 0) == 0:
            from game.user_guide import STEP_SLOT, UserGuide

            self.guide = UserGuide(app, STEP_SLOT)
        self.rng = __import__("random").Random(20261103)
        self.free_spins = [int(d.get("free_spin_%d" % i, 0) or 0) for i in range(3)]
        # ★ 跨天检测：面板开着时到了第二天，免费次数要立刻恢复。
        #   原版靠服务器 push + clearDailyTaskInfo 重置，
        #   本地改成按「一年中的第几天」判定（对齐 AppUtils::getYearDays）。
        from game.daily_timer import DailyTimer

        self._timer = DailyTimer(on_reset=self._reset_free_spins)
        self._refresh_free_spins()
        self.last_gain = (0, 0, "", 0)
        self.gain_text = ""
        self.gain_t = 0.0
        self._btn_rects = None
        self._layout()
        btn = res.load_img(SPIN_BTN_TEX)
        self._btn_size = btn.get_size() if btn else (185.0, 61.0)
        self.cols = [_Column(self, i) for i in range(3)]

    def _layout(self):
        bg = res.load_img(COL_BG_TEX)
        self.col_w, self.col_h = bg.get_size() if bg else (184.0, 273.0)

    # ---------------------------------------------------------- 免费次数
    def _refresh_free_spins(self):
        """从存档重新读 free_spin_0..2（面板打开时 / 跨天后）。"""
        d = getattr(getattr(self.app, "save", None), "d", {}) or {}
        self.free_spins = [int(d.get("free_spin_%d" % i, 0) or 0) for i in range(3)]

    def _reset_free_spins(self):
        """跨天：把三列的免费次数恢复成 1（原版 g_IsClearFreeSpin 分支）。"""
        save = getattr(self.app, "save", None)
        if save is None:
            return
        for i in range(3):
            save.d["free_spin_%d" % i] = 1
        if hasattr(save, "save"):
            save.save()
        self._refresh_free_spins()

    # ---------------------------------------------------------- 键盘
    def key_items(self):
        """全键盘：引导在场时焦点跟随引导，避免回车被它吞掉；
        全局关闭叉号仍独立生效，可随时退出老虎机。"""
        out = []
        if self.close_rect is not None:
            out.append((self.close_rect, "关闭"))
        if self.guide is not None:
            fn = getattr(self.guide, "key_items", None)
            try:
                return out + (fn() if callable(fn) else [])
            except Exception:
                return out
        if self.back_rect is None:
            self.back_rect = self._back_hit_rect()
        if self.back_rect:
            out.append((self.back_rect, "返回"))
        for i, r in enumerate(self._spin_button_rects()):
            out.append((r, "抽奖%d" % (i + 1)))
        return out

    # ---------------------------------------------------------- 交互
    def update(self, dt):
        for c in self.cols:
            c.update(dt)
        # 跨天 → 免费次数恢复（对齐原版每日重置）
        self._timer.tick()
        if self.guide is not None:
            self.guide.update(dt)
            if self.guide.done:
                self.guide = None
        if self.gain_t > 0:
            self.gain_t -= dt
            if self.gain_t <= 0:
                self.gain_text = ""

    def click(self, pos):
        if self.close_rect and self.close_rect.collidepoint(pos):
            self.done = True
            return True
        if self.guide is not None:
            if self.guide.click(pos):
                self.guide = None
            return True
        if self.back_rect and self.back_rect.collidepoint(pos):
            self.done = True
            return True
        rects = self.spin_rects
        if not rects:
            rects = self._spin_button_rects()
        for i, r in enumerate(rects):
            if r.collidepoint(pos):
                self.spin(i)
                return True
        return False

    def _spin_button_rects(self):
        """按钮的点击区（不依赖已经 draw 过）。"""
        if self._btn_rects is not None:
            return self._btn_rects
        positions, k = self._column_positions()
        sc = 0.9 * k
        bw = max(1, int(self._btn_size[0] * sc))
        bh = max(1, int(self._btn_size[1] * sc))
        rects = []
        for cx, top_y in positions:
            rects.append(pygame.Rect(int(cx - bw / 2), int(top_y), bw, bh))
        self._btn_rects = rects
        return rects

    def on_column_stopped(self, col):
        """一列停稳后发奖（原版 SlotColumn::setSpinResult @0x145230）。

        原版语义（all_merged.c:93672）：
          ① coin &gt 0    → user_coin += coin
          ② crystal &gt;0 → user_crystal += crystal
          ③ name == "enhance_potion" → en_potion_count += typ
          ④ 其它技能名      → 存档[name] += typ

        停下后还会播飞金币动画（SlotLayer::flyCoinOrCrystal）并刷新
        顶栏的金币/钻石计数（updateCoinAndCrystal）。
        """
        item = col.items[col.cur % len(col.items)] if col.items else None
        if item is None:
            return
        coin, crystal, name, typ, _wt = item
        save = getattr(self.app, "save", None)
        if save is None:
            return
        gained_coin = gained_crystal = 0
        if coin > 0:
            save.add_coins(coin)
            gained_coin = coin
        if crystal > 0:
            save.add_crystals(crystal)
            gained_crystal = crystal
        if name == "enhance_potion":
            save.add_potions(typ)
        elif name and typ:
            # 技能数量：存档[name] += typ
            abilities = save.d.setdefault("abilities", {})
            abilities[name] = int(abilities.get(name, 0) or 0) + typ
        save.save()
        # 停列发奖：金币/钻石飞进顶栏账户（原版 flyCoinOrCrystal）
        fly = getattr(self.app, "reward_fly", None)
        if fly is not None and (gained_coin or gained_crystal):
            r = getattr(col, "rect", None)
            x0, y0 = (r.centerx, r.centery) if r else (427, 250)
            fly.spawn(x0, y0, int(gained_coin), int(gained_crystal))
        self.last_gain = (gained_coin, gained_crystal, name, typ)
        self.gain_text = self._gain_label(item)
        self.gain_t = 2.2

    @staticmethod
    def _gain_label(item):
        coin, crystal, name, typ, _wt = item
        if coin > 0:
            return "金币 x%d" % coin
        if crystal > 0:
            return "钻石 x%d" % crystal
        if name == "enhance_potion":
            return "升级药水 x%d" % typ
        if name:
            return "%s x%d" % (name, typ)
        return ""

    def spin(self, i):
        col = self.cols[i]
        if not col.idle():
            return False
        save = getattr(self.app, "save", None)
        if self.free_spins[i] > 0:
            self.free_spins[i] -= 1
            if save is not None:
                # 原版扣完立刻把 free_spin_<i> 写回 0（onButtonSpin 里
                # EzGameData 的 map["free_spin_i"] = 0），否则重开面板又能白嫖
                save.d["free_spin_%d" % i] = 0
                if hasattr(save, "save"):
                    save.save()
        else:
            coin, crystal = SPIN_PRICES[i]
            if save:
                if coin and not save.spend_coins(coin):
                    return False
                if crystal and not save.spend_crystals(crystal):
                    if coin:
                        save.add_coins(coin)
                    return False
        return col.start(self.rng)

    # ---------------------------------------------------------- 绘制
    def draw(self, s):
        self._draw_bg(s)
        self._draw_topbar(s)
        self._draw_columns(s)
        self._draw_back(s)
        self._draw_gain(s)
        if self.guide is not None:
            self.guide.draw(s)
        draw_close_icon(s, self.close_rect)

    def _draw_gain(self, s):
        """中奖提示（转完后飞金币的动画时展示得到了什么）。

        原版是金币/钻石飞向顶栏计数器的动画（flyCoinOrCrystal），
        我们没有那套精细动画，用一行字告知结果。
        """
        if self.gain_t <= 0 or not self.gain_text:
            return
        f = gridfont.get_font(FONT_COIN)
        if not f:
            return
        text = self.gain_text
        size = f.text_size(text, 1.8)
        x = int(W * 0.5 - size[0] / 2)
        # 放在列底下方、启动按钮上方的空白处
        # （列底约在 0.72H，按钮约在 0.82H）
        y = int(H * 0.765)
        f.draw(s, text, x, y, 1.8, align=(0.0, 0.5))

    def _draw_bg(self, s):
        bg = res.load_img(BG_TEX)
        if not bg:
            return
        bw, bh = bg.get_size()
        sc = H / float(bh)
        w = max(1, int(bw * sc))
        h = max(1, int(bh * sc))
        s.blit(
            pygame.transform.smoothscale(bg, (w, h)), (int(W * 0.5 - w / 2), int(H * 0.5 - h / 2))
        )

    def _draw_topbar(self, s):
        bar = res.load_img(TOP_BAR_TEX)
        if not bar:
            return
        bw, bh = bar.get_size()
        sc = _topbar_scale()
        w = max(1, int(bw * sc))
        h = max(1, int(bh * sc))
        bx = int(W * 0.5 - w / 2)
        s.blit(pygame.transform.smoothscale(bar, (w, h)), (bx, 0))

        # 标题：老虎机页没有独立标题图，原版只挂金币/钻石
        self._draw_currency(s, bx, bh, sc)
        self._draw_free_countdown(s, bx, bh, sc)

    def _draw_free_countdown(self, s, bx, bh, sc):
        """画「免费抽 x3 · 距下次重置 05:23:41」。

        ★ 原版靠服务器 push 通知每日刷新，没有倒计时 UI。
          这里按「距下一个自然日 00:00」本地计算。
        地图入口那个按钮贴着屏幕右缘、原版参考帧里就被裁掉一半，
        倒计时放那儿根本看不清 —— 所以只在这里（老虎机面板）显示。
        """
        from game.daily_timer import countdown_text
        from game.dialog import text as draw_text

        free = sum(1 for v in self.free_spins if v > 0)
        # ★ 用系统字体而不是 gridfont —— gridfont 是位图字体
        #   （pic/fonts/score_white.png），里面没有中文，
        #   画「免费抽」会是一片空白。
        # countdown_text() 自带「距下次重置」前缀，别再拼一遍
        txt = "免费抽 x%d   %s" % (free, countdown_text())
        f = pygame.font.SysFont("Microsoft YaHei", 15, bold=True)
        t = f.render(txt, True, (255, 226, 150))
        tw, th = t.get_width(), t.get_height()
        # 放在顶栏左侧（货币在右侧），避开中间的槽位区
        x = bx + 16
        y = int(bh * sc * 0.5)
        # 先铺一层暗底，保证字在浅色顶栏上读得清
        pad = 7
        bg = pygame.Surface((tw + pad * 2, th + pad * 2), pygame.SRCALPHA)
        bg.fill((10, 8, 20, 180))
        s.blit(bg, (int(x - pad), int(y - th / 2 - pad)))
        s.blit(t, (int(x), int(y - th / 2)))

    def _draw_currency(self, s, bx, bh, sc):
        coin = res.load_img(COIN_TEX)
        crystal = res.load_img(CRYSTAL_TEX)
        if not coin or not crystal:
            return
        save = getattr(self.app, "save", None)
        d = getattr(save, "d", {}) if save else {}
        n_coin = int(d.get("coins", 0))
        n_crys = int(d.get("crystals", 0))
        k = 0.7
        cw, ch = coin.get_size()
        xw, _xh = crystal.get_size()
        f1 = gridfont.get_font(FONT_COIN)
        f2 = gridfont.get_font(FONT_CRYSTAL)
        t1, t2 = str(n_coin), str(n_crys)
        n1 = f1.text_size(t1, 1.6)[0] if f1 else 0
        gap = cw * 0.1
        x1 = cw + gap
        x48 = x1 + n1 + cw
        x49 = x48 + xw + gap
        left = bx + 854.0 * 0.53 * sc
        oy = bh * sc - (bh * 0.64 - ch * 0.5) * sc

        def img_at(img, cxl, cyl):
            iw = max(1, int(img.get_width() * k))
            ih = max(1, int(img.get_height() * k))
            s.blit(
                pygame.transform.smoothscale(img, (iw, ih)),
                (int(left + cxl * k - iw / 2), int(oy - cyl * k - ih / 2)),
            )

        img_at(coin, cw * 0.5, ch * 0.5)
        if f1:
            f1.draw(s, t1, left + x1 * k, oy - ch * 0.5 * k, 1.6 * k, align=(0.0, 0.5))
        img_at(crystal, x48 + xw * 0.5, ch * 0.5)
        if f2:
            f2.draw(s, t2, left + x49 * k, oy - ch * 0.5 * k, 1.6 * k, align=(0.0, 0.5))

    def _column_positions(self):
        """三列 + 三个按钮的屏幕坐标。

        原版根节点 pos(W*0.5,H*0.5) anchor(0.5,0.5) scale=this[94]，
        列 i：pos(854*0.5 + LOGIC*180*(i-1), 480*0.48) anchor(0.5,0.5)；
        按钮 i：anchor(0.5,1.0) scale 0.9，pos(同 x, 480*0.48 - LOGIC*145)。
        抽出来给 click 用 —— 以前按钮的点击区只在 draw 时才填，
        第一次点击前如果没 draw 过就永远点不到。
        """
        k = _root_scale()
        rw, rh = ROOT_W, ROOT_H
        rx0 = W * 0.5 - rw * 0.5 * k
        ry0 = H * 0.5 - rh * 0.5 * k
        out = []
        for i in range(3):
            lx = rw * 0.5 + LOGIC * 180.0 * (i - 1)
            cx_w = rx0 + lx * k
            by_w = ry0 + (rh * 0.48 - LOGIC * 145.0) * k
            out.append((cx_w, H - by_w))
        return out, k

    def _draw_columns(self, s):
        """SlotLayer::initSlots：三列 + 三个按钮，都在根节点里。

        根节点 pos(W*0.5,H*0.5) anchor(0.5,0.5) scale=this[94]，
        contentSize = 背景 sprite 的 contentSize（设计单位 854×480）。
        列 i：pos(854*0.5 + LOGIC*180*(i-1), 480*0.48) anchor(0.5,0.5)。
        按钮 i：anchor(0.5,1.0) scale 0.9，pos(同 x, 480*0.48 - LOGIC*145)。
        """
        k = _root_scale()
        rw, rh = ROOT_W, ROOT_H
        rx0 = W * 0.5 - rw * 0.5 * k
        ry0 = H * 0.5 - rh * 0.5 * k  # cocos y 向上
        self.spin_rects = []
        for i in range(3):
            lx = rw * 0.5 + LOGIC * 180.0 * (i - 1)
            ly = rh * 0.48
            # 列 anchor(0.5,0.5)，contentSize = 列底图尺寸
            cx_w = rx0 + lx * k
            cy_w = ry0 + ly * k
            ox = cx_w - self.col_w * k * 0.5  # 内容左下（屏幕 x）
            oy = (H - cy_w) + self.col_h * k * 0.5  # 内容底边（屏幕 y）
            self._draw_column_frame(s, i, ox, oy, k)
            self.cols[i].draw(s, ox, oy, k)
            # 按钮：anchor(0.5,1.0)，pos y = 480*0.48 - 145（cocos）
            by_w = ry0 + (rh * 0.48 - LOGIC * 145.0) * k
            self._draw_spin_button(s, i, cx_w, H - by_w, k)

    def _draw_win_line(self, s, rx0, ry0, rw, rh, k):
        """中奖行指示线 —— **原版没有这个东西，整条禁用**。

        早先这里画一条黄色虚线标出中奖格。原版（feat/slot.png 参考帧）三列
        「按钮设计的和我原版的一样 同风格」，多加的线属于自造装饰，去掉。

        保留方法体做文档，但不再被调用；判定中奖的逻辑在 _draw_column 里
        独立进行，不依赖这条线。
        """
        return

    def _draw_column_frame(self, s, i, ox, oy, k):
        cw = self.col_w * k
        ch = self.col_h * k
        bg = res.load_img(COL_BG_TEX)
        if bg:
            s.blit(pygame.transform.smoothscale(bg, (int(cw), int(ch))), (int(ox), int(oy - ch)))
        up = res.load_img(COL_BAR_TEX)
        if up:
            uw = max(1, int(up.get_width() * k))
            uh = max(1, int(up.get_height() * k))
            # pos(w*0.5, h*0.51) anchor(0.5,0.5)
            ux = ox + cw * 0.5
            uy = oy - ch * 0.51
            s.blit(pygame.transform.smoothscale(up, (uw, uh)), (int(ux - uw / 2), int(uy - uh / 2)))
        if i in (0, 2):
            bd = res.load_img(COL_BORDER_TEX)
            if bd:
                bw = max(1, int(bd.get_width() * k))
                bh = max(1, int(bd.get_height() * k))
                im = pygame.transform.smoothscale(bd, (bw, bh))
                if i == 2:
                    im = pygame.transform.flip(im, True, False)
                # 第 0 列 pos(0, h*0.51)，第 2 列 pos(w, h*0.51)，anchor(0.5,0.5)
                bx = ox if i == 0 else ox + cw
                by = oy - ch * 0.51
                s.blit(im, (int(bx - bw / 2), int(by - bh / 2)))

    def _draw_spin_button(self, s, i, cx, top_y, k):
        """按钮贴图 anchor(0.5,1.0) scale 0.9 —— 顶边落在 top_y。"""
        btn = res.load_img(SPIN_BTN_TEX)
        if not btn:
            return
        sc = 0.9 * k
        bw = max(1, int(btn.get_width() * sc))
        bh = max(1, int(btn.get_height() * sc))
        rect = pygame.Rect(int(cx - bw / 2), int(top_y), bw, bh)
        s.blit(pygame.transform.smoothscale(btn, (bw, bh)), rect.topleft)
        self.spin_rects.append(rect)

        # free_spin_<i> > 0 → text_free_spin.png（anchor 0.5,0.5，pos(w*0.5, h*0.55)）
        # 否则              → text_spin.png（anchor 0,0.5，pos(w*0.18, h*0.55)）+ 价格
        if self.free_spins[i] > 0:
            t = res.load_img(TEXT_FREE_TEX)
            if t:
                tw = max(1, int(t.get_width() * k))
                th = max(1, int(t.get_height() * k))
                tx = rect.centerx
                ty = rect.y + rect.h * 0.55
                s.blit(
                    pygame.transform.smoothscale(t, (tw, th)), (int(tx - tw / 2), int(ty - th / 2))
                )
        else:
            t = res.load_img(TEXT_SPIN_TEX)
            if t:
                tw = max(1, int(t.get_width() * k))
                th = max(1, int(t.get_height() * k))
                tx = rect.x + rect.w * 0.18
                ty = rect.y + rect.h * 0.55
                s.blit(pygame.transform.smoothscale(t, (tw, th)), (int(tx), int(ty - th / 2)))
            coin, crystal = SPIN_PRICES[i]
            self._draw_price(s, rect, coin, crystal, k)

    def _draw_price(self, s, rect, coin, crystal, k=1.0):
        """setPriceNode @0x142958。

        图标和数字都是**按钮的子节点**（EzFunctionButton::addImageChild），
        坐标用按钮自己的 contentSize 当单位，再乘按钮 scale 0.9 和根缩放 k：
          金币：icon anchor(0,0.54)  setScale(0.45)  pos(w*0.45, h*0.55)
                num  getTexFont(1) anchor(0,0.5) setScale(0.75) pos(w*0.57, h*0.55)
          钻石：icon anchor(0,0.50)  setScale(0.48)  pos(w*0.50, h*0.55)
                num  getTexFont(3) anchor(0,0.5) setScale(0.80) pos(w*0.65, h*0.55)

          · 图标 x 多减了 iw/2 —— anchor x 是 0（贴左边缘），不是 0.5；
          · 图标 y 从按钮**顶边**往下量 (1-ay)*h，而 cocos 的 pos.y 是从
            底边往上量的 0.55*h —— 导致图标比数字高出一截，看着就是
            「数量和图标没在一起」；
          · 图标尺寸和数字字号漏乘按钮 0.9，整体小一圈。
        """
        bw, bh = self._btn_size
        if coin > 0:
            img = res.load_img(COIN_TEX)
            font = gridfont.get_font(FONT_COIN)
            val, img_sc, num_sc, num_x = coin, 0.45, 0.75, 0.57
        elif crystal > 0:
            img = res.load_img(CRYSTAL_TEX)
            font = gridfont.get_font(FONT_CRYSTAL)
            val, img_sc, num_sc, num_x = crystal, 0.48, 0.80, 0.65
        else:
            return
        if not img or not font:
            return

        s0 = 0.9 * k
        # 按钮局部 → 屏幕：x 从按钮左边缘量，y 从按钮底边往上量
        pos_y = rect.y + rect.h - bh * 0.55 * s0

        # 图标 anchor(0, ay)：左边缘贴 pos_x，锚点在内容从底往上 ay 处。
        # 但 185×61 的 button_spin.png 里按钮本体只占 y=1..57，
        # cocos 的 contentSize 用的是整张贴图 61 —— 直接按 0.55 量会低 4px。
        # 模拟器参考帧（feat/slot.png 第一个 spin 按钮）实测：
        #   按钮紫底 x 177..316、y 403..439（rect = 164,394,166,54）
        #   金币图标 ink 16×17，左边缘 229、顶边 398
        # ⇒ 相对按钮矩形：(229-164, 398-394) = (65, 4)
        iw = max(1, int(img.get_width() * img_sc * s0))
        ih = max(1, int(img.get_height() * img_sc * s0))
        s.blit(
            pygame.transform.smoothscale(img, (iw, ih)),
            (int(round(rect.x + 65.0 * k)), int(round(rect.y + 4.0 * k))),
        )

        # 数字 anchor(0,0.5) scale 0.75/0.8（同样要乘 s0）
        font.draw(s, str(val), rect.x + bw * num_x * s0, pos_y, num_sc * s0, align=(0.0, 0.5))

    def _back_hit_rect(self):
        """返回键的命中区（不依赖已经 draw 过，键盘清单要用）。"""
        im = res.load_img(BACK_TEX)
        if not im:
            return None
        sc = _back_scale()
        w = max(1, int(im.get_width() * sc))
        h = max(1, int(im.get_height() * sc))
        return pygame.Rect(0, int(H - H * 0.03 - h), w, h)

    def _draw_back(self, s):
        im = res.load_img(BACK_TEX)
        if not im:
            return
        r = self._back_hit_rect()
        if r is None:
            return
        s.blit(pygame.transform.smoothscale(im, (r.w, r.h)), r.topleft)
        self.back_rect = r
