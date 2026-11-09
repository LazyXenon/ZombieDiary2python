"""领奖动画：奖励图标从格子飞进顶栏货币位，落地时数字才跳。

签到 / 成就这类面板点「领取」时，原版不是瞬间加钱 —— 奖励图标沿一条
抛物线飞向顶栏的货币数字，落地那一刻数字才更新并弹一下。这里复刻这条
表现层。

数据一致性：
  奖励在**点击瞬间就落盘**（避免玩家领完立刻关游戏丢奖励），
  但顶栏显示的是「存档值 − 还在飞的数量」，飞完 pending 归零，
  数字自然跳到新值。这样既有动画，又不会真的丢钱。
"""

import math

import pygame

from engine import res


# 顶栏货币位的屏幕坐标（与 scene_map._draw_dynamic_topbar 的标定一致）
COIN_POS = (338.0, 43.0)
CRYSTAL_POS = (468.0, 43.0)

FLY_TIME = 0.55  # 单颗飞行时长
STAGGER = 0.05  # 相邻两颗的出发间隔
ARC = 90.0  # 抛物线拱高（像素）
POP_TIME = 0.22  # 落地后数字放大的时长
POP_MAX = 1.35  # 数字放大峰值


class _Flyer:
    """一颗飞行中的奖励图标。"""

    def __init__(self, im, x0, y0, x1, y1, delay, kind, amount):
        self.im = im
        self.x0, self.y0 = x0, y0
        self.x1, self.y1 = x1, y1
        self.delay = delay
        self.t = 0.0
        self.kind = kind  # "coin" / "crystal"
        self.amount = amount  # 落地时结算的数量

    def update(self, dt):
        self.t += dt
        return self.t >= self.delay + FLY_TIME

    def pos(self):
        """(x, y, 缩放)：缓入缓出 + 抛物线拱起。"""
        k = (self.t - self.delay) / FLY_TIME
        k = max(0.0, min(1.0, k))
        e = k * k * (3.0 - 2.0 * k)  # smoothstep
        x = self.x0 + (self.x1 - self.x0) * e
        y = self.y0 + (self.y1 - self.y0) * e - ARC * math.sin(math.pi * k)
        sc = 1.0 - 0.35 * k  # 越飞越小，落进数字里
        return x, y, sc


class RewardFly:
    """一条领奖动画。App 持有一个实例。"""

    def __init__(self):
        self.items = []
        self.pop = 0.0  # 落地后数字放大的剩余时长
        self.pop_kind = None
        # ★ 还没落地的数量：顶栏显示 (存档 − pending)
        self.pending_coin = 0
        self.pending_crystal = 0

    def active(self):
        return bool(self.items)

    def spawn(self, x0, y0, coin=0, crystal=0):
        """从 (x0, y0) 起飞。coin / crystal 是要结算的数量。"""
        if coin <= 0 and crystal <= 0:
            return
        # 数量越多飞得越久（最多 6 颗，避免后期签到大奖励拖太久）
        if coin > 0:
            icon = res.load_img("pic/ui/common/coin.png")
            n = min(6, max(2, coin // 20))
            for i in range(n):
                if icon:
                    self.items.append(
                        _Flyer(
                            icon,
                            x0 + (i - n / 2) * 14,
                            y0,
                            COIN_POS[0],
                            COIN_POS[1],
                            i * STAGGER,
                            "coin",
                            coin,
                        )
                    )
            self.pending_coin += int(coin)
        if crystal > 0:
            icon = res.load_img("pic/ui/common/crystal.png")
            n = min(5, max(2, crystal // 3))
            for i in range(n):
                if icon:
                    self.items.append(
                        _Flyer(
                            icon,
                            x0 + (i - n / 2) * 14,
                            y0,
                            CRYSTAL_POS[0],
                            CRYSTAL_POS[1],
                            0.15 + i * STAGGER,
                            "crystal",
                            crystal,
                        )
                    )
            self.pending_crystal += int(crystal)

    def update(self, dt):
        if self.pop > 0:
            self.pop = max(0.0, self.pop - dt)
        done_kinds = set()
        alive = []
        for f in self.items:
            if f.update(dt):
                done_kinds.add(f.kind)
            else:
                alive.append(f)
        self.items = alive
        # 某一类全部落地 → pending 清零 + 数字弹一下
        for kind in done_kinds:
            if kind == "coin":
                self.pending_coin = 0
            else:
                self.pending_crystal = 0
            self.pop = POP_TIME
            self.pop_kind = kind

    def pop_scale(self, kind):
        """顶栏数字当前的缩放倍数（落地瞬间弹一下）。"""
        if self.pop <= 0 or self.pop_kind != kind:
            return 1.0
        k = self.pop / POP_TIME  # 1 → 0
        return 1.0 + (POP_MAX - 1.0) * math.sin(math.pi * k)

    def draw(self, s):
        for f in self.items:
            if f.t < f.delay:
                continue
            x, y, sc = f.pos()
            w = max(1, int(f.im.get_width() * sc))
            h = max(1, int(f.im.get_height() * sc))
            im = pygame.transform.smoothscale(f.im, (w, h))
            s.blit(im, (int(x - w / 2), int(y - h / 2)))
