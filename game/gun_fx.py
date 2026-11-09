"""开火特效 —— 枪口火光、弹道拖尾、弹壳。

原版数据来源：每把枪的 XML（assets/raw/weapon/<gun>.xml）里
`<weapon_effect>` 节点声明：

    <weapon_effect type="firearm" damage="25" shoot_distance="400" ...>
      <FireSpark  duration="0.07" offset_x="205" offset_y="170"
                  tex="pic/gun/ak47_fire_spark.png" />
      <BulletCase offset_x="143" offset_y="200"
                  tex="pic/gun/pistol_bulletcase.png" />
    </weapon_effect>

反编译依据（D:\\Code\\dsh\\full_dump\\all_merged.c）：

  WeaponEffect::addFireSparkEffect @0x19f508
      用 FireSparkDef 的 tex 建精灵，位置 = 武器节点的 (offset_x, offset_y)，
      播 FireSparkDef 的 duration 后移除。

  WeaponEffect::addBulletCaseEffect @0x19f808
      弹壳：从 (offset_x, offset_y) 抛出，带抛物线，落地消失。

  子弹拖尾 @0x1d2xxx（all_merged.c:114353）
      sub_1A0554(v47, "pic/gun/bullet_light.png");
      精灵 anchor = (1.0, 0.5)，opacity 0.45（1076964608 = 0.45f），
      水平飞过屏幕后淡出。
      bullet_light.png 223×31（单帧，不是网格动画）。

坐标换算：FireSpark 的 offset 是**武器节点局部坐标**（cocos，y 向上），
换算成屏幕：x = 士兵屏幕x + offset_x，y = 脚底y − offset_y。
"""

import math
import random
import xml.etree.ElementTree as ET

import pygame

from engine import res
from engine.skel import Skeleton


# ---------------------------------------------------------------------------
# 原版近战「刀光」= fire_upper 骨骼动画里那一帧的**武器贴图**
# ---------------------------------------------------------------------------
_MELEE_TEX_CACHE = {}


def melee_weapon_tex(gun, look=0):
    """取近战武器本体贴图（用来做挥砍特效，不再用 pygame.draw 画弧光）。

    近战枪的 <weapon_effect> 是空的，原版没有独立刀光贴图：
    SoldierCharacter::initCharacter 把 weapon/<gun>.xml 里
    `<animation name="fire_upper"><Flash sheet_xml=...>` 声明的
    upper_sheets 盖到通用骨架上，其中 zIndex 最低的 `gun_*.png`
    就是被甩出去的那把武器（例 katana → gun_katana.png）。
    """
    key = (gun, int(look or 0))
    if key in _MELEE_TEX_CACHE:
        return _MELEE_TEX_CACHE[key]
    out = None
    txt = res.load_xml("weapon/%s.xml" % gun)
    if txt:
        try:
            root = ET.fromstring(txt)
        except ET.ParseError:
            root = None
        if root is not None:
            for fl in root.iter("Flash"):
                sh = fl.get("sheet_xml") or ""
                if "upper_sheets" not in sh:
                    continue
                stxt = res.load_xml(sh)
                if not stxt:
                    continue
                try:
                    sroot = ET.fromstring(stxt)
                except ET.ParseError:
                    continue
                cand = []
                for tex in sroot.iter("Texture"):
                    p = tex.get("path") or ""
                    z = _f(tex.get("zIndex"), 99.0)
                    # 武器部件的 zIndex 各枪不同（katana 的 qiubang 是 1，
                    # axe 的 fuzi 是 7），不能按 z 过滤；只认 `gun_*.png`。
                    if "gun_" in p:
                        cand.append((0, z, p))
                    elif "gun" in p.lower():
                        cand.append((1, z, p))
                if cand:
                    cand.sort()
                    out = cand[0][2]
                    break
    # ★ 升级换形态：gun_katana_1.png / _2.png 才是手里新那把，
    #   特效也得跟着换（否则升级界面图变了、挥砍还是原始刀）。
    if out and look > 0:
        alt = "%s_%d.png" % (out[:-4], int(look))
        if res.load_img(alt) is not None:
            out = alt
    _MELEE_TEX_CACHE[key] = out
    return out


class WeaponSlash:
    """用**原版武器贴图**做的挥砍动画，左右朝向都正确。

    是绘制的就算了还只有向右攻击的特效」：
    - 不再用 pygame.draw 画几何弧光，改用 upper_sheets 里的武器贴图；
    - flip=True 时贴图水平镜像、弧线角度镜像 ⇒ 向左也有挥砍。
    """

    DURATION = 0.26

    def __init__(self, x, foot_y, reach, flip=False, img=None):
        self.x = x
        self.foot_y = foot_y
        self.reach = reach
        self.flip = flip
        self.t = 0.0
        self.img = img

    def update(self, dt):
        self.t += dt
        return self.t < self.DURATION

    def draw(self, s):
        if self.img is None:
            return
        k = max(0.0, min(1.0, self.t / self.DURATION))
        d = -1.0 if self.flip else 1.0
        src = self.img
        if self.flip:
            src = pygame.transform.flip(src, True, False)
        # 从身后上方甩到身前下方（对应 Flash 动画的 rotation 区间）
        a = -1.05 + 1.95 * k
        r = max(90.0, min(float(self.reach or 200.0), 260.0)) * 0.52
        px = self.x + d * (r * math.cos(a) * 0.72 + 30.0)
        py = self.foot_y - 116.0 - r * math.sin(a) * 0.66
        ang = -d * math.degrees(a) * 0.82
        im = pygame.transform.rotozoom(src, ang, 0.95).convert_alpha()
        im.set_alpha(int(255 * min(1.0, (1.0 - k) * 2.4)))
        s.blit(im, (int(px - im.get_width() / 2), int(py - im.get_height() / 2)))


# 枪口火光 / 弹壳 / 弹道的贴图（XML 里给的是完整路径）
FIRE_SPARK_FALLBACK = "pic/gun/ak47_fire_spark.png"
BULLET_LIGHT_TEX = "pic/gun/bullet_light.png"
# 泡泡存活秒数（Bubble::onUpdate：飞出屏幕或命中僵尸才消失，
# 这里给一个兜底寿命，免得飘出世界后一直留着）
BUBBLE_LIFE = 1.6

# 各枪的特效配置：{枪名: {duration, offset_x, offset_y, tex, case_tex, ...}}
_config_cache = {}


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def gun_effect_config(gun):
    """解析 weapon/<gun>.xml 里的 FireSpark / BulletCase 配置。"""
    key = gun or "p220"
    if key in _config_cache:
        return _config_cache[key]
    cfg = {
        "spark": None,
        "case": None,
        "type": "firearm",
        "shoot_distance": 400,
        "damage": 25,
        # ★ area_damage / delay / shotback_dis / bomb_radius：
        #   原版 WeaponEffectDef::setWeapon @0x1a2c3c 解析的字段
        #   （+20 area_damage(bool)、+16 delay(float)、+24 shotback_dis、
        #     +12 bomb_radius(int)）。
        #   近战武器（katana / axe / wrench / guitar / laser_sword / saw）
        #   area_damage=1 且 shoot_distance 只有 210~220。
        #   bomb_radius：爆炸类武器的溅射半径（rock / milkor_mgl），
        #   反编译 all_merged.c:115542 写的是
        #     *(int *)(v11 + 12) = atoi(...) * s_fLogicUnitLen;
        "area_damage": 0,
        "delay": 0.0,
        "shotback_dis": 0,
        "bomb_radius": 0,
    }
    txt = res.load_xml("weapon/%s.xml" % key)
    if txt:
        try:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(txt)
        except Exception:
            root = None
        if root is not None:
            node = root if root.tag == "soldier" else root.find("soldier")
            if node is None:
                node = root
            we = node.find("weapon_effect")
            if we is not None:
                cfg["type"] = we.get("type") or cfg["type"]
                cfg["shoot_distance"] = _f(we.get("shoot_distance"), cfg["shoot_distance"])
                cfg["damage"] = _f(we.get("damage"), cfg["damage"])
                cfg["area_damage"] = _f(we.get("area_damage"), 0)
                cfg["bomb_radius"] = _f(we.get("bomb_radius"), 0)
                cfg["delay"] = _f(we.get("delay"), 0.0)
                cfg["shotback_dis"] = _f(we.get("shotback_dis"), 0)
                # 同名节点可有多组：双炮口和双弹壳不能只取第一组。
                cfg["sparks"] = [
                    dict(
                        duration=_f(n.get("duration"), 0.08),
                        delay=_f(n.get("delay"), 0.0),
                        offset_x=_f(n.get("offset_x")),
                        offset_y=_f(n.get("offset_y")),
                        tex=n.get("tex"),
                        row_count=int(_f(n.get("row_count"), 1) or 1),
                        col_count=int(_f(n.get("col_count"), 1) or 1),
                        scale=_f(n.get("scale"), 1.0),
                    )
                    for n in we.findall("FireSpark")
                    if n.get("tex")
                ]
                cfg["cases"] = [
                    dict(
                        offset_x=_f(n.get("offset_x")),
                        offset_y=_f(n.get("offset_y")),
                        rot_speed=_f(n.get("rot_speed"), 180),
                        tex=n.get("tex"),
                    )
                    for n in we.findall("BulletCase")
                    if n.get("tex")
                ]
                fs = we.find("FireSpark")
                if fs is not None and fs.get("tex"):
                    cfg["spark"] = dict(
                        duration=_f(fs.get("duration"), 0.08),
                        offset_x=_f(fs.get("offset_x")),
                        offset_y=_f(fs.get("offset_y")),
                        tex=fs.get("tex"),
                        # ★ FireSparkDef（反编译 all_merged.c:115…）是**网格动画**：
                        #   帧宽 = texW / col_count，帧高 = texH / row_count
                        #   （EzSprite::animationWithResName）。
                        row_count=int(_f(fs.get("row_count"), 1) or 1),
                        col_count=int(_f(fs.get("col_count"), 1) or 1),
                        scale=_f(fs.get("scale"), 1.0),
                    )
                bc = we.find("BulletCase")
                if bc is not None and bc.get("tex"):
                    cfg["case"] = dict(
                        offset_x=_f(bc.get("offset_x")),
                        offset_y=_f(bc.get("offset_y")),
                        tex=bc.get("tex"),
                    )
                # ★ 其余武器专属特效节点（原版 WeaponEffect::onStartFire
                #   里逐类 addXXXEffect）
                ff = we.find("FireFlame")
                if ff is not None and ff.get("tex"):
                    cfg["flame"] = dict(
                        duration=_f(ff.get("duration"), 0.25),
                        offset_x=_f(ff.get("offset_x")),
                        offset_y=_f(ff.get("offset_y")),
                        row_count=int(_f(ff.get("row_count"), 1)),
                        col_count=int(_f(ff.get("col_count"), 1)),
                        tex=ff.get("tex"),
                    )
                fw = we.find("FreezerWave")
                if fw is not None and fw.get("tex"):
                    cfg["freezer"] = dict(
                        duration=_f(fw.get("duration"), 0.3),
                        offset_x=_f(fw.get("offset_x")),
                        offset_y=_f(fw.get("offset_y")),
                        row_count=int(_f(fw.get("row_count"), 1)),
                        col_count=int(_f(fw.get("col_count"), 1)),
                        tex=fw.get("tex"),
                    )
                ll = we.find("laser_light")
                if ll is not None:
                    cfg["laser"] = dict(
                        offset_x=_f(ll.get("offset_x")),
                        offset_y=_f(ll.get("offset_y")),
                        point0=ll.get("laser_point_0", ""),
                        point1=ll.get("laser_point_1", ""),
                        line0=ll.get("laser_line_0", ""),
                        line1=ll.get("laser_line_1", ""),
                    )
                sw = we.find("SubsonicWave")
                if sw is not None:
                    cfg["sonic"] = dict(
                        offset_x=_f(sw.get("offset_x")),
                        offset_y=_f(sw.get("offset_y")),
                        interval_x=_f(sw.get("interval_x"), 23.0),
                    )
                tf = we.find("ThunderFlash")
                if tf is not None:
                    cfg["thunder"] = dict(
                        offset_x=_f(tf.get("offset_x")),
                        offset_y=_f(tf.get("offset_y")),
                    )
                wh = we.find("Warhead")
                if wh is not None and wh.get("tex"):
                    cfg["warhead"] = dict(
                        offset_x=_f(wh.get("offset_x")),
                        offset_y=_f(wh.get("offset_y")),
                        speed=_f(wh.get("speed"), 25.0),
                        wtype=wh.get("type", "rocket"),
                        tex=wh.get("tex"),
                    )
                be = we.find("bomb_effect")
                if be is not None:
                    cfg["bomb"] = dict(
                        width=_f(be.get("width"), 500.0),
                        height=_f(be.get("height"), 500.0),
                        center_x=_f(be.get("centerX"), 250.0),
                        center_y=_f(be.get("centerY"), 360.0),
                        scale=_f(be.get("scale"), 1.0),
                        duration=_f(be.get("duration"), 0.7),
                        sheet_xml=be.get("sheet_xml", ""),
                        anim_xml=be.get("animatioin_xml", ""),
                    )
                mf = we.find("MultipleFire")
                if mf is not None:
                    delays = []
                    for tok in (mf.get("delays") or "").split(","):
                        tok = tok.strip().rstrip("f")
                        if tok:
                            delays.append(_f(tok, 0.0))
                    cfg["multi"] = dict(delays=delays)
    _config_cache[key] = cfg
    return cfg


def is_melee(gun):
    """这把武器是不是近战（挥砍）武器。

    判据来自原版武器 XML：area_damage=1 且没有 FireSpark/BulletCase 节点。
    近战武器（katana / axe / wrench / guitar / laser_sword / saw）的
    weapon_effect 是空的 —— 原版它们既不喷枪口火光也不扔弹壳，
    视觉完全靠上半身骨骼的挥砍动画（<Flash> 里的 fire_upper）。

    """
    cfg = gun_effect_config(gun)
    if not cfg.get("area_damage"):
        return False
    if cfg.get("spark") or cfg.get("case"):
        return False
    # ★ 还要看射程：近战武器 shoot_distance 只有 210~220。
    #   flamethrower（340）/ freezer（480）/ sonic（900）也是 area_damage=1，
    #   但它们是喷射/波纹/音波，不是挥砍。
    d = float(cfg.get("shoot_distance") or 0)
    return 0 < d <= 260


# ------------------------------------------------------------------ 枪口火光


class MuzzleFlash:
    """枪口火光：一次性贴图，duration 后消失（可带缩放脉冲）。"""

    def __init__(self, img, x, y, duration=0.08, flip=False):
        self.img = img
        self.x = x
        self.y = y
        self.t = 0.0
        self.duration = max(0.01, duration)
        self.flip = flip

    def update(self, dt):
        self.t += dt
        return self.t < self.duration

    def draw(self, s):
        if self.img is None:
            return
        # 火光在寿命期内从 1.25 缩到 0.9 并淡出
        k = self.t / self.duration
        scale = 1.25 - 0.35 * k
        w = max(1, int(round(self.img.get_width() * scale)))
        h = max(1, int(round(self.img.get_height() * scale)))
        im = pygame.transform.smoothscale(self.img, (w, h))
        if self.flip:
            im = pygame.transform.flip(im, True, False)
        im = im.copy()
        alpha = int(255 * (1.0 - k * k))
        im.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
        s.blit(im, (int(self.x - im.get_width() / 2), int(self.y - im.get_height() / 2)))


# ------------------------------------------------------------------ 弹道拖尾


class BulletTrail:
    """子弹拖尾：一条水平的黄色光带，从枪口飞向目标。

    原版用 pic/gun/bullet_light.png（223×31，anchor(1.0,0.5)，
    opacity 0.45），水平飞过屏幕后淡出。
    """

    def __init__(
        self, x, y, vx, img=None, life=0.12, flip=False, color=None, scale=1.0, alpha0=0.45
    ):
        self.x = x
        self.y = y
        self.vx = vx
        self.t = 0.0
        self.life = life
        self.flip = flip
        self.color = color  # (r,g,b) 染色：机甲按武器换弹道颜色
        self.scale = scale  # 1.0 = 原版 223×31 光带；机甲弹道可以更细
        self.alpha0 = alpha0  # 原版 0.45；机甲弹道要更亮才看得出来
        self.img = img if img is not None else res.load_img(BULLET_LIGHT_TEX)

    def update(self, dt):
        self.t += dt
        self.x += self.vx * dt
        return self.t < self.life

    def draw(self, s):
        if self.img is None:
            return
        k = self.t / self.life
        alpha = int(255 * self.alpha0 * (1.0 - k))
        if alpha <= 0:
            return
        im = self.img.copy()
        if self.scale != 1.0:
            if isinstance(self.scale, (tuple, list)):
                sx, sy = self.scale
            else:
                sx = sy = self.scale
            w = max(1, int(round(im.get_width() * sx)))
            h = max(1, int(round(im.get_height() * sy)))
            im = pygame.transform.smoothscale(im, (w, h))
        if self.color is not None:
            im.fill((*self.color, 255), special_flags=pygame.BLEND_RGBA_MULT)
        im.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
        # anchor(1.0, 0.5)：朝右时贴图右端对准 x，光带留在子弹后方。
        # 朝左飞必须把贴图镜像、改让左端对准 x，否则光带会横在子弹
        # 前方（原版靠翻转武器节点实现，复刻里得显式处理）。
        if self.flip:
            im = pygame.transform.flip(im, True, False)
            left = int(self.x)
        else:
            left = int(self.x - im.get_width())
        s.blit(im, (left, int(self.y - im.get_height() / 2)))


# ------------------------------------------------------------------ 弹壳


class BulletCase:
    """弹壳：抛出后落地弹跳两次，静止一会儿消失。"""

    def __init__(self, img, x, y, vx=180.0, vy=-260.0, flip=False):
        self.img = img
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.flip = flip
        self.t = 0.0
        self.ground_y = y
        self.bounces = 0
        self.done = False

    def update(self, dt, ground_y=None):
        if self.done:
            return False
        self.t += dt
        if ground_y is not None:
            self.ground_y = ground_y
        self.vy += 900.0 * dt  # 重力
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.y >= self.ground_y:
            self.y = self.ground_y
            self.bounces += 1
            self.vy = -abs(self.vy) * 0.35
            self.vx *= 0.55
            if self.bounces >= 2 or abs(self.vy) < 40:
                self.done = True
        if self.t > 2.5:
            self.done = True
        return not self.done

    def draw(self, s):
        if self.img is None:
            return
        im = self.img
        if self.flip:
            im = pygame.transform.flip(im, True, False)
        s.blit(im, (int(self.x - im.get_width() / 2), int(self.y - im.get_height() / 2)))


# ------------------------------------------------------------------ 挥砍弧光


class MeleeSlash:
    """近战挥砍的弧光。

    原版近战武器的 <weapon_effect> 是空的 —— 砍中时的反馈只有
    上半身骨骼的挥砍动画 + 命中血光，没有独立的刀光贴图
    （pic/gun/flash.png 是电击武器的电弧，用在刀上是错的）。

    这里自己画一道弧：起手淡 → 中段最亮 → 收尾淡出，
    弧线从士兵身前往 shoot_distance 处扫过，标出攻击范围。
    """

    DURATION = 0.22

    def __init__(self, x, foot_y, reach, flip=False, color=(225, 245, 255)):
        self.x = x
        self.foot_y = foot_y
        self.reach = reach
        self.flip = flip
        self.color = color
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        return self.t < self.DURATION

    def draw(self, s):
        """以士兵为圆心、身前的挥砍轨迹圆弧。

        画法 = **完整轨迹**（从水平扫到斜上 70°）+ **亮头部随时间推进**：
        头部最亮最粗，尾部渐隐渐细。挥砍是一瞬间的动作，如果从头画起，
        玩家只会看到一根慢慢长出来的短线，完全没有「挥」的感觉。
        """
        k = self.t / self.DURATION
        # 亮度：起手淡 → 中段亮 → 收尾淡
        if k < 0.22:
            alpha = int(225 * (k / 0.22))
        else:
            alpha = int(225 * (1.0 - (k - 0.22) / 0.78) ** 1.25)
        if alpha <= 6:
            return
        cx = self.x
        cy = self.foot_y - 120.0  # 圆心：腰到胸
        r = max(70.0, self.reach * 0.92)
        dirn = -1.0 if self.flip else 1.0
        a0 = 0.0  # 正前方（水平）
        a1 = 1.15  # 斜上 66°
        head = a0 + (a1 - a0) * min(1.0, k * 1.9)  # 亮头部推进

        def point(a):
            aa = dirn * a
            return (cx + math.cos(aa) * r, cy - math.sin(aa) * r * 0.72)

        steps = 24
        pts = []
        for i in range(steps + 1):
            a = a0 + (a1 - a0) * i / float(steps)
            pts.append(point(a))

        # 外发光：整条轨迹，粗而淡
        glow = pygame.Surface((s.get_width(), s.get_height()), pygame.SRCALPHA)
        for i in range(steps):
            t1 = (i + 1) / float(steps)
            # 亮头部之后的部分几乎全暗
            fade = 1.0 if t1 <= head else max(0.0, 1.0 - (t1 - head) * 3.2)
            if fade <= 0.02:
                continue
            ga = int(alpha * 0.26 * fade)
            if ga > 3:
                pygame.draw.line(
                    glow,
                    (self.color[0], self.color[1], self.color[2], ga),
                    (int(pts[i][0]), int(pts[i][1])),
                    (int(pts[i + 1][0]), int(pts[i + 1][1])),
                    22,
                )
        s.blit(glow, (0, 0))

        # 主弧：亮头部最亮最粗，尾部渐隐
        surf = pygame.Surface((s.get_width(), s.get_height()), pygame.SRCALPHA)
        for i in range(steps):
            t1 = (i + 1) / float(steps)
            fade = 1.0 if t1 <= head else max(0.0, 1.0 - (t1 - head) * 3.2)
            if fade <= 0.02:
                continue
            sa = int(alpha * fade)
            if sa > 4:
                wdt = max(3, int(14 * fade))
                pygame.draw.line(
                    surf,
                    (self.color[0], self.color[1], self.color[2], sa),
                    (int(pts[i][0]), int(pts[i][1])),
                    (int(pts[i + 1][0]), int(pts[i + 1][1])),
                    wdt,
                )
        s.blit(surf, (0, 0))


# ------------------------------------------------------------------ 网格动画


class GridAnim:
    """多帧网格动画（火花 / 火焰 / 冰冻波 / 弹壳用不到）。

    原版 FireSparkDef：帧宽 = texW / col_count，帧高 = texH / row_count
    （EzSprite::animationWithResName），按 duration 播完就移除。
    """

    def __init__(
        self,
        img,
        row_count,
        col_count,
        x,
        y,
        duration=0.25,
        scale=1.0,
        flip=False,
        vx=0.0,
        max_frames=0,
    ):
        self.img = img
        self.rows = max(1, row_count)
        self.cols = max(1, col_count)
        # 只播前 max_frames 帧（机甲炮口只想要爆闪段，不要后面的浓烟）
        self.max_frames = max(0, int(max_frames or 0))
        self.x = x
        self.y = y
        self.duration = max(0.02, duration)
        self.scale = scale
        self.flip = flip
        self.vx = vx
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        self.x += self.vx * dt
        return self.t < self.duration

    def draw(self, s):
        if self.img is None:
            return
        fw = self.img.get_width() // self.cols
        fh = self.img.get_height() // self.rows
        if fw <= 0 or fh <= 0:
            return
        # 部分原图高度不是行数的整数倍（317/3、395/3）。按每行真实
        # 比例取边界，余数分配到各行，不能统一向下取整后改变帧比例。
        x_bounds = [round(i * self.img.get_width() / self.cols) for i in range(self.cols + 1)]
        y_bounds = [round(i * self.img.get_height() / self.rows) for i in range(self.rows + 1)]
        n = self.rows * self.cols
        if self.max_frames:
            n = min(n, self.max_frames)
        idx = int((self.t / self.duration) * n)
        if idx >= n:
            idx = n - 1
        cx = idx % self.cols
        cy = idx // self.cols
        frame = self.img.subsurface(
            pygame.Rect(
                x_bounds[cx],
                y_bounds[cy],
                x_bounds[cx + 1] - x_bounds[cx],
                y_bounds[cy + 1] - y_bounds[cy],
            )
        )
        w = max(1, round(frame.get_width() * self.scale))
        h = max(1, round(frame.get_height() * self.scale))
        if (w, h) == frame.get_size():
            im = frame
        else:
            im = pygame.transform.smoothscale(frame, (w, h))
        if self.flip:
            im = pygame.transform.flip(im, True, False)
        s.blit(im, (int(self.x - w / 2), int(self.y - h / 2)))


# ------------------------------------------------------------------ 激光 / 音波 / 雷


class LaserBeam:
    """激光（laser）：横贯屏幕的光带 + 两端光柱。

    反编译 WeaponEffect::addLaserLightEffect @0x113404：
        v8  = laser_point_0.png   v10 = laser_point_1.png
        v44 = laser_line_0.png    v45 = laser_line_1.png
        · 朝右（a4==1）：v8/v10 的 anchor=(0, 0.5)，x = 枪口x + offset_x
        · 朝左       ：anchor=(1, 0.5)，x = 屏幕宽 − (枪口x+offset_x − 屏幕宽)
        · 四个图**同一个位置**（v54 = (v15, 枪口y − offset_y)）
        · setScaleX(v43)，v43 = 屏幕宽 / v10.contentSize.w
          ⇒ **横向拉满整个屏幕**，不是「枪口连到目标」的一条短线
        · 再跑 ScaleTo(0.15s, v43, 1.25) → ScaleTo(0.15s, v43, 1.0)
          做一次纵向的「撑开再收回」脉冲
        · laser_point_0 与 _1、line_0 与 _1 是**两套交替的贴图**，
          各自挂 1001/1002/1003/1004 的 tag，播完 removeFromParent

      纵向没有撑开的脉冲、也没拉满屏幕 ——
    """

    def __init__(self, x, y, end_x, cfg, flip=False):
        self.x = x
        self.y = y
        # 原版不看目标位置，直接把光带拉满整屏；
        # end_x 仅用于决定方向（朝右/朝左）
        self.end_x = end_x
        self.cfg = cfg
        self.flip = flip
        self.t = 0.0
        self.duration = 0.30  # 两个 ScaleTo 各 0.15s

    def update(self, dt):
        self.t += dt
        return self.t < self.duration

    def draw(self, s):
        # ★ 贴图职责（原版 WeaponEffect::addLaserLightEffect @0x113404）：
        #     laser_point_0/1  136×136 / 90×90   → **两端的光斑**，不缩放
        #     laser_line_0/1   20×128 / 20×36    → **横贯全屏的光带**，
        #                                          用 setScaleX(屏幕宽 / point_1.w)
        #                                          横向拉满
        p0 = res.load_img(self.cfg.get("point0") or "")
        p1 = res.load_img(self.cfg.get("point1") or "")
        l0 = res.load_img(self.cfg.get("line0") or "")
        l1 = res.load_img(self.cfg.get("line1") or "")
        if not (p0 or p1 or l0 or l1):
            return
        # 脉冲：纵向 1.0 → 1.25 → 1.0（原版 CCScaleTo 序列）
        k = self.t / self.duration
        if k <= 0.5:
            pulse = 1.0 + 0.25 * (k / 0.5)
        else:
            pulse = 1.25 - 0.25 * ((k - 0.5) / 0.5)
        alt = (int(self.t * 20) % 2) == 1
        # ---- 横贯全屏的光带：用 line 图，scaleX = 屏宽 / point_1 宽 ----
        # 原版：v43 = 屏幕宽 / v10.contentSize.w（v10 是 point_1），
        #       v44/v45（line_0/line_1）setScaleX(v43)
        line = (l1 if alt else l0) or l0 or l1
        sw = s.get_width()
        if line is not None:
            # ★ 光带必须**从枪口**朝开火方向铺出去。早先固定 blit 在
            #   x=0，宽度又只有 20*(854/90)≈190px ⇒ 激光从屏幕最左边
            #   冒出来一截，跟枪口差几百像素，朝左打时方向还反着
            if self.flip:
                bx, w = 0, max(1, int(self.x))
            else:
                bx, w = int(self.x), max(1, sw - int(self.x))
            h = max(1, int(round(line.get_height() * pulse)))
            im = pygame.transform.smoothscale(line, (w, h))
            if self.flip:
                im = pygame.transform.flip(im, True, False)
            s.blit(im, (bx, int(self.y - h / 2)))
        # ---- 枪口光斑：原版四个图挂在**同一个位置**（v54 = 枪口），
        #      不是「枪口 + 目标」各一个；目标身上凭空冒光斑是错的。
        dot = (p1 if alt else p0) or p0 or p1
        if dot is not None and self.x is not None:
            cx = int(self.x - dot.get_width() / 2)
            cy = int(self.y - dot.get_height() / 2)
            s.blit(dot, (cx, cy))


class SonicWave:
    # 音波（sonic）—— 原版 WeaponEffect::addSubsonicWaveEffect @0x114025。
    # 原版加载 pic/gun/ship_light/sheets.xml + animations.xml（21 帧骨骼），
    # 沿 X 轴生成 10 个节点，间隔 interval_x，scale 从 1.0 递增到 1.15，
    # 间隔 0.03s 依次启动。

    COUNT = 10
    STAGGER = 0.03

    def __init__(self, x, y, cfg, end_x=None, flip=False):
        self.x = x
        self.y = y
        self.cfg = cfg
        self.end_x = end_x if end_x is not None else x + 900.0
        self.flip = flip
        self.t = 0.0
        self.duration = self.STAGGER * self.COUNT + 0.5
        self.sk = _ship_light_skeleton()
        self.interval = float(cfg.get("interval_x") or 23.0)

    def update(self, dt):
        self.t += dt
        return self.t < self.duration

    def draw(self, s):
        sk = self.sk
        if sk is None or sk.frame_count <= 0:
            return
        d = -1.0 if self.flip else 1.0
        for i in range(self.COUNT):
            t0 = self.t - i * self.STAGGER
            if t0 < 0:
                continue
            sc = 1.0 + 0.15 * (i / float(max(1, self.COUNT - 1)))
            px = int(self.x + d * self.interval * i)
            frame = int((t0 * 20.0) % sk.frame_count)
            sk.render(s, frame, px, int(self.y), sc, flip=self.flip)


_ship_skel = None
_ship_failed = False


def _ship_light_skeleton():
    # pic/gun/ship_light/ —— 原版音波的骨骼动画（21 帧）
    global _ship_skel, _ship_failed
    if _ship_skel is None and not _ship_failed:
        try:
            sk = Skeleton(["pic/gun/ship_light/sheets.xml"], "pic/gun/ship_light/animations.xml")
            if sk and sk.frame_count > 0:
                _ship_skel = sk
            else:
                _ship_failed = True
        except Exception:
            _ship_failed = True
    return _ship_skel


class ThunderFlash:
    # 雷击（thunder）—— 原版 WeaponEffect::addThunderFlashEffect @0x114192。
    # 原版加载 pic/gun/flash.png（200×320）做横向拉伸 + 0.2s 淡入。
    # 画随机折线，完全不是原版素材。

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.t = 0.0
        self.duration = 0.2
        self.img = res.load_img("pic/gun/flash.png")

    def update(self, dt):
        self.t += dt
        return self.t < self.duration

    def draw(self, s):
        if self.img is None:
            return
        k = self.t / self.duration
        a = int(255 * (1.0 - k))
        if a <= 5:
            return
        # 原版：横向拉到「屏幕宽 * 0.5」或「中心 ±10%」里较大的那个，再 ×1.3
        im = self.img.copy()
        im.set_alpha(a)
        s.blit(im, (int(self.x - im.get_width() / 2), int(self.y - im.get_height())))


class Warhead:
    """弹头（rocket / grenade / bubble）：飞出去的弹头。

    ★ 三种类型行为完全不同（反编译 WeaponEffect::addWarheadEffect @0x113725）：
        "grenade" → Grenade::node   抛物线 + 落地爆炸
        "rocket"  → Rocket::node    直飞 + 命中爆炸
        "bubble"  → Bubble::node    **水平慢飞、不受重力、不落地爆炸**
                                    （Bubble 有 Box2D 物理体，creatPhysicalBody
                                     里把重力设成 0，碰到僵尸才消失）
      泡泡枪打出去是一个往下掉的泡泡、砸地上炸开
      和武器的性能很多都有问题」）。
    """

    def __init__(self, img, x, y, speed, cfg, flip=False, damage=None, on_hit=None):
        self.img = img
        self.x = x
        self.y = y
        self.spawn_y = y  # 发射高度：泡泡 / 火箭都按它走，不落到地面
        self.cfg = cfg
        self.flip = flip
        self.t = 0.0
        self.ground_y = y
        self.done = False
        self.boom_t = -1.0
        self.boom = None
        self.radius = float(cfg.get("bomb_radius") or 0.0)
        self.target_x = cfg.get("target_x")
        if cfg.get("wtype") == "bubble":
            self.speed = 150.0  # 泡泡：慢慢飘（用户明确要求「慢慢移动」）
        elif cfg.get("wtype") == "grenade":
            self.speed = 0.0  # 榴弹：抛物线，初速在 update 里算
        else:
            self.speed = 900.0  # 火箭：直冲
        self.vx = 0.0
        self.vy = 0.0
        self.gravity = 0.0
        self._launched = False
        # ★ 泡泡：水平飞、不下坠、不爆炸（Bubble::creatPhysicalBody 设的
        #   垂直速度就是 0，重力不生效），只在飞出屏幕或碰到僵尸时消失。
        self.is_bubble = cfg.get("wtype") == "bubble"
        self.is_grenade = cfg.get("wtype") == "grenade"
        self.is_rocket = cfg.get("wtype") == "rocket"
        self.is_bullet = cfg.get("wtype") == "bullet"
        if self.is_bullet:
            self.speed = float(cfg.get("speed") or 2200.0)
        # 命中判定半径：子弹小、爆炸弹头大（GunFxLayer.update 用）
        self.hit_radius = 34.0 if self.is_bubble else (26.0 if self.is_bullet else 42.0)
        self.life = BUBBLE_LIFE if self.is_bubble else 0.0
        # ★ 弹头类武器（泡泡枪 / 火箭 / 榴弹）的伤害必须**命中僵尸才结算**。
        #   开火瞬间不扣血，等这个弹头真的飞到僵尸身上再回调 Battle
        self.damage = float(damage or 0.0)
        self.on_hit = on_hit
        self.on_boom = cfg.get("on_boom")
        self.direct = None  # 被弹头直接撞上的那只（溅射要排除它）

    def hit(self, z):
        """弹头撞上僵尸：先回调结算伤害，再按类型消失 / 爆炸。"""
        if self.done or self.boom_t >= 0:
            return False
        self.direct = z
        if self.on_hit is not None:
            self.on_hit(self, z)
        if self.is_bubble or self.is_bullet:
            # 原版 Bubble 碰到僵尸只是消失，不爆炸；子弹同理（命中即消失）
            self.done = True
        else:
            self.explode_now()
        return True

    def update(self, dt, ground_y=None):
        if self.boom_t >= 0:
            self.boom_t += dt
            if self.boom is not None:
                self.boom.update(dt)
            if self.boom_t > 0.7:
                self.done = True
            return not self.done
        self.t += dt
        if ground_y is not None:
            self.ground_y = ground_y
        d = -1.0 if self.flip else 1.0
        if self.is_bubble:
            # 泡泡：只往前走，y 保持在**发射高度**附近轻微上下飘（不下坠）
            self.x += d * self.speed * dt
            self.y = self.spawn_y + math.sin(self.t * 6.0) * 6.0
            self.life -= dt
            if self.life <= 0:
                self.done = True
            return not self.done
        if self.is_bullet:
            # 子弹：直线飞，命中由 GunFxLayer 判定；飞出屏幕就消失
            self.x += d * self.speed * dt
            if self.x < -160.0 or self.x > 1010.0:
                self.done = True
            return not self.done
        if self.is_grenade:
            if not self._launched:
                self._launched = True
                drop = max(20.0, self.ground_y - self.y)
                vy0 = -230.0
                g = 640.0
                disc = vy0 * vy0 + 2.0 * g * drop
                tt = (-vy0 + math.sqrt(max(0.0, disc))) / g
                tt = max(0.30, min(1.6, tt))
                dist = 360.0
                if self.target_x is not None:
                    dist = abs(float(self.target_x) - self.x)
                dist = max(150.0, min(820.0, dist))
                self.vx = d * dist / tt
                self.vy = vy0
                self.gravity = g
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.vy += self.gravity * dt
            if self.y >= self.ground_y:
                self.y = self.ground_y
                self.explode_now()
            return not self.done
        self.x += d * self.speed * dt
        if self.is_rocket:
            # 火箭贴地高度不变，直接飞向目标；碰到僵尸由 Battle 判定
            if self.x < -120 or self.x > 974:
                self.done = True
            return not self.done
        return not self.done

    def explode_now(self):
        # 命中僵尸 / 榴弹落地时调用（只结算一次）
        if self.boom_t < 0:
            self.boom_t = 0.0
            self.boom = _bomb_boom(self.x, self.y, self.cfg.get("bomb_cfg"))
            if self.on_boom is not None:
                self.on_boom(self)

    def draw(self, s):
        if self.img is None:
            return
        if self.boom_t < 0:
            s.blit(
                self.img,
                (int(self.x - self.img.get_width() / 2), int(self.y - self.img.get_height() / 2)),
            )
        elif self.boom is not None:
            self.boom.draw(s)


class BulletShot:
    """**实体子弹**：从枪口直线飞出，撞到僵尸身上才算击中。

    画面上弹道还停在半路、僵尸已经飙血倒地，看起来就是「隔着空气打死人」。
    现在这一发是一个真正的飞行物：
      · update 按 speed 直线推进，飞满射程 / 出屏才消失；
      · GunFxLayer.update 用「本帧扫过的区间」做命中判定（高速也不穿透）；
      · hit(z) 回调 Battle 结算伤害，然后自己销毁。
    接口与 Warhead 对齐（GunFxLayer 的命中循环直接复用）。
    """

    is_bubble = False
    is_bullet = True
    boom_t = -1.0

    def __init__(
        self,
        x,
        y,
        speed=2400.0,
        flip=False,
        damage=0.0,
        on_hit=None,
        color=None,
        scale=1.0,
        max_dist=900.0,
        hit_radius=26.0,
        target_y=None,
    ):
        self.x = float(x)
        self.y = float(y)
        self.speed = max(200.0, float(speed))
        self.vy = 0.0 if target_y is None else (float(target_y) - self.y) / (max_dist / self.speed)
        self.flip = flip
        self.damage = float(damage or 0.0)
        self.on_hit = on_hit
        self.color = color or (255, 238, 168)
        self.scale = max(0.2, float(scale))
        self.max_dist = max(40.0, float(max_dist))
        self.hit_radius = float(hit_radius)
        self.travelled = 0.0
        self.done = False
        self.boom = None
        self._trail = [(self.x, self.y)]

    def update(self, dt, ground_y=None):
        if self.done:
            return False
        d = -1.0 if self.flip else 1.0
        step = self.speed * dt
        self.x += d * step
        self.y += self.vy * dt
        self.travelled += step
        self._trail.append((self.x, self.y))
        if len(self._trail) > 5:
            self._trail.pop(0)
        if self.travelled >= self.max_dist or self.x < -160 or self.x > 1010:
            self.done = True
        return not self.done

    def hit(self, z):
        if self.done:
            return False
        if self.on_hit is not None:
            self.on_hit(self, z)
        self.done = True
        return True

    def draw(self, s):
        # 曳光：把最近几帧的位置连成一条渐细的光带
        n = len(self._trail)
        if n >= 2:
            for i in range(n - 1):
                w = max(1, int(5 * self.scale * (i + 1) / float(n)))
                pygame.draw.line(
                    s,
                    (self.color[0], self.color[1], self.color[2]),
                    (int(self._trail[i][0]), int(self._trail[i][1])),
                    (int(self._trail[i + 1][0]), int(self._trail[i + 1][1])),
                    w,
                )
        r = max(2, int(3.4 * self.scale))
        pygame.draw.circle(s, (255, 252, 214), (int(self.x), int(self.y)), r)
        pygame.draw.circle(s, self.color, (int(self.x), int(self.y)), max(1, r - 2))


class MechRocket:
    """机甲火箭弹：弹头 + 尾焰拖尾 + 命中爆炸（纯视觉，伤害由机甲即时结算）。

    ★ 机甲武器 XML 里没有 <Warhead> 节点，但用户明确要求
      「机甲武器要有子弹轨迹 / 每个机甲武器都有问题」——
      火箭类机甲（mech_1/4/5）打出来必须看得见弹头飞出去，
      而不是原地闪一下。
    接口与 Warhead 兼容（GunFxLayer.update 的命中循环直接用）。
    """

    is_bubble = False
    is_bullet = False
    hit_radius = 40.0

    def __init__(
        self,
        img,
        x,
        y,
        flip=False,
        scale=1.0,
        speed=760.0,
        boom_cfg=None,
        trail_img=None,
        damage=0.0,
        on_hit=None,
    ):
        self.img = img
        self.x = float(x)
        self.y = float(y)
        self.flip = flip
        self.scale = max(0.05, scale)
        self.speed = speed
        self.boom_cfg = boom_cfg
        self.boom = None
        self.boom_t = -1.0
        self.done = False
        self.trail_img = trail_img
        self.trail = []  # [(x, y, t, life)] 尾焰残影
        # ★ 命中才结算：火箭也要「打到僵尸身上才有伤害」
        self.damage = float(damage or 0.0)
        self.on_hit = on_hit
        self.direct = None

    def update(self, dt, ground_y=None):
        if self.boom_t >= 0:
            self.boom_t += dt
            boom_done = self.boom is None or not self.boom.update(dt)
            if boom_done:
                self.done = True
            return not self.done
        d = -1.0 if self.flip else 1.0
        self.x += d * self.speed * dt
        # 尾焰：每帧在当前弹尾位置留一段短光带
        self.trail.append((self.x - d * 26.0 * self.scale, self.y, 0.0, 0.28))
        self.trail = [(tx, ty, tt + dt, tl) for tx, ty, tt, tl in self.trail if tt + dt < tl]
        if self.x < -160 or self.x > 1010:
            self.done = True
        return not self.done

    def hit(self, z):
        if self.done or self.boom_t >= 0:
            return False
        self.direct = z
        if self.on_hit is not None:
            self.on_hit(self, z)
        self.explode_now()
        return True

    def explode_now(self):
        if self.boom_t < 0:
            self.boom_t = 0.0
            self.boom = _bomb_boom(self.x, self.y, self.boom_cfg)

    def draw(self, s):
        if self.img is None:
            return
        if self.boom_t >= 0:
            if self.boom is not None:
                self.boom.draw(s)
            return
        # 尾焰先画（在弹头后面）
        if self.trail_img is not None:
            for tx, ty, tt, tl in self.trail:
                k = tt / tl
                alpha = int(220 * (1.0 - k))
                if alpha <= 0:
                    continue
                im = self.trail_img.copy()
                w = max(1, int(im.get_width() * 0.42 * self.scale))
                h = max(1, int(im.get_height() * 0.5 * self.scale))
                im = pygame.transform.smoothscale(im, (w, h))
                im.fill((255, 168, 82, 255), special_flags=pygame.BLEND_RGBA_MULT)
                im.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
                if self.flip:
                    im = pygame.transform.flip(im, True, False)
                    left = int(tx)
                else:
                    left = int(tx - im.get_width())
                s.blit(im, (left, int(ty - im.get_height() / 2)))
        w = max(1, int(self.img.get_width() * self.scale))
        h = max(1, int(self.img.get_height() * self.scale))
        im = pygame.transform.smoothscale(self.img, (w, h))
        if self.flip:
            im = pygame.transform.flip(im, True, False)
        s.blit(im, (int(self.x - im.get_width() / 2), int(self.y - im.get_height() / 2)))


_bomb_skel = None
_bomb_failed = False


def _bomb_skeleton():
    """爆炸骨骼：pic/gun/bomb/sheets.xml + animations.xml（boom，31 帧）。"""
    global _bomb_skel, _bomb_failed
    if _bomb_skel is None and not _bomb_failed:
        try:
            sk = Skeleton(["pic/gun/bomb/sheets.xml"], "pic/gun/bomb/animations.xml")
            if sk and sk.frame_count > 0:
                _bomb_skel = sk
            else:
                _bomb_failed = True
        except Exception:
            _bomb_failed = True
    return _bomb_skel


class BombBoom:
    """爆炸（bomb_effect）：骨骼动画 boom，31 帧。"""

    def __init__(self, x, y, cfg=None):
        self.x = x
        self.y = y
        self.cfg = cfg or {}
        self.t = 0.0
        self.duration = float(self.cfg.get("duration", 0.7) or 0.7)
        self.scale = float(self.cfg.get("scale", 1.0) or 1.0)

    def update(self, dt):
        self.t += dt
        return self.t < self.duration

    def draw(self, s):
        sk = _bomb_skeleton()
        if sk is None:
            return
        k = min(1.0, self.t / max(0.05, self.duration))
        frame = int(k * (sk.frame_count - 1))
        sk.render(s, frame, int(self.x), int(self.y), self.scale, flip=False)


def _bomb_boom(x, y, cfg):
    return BombBoom(x, y, cfg)


# ------------------------------------------------------------------ 特效层


class GunFxLayer:
    """战斗里的开火特效集合。

    每一把武器的特效**完全由它的 XML 决定**（原版 WeaponEffect::onStartFire
    @0x1a1a30 → all_merged.c:114790）：
      FireSpark    枪口火光（网格动画）
      BulletCase   弹壳
      FireFlame    火焰喷射（喷火枪）
      FreezerWave  冰冻波（冰冻枪）
      laser_light  激光
      SubsonicWave 音波
      ThunderFlash 雷击
      Warhead      弹头（火箭筒 / 榴弹发射器）
      MultipleFire 多发连射
    """

    def __init__(self):
        self.flashes = []
        self.trails = []
        self.cases = []
        self.slashes = []
        self.grids = []  # 网格动画（火焰 / 冰冻波）
        self.lasers = []
        self.sonics = []
        self.thunders = []
        self.warheads = []
        self.booms = []  # 独立爆炸（机甲被击毁等，不挂在弹头上）

    def add_muzzle(self, gun, soldier_x, foot_y, flip=False):
        """在枪口位置生成火光。

        soldier_x/foot_y 是士兵在屏幕上的脚底位置；
        FireSpark 的 offset 是武器节点局部坐标（cocos，y 向上）。
        """
        cfg = gun_effect_config(gun)
        spark = cfg.get("spark")
        if not spark:
            return
        img = res.load_img(spark["tex"])
        if img is None:
            return
        x = soldier_x + spark["offset_x"]
        if flip:
            x = soldier_x - spark["offset_x"]
        y = foot_y - spark["offset_y"]
        self.flashes.append(MuzzleFlash(img, x, y, spark["duration"], flip))

    def add_muzzle_at(self, gun, x, y):
        # 在给定屏幕坐标生成枪口火光。
        # 原版用 XML 的 offset_x/offset_y 定位，不是骨骼部件位置：onStartFire
        # 里 v50 = offset_x + 武器节点坐标、v33 = 基准y − offset_y
        # （all_merged.c:113022-113026）。早先复刻改用骨骼 muzzle_point，
        # 现在火光/弹壳/专属特效统一按 XML offset，骨骼枪口只给弹道拖尾用。
        cfg = gun_effect_config(gun)
        spark = cfg.get("spark")
        if not spark:
            return
        img = res.load_img(spark["tex"])
        if img is None:
            return
        # 原版 FireSparkDef 是**网格动画**（row_count × col_count），
        # 帧宽 = texW / col_count。row/col 缺省时按单帧处理。
        rows = int(spark.get("row_count", 1) or 1)
        cols = int(spark.get("col_count", 1) or 1)
        if rows > 1 or cols > 1:
            self.grids.append(
                GridAnim(
                    img, rows, cols, x, y, spark["duration"], float(spark.get("scale", 1.0) or 1.0)
                )
            )
            return
        self.flashes.append(MuzzleFlash(img, x, y, spark["duration"]))

    def add_trail(self, x, y, vx=900.0, life=0.12, flip=False, color=None, scale=1.0, alpha0=0.45):
        self.trails.append(
            BulletTrail(x, y, vx, life=life, flip=flip, color=color, scale=scale, alpha0=alpha0)
        )

    def add_rocket_visual(
        self, x, y, flip=False, scale=1.0, speed=760.0, boom_cfg=None, damage=0.0, on_hit=None
    ):
        """机甲火箭弹：弹头 + 尾焰 + 命中爆炸（伤害在命中帧结算）。"""
        img = res.load_img("pic/gun/rocket_warhead.png")
        if img is None:
            return None
        rocket = MechRocket(
            img,
            x,
            y,
            flip=flip,
            scale=scale,
            speed=speed,
            boom_cfg=boom_cfg,
            trail_img=res.load_img(BULLET_LIGHT_TEX),
            damage=damage,
            on_hit=on_hit,
        )
        self.warheads.append(rocket)
        return rocket

    def add_bullet(
        self,
        x,
        y,
        speed=2400.0,
        flip=False,
        damage=0.0,
        on_hit=None,
        color=None,
        scale=1.0,
        max_dist=900.0,
        hit_radius=26.0,
        target_y=None,
    ):
        """实体子弹（命中僵尸才结算伤害），返回子弹对象供 Battle 记录。"""
        b = BulletShot(
            x,
            y,
            speed=speed,
            flip=flip,
            damage=damage,
            on_hit=on_hit,
            color=color,
            scale=scale,
            max_dist=max_dist,
            hit_radius=hit_radius,
            target_y=target_y,
        )
        self.warheads.append(b)
        return b

    def add_boom(self, x, y, cfg=None):
        """独立爆炸（不依附弹头）。"""
        self.booms.append(_bomb_boom(x, y, cfg))

    def add_case_at(self, gun, x, y, flip=False):
        """在**给定的枪膛屏幕坐标**抛弹壳。

        在居中重排的骨骼上落在枪口右上方 100px 的空气里，弹壳像从天上掉
        下来。现在调用方从 Skeleton.part_box 拿到枪身盒子，取后段中心。
        """
        cfg = gun_effect_config(gun)
        bc = cfg.get("case")
        if not bc:
            return
        img = res.load_img(bc["tex"])
        if img is None:
            return
        vx = -random.uniform(120.0, 220.0) if not flip else random.uniform(120.0, 220.0)
        self.cases.append(BulletCase(img, x, y, vx, -random.uniform(200.0, 320.0), flip))

    def add_case(self, gun, soldier_x, foot_y, flip=False):
        """兼容旧调用：按 XML offset 定位（已弃用，见 add_case_at）。"""
        cfg = gun_effect_config(gun)
        bc = cfg.get("case")
        if not bc:
            return
        x = soldier_x + bc["offset_x"]
        if flip:
            x = soldier_x - bc["offset_x"]
        self.add_case_at(gun, x, foot_y - bc["offset_y"], flip)

    def add_slash(self, x, foot_y, reach, flip=False, gun=None, look=0):
        """近战挥砍：用该武器 upper_sheets 里的**原版武器贴图**。

        gun 为空时才退回旧的代码弧光（兼容其它调用点）。
        look 是武器形态序号（升级到 _1/_2 时贴图跟着换）。
        """
        tex = melee_weapon_tex(gun, look) if gun else None
        img = res.load_img(tex) if tex else None
        if img is not None:
            self.slashes.append(WeaponSlash(x, foot_y, reach, flip, img))
        else:
            self.slashes.append(MeleeSlash(x, foot_y, reach, flip))

    def add_weapon_special(
        self,
        gun,
        x,
        y,
        soldier_x,
        foot_y,
        reach=900.0,
        flip=False,
        target_x=None,
        damage=None,
        on_hit=None,
        on_boom=None,
    ):
        """生成这把武器**专属**的特效。

        原版 WeaponEffect::onStartFire 里每种节点都有对应的 addXXXEffect，
        这里按 XML 里的节点逐类对应。

        ★ 参数 x/y 是**枪口屏幕坐标**（调用方已经算好，见
          Battle._spawn_gun_fx → muzzle_point）。XML 里的 offset_x/offset_y
          是「武器节点 → 特效节点」的**局部偏移**，原版把特效 addChild
          到武器节点上，所以还要再加一次这就是对的。

          但复刻的 muzzle_point 已经把 offset 折进枪口坐标了 ——
          喷火枪的火焰出现在士兵右侧 265px、上方 135px 的空气里
          现在统一：x/y 就是枪口的最终屏幕位置，不再叠加 offset_x/y，
          只用 offset 的**方向**决定翻转。

        target_x: 命中目标的屏幕 x。激光 / 音波 / 雷击都要落在**目标**上
        （原版是先算射程内僵尸，再把光束 / 雷接到那个位置），
        没有目标时才退回枪口方向。
        """
        cfg = gun_effect_config(gun)
        d = -1.0 if flip else 1.0
        # 火焰喷射（喷火枪）
        fl = cfg.get("flame")
        if fl:
            img = res.load_img(fl["tex"])
            if img:
                self.grids.append(
                    GridAnim(img, fl["row_count"], fl["col_count"], x, y, fl["duration"], 1.0, flip)
                )
        # 冰冻波（冰冻枪）
        fz = cfg.get("freezer")
        if fz:
            img = res.load_img(fz["tex"])
            if img:
                self.grids.append(
                    GridAnim(img, fz["row_count"], fz["col_count"], x, y, fz["duration"], 1.0, flip)
                )
        end_x = target_x if target_x is not None else (x + d * reach)
        # 激光：横贯全屏（LaserBeam 内部自己按屏幕宽拉伸）
        ls = cfg.get("laser")
        if ls:
            self.lasers.append(LaserBeam(x, y, end_x, ls, flip))
        # 音波
        sn = cfg.get("sonic")
        if sn:
            self.sonics.append(SonicWave(x, y, sn, end_x, flip))
        # 雷击：劈在目标头上（没有目标就劈在身前远处）
        th = cfg.get("thunder")
        if th:
            tx = target_x if target_x is not None else (x + d * reach * 0.8)
            self.thunders.append(ThunderFlash(tx, y))
        # 弹头（火箭筒 / 榴弹发射器）
        wh = cfg.get("warhead")
        if wh:
            img = res.load_img(wh["tex"])
            if img:
                wh = dict(wh)
                wh["bomb_cfg"] = cfg.get("bomb")
                # 榴弹的抛物线要按目标距离反解初速
                wh["target_x"] = target_x
                # 爆炸溅射半径（XML bomb_radius，rocket 450 / mgl 300）
                wh["bomb_radius"] = cfg.get("bomb_radius") or 0.0
                wh["on_boom"] = on_boom
                self.warheads.append(
                    Warhead(img, x, y, wh["speed"], wh, flip, damage=damage, on_hit=on_hit)
                )

    def update(self, dt, ground_y=None, zombies=None, cam=0.0):
        self.flashes = [f for f in self.flashes if f.update(dt)]
        self.trails = [t for t in self.trails if t.update(dt)]
        self.cases = [c for c in self.cases if c.update(dt, ground_y)]
        self.slashes = [s for s in self.slashes if s.update(dt)]
        self.grids = [g for g in self.grids if g.update(dt)]
        self.lasers = [lz for lz in self.lasers if lz.update(dt)]
        self.sonics = [s for s in self.sonics if s.update(dt)]
        self.thunders = [t for t in self.thunders if t.update(dt)]
        self.booms = [b for b in self.booms if b.update(dt)]
        # 火箭 / 子弹：原版 Rocket::onUpdate 只在**碰到僵尸**时结算。
        # 这里每帧检查弹头屏幕 x 是否越过僵尸屏幕 x，命中就当场结算。
        # ★ 子弹速度 2000+ px/s，一帧就飞 30~40px，低帧率时更远；
        #   只用「当前 x 距僵尸 < 半径」会**穿透**。所以用本帧要扫过的
        #   区间 [x, x+速度*dt] 和僵尸占位区间求交，并取路径上最近的那只。
        if zombies:
            for w in self.warheads:
                if w.done or w.boom_t >= 0:
                    continue
                rad = float(getattr(w, "hit_radius", 0.0) or (34.0 if w.is_bubble else 42.0))
                x0 = w.x
                if getattr(w, "is_bullet", False):
                    x1 = x0 + (-1.0 if w.flip else 1.0) * w.speed * dt
                else:
                    x1 = x0
                lo, hi = (x0, x1) if x0 <= x1 else (x1, x0)
                best = None
                for z in zombies:
                    if z.get("dead") or z.get("dying"):
                        continue
                    zx = z["x"] - cam
                    if zx < lo - rad or zx > hi + rad:
                        continue
                    dd = abs(zx - x0)
                    if best is None or dd < best[0]:
                        best = (dd, z)
                if best is not None:
                    w.hit(best[1])
        self.warheads = [w for w in self.warheads if w.update(dt, ground_y)]

    def draw(self, s):
        """弹道拖尾 + 弹壳 + 挥砍弧光（画在士兵下面）。"""
        for t in self.trails:
            t.draw(s)
        for c in self.cases:
            c.draw(s)
        for sl in self.slashes:
            sl.draw(s)
        for w in self.warheads:
            w.draw(s)
        for b in self.booms:
            b.draw(s)

    def draw_flash(self, s):
        """枪口火光 / 专属特效（画在士兵上面，避免被身体挡住）。"""
        for f in self.flashes:
            f.draw(s)
        for g in self.grids:
            g.draw(s)
        for lz in self.lasers:
            lz.draw(s)
        for sn in self.sonics:
            sn.draw(s)
        for t in self.thunders:
            t.draw(s)

    def clear(self):
        self.flashes.clear()
        self.trails.clear()
        self.cases.clear()
        self.slashes.clear()
        self.grids.clear()
        self.lasers.clear()
        self.sonics.clear()
        self.thunders.clear()
        self.warheads.clear()
        self.booms.clear()


# ---------------------------------------------- 机甲形态的特效坐标换算

MECH_NODE_SIZE = 350.0
"""level/mech_actors.xml: <soldier width="350" height="350" scale="1.0">。
FireSpark / BulletCase 的 offset 是这套 350×350 节点的局部坐标。"""


def mech_fx_point(off_x, off_y, render_x, foot_y, bbox, form_scale, dir_sign):
    """把机甲 XML 的 offset 换算成屏幕坐标（机甲形态专用）。

    复刻的机甲不是 350×350 的节点：weapon/mech_N.xml 骨骼 bbox 约
    235×247，渲染时还要乘 MECH_FORM_SCALE(0.78)，实际只有 183×193。
    早先把 offset 直接当屏幕像素加在士兵中心上 —— mech_1 的火光落在
    炮口外 165px 的空气里、弹壳飘在头顶、bullet_light 起点在天上

    bbox 取 stand 状态那一份（fire 已与它共用，见 battle_summons）；
    dir_sign = +1 朝右 / -1 朝左，镜像骨骼时特效跟着取反。
    """
    if bbox:
        kx = (bbox[2] - bbox[0]) * form_scale / MECH_NODE_SIZE
        ky = (bbox[3] - bbox[1]) * form_scale / MECH_NODE_SIZE
    else:
        kx = ky = form_scale
    return (render_x + dir_sign * float(off_x) * kx, foot_y - float(off_y) * ky)
