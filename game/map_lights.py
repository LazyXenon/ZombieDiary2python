"""地图上的区域光效 —— 原版 MapLayer::addLightEffect @0x1232a4。

原版每种光效的动画不同（全部 RepeatForever）：

  map_cemetery_light_l / _r
      FadeTo(1.5s, 130) → FadeTo(1.5s, 255)      循环
  map_lcd_light
      Delay(randInt(10)) → Show → Blink(0.9s, randInt(6)) → Hide
  map_lab_light_3
      ScaleTo(1.0s, 1.9) → ScaleTo(1.5s, 0.7)     循环
  map_country_light
      FadeTo(1.5s, 128) + ScaleTo(1.5s, randFloat(0.2))  循环
  map_cemetery_light（墓地散点）
      FadeTo(1.5s, 128) → ScaleTo(1.5s, randFloat(0.2))
      → FadeTo(1.5s, 255) → Delay(randInt(3))      循环

反编译里的 randInt/randFloat 是真随机，本实现用固定种子复现，
保证每次运行画面一致（可截图对比）。
"""

import math

from engine import res
from game.dialog import H, W


FADE_A = 130
FADE_B = 255
FADE_TIME = 1.5
SCALE_TIME = 1.5


def _cycle(t, period, lo, hi):
    """循环段：前半段 lo→hi，后半段 hi→lo。"""
    p = (t % period) / period
    if p < 0.5:
        k = p * 2.0
    else:
        k = (1.0 - p) * 2.0
    return lo + (hi - lo) * k


def light_alpha(tex, t, seed):
    """按贴图名给出当前 alpha（0..255）。

    起始相位对齐原版：所有光效在 t=0 时都还没亮起（Delay 阶段）。
    """
    name = tex.rsplit("/", 1)[-1]
    if name in ("map_cemetery_light_l.png", "map_cemetery_light_r.png"):
        # FadeTo(1.5s,130) → FadeTo(1.5s,255)：起始从 130 淡入
        return _cycle(t + seed + FADE_TIME, FADE_TIME * 2, FADE_A, FADE_B)
    if name == "map_lcd_light.png":
        # Delay(randInt 10) → Show → Blink(0.9s, randInt 6) → Hide
        period = 10.0 + 0.9 * 6 + 10.0
        p = (t + seed) % period
        if p < 10.0:
            return 0
        if p < 10.0 + 0.9 * 6:
            step = int((p - 10.0) / 0.9)
            return 255 if step % 2 == 0 else 0
        return 0
    if name == "map_lab_light_3.png":
        return 255
    if name == "map_country_light.png":
        return _cycle(t + seed + FADE_TIME, FADE_TIME * 2, 128, FADE_B)
    if name == "map_cemetery_light.png":
        return _cycle(t + seed + FADE_TIME, FADE_TIME * 2, 128, FADE_B)
    return None


def light_scale(tex, t, seed):
    """部分光效还带缩放动画，返回相对 scale 系数（1.0 = 不变）。"""
    name = tex.rsplit("/", 1)[-1]
    if name == "map_lab_light_3.png":
        # ScaleTo(1.0s, 1.9) → ScaleTo(1.5s, 0.7)
        p = (t + seed) % (1.0 + 1.5)
        if p < 1.0:
            return 1.0 + (1.9 - 1.0) * (p / 1.0)
        return 1.9 + (0.7 - 1.9) * ((p - 1.0) / 1.5)
    if name == "map_country_light.png":
        # ScaleTo(1.5s, randFloat(0.2))
        p = (t + seed) % (FADE_TIME * 2)
        return 1.0 + 0.2 * math.sin(p / FADE_TIME * math.pi)
    return None
