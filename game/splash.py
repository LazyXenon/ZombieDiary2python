"""启动 Logo 场景 —— 原版 SplashLogoScene，加动态表现。

反编译依据：
  SplashLogoScene::init                @0x11ebec
  SplashLogoScene::onLoadingResCallback @0x11ee6a
  SplashLogoScene::onSwitchSceneCallback @0x11ed9a

════════════════════════════════════════════════════════════════════
原版流程
════════════════════════════════════════════════════════════════════
1. 铺一层全屏纯色（CCLayerColor，RGBA = 0xFF,0xFF,0xFF,0xFF，即不透明白）
   —— 反编译里 v15[0..3] = -1，四字节全 0xFF。
2. logo：pic_logo/ezjoy_network.png  anchor(0.5,0.5)  pos(W*0.5, H*0.5)
3. 等 3 帧（EzActionDelayFrame 3）→ onLoadingResCallback：
   载入资源；总停留时间不足 1 秒时补足到 1 秒（`1.0 - elapsed`，≤0 取 0）
   → onSwitchSceneCallback：replaceScene(MainMenuScene)

本复刻没有异步资源加载，等价于「logo 显示 MIN_TIME 秒后进主菜单」。

════════════════════════════════════════════════════════════════════
动态表现（原版是静止的，这里做增强）
════════════════════════════════════════════════════════════════════
· logo 呼吸缩放：1.0 ↔ 1.06，周期 1.6 秒
· logo 淡入：前 0.45 秒从全透明到不透明
· 星星粒子：18 颗 loading_star.png 绕 logo 中心缓慢公转 + 各自上下浮动，
  亮度随距离衰减（加色混合），模拟"能量汇聚"的观感

粒子数量刻意压到 18 —— 粒子是每帧贴图，开太多会掉帧。
"""

import math
import random

import pygame

from engine import res
from game.dialog import H, W


LOGO_TEX = "pic_logo/ezjoy_network.png"
SPARK_TEX = "pic_particle/loading_star.png"
BG_COLOR = (255, 255, 255, 255)  # CCLayerColor 四字节全 0xFF
MIN_TIME = 1.6  # 动态动画要看得清，停留稍微拉长
DELAY_FRAMES = 3

# 动态参数
FADE_IN = 0.45  # logo 淡入时长
BREATH_PERIOD = 1.6  # 呼吸缩放周期
SPARK_COUNT = 18  # 环绕星星数


class _Spark:
    """一颗绕 logo 公转的星星。"""

    def __init__(self, rng):
        self.angle = rng.uniform(0.0, math.tau)
        self.radius = rng.uniform(140.0, 230.0)
        self.speed = rng.uniform(0.35, 0.85)  # 角速度（rad/s）
        self.bob_phase = rng.uniform(0.0, math.tau)
        self.bob_amp = rng.uniform(4.0, 12.0)
        self.bob_speed = rng.uniform(1.0, 2.2)
        self.scale = rng.uniform(0.5, 1.1)
        self.alpha = rng.uniform(0.35, 0.9)

    def update(self, dt):
        self.angle = (self.angle + self.speed * dt) % math.tau
        self.bob_phase += self.bob_speed * dt

    def pos(self, cx, cy):
        x = cx + math.cos(self.angle) * self.radius
        y = cy + math.sin(self.angle) * self.radius * 0.42
        y += math.sin(self.bob_phase) * self.bob_amp
        return x, y


class SplashScene:
    """启动画面。done = True 表示可切主菜单。"""

    def __init__(self, app):
        self.app = app
        self.t = 0.0
        self.done = False
        self.rng = random.Random(20261105)
        self.sparks = [_Spark(self.rng) for _ in range(SPARK_COUNT)]

    def update(self, dt):
        self.t += dt
        for sp in self.sparks:
            sp.update(dt)
        if self.t >= MIN_TIME:
            self.done = True

    def click(self, pos):
        # 原版没有任何触摸响应，点哪都不加速
        return False

    def draw(self, s):
        s.fill(BG_COLOR)
        logo = res.load_img(LOGO_TEX)
        cx, cy = W * 0.5, H * 0.5
        self._draw_sparks(s, cx, cy)

        if not logo:
            return
        # 呼吸缩放：1.0 ↔ 1.06
        k = 0.5 + 0.5 * math.sin(self.t / BREATH_PERIOD * math.tau)
        scale = 1.0 + 0.06 * k
        w = max(1, int(logo.get_width() * scale))
        h = max(1, int(logo.get_height() * scale))
        im = pygame.transform.smoothscale(logo, (w, h))
        # 淡入
        fade = min(1.0, self.t / FADE_IN) if FADE_IN > 0 else 1.0
        if fade < 1.0:
            im = im.copy()
            im.fill((255, 255, 255, int(255 * fade)), special_flags=pygame.BLEND_RGBA_MULT)
        s.blit(im, (int(cx - w / 2), int(cy - h / 2)))

    def _draw_sparks(self, s, cx, cy):
        """绕 logo 公转的星星（加色混合）。"""
        img = res.load_img(SPARK_TEX)
        if img is None:
            return
        for sp in self.sparks:
            x, y = sp.pos(cx, cy)
            w = max(1, int(img.get_width() * sp.scale))
            h = max(1, int(img.get_height() * sp.scale))
            im = pygame.transform.smoothscale(img, (w, h))
            # 离中心越远越暗
            d = math.hypot(x - cx, (y - cy) * 2.0) / 260.0
            fade = max(0.0, 1.0 - d)
            a = int(255 * sp.alpha * fade)
            if a <= 4:
                continue
            im = im.copy()
            im.fill((255, 255, 255, a), special_flags=pygame.BLEND_RGBA_MULT)
            s.blit(im, (int(x - w / 2), int(y - h / 2)))
