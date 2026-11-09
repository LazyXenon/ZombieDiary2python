"""军火库（shop / money 页）的渲染与点击处理。"""

import contextlib
import json as json

import pygame

from app.constants import (
    SHOP_EXCLUDE,
    H,
)
from engine import (
    res,
)
from engine import (
    scene as SC,
)
from game import (
    shop_tabs as ST,
)
from game import (
    shopui as SU,
)
from game.shop_table import BY_NAME as SU_BY_NAME


class ShopSceneMixin:
    """军火库（shop / money 页）的渲染与点击处理。"""

    def _fb(self, action):
        """触发按键反馈。feedback 缺失时降级到老音效，不崩。"""
        fb = getattr(self, "feedback", None)
        if fb is not None:
            fb.trigger(action)
        else:
            self.audio.sfx("unlock" if "unlock" in action or "buy" in action else "bn_pressed")

    # ---------------- 按钮点击反馈 ----------------
    #   原版是按下时整颗按钮下沉 2px + 一圈白光扫过。这里用「白光描边 0.18s
    #   渐隐」来补，位置就是被点中的那个按钮矩形，最省事也最稳。
    def _click_fx_hit(self, pos):
        rs = []

        def _walk(v):
            if isinstance(v, pygame.Rect):
                rs.append(v)
            elif isinstance(v, (list, tuple)):
                for it in v:
                    _walk(it)

        _walk(self.shop_rects or {})
        _walk(getattr(self, "shop_btn_rects", None) or {})
        _walk(getattr(self, "shop_slot_rects", None) or {})
        _walk(getattr(self, "shop_tab_rects", None) or {})
        _walk(getattr(self, "money_rects", None) or {})
        for r in rs:
            if r.collidepoint(pos):
                self._click_fx = (r.copy(), pygame.time.get_ticks(), None)
                return

    def _click_glow(self, s, r):
        """把按钮矩形里的**亮部**（按钮实体）做成白色剪影。

        矩形**描一圈白光——可按钮图四周有透明边距，描边落在贴图边界上，
        看着就是一颗灰按钮背后垫了个浅灰方框。改成按亮度抠出按钮实体，
        只有按钮本身会闪，矩形边界彻底消失。
        """
        r = r.clip(s.get_rect())
        if r.w <= 0 or r.h <= 0:
            return False
        sub = s.subsurface(r).copy().convert_alpha()
        w, h = sub.get_size()
        out = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            for x in range(w):
                c = sub.get_at((x, y))
                lum = (c.r * 3 + c.g * 6 + c.b) // 10
                k = lum - 96
                if k <= 0:
                    continue
                out.set_at((x, y), (255, 255, 255, min(190, k * 2)))
        return out

    def _click_fx_draw(self, s):
        fx = getattr(self, "_click_fx", None)
        if not fx:
            return
        r, t0, sil = fx
        k = (pygame.time.get_ticks() - t0) / 180.0
        if k >= 1.0:
            self._click_fx = None
            return
        if sil is None:
            try:
                sil = self._click_glow(s, r)
            except Exception:
                sil = False
            self._click_fx = (r, t0, sil)
        if not sil:
            return
        im = sil.copy()
        im.set_alpha(int(160 * (1.0 - k)))
        s.blit(im, r.topleft)

    def _shop_gun(self, allow_none=False):
        """当前选中的枪 —— 一般是 SHOP_GUNS 里的一条。

        allow_none=True 时，玩家主动「取消选中」（再点一次卡片）会返回
        None，由调用方画空态提示，而不是悄悄回落到第一把枪。

        ★ shop_sel 有可能被写成军火库列表里没有的名字：经验武器弹窗
          （dialog_exp_weapon.onButtonBuy）直接 `app.shop_sel = self.gun`，
          而奖励武器可能是 fly_1 / mech_3 这类特殊武器；旧存档的
          `SU_BY_NAME[self.shop_sel]` ⇒ KeyError，整个游戏当场闪退。
          这里统一兜底：取不到就落回第一把枪，并把 shop_sel 修正回来。
        """
        g = SU_BY_NAME.get(self.shop_sel)
        if g is None:
            if allow_none and self.shop_sel is None:
                return None
            g = SU.SHOP_GUNS[0]
            self.shop_sel = g["name"]
        return g

    def draw_shop(self, s):
        """军火库 —— 静态层走 dump 树，动态层走各页签模块。

        页签只有 人物 / 枪 / 技能 / 机甲 四个（原版的充值页已删）。
        """
        if self.shop_tab in ("soldier", "ability", "mech"):
            SC.draw_tree(
                s,
                self.trees["shop"],
                self.texs["shop"][0],
                self.texs["shop"][1],
                self.texs["shop"][2],
                bg_tex="pic_bg_1/shop_bg.jpg",
                exclude=SHOP_EXCLUDE,
                skip_tex=(
                    "ui/shop/button_",
                    "ui/shop/bt_light",
                    "ui/shop/item_panel",
                    "ui/shop/gun_",
                    "shop/select_box",
                    "shop/ability_shield",
                    "pic_bg_1/",
                ),
            )
            if self.shop_tab == "soldier":
                self.shop_tab_rects = ST.draw_top_bar(s, "soldier")
                self.shop_rects = ST.draw_soldier(
                    s, self.save, self.shop_font, preview=getattr(self, "shop_soldier", None)
                )
            elif self.shop_tab == "ability":
                self.shop_tab_rects = ST.draw_top_bar(s, "ability")
                self.shop_rects = ST.draw_ability(
                    s,
                    self.save,
                    self.shop_font,
                    getattr(self, 'shop_ability', 0),
                    getattr(self, 'shop_ability_scroll', 0.0),
                )
            else:
                self.shop_tab_rects = ST.draw_top_bar(s, "mech")
                self.shop_rects = ST.draw_mech(
                    s, self.save, self.shop_font, preview=getattr(self, "shop_mech", None)
                )
            self.money_rects = SU.draw_currency(
                s, self.save.d["coins"], self.save.d["crystals"], self.money_font
            )
            self.shop_btn_rects = {}
            self.shop_slot_rects = []
            return

        SC.draw_tree(
            s,
            self.trees["shop"],
            self.texs["shop"][0],
            self.texs["shop"][1],
            self.texs["shop"][2],
            bg_tex="pic_bg_1/shop_bg.jpg",
            exclude=SHOP_EXCLUDE,
            skip_tex=(
                "ui/shop/button_",
                "ui/shop/bt_light",
                "ui/shop/item_panel",
                "ui/shop/gun_",
                "shop/select_box",
                "shop/ability_shield",
                "pic_bg_1/",
            ),
        )
        self.shop_tab_rects = SU.draw_top_bar(s, self.shop_tab)
        self.money_rects = SU.draw_currency(
            s, self.save.d["coins"], self.save.d["crystals"], self.money_font
        )
        _gun = self._shop_gun(allow_none=True)
        self.shop_rects = SU.draw_cards(s, self.save, self.shop_row, self.shop_sel, self.shop_font)
        if _gun is None:
            # 玩家再点一次卡片取消了选中 → 详情面板给空态提示
            self.shop_btn_rects = {}
            self.shop_slot_rects = SU.draw_slots(s, self.save, selected=None)
            SU.draw_empty_detail(s, self.shop_font)
            self._click_fx_draw(s)
            return
        self.shop_btn_rects = SU.draw_detail(
            s, self.save, _gun, (self.shop_font_big, self.shop_font)
        )
        self.shop_slot_rects = SU.draw_slots(s, self.save, selected=_gun["name"])
        self._click_fx_draw(s)

    def draw_coins(self, s):
        """货币行 —— 照抄战斗节点树 data/node_tree_battle.json。

        0xd64ec0c4 货币行容器 pos=[104,379.2] ap=[0,0] sc=0.6
          0xd65fa104 coin.png    pos=[0,25]     ap=[0,0.5] sz=[50,50]
          0xd6b579c4 EzScoreText pos=[55,25]    ap=[0,0.5] sz=[81.562,25] sc=1.6
          0xd65fb284 crystal.png pos=[210.5,25] ap=[0,0.5] sz=[55,41]
          0xd6b57b84 EzScoreText pos=[270.5,25] ap=[0,0.5] sz=[18,25]    sc=1.6

        容器 scale 0.6 ⇒ 屏幕坐标 = 局部 × 0.6。
        """
        from engine import gridfont

        font = gridfont.get_font(0)
        y = 379.2 - 25 * 0.6
        ICON_GAP = 8.0
        x = 104.0
        row = res.load_img("pic/ui/common/coin.png")
        coin_w = 30
        if row:
            s.blit(
                pygame.transform.smoothscale(row, (coin_w, coin_w)), (int(x), int(y) - coin_w / 2)
            )
        x += coin_w + ICON_GAP
        if font:
            txt = "{:,}".format(int(self.save.d.get("coins", 0)))
            font.draw(s, txt, x, y, 1.6 * 0.6, align=(0.0, 0.5))
            x += font.text_size(txt, 1.6 * 0.6)[0] + ICON_GAP + 8
        else:
            x += 100
        cr = res.load_img("pic/ui/common/crystal.png")
        cr_w, cr_h = 33, 25
        if cr:
            s.blit(pygame.transform.smoothscale(cr, (cr_w, cr_h)), (int(x), int(y) - cr_h / 2))
        if font:
            font.draw(
                s,
                str(self.save.d.get("crystals", 0)),
                x + cr_w + ICON_GAP,
                y,
                1.6 * 0.6,
                align=(0.0, 0.5),
            )

    def shop_click(self, pos):
        """军火库点击 —— 全部落到 shopui 的命中矩形。

        GunShopLayer::ccTouchesEnded @0x130924 点 GunItem 只负责选中；
        购买/升级/装备各有独立按钮回调（sub_133BB8 里绑定）。
        """
        with contextlib.suppress(Exception):
            self._click_fx_hit(pos)

        money = getattr(self, "money_rects", None) or {}
        add = money.get("add_crystal")
        if add is not None and add.collidepoint(pos):
            self.cheat_grant()
            return

        tab = SU.hit_tab(self.shop_tab_rects, pos)
        if tab == "back":
            self.goto("map")
            return
        if tab:
            if tab in ("gun", "soldier", "ability", "mech"):
                self.shop_tab = tab
                self.audio.ui_click()
                if tab == "soldier":
                    # 进角色页就报一句台词，不用非得点一下头像才有声音
                    actors = ST.load_soldier_actors()
                    idx = getattr(self, "shop_soldier", None)
                    if idx is None:
                        cur = self.save.soldier_name()
                        idx = next((i for i, a in enumerate(actors) if a["name"] == cur), 0)
                    if 0 <= idx < len(actors):
                        self.audio.soldier_talk(actors[idx]["name"])
            return

        # --- 士兵 / 技能 / 机甲 页 ---
        if self.shop_tab == "soldier":
            slots = self.shop_rects.get("slots", [])
            for i, r in enumerate(slots):
                if r.collidepoint(pos):
                    # 只切**预览**，不直接改存档（没买的角色不能凭空装备）
                    self.shop_soldier = i
                    self.audio.ui_click()
                    # ★ 角色台词（GameSound 第三张表 talk_soldier_N）：
                    #   点不同角色说不同的话，这是「角色有专属音效」最直观的一处。
                    actors = ST.load_soldier_actors()
                    if i < len(actors):
                        self.audio.soldier_talk(actors[i]["name"])
                    return
            buy = self.shop_rects.get("buy")
            if buy and buy.collidepoint(pos):
                actors = ST.load_soldier_actors()
                idx = getattr(self, "shop_soldier", None)
                if idx is None or idx >= len(actors):
                    return
                info = actors[idx]
                if not self.save.buy_soldier(info["name"], info["cost_coin"], info["cost_crystal"]):
                    self.toast("金币 / 钻石不足")
                    self._fb("ui.error")
                    return
                self.audio.sfx("unlock")
                self._fb("shop.buy")
                _c = int(info.get("cost_coin") or 0)
                _d = int(info.get("cost_crystal") or 0)
                _parts = []
                if _c:
                    _parts.append("%s 金币" % f"{_c:,}")
                if _d:
                    _parts.append("%d 钻石" % _d)
                _nm = info.get("title", info["name"]).title()
                self.toast(
                    "已购买 %s" % _nm
                    if not _parts
                    else "已购买 %s（花费 %s）" % (_nm, " + ".join(_parts))
                )
                return
            eq = self.shop_rects.get("equip")
            if eq and eq.collidepoint(pos):
                actors = ST.load_soldier_actors()
                idx = getattr(self, "shop_soldier", None)
                if idx is not None and idx < len(actors):
                    nm = actors[idx]["name"]
                    title = next((a["title"] for a in actors if a["name"] == nm), nm)
                    if not self.save.own_soldier(nm):
                        self.toast("还没买这个角色")
                        return
                    # 原版 onClickEquipButton @0x140200 只把选中角色写入
                    # equipped_soldier，并禁用装备按钮；equipSoldier
                    # @0x13f1c0 的 unEquip 是取消其他头像的选中态。
                    # 角色没有「卸下」操作，也没有 last_soldier 存档键。
                    if self.save.soldier_name() == nm:
                        self.toast("已经是当前角色")
                        return
                    self.save.d["soldier"] = int(nm.split("_")[1])
                    self.save.save()
                    self.audio.sfx("tab")
                    # ★ 装备成功必须有反馈（用户反馈「用了什么角色没有反馈」）
                    self.toast("已装备 %s" % title)
                return
            up = self.shop_rects.get("upgrade")
            if up and up.collidepoint(pos):
                # 已拥有的士兵 → 升级弹窗（SoldierShopLayer::onUpgradeSoldier
                # @0x13f134：建 DialogSoldierUpgrade 并 setSoldierInfo）
                actors2 = ST.load_soldier_actors()
                idx2 = getattr(self, "shop_soldier", None)
                if idx2 is None or idx2 >= len(actors2):
                    return
                # ★ 升级的是「预览中」这个角色，不是当前装备的那个
                self.dialog_soldier = actors2[idx2]["name"]
                self.audio.ui_click()
                self.open_dialog("soldier_up")
            return

        if self.shop_tab == "ability":
            for r, idx in self.shop_rects.get("cards", []):
                if r.collidepoint(pos):
                    self.shop_ability = idx
                    self.audio.ui_click()
                    return
            buy = self.shop_rects.get("buy")
            if buy and buy.collidepoint(pos):
                self._buy_ability()
                return
            equip = self.shop_rects.get("equip")
            if equip and equip.collidepoint(pos):
                self._equip_ability()
                return
            uneq = self.shop_rects.get("unequip")
            if uneq and uneq.collidepoint(pos):
                self._unequip_selected_ability()
                return
            slots = self.shop_rects.get("slots") or []
            for i, r in enumerate(slots):
                if r.collidepoint(pos):
                    self._slot_ability(i)
                    return
            return

        if self.shop_tab == "mech":
            slots = self.shop_rects.get("slots", [])
            for i, r in enumerate(slots):
                if r.collidepoint(pos):
                    mechs = ST.load_mech_actors()
                    if i < len(mechs):
                        self.shop_mech = mechs[i]["name"]
                        self.audio.ui_click()
                    return
            mechs = ST.load_mech_actors()
            # ★ 首次进机甲页时 shop_mech 还没建立、equipped_mech 也可能是空，
            #   但 draw_mech 已经用 mechs[0] 画出第一台并摆出「购买」按钮。
            #   却毫无反应（用户「这个机甲买不了」）。回退链必须和绘制端
            #   draw_mech 的 preview 回退链一致。
            cur = (
                getattr(self, "shop_mech", None)
                or self.save.d.get("equipped_mech")
                or (mechs[0]["name"] if mechs else None)
            )
            m = next((x for x in mechs if x["name"] == cur), None)
            if m is None:
                return
            # 两个按钮各走各的回调（原版 onBuyMech / onEquipMech）
            buy = self.shop_rects.get("buy")
            if buy and buy.collidepoint(pos):
                self._buy_mech(m)
                return
            eq = self.shop_rects.get("equip")
            if eq and eq.collidepoint(pos):
                self._toggle_mech_equip(m)
                return
            return

        gun = self._shop_gun()
        owned = self.save.own_weapon(gun["name"])
        for key, r in self.shop_btn_rects.items():
            if not r.collidepoint(pos):
                continue
            if key == "upgrade":
                self.audio.ui_click()
                self.open_dialog("gun_up")
            elif key == "equip":
                if owned:
                    self._equip_weapon_any_slot(gun["name"])
                    self.audio.sfx("tab")
            elif key == "buy_coin":
                if self.save.weapon_locked(gun):
                    self.toast("还没通关第 %d 关" % int(gun.get("unlock_level") or 0))
                    self._fb("ui.error")
                elif self.save.buy_weapon(gun["name"], gun["coin"]):
                    self._fb("shop.buy")
                    self.toast(
                        "已购买，花费 %s 金币（余额 %s）"
                        % (
                            "{:,}".format(int(gun["coin"] or 0)),
                            "{:,}".format(int(self.save.d.get("coins", 0))),
                        )
                    )
                else:
                    self.toast("金币不足")
                    self._fb("ui.error")
            elif key == "buy_crystal":
                if self.save.weapon_locked(gun):
                    self.toast("还没通关第 %d 关" % int(gun.get("unlock_level") or 0))
                    self._fb("ui.error")
                elif self.save.buy_weapon_crystal(gun["name"], gun["crystal"]):
                    self._fb("shop.buy")
                    self.toast(
                        "已购买，花费 %d 钻石（余额 %d）"
                        % (int(gun["crystal"] or 0), int(self.save.d.get("crystals", 0)))
                    )
                else:
                    self.toast("钻石不足")
                    self._fb("ui.error")
            elif key == "buy_bullet":
                # 军火库买弹：花 bullet_cost_coin 金币买 bullet_count 发
                cnt = int(gun.get("bullet_count", 0) or 0)
                cost = int(gun.get("bullet_cost", 0) or 0)
                if cnt > 0 and cost > 0:
                    if self.save.spend_coins(cost):
                        key_b = "%s_bullet" % gun["name"]
                        cur = int(self.save.d.get(key_b, 0) or 0)
                        self.save.d[key_b] = cur + cnt
                        self.save.save()
                        self._fb("shop.buy")
                        self.toast("已购买 %d 发子弹，花费 %s 金币" % (cnt, f"{cost:,}"))
                    else:
                        self.toast("金币不足")
                        self._fb("ui.error")
            elif key == "unlock":
                # 花钻石解开「通关等级」门槛（原版 GunShopLayer::onUnlockGun
                # @0x134bcc：扣 unlock_crystal，把枪名写进 unlock_guns）。
                #   绕过了「还要再花金币买」这一步，价格也用的是 unlock_crystal
                if self.save.unlock_weapon(gun["name"], gun.get("unlock_crystal", 0)):
                    self._fb("ui.unlock")
                    self.toast(
                        "已花 %d 钻石解锁，可以购买了" % int(gun.get("unlock_crystal", 0) or 0)
                    )
                else:
                    self.toast("钻石不足")
                    self._fb("ui.error")
            return

        slot = SU.hit_slot(self.shop_slot_rects, pos)
        if slot is not None:
            self._equip_weapon_slot(slot)
            return

        for name, r in self.shop_rects.items():
            if not hasattr(r, "collidepoint"):
                continue
            if name not in SU_BY_NAME:
                continue
            if r.collidepoint(pos):
                self.shop_sel = None if self.shop_sel == name else name
                self.audio.ui_click()
                return

        # 列表空白：上下翻一行
        if pos[0] < SU.scroll_right():
            self.shop_row = max(
                0, min(len(SU.SHOP_GUNS) - 1, self.shop_row + (1 if pos[1] > H / 2 else -1))
            )

    def _buy_mech(self, m):
        """机甲购买 —— 原版 MechShopLayer::onBuyMech @0x13d738。

        机甲是**消耗品**（mech_actors.xml 的 desc 末行 *consumable item，
        战斗里召唤一次 use_mech() 数量 -1），所以这个按钮每点一次都只做
        「数量 +1」，永远可点，不随拥有数量变成别的功能。

        扣款顺序（逐句照抄反编译）：
          user_coin < def[27] 或 user_crystal < def[28] → 打开充值页
            （本复刻没有内购通道，改成提示「金币/钻石不足」）
          def[27] <= 0 且 def[28] > 0 → 扣钻石
          def[27] > 0                → 扣金币
          数量 +1，若当前装备的不是这台 → 自动装备这台
        """
        name = m["name"]
        coin = int(m.get("cost_coin") or 0)
        crystal = int(m.get("cost_crystal") or 0)
        if int(self.save.d.get("coins", 0)) < coin or int(self.save.d.get("crystals", 0)) < crystal:
            # 原版这里 push MoneyShopLayer；离线版没有充值，直接提示
            self.toast("金币 / 钻石不足")
            self._fb("ui.error")
            return
        if coin > 0:
            if not self.save.spend_coins(coin):
                self.toast("金币不足")
                self._fb("ui.error")
                return
        elif crystal > 0:
            if not self.save.spend_crystals(crystal):
                self.toast("钻石不足")
                self._fb("ui.error")
                return
        self.save.add_mech(name, 1)
        if self.save.d.get("equipped_mech") != name:
            self.save.d["equipped_mech"] = name
            self.save.save()
        self.audio.sfx("unlock")
        self._fb("shop.buy")
        self.toast("购买 1 台，库存 ×%d" % self.save.mech_count(name))

    def _toggle_mech_equip(self, m):
        """机甲「使用 / 卸下」—— 原版 MechShopLayer::onEquipMech @0x13d630。

        「使用」只写 equipped_mech，**不扣数量**；已经在用就置空（卸下）。
        """
        name = m["name"]
        if self.save.mech_count(name) <= 0:
            self.toast("还没有这台机甲")
            self._fb("ui.error")
            return
        if self.save.d.get("equipped_mech") == name:
            self.save.d["equipped_mech"] = None
            self.save.save()
            self.audio.sfx("tab")
            self.toast("已卸下机甲")
            return
        self.save.d["equipped_mech"] = name
        self.save.save()
        self.audio.sfx("tab")
        self.toast("已使用该机甲")

    def _equip_weapon_any_slot(self, name):
        """把这把枪装进第一个空武器槽；全满则用第 1 个槽。"""
        from game.save import WEAPON_SLOTS

        if not self.save.own_weapon(name):
            self.toast("尚未购买这把武器")
            return
        eq = self.save.d.setdefault("equipped", [])
        while len(eq) < WEAPON_SLOTS:
            eq.append(None)
        for i in range(WEAPON_SLOTS):
            if eq[i] == name:
                return  # 已经在槽上，不动
        for i in range(WEAPON_SLOTS):
            if not eq[i]:
                self.save.equip(name, slot=i)
                return
        self.save.equip(name, slot=0)

    def _equip_weapon_slot(self, slot):
        """把当前选中的枪装进第 slot 个武器槽（槽位交换）。

        原版军火库页面的 4 个格子是可拖换的：点一把枪，再点一个格子就换过去。
        这里做同样的事：
          · 空槽     → 直接装进去
          · 已有别的枪 → 两把枪对调
          · 已经是这把 → 卸下来（槽变空）
        """
        from game.save import WEAPON_SLOTS

        name = self._shop_gun()["name"]
        # ★ 没买的枪不许装槽（同上，堵住「不买就能用」的另一条路）
        if not self.save.own_weapon(name):
            self.toast("尚未购买这把武器")
            return
        eq = self.save.d.setdefault("equipped", [])
        while len(eq) < WEAPON_SLOTS:
            eq.append(None)
        cur = eq[slot]
        if cur == name:
            # 再点一次 = 卸下
            eq[slot] = None
            self.save.save()
            self.audio.sfx("tab")
            return
        src = None
        for i in range(WEAPON_SLOTS):
            if eq[i] == name:
                src = i
                break
        eq[slot] = name
        if src is not None and src != slot:
            eq[src] = cur
        # equip() 会把同名枪在别的槽也清掉，交换时不能走它 ——
        # 直接同步 equipped_gun_N（战斗界面读这组键）。
        self.save._sync_equipped_gun_keys()
        self.save.save()
        self.audio.sfx("tab")

    def _own_soldier(self, name):
        """把某士兵记进 owned_soldiers 并直接装备。"""
        own = self.save.d.setdefault("owned_soldiers", [])
        if name not in own:
            own.append(name)
        self.save.d["soldier"] = int(name.split("_")[1])
        self.save.save()
        self.audio.sfx("unlock")

    def _equip_ability(self):
        """把当前选中的道具装到槽里。

        原版：装到「它现在占着的那个槽」，没有就装到第一个空槽。
        """
        idx = getattr(self, "shop_ability", 0)
        if idx >= len(ST.ABILITIES):
            return
        name = ST.ABILITIES[idx][0]
        if name not in (self.save.d.get("owned_abilities") or []):
            self.toast("还没买这个道具")
            return
        # 已经装在某个槽上 → 什么都不做（重复点不叠加）
        for i in range(ST.ABILITY_SLOT_COUNT):
            if self.save.d.get("equipped_ability_%d" % i) == name:
                return
        for i in range(ST.ABILITY_SLOT_COUNT):
            k = "equipped_ability_%d" % i
            if not self.save.d.get(k):
                self.save.d[k] = name
                self.save.save()
                self.audio.sfx("tab")
                return
        # 没有空槽 → 顶掉第 1 个
        self.save.d["equipped_ability_0"] = name
        self.save.save()
        self.audio.sfx("tab")

    def _unequip_ability(self, slot):
        """点装备格 = 卸下该格。"""
        key = "equipped_ability_%d" % slot
        if self.save.d.pop(key, None) is not None:
            self.save.save()
            self.audio.sfx("tab")

    def _unequip_selected_ability(self):
        """点「卸下」= 把当前选中的道具从它占着的槽里摘掉。"""
        idx = getattr(self, "shop_ability", 0)
        if idx >= len(ST.ABILITIES):
            return
        name = ST.ABILITIES[idx][0]
        for i in range(ST.ABILITY_SLOT_COUNT):
            if self.save.d.get("equipped_ability_%d" % i) == name:
                self._unequip_ability(i)
                return
        self.toast("这个道具没有装备在槽里")

    def _slot_ability(self, slot):
        """点装备格 —— 装入 / 交换 / 卸下。

        原版 AbilityShopLayer 的三个装备槽是可以互相拖换的，
        玩家点一个道具再点一个槽位就能把它放进去。这里按同一套语义做：

          · 槽位是空的      → 把当前选中的道具装进去
          · 槽位里有别的道具 → 与当前选中的道具**交换**
          · 槽位里就是当前道具 → 卸下（再点一次就空出来）

        没买过的道具不给装，直接提示。
        """
        idx = getattr(self, "shop_ability", 0)
        if idx >= len(ST.ABILITIES):
            return
        name = ST.ABILITIES[idx][0]
        key = "equipped_ability_%d" % slot
        cur = self.save.d.get(key)
        if cur == name:
            self._unequip_ability(slot)
            return
        if name not in (self.save.d.get("owned_abilities") or []):
            self.toast("还没买这个道具")
            return
        # 交换：当前道具原本占着别的槽 → 先摘掉
        for i in range(ST.ABILITY_SLOT_COUNT):
            k = "equipped_ability_%d" % i
            if i != slot and self.save.d.get(k) == name:
                self.save.d.pop(k, None)
        self.save.d[key] = name
        self.save.save()
        self.audio.sfx("tab")

    def _buy_ability(self):
        """购买技能（技能页「购买」按钮）。

        原版 AbilityShopLayer::onBuyAbility：先比对 AbilityItemDef 的
        cost_coin / cost_crystal，扣款后把拥有的数量 +1 并自动装备。
        """
        idx = getattr(self, "shop_ability", 0)
        if idx >= len(ST.ABILITIES):
            return
        name, _title, _icon, _num, cost_coin, cost_crystal = ST.ABILITIES[idx]
        if cost_coin > 0:
            ok = self.save.spend_coins(cost_coin)
        else:
            ok = self.save.spend_crystals(cost_crystal)
        if ok:
            ab = self.save.d["abilities"]
            ab[name] = ab.get(name, 0) + 1
            own = self.save.d.setdefault("owned_abilities", [])
            if name not in own:
                own.append(name)
            self.save.save()
            self.audio.sfx("unlock")
