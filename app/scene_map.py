"""地图 / 主菜单 / 关卡选择 的场景渲染与按钮命中。"""

import pygame

from app.constants import (
    COIN_ICON,
    CRYS_ICON,
    MAP_PLUS_SIZE,
    MAP_PLUS_X,
    MAP_PLUS_Y,
    MAP_SKIP,
    MAP_STATIC_HIDE,
    MAP_TEXFIX,
    MAP_UPBAR,
    UI,
    H,
    W,
)
from engine import (
    res,
)
from engine import (
    scene as SC,
)
from game import map_points as MP
from game.achievement import AchievementPanel
from game.dialog_daily import DailyTaskDialog
from game.dialog_level_select import LevelSelectDialog
from game.dialog_settings import SettingsDialog
from game.dialog_zombie_shop import ZombieShopDialog
from game.main_menu import MainMenu
from game.map_buttons import MapButtons
from game.map_focus import FocusEffect
from game.slot import SlotPanel
from game.user_guide import UserGuide


class MapSceneMixin:
    """地图 / 主菜单 / 关卡选择 的场景渲染与按钮命中。"""

    def draw_menu(self, s):
        if self.main_menu is None:
            self.main_menu = MainMenu(self)
        # 主菜单不画金币/钻石行：模拟器参考帧 emu_menu.png 左下角是纯背景岩石，
        # 只有地图层和战斗层才有货币行。这里多画一行会压在场景上。
        self.main_menu.draw(s)

    def draw_map(self, s):
        # 原版 MapLayer 的绘制顺序（模拟器参考帧 emu_map7.png 逐像素核对）：
        #   1) 地图背景 pic/map_bg01.jpg
        #   2) 黑色 50% 遮罩 —— 只压暗背景
        #      （反编译 EzAdLayer::init @0x1c8764：
        #        CCLayerColor::layerWithColorWidthHeight(color=(0,0,0,0x80), W, H)）
        #   3) 地图内容：灯光 / 粒子 / zone 名牌 / 任务气泡 / 侧边按钮
        #   4) 顶栏 up_bar（含货币、「第 N 天」）
        # 参考帧确认：背景比贴图暗一半，而气泡、名牌、顶栏、侧边按钮全是亮色，
        # ⇒ 遮罩只盖背景，不盖 UI。
        bg = res.load_img("pic/map_bg01.jpg")
        if bg:
            s.blit(SC.scaled(bg, W, H), (0, 0))
        if getattr(self, "_dim", None) is None:
            # 50% 黑遮罩是常量，没有必要每帧新建一张全屏 SRCALPHA 再 fill
            self._dim = pygame.Surface((W, H), pygame.SRCALPHA)
            self._dim.fill((0, 0, 0, 128))
        s.blit(self._dim, (0, 0))

        SC.draw_tree(
            s,
            self.trees["map"],
            self.texs["map"][0],
            self.texs["map"][1],
            self.texs["map"][2],
            opa_fn=self._map_light_alpha,
            texfix=self._slot_texfix(),
            skip_addr=MAP_SKIP,
            exclude={MAP_UPBAR},
        )
        MP.draw_zone_labels(s, MP.unlocked_zones(self.level_db, self.save))
        # ★ 区域描边会横穿两侧按钮（参考帧对照：zone_lcd 的青色描边压在
        #   「老虎机」按钮上，把白字糊成灰字）。节点树里按钮先画、区域图后画，
        #   原版按钮是独立 UI 层永远在区域图之上 —— 这里补画一遍按钮盖住描边。
        self._redraw_side_buttons(s)
        self._draw_focus_effect(s)
        MP.draw_points(s, self.map_points, self.save, self.shop_font)
        # 顶栏画在最后（货币 / 「第 N 天」都在 up_bar 子树里）
        # ★ 这里也必须传 skip_addr=MAP_SKIP：成就/每日任务的静态角标
        #   （dump 时残留的「0」「1」）挂在这棵子树里，漏传就会把
        #   按真实数量画好的数字又盖回「0」。
        SC.draw_tree(
            s,
            self.trees["map"],
            self.texs["map"][0],
            self.texs["map"][1],
            self.texs["map"][2],
            only=MAP_UPBAR,
            hide=MAP_STATIC_HIDE,
            skip_addr=MAP_SKIP,
        )
        self._draw_dynamic_topbar(s)
        # ★ 角标必须最后画：荣誉殿堂/设置按钮本身就在 up_bar 子树里，
        #   上面那次 draw_tree 会重画按钮底图，把先画的角标整个盖住
        self._draw_map_buttons(s)

    def _draw_dynamic_topbar(self, s):
        """顶栏里 dump 烘死的三个数字，按存档重画。

        原节点树抓 dump 时是「3.000 金币 / 5 钻石 / 第 1 天」，静态节点
        已在 MAP_STATIC_HIDE 里隐藏。这里盖一层顶栏底图再画真值，
        否则通关后永远显示第 1 天，玩家会以为关卡没解锁。
        """
        from engine import gridfont
        from engine import res as _res
        from game.map_points import current_level

        bar = _res.load_img("pic/ui/map/map_up_bar.png")
        gold = gridfont.get_font(1)  # score_gold，金币数
        blue = gridfont.get_font(3)  # score_blue，钻石数
        white = gridfont.get_font(0)  # score_white，「第 N 天」的数字
        if not (gold and blue and white):
            return
        # 底图里「第 / 天」是烘死的，数字位置留空。裁这块盖住 dump 时
        # 残留的「1」，「第 / 天」自然由底图恢复。
        if bar:
            patch = bar.subsurface(pygame.Rect(307, 4, 240, 28))
            s.blit(patch, (307, 4))
        coins = int(self.save.d.get("coins", 0))
        crystals = int(self.save.d.get("crystals", 0))
        fly = getattr(self, "reward_fly", None)
        if fly is not None:
            coins -= fly.pending_coin
            crystals -= fly.pending_crystal
        gs = fly.pop_scale("coin") if fly is not None else 1.0
        bs = fly.pop_scale("crystal") if fly is not None else 1.0

        ico = SC.node_rects(
            self.trees["map"], self.texs["map"][0], self.texs["map"][1], H, (COIN_ICON, CRYS_ICON)
        )
        coin_r = ico.get(COIN_ICON)
        crys_r = ico.get(CRYS_ICON)
        if coin_r is None or crys_r is None:
            return
        coin_img = res.load_img("pic/ui/common/coin.png")
        crys_img = res.load_img("pic/ui/common/crystal.png")
        plus = res.load_img("pic/ui/buttons/add_crystal_button.png")
        if coin_img is None or crys_img is None:
            return

        coin_x, coin_y, coin_w, coin_h = coin_r
        crys_w, crys_h = crys_r[2], crys_r[3]
        row_y = coin_y + coin_h * 0.5
        g_txt = f"{max(0, coins):,}"
        b_txt = str(max(0, crystals))
        gk, bk = 0.97 * gs, 0.97 * bs
        gw = gold.text_size(g_txt, gk)[0]
        bw = blue.text_size(b_txt, bk)[0]
        # 图标、间隔、「+」是固定开销，只有文字可以压缩；右界取军火库按钮
        # 左边，钱再多也不会压到按钮上。图标跟着文字顺排，短数字时钻石
        # 图标仍停在原版位置。
        shop_r = self.map_buttons.get("shop") if self.map_buttons else None
        right = (shop_r.x - 8) if shop_r is not None else MAP_PLUS_X + MAP_PLUS_SIZE
        fixed = coin_w + 5 + 8 + crys_w + 6 + 8 + MAP_PLUS_SIZE
        avail = right - coin_x - fixed
        if gw + bw > avail:
            k = max(0.30, min(1.0, avail / float(gw + bw)))
            gk *= k
            bk *= k
            gw = gold.text_size(g_txt, gk)[0]
            bw = blue.text_size(b_txt, bk)[0]

        s.blit(SC.scaled(coin_img, int(coin_w), int(coin_h)), (int(coin_x), int(coin_y)))
        gx = coin_x + coin_w + 5
        gold.draw(s, g_txt, gx, row_y, gk, align=(0.0, 0.5))
        cx = max(crys_r[0], gx + gw + 8)
        s.blit(SC.scaled(crys_img, int(crys_w), int(crys_h)), (int(cx), int(crys_r[1])))
        bx = cx + crys_w + 6
        blue.draw(s, b_txt, bx, row_y, bk, align=(0.0, 0.5))
        px = min(bx + bw + 8, right - MAP_PLUS_SIZE)
        if plus:
            s.blit(SC.scaled(plus, MAP_PLUS_SIZE, MAP_PLUS_SIZE), (int(px), int(MAP_PLUS_Y)))
        # 「+」位置跟着数字走，命中区必须同步，否则点得到账会点空。
        if self.map_buttons is not None:
            self.map_buttons.rects["add_crystal"] = pygame.Rect(
                int(px), int(MAP_PLUS_Y), MAP_PLUS_SIZE, MAP_PLUS_SIZE
            )

        day = current_level(self.save, self.level_db)
        white.draw(s, str(day), 414.0, 16.0, 1.1, align=(0.5, 0.5))

    def _map_light_alpha(self, node, tex):
        """MapLayer::addLightEffect：区域光效按原版动画循环淡入淡出。"""
        from game.map_lights import light_alpha

        if "light" not in tex:
            return None
        addr = node.get("addr") or ""
        seed = (int(addr, 16) % 97) * 0.37 if addr else 0.0
        return light_alpha(tex, self.t, seed)

    def _redraw_side_buttons(self, s):
        """补画左右两侧 4 个按钮，盖住后画的区域描边。

        节点树里按钮和区域图是同一棵子树，区域图排在后 ⇒ 描边压到按钮上；
        原版按钮是 MapLayer 的 UI 层，始终在区域图之上。
        老虎机按钮还带「免费 / 限免」子标签，盖了按钮要把它补回来。
        """
        from game import map_buttons as MB

        if self.map_buttons is None:
            self.map_buttons = MapButtons(self)
        for key, tex in (
            ("daily", MB.DAILY_TEX),
            ("zombie_shop", MB.ZOMBIE_SHOP_TEX),
            ("slots", MB.SLOTS_TEX),
            ("reward_notify", MB.REWARD_NOTIFY_TEX),
        ):
            r = self.map_buttons.get(key)
            img = res.load_img(tex)
            if r is None or img is None:
                continue
            s.blit(SC.scaled(img, r.w, r.h), r.topleft)
        # 老虎机按钮上的状态标签（MapLayer::updateSlotButton）
        r = self.map_buttons.get("slots")
        if r is not None:
            free = int(self.save.d.get("free_spin_0", 0) or 0) > 0
            lab = res.load_img(
                "pic/ui/map/text_free_slot.png" if free else "pic/ui/map/text_slot.png"
            )
            if lab:
                cx = r.left + r.w * 0.58
                cy = r.bottom - r.h * 0.40
                s.blit(lab, (int(cx - lab.get_width() / 2), int(cy - lab.get_height() / 2)))

    def _draw_map_buttons(self, s):
        """地图按钮由节点树渲染（树里的位置经原版截图 NCC 校验一致）。

        这里只补**角标**（count_bg + 数字）—— 原版按数量动态显示：
          MapLayer::addNewAchievementEffect(count)  成就角标（count<=0 隐藏）
          MapLayer::updateDailyTaskEffect(count)    每日任务角标（count<=0 隐藏）
        树里的是 dump 时的静态残留（成就「0」、每日「1」），故跳过树里的角标，
        改由这里按反编译公式重画。
        """
        from engine import gridfont

        if self.map_buttons is None:
            self.map_buttons = MapButtons(self)
        font = gridfont.get_font(0)  # EzTexText(getTexFont(0)) = score_white
        if font is None:
            return
        cnt_bg = res.load_img("pic/ui/map/count_bg.png")
        if not cnt_bg:
            return
        # count_bg：anchor(0.5,0.5)，scale 0.5，pos = 按钮局部 (w*0.85, h*0.85)
        #   反编译：EzSprite::setScale(count_bg, 1056964608 = 0.5)
        bw, bh = cnt_bg.get_size()
        sc = 0.5
        w, h = int(bw * sc), int(bh * sc)
        bg = pygame.transform.smoothscale(cnt_bg, (w, h))

        def badge(btn_name, n):
            if n <= 0:
                return
            btn = self.map_buttons.get(btn_name) if self.map_buttons else None
            if btn is None:
                return
            # 按钮局部原点在左下角（cocos y 向上）
            cx = btn.x + btn.width * 0.85
            cy = btn.bottom - btn.height * 0.85
            s.blit(bg, (int(cx - w / 2), int(cy - h / 2)))
            # 数字：EzTexText anchor(0.38,0.42)，scale 0.55，位置同 count_bg
            font.draw(s, str(n), cx, cy, 0.55, align=(0.38, 0.42))

        from game.achievement import claimable_count

        badge("achivement", claimable_count(self))
        # 每日任务角标：未领取的每日任务数
        badge("daily", self._daily_task_left())

    def _draw_focus_effect(self, s):
        """当前关卡的聚焦高亮（focus_level_effect 骨骼动画，循环）。

        原版 MapLayer::initLevelMissions（all_merged.c:78766）：
          ZoneColorType = getZoneColorType(zone)（默认 1）
          createAnimation("pic/effect/focus_level_effect/sheets_%d.xml",
                          ".../animations.xml", 循环)
          setScale(0.25)
          位置 = zone 锚点 + (-280, +230) × 0.25

        高亮挂在**第一个未通关的任务点**上（当天任务可任意顺序打）。
        """
        pts = getattr(self, "map_points", None)
        if not pts:
            return
        p0 = pts[0]
        fx = getattr(self, "_focus_fx", None)
        if fx is None or fx.zone != p0.zone:
            fx = FocusEffect(p0.zone, p0.x, p0.y)
            self._focus_fx = fx
        # 动画按时间推进（地图是静态场景，用全局 t）
        fx.t = getattr(self, "t", 0.0)
        fx.draw(s)

    def _slot_texfix(self):
        """老虎机按钮上的「免费 / 限免」标签贴图（动态）。

        原版 MapLayer::updateSlotButton @0x1211f4（反编译 all_merged.c:75339）：
            free_spin_0 = getKeyValue("free_spin_0", 0)
            if (free_spin_0 <= 0)  → "pic/ui/map/text_slot.png"    （限免）
            else                   → "pic/ui/map/text_free_slot.png"（免费）
        这个标签是老虎机按钮的**子节点**（节点树地址 0xc7dfd304，
        pos = (按钮宽*0.58, 按钮高*0.4) = (76.56, 29.2)，
        anchor(0.5,0.5)，size 47×22）。

        静态的 MAP_TEXFIX 把这个节点固定成 text_slot.png（限免），
        这里按存档实时改 —— 免费次数用掉后地图上的标签立刻变成「限免」。

        ★ 老虎机入口按钮在屏幕右缘，原版参考帧（feat/map.png）里就是
          **被裁掉一半**的，所以标签本身也大半在屏外；
          真正能看清免费/限免的地方是老虎机面板（pic/ui/slot/text_free_spin.png）。
        """
        fix = dict(MAP_TEXFIX)
        free = int(self.save.d.get("free_spin_0", 0) or 0) > 0
        fix["0xc7dfd304"] = "pic/ui/map/text_free_slot.png" if free else "pic/ui/map/text_slot.png"
        return fix

    def _daily_task_left(self):
        """DailyTaskManager::getLeftTaskCount @0x150ff4：未领取奖励的每日任务数。

        反编译（all_merged.c:15551）：
            for (i < 8) {
                format(v6, "task_reward_%d", i);
                KeyValue = getKeyValue(v6, 0);
                v2 += (KeyValue == 0);      ← 还没领的计入
            }
            return v2;

        原版数的是「**还没领**的任务数」（含未完成的），不是「已完成未领」。
        ⇒ 恒返回 8，地图上的角标永远是 8。
        """
        try:
            from game.dialog_daily import DAILY_TASKS

            total = len(DAILY_TASKS)
        except Exception:
            total = 0
        left = 0
        for i in range(total):
            if not int(self.save.d.get("task_reward_%d" % i, 0) or 0):
                left += 1
        return left

    def draw_level(self, s):
        """关卡选择框：DialogLevelSelect（game/dialog_level_select.py）。"""
        SC.draw_tree(
            s,
            self.trees["map"],
            self.texs["map"][0],
            self.texs["map"][1],
            self.texs["map"][2],
            bg_tex="pic/map_bg01.jpg",
        )
        MP.draw_zone_labels(s, MP.unlocked_zones(self.level_db, self.save))
        self._draw_focus_effect(s)
        MP.draw_points(s, self.map_points, self.save, self.shop_font)
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 128))
        s.blit(dim, (0, 0))
        if self.level_dialog is None:
            self.level_dialog = LevelSelectDialog(self, self.mission_id)
        self.level_dialog.draw(s)
        # 这里不画 draw_coins —— DialogLevelSelect 是模态框，
        # 原版参考帧（emu_b3_s.png）关掉地图层后画面上没有金币/钻石计数器，
        # 画了会压住底部推荐条。奖励数字在对话框自己的奖励行里。

    def draw_mission_texts(self, s):
        """任务文案条（getMissionTextPath @0x14b90c）：预渲染条 + 数字。"""
        mid = self.mission_id
        info = self.level_db.get(mid)
        if not info:
            return
        mtype = info["type"]
        base = mtype.replace("_mission", "")
        n1 = "pic/ui/dialog/%s_mission_text_1.png" % base
        n2 = "pic/ui/dialog/%s_mission_text_2.png" % base
        y = 262
        x = 200
        img = res.load_img(n1)
        if img:
            s.blit(img, (x, y))
            y += img.get_height() + 2
        # 数字行
        f = pygame.font.SysFont("Arial", 22, bold=True)
        if mtype == "time_mission":
            img2 = res.load_img("pic/ui/dialog/text_in.png")
            if img2:
                s.blit(img2, (x, y))
            s.blit(f.render("%d" % info["number"], True, (90, 40, 20)), (x + 40, y + 2))
            img3 = res.load_img("pic/ui/dialog/text_in_second.png")
            if img3:
                s.blit(img3, (x + 40 + f.size("%d" % info["number"])[0] + 4, y))
        else:
            img2 = res.load_img(n2)
            if img2:
                s.blit(img2, (x, y))
                s.blit(
                    f.render("%d" % info["number"], True, (90, 40, 20)),
                    (x + img2.get_width() + 6, y + 4),
                )
            else:
                s.blit(f.render("%d" % info["number"], True, (90, 40, 20)), (x + 8, y + 4))
        # 奖励行
        coin = res.load_img("pic/ui/common/coin.png")
        fr = pygame.font.SysFont("Arial", 18, bold=True)
        txt = "%d" % info["reward_coin"]
        cy = 388
        s.blit(fr.render(txt, True, (255, 214, 90)), (352, cy))
        if coin:
            im = pygame.transform.smoothscale(coin, (20, 20))
            s.blit(im, (352 + fr.size(txt)[0] + 6, cy))

    def _hit_map_point(self, pos):
        """任务点命中 —— 后加的点优先（叠层时选上层）。"""
        for p in reversed(self.map_points):
            x0, y0, x1, y1 = p.rect
            if x0 <= pos[0] <= x1 and y0 <= pos[1] <= y1:
                return p
        return None

    # ------------------------------------------------------------ 弹窗

    def _map_button(self, name):
        """地图按钮分发（MapLayer::onButton* 系列）。

        shop          → 军火库
        achivement    → AchievementLayer（成就）
        setting       → SettingsDialog（设置）
        daily         → DailyTaskDialog（每日任务）
        zombie_shop   → ZombieShopDialog（僵尸商店）
        slots         → SlotPanel（老虎机）
        reward_notify → 签到入口（原版活动通知按钮，本地用每日奖励弹窗）
        """
        self.audio.ui_click()
        if name == "shop":
            self.goto("shop")
        elif name == "achivement":
            self.achievement_panel = AchievementPanel(self)
        elif name == "setting":
            self.open_dialog("settings")
        elif name == "daily":
            self.open_dialog("daily")
        elif name == "zombie_shop":
            self.open_dialog("zombie_shop")
        elif name == "slots":
            # 老虎机的引导属于老虎机界面内（原版 SlotLayer::initUserGuide
            # @0x144ecc），地图层的引导要先收起来，否则会遮住界面。
            self.guide = None
            self.slot_panel = SlotPanel(self)
        elif name == "add_crystal":
            # 原版是充值入口（渠道 SDK，已下线）→ 点一下直接到账
            self.cheat_grant()
        elif name == "reward_notify":
            # 原版「签到」按钮：本地没有活动通知服务，作为唯一的签到入口
            self.open_dialog("daily_reward")

    def _maybe_daily_signin(self):
        """今天还没签到就自动弹出每日奖励面板（每次启动只弹一次）。"""
        if getattr(self, "_signin_shown", False):
            return
        if self.dialog is not None:
            return
        try:
            day = int(self.save.d.get("reward_day", 1) or 1)
            if int(self.save.d.get("reward_day_%d" % day, 0) or 0):
                self._signin_shown = True  # 今天已领，不再弹
                return
        except Exception:
            return
        self._signin_shown = True
        self.open_dialog("daily_reward")

    def _maybe_user_guide(self):
        """MapLayer::initUserGuide：按存档推进阶段决定弹哪一步。"""
        if getattr(self, "guide", None) is not None:
            return
        # 引导调度按「当前天」分支（第 2 天弹枪械升级、第 3 天弹药水），
        # 这里把真实进度临时喂给它，不再依赖存档里的 level 键。
        from game.map_points import current_level
        from game.user_guide import pick_step

        self.save.d["__guide_level"] = current_level(self.save, self.level_db)
        try:
            sid = pick_step(self.save.d)
        finally:
            self.save.d.pop("__guide_level", None)
        if sid:
            self.guide = UserGuide(self, sid)
