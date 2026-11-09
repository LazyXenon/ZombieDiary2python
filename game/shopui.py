"""军火库渲染 —— 逐条照抄 GunShopLayer::init 的原始布局公式。

设计稿 854x480。原版每个子节点都是「父节点尺寸 × 比例」，本模块照抄这些
比例，不出现像素级微调量。

来源：
  * sub_129070 @0x129070   ShopLayer::init 顶栏 / 5 页签 / 返回
  * sub_133BB8 @0x133BB8   GunShopLayer::init 滚动区 / 属性面板 / 按钮 / 槽位
  * sub_13324C @0x13324C   GunShopLayer::onSelectGun（标题 / 属性 / 弹种）
  * sub_1329BC @0x1329BC   initFireTypeTexts 弹种贴图字典
  * sub_12806A @0x12806A   initCoinAndCrystal 货币行
  * sub_1325CC @0x1325CC   addGunItems 卡片表与选中项
  * GunItem 节点树          data/node_tree_shop.json 卡片内部结构
"""

import math

import pygame

from engine import gridfont, res, scene
from game.ninecell import draw_9cell_atlas, fill_panel
from game.shop_table import SHOP_GUNS


def _sc(im, size):
    """带缓存的 smoothscale（同贴图同尺寸只算一次）。"""
    return scene.scaled(im, int(size[0]), int(size[1]))


# 详情面板底：设置弹窗同款 9 宫格（替代 shop/property_bg.png 那块橙色托盘）
BG9 = "pic/ui/dialog/9cell_bg.png"


def panel_bg(s, rect):
    fill_panel(s, BG9, rect, (40, 30, 58, 200), 1.0)
    draw_9cell_atlas(s, BG9, rect, 1.0)


DASH_PULSE_HZ = 0.07


def dashed_selection(
    s, rect, t=0.0, color=(255, 238, 150), dash=7, gap=5, width=2, pad=3, speed=0.0
):
    """虚线选中框（用户：「选中的框可以用虚线闪烁型的」）。

    t = 秒。speed>0 时虚线沿边框流动；默认 0 = 静止。
    """
    x0, y0 = rect.x - pad, rect.y - pad
    w, h = rect.w + pad * 2, rect.h + pad * 2
    if w <= 4 or h <= 4:
        return
    phase = (t * speed) % float(dash + gap) if speed else 0.0
    #   而是**低帧率**下的呼吸 —— 虚线每帧重建，帧率掉到 1~2 FPS 时
    #   226↔255 的「呼吸」看起来就是一秒亮一次。彻底改成完全不透明恒定
    #   色，任何帧率下都是死的，不可能再闪。
    col = (color[0], color[1], color[2], 255)
    layer = pygame.Surface((w + width, h + width), pygame.SRCALPHA)
    off = -int(phase)
    for x in range(off, w, dash + gap):
        pygame.draw.line(layer, col, (x, 0), (x + dash, 0), width)
        pygame.draw.line(layer, col, (x, h), (x + dash, h), width)
    for y in range(off, h, dash + gap):
        pygame.draw.line(layer, col, (0, y), (0, y + dash), width)
        pygame.draw.line(layer, col, (w, y), (w, y + dash), width)
    s.blit(layer, (x0, y0))


# 贴图轮廓缓存：(texture, alpha) → [(x, y), ...]
_SHAPE_OUTLINE = {}
_DASH_LAYER = {}


def shape_outline(texture, alpha=96):
    """贴图**不透明区域**的轮廓点（贴图左上为原点）。

    武器卡、技能卡、机甲卡都不是矩形 —— 两侧有三角、右边是斜切尖角。
    用矩形虚线去框它，四角必然「出框」（用户反复提「贴图必须在框框里面」
    「这个框改成刚好适配游戏框框的」）。这里直接取 alpha 掩膜的轮廓，
    虚线就永远贴着卡片本身的形状走。
    """
    key = (texture, alpha)
    if key in _SHAPE_OUTLINE:
        return _SHAPE_OUTLINE[key]
    surf = img(shop(texture))
    if surf is None:
        _SHAPE_OUTLINE[key] = []
        return []
    mask = pygame.mask.from_surface(surf, alpha)
    pts = mask.outline(6)
    _SHAPE_OUTLINE[key] = pts
    return pts


BREATH_PERIOD = 1.4  # 选中框呼吸周期（秒）


def breath_alpha(t, lo=104, hi=255, period=BREATH_PERIOD):
    """呼吸透明度：lo→hi→lo 平滑往返，量化成 12 档配合整层缓存。

    选中框完全静止，看起来像贴上去的一张图。
    """
    k = 0.5 + 0.5 * math.sin(float(t) * math.tau / float(period))
    return int((lo + (hi - lo) * k) // 12 * 12)


def select_marks(s, r, outset=2, t=None):
    """原版 select_box.png 的四角绿色三角箭头 + 呼吸闪烁。

    军火库底部武器槽 / 底部头像格 / 技能格共用这一套选中态。
    """
    box = res.load_img("pic/ui/shop/select_box.png")
    if not box:
        pygame.draw.rect(s, (90, 220, 120), r.inflate(-2, -2), 2, border_radius=6)
        return
    if t is None:
        t = pygame.time.get_ticks() / 1000.0
    rr = r.inflate(outset * 2, outset * 2)
    im = _sc(box, rr.size).copy()
    im.fill((255, 255, 255, breath_alpha(t)), special_flags=pygame.BLEND_RGBA_MULT)
    s.blit(im, rr.topleft)


def dashed_shape(
    s, texture, topleft, t=0.0, color=(255, 238, 150), dash=9, gap=7, width=2, speed=0.0, alpha=96
):
    """沿贴图轮廓画一圈呼吸虚线（形状自适应，不会出框）。"""
    pts = shape_outline(texture, alpha)
    if not pts or len(pts) < 4:
        return
    step_pts = max(1, len(pts) // 260)
    if step_pts > 1:
        pts = pts[::step_pts]
    ox, oy = topleft
    segs = []
    total = 0.0
    n = len(pts)
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        if d < 0.6:
            continue
        segs.append((a, b, d))
        total += d
    if total <= 2.0:
        return

    # ★ 呼吸闪烁：透明度随时间往返，量化成 12 档 —— col 已在缓存键里，
    #   所以每一档只画一次 227 个 circle，之后整层复用。
    col = (color[0], color[1], color[2], breath_alpha(t))
    phase = (t * speed) % float(dash + gap) if speed else 0.0

    # 虚线整层缓存：speed=0 ⇒ 相位恒为 0，只剩呼吸档位的差异。
    ckey = (texture, alpha, col, dash, gap, width, round(phase, 2))
    hit = _DASH_LAYER.get(ckey)
    if hit is not None:
        layer, minx, miny = hit
        s.blit(layer, (int(ox + minx), int(oy + miny)))
        return

    minx = min(p[0] for p in pts) - width - 2
    miny = min(p[1] for p in pts) - width - 2
    maxx = max(p[0] for p in pts) + width + 2
    maxy = max(p[1] for p in pts) + width + 2
    lw = max(1, int(maxx - minx))
    lh = max(1, int(maxy - miny))
    layer = pygame.Surface((lw, lh), pygame.SRCALPHA)
    period = float(dash + gap)
    x = -phase
    i = 0
    acc = 0.0
    while x < total:
        while i < len(segs) and acc + segs[i][2] < x:
            acc += segs[i][2]
            i += 1
        if i >= len(segs):
            break
        a, b, d = segs[i]
        f = (x - acc) / d
        if 0.0 <= f <= 1.0 and (x % period) < dash:
            px = a[0] + (b[0] - a[0]) * f - minx
            py = a[1] + (b[1] - a[1]) * f - miny
            pygame.draw.circle(layer, col, (int(px), int(py)), width)
        x += 2.0
    if len(_DASH_LAYER) > 64:
        _DASH_LAYER.clear()
    _DASH_LAYER[ckey] = (layer, minx, miny)
    s.blit(layer, (int(ox + minx), int(oy + miny)))


W, H = 854, 480

# ------------------------------------------------------------------ 顶栏
TOP_BAR = "pic/ui/shop/up_bar.png"
UP_BAR_H = 98.0
# 中心比例：0.20 / 0.37 / 0.54 / 0.71 / 0.88，但选中的那一项上移 12 后
# 中心落在 0.356（dump 实测），所以每个页签都要按自身状态校正
# ★ 原版第 3 个是充值页（money），服务器已下线、整页全是死按钮 ——
#   删掉后剩下 4 个页签按 0.20/0.40/0.60/0.80 重新均分。
TABS = (
    ("soldier", "soldier_icon.png", 0.20),
    ("gun", "gun_icon.png", 0.40),
    ("ability", "ability_icon.png", 0.60),
    ("mech", "mech_icon.png", 0.80),
)
TAB_CENTER_DROP = 12.0 / 854  # 选中态中心相对比例位右移？实为位置不变，见下
TAB_Y = 45.0  # 页签锚点 y = up_bar.h*0.46 ≈ 45.08，取整
BACK_TEX = "pic/ui/shop/button_back.png"
BACK_BOTTOM = 14.0  # pos.y = H*0.03 = 14.4，取整
TAB_TEX_Y = 0  # 选中态只换贴图上半张


def tab_scale():
    """up_bar 等比缩放 = W*k / up_bar.w。"""
    r = W / H
    if r >= 1.6:
        return 1.0
    if r >= 1.4:
        return 1.06
    return 1.08


def back_scale():
    r = W / H
    if r >= 1.6:
        return 0.85 if r >= 1.7 else 0.80
    if r >= 1.4:
        return 0.73
    return 0.64


def panel_scale():
    r = W / H
    if r >= 1.6:
        return 1.0
    if r >= 1.4:
        return 0.95
    return 0.87


def panel_dy():
    """v144：面板整体下移量，短屏时补一点。"""
    r = W / H
    if r >= 1.6:
        return 0.0
    if r >= 1.4:
        return H * 0.006
    return H * 0.02


# ------------------------------------------------------------------ 列表
# 节点树实测（data/node_tree_shop.json）：
#   ScrollNode 0xd6620804  pos=[420.78, 211.2] ap=[1.0,0.5] sz=[315.73, 408.0]
#   内层 ScrollNode 0xec0b3844 pos=[0, 933] ap=[0,1]（内容容器）
#   每个 GunItem 容器：gun_bg.png pos=[0, -105*k] ap=[0,1] sz=[300,95]
#     （k = 1,2,3… 依次 -2100 / -2205 / -2310 …，行距 105）
#     选中项的 gun_bg 在容器内 pos=[0, 95]（比其它项上移 95 → 选中项浮起）
#   gun_locker.png pos=[150, 47.5] ap=[0.5,0.5] sz=[300,95]
# 换算：ScrollNode anchor(1,0.5) ⇒ 右缘屏幕 x = 420.78，
#       垂直中心屏幕 y = 480 − 211.2 = 268.8
SCROLL_RIGHT = 420.78
SCROLL_CY = 268.8
SCROLL_W = 315.73
SCROLL_H = 408.0
# 裁剪区上沿 = 中心 − 半高 = 268.8 − 204 = 64.8
SCROLL_TOP = SCROLL_CY - SCROLL_H / 2
CARD_W, CARD_H = 300, 95  # GunItem 内容尺寸
CARD_PITCH = 105  # ScrollNode 内部行距
SCROLL_LEAD = 1  # scrollAndSelectGun 把选中项停在第二行


def _gun_frame(rect):
    """gun_bg.png 里**可见白框**的屏幕矩形。

    ★ 贴图 300×95，白框只到 (3,3)-(291,73)：右边 9px、下边 22px 是软阴影
      （alpha 有值但像素是暗的）。角标按 rect 的右下角摆会落到阴影上，
      看着像画到卡片外面去了。
    """
    return pygame.Rect(rect.x + 4, rect.y + 4, CARD_W - 13, CARD_H - 26)


def scroll_right():
    """卡片区右缘（ScrollNode anchor(1,0.5) 的屏幕 x）。"""
    return SCROLL_RIGHT


# ------------------------------------------------------------------ 详情面板
PANEL_TEX = "pic/ui/shop/property_bg.png"
PANEL_W, PANEL_H = 391, 238
PANEL_X = 631.47  # 节点树 property_bg pos=[631.47, 256.8]
PANEL_CY = 256.8  # 节点树 property_bg pos=[631.47, 256.8]


# 属性行几何 —— 全部照抄节点树 data/node_tree_shop.json 的实测值。
# property_bg（0xd6623b84）pos=[631.47,256.8] ap=[0.5,0.5] sz=[391,238]
#   ⇒ 屏幕矩形 = (435.97, 104.2, 391, 238)
# 三条属性标签（text_power / text_frate / text_crit）都 anchor(1,0.5)：
#   power pos=[136.85,147.56] sz=[51,24]
#   frate pos=[136.85,121.38] sz=[50,22]
#   crit  pos=[136.85, 95.20] sz=[51,24]
# 三条 PropertyCells anchor(0,0.5)，pos x 都是 144.67：
#   y = 147.56 / 121.38 / 95.20
# 局部 → 屏幕：x = panel.x + local_x
#              y = panel.y + (panel.h - local_y)      （cocos y 向上）
# 所以：
#   属性条左端（cell_bg 锚点 x=0）屏幕 x = 435.97 + 144.67 = 580.64
#   三行条的中线屏幕 y = 194.64 / 220.82 / 247.00
CELL_X = 580.64
CELL_ROW_Y = (194.64, 220.82, 247.00)
ATTR_LABEL_RIGHT = 136.85  # 标签 anchor(1,0.5) 的局部 x
ATTR_TEX = ("text_power.png", "text_frate.png", "text_crit.png")
# 原版三行共用同一套 cell_now / cell_bg 贴图，不按行换色
ATTR_COLOR = (255, 168, 48)
CELL_PITCH = 15  # cell_bg.w * 0.6 = 25 * 0.6
CELL_COUNT = 12

# 弹种贴图：x=w*0.48；名 y=h*0.87、说明 y=h*0.74（cocos，自面板中心起）
FIRE_X = 0.48
FIRE_TITLE_Y = 0.87
FIRE_NAME_Y = 0.74
FIRE_TEX = {
    "semi_auto": "semi_auto_firearm.png",
    "auto": "automatic_firearm.png",
    "explosive": "explosive_damage.png",
    "aoe": "aoe_damage.png",
    "freeze": "freeze_3_seconds.png",
    "penetrating": "penetrating_damage.png",
}

# 弹匣：bg x=w*0.44 y=h*0.17；图标 x=w*0.10；x比分 x=w*0.24
AMMO_BG_X, AMMO_BG_Y = 0.44, 0.17
BULLET_ICON_X, BULLET_X = 0.10, 0.24
# 弹药行（GunShopLayer::init @0x136e9c 尾段，节点树实测）：
#   gun_bullets.png  anchor(0,0)   pos = (w*0.10, h*0.17)
#   EzScoreText "x"  anchor(0,0.5) pos = (w*0.24, h*0.24) scale 0.93
#   infinit_ammo.png anchor(0,0)   pos = (w*0.53, h*0.25)
AMMO_ICON_X, AMMO_ICON_Y = 0.10, 0.17
AMMO_NUM_X, AMMO_NUM_Y = 0.24, 0.24

# property_bg.png 里的「内容区」：局部 x 19..358、下白线 y≈205
# （外面还有 33px 投影 + 左下/右下两枚蓝色护角）
PANEL_INNER_L, PANEL_INNER_R = 19, 358
PANEL_INNER_B = 205


def buy_bullet_rect(pr):
    """「买子弹 +N  M金币」条：收在面板内框里，不压白线、不骑蓝角。

    ★ 原来按面板外缘算 (pr.bottom − BTN_H − 10)，落在 284..332 ——
      下半截直接盖到 y≈309 的下白线和右下蓝色护角上，右边还顶出白描边
      （用户截图「子弹数量和这个框的位置重叠了」）。
    """
    w = min(BTN_W, 145)
    h = 41
    return pygame.Rect(int(pr.x + PANEL_INNER_R - 4 - w), int(pr.y + PANEL_INNER_B - 6 - h), w, h)


INF_AMMO_X, INF_AMMO_Y = 0.53, 0.25

# ------------------------------------------------------------------ 按钮
# anchor(0,1)；y = panel.y − panel.h*0.48
#   unlock / buy / equip  x = panel.x
#   upgrade               x = panel.x − 180*scale
BTN_W, BTN_H = 170, 48
BTN_DROP = 0.48
BTN_UPGRADE_DX = 180.0

# ------------------------------------------------------------------ 槽位
# 82x82 anchor(1,0)；x = panel.x + panel.w*0.47*scale − (3−k)*82*1.2*scale
# y = H*0.01 + v144
SLOT_SZ = 82
SLOT_PITCH = SLOT_SZ * 1.2
SLOT_N = 4
SLOT_DX = 0.47  # panel.w*0.47 = 183.8 → 右缘 815.8
SLOT_Y = 5.0  # H*0.01 = 4.8，取整

# 货币行（节点树实测 data/node_tree_shop.json）
#   容器 0xcc5ba184: CCNode pos=[614.4, 390.72] ap=[0.5,0.5] sz=[304.3,50] sc=0.7
#     ├ coin.png        pos=[0,   25]  ap=[0,0.5]  sz=[50,50]   sc=1
#     ├ EzScoreText     pos=[55,  25]  ap=[0,0.5]  sz=[81.56,25] sc=1.6  (金币数)
#     ├ EzScoreText     pos=[55, -30]  ap=[0,0.65] sz=[18,25]   sc=1.7  (绿药)
#     ├ crystal.png     pos=[215.5,25] ap=[0,0.5]  sz=[55,41]   sc=1
#     └ EzScoreText     pos=[275.5,25] ap=[0,0.5]  sz=[18,25]   sc=1.6  (钻石数)
#   子节点坐标是**容器局部**坐标（容器锚点中心为原点，y 向上）。
#   换算到屏幕：x = 容器中心 x + 局部 x
#                y = 容器中心 y − 局部 y（cocos 向上 → 屏幕向下）
#   容器中心屏幕位置 = (614.4, 480 − 390.72) = (614.4, 89.28)
# 参考帧核对（feat/shop.png，854×480 原始分辨率）：用 coin.png 本体做
# 多尺度模板匹配，原版贴图绘制框 = (507, 54, 35, 35)。
#   coin 高 50×0.7 = 35，中心 y = 54+17.5 = 71.5；
#   子节点局部 y=25，乘 0.7 得 17.5 ⇒ 容器中心屏幕 y = 71.5 + 17.5 = 89
#   coin 局部 x=0 ⇒ 容器中心 x = 507
# 贴图边框，整行因此偏右下约 (5, 20) —— 和原版比就是图标整体错位。
# 同一匹配给出的 crystal (658, 60) 和 add (725, 69) 都能用新值复现。
COIN_BOX_X, COIN_BOX_Y = 507.0, 89.0  # 容器中心的**屏幕**坐标
COIN_BOX_W, COIN_BOX_H = 304.3, 50.0
COIN_BOX_SC = 0.7
COIN_ADD_X = 725.0
COIN_MAX_W = 0.35  # 整行上限 = 0.35W（sub_12806A 的超宽判定）
COIN_TEXT_SCALE = 0.7  # 25(容器高)/36(atlas 字形高) ≈ 0.69，取 0.7
COIN_SLOTS = (
    (0.0, 25.0, 50.0, 50.0, "coin"),
    (55.0, 25.0, 81.56, 25.0, "num_coin"),
    (215.5, 25.0, 55.0, 41.0, "crystal"),
    (275.5, 25.0, 18.0, 25.0, "num_crystal"),
)

_IMG = {}


def img(name):
    if name not in _IMG:
        _IMG[name] = res.load_img(name)
    return _IMG[name]


def shop(n):
    return "pic/ui/shop/" + n


def ui(n):
    return "pic/ui/" + n


def sy(y):
    """cocos y（向上）→ pygame y（向下）。"""
    return H - y


# ------------------------------------------------------------------ 字体
class ScoreFont:
    """EzScoreText：pic/fonts/score_*.png，每格 36x40。

    图集顺序（实测）：1 2 3 4 5 6 7 8 9 0 , x + - : /
    """

    ORDER = "1234567890,x+-:/"
    CELL = 36

    def __init__(self, name, scale=1.0):
        self.sheet = res.load_img(name)
        self.scale = scale
        self.glyphs = {}
        self._sc = {}  # (字, 宽, 高) -> 缩放好的字形
        if not self.sheet:
            return
        for i, ch in enumerate(self.ORDER):
            r = pygame.Rect(i * self.CELL, 0, self.CELL, self.sheet.get_height())
            if not self.sheet.get_rect().contains(r):
                break
            cell = self.sheet.subsurface(r).copy()
            bb = cell.get_bounding_rect()
            if bb.width:
                self.glyphs[ch] = (cell, bb)

    def width(self, text, scale=None):
        k = self.scale if scale is None else scale
        total = 0
        for c in str(text):
            g = self.glyphs.get(c)
            total += int((g[1].width + 2) * k) if g else int(self.CELL * k)
        return total

    def draw(self, surf, text, x, y, scale=None, align=0.0):
        """y = 中线；align 0=左 0.5=中 1=右。"""
        if not self.sheet:
            return 0
        k = self.scale if scale is None else scale
        text = str(text)
        cursor = x - self.width(text, k) * align
        for ch in text:
            g = self.glyphs.get(ch)
            if not g:
                cursor += int(self.CELL * k)
                continue
            cell, bb = g
            w, h = max(1, int(bb.width * k)), max(1, int(bb.height * k))
            # 同一字同尺寸的缩放结果每帧相同，缓存掉 subsurface + smoothscale
            gim = self._sc.get((ch, w, h))
            if gim is None:
                gim = pygame.transform.smoothscale(cell.subsurface(bb).copy(), (w, h))
                self._sc[(ch, w, h)] = gim
            surf.blit(gim, (int(cursor), int(y - h / 2)))
            cursor += int((bb.width + 2) * k)
        return self.width(text, k)


# ------------------------------------------------------------------ 顶栏
def draw_top_bar(s, active="gun"):
    """up_bar anchor(0.5,1) 落在 (W/2, H)：贴图顶边贴屏幕顶，向下铺 98px。"""
    rects = {}
    bar = img(TOP_BAR)
    if not bar:
        return rects

    bw0, bh0 = bar.get_size()
    k = tab_scale()
    bw, bh = int(bw0 * k), int(bh0 * k)
    left = W / 2 - bw / 2  # 世界 x，屏幕同轴
    s.blit(_sc(bar, (bw, bh)), (int(left), 0))

    for tid, tex, ratio in TABS:
        tile = img(shop(tex))
        if not tile:
            continue
        tw, th = tile.get_width(), tile.get_height() // 2  # 上下两态，不是左右
        row = 0 if tid == active else th
        sub = tile.subsurface(pygame.Rect(0, row, tw, th)).copy()
        # 子节点 anchor(0,0)：x = up_bar.w*ratio − btn.w*0.5，
        # y = up_bar.h*0.46（选中态 45.08−12=33.08，底边对齐不变）
        dx = bw0 * ratio - tw / 2
        dy = TAB_Y
        r = pygame.Rect(int(left + dx * k), int(bh0 * k - (dy + th) * k), int(tw * k), int(th * k))
        s.blit(_sc(sub, r.size), r.topleft)
        rects[tid] = r

    back = img(BACK_TEX)
    if back:
        bs = back_scale()
        im = _sc(back, (int(back.get_width() * bs), int(back.get_height() * bs)))
        pos = (0, int(H - BACK_BOTTOM - im.get_height()))  # anchor(0,0)
        s.blit(im, pos)
        rects["back"] = pygame.Rect(pos[0], pos[1], im.get_width(), im.get_height())
    return rects


# ------------------------------------------------------------------ 货币行
def draw_currency(s, coins, crystals, font):
    """sub_12806A：整行 CCNode anchor(0.5,0.5) at (0.72W, 0.814H)。

    行内 coin / 数字 / crystal / 数字 / add 全部 anchor(0,0.5)，左起排，
    父节点 pos 是 cocos y，先翻到屏幕坐标再逐项累加。
    """
    coin = img(ui("common/coin.png"))
    crystal = img(ui("common/crystal.png"))
    add = img(ui("buttons/add_crystal_button.png"))
    if not coin or not crystal:
        return {}

    coin_txt = f"{int(coins):,}"
    cry_txt = str(int(crystals))
    k = COIN_BOX_SC
    C_W, C_H = int(50 * k), int(50 * k)  # coin.png
    R_W, R_H = int(55 * k), int(41 * k)  # crystal.png
    GAP = 7
    add_w = add.get_width() if add else 0
    avail = W - 8 - COIN_BOX_X  # 容器左缘到屏幕右边的可用宽度

    # 数字太宽就压字号（只压字，图标尺寸不动），保证整行不出屏
    tk = COIN_TEXT_SCALE
    _tot = 0
    for _ in range(8):
        _tot = (
            C_W
            + GAP
            + font.width(coin_txt, tk)
            + GAP * 2
            + R_W
            + GAP
            + font.width(cry_txt, tk)
            + GAP
            + add_w
        )
        if _tot <= avail:
            break
        tk *= 0.9

    # 容器中心在 COIN_BOX_X；整行太长就往左让，右缘最多到 W-6
    left = min(COIN_BOX_X, W - 6 - _tot)
    left = max(6, left)
    top = COIN_BOX_Y
    rects = {}

    # 金币图标
    r = pygame.Rect(int(left), int(top - C_H / 2), C_W, C_H)
    s.blit(_sc(coin, r.size), r.topleft)
    rects["coin"] = r

    # 金币数字（用 draw 的返回值推进，绝不靠估算）
    sx = r.right + GAP
    sx += font.draw(s, coin_txt, sx, top, tk, align=0.0) + GAP * 2

    # 钻石图标
    r = pygame.Rect(sx, int(top - R_H / 2), R_W, R_H)
    s.blit(_sc(crystal, r.size), r.topleft)
    rects["crystal"] = r

    # 钻石数字
    sx = r.right + GAP
    sx += font.draw(s, cry_txt, sx, top, tk, align=0.0) + GAP

    if add:
        aw, ah = add.get_size()
        r = pygame.Rect(sx, int(top - ah / 2), aw, ah)
        s.blit(add, r.topleft)
        rects["add_crystal"] = r
    return rects


# ------------------------------------------------------------------ 列表
def card_rect(index, first_row):
    """第 index 张卡片的屏幕矩形。

    first_row = 显示在**列表最顶端**那张卡的索引。
    顶端 y = ScrollNode 裁剪区上沿 = 64.8（节点树 ScrollNode 中心屏幕 y 268.8
    减半高 204）。行距 105（节点树 gun_bg 的 pos 步长 -105），往下排。
    """
    return pygame.Rect(
        int(scroll_right() - CARD_W),
        int(SCROLL_TOP + (index - first_row) * CARD_PITCH),
        CARD_W,
        CARD_H,
    )


def row_range(first_row):
    """可见的行：从 first_row（最顶端那张）往下。"""
    rows = int(SCROLL_H // CARD_PITCH) + 2
    return range(max(0, first_row), min(len(SHOP_GUNS), first_row + rows))


def scroll_rect():
    """ScrollNode 的屏幕包围盒：size(315.73, 408) anchor(1,0.5)，中心 y=268.8。"""
    right = scroll_right()
    top = SCROLL_TOP
    return pygame.Rect(int(right - SCROLL_W), int(top), int(SCROLL_W), int(SCROLL_H))


def draw_cards(s, save, first_row, selected, font):
    """卡片画在 ScrollNode 的裁剪区内（原版 ScrollNode 自带 setClippingRegion）。"""
    clip = scroll_rect().clip(pygame.Rect(0, 0, W, H))
    if clip.width <= 0 or clip.height <= 0:
        return {}
    layer = pygame.Surface(clip.size, pygame.SRCALPHA)
    rects = {}
    for i in row_range(first_row):
        g = SHOP_GUNS[i]
        local = card_rect(i, first_row).move(-clip.x, -clip.y)
        if local.bottom < 0 or local.top > clip.height:
            continue
        rects[g["name"]] = card_rect(i, first_row)
        _draw_card(layer, g, local, save, selected, font)
    s.blit(layer, clip.topleft)
    return rects


def _shop_gun_icon(save, name):
    lv = save.weapon_level(name) if hasattr(save, "weapon_level") else 0
    pick = 0
    try:
        from game.weapons import load_upgrade_table

        tab = load_upgrade_table().get(name) or {}
        for lk in tab.get("looks") or []:
            if lv >= int(lk.get("min_lv", 0) or 0):
                pick = int(lk.get("look_index", 0) or 0)
    except Exception:
        pick = 0
    if pick > 0:
        alt = img(shop("gun_%s_%d.png" % (name, pick)))
        if alt:
            return alt
    return img(shop("gun_%s.png" % name)) or img(shop("gun_%s_1.png" % name))


def _draw_card(s, g, rect, save, selected, font):
    """一张武器卡片 —— 全部照抄节点树实测的 GunItem 局部坐标。

    节点树（选中项 0xd64f0644，GunItem 容器 300x95）：
      gun_selected.png   pos=[150, 47.5] ap=[0.5,0.5] sz=[320,105]
      gun_bought.png     pos=[270, 85.5] ap=[1,1]     sz=[46,46] sc=0.8   ← 绿勾
      label_equipped.png pos=[250.5, 26.6] ap=[1,0]  sz=[55,18]
      gun_<name>.png     pos=[20, 24]    ap=[0,0]
      gun_locker.png     pos=[150, 47.5] ap=[0.5,0.5] sz=[300,95]

    局部坐标 y 向上，anchor(1,1) = 贴图右上角、(1,0) = 右下角、
    (0.5,0.5) = 中心、(0,0) = 左下角。
    """
    owned = save.own_weapon(g["name"])
    equipped = g["name"] in save.d["equipped"]

    bg = img(shop("gun_bg.png"))
    if bg:
        s.blit(bg, rect.topleft)

    # 选中框：gun_selected 320x105，中心在 (150, 47.5) ⇒ 卡片内 (150, 47.5)，
    # 屏幕 = rect.x + 150 − 160、rect.y + 95 − 47.5 − 52.5
    if g["name"] == selected:
        sel = img(shop("gun_selected.png"))
        if sel:
            sx = rect.x + 150 - sel.get_width() // 2
            sy = rect.y + 95 - 47.5 - sel.get_height() // 2
            s.blit(sel, (int(sx), int(sy)))
        if sel:
            dashed_shape(s, "gun_selected.png", (sx, sy), pygame.time.get_ticks() / 1000.0)
        else:
            dsel = pygame.Rect(rect.x + 2, rect.y + 5, 296, 86)
            dashed_selection(s, dsel, pygame.time.get_ticks() / 1000.0)

    # 枪图标：anchor(0,0) = 左下角，pos=(20, 24)
    icon = _shop_gun_icon(save, g["name"])
    if icon:
        ix = rect.x + 20
        iy = rect.y + 95 - 24
        s.blit(icon, (int(ix), int(iy - icon.get_height())))

    if not owned:
        lk = img(shop("gun_locker.png"))
        if lk:
            lx = rect.x + 150 - lk.get_width() // 2
            ly = rect.y + 95 - 47.5 - lk.get_height() // 2
            s.blit(lk, (int(lx), int(ly)))
        _need = int(g.get("unlock_level") or 0)
        _cost = int(g.get("unlock_crystal") or 0)
        if _need > 0 or _cost > 0:
            f = pygame.font.SysFont("Microsoft YaHei", 13, bold=True)
            # need 是「通关第几关才能买」、cost 是「花钻石提前解锁」，
            # 都跟卡片右下角的**购买价**不是一回事，措辞要区分开，
            # 否则卡片上出现「80钻」而价格写「400」会自相矛盾。
            label = "关卡 %d" % _need if _need > 0 else "钻石解锁"
            if _cost > 0 and _need > 0:
                label += " / %d钻提前" % _cost
            t = f.render(label, True, (255, 214, 145))
            sh = f.render(label, True, (30, 14, 6))
            crys = img(ui("common/crystal.png")) if _cost > 0 else None
            ic_sz = 16
            icon_w = ic_sz + 4 if crys else 0
            box_w = icon_w + t.get_width()
            fr = _gun_frame(rect)
            # 整块（含底板）右对齐到**可见白框**内侧：gun_bg.png 右边 9px
            # 是软阴影，按 rect.right 摆的话标签尾巴和白描边一起被切掉。
            bx = fr.right - 6 - box_w
            by = fr.top + 3
            plate = pygame.Surface((box_w + 8, t.get_height() + 4), pygame.SRCALPHA)
            plate.fill((10, 8, 20, 175))
            s.blit(plate, (int(bx - 4), int(by - 2)))
            tx = bx
            if crys:
                s.blit(
                    _sc(crys, (ic_sz, ic_sz)), (int(tx), int(by + (t.get_height() - ic_sz) // 2))
                )
                tx += icon_w
            s.blit(sh, (int(tx) + 1, int(by) + 1))
            s.blit(t, (int(tx), int(by)))
        _draw_price(s, g, rect, font)
        return

    # 已拥有 → 右上角绿勾（gun_bought，anchor(1,1)，scale 0.8）
    bought = img(shop("gun_bought.png"))
    if bought:
        sc = 0.8
        bw = max(1, int(round(bought.get_width() * sc)))
        bh = max(1, int(round(bought.get_height() * sc)))
        bx = rect.x + 270
        by = rect.y + 95 - 85.5
        s.blit(_sc(bought, (bw, bh)), (int(bx - bw), int(by - bh)))

    # 已装备 → 右下角「已装备」（label_equipped，anchor(1,0)）
    if equipped:
        lab = img(shop("label_equipped.png"))
        if lab:
            lx = rect.x + 250.5
            ly = rect.y + 95 - 26.6
            s.blit(lab, (int(lx - lab.get_width()), int(ly - lab.get_height())))


def _draw_price(s, g, rect, font):
    text = str(g["crystal"] or g["coin"])
    icon = img(ui("common/crystal.png") if g["crystal"] else ui("common/coin.png"))
    size = 25
    right = rect.right - 48
    cy = rect.bottom - 28
    tw = font.width(text, 0.5)
    tx = right - tw
    if icon:
        s.blit(_sc(icon, (size, size)), (int(tx - size - 4), int(cy - size / 2)))
    font.draw(s, text, tx, cy, 0.5)


# ------------------------------------------------------------------ 面板
def panel_rect():
    ps = panel_scale()
    pw, ph = PANEL_W * ps, PANEL_H * ps
    return pygame.Rect(
        int(PANEL_X - pw / 2), int(sy(PANEL_CY + panel_dy()) - ph / 2), int(pw), int(ph)
    )


def draw_empty_detail(s, font=None, msg="点一下卡片选中 · 再点一次取消"):
    """玩家取消选中后，右侧详情面板的空态（面板底照旧，只换内容）。"""
    rect = panel_rect()
    panel_bg(s, rect)
    f = pygame.font.SysFont("Microsoft YaHei", 16, bold=True)
    t1 = f.render("未选择武器", True, (236, 228, 250))
    t2 = f.render(msg, True, (176, 168, 200))
    s.blit(t1, (rect.centerx - t1.get_width() // 2, rect.centery - 22))
    s.blit(t2, (rect.centerx - t2.get_width() // 2, rect.centery + 4))


def draw_detail(s, save, gun, fonts):
    _font_title, _font_sub = fonts
    rect = panel_rect()
    panel_bg(s, rect)

    # ---- 抬头：枪名贴图 + 弹种说明 ----
    #   就有 30~40 px 高 ⇒ 弹种说明直接压在标题下缘，再往下顶进「威力」行，
    #   「武器那边有文字重叠的问题 比如全自动武器」）。
    #   永远不会压到第一条属性行（row1_top 之上留 1px）。
    title = img(gun["title"])
    sub = img(shop(FIRE_TEX.get(gun["fire"], "semi_auto_firearm.png")))
    row1_top = CELL_ROW_Y[0] - 9.0
    cx = rect.centerx
    ty = float(rect.y + 5)
    if title:
        s.blit(title, (int(cx - title.get_width() / 2), int(ty)))
        ty += title.get_height() + 1
    if sub:
        sh_ = sub.get_height()
        if ty + sh_ > row1_top:
            ty = max(float(rect.y + 3), row1_top - sh_ - 1)
        s.blit(sub, (int(cx - sub.get_width() / 2), int(ty)))

    from game import shopui_data

    # 军火库主界面：GunShopLayer::onSelectGun 取存档里的 <gun>_lv（玩家当前等级），
    # setProperty(cur, 0.0, 0) —— next 传 0，所以只点亮当前等级那一段。
    lv = save.weapon_level(gun["name"])
    cur_vals, _next_vals = shopui_data.attr_cells(gun["name"], lv)
    for i, (tex, val) in enumerate(zip(ATTR_TEX, cur_vals)):
        cy = CELL_ROW_Y[i]
        lab = img(shop(tex))
        if lab:
            s.blit(
                lab,
                (int(rect.x + ATTR_LABEL_RIGHT - lab.get_width()), int(cy - lab.get_height() / 2)),
            )
        _draw_cells(s, CELL_X, cy, val, 0.0)

    # ---- 弹药行（GunShopLayer::init @0x136e9c 尾段，反编译 137116-137152）----
    # 父节点是 property_bg 面板（v153/v154 就是面板 contentSize 391×238）：
    #   gun_bullets.png   anchor(0,0)    pos = (w*0.10, h*0.17)
    #   EzScoreText "x"   anchor(0,0.5)  pos = (w*0.24, h*0.24) scale 0.93
    #                     —— 文字**就是 "x"**，不是数量
    #   infinit_ammo.png  anchor(0,0)    pos = (w*0.53, h*0.25)
    #   数量节点 (this+107) 是 EzScoreText，文本由 setBulletCount 单独写。
    #   屏幕上就是一条光秃秃的数字；无限弹药那行又被画到面板外
    # ★ 参考帧（shop_bullet.png）里弹药行是「左下角一簇子弹图标 + 右侧余量」，
    #   两者同一条水平线；无限弹药的枪**不画**子弹簇，只留「* 无限弹药 *」。
    owned = save.own_weapon(gun["name"])
    equipped = gun["name"] in save.d["equipped"]

    from game.gun_fx import is_melee as _is_melee

    if owned and not _is_melee(gun["name"]):
        bar = buy_bullet_rect(rect)
        ammo_cy = float(bar.centery)
        icon_w = 0
        ammo_x = int(rect.x + 64)
        fx = gridfont.get_font(0)
        if gun["inf"]:
            inf = img(shop("infinit_ammo.png"))
            if inf:
                s.blit(
                    inf,
                    (int(rect.centerx - inf.get_width() / 2), int(ammo_cy - inf.get_height() / 2)),
                )
        else:
            bullets = img(shop("gun_bullets.png"))
            if bullets:
                bw = max(1, int(bullets.get_width() * 0.62))
                bh = max(1, int(bullets.get_height() * 0.62))
                s.blit(_sc(bullets, (bw, bh)), (ammo_x, int(ammo_cy - bh / 2)))
                icon_w = bw + 8
            left = (
                save.bullet_count(gun["name"])
                if hasattr(save, "bullet_count")
                else int((save.d or {}).get("%s_bullet" % gun["name"], 0))
            )
            if fx:
                fx.draw(s, "x" + str(int(left)), ammo_x + icon_w, ammo_cy, 1.0, align=(0.0, 0.5))

    # ---- 购买条件（GunShopLayer::onSelectGun @0x130b44 / onUnlockGun @0x134bcc）----
    # 反编译原文：
    #   if (def->locked) {
    #       if (unlock_guns 里有这把枪)  → GunItem::unlock（只改外观）
    #       else if (getKeyValue("level",1) < def->unlock_level
    #                && 不在 unlock_guns) → 只显示「解锁」按钮（花 def->unlock_crystal）
    #   }
    # 也就是说：**通关等级够了才能买**；等级不够只能花钻石解锁，
    # 解锁后名字写进 unlock_guns 存档键，之后永久按「已解锁」处理。
    # 「武器有购买条件要通关到多少关，不满足购买条件要花钻石解锁」）。
    need = int(gun.get("unlock_level") or 0)
    locked = save.weapon_locked(gun)

    btns = _draw_buttons(s, gun, owned, equipped, locked=locked)
    if locked and not owned:
        # ★ 解锁条件必须**分两种**写清楚，不能挤成一句文字：
        #   ① 关卡解锁 ② 钻石解锁（带原版钻石图标 + 数量）
        #   再标注要多少」。
        f = pygame.font.SysFont("Microsoft YaHei", 14, bold=True)
        cost = int(gun.get("unlock_crystal") or 0)
        rows = []
        if need > 0:
            rows.append(("text", "关卡解锁：通关第 %d 关" % need))
        if cost > 0:
            rows.append(("crystal", "%d 钻石提前解锁" % cost))
        if not rows:
            rows.append(("text", "尚未解锁"))
        row_h = 20
        plate_w = 0
        for kind, msg in rows:
            plate_w = max(plate_w, f.size(msg)[0] + (26 if kind == "crystal" else 0))
        plate_w += 18
        plate_h = row_h * len(rows) + 8
        top = min(r.top for r in btns.values()) if btns else 0
        px = rect.centerx - plate_w // 2
        py = top - plate_h - 8
        plate = pygame.Surface((plate_w, plate_h), pygame.SRCALPHA)
        plate.fill((10, 8, 20, 190))
        s.blit(plate, (px, py))
        crys = res.load_img("pic/ui/common/crystal.png")
        for i, (kind, msg) in enumerate(rows):
            t = f.render(msg, True, (255, 214, 145))
            sh = f.render(msg, True, (30, 14, 6))
            yy = py + 5 + i * row_h
            xx = px + 9
            if kind == "crystal" and crys:
                s.blit(_sc(crys, (18, 18)), (xx, yy))
                xx += 22
            s.blit(sh, (xx + 1, yy + 1))
            s.blit(t, (xx, yy))
    return btns


def _draw_cells(s, x, cy, cur, nxt=0.0):
    """属性格：反编译 PropertyCells::setProperty1 的分段画法 + 节点树实测几何。

    节点树实测（data/node_tree_shop.json，PropertyCells anchor(0,0.5)）：
      · 12 个 cell_bg     anchor(0,0.5) pos = (i*15,   8.5)  z=1
      · 12 个 cell_shadow anchor(0,0.5) pos = (i*15+3, 4.5)  z=0
      · 前景区（cell_now / cell_now_l / cell_next…）z=4，挂在
        一个 anchor(0.5,0.5) pos=(12.5, 8.5) 的容器里
    cocos y 向上 ⇒ 屏幕 y = 父中心 - 子节点 pos.y。

    PropertyCells::setProperty(this, cur, next, 0) → setProperty1(0, cur, next)：
      · i_8 = 0（当前值）→ 不画 cell_now_r
      · 0 .. int(cur)-1 → cell_now.png（已达成整格）
      · cur 的小数 → cell_now_l.png（半格）
      · int(cur) .. int(next)-1 → cell_next.png（未达成整格）
      · next 的小数 → cell_next_r / cell_next_l
    """
    base = img(ui("common/cell_bg.png"))
    shadow = img(ui("common/cell_shadow.png"))

    cur = max(0.0, min(float(cur), float(CELL_COUNT)))
    nxt = max(0.0, min(float(nxt), float(CELL_COUNT)))

    # z 序（节点树实测）：cell_shadow z=0，cell_bg z=1，前景区 z=4。
    # 影子 x 偏移 +3、y 比底格低 4px（cocos y 向上 ⇒ 屏幕更低），
    # 它只从底格右下角露出来一截。先画影子、再画底格，底格才不会被压暗。
    if shadow:
        _sw, sh = shadow.get_size()
        for i in range(CELL_COUNT):
            s.blit(shadow, (int(x + i * CELL_PITCH + 3), int(cy - 4.5 - sh / 2)))
    if base:
        _bw, bh = base.get_size()
        for i in range(CELL_COUNT):
            s.blit(base, (int(x + i * CELL_PITCH), int(cy - 8.5 - bh / 2)))

    def put(tex, index):
        im = img(ui(tex))
        if im:
            s.blit(im, (int(x + index * CELL_PITCH), int(cy - 8.5 - im.get_height() / 2)))

    i_now = int(cur)
    slot = 0
    # 已达成的整格
    while slot < CELL_COUNT and slot < i_now:
        put("common/cell_now.png", slot)
        slot += 1
    # cur 的小数半格
    if (cur - i_now) > 0.1 and slot < CELL_COUNT:
        put("common/cell_now_l.png", slot)
        slot += 1


def _draw_buttons(s, gun, owned, equipped, locked=False):
    pr = panel_rect()
    ps = panel_scale()
    # y（cocos 顶边）= panel.y − panel.h*0.48，anchor(0,1)
    top_cocos = (PANEL_CY + panel_dy()) - PANEL_H * ps * BTN_DROP
    top = int(sy(top_cocos))
    left = int(PANEL_X)
    btns = {}

    if locked and not owned:
        # 等级不够、也没花钻石解锁 → 原版只留 button_unlock
        # （showGun 里把购买按钮 setVisible(0)+disable）
        entries = [("unlock", "button_unlock.png", 0, False)]
    elif owned:
        entries = [
            ("upgrade", "button_upgrade.png", 0, True),
            ("equip", "button_equip.png", 0 if not equipped else BTN_H, False),
        ]
        # ★ 已拥有且不是无限子弹 → 多一个「买子弹」，放在升级按钮左边一格。
        if not gun.get("inf") and int(gun.get("bullet_cost", 0) or 0) > 0:
            entries.append(("buy_bullet", "gun_buy_bullet_bg.png", 0, "left2"))
    elif int(gun.get("crystal") or 0) > 0 and int(gun.get("coin") or 0) <= 0:
        entries = [("buy_crystal", "button_buy.png", 0, False)]
    else:
        entries = [("buy_coin", "button_buy.png", 0, False)]

    for key, tex, row, is_upgrade in entries:
        if is_upgrade is True:
            x, y = left - BTN_UPGRADE_DX * ps, top
            r = pygame.Rect(int(x), int(y), BTN_W, BTN_H)
        elif is_upgrade == "left2":
            r = buy_bullet_rect(pr)
        else:
            r = pygame.Rect(int(left), int(top), BTN_W, BTN_H)
        sheet = img(shop(tex))
        if sheet:
            im = (
                sheet.subsurface(pygame.Rect(0, row, BTN_W, BTN_H)).copy()
                if sheet.get_height() >= row + BTN_H and sheet.get_width() >= BTN_W
                else sheet
            )
            if im.get_size() != r.size:
                im = _sc(im, r.size)
            s.blit(im, r.topleft)
        if key == "buy_bullet":
            # 弹药购买条：底图上叠「子弹 +N  ¥M」文字（条变窄后自动缩字）
            cnt = int(gun.get("bullet_count", 0) or 0)
            cost = int(gun.get("bullet_cost", 0) or 0)
            label = "买子弹 +%d  %d金币" % (cnt, cost)
            fs = 14
            f = pygame.font.SysFont("Microsoft YaHei", fs, bold=True)
            t = f.render(label, True, (255, 245, 220))
            while t.get_width() > r.w - 10 and fs > 9:
                fs -= 1
                f = pygame.font.SysFont("Microsoft YaHei", fs, bold=True)
                t = f.render(label, True, (255, 245, 220))
            sh = f.render(label, True, (60, 30, 10))
            s.blit(sh, (r.centerx - t.get_width() // 2 + 1, r.centery - t.get_height() // 2 + 1))
            s.blit(t, (r.centerx - t.get_width() // 2, r.centery - t.get_height() // 2))
        btns[key] = r
    return btns


# ------------------------------------------------------------------ 槽位
def slot_rects():
    """ShopItemPanel 82x82，anchor(1,0)。
    x = panel.x + panel.w*0.47*scale − (3−k)*82*1.2*scale，y = H*0.01。
    """
    ps = panel_scale()
    base = PANEL_X + PANEL_W * ps * SLOT_DX
    bottom = sy(SLOT_Y + panel_dy())  # anchor 底边 → 屏幕底
    out = []
    for k in range(SLOT_N):
        w = SLOT_SZ * ps
        right = base - (SLOT_N - 1 - k) * SLOT_PITCH * ps
        out.append(pygame.Rect(int(right - w), int(bottom - w), int(w), int(w)))
    return out


def draw_slots(s, save, selected=None):
    """军火库右下的 4 个武器槽。

    槽位要显示：武器图标、槽序号（1..4）、当前选中这把枪的绿框。
    而且 equipped_weapons() 过滤掉了空槽，槽位和枪对不上号。
    """
    rects = slot_rects()
    panel = img(shop("item_panel.png"))
    equipped = save.equipped_slots() if hasattr(save, "equipped_slots") else save.equipped_weapons()
    for k, r in enumerate(rects):
        if panel:
            s.blit(_sc(panel, r.size), r.topleft)
        nm = equipped[k] if k < len(equipped) else None
        if nm:
            icon = _shop_gun_icon(save, nm)
            if icon:
                sc = min((r.width - 8) / icon.get_width(), (r.height - 8) / icon.get_height(), 1.0)
                iw, ih = int(icon.get_width() * sc), int(icon.get_height() * sc)
                s.blit(_sc(icon, (iw, ih)), (r.centerx - iw // 2, r.centery - ih // 2))
        else:
            # 空槽：写序号，玩家才知道哪个格子是几号
            f = pygame.font.SysFont("Microsoft YaHei", 18, bold=True)
            t = f.render("%d" % (k + 1), True, (190, 180, 215))
            s.blit(t, (r.centerx - t.get_width() // 2, r.centery - t.get_height() // 2))
        if selected and nm == selected:
            select_marks(s, r, outset=3)
    return rects


# ------------------------------------------------------------------ 命中
def hit_tab(rects, pos):
    for tid, r in rects.items():
        if r.collidepoint(pos):
            return tid
    return None


def hit_slot(rects, pos):
    for i, r in enumerate(rects):
        if r.collidepoint(pos):
            return i
    return None
