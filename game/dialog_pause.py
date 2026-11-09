"""暂停对话框 —— 原版 DialogLevelPaused。

反编译照抄（sub_1AAFE4 @0x1aafe4，即 DialogLevelPaused::init 的实现）：

  音乐按钮 button_music_on_off.png
      anchor(1.0, 1.0)          scale 0.72
      pos.x = W - (btn.w * 0.7) * 0.1
      pos.y = H - (btn.h + 4) * 0.55
  音效按钮 button_sound_on_off.png
      anchor(1.0, 1.0)          scale 0.72
      pos.x = 同上（复用 v51）
      pos.y = H - (btn.h + 4) * 1.6
  继续按钮 button_resume.png
      anchor(0.5, 0.5)          scale 1.2
      pos = (W * 0.5, H * 0.75)
  重来按钮 button_retry.png
      anchor(0.5, 0.5)          scale 1.2
      pos = (W * 0.5, H * 0.5)
  退出按钮 button_menu.png
      anchor(0.5, 0.5)          scale 1.2
      pos = (W * 0.5, H * 0.25)

音效/音乐状态：EzGameData::isSoundOn / isMusicOn，
按钮用 EzFunctionButton::setCheckStatus 切换上下半张贴图。
"""

import pygame

from engine import res
from game.dialog import DButton, Dialog, H, W, bg_dim, draw_bg


MUSIC_TEX = "pic/ui/dialog/button_music_on_off.png"
SOUND_TEX = "pic/ui/dialog/button_sound_on_off.png"
RESUME_TEX = "pic/ui/shop/button_resume.png"
RETRY_TEX = "pic/ui/shop/button_retry.png"
MENU_TEX = "pic/ui/shop/button_menu.png"
PAUSE_BG = "pic/ui/dialog/paused_bg.png"


class PauseDialog(Dialog):
    """暂停。result: 'resume' / 'restart' / 'quit'"""

    CLOSE_FULL = True  # 暂停层没有面板底图，叉号贴屏幕右上角

    def build(self):
        save = self.app.save

        # 音乐开关
        self.music_btn = self.add(
            DButton(
                MUSIC_TEX,
                (0, 0),
                anchor=(1.0, 1.0),
                scale=0.72,
                on_off=True,
                name="music",
                callback=self._toggle_music,
            )
        )
        self.music_btn.checked = bool(save.d["settings"].get("music", True))

        # 音效开关
        self.sound_btn = self.add(
            DButton(
                SOUND_TEX,
                (0, 0),
                anchor=(1.0, 1.0),
                scale=0.72,
                on_off=True,
                name="sound",
                callback=self._toggle_sound,
            )
        )
        self.sound_btn.checked = bool(save.d["settings"].get("sound", True))

        # 继续 / 重来 / 退出
        self.add(
            DButton(
                RESUME_TEX,
                (W * 0.5, H * 0.75),
                anchor=(0.5, 0.5),
                scale=1.2,
                name="resume",
                callback=self._resume,
            )
        )
        self.add(
            DButton(
                RETRY_TEX,
                (W * 0.5, H * 0.5),
                anchor=(0.5, 0.5),
                scale=1.2,
                name="restart",
                callback=self._restart,
            )
        )
        self.add(
            DButton(
                MENU_TEX,
                (W * 0.5, H * 0.25),
                anchor=(0.5, 0.5),
                scale=1.2,
                name="quit",
                callback=self._quit,
            )
        )

        self._layout()

    def _layout(self):
        """原版按按钮「缩放后尺寸」算位置。

        sub_1AAFE4:
            pos.x = W - (btn.getContentSize().w * 0.7) * 0.1
            pos.y = H - (btn.getContentSize().h + 4) * drop
        getContentSize() 返回的是**已缩放**的尺寸，所以要先乘 scale。
        原版实测（walker dump 主菜单同款按钮）：
            pos.x = 840.613  →  W(853.33) - (212*0.8*0.7)*0.1 = 840.61 ✓
        """
        for btn, drop in ((self.music_btn, 0.55), (self.sound_btn, 1.6)):
            im = res.load_img(btn.tex)
            if not im:
                btn.pos = (W * 0.9, H * 0.5)
                continue
            bw, bh = im.get_size()
            sw, sh = bw * btn.scale, bh * btn.scale
            # pos.x = W - (sw * 0.7) * 0.1
            x = W - (sw * 0.7) * 0.1
            # pos.y = H - (sh + 4) * drop
            y = H - (sh + 4) * drop
            btn.pos = (x, y)
            btn._compute_rect()  # pos 变了要重算命中矩形

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

    def _resume(self, btn):
        self.result = "resume"
        self.done = True

    def _restart(self, btn):
        self.result = "restart"
        self.done = True

    def _quit(self, btn):
        self.result = "quit"
        self.done = True

    def on_key(self, key):
        if key == pygame.K_ESCAPE:
            self.result = "resume"
            self.done = True

    # ---- 渲染 ----
    def draw(self, s):
        bg_dim(s, 170)
        bg = res.load_img(PAUSE_BG)
        if bg:
            draw_bg(s, PAUSE_BG, (W * 0.5, H * 0.5), (0.5, 0.5), 1.0)
        for b in self.buttons:
            b.draw(s, self._is_pressed(b))
        self._draw_close_button(s)
