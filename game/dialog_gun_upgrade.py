"""枪械升级对话框 —— 原版 DialogGunUpgrade。

反编译照抄（sub_148D58 @0x148d58，即 DialogGunUpgrade::init 的实现）：

  底图  pic/ui/shop/upgrade_bg.png (493x315)
        anchor(0.5,0.5) at (W * 0.52, H * 0.455)
  内部容器 n255 = upgrade_bg.png 的尺寸

  三条属性标签 text_power / text_frate / text_crit   anchor(1.0,0.5)
        x = n255.w * 0.375
        y = n255.h * 0.53 / 0.53-0.09 / 0.53-0.18
  三条属性格（PropertyCells）
        x = n255.w * 0.375 + n255.w * 0.02
        y 同上三行
  升级按钮 button_upgrade.png  anchor(0,0)
        pos = (n255.w * 0.53, n255.h * 0.14)
  关闭按钮 button_close.png  anchor(0.5,0.5) scale 0.8
        pos = (n255.w * 0.91, n255.h * 0.96)

  枪械形象（setGunInfo）：
        枪 icon  pos = (n255.w * 0.5, n255.h * 0.905)
        等级节点  pos = (n255.w * 0.37, n255.h * 0.73)  scale 0.58
        下一级预览 pos = (n255.w * 0.77, n255.h * 0.66)  scale 0.4
        升级箭头   pos = (n255.w * 0.58, n255.h * 0.66)

升级花费：upgrade.xml 的 <gun><level> 里 next_coin / next_crystal
（存的是「升到下一级」的花费）。
"""

import pygame

from engine import res
from engine.bmpfont import BitmapText
from game.dialog import DButton, Dialog, H, W, bg_dim, draw_bg, text
from game.shop_table import SHOP_GUNS
from game.weapons import load_upgrade_table


BG_TEX = "pic/ui/shop/upgrade_bg.png"
UPGRADE_TEX = "pic/ui/shop/button_upgrade.png"
CLOSE_TEX = "pic/ui/dialog/button_close.png"
ARROW_TEX = "pic/ui/shop/upgrade_arrow.png"
LABEL_TEX = (
    "pic/ui/shop/text_power.png",
    "pic/ui/shop/text_frate.png",
    "pic/ui/shop/text_crit.png",
)
CELL_NOW = "pic/ui/common/cell_now.png"
CELL_BG = "pic/ui/common/cell_bg.png"
COIN_TEX = "pic/ui/common/coin.png"
CRYSTAL_TEX = "pic/ui/common/crystal.png"

ROW_GAP = 0.09  # n255.h * 0.09 行距
ATTR_KEYS = ("power", "speed", "crit")

# --- 版面（相对面板左下角，cocos 惯例 y 向上）---
# 原版那套 0.905 / 0.73 / 0.66 的比例是围着 493×315 手摆的，武器图标宽
# 98~179 px 不等 ⇒ 长枪（ak47 167 px）会顶出面板、等级字又压在枪身上。
# 这里改成「一条顶部武器带 + 三条属性 + 底部按钮」的固定栅格。
BAND_Y = 268  # 顶部武器带中线
LV_CX = 74  # 「LV n」中心
GUN_CX = 186  # 当前形态中心
ARROW_CX = 282  # 箭头中心
NEXT_CX = 366  # 下一形态中心（右边要给关闭按钮留位）
GUN_MAX_W, GUN_MAX_H = 148, 66
ROW_Y = (196, 166, 136)  # 三条属性行中线
LAB_R = 118  # 属性标签右缘
BAR_X = 128  # 第一格左缘
PITCH = 23  # 格间距
CELL_W, CELL_H = 20, 13  # 格子尺寸（cell 原图 25×17 的 0.78 倍）
CELL_N = 12
BTN_X, BTN_Y = 148, 41  # 升级按钮左下角（48 高的按钮底边落在面板内）
CLOSE_INSET = (69, 66)

# --- 升级花费（金币 / 钻石）---
# 原版是 coin 50×50、crystal 55×41 缩到 ~18px 高，数字又是 0.48 倍位图字，
# 压在橙黄色面板上基本看不清。这里统一放大到 26px 高、数字 0.78 倍并加
# 投影 + 四向描边。
COST_ICON_H = 26  # 图标高度（金币、钻石同高才齐）
COST_ICON_GAP = 6  # 图标 → 数字
COST_ROW_H = 30  # 两行（金币上、钻石下）的行距
COST_TEXT_K = 0.78  # 位图数字缩放（BitmapText 36 号）
COST_INDENT = 14  # 花费区距升级按钮右缘
COST_RIGHT_PAD = 10  # 数字离面板右缘的最小留白


_CELL_CACHE = {}
_UP_ARROW = None


def _up_arrow(base):
    """把右箭头贴图转成上箭头（不换外形，只涨数值）。

    ★ pygame.transform.rotate 的正角是**逆时针**：右箭头（→）要变成
      用户截图里就是那个「蓝色向下箭头」。
    """
    global _UP_ARROW
    if _UP_ARROW is None:
        _UP_ARROW = pygame.transform.rotate(base, 90)
    return _UP_ARROW


_SIG_CACHE = {}


def _icon_sig(img):
    """贴图指纹 (w, h, 像素哈希)。用来判断「升级后是不是同一张图」。"""
    if img is None:
        return None
    key = id(img)
    hit = _SIG_CACHE.get(key)
    if hit is not None and hit[0] is img:  # 同 id 必须是同一对象，防 id 复用读错指纹
        return hit[1]
    try:
        raw = pygame.image.tostring(img, "RGBA")
    except (pygame.error, ValueError):
        raw = b""
    sig = (img.get_width(), img.get_height(), hash(raw))
    _SIG_CACHE[key] = (img, sig)
    return sig


# 「换没换外形」的阈值：相邻两级贴图归一化后的平均像素差小于它就算
# 「只是数值涨了」。实测（缓存/_probe_diff.py）L2→L3 全枪为 0.000，
# L1→L2 / L3→L4 落在 0.086~0.19，只有 aug(0.033) / katana(0.043)
# 两把是「换了贴图但肉眼看不出差别」—— 它们也该给上箭头。
_LOOK_SAME_EPS = 0.055
_DELTA_CACHE = {}


def _look_delta(a, b):
    """两张武器贴图的视觉差异率（0 = 完全一样，1 = 天差地别）。"""
    if a is None or b is None:
        return 1.0
    key = (id(a), id(b))
    hit = _DELTA_CACHE.get(key)
    # 同 id 必须还是同一对对象：res.clear_cache() 后 id 会被复用，
    # 只按 id 认会拿到别的枪的差异率（表现为升级箭头忽有忽无）。
    if hit is not None and hit[0] is a and hit[1] is b:
        return hit[2]
    d = _look_delta_calc(a, b)
    _DELTA_CACHE[key] = (a, b, d)
    return d


def _look_delta_calc(a, b):
    w1, h1 = a.get_size()
    w2, h2 = b.get_size()
    if not w1 or not h1 or not w2 or not h2:
        return 1.0
    # 尺寸差超过 8% 一定是换了形态（长枪换成了另一种枪型）
    if abs(w1 - w2) / float(max(w1, w2)) > 0.08 or abs(h1 - h2) / float(max(h1, h2)) > 0.08:
        return 1.0
    bb = b if (w1, h1) == (w2, h2) else pygame.transform.smoothscale(b, (w1, h1))
    n = w1 * h1
    step = max(1, n // 3000)
    tot = 0.0
    cnt = 0
    try:
        for i in range(0, n, step):
            x, y = i % w1, i // w1
            pa, pb = a.get_at((x, y)), bb.get_at((x, y))
            tot += abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]) + abs(pa[2] - pb[2]) + abs(pa[3] - pb[3])
            cnt += 1
    except (pygame.error, IndexError):
        return 1.0
    return tot / (max(1, cnt) * 4 * 255.0)


def _cell(lit, preview, frac=0.0):
    """缩放好的格子贴图（带缓存）。

    frac > 0 ⇒ 只画左半边（原版 PropertyCells 用 cell_now_l / cell_now_r
    画「半格」：p220 的 power 初始值 0.5 就是画半格，不是空着）。
    """
    fq = round(frac, 2) if lit else 0.0
    key = (lit, preview, fq)
    if key in _CELL_CACHE:
        return _CELL_CACHE[key]
    im = res.load_img(CELL_NOW if lit else CELL_BG)
    out = None
    if im:
        out = pygame.transform.smoothscale(im, (CELL_W, CELL_H))
        if preview:
            out = out.copy()
            out.fill((90, 160, 255, 255), special_flags=pygame.BLEND_RGBA_MULT)
        if fq > 0.05:
            w = max(3, int(round(CELL_W * min(1.0, fq))))
            out = out.subsurface(pygame.Rect(0, 0, w, CELL_H)).copy()
    _CELL_CACHE[key] = out
    return out


def _tint(surf, color, alpha=255):
    """把贴图乘成纯色剪影（保留 alpha，可整体降低透明度）。

    BLEND_RGBA_MULT 是逐通道相乘：先乘颜色得到剪影，再乘 (255,255,255,a)
    只压 alpha —— 不新增任何贴图资源，也不依赖 set_alpha 对逐像素 alpha
    面是否生效的实现差异。
    """
    out = surf.copy()
    out.fill((*tuple(color), 255), special_flags=pygame.BLEND_RGBA_MULT)
    if alpha < 255:
        out.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
    return out


def _blit_outlined(s, surf, pos, color=(26, 12, 4), pad=2, shadow=(2, 2)):
    """贴图字「投影 + 描边」（位图数字自己没有边，压在橙色面板上会糊）。

    阴影描边」，只有描边时字是浮在面板上的，加一层投影才立起来。
    """
    x, y = pos
    if shadow:
        s.blit(_tint(surf, color, 120), (x + shadow[0], y + shadow[1]))
    edge = _tint(surf, color)
    for dx, dy in (
        (-pad, 0),
        (pad, 0),
        (0, -pad),
        (0, pad),
        (pad, pad),
        (-pad, pad),
        (pad, -pad),
        (-pad, -pad),
    ):
        s.blit(edge, (x + dx, y + dy))
    s.blit(surf, (x, y))


class GunUpgradeDialog(Dialog):
    """枪械升级。result: 'close'"""

    def build(self):
        # shop_sel 可能为 None（玩家在军火库里点了两下卡片取消了选中）
        self.gun = getattr(self.app, "shop_sel", None) or "p220"
        self.tab = load_upgrade_table()
        self.lv = self.app.save.weapon_level(self.gun)

        self.bg = res.load_img(BG_TEX)
        bw, bh = self.bg.get_size() if self.bg else (493, 315)
        self.bw, self.bh = bw, bh

        # cocos 惯例：子节点原点 = 父内容空间左下角，y 向上。
        # 底图 anchor(0.5,0.5) at (W*0.52, H*0.455)
        self.base_x = W * 0.52 - bw * 0.5
        self.base_y = H * 0.455 - bh * 0.5

        self.lab_x = LAB_R
        self.bar_x = BAR_X
        self.lab_y = ROW_Y

        self.up_btn = self.add(
            DButton(
                UPGRADE_TEX,
                (0, 0),
                anchor=(0.0, 0.0),
                scale=1.0,
                name="upgrade",
                callback=self._upgrade,
            )
        )
        self.add(
            DButton(
                CLOSE_TEX, (0, 0), anchor=(0.5, 0.5), scale=0.8, name="close", callback=self._close
            )
        )
        self._layout()
        self._refresh()

    def _layout(self):
        bw, bh = self.bw, self.bh
        self.up_btn.pos = (self.base_x + BTN_X, self.base_y + BTN_Y)
        self.up_btn._compute_rect()
        cl = self.buttons[-1]
        cl.pos = (self.base_x + bw - CLOSE_INSET[0], self.base_y + bh - CLOSE_INSET[1])
        cl._compute_rect()

    def _sx(self, lx):
        return int(self.base_x + lx)

    def _sy(self, ly):
        return int(H - (self.base_y + ly))

    # ---- 数据 ----
    def _levels(self):
        return self.tab.get(self.gun, {}).get("levels", [])

    def _look_at(self, lv):
        """某等级对应的形态序号（upgrade.xml 的 looks）。

        looks = [{"min_lv":1,"look_index":1}, {"min_lv":3,"look_index":2}]
        ⇒ lv>=3 用形态 2，lv>=1 用形态 1，否则 0（无后缀的原始贴图）。
        """
        t = self.tab.get(self.gun) or {}
        looks = t.get("looks") or []
        pick = 0
        for lk in looks:
            if lv >= int(lk.get("min_lv", 0) or 0):
                pick = int(lk.get("look_index", 0) or 0)
        return pick

    def _look_icon(self, lv):
        """某等级实际显示的那张枪贴图（解析顺序和军火库卡片一致）。"""
        pick = self._look_at(lv)
        if pick > 0:
            alt = res.load_img("pic/ui/shop/gun_%s_%d.png" % (self.gun, pick)) or res.load_img(
                "pic/ui/weapon_icon/gun_%s_%d.png" % (self.gun, pick)
            )
            if alt:
                return alt
        return res.load_img("pic/ui/shop/gun_%s.png" % self.gun) or res.load_img(
            "pic/ui/shop/gun_%s_1.png" % self.gun
        )

    def _same_look(self, lv_a, lv_b):
        """升级后外形有没有变 —— 比**实际贴图**，不是比 look 序号。

        ★ upgrade.xml 里只写了「L1 用形态1、L3 用形态2」，但很多枪的
          gun_<name>_2.png 根本没这张图（或和形态1一模一样）：
          序号变了、画面里还是同一把枪，玩家看到的就是「不变外形却给了
          所以这里按贴图指纹判定，同图 → 上箭头。
        """
        ia, ib = self._look_icon(lv_a), self._look_icon(lv_b)
        if ia is None or ib is None:
            return self._look_at(lv_a) == self._look_at(lv_b)
        if _icon_sig(ia) == _icon_sig(ib):
            return True
        # 同一张图直接命中；贴图不同但几乎一样的（aug / katana）也算没换形。
        return _look_delta(ia, ib) < _LOOK_SAME_EPS

    def _cost(self):
        """升到下一级的花费 (coin, crystal)。

        只有「当前等级 < 最高等级」时才有价。
        levels[] 长度 4，最高等级号是 3 —— 满级时取 levels[3]
        会读到那条无意义的 next_coin（配置里是 20000），
        """
        lvls = self._levels()
        if not lvls or self.lv >= len(lvls) - 1:
            return 0, 0
        cur = lvls[self.lv]
        return cur.get("next_coin", 0), cur.get("next_crystal", 0)

    def _upgrade(self, btn=None):
        fb = getattr(self.app, "feedback", None)
        if self.lv >= max(0, len(self._levels()) - 1):
            self.app.toast("已满级")
            if fb is not None:
                fb.trigger("shop.maxed")
            return
        coin, crystal = self._cost()
        if coin <= 0 and crystal <= 0:
            return
        if not self.app.save.upgrade_weapon(self.gun, coin, crystal):
            self.app.toast("金币不足")
            if fb is not None:
                fb.trigger("shop.upgrade_fail")
            return
        self.lv = self.app.save.weapon_level(self.gun)
        self._refresh()
        if fb is not None:
            fb.trigger("shop.upgrade")
        else:
            self.app.audio.buy()

    def _close(self, btn):
        self.result = "close"
        self.done = True

    def _refresh(self):
        # _cost() 满级时返回 (0, 0)，所以 (coin>0 or crystal>0) 已经隐含满级
        coin, crystal = self._cost()
        self.up_btn.enabled = coin > 0 or crystal > 0

    # ---- 渲染 ----
    def _cost_rows(self):
        """升级花费行 [(数值, 图标贴图, 数字染色)]，0 的不画。"""
        coin, crystal = self._cost()
        rows = []
        if coin:
            rows.append((coin, COIN_TEX, None))
        if crystal:
            # 钻石数字染亮青（原版 score_blue），和金币的白黄一眼区分
            rows.append((crystal, CRYSTAL_TEX, (150, 235, 255)))
        return rows

    def _draw_costs(self, s):
        """升级花费：图标 + 数字（带投影描边），整块垂直居中在按钮右侧。

        ★ 只有一行时（多数枪只花金币）整块要落在按钮中线上；两行时才
          单行会明显偏高，且图标（居中）与数字（基线对齐）互相错位。
        """
        rows = self._cost_rows()
        if not rows:
            return
        right_limit = self._sx(self.bw) - COST_RIGHT_PAD
        x0 = self.up_btn.rect.right + COST_INDENT
        cy0 = self.up_btn.rect.centery
        n = len(rows)
        for j, (val, tex, bright) in enumerate(rows):
            cy = cy0 + int(round((j - (n - 1) * 0.5) * COST_ROW_H))
            tx = x0
            icon = res.load_img(tex)
            if icon:
                k = COST_ICON_H / float(max(1, icon.get_height()))
                iw = max(1, int(round(icon.get_width() * k)))
                ih = max(1, int(round(icon.get_height() * k)))
                s.blit(pygame.transform.smoothscale(icon, (iw, ih)), (x0, cy - ih // 2))
                tx = x0 + iw + COST_ICON_GAP
            t = BitmapText(str(val), 36)
            if not t.surf:
                continue
            k = COST_TEXT_K
            tw = max(1, int(round(t.surf.get_width() * k)))
            # 数值特别长时按可用宽度回缩，绝不顶出面板右缘
            room = max(8, right_limit - tx)
            if tw > room:
                k *= room / float(tw)
                tw = max(1, int(round(t.surf.get_width() * k)))
            th = max(1, int(round(t.surf.get_height() * k)))
            num = pygame.transform.smoothscale(t.surf, (tw, th))
            if bright:
                num = num.copy()
                num.fill((*tuple(bright), 255), special_flags=pygame.BLEND_RGBA_MULT)
            _blit_outlined(s, num, (tx, cy - th // 2))

    def draw(self, s):
        bg_dim(s, 170)
        draw_bg(s, BG_TEX, (W * 0.52, H * 0.455), (0.5, 0.5), 1.0)

        # ---- 顶部武器带：LV 徽标 → 当前形态 → 箭头 → 下一形态 ----
        # ★ 必须按**当前等级**取形态：upgrade.xml 的 <change_look>
        #   min_lv=1 → gun_<name>_1.png、min_lv=3 → gun_<name>_2.png。
        #   还是 L1 的样子，玩家以为升级没换外观。
        from game.shopui import _shop_gun_icon

        im = _shop_gun_icon(self.app.save, self.gun)
        if im:
            k = min(1.0, GUN_MAX_W / float(im.get_width()), GUN_MAX_H / float(im.get_height()))
            iw = max(1, int(im.get_width() * k))
            ih = max(1, int(im.get_height() * k))
            s.blit(
                pygame.transform.smoothscale(im, (iw, ih)),
                (self._sx(GUN_CX) - iw // 2, self._sy(BAND_Y) - ih // 2),
            )

        lv_txt = "LV %d" % (self.lv + 1)
        lf = pygame.font.SysFont("Microsoft YaHei", 19, bold=True)
        lt = lf.render(lv_txt, True, (255, 250, 225))
        lshadow = lf.render(lv_txt, True, (46, 20, 6))
        lx = self._sx(LV_CX) - lt.get_width() // 2
        ly2 = self._sy(BAND_Y) - lt.get_height() // 2
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (1, 1)):
            s.blit(lshadow, (lx + dx, ly2 + dy))
        s.blit(lt, (lx, ly2))

        maxed = self.lv >= max(0, len(self._levels()) - 1)
        same_look = True if maxed else self._same_look(self.lv, self.lv + 1)
        arrow = None if maxed else res.load_img(ARROW_TEX)
        if arrow:
            if same_look:
                arrow = _up_arrow(arrow)
            s.blit(
                arrow,
                (
                    self._sx(ARROW_CX) - arrow.get_width() // 2,
                    self._sy(BAND_Y) - arrow.get_height() // 2,
                ),
            )

        if not same_look:
            alt = self._look_icon(self.lv + 1)
            if alt and alt is not self._look_icon(self.lv):
                k2 = min(
                    1.0,
                    GUN_MAX_W * 0.58 / float(alt.get_width()),
                    GUN_MAX_H * 0.58 / float(alt.get_height()),
                )
                iw = max(1, int(alt.get_width() * k2))
                ih = max(1, int(alt.get_height() * k2))
                s.blit(
                    pygame.transform.smoothscale(alt, (iw, ih)),
                    (self._sx(NEXT_CX) - iw // 2, self._sy(BAND_Y) - ih // 2),
                )

        # ---- 三条属性行 ----
        # 格数：原版 PropertyCells::setProperty 用 (int) 截断 —— 4.5 → 4 格
        lvls = self._levels()
        cur = lvls[self.lv] if self.lv < len(lvls) else (lvls[-1] if lvls else {})
        nxt = lvls[self.lv + 1] if self.lv + 1 < len(lvls) else cur
        for i, (key, lab_tex) in enumerate(zip(ATTR_KEYS, LABEL_TEX)):
            ly = self.lab_y[i]
            lab = res.load_img(lab_tex)
            if lab:
                s.blit(
                    lab,
                    (self._sx(self.lab_x) - lab.get_width(), self._sy(ly) - lab.get_height() // 2),
                )
            cur_v = cur.get(key, 0)
            nxt_v = nxt.get(key, 0)
            n_lit = min(CELL_N, int(cur_v))
            frac = float(cur_v) - n_lit
            off = 1 if (frac > 0.05 and n_lit < CELL_N) else 0
            n_next = max(0, min(CELL_N - n_lit - off, int(nxt_v) - n_lit - off))
            for j in range(CELL_N):
                x = self._sx(self.bar_x + j * PITCH)
                y = self._sy(ly) - CELL_H // 2
                if j < n_lit:
                    im2 = _cell(True, False)
                elif j == n_lit and off:
                    im2 = _cell(True, False, frac)
                elif j < n_lit + off + n_next:
                    im2 = _cell(False, True)
                else:
                    im2 = _cell(False, False)
                if im2 is None:
                    continue
                s.blit(im2, (x, y))

        # ---- 升级花费：挂在按钮右侧（金币上、钻石下）----
        self._draw_costs(s)

        # ★ 满级时 _cost() 返回 (0,0) ⇒ up_btn.enabled=False，但 DButton.draw
        #   不看 enabled，所以 LV4 那颗「升级」还亮着、点了只弹「已满级」
        #   （用户「武器升级满级不要再有这个按钮了」）。满级直接不画；
        for b in self.buttons:
            if b is self.up_btn and not b.enabled:
                continue
            b.draw(s, self._is_pressed(b))
