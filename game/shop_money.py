"""军火库子页 —— money（充值）页。

对应 MoneyShopLayer::init @0x12BEA0 / initItems @0x12BB30：
  * 顶栏 up_bar + text_bank 标题 + 返回
  * 六格 BankItemButton：3 行 × 2 列
      x = 0.5W + 186*0.5 + 186*1.1*col
      y = (0.63 − i*0.23)*H  （cocos）；实测屏幕再 −12
  * 左侧 BankPackNode 推荐包：anchor(1,0.5) at (0.48W, 0.4H)
  * 整层若超 0.92W，按 0.92W/内容宽 整体缩
"""

import pygame


W, H = 854, 480

# --- 顶栏（与 ShopLayer::init 同一套）
UP_BAR = "pic/ui/shop/up_bar.png"
TITLE = "pic/ui/shop/text_bank.png"
BACK_TEX = "pic/ui/shop/button_back.png"
TAB_Y = 45.0
BACK_BOTTOM = 14.0
TAB_RATIOS = (0.20, 0.37, 0.54, 0.71, 0.88)
TABS = (
    ("soldier", "soldier_icon.png"),
    ("gun", "gun_icon.png"),
    ("money", "money_icon.png"),
    ("ability", "ability_icon.png"),
    ("mech", "mech_icon.png"),
)

# --- 六格
CELL_TEX = "pic/ui/bank/bank_bg_1.png"  # 186x116
CELL_W, CELL_H = 186, 116
CELL_X0 = 516.0  # 第一列中心（实测）
CELL_STEP_X = 206.0  # 列距 = 186*1.1 ≈ 205
CELL_ROW0 = 0.37  # 屏幕 y 比例（自顶）
CELL_ROW_STEP = 0.23
CELL_DROP = 12.0  # node 整体下移（实测）
COIN_ICON = "pic/ui/common/coin.png"
CRYSTAL_ICON = "pic/ui/common/crystal.png"
CBANK = "pic/ui/shop/shop_bank_number.png"  # ¥ 价格图集
SHOP_BANK_NUM = "pic/fonts/shop_bank_number.png"

# --- 推荐包
PACK_TEX = "pic/ui/bank/bank_bg_2.png"  # 354x328
PACK_RIGHT = 0.48  # anchor(1,0.5) 的右缘
PACK_CY = 0.40  # cocos y 比例
HOT_TEX = "pic/ui/bank/bank_hot.png"
FORTUNE_TITLE = "pic/ui/bank/big_fortune_title.png"
BUY_TEX = "pic/ui/shop/button_buy.png"

# --- 数据（截图实测）
COIN_PACKS = ((10000, "2.0"), (50000, "6.0"), (100000, "10.0"))
CRYSTAL_PACKS = ((20, "4.0"), (80, "10.0"), (200, "20.0"))
HOT_PACK = dict(coin=10000, crystal=10, old="4.0", now="2.0")

MAX_W = 0.92  # 整层宽度上限
# 字号全部按模拟器墨迹高度标定（score_gold 橙色本体 25px @ k=1.0）
AMOUNT_SCALE = 0.6  # 格子内数量：实测墨迹高 15
ICON_SCALE = 0.4  # 货币图标 50 → 20
PRICE_SCALE = 1.25  # 白色价格：实测 ¥2.0 高 21（atlas 数字 17）
PACK_AMOUNT_SCALE = 0.8  # 推荐包内数量字号

_IMG = {}


def img(name):
    if name not in _IMG:
        _IMG[name] = _res_load(name)
    return _IMG[name]


def _res_load(name):
    from engine import res

    return res.load_img(name)


def sy(y):
    return H - y


class ScoreFont:
    """shop_bank_number.png：204x21，12 格 × 17px，顺序 0-9 . ¥"""

    ORDER = "0123456789.¥"
    CELL = 17

    def __init__(self, sheet):
        self.sheet = sheet
        self.glyphs = {}
        self._sc = {}  # (字, 宽, 高) -> 缩放好的字形
        if not sheet:
            return
        for i, ch in enumerate(self.ORDER):
            r = pygame.Rect(i * self.CELL, 0, self.CELL, sheet.get_height())
            if not sheet.get_rect().contains(r):
                break
            cell = sheet.subsurface(r).copy()
            bb = cell.get_bounding_rect()
            if bb.width:
                self.glyphs[ch] = (cell, bb)

    def width(self, text, k=1.0):
        return sum(
            int(self.glyphs[c][1].width * k) if c in self.glyphs else int(self.CELL * k)
            for c in str(text)
        )

    def draw(self, surf, text, x, y, k=1.0, align=0.0):
        cur = x - self.width(text, k) * align
        for c in str(text):
            g = self.glyphs.get(c)
            if not g:
                cur += int(self.CELL * k)
                continue
            cell, bb = g
            w, h = max(1, int(bb.width * k)), max(1, int(bb.height * k))
            # 数字按中线居中；点号按基线对齐（否则会被拉成方块）
            oy = 0 if c == "." else int(-h / 2)
            # 同一个字同一尺寸每帧缩放结果都一样，缓存起来（切 subsurface +
            # smoothscale 是商店帧时间的大头之一）
            gim = self._sc.get((c, w, h))
            if gim is None:
                gim = pygame.transform.smoothscale(cell.subsurface(bb).copy(), (w, h))
                self._sc[(c, w, h)] = gim
            surf.blit(gim, (int(cur), int(y + oy)))
            cur += int(bb.width * k)
        return self.width(text, k)


_FONT_CACHE = {}


def _num_font():
    # 每次 draw 都会调到这里：构造要切 12 个字形并算包围盒，必须只做一次。
    f = _FONT_CACHE.get("num")
    if f is None:
        f = _FONT_CACHE["num"] = ScoreFont(img(SHOP_BANK_NUM))
    return f


def _gold_font():
    """金币/钻石数量用金色分数字体。"""
    f = _FONT_CACHE.get("gold")
    if f is None:
        from game.shopui import ScoreFont as G

        f = _FONT_CACHE["gold"] = G("pic/fonts/score_gold.png", 0.7)
    return f


# ------------------------------------------------------------------ 顶栏
def draw_top_bar(s, active="money"):
    rects = {}
    bar = img(UP_BAR)
    if not bar:
        return rects
    bw, bh = bar.get_size()
    s.blit(bar, (0, 0))

    for tid, tex in TABS:
        tile = img("pic/ui/shop/" + tex)
        if not tile:
            continue
        tw, th = tile.get_width(), tile.get_height() // 2
        row = 0 if tid == active else th
        sub = tile.subsurface(pygame.Rect(0, row, tw, th)).copy()
        ratio = TAB_RATIOS[[t[0] for t in TABS].index(tid)]
        dx = bw * ratio - tw / 2
        r = pygame.Rect(int(dx), int(bh - (TAB_Y + th)), tw, th)
        s.blit(sub, r.topleft)
        rects[tid] = r

    back = img(BACK_TEX)
    if back:
        im = pygame.transform.smoothscale(
            back, (int(back.get_width() * 0.85), int(back.get_height() * 0.85))
        )
        pos = (0, int(H - BACK_BOTTOM - im.get_height()))
        s.blit(im, pos)
        rects["back"] = pygame.Rect(pos[0], pos[1], im.get_width(), im.get_height())
    return rects


# ------------------------------------------------------------------ 货币行
# MoneyShopLayer::initCoinAndCrystal：整行 CCNode scale=0.8，
# anchor(0.5,0) 放在 (0.51W, 0.76H)；行内 coin/数字/crystal/数字 全部 anchor(0,0.5)
COIN_ROW_X = 0.51
COIN_ROW_Y = 0.76
COIN_ROW_SCALE = 0.8
COIN_TEXT_SC = 0.8  # 实测墨迹高 20px；score_gold 本体 25px @1.0 → 0.8
COIN_TEXT_K = 1.0  # 最终字号 = COIN_TEXT_SC * COIN_ROW_SCALE * COIN_TEXT_K


def draw_currency_row(s, save, font_gold):
    """金币数 + 钻石数，整行以 (0.51W, 0.76H) 为锚点、缩放 0.8。"""
    coin = img(COIN_ICON)
    crystal = img(CRYSTAL_ICON)
    if not coin or not crystal:
        return {}

    k = COIN_ROW_SCALE
    cw, ch = coin.get_size()
    xw, xh = crystal.get_size()

    coin_txt = str(save.d["coins"])
    cry_txt = str(save.d["crystals"])
    gap = cw * 0.1
    # 字号已经含 0.5，几何再整体乘行缩放 k
    n1 = font_gold.width(coin_txt, COIN_TEXT_SC * k)
    n2 = font_gold.width(cry_txt, COIN_TEXT_SC * k)
    total = cw * k + gap * k + n1 + gap * k + xw * k + gap * k + n2

    base_x = W * COIN_ROW_X - total / 2
    base_y = sy(H * COIN_ROW_Y)
    cy = base_y - ch * k / 2

    x = base_x
    s.blit(
        pygame.transform.smoothscale(coin, (int(cw * k), int(ch * k))),
        (int(x), int(cy - ch * k / 2)),
    )
    x += (cw + gap) * k
    font_gold.draw(s, coin_txt, x, cy, COIN_TEXT_SC * k)
    x += n1 + gap * k
    s.blit(
        pygame.transform.smoothscale(crystal, (int(xw * k), int(xh * k))),
        (int(x), int(cy - xh * k / 2)),
    )
    x += (xw + gap) * k
    font_gold.draw(s, cry_txt, x, cy, COIN_TEXT_SC * k)
    return {}


# ------------------------------------------------------------------ 六格
def cell_rect(col, row):
    w, h = CELL_W, CELL_H
    cx = CELL_X0 + col * CELL_STEP_X
    cy = (CELL_ROW0 + row * CELL_ROW_STEP) * H - CELL_DROP
    return pygame.Rect(int(cx - w / 2), int(cy - h / 2), w, h)


def draw_items(s, coins_bank, crystals_bank, font_gold):
    """六格：图标 + 金色数量（同一行，y≈0.30h），白色大号 ¥价格（y≈0.66h）。"""
    rects = {}
    bg = img(CELL_TEX)
    coin = img(COIN_ICON)
    crystal = img(CRYSTAL_ICON)
    num = _num_font()

    for col, packs in ((0, COIN_PACKS), (1, CRYSTAL_PACKS)):
        icon = coin if col == 0 else crystal
        for row, (amount, price) in enumerate(packs):
            r = cell_rect(col, row)
            if bg:
                s.blit(bg, r.topleft)

            txt = str(amount)
            aw = font_gold.width(txt, AMOUNT_SCALE)
            sz = int(icon.get_width() * ICON_SCALE) if icon else 0
            gap = 4
            total = sz + gap + aw
            x = r.centerx - total // 2
            cy = r.y + r.h * 0.31
            if icon:
                im = pygame.transform.smoothscale(icon, (sz, sz))
                s.blit(im, (x, int(cy - sz / 2)))
            font_gold.draw(s, txt, x + sz + gap, cy, AMOUNT_SCALE, align=0.0)

            if num.sheet:
                num.draw(s, "¥" + price, r.centerx, r.y + r.h * 0.67, PRICE_SCALE, align=0.5)
            rects[(col, row)] = r
    return rects


# ------------------------------------------------------------------ 推荐包
def pack_rect():
    im = img(PACK_TEX)
    w, h = im.get_size() if im else (354, 328)
    right = W * PACK_RIGHT
    cy = sy(H * PACK_CY)
    return pygame.Rect(int(right - w), int(cy - h / 2), w, h)


def draw_pack(s, save, font_gold):
    r = pack_rect()
    bg = img(PACK_TEX)
    if bg:
        s.blit(bg, r.topleft)

    # 金币堆（pack_item_0 278x126）
    pile = img("pic/ui/bank/pack_item_0.png")
    if pile:
        pw, _ph = pile.get_size()
        s.blit(pile, (r.centerx - pw // 2, int(r.y + r.h * 0.14)))

    # 热卖角标
    hot = img(HOT_TEX)
    if hot:
        s.blit(hot, (r.right - hot.get_width() - int(r.w * 0.03), r.y + int(r.h * 0.02)))

    # 内容行：金币 10000 + 钻石 10
    coin = img(COIN_ICON)
    crystal = img(CRYSTAL_ICON)
    cy = int(r.y + r.h * 0.60)
    txt = str(HOT_PACK["coin"])
    cw = font_gold.width(txt, PACK_AMOUNT_SCALE)
    xw = font_gold.width(str(HOT_PACK["crystal"]), PACK_AMOUNT_SCALE)
    isz = int(50 * 0.42)
    total = isz + 2 + cw + 14 + 22 + 14 + isz + 2 + xw
    x = r.centerx - total // 2
    if coin:
        s.blit(pygame.transform.smoothscale(coin, (isz, isz)), (x, int(cy - isz / 2)))
    font_gold.draw(s, txt, x + isz + 2, cy, PACK_AMOUNT_SCALE, align=0.0)
    x += isz + 2 + cw + 14
    font_gold.draw(s, "+", x, cy, PACK_AMOUNT_SCALE, align=0.5)
    x += 22
    if crystal:
        s.blit(
            pygame.transform.smoothscale(crystal, (isz, int(isz * 0.75))),
            (x, int(cy - isz * 0.375)),
        )
    font_gold.draw(s, str(HOT_PACK["crystal"]), x + isz + 2, cy, PACK_AMOUNT_SCALE, align=0.0)

    # 原价（划线）+ 现价
    py = int(r.y + r.h * 0.73)
    num = _num_font()
    if num.sheet:
        num.draw(s, "¥" + HOT_PACK["old"], r.centerx - 40, py, 1.2, align=0.5)
        num.draw(s, "¥" + HOT_PACK["now"], r.centerx + 46, py, 1.2, align=0.5)
    strike = img("pic/ui/bank/price_delete.png")
    if strike:
        sw = int(strike.get_width() * 0.7)
        sh = int(strike.get_height() * 0.7)
        s.blit(
            pygame.transform.smoothscale(strike, (sw, sh)),
            (int(r.centerx - 40 - sw / 2), int(py - sh / 2)),
        )

    # 优惠文案
    hint = img("pic/ui/bank/text_fortune_hint.png")
    if hint:
        hw = int(hint.get_width() * 0.28)
        hh = int(hint.get_height() * 0.28)
        s.blit(
            pygame.transform.smoothscale(hint, (hw, hh)),
            (r.centerx - hw // 2, int(r.y + r.h * 0.81)),
        )

    buy = img(BUY_TEX)
    br = None
    if buy:
        bw = int(buy.get_width() * 0.78)
        bh = int(buy.get_height() * 0.78)
        bx = r.centerx - bw // 2
        by = int(r.y + r.h * 0.88)
        s.blit(pygame.transform.smoothscale(buy, (bw, bh)), (bx, by))
        br = pygame.Rect(bx, by, bw, bh)
    return br


# ------------------------------------------------------------------ 整页
def draw_money(s, save, font_gold):
    """返回命中矩形：tabs / items / pack。"""
    rects = draw_top_bar(s, "money")
    draw_currency_row(s, save, font_gold)
    rects["items"] = draw_items(s, save.d["coins"], save.d["crystals"], font_gold)
    rects["pack"] = draw_pack(s, save, font_gold)
    return rects
