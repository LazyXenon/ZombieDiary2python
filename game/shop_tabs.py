"""军火库的士兵 / 技能 / 机甲 三个页签。

几何全部照抄模拟器原版 854x480 布局（截图实测，换算自 1280x720）：
  * 士兵页：左侧三条属性条（生命/速度/装甲）、中央聚光灯士兵形象 + 名字、
             底部 7 个士兵头像格、右侧「升级」按钮
  * 技能页：左侧 2 列技能卡（带价格）、右侧详情面板 + 「购买」按钮、
             底部 3 个空槽
  * 机甲页：左侧三条属性条、中央机甲形象 + 名字、底部机甲头像格、
             右侧「购买」按钮
"""

import contextlib
import math

import pygame

from engine import gridfont, res
from game.battle_summons import MECH_ANIM_FPS as _MECH_FPS
from game.ninecell import draw_9cell_atlas, fill_panel
from game.shop_character import CHAR_POS, draw_soldier_character
from game.shop_extra import (
    ABILITIES,
    load_mech_actors,
    load_soldier_actors,
    load_soldier_upgrades,
    name2icon,
)


#   9 宫格深紫底板（半透明 + 银白描边 + 四角蓝块），尺寸沿用原面板，
#   所以布局坐标不用动。
BG9 = "pic/ui/dialog/9cell_bg.png"


def panel_bg(s, rect):
    fill_panel(s, BG9, rect, (40, 30, 58, 200), 1.0)
    draw_9cell_atlas(s, BG9, rect, 1.0)


W, H = 854, 480

# --- 通用素材 ---
UP_BAR = "pic/ui/shop/up_bar.png"
BACK_TEX = "pic/ui/shop/button_back.png"
ITEM_PANEL = "pic/ui/shop/item_panel.png"
PROPERTY_BG = "pic/ui/shop/property_bg.png"
BUY_TEX = "pic/ui/shop/button_buy.png"
EQUIP_TEX = "pic/ui/shop/button_equip.png"
CELL_BG = "pic/ui/common/cell_bg.png"
CELL_NOW = "pic/ui/common/cell_now_l.png"
# ★ 属性格的「已达成整格」贴图（原版 PropertyCells::setProperty1 用的 cell_now.png）
CELL_NOW_FULL = "pic/ui/common/cell_now.png"
# ★ 士兵页三条属性的标签贴图（原版 SoldierShopLayer 用的是图片，不是系统字）
ATTR_LABEL_TEX = (
    "pic/ui/shop/text_blood.png",
    "pic/ui/shop/text_speed.png",
    "pic/ui/shop/text_armor.png",
)
COIN = "pic/ui/common/coin.png"
CRYSTAL = "pic/ui/common/crystal.png"
SOLDIER_ICON = "pic/ui/soldier_icon/%s.png"
MECH_ICON = "pic/ui/mech_icon/%s.png"
ABILITY_ICON = "pic/ui/shop/ability_%s.png"
ABILITY_NUM = "pic/ui/shop/ability_num_%d.png"
ABILITY_BG = "pic/ui/shop/abilitiy_bg.png"
# 原版 AbilityItem::setBought 用的「已购买」绿勾（z=3，加弹性缩放动画）
BOUGHT_TEX = "pic/ui/shop/gun_bought.png"
SOLDIER_NAME = "pic/ui/soldier_pub/text_soldier_name_%02d.png"
MECH_NAME = "pic/ui/soldier_pub/text_soldier_name_%02d.png"

# --- 顶栏页签（与 game/shopui.py 一致） ---
TAB_Y = 45.0
BACK_BOTTOM = 14.0
TAB_RATIOS = (0.20, 0.40, 0.60, 0.80)
TABS = (
    ("soldier", "soldier_icon.png"),
    ("gun", "gun_icon.png"),
    ("ability", "ability_icon.png"),
    ("mech", "mech_icon.png"),
)

# --- 属性条（左上）---
# ★ 原版 SoldierShopLayer（sub_140964 @0x140964）的公式：
#     v82 = this+96 = 屏幕宽 W(853.33)   v2 = this+100 = 屏幕高 H(480)
#     this+420 = scale（854/480=1.779 → 1.0）
#     v83 = W * 0.145               标签 x
#     v86 = H * 0.77                生命行 y（cocos 向上）
#     v91 = LOGIC*5  * scale        标签→格子间距
#     v93 = LOGIC*30 * scale        行距
#     v92 = v83 + v91               格子 x
#     格子步进 = cell_bg.png 宽 25 * 0.6 = 15
#     格子 scale = this+420 = 1.0
#   ⇒ 屏幕坐标（cocos y 向上 → 屏幕 y 向下）：
#     标签 x = 123.7      格子 x = 128.7
#     生命 y = 480 − 369.6 = 110.4
#     速度 y = 480 − 399.6 =  80.4
#     装甲 y = 480 − 429.6 =  50.4
#     正好撞上「天赋技能：」标题（y 190..220），画面上就是白色大字
#   ★ 原版的 110/80/50 也不能照抄：装甲行 y=50 会顶进军火库顶栏
#     （页签条可见区 0..58）。整组下移 40px ⇒ 生命 90 / 速度 120 / 装甲 150，
#     全部落在顶栏之下（≥58）、天赋技能标题之上（<190）。
#   ★ 顺序必须是「生命在上一行、装甲在最下一行」—— 原版截图 F_shop_soldier
#   整组收紧到 x=82..306 的左上角，与中央展示区（x≥315）完全分离。
#   12 格仍在（数值上限不变）：140 + 11*14 + 12 = 306。
ATTR_ROW_Y = (100.0, 140.0, 180.0)  # 生命 / 速度 / 装甲 三行的屏幕 y
ATTR_LABEL_X = 132.0  # 标签右缘；50px 标签占 x=82..132
ATTR_CELL_SCALE = 0.64
ATTR_CELL_W = 12
ATTR_CELL_H = 10
ATTR_CELL_PITCH = 14.0
ATTR_CELL_COUNT = 12
ATTR_BAR_X = 140.0  # 第一格 x

# 士兵页 / 机甲页属性格配色（对 F_shop_soldier.png 逐像素采样）：
#   点亮 = 墨绿斜条；未点亮 = 淡粉紫（原版用的 cell_null，本地素材包没导出，
#   这里用 cell_bg 按同色重染近似）。
# ★ 早期填的 (62,142,80)→(152,238,158) 是按肉眼估的「亮绿」，参考帧里点亮格
#   主色只有 #386848 / #406848（≈(56,104,72)），照抄后整排属性格像开了荧光，
#   和原版那种压在暗背景里的墨绿完全不是一回事。
ATTR_LIT_GREEN = ((120, 205, 130), (55, 145, 85))
ATTR_OFF_PINK = ((208, 190, 204), (150, 138, 170))

# --- 底部头像格 ---
SLOT_SIZE = 82
SLOT_Y = 480 - 82 - 8
SLOT_X0 = 128
SLOT_PITCH = 100


def _img(name):
    return res.load_img(name)


def _btn(name, row=0):
    """按钮贴图按帧切。

    button_equip.png 是 **170×96 的两帧竖排**（第 0 帧普通、第 1 帧选中），
    button_buy / button_select / button_upgrade / button_unlock 是 170×48 单帧。
    早先直接 blit 整张 96 高的图 ⇒ 按钮比原版高一倍，压住了下面一排东西
    """
    im = _img(name)
    if not im:
        return None
    w, h = im.get_size()
    if h >= 96:
        im = im.subsurface(pygame.Rect(0, 48 * row, w, 48)).copy()
    return im


_USE_BTN = None


def _use_btn():
    """角色页的「使用」按钮（原版印的是「装备」）。

    **button_empty.png**（170×48，同款橙红立体底、不带字），直接用它打底
    就干净了。
    """
    global _USE_BTN
    if _USE_BTN is not None:
        return _USE_BTN or None
    base = _img("pic/ui/shop/button_empty.png") or _img("pic/ui/shop/button_blank.png")
    if not base:
        _USE_BTN = False
        return None
    im = base.copy()
    w, h = im.get_size()
    f = pygame.font.SysFont("Microsoft YaHei", max(15, int(h * 0.50)), bold=True)
    t_fg = f.render("使用", True, (255, 251, 240))
    t_sh = f.render("使用", True, (118, 30, 20))
    cx = w // 2 - t_fg.get_width() // 2
    cy = h // 2 - t_fg.get_height() // 2
    # 原版中文字的写法：深红描边 + 字身微微下沉的硬阴影
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (1, 3), (-1, 3)):
        im.blit(t_sh, (cx + dx, cy + dy))
    im.blit(t_fg, (cx, cy))
    _USE_BTN = im
    return im


_MAXED_BTN = None


def _maxed_btn():
    """满级后替换「升级」按钮的禁用态：同款橙红底压成灰紫 + 印「已满级」。

    写在 ur.bottom+4 —— 用户连报两条：「升级按钮这个白框去掉」「已满级和
    使用按键重合了」。描边就是那个白框（它比按钮大一圈、四角还露在橙色
    底板外面），而 ur.bottom+4 = 292 正压在下面「使用」按钮（297.6）的顶上。
    现在禁用态直接换一张干净的空底按钮、字印在按钮里面，不再外挂任何东西。
    """
    global _MAXED_BTN
    if _MAXED_BTN is not None:
        return _MAXED_BTN or None
    base = _img("pic/ui/shop/button_empty.png") or _img("pic/ui/shop/button_blank.png")
    if not base:
        _MAXED_BTN = False
        return None
    im = base.copy()
    w, h = im.get_size()
    try:
        grey = pygame.transform.grayscale(im)
    except Exception:
        grey = im.copy()
    im = grey
    # 去饱和后偏冷一点点（灰中带蓝紫），和原始橙红区分开
    tint = pygame.Surface((w, h), pygame.SRCALPHA)
    tint.fill((96, 92, 116, 46))
    im.blit(tint, (0, 0))
    f = pygame.font.SysFont("Microsoft YaHei", max(14, int(h * 0.46)), bold=True)
    t_fg = f.render("已满级", True, (232, 230, 240))
    t_sh = f.render("已满级", True, (58, 54, 66))
    cx = w // 2 - t_fg.get_width() // 2
    cy = h // 2 - t_fg.get_height() // 2
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (1, 3), (-1, 3)):
        im.blit(t_sh, (cx + dx, cy + dy))
    im.blit(t_fg, (cx, cy))
    _MAXED_BTN = im
    return im


def _blit_center(s, img, cx, cy):
    if img:
        s.blit(img, (int(cx - img.get_width() / 2), int(cy - img.get_height() / 2)))


def draw_top_bar(s, active):
    """顶栏 + 5 个页签 + 返回按钮（与军火库页共用）。"""
    rects = {}
    bar = _img(UP_BAR)
    if not bar:
        return rects
    bw, bh = bar.get_size()
    s.blit(bar, (0, 0))
    for i, (tid, tex) in enumerate(TABS):
        tile = _img("pic/ui/shop/" + tex)
        if not tile:
            continue
        tw, th = tile.get_width(), tile.get_height() // 2
        row = 0 if tid == active else th
        sub = tile.subsurface(pygame.Rect(0, row, tw, th)).copy()
        dx = bw * TAB_RATIOS[i] - tw / 2
        r = pygame.Rect(int(dx), int(bh - (TAB_Y + th)), tw, th)
        s.blit(sub, r.topleft)
        rects[tid] = r
    back = _img(BACK_TEX)
    if back:
        im = pygame.transform.smoothscale(
            back, (int(back.get_width() * 0.85), int(back.get_height() * 0.85))
        )
        pos = (0, int(H - BACK_BOTTOM - im.get_height()))
        s.blit(im, pos)
        rects["back"] = pygame.Rect(pos[0], pos[1], im.get_width(), im.get_height())
    return rects


_FIT_CACHE = {}


def _fit(name, w=None, h=None, scale=None):
    """按名字取图并缩放（带缓存），属性条每帧要画 3 标签 + 36 格。"""
    im = _img(name)
    if not im:
        return None
    if scale is not None:
        w = max(1, int(round(im.get_width() * scale)))
        h = max(1, int(round(im.get_height() * scale)))
    key = (name, w, h)
    got = _FIT_CACHE.get(key)
    if got is None:
        got = pygame.transform.smoothscale(im, (w, h))
        _FIT_CACHE[key] = got
    return got


def _recolor(name, w, h, top, bottom, key=""):
    """把一张格子贴图重染成「上 top → 下 bottom」的竖向渐变，形状沿用原 alpha。

    原版士兵页的格子是绿色斜条、未点亮的是淡粉紫，而本地素材包只有橙色
    cell_now / 紫灰 cell_bg（cell_null.png 没导出）。直接 BLEND_RGBA_MULT
    乘不出比原图更亮的绿，所以这里先把贴图 rgb 抬成纯白（只留 alpha 当蒙版），
    再乘上渐变层 —— 得到同形状、任意配色的格子。
    """
    base = _fit(name, w, h)
    if not base:
        return None
    ck = ("recolor", name, w, h, top, bottom, key)
    got = _FIT_CACHE.get(ck)
    if got is not None:
        return got
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        t = y / float(max(1, h - 1))
        col = (
            int(top[0] + (bottom[0] - top[0]) * t),
            int(top[1] + (bottom[1] - top[1]) * t),
            int(top[2] + (bottom[2] - top[2]) * t),
        )
        pygame.draw.line(out, (*col, 255), (0, y), (w, y))
    mask = base.convert_alpha()
    mask.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGB_MAX)
    out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    _FIT_CACHE[ck] = out
    return out


def draw_attr_bars(
    s,
    values,
    labels=("生 命", "速 度", "装 甲"),
    colors=((255, 150, 60), (90, 200, 255), (200, 120, 255)),
    preview_color=(60, 130, 235),
    total=None,
    label_tex=None,
    rows=None,
    label_x=None,
    bar_x=None,
    pitch=None,
    tint=None,
    cell_w=None,
    cell_h=None,
    label_scale=0.86,
):
    # 左上三条属性格（生命 / 速度 / 装甲）。values: [(已点亮格数, 预览格数), ...]
    # 全部照原版 SoldierShopLayer（sub_140964 @0x140964）：
    #   标签 text_blood/text_speed/text_armor.png，anchor(1,0.5)
    #   格子 PropertyCells，x = 标签右缘 + 一格步进
    # label_tex 允许换一套标签（机甲页第二行是「威力」不是「速度」）。
    # tint=(lit_top,lit_bottom,off_top,off_bottom) 可整套换色（士兵页是绿色）。
    if total is None:
        total = ATTR_CELL_COUNT
    rows = rows or ATTR_ROW_Y
    label_x = ATTR_LABEL_X if label_x is None else label_x
    bar_x = ATTR_BAR_X if bar_x is None else bar_x
    pitch = ATTR_CELL_PITCH if pitch is None else pitch
    tex = label_tex or ATTR_LABEL_TEX
    cw = ATTR_CELL_W if cell_w is None else cell_w
    ch = ATTR_CELL_H if cell_h is None else cell_h
    if tint:
        lit_t, lit_b, off_t, off_b = tint
        now = _recolor(CELL_NOW_FULL, cw, ch, lit_t, lit_b)
        bg = _recolor(CELL_BG, cw, ch, off_t, off_b)
    else:
        bg = _fit(CELL_BG, cw, ch)
        now = _fit(CELL_NOW_FULL, cw, ch)
    prev = None
    if now:
        prev = now.copy()
        # 预览格 = 点亮色再压暗一点，和「已拥有」区分开
        prev.fill((*preview_color, 255), special_flags=pygame.BLEND_RGBA_MULT)
    for row, (n_lit, n_next) in enumerate(values):
        if row >= len(rows):
            break
        y = rows[row]
        # 标签贴图：anchor(1.0, 0.5)，右缘贴到 label_x
        lab = _fit(tex[row], scale=label_scale) if row < len(tex) else None
        if lab:
            s.blit(
                lab, (int(round(label_x - lab.get_width())), int(round(y - lab.get_height() / 2)))
            )
        else:
            f = pygame.font.SysFont("Microsoft YaHei", 15, bold=True)
            t = f.render(labels[row], True, colors[row])
            s.blit(t, (int(label_x - t.get_width()), int(y - t.get_height() / 2)))
        for i in range(total):
            x = bar_x + i * pitch
            im = None
            if i < n_lit and now:
                im = now
            elif n_lit <= i < n_lit + n_next and prev:
                im = prev
            elif bg:
                im = bg
            if im is None:
                continue
            s.blit(im, (int(round(x)), int(round(y - im.get_height() / 2))))


def draw_select_marks(s, r, outset=2):
    """选中态：原版 select_box.png 的四个绿色三角箭头，套在 r 外面。

      用户原话「这个绿框太丑了」。素材包里本来就有 select_box.png
      （100×100，四角绿色三角，原版军火库/技能格都用它），换回来。
    ★ 现在统一走 shopui.select_marks：同一套绿三角 + 呼吸闪烁，
      军火库底部武器槽也用它，避免两处选中态长得不一样。
    """
    from game.shopui import select_marks

    select_marks(s, r, outset=outset)


def draw_slot_row(s, icons, selected=0, size=SLOT_SIZE, x0=SLOT_X0, pitch=SLOT_PITCH, y=None):
    """底部头像格行：选中项套原版 select_box 四角箭头。"""
    panel = _img(ITEM_PANEL)
    y = SLOT_Y if y is None else y
    rects = []
    for i, icon in enumerate(icons):
        r = pygame.Rect(int(x0 + i * pitch), int(y), size, size)
        if panel:
            s.blit(pygame.transform.smoothscale(panel, r.size), r.topleft)
        if icon:
            im = pygame.transform.smoothscale(icon, (size - 8, size - 8))
            s.blit(im, (r.x + 4, r.y + 4))
        if i == selected:
            draw_select_marks(s, r)
        rects.append(r)
    return rects


# ================================================================== 士兵页
SOLDIER_STATS = (("blood", "生命"), ("speed", "速度"), ("armor", "装甲"))


def draw_soldier(s, save, font=None, frame=0, preview=None):
    """士兵页。返回命中矩形。

    preview: 预览中的士兵序号（None = 用存档里已装备的）。
    点底部头像只切换**预览**，点「购买 / 使用」才真正落盘 ——
    """
    rects = {}
    actors = load_soldier_actors()
    ups = load_soldier_upgrades()
    cur = save.soldier_name()
    #   stand 循环一秒播 6 圈多，画面上就是高频抽搐（体感像低帧率）。
    #   现在统一交给 draw_soldier_character 按 stand 的自然时长（0.6s）采样。
    frame = 0

    # 底部头像行
    icons = [_img(SOLDIER_ICON % a["name"]) for a in actors]
    if preview is None:
        sel = next((i for i, a in enumerate(actors) if a["name"] == cur), 0)
    else:
        sel = max(0, min(len(actors) - 1, preview))
    rects["slots"] = draw_slot_row(s, icons, sel)
    # ★ 属性条必须按**当前预览角色**算，不是存档里正在用的角色。
    #   原版 SoldierShopLayer::clickSoldierIcon @0x13f238 点了头像就
    #   setPropertyCells 重算三条属性条，玩家换角色立刻看到数值变化。
    shown_name = actors[sel]["name"] if actors else cur

    # 左上属性条：每条 12 格。
    # ★ 原版 SoldierShopLayer::showSoldier @0x136c?? 调
    #   UpgradeManager::getSoldierLevelDefP(name, 1/2/3, &cur, &next)，
    #   再把这两个值直接交给 PropertyCells::setProperty(cur, next)；
    #   setProperty1 里 `(int)cur` 就是**点亮格数**、`(int)next` 是预览格数，
    #   超过 12 格才钳到 12 —— 所以那一列数字是 pval（1.0~12.0），
    #   不是 250/150/0.03 那种原始属性值。
    lv = save.soldier_levels_of(shown_name)
    values = []
    for kind in ("blood", "speed"):
        table = ups.get(shown_name, {}).get(kind, [])
        lv_now = int(lv.get(kind, 0) or 0)
        cur_p = nxt_p = 0.0
        if table:
            i0 = min(max(0, lv_now), len(table) - 1)
            cur_p = float(table[i0].get("pval", 0) or 0)
            if lv_now + 1 < len(table):
                nxt_p = float(table[lv_now + 1].get("pval", 0) or 0)
        n_lit = max(0, min(ATTR_CELL_COUNT, int(cur_p)))
        n_next = max(0, min(ATTR_CELL_COUNT, int(nxt_p)) - n_lit)
        values.append((n_lit, n_next))
    # 未点亮的格子在原版是淡粉紫斜条，别用深灰直接糊进背景里
    _tint = (ATTR_LIT_GREEN[0], ATTR_LIT_GREEN[1], (176, 112, 132), (100, 60, 82))
    draw_attr_bars(s, values, rows=(ATTR_ROW_Y[0], ATTR_ROW_Y[1]), tint=_tint)
    blue = ((96, 190, 255), (40, 110, 205), (82, 80, 100), (52, 50, 66))
    draw_attr_bars(
        s,
        [(4, 0)],
        label_tex=("pic/ui/shop/talent_skill.png",),
        rows=(ATTR_ROW_Y[2],),
        label_x=ATTR_LABEL_X,
        total=4,
        tint=blue,
        label_scale=0.66,
    )

    idx = sel
    if 0 <= idx < len(actors):
        info = actors[idx]
        name = info["name"]

        # 聚光灯（原版 anchor(0.5,1.0) scale 2.0，pos = (W*0.5, H*0.92)）
        # cocos 纹理 y 向上 → 贴图上下翻转；pygame 直接画原图即可（视觉一致）
        light = _img("pic/ui/shop/soldier_light.png")
        if light:
            lw = int(light.get_width() * 2.0)
            lh = int(light.get_height() * 2.0)
            im = pygame.transform.smoothscale(light, (lw, lh))
            # anchor y=1 → 图片顶边在 pos.y（cocos），屏幕 y = H - pos.y
            s.blit(im, (int(W * 0.5 - lw / 2), int(H - H * 0.92)))

        # 中央角色（骨骼渲染）：把当前携带的第 1 把枪传进去，
        # 让 soldier_1 手上的武器贴图跟着换（不再永远是一把默认枪）。
        _eq = list(save.d.get("equipped") or [])
        _cur_gun = _eq[0] if _eq else None
        draw_soldier_character(s, name, frame=frame, pos=CHAR_POS, gun=_cur_gun)

        desc_tex = name2icon(name + "_desc")
        di = _img(desc_tex) if desc_tex else None
        if di:
            s.blit(di, (int(W * 0.08), int(268 - di.get_height())))

    # ---------------- 右侧按钮（原版 SoldierShopLayer::init @0x13F2B4） ----------------
    # button_buy.png      anchor(0.5,1) pos(W*0.84, H*0.50) → onClickBuyButton
    # button_upgrade.png  anchor(0.5,1) pos(W*0.84, H*0.50) → onUpgradeSoldier
    # button_select.png   anchor(0.5,1) pos(W*0.84, H*0.38) → onClickEquipButton
    # ★ 购买和升级**必须放在同一个位置**：原版 showSoldier @0x13fc5c 是
    #   「未拥有 → 只显示购买；已拥有 → 只显示升级（满级则禁用）」的互斥关系。
    #   而且只在「已拥有且未装备」时才画 ⇒ 玩家正在用的角色没有升级按钮，
    # ★ 装备按钮的位置是 H*0.38（屏幕 y = 297.6），比购买/升级低一指。
    sel_name = actors[sel]["name"] if 0 <= sel < len(actors) else cur
    owned = save.own_soldier(sel_name)
    equipped = save.soldier_name() == sel_name

    _r_y = int(H - H * 0.50)  # 购买 / 升级：屏幕 y = 240
    _e_y = int(H - H * 0.38)  # 装备：屏幕 y = 297.6

    if not owned:
        buy = _btn("pic/ui/shop/button_buy.png")
        if buy:
            r = pygame.Rect(
                int(W * 0.84 - buy.get_width() / 2), _r_y, buy.get_width(), buy.get_height()
            )
            s.blit(buy, r.topleft)
            rects["buy"] = r
    else:
        _lv = save.soldier_levels_of(sel_name)
        _maxed = all(int(_lv.get(k, 0)) >= 3 for k in ("blood", "speed", "armor"))
        ug = _btn("pic/ui/shop/button_upgrade.png")
        if ug:
            ur = pygame.Rect(
                int(W * 0.84 - ug.get_width() / 2), _r_y, ug.get_width(), ug.get_height()
            )
            if _maxed:
                # 三条属性全满 → 原版 disable（不接收点击）。
                # ★ 禁用态整颗换掉：灰底「已满级」按钮，不再给「升级」外挂
                #   描边、也不再往下写一行字（会和「使用」按钮压在一起）。
                mb = _maxed_btn()
                if mb:
                    s.blit(pygame.transform.smoothscale(mb, ur.size), ur.topleft)
                else:
                    s.blit(ug, ur.topleft)
            else:
                s.blit(ug, ur.topleft)
                rects["upgrade"] = ur
        if not equipped:
            eq = _use_btn()
            if eq:
                er = pygame.Rect(
                    int(W * 0.84 - eq.get_width() / 2), _e_y, eq.get_width(), eq.get_height()
                )
                s.blit(eq, er.topleft)
                rects["equip"] = er
        # 已在用这个角色时原版隐藏装备按钮，头像上的绿框就是状态指示

    # 价格（原版 EzScoreText，画在购买按钮正上方；0.55H → 屏幕 y 216）
    if 0 <= idx < len(actors):
        info = actors[idx]
        if not save.own_soldier(info["name"]):
            amount = info["cost_coin"] or info["cost_crystal"]
            if amount:
                tex = COIN if info["cost_coin"] else CRYSTAL
                icon = _img(tex)
                f = pygame.font.SysFont("Microsoft YaHei", 24, bold=True)
                col = (255, 214, 90) if info["cost_coin"] else (120, 210, 255)
                t = f.render(str(amount), True, col)
                sh = f.render(str(amount), True, (40, 18, 6))
                iw = 30 if info["cost_coin"] else 32
                ih = 30 if info["cost_coin"] else 24
                total_w = iw + 6 + t.get_width()
                cx = int(W * 0.84 - total_w / 2)
                cy = int(H - H * 0.55) - t.get_height() // 2
                if icon:
                    s.blit(
                        pygame.transform.smoothscale(icon, (iw, ih)),
                        (cx, cy + (t.get_height() - ih) // 2),
                    )
                s.blit(sh, (cx + iw + 7, cy + 3))
                s.blit(t, (cx + iw + 6, cy + 2))
            else:
                f = pygame.font.SysFont("Microsoft YaHei", 20, bold=True)
                t = f.render("免费", True, (140, 255, 150))
                s.blit(
                    t, (int(W * 0.84 - t.get_width() / 2), int(H - H * 0.55) - t.get_height() // 2)
                )
    return rects


# ================================================================== 技能页
# 反编译依据：
#   AbilityShopLayer::init            @0x13aa38
#   AbilityItem::init                 @0x13a020
#   AbilityItem::initCoinOrCrystal    @0x139fc0
#   AbilityItem::node                 @0x13a190
#   AbilityShopLayer::initAbilityItems @0x137f00
# 缩放分支（init）：ratio = W/H
#   < 1.4 → scale 0.87, dy = H*0.02,   面板 y 偏移 H*0.04
#   < 1.6 → scale 0.95, dy = H*0.006,  面板 y 偏移 0
#   其余  → scale 1.00, dy = 0,         面板 y 偏移 0    ← 854/480 = 1.779
# 布局（全部以 scale 为外乘）：
#   详情面板 property_bg.png
#       锚点默认(0.5,0.5)，pos(W*0.74, H*0.535 + 面板dy)，setScale(scale)
#   技能滚动区 ScrollNode
#       contentSize (W*0.37, H*0.87)，anchor(1,0.5)
#       pos(面板右缘 - 面板宽*0.635, H*0.44 + dy)，setScale(scale*0.95)
#       比例 >1.7 再右移 15，>1.66 右移 10
#   技能卡片 AbilityItem
#       abilitiy_bg.png 162×110，anchor(0,1)，pos(0, h)
#       卡片节点 contentSize = 底图尺寸，anchor(0.5,0.5)
#       图标 ability_<name>.png anchor(0.5,1.0) pos(w*0.5, h*0.85)
#       价格节点 anchor(0.5,0.0) pos(w*0.43, h*0.16) scale 0.5
#         金币：coin.png anchor(0,0.54) pos(0, h*0.5)，数字 font1 scale 1.6 pos(w, h*0.5)
#         钻石：crystal.png anchor(0,0.5) pos(0, h*0.5)，数字 font3 scale 1.6 pos(w, h*0.5)
#   购买按钮 button_buy.png   anchor(0,1) pos(面板x, 面板底 - 面板高*0.48) scale
#   装备按钮 button_equip.png anchor(0,1) pos(面板x - LOGIC*180*scale, 同上)  scale
ABILITY_SCALE_14 = 0.87
ABILITY_SCALE_16 = 0.95
ABILITY_SCALE_DEFAULT = 1.0
ABILITY_SCROLL_W_RATIO = 0.37
ABILITY_SCROLL_H_RATIO = 0.87
ABILITY_PANEL_X = 0.74
ABILITY_PANEL_Y = 0.535
ABILITY_SCROLL_X_OFFSET = 0.635  # 面板右缘 - 面板宽*该值
ABILITY_SCROLL_Y = 0.44
ABILITY_CELL_SCALE = 0.95
ABILITY_SLOT_COUNT = 3  # 右侧 3 个装备格

# 技能中文名（ABILITIES 里的 title 是英文资源名，直接显示玩家看不懂）
ABILITY_CN = {
    "hp_1": "治疗药水 I",
    "hp_2": "治疗药水 II",
    "shield_1": "防御护盾 I",
    "shield_2": "防御护盾 II",
    "power_1": "力量药水 I",
    "power_2": "力量药水 II",
    "speed_1": "急速药水 I",
    "speed_2": "急速药水 II",
    "airstrike": "空中支援",
    "invisible": "隐身",
    "mech_1": "召唤机甲 1",
    "mech_3": "召唤机甲 3",
    "mech_4": "召唤机甲 4",
    "mech_5": "召唤机甲 5",
    "mech_7": "召唤机甲 7",
    "mech_8": "召唤机甲 8",
    "mech_9": "召唤机甲 9",
    "mech_10": "召唤机甲 10",
    "fly_1": "无人机 1",
    "fly_2": "无人机 2",
}


def ability_desc(key):
    """技能说明文案：数值直接取自战斗里真正生效的 ABILITY_DEFS。

    p1/p2 的含义见 battle.py::apply_ability —— 护盾 p1 是**百分比减伤**
    （1.0 = 免疫），加速/力量 p1 是加成比例（0.5 = +50%），hp 的 p1 是
    回复的最大生命比例。写死文案容易和战斗表现对不上，所以在这里算。
    """
    from game.battle_abilities import ABILITY_DEFS

    p1, p2 = ABILITY_DEFS.get(key, (0.0, 0.0))
    pp = int(round(p1 * 100))
    if key.startswith("hp"):
        return ["立即恢复 %d%% 生命值" % pp, "血量见底时能直接保命"]
    if key.startswith("shield"):
        if pp >= 100:
            return ["完全免疫僵尸伤害", "持续 %d 秒" % int(p2)]
        return ["受到伤害减少 %d%%" % pp, "持续 %d 秒" % int(p2)]
    if key.startswith("speed"):
        return ["移动速度 +%d%%" % pp, "持续 %d 秒" % int(p2)]
    if key.startswith("power"):
        return ["攻击力 +%d%%" % pp, "持续 %d 秒" % int(p2)]
    if key == "airstrike":
        return ["呼叫空中支援全覆盖轰炸", "持续 %d 秒" % int(p2)]
    if key.startswith("mech"):
        return ["召唤机甲骑乘作战", "持续 %d 秒，耐久归零离场" % int(p2)]
    if key.startswith("fly"):
        return ["无人机跟随自动开火", "持续 %d 秒" % int(p2)]
    return []


def ability_scale():
    """init 的缩放分支：返回 (卡片/面板缩放, 滚动区 y 偏移, 面板 y 偏移)。"""
    r = W / float(H) if H else 1.0
    if r < 1.4:
        return ABILITY_SCALE_14, H * 0.02, H * 0.04
    if r < 1.6:
        return ABILITY_SCALE_16, H * 0.006, 0.0
    return ABILITY_SCALE_DEFAULT, 0.0, 0.0


def ability_price(item):
    """AbilityItemDef 的 (coin, crystal)。"""
    return int(item[4]), int(item[5])


def ability_view_rect():
    """左列技能滚动区（屏幕矩形）。"""
    scale, dy, _panel_dy = ability_scale()
    panel = _img(PROPERTY_BG)
    if panel:
        # v13 = 面板的**位置 x**（不是右缘），v49 = 面板x − 面板宽*0.635。
        # 滚动区 anchor(1,0.5) → 右缘就落在 v49，整块在面板左侧。
        pw = panel.get_width() * scale
        right = W * ABILITY_PANEL_X - pw * ABILITY_SCROLL_X_OFFSET
        r = W / float(H) if H else 1.0
        if r > 1.7:
            right += 15.0
        elif r > 1.66:
            right += 10.0
    else:
        right = W * 0.46
    w = W * ABILITY_SCROLL_W_RATIO * scale
    h = H * ABILITY_SCROLL_H_RATIO * scale
    # ScrollNode anchor(1,0.5)：中心 cocos y = H*0.44+dy，屏幕 y = H - 该值
    center_y = H - (H * ABILITY_SCROLL_Y + dy)
    return pygame.Rect(int(right - w), int(center_y - h / 2), int(w), int(h))


def draw_ability(s, save, font=None, sel=0, scroll=0.0):
    """技能页。返回命中矩形。sel = 选中的技能序号。"""
    rects = {"cards": [], "slots": [], "buy": None, "equip": None, "unequip": None}
    scale, dy, panel_dy = ability_scale()
    coin = _img(COIN)
    crystal = _img(CRYSTAL)

    # ---------------- 右侧详情面板 ----------------
    panel = _img(PROPERTY_BG)
    pr = None
    if panel:
        pw = int(panel.get_width() * scale)
        ph = int(panel.get_height() * scale)
        pcx = W * ABILITY_PANEL_X
        pcy = H * ABILITY_PANEL_Y + panel_dy
        pr = pygame.Rect(int(pcx - pw / 2), int(H - pcy - ph / 2), pw, ph)
        panel_bg(s, pr)
        rects["panel"] = pr

    # ---------------- 左侧技能滚动区 ----------------
    view = ability_view_rect()
    cell_scale = scale * ABILITY_CELL_SCALE
    bg = _img("pic/ui/shop/abilitiy_bg.png")
    cw_raw, ch_raw = bg.get_size() if bg else (162, 110)
    cell_w = cw_raw * cell_scale
    cell_h = ch_raw * cell_scale

    # ScrollNode::addCell —— 本滚动区 this[65] = 2，即 **2 列网格**：
    #   x = (gapX + cellW) * (i % 2)
    #   y = -((gapY + cellH) * (i // 2) + cellH)
    # 两个 gap 都是 10（ScrollNode 构造 this[66] = this[67] = 10.0f）。
    cols = 2
    gap = 10.0 * cell_scale
    rows = (len(ABILITIES) + cols - 1) // cols
    total = rows * (cell_h + gap)
    scroll = max(0.0, min(max(0.0, total - view.h), scroll))
    owned_ab = save.d.get("abilities") or {}
    equipped_set = set(save.d.get("owned_abilities") or [])
    s.set_clip(view)
    for i, item in enumerate(ABILITIES):
        cx = (gap + cell_w) * (i % cols)
        cy = (gap + cell_h) * (i // cols)
        r = pygame.Rect(int(view.left + cx), int(view.top + cy - scroll), int(cell_w), int(cell_h))
        if r.bottom > view.top and r.top < view.bottom:
            _draw_ability_cell(
                s,
                r,
                item,
                coin,
                crystal,
                cell_scale,
                selected=(i == sel),
                owned_count=int(owned_ab.get(item[0], 0) or 0),
                equipped=item[0] in equipped_set,
            )
            rects["cards"].append((r, i))
    s.set_clip(None)
    # 滚动区的屏幕矩形：给主循环做滚轮/拖拽命中（不是滚动条，是列表可见区）
    rects["list_view"] = pygame.Rect(view)

    # ---------------- 右侧详情面板：道具名 / 说明 / 按钮 ----------------
    #   标题居中、内容沿面板中轴一列等距、按钮保持官方贴图原始比例、四周留白
    #   bottom−26），但当前面板实际由 9cell_bg 绘制，白描边内侧在
    #   frame_line=(42,37,32,27) ⇒ 手算的 top=pr.y+22 比描边内侧 pr.y+37
    #   还高 15px，标题正好被顶框线穿过；三颗按钮又被 smoothscale 拉成
    #   118×30 的扁条（官方 170×48，比例 3.54 被压成 3.93）并贴住左右与
    #   底边，文字全挤在上半截、中间空一大块。
    #   现在统一用官方 frame_inner 取安全区，整块内容沿中轴居中排布。
    if pr and 0 <= sel < len(ABILITIES):
        from game.ninecell import frame_inner

        inner = frame_inner(BG9, pr, 1.0)
        rects["_inner"] = inner
        old_clip = s.get_clip()

        def centered(text, font, color, y, shadow=(30, 18, 42)):
            im = font.render(text, True, color)
            sh = font.render(text, True, shadow)
            x = pr.centerx - im.get_width() // 2
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                s.blit(sh, (x + dx, y + dy))
            s.blit(im, (x, y))

        def fit_font(text, base, bold=True):
            size = max(9, int(base))
            while size > 9:
                f = pygame.font.SysFont("Microsoft YaHei", size, bold=bold)
                if f.render(text, True, (255, 255, 255)).get_width() <= inner.w - 8:
                    return f
                size -= 1
            return pygame.font.SysFont("Microsoft YaHei", 9, bold=bold)

        kx = pr.w / 391.0
        ky = pr.h / 238.0
        # 按钮按官方 170×48 等比缩放，不再拉伸成扁条；两颗并排时以中轴
        # 成组居中，而不是各自贴住左右描边。
        bw = min(int(146 * kx), max(64, (inner.w - 40) // 2))
        bh = max(24, int(round(bw * 48.0 / 170.0)))
        row_gap = 6
        by2 = inner.bottom - 5 - bh
        by1 = by2 - bh - row_gap

        # try/finally 保证任何分支（含异常）都恢复剪裁，不会污染后续装备格绘制
        try:
            s.set_clip(inner)
            it = ABILITIES[sel]
            title = ABILITY_CN.get(it[0], it[1] if isinstance(it[1], str) and it[1] else it[0])

            ft = fit_font(title, max(13, int(20 * kx)))
            title_y = inner.top + 4
            centered(title, ft, (255, 236, 170), title_y)

            own_n = int((save.d.get("abilities") or {}).get(it[0], 0) or 0)
            sub = ("已拥有 ×%d" % own_n) if own_n else "未购买"
            fs = fit_font(sub, max(10, int(14 * ky)))
            centered(
                sub,
                fs,
                (200, 190, 220) if own_n else (255, 160, 160),
                title_y + max(24, int(26 * ky)),
            )

            lines = ability_desc(it[0])
            line_y = title_y + max(45, int(48 * ky))
            gap = max(15, int(17 * ky))
            if lines:
                gap = min(gap, max(12, (by1 - line_y - 4) // len(lines)))
            for line in lines:
                fd = fit_font(line, max(10, int(14 * ky)))
                centered(line, fd, (222, 214, 240), line_y)
                line_y += gap

            # ---------------- 购买 / 装备（装备后同一颗按钮变「卸下」）----------------
            # 未购买只给「购买」；已拥有未装备给「装备」；装上后原位换成「卸下」。
            # 之前已拥有未装备时同时画了「装备」和「卸下」，没装上也能点卸下。
            sel_name = it[0]
            is_eq = any(
                save.d.get("equipped_ability_%d" % i) == sel_name for i in range(ABILITY_SLOT_COUNT)
            )
            buttons = [(BUY_TEX, "buy", 0)]
            if own_n > 0:
                if is_eq:
                    buttons.append(("pic/ui/shop/button_unequip.png", "unequip", 0))
                else:
                    buttons.append((EQUIP_TEX, "equip", 0))
            for key in ("buy", "equip", "unequip"):
                rects[key] = None
            cx = pr.centerx
            group_w = bw * 2 + row_gap
            mid_y = by1 + (2 * bh + row_gap - bh) // 2
            if len(buttons) == 2:
                positions = [(int(cx - group_w / 2), mid_y), (int(cx + group_w / 2 - bw), mid_y)]
            else:
                positions = [(int(cx - bw / 2), mid_y)]
            for (tex, key, row), (bx, by) in zip(buttons, positions):
                r = pygame.Rect(bx, by, bw, bh)
                rects[key] = r
                im = _btn(tex, row)
                if im:
                    s.blit(pygame.transform.smoothscale(im, r.size), r.topleft)
        finally:
            s.set_clip(old_clip)

    # ---------------- 面板右下 3 个装备格 ----------------
    slot_panel = _img(ITEM_PANEL)
    if pr and slot_panel:
        sw = int(slot_panel.get_width() * scale)
        sh = int(slot_panel.get_height() * scale)
        sy = H - (H * 0.01 + dy) - sh
        by_name = {it[0]: it for it in ABILITIES}
        sel_name = None
        if 0 <= sel < len(ABILITIES):
            sel_name = ABILITIES[sel][0]
        for i in range(ABILITY_SLOT_COUNT):
            # 面板右下角的格子：自右向左排，最后一个贴着面板右缘
            sx = pr.right - (i + 1) * sw * 1.55
            sr = pygame.Rect(int(sx), int(sy), sw, sh)
            s.blit(pygame.transform.smoothscale(slot_panel, (sw, sh)), sr.topleft)
            nm = save.d.get("equipped_ability_%d" % i)
            it = by_name.get(nm) if nm else None
            if it:
                ic = _img(ABILITY_ICON % it[2])
                if ic:
                    k2 = min(sr.w * 0.72 / ic.get_width(), sr.h * 0.72 / ic.get_height())
                    iw = max(1, int(ic.get_width() * k2))
                    ih = max(1, int(ic.get_height() * k2))
                    s.blit(
                        pygame.transform.smoothscale(ic, (iw, ih)),
                        (sr.centerx - iw // 2, sr.centery - ih // 2),
                    )
            else:
                # 空槽：写个序号，玩家才知道哪个槽是 1 号、哪个是 2 号
                fseq = pygame.font.SysFont("Microsoft YaHei", 15, bold=True)
                t = fseq.render("%d" % (i + 1), True, (190, 180, 215))
                s.blit(t, (sr.centerx - t.get_width() // 2, sr.centery - t.get_height() // 2))
            # ★ 当前选中的道具 = 待装备。槽里已有同款时套原版四角箭头，
            #   点它 = 交换（把当前道具挪进这个槽，原有的挪回手上）。
            if it and sel_name and nm == sel_name:
                draw_select_marks(s, sr)
            rects["slots"].append(sr)
    return rects


_FRAME_CACHE = {}


def _card_frame(r):
    """卡片贴图里**可见白框**的屏幕矩形。

    ★ abilitiy_bg.png 是 162×110，但右/下各有 ~15px 是**软阴影**
      （alpha 有值、像素是暗的）。之前角标和价格都按 cell rect 摆 ——
      rect 的右下角落在阴影里，于是「×5」数量角标画到了白框外面，
    """
    if "ink" not in _FRAME_CACHE:
        bg = _img("pic/ui/shop/abilitiy_bg.png")
        ink = None
        if bg:
            w, h = bg.get_size()
            xs, ys = [], []
            for y in range(h):
                for x in range(w):
                    c = bg.get_at((x, y))
                    # 白框：不透明且足够亮；软阴影透明度和它差着量级
                    if c.a > 200 and c.r + c.g + c.b > 420:
                        xs.append(x)
                        ys.append(y)
            if xs:
                ink = (min(xs), min(ys), max(xs), max(ys), w, h)
        _FRAME_CACHE["ink"] = ink
    ink = _FRAME_CACHE["ink"]
    if not ink:
        return r
    x0, y0, x1, y1, w, h = ink
    kx = r.w / float(w)
    ky = r.h / float(h)
    return pygame.Rect(
        r.x + int(x0 * kx), r.y + int(y0 * ky), int((x1 - x0 + 1) * kx), int((y1 - y0 + 1) * ky)
    )


def _draw_ability_cell(s, r, item, coin, crystal, k, selected=False, owned_count=0, equipped=False):
    """AbilityItem::init 的卡片渲染。"""
    _name, _title, icon, _num, c_coin, c_crystal = item
    bg = _img("pic/ui/shop/abilitiy_bg.png")
    if bg:
        s.blit(pygame.transform.smoothscale(bg, r.size), r.topleft)
    if selected:
        sel_img = _img("pic/ui/shop/ability_selected.png")
        if sel_img:
            sw = int(sel_img.get_width() * k)
            sh = int(sel_img.get_height() * k)
            s.blit(
                pygame.transform.smoothscale(sel_img, (sw, sh)),
                (r.centerx - sw // 2, r.centery - sh // 2),
            )

    # 图标：anchor(0.5,1.0) pos(w*0.5, h*0.85)
    # 图标：anchor(0.5,1.0) —— cocos 里 ay=1.0 是**顶边**，不是底边。
    # 卡片内容坐标原点在左下、y 向上，屏幕 y = cardBottom − cocos y。
    # 所以 pos(w*0.5, h*0.85) 指的是图标**顶边中点**落在 h*0.85 处，
    # 图标从该点向下生长；贴图顶 = r.bottom − 0.85h。
    # ★ 价格块改成「图标固定一列、数字往右排」。
    #   原版位图字等宽、按节点宽度居中看不出问题；这里的数字是
    #   「4 / 1250 / 2000」这种宽度不一的串，居中会让每张卡的金币/钻石
    #   「图标缩进不一致」）。现在图标钉在同一列，数字只需跟着走。
    fr = _card_frame(r)
    psc = 0.5 * k
    px = fr.x + fr.w * 0.26
    # 价格行的中线贴着**可见框**的下沿往上收一点：按 cell rect 算会落到
    # 贴图的软阴影上，图标下半截看起来压在描边外。
    py = fr.bottom - max(8, int(fr.h * 0.14))
    if c_coin > 0:
        img, val, fi, ay = coin, c_coin, 1, 0.54
    elif c_crystal > 0:
        img, val, fi, ay = crystal, c_crystal, 3, 0.5
    else:
        img, val, fi, ay = None, 0, 1, 0.5
    # 价格块占的高度：图标高与数字高取大者；图标要落在它上面，不许压字
    price_h = int(img.get_height() * psc) if img else max(10, int(fr.h * 0.12))
    price_top = py - price_h - max(2, int(2 * k))

    # ★ 图标：先按原版 anchor(0.5,1.0) pos(w*0.5, h*0.85) 放，再**整体上提**
    #   道具图上就是这个原因（图标压价格、价格压图标，两层字挤在卡底）。
    #   顺带收 0.90 倍，空出来的一行专门给价格。
    ic = _img(ABILITY_ICON % icon)
    if ic:
        box_top = fr.top + max(3, int(fr.h * 0.06))
        box_bottom = price_top - max(2, int(fr.h * 0.03))
        box_w = fr.w * 0.92
        box_h = max(8, box_bottom - box_top)
        iw0, ih0 = ic.get_size()
        sc = min(box_w / float(iw0), box_h / float(ih0))
        iw = max(1, int(iw0 * sc))
        ih = max(1, int(ih0 * sc))
        s.blit(
            pygame.transform.smoothscale(ic, (iw, ih)),
            (int(r.x + r.w * 0.5 - iw / 2), int(box_bottom - ih)),
        )

    if img:
        f = gridfont.get_font(fi)
        node_h = img.get_height() * psc  # 节点 contentSize 高 = 图标高
        left = px
        node_bottom = py
        iw = max(1, int(img.get_width() * psc))
        ih = max(1, int(img.get_height() * psc))
        # 图标 anchor(0, ay)，pos(0, nodeH*0.5)：锚点落在节点竖直中心线。
        # 顶部偏移 = (1 − ay) * ih（ay 从**底边**量起）。
        mid_y = node_bottom - node_h * 0.5
        s.blit(
            pygame.transform.smoothscale(img, (iw, ih)), (int(left), int(mid_y - ih * (1.0 - ay)))
        )
        if f:
            f.draw(s, str(val), left + iw + max(2, int(2 * k)), mid_y, 1.6 * psc, align=(0.0, 0.5))

    # ★ 原版 AbilityItem::setBought：拥有该道具时在卡片**右上**挂一张
    #   gun_bought.png 绿勾（pos = w*0.85, h*0.85，带弹性缩放）。
    #   这里绿勾表示「已拥有」；「已装备」在下面的槽位里用绿框标。
    # ★ 数量角标（买了几个）跟在绿勾**左边同一行**：
    #   卡片右下角是斜切的软阴影，放那儿会飘到白框外面去（截图里「5」
    #   就悬在卡片旁边的背景上），右上角这一条才是实心橙底。
    if owned_count > 0:
        bought = _img(BOUGHT_TEX)
        bw = bh = 0
        if bought:
            bw = int(bought.get_width() * 0.48)
            bh = int(bought.get_height() * 0.48)
            s.blit(pygame.transform.smoothscale(bought, (bw, bh)), (fr.right - bw - 2, fr.top + 4))
        # 角标跟绿勾共用一条中线，不再一个压线一个悬空
        badge_cy = fr.top + 4 + bh // 2 if bh else fr.top + int(fr.h * 0.2)
        badge_right = fr.right - bw - 6 if bw else fr.right - 8
        _draw_owned_badge(s, fr, owned_count, badge_right, badge_cy)


def _draw_owned_badge(s, frame, owned_count, right, cy):
    """「N」数量角标 —— 位图数字 + 深色描边，不垫底板；右对齐到 right，
    垂直方向以 cy 为中线（和绿勾对齐）。

      白色描边上 —— 截图里卡片右上角像被人抠掉一块，方块中间再塞个「1」
      （用户反馈「图标数量混乱」）。原版 AbilityItem 上根本没有底板。
    ★ 位置从「卡片右下角」改成「右上角绿勾左边」：卡片贴图右下角是斜切
      的软阴影，按 cell rect 摆的角标会飘到白框外面的背景上。
    """
    txt = str(owned_count)  # 位图数字字体只有 0-9，不带 "x"
    k = 0.62
    fnum = gridfont.get_font(5)  # shop_ability_number，技能页专用数字
    if fnum is None:
        f = pygame.font.SysFont("Microsoft YaHei", 15, bold=True)
        t = f.render(txt, True, (255, 236, 150))
        sh = f.render(txt, True, (40, 20, 10))
        bx = right - t.get_width()
        by = cy - t.get_height() // 2
        s.blit(sh, (bx + 1, by + 1))
        s.blit(t, (bx, by))
        return
    nw, nh = fnum.text_size(txt, k)
    nw, nh = int(nw) + 2, int(nh) + 2
    txt_surf = pygame.Surface((nw, nh), pygame.SRCALPHA)
    fnum.draw(txt_surf, txt, 1, 1, k, align=(0.0, 0.0))
    # 用字形剪影做描边：四个方向各偏 1px，再盖上原色
    mask = pygame.mask.from_surface(txt_surf)
    sil = mask.to_surface(setcolor=(38, 18, 8, 255), unsetcolor=(0, 0, 0, 0))
    bx = right - nw
    by = cy - nh // 2
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        s.blit(sil, (bx + dx, by + dy))
    s.blit(txt_surf, (bx, by))


# ================================================================== 机甲页
MECH_STATS = (("blood", "生 命"), ("power", "威 力"), ("speed", "速 度"))

# 机甲名：原版是 Name2IconTex 里的 mech_N_title 贴图（虎鲸 / 血色风暴 /
# 忧郁罗密欧 …），贴图就在 assets/images/pic/ui/shop/，下面这份中文只是
# 贴图万一缺失时的兜底，必须和贴图上的字一致，不能自己另起译名。
MECH_CN = {
    "mech_1": "虎鲸",
    "mech_3": "美洲狮",
    "mech_4": "恐惧凶狼",
    "mech_5": "新星土卫七",
    "mech_7": "狙击机甲 VII",
    "mech_8": "血色风暴",
    "mech_9": "忧郁罗密欧",
    "mech_10": "打击者",
}

MECH_SHOW = pygame.Rect(315, 78, 310, 300)

_MECH_FORM_CACHE = {}
_MECH_ART = {}


def _mech_form(name, soldier=None):
    from game.battle_summons import MechForm

    # 骑乘机甲（美洲狮）预览里坐的是当前角色，缓存 key 得带上角色名
    key = (name, soldier)
    if key in _MECH_FORM_CACHE:
        return _MECH_FORM_CACHE[key]
    try:
        form = MechForm(name, soldier, 0)
    except Exception:
        form = None
    _MECH_FORM_CACHE[key] = form
    return form


def _mech_art(name, show, soldier=None):
    """实测机甲待机动画的**真实像素**包围盒 → 算裁剪后的缩放和脚底位置。

    骨骼自带的 bbox 只按部件注册点算，实际画出来会比 bbox 更大一圈
    （旋转 + u/v 偏移），直接拿 bbox 等比会顶出展示框。这里真渲一遍所有帧
    取非透明像素的并集，缓存起来，只算一次。
    """
    key = (name, show.size, soldier)
    if key in _MECH_ART:
        return _MECH_ART[key]
    form = _mech_form(name, soldier)
    out = None
    if form is not None:
        tmp = pygame.Surface((960, 900), pygame.SRCALPHA)
        ox, oy = 480, 700
        box = None  # 待机 + 开火 的并集（决定画面重心/不出框）
        stand = None  # 只量待机（决定「机体有多高」）
        for st in ("stand", "fire"):
            sk = form.sk.get(st)
            if sk is None or not sk.images or sk.frame_count <= 0:
                continue
            for i in range(sk.frame_count):
                tmp.fill((0, 0, 0, 0))
                sk.render(tmp, i, ox, oy, 1.0)
                r = tmp.get_bounding_rect()
                if r.w <= 0 or r.h <= 0:
                    continue
                box = r.copy() if box is None else box.union(r)
                if st == "stand":
                    stand = r.copy() if stand is None else stand.union(r)
            if box is not None:
                from game.battle_summons import MECH_FORM_SCALE

                ref = stand or box
                k_stand = min(show.w * 0.96 / ref.w, show.h * 0.96 / ref.h)
                k_union = min(show.w * 0.92 / box.w, show.h * 0.94 / box.h)
                k = min(k_stand, k_union * 1.06)
                ssc = k / MECH_FORM_SCALE
                cx = show.centerx - ((box.left + box.right) * 0.5 - ox) * k
                gy = show.centery - ((box.top + box.bottom) * 0.5 - oy) * k
                out = (ssc, int(cx), int(gy))
    _MECH_ART[key] = out
    return out


def draw_mech_preview(s, name, show, save=None):
    """机甲页中央立绘：直接渲染机甲**骨骼**，会待机、会开炮。

    既糊又像「装甲上面坐着个玩家」。现在：
      · 待机 = stand 循环（20fps，和战斗里同一套骨骼）
      · 攻击 = 每 2.6 秒播一次 fire 动画（帧数/20 秒）
    尺寸按实测像素包围盒等比 fit 进展示框，各机甲大小一致。
    骑乘机甲（美洲狮 mech_3）的 ren 部件由 MechForm 填当前玩家的头肩像，
    其余机甲 ren 仍是空白占位。save 用来取当前角色，缺省则画默认小兵。
    """
    soldier = None
    if save is not None:
        try:
            soldier = save.soldier_name()
        except Exception:
            soldier = None
    form = _mech_form(name, soldier)
    art = _mech_art(name, show, soldier)
    if form is None or art is None:
        return False
    ssc, cx, gy = art
    fire = form.sk.get("fire")
    now = pygame.time.get_ticks() / 1000.0
    fdur = max(0.22, fire.frame_count / _MECH_FPS) if fire else 0.0
    cyc = max(2.6, fdur + 1.6)
    ph = now % cyc
    if fire is not None and ph < fdur:
        form.render(s, "fire", ph, cx, gy, ssc)
    else:
        form.render(s, "stand", now, cx, gy, ssc)
    return True


def draw_mech(s, save, font=None, preview=None):
    """机甲页。返回命中矩形。

    preview: 预览中的机甲名（None = 存档里已装备的）。

    原版 MechShopLayer::showMech（sub_13CF58）：
      中央机甲  容器 anchor(0.5,0.5)，scale = 机甲自身 scale * 0.75
      六行参数  标签 pos = (W*0.1, H*0.54/0.48/0.44/0.40/0.36/0.32)
                anchor(0,0.5)；值文本紧跟标签右侧
      名字      mech_N_title 贴图
    """
    rects = {}
    mechs = load_mech_actors()
    cur = preview or save.d.get("equipped_mech") or (mechs[0]["name"] if mechs else None)

    icons = [_img(MECH_ICON % m["name"]) for m in mechs]
    sel = next((i for i, m in enumerate(mechs) if m["name"] == cur), 0)
    rects["slots"] = draw_slot_row(s, icons, sel)
    # ★ 每台机甲的拥有数量（角标）—— 玩家点图标时能直接看到自己有几台。
    for i, m in enumerate(mechs):
        n = save.mech_count(m["name"]) if hasattr(save, "mech_count") else 0
        if n <= 0 or i >= len(rects["slots"]):
            continue
        r = rects["slots"][i]
        fnum = pygame.font.SysFont("Microsoft YaHei", 14, bold=True)
        t = fnum.render("×%d" % n, True, (255, 240, 170))
        sh = fnum.render("×%d" % n, True, (30, 16, 6))
        bx = r.right - t.get_width() - 4
        by = r.top + 4
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            s.blit(sh, (bx + dx, by + dy))
        s.blit(t, (bx, by))

    if not mechs:
        return rects
    m = mechs[sel]

    # 左上属性条（机甲三条：生命/威力/速度，格数 = 属性值）
    # ★ 标签必须跟着 MECH_STATS 走：机甲第二行是「威力」，早先固定用 soldier
    #   的 text_speed ⇒ 机甲页第二行写着「速度」其实画的是威力。
    values = [(min(ATTR_CELL_COUNT, m.get(k, 0)), 0) for k, _ in MECH_STATS]
    draw_attr_bars(
        s,
        values,
        labels=(MECH_STATS[0][1], MECH_STATS[1][1], MECH_STATS[2][1]),
        colors=((255, 150, 60), (90, 200, 255), (200, 120, 255)),
        label_tex=(
            "pic/ui/shop/text_blood.png",
            "pic/ui/shop/text_power.png",
            "pic/ui/shop/text_speed.png",
        ),
    )

    show = MECH_SHOW
    if not draw_mech_preview(s, m["name"], show, save):
        big = _img(MECH_ICON % m["name"])
        if big:
            bw, bh = big.get_size()
            k = min(show.w / bw, show.h / bh)
            iw, ih = max(1, int(bw * k)), max(1, int(bh * k))
            im = pygame.transform.smoothscale(big, (iw, ih))
            s.blit(im, (show.centerx - iw // 2, show.centery - ih // 2))

    # 机甲名字：原版 Name2IconTex 里的 mech_N_title 贴图
    #   （虎鲸 / 血色风暴 / 忧郁罗密欧 …）。name2icon 读不到
    #   data/name2icon.json 时现在会回退到反编译保存的
    #   engine/name2icon.py，贴图能正常显示，不再用自己编的中文名。
    #   名字放在左上数值区下方、五行参数上方。
    mt = name2icon(m["name"] + "_title")
    mi = _img(mt) if mt else None
    # ★ 名字放 232：属性格第三行现在落在 y=180，名字与五行参数
    #   （258 起）之间各留一段空隙，不跟任何格子挤在同一水平线上。
    name_y = 232
    if mi:
        s.blit(mi, (int(W * 0.1), int(name_y - mi.get_height() / 2)))
    else:
        fname = pygame.font.SysFont("Microsoft YaHei", 20, bold=True)
        nm = fname.render(MECH_CN.get(m["name"], m["name"]), True, (255, 214, 120))
        s.blit(nm, (int(W * 0.1), int(name_y - nm.get_height() / 2)))

    # 五行参数（原版 MechShopLayer::getMechDetailedDesc @0x13c478）
    #   数据是原版硬编码的英文串，已逐条抄进 data/mech_desc.json。
    #   ★ **标签和取值全部汉化**（原版是英文，玩家看不懂）。
    desc = _load_mech_desc().get(m["name"])
    if desc:
        f = pygame.font.SysFont("Microsoft YaHei", 15, bold=True)
        # ★ 五行整体下移到名字（232）之下，步进 22：
        #   原版比例 H*0.54 起会顶到名字，且行距 19 太挤。
        rows = (("weight", 0), ("tech", 22), ("class", 44), ("weapon", 66), ("time", 88))
        for key, dy in rows:
            y = 258 + dy
            lab = desc.get("cn_" + key, key)
            t = f.render("%s：" % lab, True, (198, 194, 216))
            s.blit(t, (int(W * 0.1), y - t.get_height() // 2))
            # 取值：能汉化的用中文（class / weapon），其余保留原版数字
            val = desc.get("cn_" + key + "_value") or desc.get(key, "")
            if key == "tech" and val == desc.get(key, ""):
                # 科技名保留原版缩写（TSV-1 / MGS112），其余汉化
                pass
            if key == "time":
                val = "%s 秒" % desc.get(key, "").split()[0]
            v = f.render(val, True, (238, 238, 246))
            s.blit(v, (int(W * 0.1) + 84, y - v.get_height() // 2))
        # 消耗品提示（原版 *consumable item）
        cy = 258 + 110
        ct = f.render(desc.get("cn_note", "*消耗品"), True, (206, 168, 138))
        s.blit(ct, (int(W * 0.1), cy - ct.get_height() // 2))

    # ---------------- 右侧两个按钮 + 价格节点 ----------------
    # 反编译依据 MechShopLayer::init（sub_13DDE0）：
    #   button_buy.png    anchor(0.5,1) pos(W*0.84, H*0.50) → onBuyMech
    #   button_equip.png  anchor(0.5,1) pos(W*0.84, H*0.38) → onEquipMech
    #   价格节点            anchor(0.5,0.5) pos(W*0.84, H*0.55)
    #                     金币价格 >0 → coin.png + 数字；否则 crystal.png + 数字
    # ★ 机甲是**消耗品**（原版 desc 最后一行 *consumable item）：
    #   onBuyMech 每次都只做「数量 +1」，所以购买按钮永远可点，
    #   854 宽屏幕上 0.84W=717、按钮宽 170 ⇒ 右半截在 982，
    #   现在按原版位置：购买在上、使用/卸下在下，价格在购买按钮正上方。
    owned_cnt = (
        save.mech_count(m["name"])
        if hasattr(save, "mech_count")
        else (1 if m["name"] in (save.d.get("owned_mechs") or []) else 0)
    )
    equipped = save.d.get("equipped_mech") == m["name"]
    coin_cost = int(m.get("cost_coin") or 0)
    crystal_cost = int(m.get("cost_crystal") or 0)

    # ---- 价格（屏幕 y = H - 0.55H = 216，正好在购买按钮 240 上方）----
    f = pygame.font.SysFont("Microsoft YaHei", 22, bold=True)
    if coin_cost > 0 or crystal_cost > 0:
        amount = coin_cost if coin_cost > 0 else crystal_cost
        txt = str(amount)
        col = (255, 214, 90) if coin_cost > 0 else (120, 210, 255)
        t = f.render(txt, True, col)
        sh = f.render(txt, True, (40, 18, 6))
        icon = _img(COIN if coin_cost > 0 else CRYSTAL)
        iw = 28 if coin_cost > 0 else 32
        ih = 28 if coin_cost > 0 else 24
        total_w = iw + 8 + t.get_width()
        cx = int(W * 0.84 - total_w / 2)
        cy = int(H - H * 0.55) - t.get_height() // 2
        if icon:
            s.blit(
                pygame.transform.smoothscale(icon, (iw, ih)), (cx, cy + (t.get_height() - ih) // 2)
            )
        for ox, oy in ((-2, 0), (2, 0), (0, -2), (0, 2), (2, 3)):
            s.blit(sh, (cx + iw + 8 + ox, cy + 2 + oy))
        s.blit(t, (cx + iw + 8, cy + 2))
    else:
        t = f.render("免费", True, (140, 255, 150))
        s.blit(t, (int(W * 0.84 - t.get_width() / 2), int(H - H * 0.55) - t.get_height() // 2))

    # ---- 购买按钮（消耗品，永远可点）----
    buy = _btn("pic/ui/shop/button_buy.png")
    if buy:
        br = pygame.Rect(
            int(W * 0.84 - buy.get_width() / 2),
            int(H - H * 0.50),
            buy.get_width(),
            buy.get_height(),
        )
        s.blit(buy, br.topleft)
        rects["buy"] = br

    # ---- 使用 / 卸下按钮（数量 0 → 隐藏，等同原版 setVisible(0)）----
    if owned_cnt > 0:
        eq_tex = "pic/ui/shop/button_unequip.png" if equipped else "pic/ui/shop/button_equip.png"
        eq = _btn(eq_tex)
        if eq:
            er = pygame.Rect(
                int(W * 0.84 - eq.get_width() / 2),
                int(H - H * 0.38),
                eq.get_width(),
                eq.get_height(),
            )
            s.blit(eq, er.topleft)
            if equipped:
                pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.0042)
                alpha = int(60 + 130 * pulse)
                glow = pygame.Surface((er.w + 10, er.h + 10), pygame.SRCALPHA)
                pygame.draw.rect(
                    glow,
                    (255, 216, 96, alpha),
                    pygame.Rect(0, 0, er.w + 10, er.h + 10),
                    3,
                    border_radius=9,
                )
                s.blit(glow, (er.x - 5, er.y - 5))
            rects["equip"] = er
            fnum = pygame.font.SysFont("Microsoft YaHei", 15, bold=True)
            lab = (
                "已使用 ×%d（点击卸下）" % owned_cnt
                if equipped
                else "库存 ×%d（点击使用）" % owned_cnt
            )
            lcol = (140, 255, 150) if equipped else (255, 236, 170)
            lt = fnum.render(lab, True, lcol)
            s.blit(lt, (int(W * 0.84 - lt.get_width() / 2), er.bottom + 4))
    return rects


_MECH_DESC = None


def _load_mech_desc():
    global _MECH_DESC
    if _MECH_DESC is None:
        import json
        import os

        p = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "mech_desc.json"
        )
        try:
            with open(p, encoding="utf-8") as f:
                _MECH_DESC = json.load(f)
        except (OSError, ValueError):
            _MECH_DESC = {}
    return _MECH_DESC
