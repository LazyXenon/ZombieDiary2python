"""每日奖励签到 —— 原版 DialogDailyReward。

反编译依据：
  DialogDailyReward::init            @0x155878
  DialogDailyReward::getDialogBg     @0x154314
  DialogDailyReward::getRewardNode   @0x154fd8
  DialogDailyReward::getCoinOrCrystalNode @0x15452c
  DialogDailyReward::updateDailyReward @0x1552c4
  EzPageContainer::addPage @0x1c4200 / showPage @0x1c36b8
  EzPageContainer::initPageIndicator @0x1c4280 / syncPageIndicator @0x1c0348
  Combined9Cells::update @0x1c2b6a

════════════════════════════════════════════════════════════════════
cocos 坐标语义（cocos2d-x 2.1.4）
════════════════════════════════════════════════════════════════════
· 子节点坐标原点 = 父节点的**内容左下角**（不是父节点锚点）。
· 节点自身 position 相对其父内容左下角；anchor 只决定自身贴图的对齐。
· 屏幕 y = H - cocos_y（cocos y 向上）。
· 父节点 setScale 等比缩放其**全部**子孙的渲染，但子孙的 position 仍以
  父的**未缩放内容坐标**表达 → 全局 = 父左下 + 局部 × scale。

════════════════════════════════════════════════════════════════════
原版结构树
════════════════════════════════════════════════════════════════════
DialogBg (CCNode, contentSize 800×400, anchor 0.5,0.5)
  setPosition(W*0.5, H*0.44)   setScale(s)          s = 0.82/0.87/0.9/1.0
  ├─ 9cell_bg.png  (Combined9Cells)  pos (400, 200)
  ├─ 9cell_bg_1.png (EzSprite)  setScaleX(720/14) setScaleY(330/256)
  │                  pos (400, 200)      ← 内框
  ├─ 9cell_line.png (EzSprite)  setScaleX(800/850)  anchor (0.5,1.0)
  │                  pos (400, 18)       ← 顶部横线
  ├─ EzPageContainer  anchor (0,0)  pos (0, 55)     contentSize 800×280
  │    ├─ page0 (EzNode, contentSize 800×280, anchor 0,0)  pos (0, 0)
  │    │    ├─ reward_bg_0/1.png (EzSprite, anchor 0.5,0.5)
  │    │    │    pos (104 + col*118, 229.6 | 75.6)
  │    │    │    ├─ EzTexText  天数   pos (w*0.515, h*0.804)  anchor 0.5,0.5  scale 0.7
  │    │    │    ├─ reward_flag.png    pos (w*0.5,  h*0.45)
  │    │    │    └─ getRewardNode 容器 pos (w*0.5, h*0.475)
  │    │    │          └─ 100×100 容器 anchor 0.5,0.5
  │    │    │                ├─ pack_item_0.png  scale 0.2  pos (50,50)
  │    │    │                └─ 金币/钻石节点   scale 0.45 anchor (0.5,1.0) pos (50,20)
  │    ├─ page1  pos (800, 0)      ← addPage：页索引 × 容器宽
  │    ├─ page2  pos (1600, 0)
  │    └─ button_reward.png (EzFunctionButton) anchor (0.5,0.5) scale 0.72
  │                              pos (800*0.76, -280*0.07)
  │    └─ page_indicator.png × PAGES
  └─ 30_days.png (EzSprite)  pos (W*0.5, H*0.92)  setScale(s)

页切换：showPage 把当前页移到 x=0，其余页在两侧（滑动分页）。
指示器：initPageIndicator(res, 1.0)，每图标宽 = 图宽×1.2，
        x = (容器宽 - 总宽)*0.5 + 单宽*(i+0.5)，y = -图高 * 1.0。
        当前页不透明 255，其余 168（syncPageIndicator）。
"""

import math

import pygame

from engine import gridfont, res
from engine.name2icon import NAME2ICON
from game.dialog import DButton, Dialog, H, W, bg_dim, close_rect_for
from game.ninecell import draw_9cell_atlas, fill_panel


LOGIC = 1.0

BG_TEX = "pic/ui/dialog/9cell_bg.png"
BG_INNER_TEX = "pic/ui/dialog/9cell_bg_1.png"
BG_LINE_TEX = "pic/ui/dialog/9cell_line.png"
TITLE_TEX = "pic/ui/dialog/30_days.png"
CELL_TEX = "pic/ui/dialog/reward_bg_0.png"
CELL_LAST_TEX = "pic/ui/dialog/reward_bg_1.png"
FLAG_TEX = "pic/ui/dialog/reward_flag.png"
INDICATOR_TEX = "pic/ui/dialog/page_indicator.png"
BUTTON_TEX = "pic/ui/dialog/button_reward.png"
GIFT_TEX = "pic/ui/bank/pack_item_0.png"
COIN_TEX = "pic/ui/common/coin.png"
CRYSTAL_TEX = "pic/ui/common/crystal.png"

# ---- 原版常量（来自反编译） ----
BOX_W = LOGIC * 800.0  # DialogBg contentSize 宽
BOX_H = LOGIC * 400.0  # DialogBg contentSize 高
PAGE_H = BOX_H * 0.7  # 页容器 contentSize 高 = 280
PAGE_Y = LOGIC * 55.0  # 页容器在 DialogBg 内的 y
BTN_SCALE = 0.72  # button_reward 缩放
IND_SCALE = 1.0  # initPageIndicator 的 a3
GIFT_SCALE = 0.37  # pack_item_0 缩放（常量 1052602532 = 0.37f）
ICON_SCALE = 0.83  # type2/3 图标缩放（常量 1062501089 = 0.83f）
ICON_SCALE_4 = 0.85  # type4 图标缩放（常量 1062836634 = 0.85f）
MECH5_SCALE = 1.1  # mech_5 额外缩放（常量 1066192077 = 1.1f）
MECH7_SCALE = 0.9  # mech_7 额外缩放（常量 1063675494 = 0.9f）
COIN_SCALE = 0.45  # 金币/钻石节点整体缩放（字面量 0.45）
NUM_SCALE = 1.6  # 数量文字缩放（字面量 1.6）
CELL_DX = LOGIC * 118.0  # 格子 x 步进
X0_RATIO = 0.13  # 首列 x = 容器宽 * 0.13
Y_TOP_RATIO = 0.82  # 上排 y = 容器高 * 0.82
Y_BOT_RATIO = 0.27  # 下排 y = 容器高 * 0.27
DAY_FONT_INDEX = 4  # EzTexText(getTexFont(4)) = shop_gun_number

# 格子底部道具名的字体缓存（按字号）
_CAPTION_FONTS = {}

COLS = 6
ROWS_PER_PAGE = 2
DAYS = 30
PER_PAGE = COLS * ROWS_PER_PAGE
PAGES = (DAYS + PER_PAGE - 1) // PER_PAGE

# reward 容器尺寸（getRewardNode）
REWARD_BOX = LOGIC * 100.0


def _bg_scale(w, h):
    """原版 DialogDailyReward::init 的缩放分支。854/480 = 1.779 → 1.0"""
    ratio = w / float(h) if h else 1.0
    if ratio < 1.4:
        return 0.82
    if ratio < 1.6:
        return 0.87
    if ratio < 1.7:
        return 0.9
    return 1.0


class DailyRewardDialog(Dialog):
    """每日奖励签到。done = 'close'"""

    # 左右键用于翻页，不参与通用按钮焦点移动。
    ARROWS_PAGE = True

    def __init__(self, app):
        d = getattr(getattr(app, "save", None), "d", {}) or {}
        self.day = max(1, min(DAYS, int(d.get("reward_day", 1) or 1)))
        self.claimed = set()  # 已领取的天（本次会话内，仅用于绘制）
        self.page = self._page_of(self.day)
        self.btn_claim = None
        self.cell_rects = []
        Dialog.__init__(self, app)

    def close_button_rect(self):
        return close_rect_for(self._screen_rect(_bg_scale(W, H)), right=10, top=8)

    # ---- 建立 ----
    def build(self):
        self.btn_claim = self.add(
            DButton(
                BUTTON_TEX,
                (BOX_W * 0.76, -PAGE_H * 0.07),
                anchor=(0.5, 0.5),
                scale=BTN_SCALE,
                callback=self._on_claim,
            )
        )

    def _on_claim(self, btn):
        save = getattr(self.app, "save", None)
        day = self.day
        if getattr(self, "_closing_anim", False):
            return
        # 落盘：reward_day_<n> = 1 表示这天已领（原版键名）
        if save is not None:
            key = "reward_day_%d" % day
            if int(save.d.get(key, 0) or 0):
                # 今天已领过：给一句提示再关，别让玩家以为按钮坏了
                toast = getattr(self.app, "toast", None)
                if toast:
                    toast("第 %d 天奖励已领取，明天再来" % day)
                self.done = "close"
                return
            save.d[key] = 1
            _type, _name, coin, crystal = self._reward(day)
            if coin:
                save.add_coins(int(coin))
            if crystal:
                save.add_crystals(int(crystal))
            label = ""
            if _type in (2, 3, 4):
                label = self._grant_reward(save, _type, _name)
            save.save()
            if label:
                toast = getattr(self.app, "toast", None)
                if toast:
                    toast("第 %d 天签到奖励：%s" % (day, label))
            # ★ 领奖动画：奖励图标从这里飞进顶栏货币位，落地时数字才跳。
            #   数据在上面已经落盘（关游戏也不丢），
            #   `RewardFly.pending_*` 只影响顶栏显示值。
            fly = getattr(self.app, "reward_fly", None)
            if fly is not None and (coin or crystal):
                r = None
                for d, rect in self.cell_rects:
                    if d == day:
                        r = rect
                        break
                if r is not None:
                    fly.spawn(r.centerx, r.centery, int(coin), int(crystal))
                    self._closing_anim = True
                    self._close_wait = 0.75
                    self._claimed_day = day
                    return
        # ★ 这里**不要**把 self.day 推到 day+1：签到进度只由每日刷新
        #   （save.clearDailyTaskInfo 里连续登录 reward_day+1）推进，
        #   存档 reward_day 不一致，重开面板又跳回当天，看起来像「领完
        #   又变成没领」，is_claimed_today() 也会跟着判错。
        self.claimed.add(day)
        self.page = self._page_of(day)
        self.done = "close"

    def update(self, dt):
        super().update(dt)
        # 领奖后等飞行动画播完再收起面板
        if getattr(self, "_closing_anim", False):
            self._close_wait -= dt
            if self._close_wait <= 0:
                self._closing_anim = False
                day = getattr(self, "_claimed_day", self.day)
                # 同上：天只在每日刷新时推进，领取不改 self.day
                self.claimed.add(day)
                self.page = self._page_of(day)
                self.done = "close"
        # 翻页滑动松手后的回弹（趋近 0）
        # 必须与领奖逻辑放在同一个 update 中：拆成两个 update 会被覆盖，
        # 导致领奖后面板不关闭。
        off = int(getattr(self, "_page_drag_off", 0) or 0)
        if off:
            self._page_drag_off = int(off * 0.6)
            if abs(self._page_drag_off) < 4:
                self._page_drag_off = 0

    def _claimed(self, day):
        """这一天是否已领（读存档 reward_day_N）。"""
        save = getattr(self.app, "save", None)
        if save is None:
            return False
        try:
            return bool(int(save.d.get("reward_day_%d" % day, 0) or 0))
        except Exception:
            return False

    def is_claimed_today(self):
        """签到页：今天这次是否已经领过。"""
        save = getattr(self.app, "save", None)
        if save is None:
            return False
        return bool(int(save.d.get("reward_day_%d" % self.day, 0) or 0))

    def _page_of(self, day):
        """原版 updateDailyReward 尾段：day<=12 → 第 0 页；<=24 → 第 1 页；否则第 2 页。"""
        return max(0, min(PAGES - 1, (day - 1) // PER_PAGE))

    # ---- 奖励内容 ----
    def _reward(self, day):
        """返回 (type, name, coin, crystal)。

        原版数据来自服务器 "reward_day_N"（DRItemDef: coin/crystal/type/name）。
        原版服务器已废，这里用从原版参考帧逐格抄下来的本地等价表
        （data/daily_reward.json），30 天的图标与数量都与原版一致。

        type 0 = 默认分支（pack_item_0 金币堆 + 数量）
        type 2/3/4 = Name2IconTex 图标（无数量）
        """
        row = self._reward_table().get(day)
        if not row:
            return (0, "", 0, 0)
        return tuple(row)

    def _reward_table(self):
        """载入本地奖励表（带缓存）。"""
        if getattr(self, "_rtable", None) is None:
            import json
            import os

            path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data",
                "daily_reward.json",
            )
            try:
                with open(path, encoding="utf-8") as f:
                    days = json.load(f)["days"]
            except Exception:
                days = []
            self._rtable = {i + 1: r for i, r in enumerate(days)}
        return self._rtable

    # ---- 具名奖励的发放（type 2/3/4）----
    @staticmethod
    def _reward_target(name):
        """把奖励名归一成（类别, 存档名）。

        原版 reward_day_N 里 type 2/3/4 混着三类东西：
          · 机甲整机      mech_1 / mech_3 / mech_4 / mech_5 / mech_8 / mech_10 …
          · 机甲头像写法  mech_5_head —— 旧档可能是驾驶舱头像皮肤，本复刻
                          没有皮肤系统，仍等价成「机甲 5 一台」；新签到表
                          直接显示整机图标 mech_5，避免实发整机却画座舱罩
          · 技能道具      airstrike / mech_7（七号炮塔）/ fly_1 / fly_2
        """
        if not name:
            return None, None
        mech = name[:-5] if name.endswith("_head") else name
        try:
            from game.shop_extra import load_mech_actors

            mechs = {m["name"] for m in load_mech_actors()}
        except Exception:
            mechs = {"mech_1", "mech_3", "mech_4", "mech_5", "mech_8", "mech_9", "mech_10"}
        if mech in mechs:
            return "mech", mech
        try:
            from game.battle_abilities import ABILITY_DEFS
        except Exception:
            ABILITY_DEFS = {}
        if mech in ABILITY_DEFS:
            return "ability", mech
        return None, None

    def _grant_reward(self, save, kind, name):
        """真正把 type 2/3/4 的奖励写进存档，返回给玩家看的一句话。"""
        cat, key = self._reward_target(name)
        if not cat:
            return ""
        cn = key
        try:
            from game.shop_tabs import ABILITY_CN, MECH_CN

            cn = MECH_CN.get(key) or ABILITY_CN.get(key) or key
        except Exception:
            pass
        if cat == "mech":
            save.add_mech(key, 1)
            return "机甲「%s」x1" % cn
        ab = save.d.setdefault("abilities", {})
        ab[key] = int(ab.get(key, 0) or 0) + 1
        own = save.d.setdefault("owned_abilities", [])
        if key not in own:
            own.append(key)
        return "道具「%s」x1" % cn

    def _reward_label(self, kind, name):
        """格子里那行小字：告诉玩家这个图标到底是什么（没有就返回 ""）。"""
        if kind not in (2, 3, 4):
            return ""
        cat, key = self._reward_target(name)
        if not cat:
            return ""
        try:
            from game.shop_tabs import ABILITY_CN, MECH_CN

            return MECH_CN.get(key) or ABILITY_CN.get(key) or key
        except Exception:
            return key

    # ---- 绘制 ----
    def draw(self, s):
        # 与设置面板一致：只压暗一层背景，面板本体保持深紫半透明，
        # 不再额外铺近乎纯黑的全屏遮罩。
        bg_dim(s, 88)
        scale = _bg_scale(W, H)
        self._draw_box(s, scale)
        self._draw_title(s, scale)
        self.cell_rects = []
        self._draw_cells(s, scale)
        self._draw_claim_button(s, scale)
        self._draw_indicator(s, scale)
        self._draw_close_button(s)

    # ------------------------------------------------------------ 几何
    def _box_local(self, scale):
        """DialogBg 内容左下角的 cocos 坐标 + 缩放后尺寸。

        DialogBg: anchor (0.5,0.5), pos (W*0.5, H*0.44), size 800×400, scale s
        → 内容左下角（cocos 全局）= (W*0.5 - 400s, H*0.44 - 200s)
        """
        bw = int(BOX_W * scale)
        bh = int(BOX_H * scale)
        x0 = W * 0.5 - bw / 2.0
        y0 = H * 0.44 - bh / 2.0  # cocos y；屏幕 y = H - y
        return x0, y0, bw, bh

    def key_items(self):
        """键盘焦点候选：领取键 + 分页指示器（其余是格子装饰，不可点）。"""
        from app.keynav import as_rect

        out = []
        if self.close_rect is not None:
            out.append((self.close_rect, "关闭"))
        r = as_rect(getattr(self.btn_claim, "rect", None))
        if r is not None:
            out.append((r, "领取奖励"))
        for i, rect in enumerate(getattr(self, "_ind_rects", []) or []):
            rr = as_rect(rect)
            if rr is not None:
                out.append((rr, "第%d页" % (i + 1)))
        return out

    def _screen_rect(self, scale):
        """面板在屏幕上的矩形（用于「点遮罩关闭」判定）。"""
        x0, y0, bw, bh = self._box_local(scale)
        return pygame.Rect(int(x0), int(H - (y0 + bh)), int(bw), int(bh))

    def _draw_box(self, s, scale):
        """弹窗底：9cell_bg（图集九宫格）+ 内框 9cell_bg_1 + 顶部横线 9cell_line。"""
        x0, y0, bw, bh = self._box_local(scale)
        rect = pygame.Rect(int(x0), int(H - y0 - bh), bw, bh)

        # ★ 面板底与设置页同款：深紫半透明，保留官方 9cell 金属边框。
        #   9cell_bg.png 中心本身全透明，所以必须先铺一层底色；
        #   用 fill_panel 而非 draw.rect，确保 SRCALPHA 面板的 alpha 正确。
        fill_panel(s, BG_TEX, rect, (34, 28, 54, 208), scale)

        draw_9cell_atlas(s, BG_TEX, rect, scale)

        # 内框：setScaleX((800-80)/14) setScaleY((400-70)/256)，pos (400,200)
        inner = res.load_img(BG_INNER_TEX)
        if inner:
            iw = int(BOX_W - LOGIC * 80.0)
            ih = int(BOX_H - LOGIC * 70.0)
            im = pygame.transform.smoothscale(inner, (iw, ih))
            im.set_alpha(72)
            ix = x0 + 400.0 * scale
            iy = y0 + 200.0 * scale
            s.blit(im, (int(ix - iw / 2), int(H - iy - ih / 2)))

        # 顶部横线：setScaleX(800/850)，anchor (0.5,1.0)，pos (400, 18)
        line = res.load_img(BG_LINE_TEX)
        if line:
            lw = max(1, int(line.get_width() * (BOX_W / (LOGIC * 850.0))))
            lh = max(1, int(line.get_height()))
            im = pygame.transform.smoothscale(line, (lw, lh))
            im.set_alpha(150)
            lx = x0 + 400.0 * scale
            ly = y0 + 18.0 * scale
            s.blit(im, (int(lx - lw / 2), int(H - ly - lh)))

    def _draw_title(self, s, scale):
        """标题 30_days.png：pos (W*0.5, H*0.92)，setScale(s)。"""
        im = res.load_img(TITLE_TEX)
        if not im:
            return
        w = max(1, int(im.get_width() * scale))
        h = max(1, int(im.get_height() * scale))
        im = pygame.transform.smoothscale(im, (w, h))
        s.blit(im, (int(W * 0.5 - w / 2), int(H - H * 0.92 - h / 2)))

    def _page_local(self, scale):
        """当前页内容左下角的 cocos 坐标。

        DialogBg 内容左下 = (x0, y0)
        页容器 pos (0,55) anchor (0,0) → 页容器内容左下 = DialogBg 内容左下 + (0, 55*s)
        页节点 pos (页索引*800, 0) anchor (0,0)；showPage 把当前页移到 x=0
        """
        x0, y0, _bw, _bh = self._box_local(scale)
        return x0, y0 + PAGE_Y * scale

    def _draw_cells(self, s, scale):
        """每页 12 格（6 列 × 2 行）。

        格子 pos 相对**页节点内容左下角**：
          x = 容器宽*0.13 + col*118
          y = 容器高*0.82（上排）| 容器高*0.27（下排）
        格子 anchor (0.5,0.5) → 该点是格子**中心**。
        格子子节点（天数字/已领标记/奖励图标）坐标相对**格子内容左下角**。

        ★ 原版是 EzPageContainer（3 页都在节点树里），当前页移到 x=0、
          ⇒ 玩家只能看到 12 天，13~30 天**根本看不到**
          现在按原版画法把三页都铺上，当前页 x=0，
          邻页按滑动偏移画出来（滑动时能看到内容跟着走）。
        """
        px, py = self._page_local(scale)
        # 滑动偏移（像素）：拖拽时跟随手指，松手回弹
        off = int(getattr(self, "_page_drag_off", 0) or 0)
        for idx in range(DAYS):
            day = idx + 1
            page = idx // PER_PAGE
            local = idx % PER_PAGE
            row = 0 if local < COLS else 1
            col = local % COLS

            # 页在容器里的 x = 页索引 * 容器宽；当前页移到 x=0
            page_dx = (page - self.page) * BOX_W
            # 相邻页只在滑动时露出边缘
            if page != self.page and abs(page_dx + off) > BOX_W:
                continue
            cx_page = px + (page_dx + off) * scale

            cy = (PAGE_H * Y_TOP_RATIO) if row == 0 else (PAGE_H * Y_BOT_RATIO)
            cx = BOX_W * X0_RATIO + col * CELL_DX

            # 格子中心（cocos 全局）
            gcx = cx_page + cx * scale
            gcy = py + cy * scale

            tex = CELL_LAST_TEX if col == COLS - 1 else CELL_TEX
            cell = res.load_img(tex)
            if not cell:
                continue
            cw, ch = cell.get_size()
            dw = max(1, int(cw * scale))
            dh = max(1, int(ch * scale))
            im = cell.copy()
            im.set_alpha(232)
            # 当前天：呼吸 ScaleTo(1.2,1.1,0.5s) + ScaleTo(1.15,1.15,0.2s) 循环
            # （原版对格子 setScale，cocos 会带着子节点一起缩放）
            bscale = 1.0
            if day == self.day:
                # ★ 呼吸放大只在**原尺寸以内**小幅度做。
                #   原版 ScaleTo(1.2,1.1) → ScaleTo(1.15,1.15) 循环，
                #   但原版格子宽 109、步进 118，1.2 倍正好 130.8 —— 会压住邻居；
                #   参考帧里当前天格子**并没有盖住旁边**，说明原版的格子在
                #   缩放前留了足够间距。这里按参考帧取 1.06 封顶：
                #   109*1.06 = 115.5 < 118 步进，不会越界。
                p = 0.5 + 0.5 * math.sin(self.t * 4.4)
                bscale = 1.03 + 0.03 * p
                dw = max(1, int(dw * bscale))
                dh = max(1, int(dh * bscale))
                im = pygame.transform.smoothscale(im, (dw, dh))

            # 格子内容左下角（cocos 全局）
            clx = gcx - dw / 2.0
            cly = gcy - dh / 2.0
            rect = pygame.Rect(int(clx), int(H - cly - dh), dw, dh)
            s.blit(im, rect.topleft)
            self.cell_rects.append((day, rect))

            # 天数文字：EzTexText pos (w*0.515, h*0.804) 相对格子内容左下，anchor 0.5,0.5
            # 字体 getTexFont(4)，scale 0.7
            # 注意：原版对格子 setScale 后，子节点跟随缩放 → 用缩放后的 dw/dh 而非 cw/ch。
            font = gridfont.get_font(DAY_FONT_INDEX)
            if font:
                nx = clx + dw * 0.515
                ny = cly + dh * 0.804
                # ny 是 cocos y（向上）→ 屏幕 y = H - ny
                font.draw(s, str(day), nx, H - ny, 0.7 * scale * bscale, align=(0.5, 0.5))

            # 奖励图标容器：pos (w*0.5, h*0.475) 相对格子内容左下
            rx = clx + dw * 0.5
            ry = cly + dh * 0.475
            self._draw_reward(s, day, rx, ry, scale)

            _k, _nm = self._reward(day)[0], self._reward(day)[1]
            cap = self._reward_label(_k, _nm)
            if cap:
                self._draw_caption(s, cap, clx + dw * 0.5, cly + dh * 0.085, dw, scale)

            if self._claimed(day):
                flag = res.load_img(FLAG_TEX)
                if flag:
                    fw = max(1, int(flag.get_width() * scale))
                    fh = max(1, int(flag.get_height() * scale))
                    fim = pygame.transform.smoothscale(flag, (fw, fh))
                    fx = clx + dw * 0.5
                    fy = cly + dh * 0.45
                    s.blit(fim, (int(fx - fw / 2), int(H - fy - fh / 2)))

    def _draw_caption(self, s, text, cx, cy, cell_w, scale):
        """格子底部的一行道具名（中文，用系统字体）。

        cx / cy 是 cocos 坐标（cy 向上），文字以 (cx, cy) 为水平中心、垂直居中。
        字号随 scale 走；超宽就等比缩，保证**不越出格子**。
        """
        size = max(9, int(11 * scale))
        key = size
        font = _CAPTION_FONTS.get(key)
        if font is None:
            font = pygame.font.SysFont("Microsoft YaHei", size, bold=True)
            _CAPTION_FONTS[key] = font
        surf = font.render(text, True, (255, 226, 150))
        maxw = max(1, int(cell_w * 0.94))
        if surf.get_width() > maxw:
            k = maxw / float(surf.get_width())
            surf = pygame.transform.smoothscale(surf, (maxw, max(1, int(surf.get_height() * k))))
        # 描边：深色底一圈，压在格子的木纹上也能看清
        edge = font.render(text, True, (40, 20, 18))
        if edge.get_width() != surf.get_width() and surf.get_width() > 0:
            edge = pygame.transform.smoothscale(edge, surf.get_size())
        x = int(cx - surf.get_width() / 2.0)
        y = int(H - cy - surf.get_height() / 2.0)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            s.blit(edge, (x + dx, y + dy))
        s.blit(surf, (x, y))

    def _draw_reward(self, s, day, cx, cy, scale):
        """getRewardNode（@0x154fd8）。

        返回一个 100×100 容器节点，anchor (0.5,0.5)，父是格子。
        容器内：
          type 0（default）：pack_item_0.png（金币+钻石堆）setScale 0.37，pos (50,50)
                            + getCoinOrCrystalNode（金额），scale 0.45，
                              anchor (0.5,1.0)，pos (50,20)
          type 2/3/4：Name2IconTex[name] 的图标，setScale 0.83 / 0.85，pos (50,40)
                       （type3 的 mech_7 额外 ×0.9；type4 的 mech_5 额外 ×1.1）
        """
        kind, name, coin, crystal = self._reward(day)
        bw = int(REWARD_BOX * scale)
        bh = int(REWARD_BOX * scale)
        # 容器内容左下角（cocos 全局）
        blx = cx - bw / 2.0
        bly = cy - bh / 2.0

        if kind in (2, 3, 4):
            self._draw_named_icon(s, kind, name, blx, bly, scale)
            return

        # default 分支：pack_item_0（金币+钻石堆）
        gift = res.load_img(GIFT_TEX)
        if gift:
            gw = max(1, int(gift.get_width() * GIFT_SCALE * scale))
            gh = max(1, int(gift.get_height() * GIFT_SCALE * scale))
            gim = pygame.transform.smoothscale(gift, (gw, gh))
            # 礼盒 pos (50,50)，anchor 0.5,0.5 → 中心在容器内容左下 + (50,50)
            # ★ 原版礼盒中心在容器 (50,50)，金额节点在 (50,20) —— 两者只隔 30px，
            #   而 pack_item_0 ×0.37 有 70px 高 ⇒ 数字直接压在金币堆上（看起来
            #   像「100」贴在礼盒底边）。礼盒上抬到 56、金额下移，留出一条空隙。
            gx = blx + 50.0 * scale
            gy = bly + 56.0 * scale
            s.blit(gim, (int(gx - gw / 2), int(H - gy - gh / 2)))

        # 金额节点：anchor (0.5,1.0)，scale 0.45，pos (50,20) 相对容器内容左下
        if coin > 0:
            self._draw_amount(s, blx + 50.0 * scale, bly + 12.0 * scale, scale, coin, COIN_TEX, 1)
        elif crystal > 0:
            self._draw_amount(
                s, blx + 50.0 * scale, bly + 12.0 * scale, scale, crystal, CRYSTAL_TEX, 3
            )

    def _draw_named_icon(self, s, kind, name, blx, bly, scale):
        """type 2/3/4：Name2IconTex[name] 图标。

        setScale：type2/3 = 0.83，type4 = 0.85；
        额外：name == "mech_7" ×0.9（type3），name == "mech_5" ×1.1（type4）。
        位置：容器局部 (50, 40)，anchor 0.5,0.5。
        """
        path = NAME2ICON.get(name)
        if not path and name.startswith("gun_"):
            path = "pic/ui/weapon_icon/%s.png" % name
        if not path:
            for prefix in (
                "pic/ui/mech_icon/",
                "pic/mech/",
                "pic/mech/01/",
                "pic/mech/03/",
                "pic/mech/04/",
                "pic/mech/05/",
                "pic/mech/07/",
                "pic/mech/08/",
                "pic/mech/09/",
                "pic/mech/10/",
                "pic/mech/11/",
                "pic/mech/12/",
                "pic/mech/13/",
            ):
                cand = prefix + name + ".png"
                if res.load_img(cand) is not None:
                    path = cand
                    break
        if not path:
            return
        img = res.load_img(path)
        if not img:
            return
        sc = ICON_SCALE_4 if kind == 4 else ICON_SCALE
        if kind == 3 and name == "mech_7":
            sc *= MECH7_SCALE
        elif kind == 4 and name == "mech_5":
            sc *= MECH5_SCALE
        # ★ 原版 UI 图标统一 96×85（mech_1 / mech_5 / soldier_2 全是）。
        #   标准图标直接按 setScale 画（0.83 → 80×70.6），**不要再套缩小框** ——
        #   第 12 天的 mech_10 只有原版七成大。
        #   只有「游戏内大图」（feichuan.png 280×163 之类）才需要等比压到框内。
        MAX_W, MAX_H = 96.0, 85.0
        fw = img.get_width()
        fh = img.get_height()
        fit = min(1.0, MAX_W / fw, MAX_H / fh)
        iw = max(1, int(fw * fit * sc))
        ih = max(1, int(fh * fit * sc))
        im = pygame.transform.smoothscale(img, (iw, ih))
        gx = blx + 50.0 * scale
        gy = bly + 40.0 * scale
        s.blit(im, (int(gx - iw / 2), int(H - gy - ih / 2)))

    def _draw_amount(self, s, x, y, scale, value, tex, font_index):
        """getCoinOrCrystalNode（@0x15452c）。

        图标 anchor (0,0.5)，位置 (0, 图高*0.5)（相对节点左下）；
        数字 EzTexText anchor (0,0.5)，setScale 1.6，位置 (图宽*1.1, 图高*0.5)。
        字体：金币 index 1（score_gold），钻石 index 3（number_blood）。
        """
        icon = res.load_img(tex)
        if not icon:
            return
        iw = max(1, int(icon.get_width() * COIN_SCALE * scale))
        ih = max(1, int(icon.get_height() * COIN_SCALE * scale))
        im = pygame.transform.smoothscale(icon, (iw, ih))
        # 图标 anchor (0,0.5)，左缘在 x，纵向中心在 y
        s.blit(im, (int(x), int(H - y - ih / 2)))
        # 数字 anchor (0,0.5)，scale 1.6，左缘在 x + 图宽*1.1
        font = gridfont.get_font(font_index)
        if font:
            # 数字是 getCoinOrCrystalNode 节点的子节点，随该节点一起缩放 0.45；
            # 节点自身 setScale 1.6 → 数字最终缩放 = 1.6 * 0.45
            # 数字左缘 = 图标左缘 + 图宽*1.1（图标 anchor 0,0.5，左缘在 x）
            font.draw(
                s, str(value), x + iw * 1.1, H - y, NUM_SCALE * COIN_SCALE * scale, align=(0.0, 0.5)
            )

    def _draw_claim_button(self, s, scale):
        """button_reward.png：页容器子节点，anchor (0.5,0.5)，scale 0.72，
        pos (容器宽*0.76, -容器高*0.07) 相对页容器内容左下角。"""
        if not self.btn_claim:
            return
        im = res.load_img(self.btn_claim.tex)
        if not im:
            return
        w = max(1, int(im.get_width() * BTN_SCALE * scale))
        h = max(1, int(im.get_height() * BTN_SCALE * scale))
        im = pygame.transform.smoothscale(im, (w, h))
        px, py = self._page_local(scale)
        bx = px + BOX_W * 0.76 * scale
        by = py - PAGE_H * 0.07 * scale
        # 命中区始终用常态尺寸，按下态只改绘制大小（否则按下时 rect 缩水，
        # 松手前再点一次会落到按钮外面）
        self.btn_claim.rect = pygame.Rect(int(bx - w / 2), int(H - by - h / 2), w, h)
        dw, dh, h_off = w, h, 0
        # 按下态：与 DButton.draw 一致，缩到 0.94 并下移 2px
        if self._is_pressed(self.btn_claim):
            dw = max(1, int(w * 0.94))
            dh = max(1, int(h * 0.94))
            im = pygame.transform.smoothscale(im, (dw, dh))
            h_off = 2
        s.blit(im, (int(bx - dw / 2), int(H - by - dh / 2) + h_off))

    def _draw_indicator(self, s, scale):
        """page_indicator.png：每页一个，x = (容器宽 - 总宽)*0.5 + 单宽*(i+0.5)，
        y = -图高 * a3 相对页容器内容左下角。当前页不透明 255，其余 168。"""
        im = res.load_img(INDICATOR_TEX)
        if not im:
            return
        px, py = self._page_local(scale)
        iw = im.get_width() * 1.2
        ih = im.get_height() * IND_SCALE
        total = iw * PAGES
        base_x = (BOX_W - total) * 0.5
        self._ind_rects = []
        for i in range(PAGES):
            a = 255 if i == self.page else 168
            dim = im.copy()
            dim.set_alpha(a)
            x = px + (base_x + iw * (i + 0.5)) * scale
            y = py - ih * scale
            # 指示器可点：点哪一页跳到哪一页
            self._ind_rects.append(pygame.Rect(int(x - iw / 2), int(H - y - ih), int(iw), int(ih)))
            s.blit(dim, (int(x - iw / 2), int(H - y - ih)))

    # ------------------------------------------------------------ 翻页
    def _activate_click(self, pos):
        """真正执行一次点击；鼠标流程在松手时才调用它。"""
        if self.closing():
            return False
        for i, r in enumerate(getattr(self, "_ind_rects", []) or []):
            if r.collidepoint(pos):
                self.page = i
                self._page_drag_off = 0
                return True
        if super().click(pos):
            return True
        # 点面板外的暗色区域 = 关掉签到面板，避免只能领奖才能退出。
        if not self._screen_rect(_bg_scale(W, H)).collidepoint(pos):
            self.result = "close"
            self.close()
            return True
        # 面板内空白处吃掉点击，防止穿透到地图/战场。
        return True

    def click(self, pos):
        """键盘导航等直接点击立即生效；鼠标按下则延迟到 release 判定。

        判定：一开始拖动就先触发领取/关闭，13~30 天根本滑不过去。
        """
        if self.closing():
            return False
        if getattr(self, "_press_pos", None) is not None:
            self._pending_click = tuple(pos)
            return True
        return self._activate_click(pos)

    def press(self, pos):
        """按下：记按钮态与滑动起点，不立刻派发点击。"""
        self._press_pos = tuple(pos)
        self._pending_click = None
        if super().press(pos):
            self._drag_x0 = None
            self._page_drag_off = 0
            return True
        self._drag_x0 = pos[0]
        self._drag_x1 = pos[0]
        self._page_drag_off = 0
        return False

    def drag_to(self, pos):
        """拖动：页内容跟随手指横移（按在按钮上起手的不算翻页）。"""
        x0 = getattr(self, "_drag_x0", None)
        if x0 is None:
            return
        self._drag_x1 = pos[0]
        self._page_drag_off = int(pos[0] - x0)

    def release(self):
        """松手：先按位移翻页，再决定这次按下是否是点击。"""
        super().release()
        off = int(getattr(self, "_page_drag_off", 0) or 0)
        half = int(BOX_W * 0.5)
        if off <= -half:
            self.page = min(PAGES - 1, self.page + 1)
        elif off >= half:
            self.page = max(0, self.page - 1)
        self._page_drag_off = 0

        pending = getattr(self, "_pending_click", None)
        self._press_pos = None
        self._pending_click = None
        self._drag_x0 = None
        self._drag_x1 = None
        # 拖动超过 18px 视为翻页手势，不误触领取/关闭。
        if pending is not None and abs(off) < 18 and not self.closing():
            self._activate_click(pending)
            after = getattr(self.app, "_after_dialog", None)
            if after is not None and getattr(self, "done", False):
                after()
        return False

    def wheel(self, steps):
        """滚轮翻页，避免只能横拖才能看到 13~30 天。"""
        if self.closing() or not steps:
            return
        self.page = max(0, min(PAGES - 1, self.page + (1 if steps < 0 else -1)))
        self._page_drag_off = 0

    def on_key(self, key):
        """Esc 关闭；左右 / PageUp / PageDown 翻页。"""
        if key == pygame.K_ESCAPE:
            self.result = "close"
            self.close()
            return
        if key in (pygame.K_LEFT, pygame.K_PAGEUP, pygame.K_HOME):
            self.page = max(0, self.page - 1)
        elif key in (pygame.K_RIGHT, pygame.K_PAGEDOWN, pygame.K_END):
            self.page = min(PAGES - 1, self.page + 1)
        else:
            return
        self._page_drag_off = 0
