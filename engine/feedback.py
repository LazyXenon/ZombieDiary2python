"""统一的按键反馈系统。

三层结构：

  1. **动作表（ACTIONS）** —— 动作名 → 默认键、触发状态、反馈规格
  2. **反馈规格（Feedback）** —— 音效 / 视觉 / 触觉，按优先级仲裁
  3. **运行时（FeedbackBus）** —— 接收事件、播放在场反馈、驱动 UI 状态

设计要点：
  * 反馈分四级优先级：ERROR > SUCCESS > NORMAL > IDLE。
    同帧触发多个时高优先级覆盖低优先级（低优先级仍会播完自己的音效，
    但视觉只显示最高级的那个）。
  * 视觉反馈有两种：
      - **瞬时**：整屏闪烁 / 缩放（存 flash 时长）
      - **持续**：按钮按住态（存 pressed 集合，松手清除）
  * 音效走 `engine.audio.Audio`，缺文件时静默（原版音效不全）。
  * 所有时间用秒，由 App.step(dt) 驱动。

对外 API：

    bus = FeedbackBus(audio)
    bus.trigger("ui.press", pos=(x, y))       # 按下
    bus.trigger("ui.click", pos=(x, y))       # 点击成功
    bus.trigger("ui.error", pos=(x, y))       # 无效操作
    bus.release(pos)                          # 松手
    bus.update(dt)                            # 每帧推进
    bus.flash_alpha()                         # 当前整屏闪烁 alpha
    bus.is_pressed("btn_name")                # 按钮是否按住
"""

import pygame


# ---------------------------------------------------------------- 优先级
ERROR = 3
SUCCESS = 2
NORMAL = 1
IDLE = 0

PRIORITY_NAME = {ERROR: "ERROR", SUCCESS: "SUCCESS", NORMAL: "NORMAL", IDLE: "IDLE"}


# ---------------------------------------------------------------- 动作表
# key: 动作名
#   sfx      音效名（engine/audio 的 sfx() 参数，可给列表）
#   volume   音量
#   priority 优先级
#   flash    整屏闪烁时长（秒），0 = 不闪
#   flash_color 闪烁颜色 (r,g,b)
#   hold     是否是「按住态」动作（按下要记住、松手要清）
#   shake    屏幕抖动强度（像素）
ACTIONS = {
    # ---- 通用 UI ----
    "ui.press": dict(sfx="bn_pressed", volume=0.35, priority=NORMAL, flash=0.0, hold=True),
    "ui.click": dict(sfx="bn_pressed", volume=0.7, priority=SUCCESS),
    "ui.error": dict(
        sfx="lose_life", volume=0.6, priority=ERROR, flash=0.16, flash_color=(255, 70, 70)
    ),
    "ui.open": dict(sfx="board_open", volume=0.6, priority=NORMAL),
    "ui.close": dict(sfx="tab", volume=0.5, priority=NORMAL),
    "ui.tab": dict(sfx="tab", volume=0.6, priority=NORMAL),
    "ui.coin": dict(sfx="coin_added", volume=0.8, priority=SUCCESS),
    "ui.unlock": dict(sfx="unlock", volume=0.8, priority=SUCCESS),
    # ---- 商店 / 升级 ----
    "shop.buy": dict(sfx="buy_bullet_1", volume=0.8, priority=SUCCESS),
    "shop.owned": dict(sfx="tab", volume=0.5, priority=NORMAL),
    "shop.upgrade": dict(
        sfx="upgrade_gun", volume=0.9, priority=SUCCESS, flash=0.22, flash_color=(255, 230, 120)
    ),
    "shop.upgrade_fail": dict(
        sfx="lose_life", volume=0.6, priority=ERROR, flash=0.16, flash_color=(255, 70, 70)
    ),
    "shop.maxed": dict(sfx="tab", volume=0.5, priority=NORMAL),
    # ---- 战斗 ----
    "battle.fire": dict(sfx=None, volume=0.5, priority=NORMAL, hold=True),
    "battle.switch": dict(sfx="tab", volume=0.55, priority=NORMAL),
    "battle.ability": dict(sfx="unlock", volume=0.7, priority=NORMAL),
    "battle.hurt": dict(
        sfx="hurt_soldier_1",
        volume=0.6,
        priority=ERROR,
        flash=0.12,
        flash_color=(200, 40, 40),
        shake=6.0,
    ),
    "battle.empty": dict(sfx="bn_pressed", volume=0.4, priority=ERROR),
}


# ---------------------------------------------------------------- 视觉状态
class VisualFeedback:
    """瞬时视觉（整屏闪烁 / 抖动）。同一时刻只有一个生效。"""

    def __init__(self):
        self.t = 0.0  # 剩余时长
        self.dur = 0.0
        self.color = (255, 255, 255)
        self.priority = IDLE
        self.shake = 0.0

    def start(self, dur, color, priority, shake=0.0):
        # 高优先级覆盖；同级刷新时长
        if priority < self.priority and self.t > 0:
            return False
        self.t = dur
        self.dur = max(dur, 1e-6)
        self.color = color
        self.priority = priority
        self.shake = shake
        return True

    def update(self, dt):
        if self.t > 0:
            self.t = max(0.0, self.t - dt)
            if self.t <= 0:
                self.priority = IDLE

    def alpha(self):
        """闪烁透明度：触发瞬间最亮（1.0），之后线性衰减到 0。

        玩家点下去的第一帧完全看不见，等于没反馈。
        现在改成「起手满亮、单调衰减」，符合原版 EzSprite 闪白的观感。
        """
        if self.t <= 0:
            return 0
        k = self.t / self.dur  # 1 → 0
        # 前 25% 保持满亮，之后线性衰减
        if k >= 0.75:
            fade = 1.0
        else:
            fade = k / 0.75
        return int(120 * fade)

    def offset(self):
        """抖动偏移（像素）。只在有 shake 时非零。"""
        if self.t <= 0 or self.shake <= 0:
            return 0, 0
        k = self.t / self.dur
        amp = self.shake * k
        # 用剩余时间做相位，保证衰减到 0
        ph = self.t * 90.0
        return int(amp * pygame.math.Vector2(1, 0).rotate(ph * 57.3).x), 0


# ---------------------------------------------------------------- 总线
class FeedbackBus:
    """按键反馈总线。由 App 持有，一个实例贯穿全局。"""

    def __init__(self, audio=None):
        self.audio = audio
        self.visual = VisualFeedback()
        self.held = {}  # pos_key → action  当前按住的按钮
        self.counts = {}  # action → 累计触发次数（测试与调试用）
        self.muted = False
        self.ripples = []  # [x, y, t, dur, (r,g,b)]

    def ripple(self, pos, color=(255, 240, 190), dur=0.34):
        if pos is None:
            return
        self.ripples.append([float(pos[0]), float(pos[1]), 0.0, dur, color])
        if len(self.ripples) > 8:
            del self.ripples[:-8]

    # ---- 触发 ----
    def trigger(self, action, pos=None, sfx_override=None):
        """触发一个动作的反馈。返回实际生效的规格（可能为 None）。"""
        spec = ACTIONS.get(action)
        if spec is None:
            return None
        self.counts[action] = self.counts.get(action, 0) + 1

        if self.muted:
            return spec

        # 按住态：记住位置
        if spec.get("hold") and pos is not None:
            self.held[self._key(pos)] = action
        if pos is not None:
            self.ripple(pos, spec.get("ripple_color", (255, 240, 190)))

        # 音效
        snd = sfx_override if sfx_override is not None else spec.get("sfx")
        if snd and self.audio is not None:
            self.audio.sfx(snd, spec.get("volume", 0.8))

        # 瞬时视觉
        dur = spec.get("flash", 0.0)
        if dur > 0:
            self.visual.start(
                dur,
                spec.get("flash_color", (255, 255, 255)),
                spec.get("priority", NORMAL),
                spec.get("shake", 0.0),
            )
        return spec

    def release(self, pos=None):
        """松手：清掉按住态。pos=None 清空全部。"""
        if pos is None:
            self.held.clear()
        else:
            self.held.pop(self._key(pos), None)

    @staticmethod
    def _key(pos):
        # 20px 一格的桶，避免 1px 抖动导致记不住
        return (int(pos[0]) // 20, int(pos[1]) // 20)

    def is_pressed(self, pos):
        return self._key(pos) in self.held

    def any_pressed(self):
        return bool(self.held)

    # ---- 推进 ----
    def update(self, dt):
        self.visual.update(dt)
        if self.ripples:
            for r in self.ripples:
                r[2] += dt
            self.ripples = [r for r in self.ripples if r[2] < r[3]]

    # ---- 查询 ----
    def flash_alpha(self):
        return self.visual.alpha()

    def flash_color(self):
        return self.visual.color

    def shake_offset(self):
        return self.visual.offset()

    def busy(self):
        """是否有正在播放的瞬时反馈。"""
        return self.visual.t > 0

    def reset(self):
        self.held.clear()
        self.ripples.clear()
        self.visual.t = 0.0
        self.visual.priority = IDLE
        self.counts.clear()
