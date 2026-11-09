"""僵尸命中特效 —— 中弹喷血 / 死亡断肢碎片。

数据来自各僵尸 XML 的 <shot_effect> / <Death> 段：
  shot_blood_effect duration=0.4 row_count=2 col_count=3 offset_x=70 offset_y=20
      → pic/zombies/shot_blood_2.png 切成 2x3 = 6 帧，0.4 秒播完
  Death Box2DItem offset_x/offset_y force_angle tex
      → 死亡时把断肢/眼球/脑花朝该角度抛出去，受重力落地

两者都是纯表现层，不影响战斗数值。
"""

import math
import random
import xml.etree.ElementTree as ET

import pygame

from engine import res


# 喷血图集：2 行 3 列
BLOOD_TEX = "pic/zombies/shot_blood_2.png"
BLOOD_ROWS = 2
BLOOD_COLS = 3
BLOOD_DUR = 0.4

# 玩家阵亡「脑子被咬出」：直接复用僵尸 <Death> 的脑花贴图，
# 不另画一套，保证和僵尸死亡表现是同一批素材（见 EffectLayer.add_brain_bite）。
BRAIN_TEXES = ("pic/zombies/head_nao01.png", "pic/zombies/head_nao03.png")

_blood_sheet = None


def _blood_frames():
    """把 shot_blood_2.png 切成 6 张子图（缓存）。"""
    global _blood_sheet
    if _blood_sheet is not None:
        return _blood_sheet
    im = res.load_img(BLOOD_TEX)
    if im is None:
        _blood_sheet = []
        return _blood_sheet
    w, h = im.get_size()
    cw, ch = w // BLOOD_COLS, h // BLOOD_ROWS
    frames = []
    for r in range(BLOOD_ROWS):
        for c in range(BLOOD_COLS):
            frames.append(im.subsurface((c * cw, r * ch, cw, ch)).copy())
    _blood_sheet = frames
    return frames


class BloodBurst:
    """一次中弹喷血。"""

    __slots__ = ("flip", "life", "t", "x", "y")

    def __init__(self, x, y, flip=False):
        self.x = x
        self.y = y
        self.t = 0.0
        self.life = BLOOD_DUR
        self.flip = flip

    def update(self, dt):
        self.t += dt
        return self.t >= self.life

    def draw(self, s):
        frames = _blood_frames()
        if not frames:
            return
        n = len(frames)
        fi = min(n - 1, int(self.t / self.life * n))
        im = frames[fi]
        if self.flip:
            im = pygame.transform.flip(im, True, False)
        s.blit(im, (int(self.x - im.get_width() / 2), int(self.y - im.get_height() / 2)))


# ---------------------------------------------------------- Box2D 真值
# ZombieBox2DItem::creatPhysicalBody @0x1756ec（all_merged.c:118754）：
#   v22  = LOGIC * 13.58 * mass
#   x    = (randFloat(-20, 20) + force_angle) * pi / 180
#   v29  = (cos(x) * v22 * a4,  sin(x) * v22)
#   ApplyLinearImpulse(v29, ...)
# 因此碎片初速 = 13.58 逻辑单位/秒 × 质量系数，方向是 XML 的
# force_angle 再随机偏 ±20°。
# 单位换算：Box2D 里 1 米 = 32 px（creatPhysicalBody 到处乘 0.03125=1/32；
# init 里 CCSize 也是 `PTM_RATIO = 32`）。所以：
#     速度 13.58 m/s  →  434.6 px/s
# 重力在 BattleField 构造里：`v6[1] = LOGIC * -18.8`（all_merged.c:8077）
#     ⇒ 18.8 * 32 = 601.6 px/s²
# 重力是原版的 2.5 倍 ⇒ 碎片刚离地就砸回地面，只弹 7px，
# 看着像「原地抖一下」，这就是死亡特效生草的根因。
BOX2D_PTM = 32.0
DEBRIS_SPEED = 13.58 * BOX2D_PTM  # 434.6 px/s
DEBRIS_GRAVITY = 18.8 * BOX2D_PTM  # 601.6 px/s²
DEBRIS_ANGLE_JITTER = 20.0  # randFloat(-20, 20)
DEBRIS_MASS_SCALE = 0.3  # a4 —— 见 spawn_death_debris


class Debris:
    """死亡碎片：一个刚体小图，受重力抛物落地淡出。"""

    __slots__ = ("ground", "img", "life", "rot", "t", "vrot", "vx", "vy", "x", "y")

    def __init__(self, img, x, y, angle_deg, ground_y, mass_scale=DEBRIS_MASS_SCALE):
        self.img = img
        self.x = x
        self.y = y
        self.ground = ground_y
        # 原版：方向 = force_angle + randFloat(-20, 20)
        a = math.radians(angle_deg + random.uniform(-DEBRIS_ANGLE_JITTER, DEBRIS_ANGLE_JITTER))
        spd = DEBRIS_SPEED * mass_scale
        self.vx = math.cos(a) * spd
        self.vy = -math.sin(a) * spd
        # 自转：原版 CActionRotate 的角速度是随机的，保留观感即可
        self.rot = 0.0
        self.vrot = random.uniform(-320.0, 320.0)
        self.t = 0.0
        self.life = 1.6

    def update(self, dt):
        self.t += dt
        self.vy += DEBRIS_GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.rot += self.vrot * dt
        if self.y > self.ground:
            self.y = self.ground
            # Box2D 默认 restitution 0.2（b2FixtureDef 里没改），
            # 落地反弹只留两成速度。
            self.vy *= -0.2
            self.vx *= 0.5
            self.vrot *= 0.5
        return self.t >= self.life

    def draw(self, s):
        k = self.t / self.life
        im = self.img
        if abs(self.rot) > 0.5:
            im = pygame.transform.rotate(im, self.rot)
        if k > 0.62:
            im = im.copy()
            im.set_alpha(max(0, int(255 * (1.0 - (k - 0.62) / 0.38))))
        s.blit(im, (int(self.x - im.get_width() / 2), int(self.y - im.get_height() / 2)))


class DeathSplat:
    """死亡大喷血 —— ZombieCharacter::onDeath @0x194204 开头那段。

    原版（all_merged.c:120583）：
        1. 一副 EzSprite(shot_blood_2.png, 3 行 5 列) 摆在
           Zombie::getCenterX/YInBattleFiled 再 +40 逻辑单位的高度上；
           它自己带一个 3 秒的动画链。
        2. 同一张图再走 animationWithResName(shot_blood_2, 3, ...)，
           每帧时长 = 0.4 / 帧数（`*((float*)v14+10) = 0.4 / n`），
           播完接 CCFadeOut(0.8) 再 removeFromParent。
           ⇒ 这是一次**0.4 秒播完、再淡出 0.8 秒**的喷血。

    （BloodBurst，0.4 秒 2×3），死亡瞬间完全没有，看着像静静躺下。
    """

    __slots__ = ("flip", "life", "t", "x", "y")

    ANIM = 0.4  # 0.4 / 帧数 × 帧数
    FADE = 0.8  # CCFadeOut::actionWithDuration(0x3F4CCCCD = 0.8)

    def __init__(self, x, y, flip=False):
        self.x = x
        self.y = y
        self.t = 0.0
        self.life = self.ANIM
        self.flip = flip

    def update(self, dt):
        self.t += dt
        return self.t >= self.life + self.FADE

    def draw(self, s):
        frames = _blood_frames()
        if not frames:
            return
        n = len(frames)
        # 0..ANIM 播帧（播完停在最后一帧），之后原地淡出
        k = min(1.0, self.t / self.ANIM)
        im = frames[min(n - 1, int(k * n))]
        if self.flip:
            im = pygame.transform.flip(im, True, False)
        if self.t > self.ANIM:
            a = 1.0 - (self.t - self.ANIM) / self.FADE
            im = im.copy()
            im.set_alpha(max(0, int(255 * a)))
        s.blit(im, (int(self.x - im.get_width() / 2), int(self.y - im.get_height() / 2)))


class DeathStain:
    """死亡后飞出的血渍贴图 xuezi04.png。

    原版（all_merged.c:120614）：
        贴图 xuezi04.png，旋转 randInt(-15, 15) 度，scale 0.3，
        摆在 Zombie 的某个子节点位置（`(*(**)(a1+428))(72)` 取节点位置）。
        动画链：CCScaleTo(0.1, zscale * 0.8 * v26)
              + CCDelayTime(1.0) + CCFadeTo(1.0, 0)
        v26 对 boss_1 = 2.5、boss_2 = 254<<22，普通僵尸 = 255<<22
        （这两处是反编译把 float 常量当整数的残留，实际就是缩放系数）。
    """

    __slots__ = ("im", "life", "rot", "s0", "s1", "t", "x", "y")

    GROW = 0.1
    HOLD = 1.0
    FADE = 1.0

    def __init__(self, im, x, y, scale=0.3, target_scale=1.0):
        self.im = im
        self.x = x
        self.y = y
        self.t = 0.0
        self.life = self.GROW + self.HOLD + self.FADE
        self.s0 = scale
        self.s1 = target_scale
        self.rot = float(random.randint(-15, 15))

    def update(self, dt):
        self.t += dt
        return self.t >= self.life

    def draw(self, s):
        t = self.t
        if t < self.GROW:
            k = t / self.GROW
            sc = self.s0 + (self.s1 - self.s0) * k
            alpha = 255
        elif t < self.GROW + self.HOLD:
            sc = self.s1
            alpha = 255
        else:
            sc = self.s1
            f = (t - self.GROW - self.HOLD) / self.FADE
            alpha = max(0, int(255 * (1.0 - f)))
        w = max(1, int(self.im.get_width() * sc))
        h = max(1, int(self.im.get_height() * sc))
        im = pygame.transform.smoothscale(self.im, (w, h))
        if self.rot:
            im = pygame.transform.rotate(im, self.rot)
        if alpha < 255:
            im = im.copy()
            im.set_alpha(alpha)
        s.blit(im, (int(self.x - im.get_width() / 2), int(self.y - im.get_height() / 2)))


class EffectLayer:
    """一个战场上的所有表现层特效。"""

    def __init__(self):
        self.bloods = []
        self.debris = []
        self.splats = []  # 死亡大喷血
        self.stains = []  # 落地血渍

    def add_blood(self, x, y, flip=False):
        self.bloods.append(BloodBurst(x, y, flip))

    def add_death_splat(self, x, y, flip=False):
        self.splats.append(DeathSplat(x, y, flip))

    def add_stain(self, im, x, y, scale=0.3, target_scale=1.0):
        if im is not None:
            self.stains.append(DeathStain(im, x, y, scale, target_scale))

    def add_debris(self, items):
        self.debris.extend(items)

    def add_brain_bite(self, screen_x, head_y, ground_y, flip=False):
        """玩家阵亡：脑花被咬出（一次性，只在 hp<=0 那帧调用）。

        复用僵尸 <Death> 的脑花贴图 + 同一套 Box2D 抛射物理，起点换到
        士兵头部、朝面朝的反侧上方抛出，再补一蓬血。复活 / 续关不重播。
        """
        for tex in BRAIN_TEXES:
            im = res.load_img(tex)
            if im is None:
                continue
            ang = (70.0 if flip else 110.0) + random.uniform(-14.0, 14.0)
            self.debris.append(
                Debris(im, screen_x, head_y, ang, ground_y, mass_scale=random.uniform(0.45, 0.7))
            )
        self.splats.append(DeathSplat(screen_x, head_y + 24.0, flip))

    def update(self, dt):
        self.bloods = [b for b in self.bloods if not b.update(dt)]
        self.debris = [d for d in self.debris if not d.update(dt)]
        self.splats = [p for p in self.splats if not p.update(dt)]
        self.stains = [p for p in self.stains if not p.update(dt)]

    def draw_blood(self, s):
        for b in self.bloods:
            b.draw(s)

    def draw_debris(self, s):
        for d in self.debris:
            d.draw(s)

    def draw_stains(self, s):
        """血渍贴地，必须画在僵尸**下面**。"""
        for p in self.stains:
            p.draw(s)

    def draw_splats(self, s):
        for p in self.splats:
            p.draw(s)

    def clear(self):
        self.bloods.clear()
        self.debris.clear()
        self.splats.clear()
        self.stains.clear()


# ---------------------------------------------------------------- 死亡碎片
# ★ 每只僵尸的 <Death> 里各写各的 Box2DItem 贴图（zombie_1 → pic/zombies/01/
#   pic/zombies/01 的眼球/左臂/右臂 —— 于是**任何**僵尸死掉都抛出一条
#   01 的手臂（那只手还攥着个绿色药瓶），玩家看到的就是「这瓶子哪来的」。
#   现在按僵尸名读它自己的 <Death>，只用它自己的部件。
_COMMON_DEBRIS = [
    ("pic/zombies/body_suipian01.png", 170.0),
    ("pic/zombies/body_suipian02.png", 30.0),
    ("pic/zombies/body_suipian03.png", 10.0),
    ("pic/zombies/head_nao01.png", 100.0),
    ("pic/zombies/head_nao03.png", 65.0),
]

# 死亡血渍贴图（ZombieCharacter::onDeath @0x194204 里 xuezi04.png）
STAIN_TEX = "pic/zombies/xuezi04.png"
_stain_img = None


def stain_image():
    global _stain_img
    if _stain_img is None:
        _stain_img = res.load_img(STAIN_TEX)
    return _stain_img


_debris_imgs = None


def debris_images():
    """通用兜底池（僵尸 XML 里没有可用的 Box2DItem 时用）。"""
    global _debris_imgs
    if _debris_imgs is None:
        out = []
        for path, ang in _COMMON_DEBRIS:
            im = res.load_img(path)
            if im is not None:
                out.append((im, ang))
        _debris_imgs = out
    return _debris_imgs


# zombie 名 → [(lo, hi, fragment_count, [(img, angle), …]), …]
_DEATH_CACHE = {}


def _death_table(name):
    """解析 zombies/<name>.xml 的每个 <Death> 段。

    每段是：<Death last_min_damage last_max_damage fragment_count>
               <Box2DItem tex offset_x offset_y force_angle status/>
             </Death>
    贴图**逐僵尸独立**，绝不跨僵尸复用。
    """
    if name in _DEATH_CACHE:
        return _DEATH_CACHE[name]
    table = []
    txt = res.load_xml("zombies/%s.xml" % name) if name else None
    if txt:
        try:
            root = ET.fromstring(txt)
        except Exception:
            root = None
        if root is not None:
            for dd in root.iter("Death"):
                try:
                    fc = int(dd.get("fragment_count") or 0)
                except Exception:
                    fc = 0
                lo = _num(dd.get("last_min_damage"), 0.0)
                hi = _num(dd.get("last_max_damage"), 1e9)
                items = []
                for it in dd.iter("Box2DItem"):
                    tex = it.get("tex")
                    if not tex:
                        continue
                    im = res.load_img(tex)
                    if im is None:
                        continue
                    status = (it.get("status") or "unburned").lower()
                    if status == "burned":
                        # 烧焦版只在僵尸被烧死时用，平时丢掉
                        continue
                    items.append((im, _num(it.get("force_angle"), 90.0)))
                if items:
                    table.append((lo, hi, max(1, fc or len(items)), items))
    _DEATH_CACHE[name] = table
    return table


def _num(v, d):
    try:
        return float(v)
    except Exception:
        return d


def spawn_death_debris(layer, screen_x, ground_y, last_damage=0, threshold=50, name=None):
    """僵尸死亡时炸出碎片（ZombieCharacter 的 <Death> + Box2DItem）。

    · 按 last_damage 选中该僵尸对应的那一档（1..50 轻档 / 51.. 重档）；
    · 拼图只用**这只僵尸自己**的部件，抽 fragment_count 片；
    · 抽不到（XML 缺失）才退回通用血肉块池。
    """
    pool = []
    cnt = 0
    for lo, hi, fc, items in _death_table(name):
        if lo <= last_damage <= hi:
            pool, cnt = items, fc
            break
    if not pool:
        for _lo, hi, fc, items in _death_table(name):
            if last_damage <= hi:
                pool, cnt = items, fc
                break
    if not pool:
        pool = debris_images()
        cnt = max(1, (len(pool) + 1) // 2)
    if not pool:
        return
    picks = list(pool)
    random.shuffle(picks)
    for im, ang in picks[: max(1, cnt)]:
        layer.add_debris(
            [
                Debris(
                    im, screen_x, ground_y - 40, ang, ground_y, mass_scale=random.uniform(0.55, 1.0)
                )
            ]
        )
