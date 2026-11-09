"""键鼠输入分发。"""

import pygame

from app.constants import (
    UI,
)
from game.dialog_game_intro import GameIntroduceDialog
from game.dialog_level_select import LevelSelectDialog


class InputMixin:
    """键鼠输入分发。"""

    @staticmethod
    def in_rect(p, r):
        return r[0] <= p[0] <= r[2] and r[1] <= p[1] <= r[3]

    def right_click(self, pos):
        """「+」打开金手指手动输入面板（左键 / 右键都一样）。"""
        if self.dialog is not None:
            return
        if self.scene == "map":
            r = self.map_buttons.get("add_crystal") if self.map_buttons else None
            if r is not None and r.collidepoint(pos):
                self.open_dialog("cheat")
        elif self.scene == "shop":
            r = (getattr(self, "money_rects", None) or {}).get("add_crystal")
            if r is not None and r.collidepoint(pos):
                self.open_dialog("cheat")

    def click(self, pos):
        sc = self.scene
        # 覆盖式面板优先（成就 / 老虎机）
        if getattr(self, "achievement_panel", None) is not None:
            if self.achievement_panel.click(pos):
                if self.achievement_panel.done:
                    self.achievement_panel = None
            return
        if getattr(self, "slot_panel", None) is not None:
            if self.slot_panel.click(pos):
                if self.slot_panel.done:
                    self.slot_panel = None
            return
        # 新手引导优先吃点击（模态）。指任务点的步骤点击要穿透：
        # guide.click 返回 False 表示放行，但引导本身可能已 finish。
        if getattr(self, "guide", None) is not None:
            swallowed = self.guide.click(pos)
            if self.guide.done:
                self.guide = None
            if swallowed:
                return
            # 穿透后继续走地图逻辑（点任务点）
        # 弹窗优先（模态）
        if self.dialog is not None:
            if self.dialog.click(pos):
                self._after_dialog()
            return
        if sc == "menu":
            act = self.main_menu.click(pos) if self.main_menu else None
            if act == "play":
                self.audio.ui_click()
                self.goto("map")
            elif act == "music":
                self.audio.ui_click()
                self.main_menu.on_button_music()
            elif act == "sound":
                self.audio.ui_click()
                self.main_menu.on_button_sound()
            elif act == "intro":
                self.audio.ui_click()
                self.dialog = GameIntroduceDialog(self)
            elif act == "moregames":
                self.audio.ui_click()
                # AppUtils::showFTMoreGames —— 渠道 SDK 外链，本地无对应实现
        elif sc == "map":
            hit = self._hit_map_point(pos)
            btn = self.map_buttons.hit(pos) if self.map_buttons else None
            if btn is not None:
                self._map_button(btn)
            elif hit is not None:
                if hit.locked:
                    self.audio.ui_click()
                else:
                    self.audio.ui_click()
                    self.mission_id = hit.mission_id
                    self.goto("level")
                    # DialogLevelSelect::setLevelInfo → 每次都重建
                    self.level_dialog = LevelSelectDialog(self, self.mission_id)
            elif self.in_rect(pos, UI["map_shop"]):
                self.audio.ui_click()
                self.goto("shop")
            elif self.in_rect(pos, UI["map_back"]):
                self.audio.ui_click()
                self.goto("menu")
        elif sc == "level":
            dlg = self.level_dialog
            if dlg is None:
                dlg = self.level_dialog = LevelSelectDialog(self, self.mission_id)
            if dlg.click(pos):
                self.audio.ui_click()
                if getattr(dlg, "go_shop", False):
                    # _open_recommend 已经 goto("shop")，这里别再回地图把它覆盖掉
                    self.level_dialog = None
                elif dlg.accepted:
                    self.start_mission(self.mission_id)
                elif dlg.done:
                    self.goto("map")
                    self.level_dialog = None
        elif sc == "shop":
            self.shop_click(pos)
        elif sc == "battle":
            if getattr(self, "failed_weapon", None) is not None:
                self.failed_weapon.click(pos)
                return
            if self.result_panel:
                # 坐标必须传：失败面板的「重试 / 菜单」按钮靠命中判定
                self.result_panel.click(pos)
                if self.result_panel.done:
                    self.after_result()
                return
            if self.revive_panel:
                self.revive_panel.click(pos)
                return
            if self.in_rect(pos, UI["battle_pause"]):
                self.audio.ui_click()
                self.open_dialog("pause")
            elif self.weapon_slots and self.weapon_slots.hit(pos):
                # WeaponItemButton::select：子弹打空 → onBuyBullet（买弹），
                # 否则 → Soldier::onChangeWeapon（换枪）
                act = self.weapon_slots.click(pos)
                if act and act[0] == "switch":
                    if self.battle.change_weapon(act[1]):
                        self.audio.ui_click()
                        self.weapon_slots = None  # 槽位状态变了，重建
                elif act and act[0] == "buy":
                    if self.battle.buy_bullet(act[1]):
                        self.audio.ui_click()
                        self.weapon_slots = None
                    else:
                        self.toast("金币不足")
            elif self.mech_slot is not None and self.mech_slot.hit(pos):
                ok, msg = self.mech_slot.trigger()
                if ok:
                    self.audio.ui_click()
                    self.weapon_slots = None
                elif msg:
                    self.toast(msg)
            elif self.ability_bar and self.ability_bar.hit(pos):
                # UIBoard::onTouchesBeganOnAbilityButton
                name = self.ability_bar.hit(pos)
                if name and self.ability_bar.trigger(name):
                    self.audio.ui_click()
            elif self.in_rect(pos, UI["battle_left"]):
                self.battle.move_dir = -1
                self._touch_flag("move")
            elif self.in_rect(pos, UI["battle_right"]):
                self.battle.move_dir = 1
                self._touch_flag("move")
            elif self.in_rect(pos, UI["battle_fire"]):
                self.battle.hold_fire = True
                self._touch_flag("fire")

    def _touch_flag(self, name):
        """记下本次指针按住过的战斗虚拟键（move / fire）。

        用集合而不是单个字符串：一个指针可以在不抬手的情况下从方向键滑到
        开火键，两边都得记，抬手才清得干净。
        """
        touch = getattr(self, "_battle_touch", None)
        if not isinstance(touch, set):
            touch = set()
            self._battle_touch = touch
        touch.add(name)

    def release(self):
        # ★ 签到面板自己处理松手（判断翻到第几页）
        if self.dialog is not None:
            r = getattr(self.dialog, "release", None)
            if r is not None:
                r()
        self.shop_drag = None
        if getattr(self, "feedback", None) is not None:
            self.feedback.release()
        if self.scene == "battle" and self.battle:
            touch = getattr(self, "_battle_touch", None)
            if isinstance(touch, set):
                if "move" in touch:
                    self.battle.move_dir = 0
                if "fire" in touch:
                    self.battle.hold_fire = False
                # 右键开火（"fire_r"）由 right_release 单独收，这里不动它
                touch.difference_update(("move", "fire"))
                if not touch:
                    self._battle_touch = None
            else:
                self._battle_touch = None

    # ------------------------------------------------------ 右键（开火）
    def right_press(self, pos):
        """鼠标右键：战斗里 = 按住开火，其余场景 = 原来的「+」快捷入口。

        ★ 加这条是为了「边移动边攻击」。屏幕上的方向键和开火键共用一个
          指针，鼠标按住左键时不可能再按第二个虚拟键 —— 桌面玩家只能
          A/D + 空格。右键按住开火后，左手（键盘或左键点方向键）+ 右手
          右键就能边跑边打，和原版双拇指同时按是一个意思。
        """
        if (
            self.scene == "battle"
            and self.battle
            and self.dialog is None
            and not (self.result_panel or self.revive_panel)
        ):
            if not self.battle.over:
                self.battle.hold_fire = True
                self._touch_flag("fire_r")
                return
        self.right_click(pos)

    def right_release(self):
        if self.scene == "battle" and self.battle:
            touch = getattr(self, "_battle_touch", None)
            if isinstance(touch, set) and "fire_r" in touch:
                self.battle.hold_fire = False
                touch.discard("fire_r")
                if not touch:
                    self._battle_touch = None

    # ------------------------------------------------------------ 滚动

    def press(self, pos):
        """按下：记按住态（视觉反馈）+ 在可滚动区域记拖拽起点。"""
        # ★ 玩家一动鼠标就撤掉键盘焦点框：否则「用键盘选中 A、又用鼠标点了
        #   B」之后焦点框还挂在 A 上，回车会点到看不见的东西。
        nav = getattr(self, "keynav", None)
        if nav is not None:
            nav.clear()
        fb = getattr(self, "feedback", None)
        if fb is not None:
            fb.trigger("ui.press", pos)
        if self.dialog is not None:
            p = getattr(self.dialog, "press", None)
            if p is not None:
                return p(pos)
            return
        if self.scene != "shop":
            return
        if self.shop_tab == "gun":
            from game import shopui as _SU

            if _SU.scroll_rect().collidepoint(pos):
                self.shop_drag = dict(y0=pos[1], row0=self.shop_row)
        elif self.shop_tab == "ability":
            r = self.shop_rects.get("list_view") if self.shop_rects else None
            if r and r.collidepoint(pos):
                self.shop_drag = dict(y0=pos[1], scr0=self.shop_ability_scroll)

    def drag_to(self, pos):
        """拖动：按位移量滚动列表。"""
        if self.dialog is not None:
            d = getattr(self.dialog, "drag_to", None)
            if d is not None:
                return d(pos)
            return
        d = self.shop_drag
        if d is None or self.scene != "shop":
            return
        dy = pos[1] - d["y0"]
        if self.shop_tab == "gun":
            from game import shopui as _SU

            pitch = getattr(_SU, "CARD_PITCH", 108)
            row = d["row0"] - int(round(dy / float(pitch)))
            self.shop_row = max(0, min(len(_SU.SHOP_GUNS) - 1, row))
        elif self.shop_tab == "ability":
            self.shop_ability_scroll = max(0.0, d["scr0"] - dy)

    def wheel(self, steps):
        """滚轮：一档一行 / 一档 60 像素。"""
        if self.dialog is not None:
            w = getattr(self.dialog, "wheel", None)
            if w is not None:
                w(steps)
            return
        if self.scene != "shop":
            return
        if self.shop_tab == "gun":
            from game import shopui as _SU

            self.shop_row = max(0, min(len(_SU.SHOP_GUNS) - 1, self.shop_row - steps))
        elif self.shop_tab == "ability":
            self.shop_ability_scroll = max(0.0, self.shop_ability_scroll - steps * 60.0)

    # ------------------------------------------------------------ 键盘

    def keybinds(self):
        """当前键位（存档字符串 → pygame 键码）。

        名字用 pygame.key.name() 存（'a' / 'd' / 'space'），读的时候
        pygame.key.key_code() 反查。旧档没有 keybinds 时回落到默认值。
        """
        d = self.save.d if getattr(self, "save", None) else {}
        kb = d.get("keybinds") or {}
        from game.save import DEFAULT_KEYBINDS

        out = {}
        for k, default in DEFAULT_KEYBINDS.items():
            name = kb.get(k) or default
            try:
                out[k] = pygame.key.key_code(name)
            except (ValueError, TypeError):
                out[k] = pygame.key.key_code(default)
        return out

    def keyboard_mode(self):
        d = getattr(self.save, "d", {}) or {}
        return bool((d.get("settings") or {}).get("keyboard", True))

    def hide_buttons(self):
        """默认**隐藏**触屏虚拟键（用户要求：默认隐藏原来的触屏键位）。

        老档没这个字段时返回 True；想用触屏的玩家可以在设置里打开。
        """
        d = getattr(self.save, "d", {}) or {}
        return bool((d.get("settings") or {}).get("hide_buttons", True))

    def escape(self):
        """ESC 的总入口。返回 True = 已处理（不要退游戏）。

        层级从内到外逐层退：弹窗 → 覆盖面板 → 引导 → 场景 →
        设置面板写着「Esc 返回设置」却一点就直接关掉整个程序。
        """
        # 1) 弹窗：交给它自己的 on_key 处理（设置 / 键位页都有专门逻辑）
        if self.dialog is not None:
            if getattr(self.dialog, "any_key_close", False):
                key_fn = getattr(self.dialog, "key", None)
                if key_fn is not None:
                    key_fn(pygame.K_ESCAPE)
                else:
                    self.dialog.done = True
                if getattr(self.dialog, "done", False):
                    self._after_dialog()
                return True
            # ★ 僵尸商店 / 关卡选择没有 key()；旧代码无条件调用会闪退。
            key_fn = getattr(self.dialog, "key", None)
            if key_fn is not None:
                key_fn(pygame.K_ESCAPE)
            elif getattr(self.dialog, "close", None) is not None:
                self.dialog.close()
            if getattr(self.dialog, "done", False):
                self._after_dialog()
            return True
        # 2) 覆盖式面板
        if getattr(self, "achievement_panel", None) is not None:
            self.achievement_panel = None
            return True
        if getattr(self, "slot_panel", None) is not None:
            self.slot_panel = None
            return True
        # 3) 新手引导
        if getattr(self, "guide", None) is not None:
            self.guide.finish()
            self.guide = None
            return True
        # 4) 结算 / 续天 / 失败武器面板：不吃 ESC，别让玩家误关
        if (
            self.result_panel
            or self.revive_panel
            or getattr(self, "failed_weapon", None) is not None
        ):
            return True
        # 5) 按场景往回退一层
        if self.scene == "battle":
            self.open_dialog("pause")
            return True
        if self.scene in ("level", "shop"):
            self.level_dialog = None
            self.goto("map")
            return True
        if self.scene == "map":
            self.goto("menu")
            return True
        # 6) 主菜单：真的退出
        return False

    def keynav_key(self, key):
        """全键盘导航：方向键选控件，回车 / 空格确认，Tab 轮换。

        只处理这四个方向 + 确认键，其它键原样返回 False，各界面自己的
        键位（战斗移动 / 设置改键）完全不受影响。战斗场景的候选清单是
        空的（见 key_items），所以左右移动、空格开火照旧走原逻辑。
        """
        dlg = getattr(self, "dialog", None)
        # 签到等多页弹窗把左右键留给翻页，不再抢去移动按钮焦点。
        if (
            dlg is not None
            and getattr(dlg, "ARROWS_PAGE", False)
            and key in (pygame.K_LEFT, pygame.K_RIGHT)
        ):
            key_fn = getattr(dlg, "key", None)
            if key_fn is not None:
                key_fn(key)
            return True
        if not self.keyboard_mode():
            return False
        # 正在「按下要绑定键」的捕获态：任何键都得留给改键框
        if getattr(dlg, "_capturing", None) is not None:
            return False
        nav = getattr(self, "keynav", None)
        if nav is None:
            return False
        items = self.key_items()
        nav.set_items(items, self.key_signature())
        if not items:
            return False
        dirs = {
            pygame.K_LEFT: (-1, 0),
            pygame.K_RIGHT: (1, 0),
            pygame.K_UP: (0, -1),
            pygame.K_DOWN: (0, 1),
        }
        if key in dirs:
            moved = nav.step_next(1) if nav.idx < 0 else nav.move(*dirs[key])
            if moved:
                self.audio.ui_click()
            return True
        if key == pygame.K_TAB:
            back = pygame.key.get_mods() & pygame.KMOD_SHIFT
            if nav.step_next(-1 if back else 1):
                self.audio.ui_click()
            return True
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            r = nav.current_rect()
            if r is None and len(items) == 1:
                # 全屏只有一个候选（引导的「确定」、结算的「继续」）时，
                # 玩家第一反应就是直接按回车 —— 别逼他先按一次方向键
                # 才肯认账，否则会像「按了没反应」。
                nav.step_next(1)
                r = nav.current_rect()
            if r is None:
                return False
            # 复用鼠标点击：音效、冷却、二次确认、失败提示全都一致
            self.click(r.center)
            return True
        return False

    def key_down(self, key):
        """键盘按下/松开的总入口。返回 True 表示已被消费。"""
        # 首次键盘指南：任意键（含 F11 / 方向键 / Enter）直接关闭，避免穿透。
        dlg = self.dialog
        if dlg is not None and getattr(dlg, "any_key_close", False):
            key_fn = getattr(dlg, "key", None)
            if key_fn is not None:
                key_fn(key)
            else:
                dlg.done = True
            if getattr(dlg, "done", False):
                self._after_dialog()
            return True
        # F11 是全局显示开关：优先于改键捕获，避免被绑成游戏动作。
        if key == pygame.K_F11:
            st = self.save.d.get("settings") or {}
            self.set_fullscreen(not bool(st.get("fullscreen", False)))
            return True
        # ★ 全键盘方案：方向键 / 回车先在界面控件之间导航
        if self.keynav_key(key):
            return True
        # 弹窗优先（模态）：设置面板要用键盘改键
        if self.dialog is not None:
            key_fn = getattr(self.dialog, "key", None)
            if key_fn is not None:
                key_fn(key)
            return True
        # 战斗里才响应移动/开火
        if self.scene != "battle" or self.battle is None:
            return False
        if self.battle.over or self.result_panel or self.revive_panel:
            return False
        # keyboard 只控制键位提示的显示；物理键盘在战斗中始终可用。
        kb = self.keybinds()
        if key in (pygame.K_UP, pygame.K_DOWN):
            return self._cycle_weapon(-1 if key == pygame.K_UP else 1)
        cycle_keys = [kb["cycle"]]
        if kb["cycle"] == pygame.K_LSHIFT:
            cycle_keys.append(pygame.K_RSHIFT)
        if key in cycle_keys:
            return self._cycle_weapon(1)
        for i in range(4):
            if key == kb["weapon_%d" % (i + 1)]:
                return self._select_weapon(i)
        for i in range(3):
            if key == kb["ability_%d" % (i + 1)]:
                return self._fire_ability(i)
        if key == kb["mech"]:
            return self._fire_mech()
        if key == kb["armor"]:
            return self._fire_armor()
        if key in (kb["left"], pygame.K_LEFT):
            self.battle.key_left = True
            return True
        if key in (kb["right"], pygame.K_RIGHT):
            self.battle.key_right = True
            return True
        if key == kb["fire"]:
            # 键盘开火走独立通道（见 release() 的说明）
            self.battle.key_fire = True
            return True
        return False

    def _cycle_weapon(self, step):
        """W / S 换枪：step = -1 向左（前一把），+1 向右（后一把）。

        和点右上角武器槽等价 —— 都走 Battle.change_weapon，
        右上角的选中框跟着当前枪走。
        """
        b = self.battle
        slots = getattr(self, "weapon_slots", None)
        names = [n for _r, n in slots.rects] if slots else []
        if not names:
            return False
        if b.weapon in names:
            i = names.index(b.weapon)
        else:
            i = 0
        i = (i + step) % len(names)
        tgt = names[i]
        if tgt == b.weapon:
            return True
        if b.change_weapon(tgt):
            self.audio.ui_click()
            self.weapon_slots.refresh()  # 立即刷新，连按数字键不丢输入
        return True

    def _fire_ability(self, idx):
        """Q / E / R 触发第 idx 个道具。"""
        bar = getattr(self, "ability_bar", None)
        if bar is None or idx >= len(bar.rects):
            return False
        name = bar.rects[idx][1]
        if bar.trigger(name):
            self.audio.ui_click()
        return True

    def _select_weapon(self, idx):
        """1 / 2 / 3 / 4 = 直接切到第 idx 把武器（不是循环）。"""
        b = self.battle
        slots = getattr(self, "weapon_slots", None)
        names = [n for _r, n in slots.rects] if slots else []
        if not names:
            return False
        if idx >= len(names):
            return True
        tgt = names[idx]
        if tgt != b.weapon and b.change_weapon(tgt):
            self.audio.ui_click()
            self.weapon_slots.refresh()
        return True

    def _fire_mech(self):
        """C = 召唤机甲，和点击右上角机甲按钮走同一条链路。"""
        slot = getattr(self, "mech_slot", None)
        if slot is None or not slot.visible():
            self.toast("没装备机甲")
            return True
        ok, msg = slot.trigger()
        if ok:
            self.audio.ui_click()
            self.weapon_slots = None
        elif msg:
            self.toast(msg)
        return True

    def _fire_armor(self):
        """X = 装护甲。

        原版没有独立的「护甲」按钮：装甲是士兵的被动减伤。战斗里能「装」
        的只有技能栏里的护甲类道具（护盾 / 装甲包）。这里按名字找，
        找不到就退到第 4 个道具，再没有就提示。
        """
        bar = getattr(self, "ability_bar", None)
        if bar is None or not getattr(bar, "rects", None):
            self.toast("没有可用的护甲道具")
            return True
        names = [n for _r, n in bar.rects]
        pick = None
        for n in names:
            nl = str(n).lower()
            if "armor" in nl or "shield" in nl or "armo" in nl:
                pick = n
                break
        if pick is None and len(names) > 3:
            pick = names[3]
        if pick is None:
            self.toast("没有可用的护甲道具")
            return True
        if bar.trigger(pick):
            self.audio.ui_click()
        return True

    def key_up(self, key):
        if self.scene != "battle" or self.battle is None:
            return False
        # 松开始终走同一套映射，提示开关不会留下卡住的移动/开火状态。
        kb = self.keybinds()
        if key in (kb["left"], pygame.K_LEFT):
            self.battle.key_left = False
        elif key in (kb["right"], pygame.K_RIGHT):
            self.battle.key_right = False
        elif key == kb["fire"]:
            self.battle.key_fire = False
        else:
            return False
        return True

    # ------------------------------------------------------------ 主循环
