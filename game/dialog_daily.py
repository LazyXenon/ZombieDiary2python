"""每日任务 —— 原版 DialogDailyTask。

原版资源（从反编译字符串表抽出）：
  标题      pic/ui/daily_task/text_daily_tasks.png
  任务底    pic/ui/daily_task/task_bg.png
  任务按钮  pic/ui/daily_task/task_button_bg_1.png / _3.png
  已完成    pic/ui/daily_task/task_finished.png
  星标      pic/ui/daily_task/fp_star.png
  弹窗底    pic/ui/dialog/9cell_bg.png
  关闭      pic/ui/dialog/button_close.png

任务类型（原版文字贴图）：
  text_kill.png          击杀僵尸
  text_zombie.png        消灭僵尸
  text_times.png         次数
  text_update_soldier.png 升级士兵
  text_task.png          完成任务
  text_finish.png        已完成

进度存 EzGameData 的 key-value（原版 DialogDailyTask::getRewardNode），
就是存档顶层那四个累计键：
  daily_kills / daily_done_missions / daily_use_potions / daily_vungles
领取标记：task_reward_<n>
"""

import pygame

from engine import res
from game.dialog import DButton, Dialog, H, W, bg_dim, draw_bg


BG_TEX = "pic/ui/dialog/9cell_bg.png"
TITLE_TEX = "pic/ui/daily_task/text_daily_tasks.png"
ROW_BG = "pic/ui/daily_task/task_bg.png"
STAR_TEX = "pic/ui/daily_task/fp_star.png"
FINISHED_TEX = "pic/ui/daily_task/task_finished.png"
CLOSE_TEX = "pic/ui/dialog/button_close.png"
COIN_TEX = "pic/ui/common/coin.png"
CRYSTAL_TEX = "pic/ui/common/crystal.png"

# 领取按钮：底框 + 红色进度条（原版 DialogDailyTask 的画法）。
#   task_button_bg_1.png  深色空框（底板）
#   task_button_bg_3.png  红色填充条（ProgressSprite，按完成度从左往右填）
# 反编译 all_merged.c:18341：
#   sub_15125E(v109, "pic/ui/daily_task/task_button_bg_1.png");  ← 底板 z=1
#   v42 = ProgressSprite::node(v110);                          ← 进度条
#   v110 = "pic/ui/daily_task/task_button_bg_3.png";
#   进度条位置 = 底板中心 + (-3, +2.5)
#   ProgressSprite::updateSprite → EzResizableSprite::updateHidePercent(
#       0, 1-percent, 0, 0)  ⇒ 从右端吃，左边按剩余比例保留
CLAIM_BG = "pic/ui/daily_task/task_button_bg_1.png"
CLAIM_FILL = "pic/ui/daily_task/task_button_bg_3.png"
# 任务完成可领时，原版把按钮换成这张金色「领取」
REWARD_BTN_TEX = "pic/ui/shop/button_reward.png"

TASK_TEXT = {
    # kind: (条件名贴图 v96[最左], 单位贴图 v93[最右])
    "kills": ("pic/ui/dialog/text_kill.png", "pic/ui/dialog/text_zombie.png"),
    "missions": ("pic/ui/dialog/text_finish.png", "pic/ui/dialog/text_task.png"),
    "potions": ("pic/ui/dialog/text_update_soldier.png", "pic/ui/dialog/text_times.png"),
}
# 存档进度键 → 显示用的 kind
KIND_KEY = {
    "kills": "daily_kills",
    "missions": "daily_done_missions",
    "potions": "daily_use_potions",
}

# 每日任务表 —— 原版 dword_48F9AC（8 条 × 6 个 dword）。
# ★ 反编译的静态初始化（all_merged.c:143081）被 IDA 折叠成了常量池别名
#   （n1000 = 1000 / n5_1 = 5 这种），照抄它得到的表值全是错的。
#   真值从 libezjoygame.so 的 ARM 汇编解出来：
#   sub_1537E8 里 0x153968 之后一串连续 str，基址
#   r3 = (0x153972 & ~3) + 0x33c03a = 0x48F9AC（表首）。
# 每条 6 个字段（v13 = &dword_48F9AC[6*i]）：
#   [0] 金币奖励   [1] 钻石奖励
#   [2] daily_kills 需求          [3] daily_done_missions 需求
#   [4] daily_use_potions 需求    [5] daily_vungles 需求
# 需求为 0 表示无该条件。
# 汇编解出的真表：
#   task0: 500 金币   击杀 100
#   task1: 1000 金币  击杀 250
#   task2: 2500 金币  击杀 500
#   task3: 5 钻石     击杀 1000
#   task4: 2000 金币  完成 5 任务
#   task5: 5 钻石     完成 10 任务
#   task6: 500 金币   角色升级 1 次
#   task7: 1000 金币  角色升级 3 次
# 注意 task6/task7 的需求落在 **[4] daily_use_potions**，
# 但文字贴图走的是「角色升级」那对（text_times / text_update_soldier）——
# 需求字段和文字语义在原版里就不是一一对应，这里照抄。
# 本表每项：(kind, need, coin, crystal)
DAILY_TASKS = (
    ("kills", 100, 500, 0),
    ("kills", 250, 1000, 0),
    ("kills", 500, 2500, 0),
    ("kills", 1000, 0, 5),
    ("missions", 5, 2000, 0),
    ("missions", 10, 0, 5),
    ("potions", 1, 500, 0),
    ("potions", 3, 1000, 0),
)

# 兼容旧接口：(kind, need, reward_coin)
TASKS = tuple((k, n, c) for (k, n, c, _x) in DAILY_TASKS)

# ---------------------------------------------------------------- 版面常量
# 全部来自反编译 DialogDailyTask::init + getRewardNode + getCoinOrCrystalNode
# （all_merged.c:17651-18410）。
# LOGIC = EzGameScene::s_fLogicUnitLen = 1/contentScaleFactor。
# 本项目设计分辨率 854×480、contentScaleFactor = 1 ⇒ LOGIC = 1.0
# （全项目其它对话框也都用 LOGIC = 1.0，见 game/dialog_daily_reward.py:66）。
BG_SCALE = 0.6  # setScale(task_bg, 1063675494) = 0.6
LOGIC = 1.0
ROW_BG_W = 512.0  # task_bg 原始宽
ROW_BG_H = 40.0

# ---- 面板几何（DialogDailyTask::init，反编译 all_merged.c:17787-17890）
# DialogBg contentSize = (LOGIC*720, LOGIC*360)
# 缩放按 宽/高 分支：
#   <1.4 → v24=H*0.09 scale 0.82；<1.6 → H*0.02/0.87；
#   <1.7 → H*0.05/0.9；else → v24=0 scale 1.0
# 本项目 854/480 = 1.779 ⇒ v24 = 0, scale = 1.0
# DialogBg pos = (W*0.5, H*0.45 + v24) ⇒ 中心屏幕 (427, 264)
BOX_W = LOGIC * 720.0
# 原版 360 高、行距 60、8 行靠滚动。复刻不滚动 ⇒
# 面板加高到 430（列表区 260→330），行距 40，8 行 = 320 正好塞下。
BOX_H = LOGIC * 400.0
BOX_SCALE = 1.0
BOX_CX = W * 0.5
# 面板顶留 58px 给标题栏，底留 20px：58 + 400 = 458 ≤ 480。
# 内容左下角屏幕 y = (H - BOX_CY) + BOX_H/2 ⇒ 取 BOX_CY 使底部 = 478。
BOX_CY = H - (478.0 - BOX_H * 0.5)  # ⇒ 面板底 478、顶 78

# 标题栏 shop_bar.png：anchor(0.5,1.4)，pos(W*0.5, H)，scale 0.82*0.9
BAR_TEX = "pic/ui/zk_shop/shop_bar.png"
BAR_SCALE = 0.82 * 0.9

# ---- 列表容器（setDailyRewards，反编译 all_merged.c:18515-18620）
# 列表容器 contentSize = DialogBg 尺寸 − (LOGIC*95, LOGIC*100) = (625, 260)
# 列表容器 pos = (LOGIC*50, LOGIC*49)（相对 DialogBg 内容左下角，y 向上）
LIST_DX = LOGIC * 50.0
LIST_DY = LOGIC * 49.0
LIST_W = BOX_W * BOX_SCALE - LOGIC * 95.0
LIST_H = BOX_H * BOX_SCALE - LOGIC * 100.0

# ---- 行容器
# 原版：行容器 anchor(0.5,1.0)，scale 0.95，
#       pos = (列表宽*0.43, 列表高 − LOGIC*10)，逐行往下 LOGIC*60。
#       8 行 × 60 = 480 > 列表高 260 ⇒ **原版这 8 行是滚动的**
#       （EzScrollableContainer::node）。
# 复刻不实现滚动 ⇒ 行距压缩，8 行塞进列表区。
# ★ 40 → 36：列表区高 300、首行内缩 8，行距 40 时最后一行中心落在 288，
#   行条下沿 299 正好贴到列表底边的蓝色折角，截图里第 8 行被折角压住一角。
#   36 ⇒ 末行中心 260、下沿 271，离折角还有 29px。
ROW_H = 36.0
# 原版行距 60（8 行 = 480，超过列表区 260 ⇒ 原版是滚动的）。
# 复刻不滚动 ⇒ 行距压到 33，同时整行内容也要按 33/60 = 0.55 等比缩小，
# 否则文字贴图（原始 18~19px 高）和 33px 行高不成比例，挤成一团。
CONTENT_K = 1.0  # 内容不缩；靠加高面板 + 加大行距解决拥挤
ROW_SCALE = 0.95
ROW_X_RATIO = 0.43
ROW_TOP_INSET = LOGIC * 8.0  # 首行往下让 8px，不压顶边框

# ---- 行内横向锚点（getRewardNode，v57 = task_bg 的 contentSize）
#   task_bg       anchor(0,0.5)  pos(0, bg_h*0.5)      scale 0.6
#   v93 单位贴图  anchor(1,0.4)  pos(bg_w*0.47, bg_h*0.5)
#   数字          anchor(1,0.4)  scale 0.7
#                pos = 文字右缘 − 2*LOGIC − 文字宽
#   v96 条件名    anchor(1,0.4)
#                pos = 数字右缘 − 数字宽*0.7 − 2*LOGIC
#   奖励图标      anchor(0,0.5)  scale 0.6  pos(bg_w*0.63, bg_h*0.5)
#   奖励数字      score_gold/score_blue 字体，scale 1.6
#                pos = 图标宽*1.1
#   右侧按钮      pos(bg_w*1.05, bg_h*0.5)
TEXT_ANCHOR_RATIO = 0.47
ICON_ANCHOR_RATIO = 0.63
BTN_ANCHOR_RATIO = 1.05
# 需求值数字缩放。反编译是 0.7，但那是配原版 60px 行距；
# 复刻行高 40、文字贴图 18px 高，0.7 的数字只有 10px，比两边的
# 「击杀」「僵尸」小一大截，读起来断成三段。提到 0.9 让三者等高。
NUM_SCALE = 0.9
# 原版 scale 1.6，但原版行距 60 放得下；复刻行距压到 30，
# 1.6 的数字（score_gold 字号 40×1.6=64px）会撑爆整行 ⇒ 降到 1.05。
REWARD_NUM_SCALE = 1.05
# 领取按钮缩放。原版未完成时 task_button_bg_1.png 是 129 宽不缩放、
# 完成时 button_reward.png scale 0.8（170×0.8 = 136 宽）—— 两者宽度相近，
# 所以切换时按钮不会横向跳位。
# 复刻行距压到 30，放不下原版 34 高的按钮 ⇒ 统一降到 0.62：
#   未完成 129×0.62 = 80 宽、高 29（< 30 行距，不叠行）
#   完成   170×0.62 = 105 宽
# 宽度仍差 25px，但比 0.5/0.8（64 vs 136）的跳位小得多。
CLAIM_BTN_SCALE = 0.62
# 数字右缘相对文字右缘的间隙：2*LOGIC（反编译是 2 个 s_fLogicUnitLen）
TEXT_GAP = 2.0 * LOGIC

# 面板矩形（屏幕坐标）。9cell_bg.png 的九宫格中心是**透明的**
# （只是一圈描边），直接铺上去挡不住背后的地图，所以先填实底再叠边框。
PANEL = (
    int(BOX_CX - BOX_W * BOX_SCALE / 2),
    int(H - BOX_CY - BOX_H * BOX_SCALE / 2),
    int(BOX_W * BOX_SCALE),
    int(BOX_H * BOX_SCALE),
)


class DailyTaskDialog(Dialog):
    """每日任务。result: 'close'"""

    def build(self):
        # 用 DAILY_TASKS（4 元组，含钻石奖励）—— TASKS 是丢掉了 crystal 的兼容接口
        self.tasks = DAILY_TASKS
        self.add(
            DButton(
                CLOSE_TEX,
                (W * 0.94, H * 0.94),
                anchor=(0.5, 0.5),
                scale=0.8,
                name="close",
                callback=self._close,
            )
        )
        # 每个任务一行「领取」按钮（完成且未领时可见）
        self.claim = {}
        for i, (_kind, _need, _coin, _crystal) in enumerate(self.tasks):
            y = self._row_screen_y(i)
            b = self.add(
                DButton(
                    CLAIM_BG,
                    (self._btn_cx(), H - y),
                    anchor=(0.5, 0.5),
                    scale=CLAIM_BTN_SCALE,
                    name="claim%d" % i,
                    callback=self._make_claim(i),
                )
            )
            self.claim[i] = b
        self._refresh()

    # ---------------------------------------------------------------- 坐标
    def _list_origin(self):
        """列表容器的屏幕左缘 / 顶缘 / 尺寸。

        原版 DialogDailyTask::init + setDailyRewards：
          DialogBg contentSize = (LOGIC*720, LOGIC*360)，scale 1.0，
          pos = (W*0.5, H*0.45)  ⇒ 中心屏幕 (W/2, H*0.55)
          列表容器 contentSize = DialogBg 尺寸 − (LOGIC*95, LOGIC*100)
          列表容器 pos = (LOGIC*50, LOGIC*49)（相对 DialogBg 内容左下角，y 向上）

        cocos 内容坐标原点 = 父节点内容左下角 ⇒ 屏幕 y = 父底 − 局部 y。
        """
        # DialogBg anchor(0.5,0.5)，pos=(W*0.5, H*0.45)：
        #   锚点屏幕 y = H - BOX_CY = 264
        #   内容左下角屏幕 y = 锚点 + 半个高 = 264 + 180 = 444（= 面板底）
        # DialogBg anchor(0.5,0.5)，pos=(W*0.5, H*0.45)：
        #   锚点屏幕 y = H - BOX_CY = 264
        #   内容左下角屏幕 y = 锚点 + 半个高 = 264 + 180 = 444（= 面板底）
        box_left = BOX_CX - BOX_W * BOX_SCALE / 2.0
        box_bottom = (H - BOX_CY) + BOX_H * BOX_SCALE / 2.0
        # 列表容器 pos=(LOGIC*50, LOGIC*49)，是相对 DialogBg 内容左下角的
        # **内容坐标**（y 向上）⇒ 列表容器内容左下角屏幕 y = 面板底 − 49
        lx = box_left + LIST_DX
        lbottom = box_bottom - LIST_DY
        ltop = lbottom - LIST_H  # 列表容器内容顶缘（屏幕 y）
        return lx, ltop, LIST_W, LIST_H

    def _row_screen_y(self, i):
        """第 i 行的任务条中心（屏幕 y）。

        原版：行容器 anchor(0.5,1.0)，逐行往下 LOGIC*60（这里是 30）。
        行容器在列表容器内 pos.y = 列表高 − LOGIC*10（内容坐标，向上）。
        """
        _lx, ltop, _lw, _lh = self._list_origin()
        top = ltop + ROW_TOP_INSET
        return top + i * ROW_H

    def _row_origin_x(self):
        """任务条贴图的左缘（屏幕 x）。

        原版：行容器 pos.x = 列表宽*0.43，anchor(0.5,1.0)，scale 0.95。
        行容器内容宽 = task_bg 的 contentSize（未缩放的 512），
        行容器 anchor 0.5 ⇒ 内容左缘 = 锚点 x − 512/2；
        再乘行容器 scale 0.95 得到贴图实际左缘。
        """
        lx, _ltop, lw, _lh = self._list_origin()
        row_cx = lx + lw * ROW_X_RATIO
        return row_cx - ROW_BG_W * ROW_SCALE / 2.0

    def _btn_cx(self):
        """领取按钮中心（屏幕 x）。原版 pos = bg_w*1.05（相对行容器左缘）。"""
        return self._row_origin_x() + ROW_BG_W * ROW_SCALE * BTN_ANCHOR_RATIO

    def _progress(self, kind, need):
        """读当前任务进度。

        原版直接读存档顶层的四个累计键（不是子字典）：
          daily_kills          累计击杀
          daily_done_missions  通关数
          daily_use_potions    升级士兵次数（喝药水）
          daily_vungles        漏过传送门的僵尸

        从上面那四个键映射过来 —— 多绕一层，还容易漏同步。
        现在直接读原版键，和反编译一致。
        """
        key = KIND_KEY.get(kind)
        if not key:
            return 0
        return int(self.app.save.d.get(key, 0) or 0)

    def _claimed(self, i):
        """领取标记 —— 原版用 task_reward_<i> 存档键。

        DailyTaskManager::getLeftTaskCount @0x150ff4（all_merged.c:15551）：
            format(v6, "task_reward_%d", i);
            KeyValue = getKeyValue(v6, 0);
            v2 += (KeyValue == 0);      ← 为 0 表示还没领
        早先复刻自造了 daily_claimed 键，和原版存档不兼容。
        """
        return bool(int(self.app.save.d.get("task_reward_%d" % i, 0) or 0))

    def _make_claim(self, i):
        def handler(btn):
            kind, need, coin, crystal = self.tasks[i]
            if self._progress(kind, need) < need or self._claimed(i):
                return
            self.app.save.d["task_reward_%d" % i] = 1
            if coin:
                self.app.save.add_coins(coin)
            if crystal:
                self.app.save.add_crystals(crystal)
            self.app.save.save()
            self.app.audio.coin()
            # 金币/钻石飞进账户（和签到、成就同一套动画）
            fly = getattr(self.app, "reward_fly", None)
            if fly is not None and (coin or crystal):
                br = getattr(self.claim[i], "rect", None)
                x0, y0 = (br.centerx, br.centery) if br else (427, 300)
                fly.spawn(x0, y0, int(coin), int(crystal))
            self._refresh()

        return handler

    def _close(self, btn):
        self.result = "close"
        self.done = True

    def _refresh(self):
        for i, (kind, need, _coin, _crystal) in enumerate(self.tasks):
            done = self._progress(kind, need) >= need
            claimed = self._claimed(i)
            self.claim[i].enabled = done and not claimed

    def on_key(self, key):
        if key == pygame.K_ESCAPE:
            self.result = "close"
            self.done = True

    def draw(self, s):
        bg_dim(s, 180)
        # 底板：先铺一层不透明深紫（9cell_bg 中心透明，单靠描边挡不住地图），
        # 再叠 3×3 九宫格描边。
        from game.ninecell import draw_9cell_atlas, fill_panel

        pr = pygame.Rect(*PANEL)
        # ★ 底色必须铺在框线**以内**（用户：「所有背景都不能超过边框」）
        fill_panel(s, BG_TEX, pr, (58, 40, 96, 255), 1.0)
        draw_9cell_atlas(s, BG_TEX, pr, 1.0)

        # 标题栏 shop_bar.png：anchor(0.5,1.4)，pos(W*0.5, H)，scale 0.82*0.9
        bar = res.load_img(BAR_TEX)
        if bar:
            bw2, bh2 = bar.get_size()
            sw, sh = int(bw2 * BAR_SCALE), int(bh2 * BAR_SCALE)
            # anchor(0.5,1.4) ⇒ 以底边上方 40% 为锚点，贴到屏幕 y=0 附近
            s.blit(
                pygame.transform.smoothscale(bar, (sw, sh)), (int(W * 0.5 - sw / 2), int(-sh * 0.4))
            )

        # 标题文字 text_daily_tasks.png：pos = shop_bar 尺寸 × (0.5, 0.48)
        ti = res.load_img(TITLE_TEX)
        if ti:
            s.blit(ti, (int(W * 0.5 - ti.get_width() / 2), 44))

        for i, (kind, need, coin, crystal) in enumerate(self.tasks):
            self._draw_row(s, i, kind, need, coin, crystal, self._row_screen_y(i))

        # 领取按钮：底框 + 红色进度条（原版 ProgressSprite 的画法）
        self._draw_claim_buttons(s)

        # 其余按钮（关闭等）；领取按钮已由 _draw_claim_buttons 画过
        for b in self.buttons:
            if b.name.startswith("claim"):
                continue
            b.draw(s, self._is_pressed(b))

    def _draw_row(self, s, i, kind, need, coin, crystal, y):
        """一行每日任务 —— 严格按 DialogDailyTask::getRewardNode 反编译。

        all_merged.c:18195-18400 的节点顺序（从右往左看，因为 anchor 都是 1）：
          1. task_bg.png      anchor(0,0.5) setScale(0.6)
                             pos = (0, bg_h*0.5)   父节点是行容器
          2. v93 单位贴图      anchor(1,0.4)  pos = (bg_w*0.47, bg_h*0.5)
          3. 数字 EzTexText   anchor(1,0.4)  scale 0.7
                             pos = 文字右缘 − 2*LOGIC − 文字宽
          4. v96 条件名贴图    anchor(1,0.4)
                             pos = 数字右缘 − 数字宽*scale − 2*LOGIC
          5. 金币/钻石图标     anchor(0,0.5)  scale 0.6
                             pos = (bg_w*0.63, bg_h*0.5)
          6. 奖励数字         （getCoinOrCrystalNode 带出）
          7. 右侧按钮：完成未领 → button_reward；未完成 → task_button_bg_1
             + ProgressSprite(task_button_bg_3) + 百分比 EzScoreText

        ★ 数字显示的是**需求值**（`EzStringUtils::format(v105, "%d", v61)`，
        v61 就是 v13[2]/v13[3]/v13[4]），不是当前进度 ——
        当前进度由右侧那条填充条的百分比表示。
        """
        bg = res.load_img(ROW_BG)
        if not bg:
            return

        # ---- 第 2 步：v93 单位贴图（anchor 1,0.4 ⇒ 右缘对齐 x）
        # 反编译 v77 = (bg_w*0.47, bg_h*0.5) 是 v93 的 **pos**（anchor 1,0.4 ⇒ 右缘）。
        # v93 是**单位**（「僵尸」「任务」「次」），v96 是**条件名**（「击杀」「完成」「角色升级」），
        # 中间夹一个**需求值数字**。整行从左到右读作「击杀 100 僵尸」。
        #   task_bg 自己的 scale 0.6 只作用于**它自己**，不影响兄弟节点；
        #   v93 / v96 是行容器（scale 0.95）的直接子节点，**自身不缩放**，
        #   所以文字贴图的绘制尺寸 = 原始像素 × 0.95；
        #   它们的 pos 用的是**行容器内容坐标**（v57 = task_bg 的 contentSize
        #   512×40），所以屏幕 x = 行左缘 + 内容坐标 × 0.95（行容器 scale）。
        # 行容器内容宽 = task_bg 的 contentSize = 512
        content_w = ROW_BG_W  # 512（行容器内容坐标）
        row_k = ROW_SCALE  # 行容器 scale 0.95
        ck = CONTENT_K  # 行内容等比缩（33/60）
        # 任务条贴图：task_bg 自己 scale 0.6，在行容器 scale 0.95 内
        draw_w = content_w * BG_SCALE * row_k  # 291.8
        draw_h = ROW_BG_H * BG_SCALE * row_k  # 22.8
        x0 = self._row_origin_x()
        s.blit(
            pygame.transform.smoothscale(bg, (int(draw_w), int(draw_h))),
            (int(x0), int(y - draw_h / 2)),
        )

        def cx(content_x):
            """行容器内容坐标 x → 屏幕 x。"""
            return x0 + content_x * row_k

        cond_tex, unit_tex = TASK_TEXT.get(kind, (None, None))
        # 文字贴图在行容器内容坐标里，绘制尺寸 = 原始 × 0.95
        text_anchor_x = cx(content_w * TEXT_ANCHOR_RATIO)
        unit_w = 0
        if unit_tex:
            im = res.load_img(unit_tex)
            if im:
                iw, ih = im.get_size()
                unit_w = iw * row_k * ck
                s.blit(
                    pygame.transform.smoothscale(im, (int(iw * row_k * ck), int(ih * row_k * ck))),
                    (int(text_anchor_x - unit_w), int(y - ih * row_k * ck * 0.4)),
                )

        # ---- 第 3 步：需求值数字（daily_task_num 字体，scale 0.7，anchor 1,0.4）
        # 反编译：数字右缘 = 文字右缘 − 2*LOGIC − 文字宽
        #         （all_merged.c:18236 `v77[0] = v19 - (2*LOGIC + 文字宽)`）
        # 数字的 pos 用行容器内容坐标，绘制 scale 0.7 × 行容器 0.95。
        num_right = text_anchor_x - TEXT_GAP * row_k * ck - unit_w
        if need > 0:
            self._draw_num_text(s, str(need), num_right, y, NUM_SCALE * row_k * ck)

        # ---- 第 4 步：v96 条件名贴图
        # 反编译：条件名右缘 = 数字右缘 − 数字宽*scale − 2*LOGIC
        if cond_tex and need > 0:
            im = res.load_img(cond_tex)
            if im:
                iw, ih = im.get_size()
                num_w = self._num_width(str(need)) * NUM_SCALE * row_k * ck
                cond_right = num_right - num_w - TEXT_GAP * row_k * ck
                s.blit(
                    pygame.transform.smoothscale(im, (int(iw * row_k * ck), int(ih * row_k * ck))),
                    (int(cond_right - iw * row_k * ck), int(y - ih * row_k * ck * 0.4)),
                )

        # ---- 第 5 步：奖励图标 + 奖励数字
        # getCoinOrCrystalNode（all_merged.c:17651）：
        #   金币 > 0 → coin.png + score_gold 字体，scale 1.6
        #   钻石 > 0 → crystal.png + score_blue 字体，scale 1.6
        #   两者都 0 → 空节点
        # 图标是行容器的子节点，自身 scale 0.6 ⇒ 实际 0.6 × 0.95
        if coin > 0:
            icon, amount, is_gold = res.load_img(COIN_TEX), coin, True
        elif crystal > 0:
            icon, amount, is_gold = res.load_img(CRYSTAL_TEX), crystal, False
        else:
            icon, amount, is_gold = None, 0, True
        icon_x = cx(content_w * ICON_ANCHOR_RATIO)
        if icon:
            iw, ih = icon.get_size()
            sc = 0.6 * row_k * ck
            s.blit(
                pygame.transform.smoothscale(icon, (int(iw * sc), int(ih * sc))),
                (int(icon_x), int(y - ih * sc / 2)),
            )
            # 奖励数字：原版用 score_gold / score_blue 位图字体，scale 1.6，
            # pos = 图标宽*1.1（在行容器内）
            rt = self._reward_num(amount, is_gold, ck)
            if rt:
                s.blit(rt, (int(icon_x + iw * sc * 1.1), int(y - rt.get_height() / 2)))

        # ---- 已领取标记
        if self._claimed(i):
            fin = res.load_img(FINISHED_TEX)
            if fin:
                fw2, fh2 = fin.get_size()
                k2 = (ROW_H * 0.60) / float(fh2)
                sw2 = max(1, int(fw2 * k2))
                sh2 = max(1, int(fh2 * k2))
                s.blit(
                    pygame.transform.smoothscale(fin, (sw2, sh2)),
                    (int(x0 + draw_w - sw2 - 6), int(y - sh2 / 2)),
                )

    def _reward_num(self, value, is_gold=True, ck=1.0):
        """奖励数字 —— 原版用 score_gold（币）/ score_blue（钻）位图字体。

        getCoinOrCrystalNode（all_merged.c:17651）：
          金币 → GameFonts::getTexFont(1) = score_gold，scale 1.6
          钻石 → GameFonts::getTexFont(3) = score_blue，scale 1.6
        早先这里用系统字（Microsoft YaHei），和原版的位图字体不是一个样子。
        """
        from engine import gridfont

        font = gridfont.get_font(1 if is_gold else 3)
        if font is None:
            return None
        sc = REWARD_NUM_SCALE * ROW_SCALE * ck
        w, h = font.text_size(str(value), sc)
        surf = pygame.Surface((max(1, int(w)), max(1, int(h))), pygame.SRCALPHA)
        font.draw(surf, str(value), 0, h / 2.0, sc, align=(0.0, 0.5))
        return surf

    def _num_width(self, text):
        """daily_task_num 位图字体的文本宽度（未乘 scale）。"""
        font = res.load_img("pic/fonts/daily_task_num.png")
        if not font:
            return 0.0
        cw = font.get_width() // 5
        return float(cw * len(str(text)))

    def _draw_num_text(self, s, text, right_x, y, scale):
        """用 daily_task_num 位图字体画需求值数字。

        原版这里用的是 EzTexText（getTexFont(8) = daily_task_num），
        不是系统字。字体只有 5 格「01235」（GameFonts 注释），
        所以画不出来的字符会留空位。

        ★ 真表里的需求值恰好只用这五个数字（100 / 250 / 500 / 1000 / 5 / 10 / 1 / 3），
        这反过来验证了从 ARM 汇编解出来的表是对的 —— 早先照抄反编译里
        被 IDA 折叠的常量池（得到 4000）根本画不出来。
        """
        digits = "01235"
        font = res.load_img("pic/fonts/daily_task_num.png")
        if not font:
            return
        cw = font.get_width() // 5
        ch = font.get_height()
        w = cw * scale
        x = right_x - len(str(text)) * w
        for ch_ in str(text):
            if ch_ not in digits:
                x += w
                continue
            i = digits.index(ch_)
            cell = font.subsurface(pygame.Rect(i * cw, 0, cw, ch)).copy()
            s.blit(
                pygame.transform.smoothscale(cell, (int(w), int(ch * scale))),
                (int(x), int(y - ch * scale / 2)),
            )
            x += w

    def _draw_claim_buttons(self, s):
        """每个任务右侧的领取框。

        原版 getRewardNode（all_merged.c:18280-18410）分两种：
          · 完成且未领 → `pic/ui/shop/button_reward.png`（anchor 0.48,0.5，
            scale 0.8，pos = bg_w*1.05）
          · 未完成     → `task_button_bg_1.png` 作底板（z=1），
            ProgressSprite(`task_button_bg_3.png`) 叠上面（z=2），
            再叠一个 EzScoreText 百分比（z=4，anchor 0.5,0.5，scale 0.8，
            贴在底板中心），内容 = int(percent*100) + "%"

        ProgressSprite::updatePercent(0, percent, percent*2) ⇒
        updateHidePercent(0, 1-percent, 0, 0) ⇒ **从右端吃**，
        左边按剩余比例保留。
        """
        bg = res.load_img(CLAIM_BG)
        fill = res.load_img(CLAIM_FILL)
        reward = res.load_img(REWARD_BTN_TEX)
        if not bg:
            return
        bw, bh = bg.get_size()
        scale = CLAIM_BTN_SCALE
        for i, (kind, need, _coin, _crystal) in enumerate(self.tasks):
            b = self.claim.get(i)
            if b is None:
                continue
            # 所有元素都以按钮**中心**对齐 —— 底框 129×0.62=80、
            # button_reward 170×0.62=105，两者宽度不同，按左上角画会左右错位。
            bcx, bcy = b.rect.centerx, b.rect.centery
            done = self._progress(kind, need) >= need if need > 0 else False
            if done and not self._claimed(i):
                # 已完成可领：原版换成金色的 button_reward
                if reward:
                    rw, rh = reward.get_size()
                    rs = CLAIM_BTN_SCALE
                    sw, sh = int(rw * rs), int(rh * rs)
                    s.blit(
                        pygame.transform.smoothscale(reward, (sw, sh)),
                        (int(bcx - sw / 2), int(bcy - sh / 2)),
                    )
                continue
            sw0, sh0 = int(bw * scale), int(bh * scale)
            s.blit(
                pygame.transform.smoothscale(bg, (sw0, sh0)),
                (int(bcx - sw0 / 2), int(bcy - sh0 / 2)),
            )
            x = int(bcx - sw0 / 2)
            y = int(bcy - sh0 / 2)
            pct = 0.0
            if need > 0:
                pct = min(1.0, self._progress(kind, need) / float(need))
            if fill and not self._claimed(i) and pct > 0:
                fw, fh = fill.get_size()
                tw = max(1, int(round(fw * pct)))
                sub = fill.subsurface(pygame.Rect(0, 0, tw, fh)).copy()
                sw, sh = int(fw * scale), int(fh * scale)
                sub = pygame.transform.smoothscale(sub, (max(1, int(round(tw * scale))), sh))
                pad = (bw - fw) / 2.0
                bar_x = x + int(pad * scale)
                cy = y + int(bh * scale / 2) - int(2.5 * scale)
                s.blit(sub, (bar_x, cy - sub.get_height() // 2))
            # ★ 百分比文字无条件画（含 0%）：
            #   0% 时底板里空着，一整列深色空框看着像「按钮没加载出来」。
            pt = pygame.font.SysFont("Microsoft YaHei", 13, bold=True).render(
                "%d%%" % int(pct * 100), True, (255, 255, 255)
            )
            cx = x + int(bw * scale / 2)
            cy = y + int(bh * scale / 2) - int(2.5 * scale)
            s.blit(pt, (int(cx - pt.get_width() / 2), int(cy - pt.get_height() / 2)))
