"""设置对话框 —— 原版 DialogSettings。

反编译照抄（DialogSettings::init @0x150560）：

  音乐开关 button_music_on_off.png  anchor(0.5,0.5) scale 1.1
      pos = (W * 0.5, H * 0.72)
  音效开关 button_sound_on_off.png  anchor(0.5,0.5) scale 1.1
      pos = (W * 0.5, H * 0.5)
  返回按钮 button_back.png          anchor(0,0)
      pos = (0, H * 0.031)，scale 按宽高比算

另有「重置数据」按钮（onButtonResetData），原版放在设置界面里，
这里复用 button_reset.png。

════════════════════════════════════════════════════════════════════
键位设置页（原版没有，本复刻新增）
════════════════════════════════════════════════════════════════════
点右侧「键位设置」按钮进入第二页，页内可调：
  · 按键模式      开 = A 左 / D 右 / 空格攻击；关 = 触屏摇杆
  · 隐藏屏幕按键  开 = 战斗里不画虚拟摇杆/开火键
  · 左移 / 右移 / 攻击  点一下进入「请按新键」捕获态，按任意键写入

三项都落盘到 Save.d["settings"] 和 Save.d["keybinds"]，重开游戏仍生效。
改键用 pygame.key.name() 的字符串存，读的时候反查。
"""

import json

import pygame

from engine import res
from game.dialog import DButton, Dialog, H, W, bg_dim, close_rect_for, draw_bg
from game.dialog_game_intro import draw_keycap
from game.ninecell import draw_9cell_atlas, fill_panel
from game.save import DEFAULT_KEYBINDS, key_display_name


MUSIC_TEX = "pic/ui/dialog/button_music_on_off.png"
SOUND_TEX = "pic/ui/dialog/button_sound_on_off.png"
BACK_TEX = "pic/ui/shop/button_back.png"
RESET_TEX = "pic/ui/dialog/button_reset.png"
KEYBINDS_TEX = "pic/ui/dialog/button_keybinds.png"
# ★ 设置面板底图。原版 DialogSettings 的节点树没有 dump 出来
# （data/node_tree_*.json 只有 menu/map/level/shop/battle 五棵树），
# 所以一直引用一个不存在的 setting_bg.png ⇒ 面板底下什么都没有，
# 「音乐 / 音效」两个开关直接浮在主菜单的爆炸背景上。
# 改成用库里的 9 宫格边框（Combined9Cells），和游戏内其它弹窗同款。
BG_TEX = "pic/ui/dialog/9cell_bg.png"
BG_RECT = (60, 56, 734, 372)

# 键位默认值。名字用 pygame.key.name() 的输出（'a' / 'd' / 'space'），
# 这样存档里是人类可读的字符串，也方便手改。
KEYBIND_LABELS = (
    ("left", "左移"),
    ("right", "右移"),
    ("fire", "攻击"),
    ("cycle", "顺序换枪"),
    ("weapon_1", "武器 1"),
    ("weapon_2", "武器 2"),
    ("weapon_3", "武器 3"),
    ("weapon_4", "武器 4"),
    ("ability_1", "道具 1"),
    ("ability_2", "道具 2"),
    ("ability_3", "道具 3"),
    ("armor", "护甲"),
    ("mech", "机甲"),
)

# 按键底板 —— 原版对话框按钮用的就是这套 3×3 图集（Combined9Cells）。
# 四张切片里只有 cell_now.png 是橙色（和「初始设置」「接受任务」同色系）：
#   cell_bg    紫色
#   cell_now   橙色  ← 用这个
#   cell_next  蓝色
# 25×17 的 3×3 切片九宫格拉伸后就是原版那种斜切立体按钮。
PLATE_TEX = "pic/ui/common/cell_now.png"
STATE_TEX = "pic/ui/common/cell_next.png"


class SettingsDialog(Dialog):
    """设置。result: 'close' / 'reset'"""

    ROW_Y0 = 158  # 第一行中心
    ROW_DY = 82  # 行距
    SMALL_ROW_Y = ROW_Y0 + ROW_DY  # 第二行：初始设置 / 键位设置
    SMALL_BTN_W = 212
    SMALL_BTN_H = 46
    SMALL_BTN_GAP = 34
    FULLSCREEN_Y = ROW_Y0 + ROW_DY * 2  # 第三行居中
    FULLSCREEN_W = SMALL_BTN_W
    FULLSCREEN_H = SMALL_BTN_H
    FULLSCREEN_LABEL_W = 146

    # 键位页布局。绘制、点击、键盘焦点共用这组常量，改一处三处同时生效。
    # 标签与开关沿用主页橙/蓝底板；具体键值使用黑灰立体键帽。
    # 横向以面板内框（inner_rect(BG_TEX, PAGE_RECT) = 141,117,572,250）为边界，
    # 开关行与七行键位都落在内框里；「恢复默认」放内框下方的面板底部横条，
    # 把内框的高度让给键位行，避免为了塞进 16 个控件而把按钮压扁。
    KEY_TITLE_Y = 108  # 标题文字中心 y（内框上方的标题栏）
    CONTENT_X0 = 141  # 内框左缘
    CONTENT_X1 = 713  # 内框右缘
    SWITCH_Y = 140
    SWITCH_H = 34
    SWITCH_LABEL_W = 118
    SWITCH_STATE_W = 56
    SWITCH_INNER_GAP = 0  # 标签与状态块相接，同主页「音乐 / 开」的一体按钮
    COL_W = 274  # 一列的槽宽，「标签 + 键值」组在槽内居中
    COL_GAP = 24
    KEY_ROW_Y0 = 182
    # 十三项要排成两列七行，压紧行距让最后一行仍在「恢复默认」按钮上方。
    KEY_ROW_DY = 27
    KEY_ROW_H = 26
    KEY_LABEL_W = 130
    KEY_LABEL_GAP = 0
    KEY_VALUE_W = 100  # 与主页蓝色状态块同量级，避免键值条过长显空

    def close_button_rect(self):
        return close_rect_for(pygame.Rect(BG_RECT), right=12, top=10)

    def build(self):
        save = self.app.save

        # 设置主页：两列网格，所有主按钮实际尺寸一致。
        half = (self.SMALL_BTN_W + self.SMALL_BTN_GAP) / 2.0
        self.music_btn = self.add(
            DButton(
                MUSIC_TEX,
                (W * 0.5 - half, H - self.ROW_Y0),
                anchor=(0.5, 0.5),
                scale=1.0,
                on_off=True,
                name="music",
                callback=self._toggle_music,
            )
        )
        self.music_btn.checked = bool(save.d["settings"].get("music", True))

        self.sound_btn = self.add(
            DButton(
                SOUND_TEX,
                (W * 0.5 + half, H - self.ROW_Y0),
                anchor=(0.5, 0.5),
                scale=1.0,
                on_off=True,
                name="sound",
                callback=self._toggle_sound,
            )
        )
        self.sound_btn.checked = bool(save.d["settings"].get("sound", True))

        # 返回（左下角）
        back = res.load_img(BACK_TEX)
        if back:
            r = W / float(H)
            sc = 0.85 if r >= 1.7 else (0.73 if r >= 1.4 else 0.64)
            self.add(
                DButton(
                    BACK_TEX,
                    (0, H * 0.031),
                    anchor=(0.0, 0.0),
                    scale=sc,
                    name="close",
                    callback=self._close,
                )
            )

        # 「初始设置」（清档重来）与「键位设置」在第二行并排。
        small_scale = 1.0
        self.add(
            DButton(
                RESET_TEX,
                (W * 0.5 - half, H - self.SMALL_ROW_Y),
                anchor=(0.5, 0.5),
                scale=small_scale,
                name="reset_data",
                callback=self._reset_data,
            )
        )
        self._confirm_reset = False
        self._confirm_t = 0.0

        self.keys_entry_rect = pygame.Rect(0, 0, self.SMALL_BTN_W, self.SMALL_BTN_H)
        self.keys_entry_rect.center = (int(W * 0.5 + half), int(self.SMALL_ROW_Y))
        self.fullscreen_rect = self._fullscreen_rect()
        self.page = "main"  # main / keys
        self._capturing = None  # 正在等玩家按键的字段（left/right/fire）
        self._capture_t = 0.0
        self._kb_error = ""  # 改键冲突提示（非空时画红字）

    # ---- 键位页 ----
    def _open_keys(self, btn):
        self.page = "keys"
        self.buttons = []
        self._build_keys_page()

    def _build_keys_page(self):
        self.music_btn = None
        self.sound_btn = None

        self.kb_mode_btn = None
        self.hide_btn = None

        back = res.load_img(BACK_TEX)
        if back:
            r = W / float(H)
            sc = 0.85 if r >= 1.7 else (0.73 if r >= 1.4 else 0.64)
            self.add(
                DButton(
                    BACK_TEX,
                    (0, H * 0.031),
                    anchor=(0.0, 0.0),
                    scale=sc,
                    name="back_page",
                    callback=self._back_to_main,
                )
            )

    def _switch_rects(self):
        """三个开关的整组矩形（标签 + 状态块），绘制与点击共用。

        三组在内框内等距铺开，左右缘与内框对齐。
        """
        group_w = self.SWITCH_LABEL_W + self.SWITCH_INNER_GAP + self.SWITCH_STATE_W
        span = self.CONTENT_X1 - self.CONTENT_X0
        step = group_w + (span - 3 * group_w) // 2
        out = []
        for i, key in enumerate(("keyboard", "hide_buttons", "key_hints")):
            x = self.CONTENT_X0 + i * step
            out.append((key, pygame.Rect(x, self.SWITCH_Y, group_w, self.SWITCH_H)))
        return out

    @staticmethod
    def _split_group(rect, label_w, gap):
        """把整组矩形切成「标签」和「值」两块，开关行与键位行共用。"""
        label = pygame.Rect(rect.x, rect.y, label_w, rect.h)
        value = pygame.Rect(label.right + gap, rect.y, rect.right - label.right - gap, rect.h)
        return label, value

    def _fullscreen_rect(self):
        """第五行的「全屏 / 开或关」一体按钮，绘制、点击、键盘焦点共用。"""
        r = pygame.Rect(0, 0, self.FULLSCREEN_W, self.FULLSCREEN_H)
        r.center = (int(W * 0.5), self.FULLSCREEN_Y)
        return r

    def _toggle_fullscreen(self):
        st = self.app.save.d["settings"]
        self.app.set_fullscreen(not bool(st.get("fullscreen", False)))

    def _toggle_switch(self, key):
        st = self.app.save.d["settings"]
        st[key] = not st.get(key, False)
        self.app.save.save()

    def _reset_keybinds(self):
        """把三个键位恢复成默认 a / d / space。"""
        self.app.save.d["keybinds"] = dict(DEFAULT_KEYBINDS)
        self.app.save.save()
        self._capturing = None
        self._kb_error = ""

    def _back_to_main(self, btn):
        self.page = "main"
        self.buttons = []
        self._capturing = None
        self.build()

    # ---- 回调 ----

    def _keybind_rects(self):
        """十三个键位的整组矩形（标签 + 键值），两列七行。

        每列槽宽与开关行一致，「标签 + 键值」组在槽内居中，两列自然对称。
        """
        group_w = self.KEY_LABEL_W + self.KEY_LABEL_GAP + self.KEY_VALUE_W
        inset = (self.COL_W - group_w) // 2
        out = []
        for i, (field, _label) in enumerate(KEYBIND_LABELS):
            col, row = i % 2, i // 2
            x = self.CONTENT_X0 + col * (self.COL_W + self.COL_GAP) + inset
            y = self.KEY_ROW_Y0 + row * self.KEY_ROW_DY
            out.append((field, pygame.Rect(x, y, group_w, self.KEY_ROW_H)))
        return out

    # 与设置主页同尺寸的面板。
    PAGE_RECT = BG_RECT
    RESET_RECT = (317, 380, 220, 34)

    def _capture_done(self, key):
        if self._capturing is None:
            return False
        name = pygame.key.name(key)
        if not name or name == "escape":
            self._capturing = None
            return True
        kb = self.app.save.d.setdefault("keybinds", dict(DEFAULT_KEYBINDS))
        # 冲突检测：同一个键不能绑两个动作，否则按下时只命中先判的那个。
        others = [f for f, v in kb.items() if f != self._capturing and v == name]
        if others:
            self._kb_error = "「%s」已被「%s」占用" % (
                name,
                " / ".join(dict(KEYBIND_LABELS).get(f, f) for f in others),
            )
            self._capturing = None
            return True
        kb[self._capturing] = name
        self.app.save.save()
        self._capturing = None
        self._kb_error = ""
        return True

    # ---- 回调 ----
    def _toggle_music(self, btn):
        st = self.app.save.d["settings"]
        st["music"] = not st.get("music", True)
        btn.checked = st["music"]
        self.app.save.save()
        self.app.audio.set_music(st["music"])

    def _toggle_sound(self, btn):
        st = self.app.save.d["settings"]
        st["sound"] = not st.get("sound", True)
        btn.checked = st["sound"]
        self.app.save.save()
        self.app.audio.set_sound(st["sound"])

    def _reset_data(self, btn):
        """清档重来（原版 onButtonResetData → DialogRemind 二段确认）。

        第一下点：进入确认态（按钮变成「再点一次确认」提示，5 秒后自动撤回）。
        第二下点：清空存档、重建 App 状态、重载游戏。
        """
        if not self._confirm_reset:
            self._confirm_reset = True
            self._confirm_t = 5.0
            return
        self._do_reset()

    def _do_reset(self):
        """清空存档并重载。

        对应 DialogRemind::resetData：先记下音乐/音效开关，clearAll，再把
        """
        save = self.app.save
        st = dict(save.d.get("settings") or {})
        try:
            save.reset_all()
        except AttributeError:
            # 兜底：Save 没提供 reset_all 时直接重建默认档
            from game.save import DEFAULT

            save.d = json.loads(json.dumps(DEFAULT))
            save.save()
        save.d["settings"]["music"] = bool(st.get("music", True))
        save.d["settings"]["sound"] = bool(st.get("sound", True))
        # 全屏是当前窗口状态，清档不该把玩家突然踢回窗口模式。
        save.d["settings"]["fullscreen"] = bool(st.get("fullscreen", False))
        save.save()
        try:
            self.app.audio.set_music(save.d["settings"]["music"])
            self.app.audio.set_sound(save.d["settings"]["sound"])
        except Exception:
            pass
        self.result = "reset"
        self.done = True

    def _close(self, btn):
        self.result = "close"
        self.done = True

    def update(self, dt):
        super().update(dt)
        if self._confirm_reset:
            self._confirm_t -= dt
            if self._confirm_t <= 0:
                self._confirm_reset = False

    def on_key(self, key):
        # 键位捕获态：任何键都写进对应的字段（Esc 取消）
        if self._capturing is not None:
            self._capture_done(key)
            return
        if key == pygame.K_ESCAPE:
            if self.page == "keys":
                self._back_to_main(None)
                return
            self.result = "close"
            self.done = True

    def key_items(self):
        """键盘焦点候选：只给**当前页**真正能点的东西。

        反射会把另一页的开关 / 改键框也算进来（它们在 main 页根本看不到），
        焦点框就会悬在空白处，所以这里按页面显式列一遍。
        """
        from app.keynav import as_rect

        out = []
        if self.close_rect is not None:
            out.append((self.close_rect, "关闭"))
        for b in self.buttons:
            if getattr(b, "enabled", True):
                r = as_rect(getattr(b, "rect", None))
                if r is not None:
                    out.append((r, getattr(b, "name", "")))
        if self.page == "main":
            r = as_rect(getattr(self, "keys_entry_rect", None))
            if r is not None:
                out.append((r, "keys_entry"))
            r = as_rect(getattr(self, "fullscreen_rect", None))
            if r is not None:
                out.append((r, "fullscreen"))
        else:
            for key, r in self._switch_rects():
                if as_rect(r) is not None:
                    out.append((as_rect(r), key))
            for field, r in self._keybind_rects():
                if as_rect(r) is not None:
                    out.append((as_rect(r), field))
            r = as_rect(pygame.Rect(self.RESET_RECT))
            if r is not None:
                out.append((r, "reset"))
        return out

    def click(self, pos):
        if self.closing():
            return False
        if self.page == "main":
            r = getattr(self, "keys_entry_rect", None)
            if r is not None and r.collidepoint(pos):
                self._open_keys(None)
                return True
            r = getattr(self, "fullscreen_rect", None)
            if r is not None and r.collidepoint(pos):
                self._toggle_fullscreen()
                return True
        # 键位页的开关行和改键框不走 DButton（它们不是贴图按钮）
        if self.page == "keys":
            rr = pygame.Rect(self.RESET_RECT)
            if rr.collidepoint(pos):
                self._reset_keybinds()
                return True
            for key, r in self._switch_rects():
                if r.collidepoint(pos):
                    self._toggle_switch(key)
                    return True
            for field, r in self._keybind_rects():
                if r.collidepoint(pos):
                    self._capturing = field
                    return True
        return super().click(pos)

    def draw(self, s):
        # 原版设置定帧外部 HUD 只剩约 31% 亮度（顶栏 103/85/94→32/28/27，
        # 右缘 51/48/60→15/15/19），且三段衰减一致 ⇒ 纯黑 0xB8 遮罩，不加色调。
        bg_dim(s, 184)
        if self.page == "keys":
            self._draw_page_panel(s)
            draw_9cell_atlas(s, BG_TEX, pygame.Rect(SettingsDialog.PAGE_RECT), 1.0)
            for b in self.buttons:
                b.draw(s, self._is_pressed(b))
            self._draw_keys_page(s)
            self._draw_close_button(s)
            return
        #   面板底，但底色只铺在框线**以内**，也不加四角贴花
        #   （「框框以外不要加贴图」）。
        pr = pygame.Rect(BG_RECT)
        fill_panel(s, BG_TEX, pr, (40, 30, 58, 255), 1.0)
        draw_9cell_atlas(s, BG_TEX, pr, 1.0)
        for b in self.buttons:
            b.draw(s, self._is_pressed(b))
        self._draw_title(s, "设  置", BG_RECT[1] + 49)
        self._draw_keys_entry(s)
        self._draw_fullscreen(s)
        if self._confirm_reset:
            self._draw_confirm(s)
        self._draw_close_button(s)

    def _draw_keys_entry(self, s):
        """设置主页的「键位设置」入口（官方橙金斜面按钮）。"""
        r = getattr(self, "keys_entry_rect", None)
        if r is None:
            return
        im = res.load_img(KEYBINDS_TEX)
        if im is None:
            return
        if im.get_size() != r.size:
            im = pygame.transform.smoothscale(im, r.size)
        s.blit(im, r.topleft)

    def _draw_fullscreen(self, s):
        """橙金标签 + 蓝色状态块，与设置主页「音乐 / 开」同套视觉。"""
        r = getattr(self, "fullscreen_rect", None)
        if r is None:
            return
        label, state = self._split_group(r, self.FULLSCREEN_LABEL_W, 0)
        draw_9cell_atlas(s, PLATE_TEX, label, 1.0)
        self._button_text(s, label, "全屏（F11）", 15, (255, 244, 224))
        on = bool(self.app.save.d["settings"].get("fullscreen", False))
        draw_9cell_atlas(s, STATE_TEX, state, 1.0)
        self._button_text(s, state, "开" if on else "关", 15)

    @staticmethod
    def _draw_page_panel(s):
        """键位页的压暗层。

        ★ 用户「框框以外不要加贴图了」：原来这里画了两圈描边（紫 + 深紫），
          等于又做了一层框。现在只留一层很淡的压暗，不放任何边框/角花，
          保证文字可读的同时不再出现「框」。
        """
        fill_panel(s, BG_TEX, pygame.Rect(SettingsDialog.PAGE_RECT), (40, 30, 58, 255), 1.0)

    @staticmethod
    def _draw_title(s, text, cy, color=(255, 236, 170)):
        """面板标题：26 号金色描影字，主页与键位页共用同一规格。"""
        font = pygame.font.SysFont("Microsoft YaHei", 26, bold=True)
        image = font.render(text, True, color)
        shadow = font.render(text, True, (60, 30, 10))
        pos = (W // 2 - image.get_width() // 2, cy - image.get_height() // 2)
        s.blit(shadow, (pos[0] + 2, pos[1] + 3))
        s.blit(image, pos)

    @staticmethod
    def _button_text(s, rect, text, size=14, color=(255, 255, 255)):
        # 键名长度不一，过宽时逐级缩字号，保证文字始终落在底板内。
        font = pygame.font.SysFont("Microsoft YaHei", size, bold=True)
        while size > 10 and font.size(text)[0] > rect.w - 12:
            size -= 1
            font = pygame.font.SysFont("Microsoft YaHei", size, bold=True)
        image = font.render(text, True, color)
        shadow = font.render(text, True, (55, 30, 25))
        pos = (rect.centerx - image.get_width() // 2, rect.centery - image.get_height() // 2)
        s.blit(shadow, (pos[0] + 1, pos[1] + 2))
        s.blit(image, pos)

    # ---------------------------------------------------------- 键位页绘制
    def _draw_keys_page(self, s):
        title = self._kb_error or "键位设置"
        color = (255, 125, 110) if self._kb_error else (255, 236, 170)
        self._draw_title(s, title, self.KEY_TITLE_Y, color)
        hint = pygame.font.SysFont("Microsoft YaHei", 12, bold=True).render(
            "Esc 返回", True, (205, 194, 214)
        )
        s.blit(hint, (self.CONTENT_X1 - hint.get_width(), 100))

        labels = {"keyboard": "按键模式", "hide_buttons": "隐藏触屏", "key_hints": "键位提示"}
        st = self.app.save.d["settings"]
        for key, rect in self._switch_rects():
            name_rect, state_rect = self._split_group(
                rect, self.SWITCH_LABEL_W, self.SWITCH_INNER_GAP
            )
            draw_9cell_atlas(s, PLATE_TEX, name_rect, 1.0)
            self._button_text(s, name_rect, labels[key], 15)
            on = bool(st.get(key, key == "key_hints"))
            draw_9cell_atlas(s, STATE_TEX, state_rect, 1.0)
            self._button_text(s, state_rect, "开" if on else "关", 15)

        label_of = dict(KEYBIND_LABELS)
        kb = dict(DEFAULT_KEYBINDS)
        kb.update(self.app.save.d.get("keybinds") or {})
        for field, rect in self._keybind_rects():
            name_rect, value_rect = self._split_group(rect, self.KEY_LABEL_W, self.KEY_LABEL_GAP)
            draw_9cell_atlas(s, PLATE_TEX, name_rect, 1.0)
            self._button_text(s, name_rect, label_of[field], 14, (255, 244, 224))
            key_name = key_display_name(kb[field])
            capturing = self._capturing == field
            draw_keycap(s, value_rect, "请按键…" if capturing else key_name, 14)
            if capturing:
                pygame.draw.rect(s, (241, 190, 82), value_rect, width=2, border_radius=7)

        rr = pygame.Rect(self.RESET_RECT)
        draw_9cell_atlas(s, PLATE_TEX, rr, 1.0)
        self._button_text(s, rr, "恢复默认键位", 16, (255, 244, 224))

    def _draw_confirm(self, s):
        """二次确认提示（原版 DialogRemind：「确定要清除所有数据吗？」）。"""
        f = pygame.font.SysFont("Microsoft YaHei", 22, bold=True)
        txt = "再点一次「初始设置」确认清除全部数据"
        im = f.render(txt, True, (255, 96, 96))
        pad = 14
        box = pygame.Rect(0, 0, im.get_width() + pad * 2, im.get_height() + pad * 2)
        # 压在按钮上会看不清，挪到面板下方的空白处（toast 位置）
        box.center = (int(W * 0.5), int(H - 34))
        for ox, oy in ((-2, 0), (2, 0), (0, -2), (0, 2), (2, 3)):
            sh = f.render(txt, True, (36, 8, 12))
            s.blit(sh, (box.x + pad + ox, box.y + pad + oy))
        s.blit(im, (box.x + pad, box.y + pad))
