"""僵尸骨骼动画：为每种僵尸建立 Skeleton，按状态切换动画。

游戏里有 19 种普通僵尸（zombie_1..zombie_19）+ 4 个 boss。
每种僵尸的贴图目录是 pic/zombies/NN/，动画定义在各自的 XML 里。

状态：
  walk    走路（循环）
  attack  攻击（循环）
  death   死亡（播一次，然后倒地消失）
"""

import contextlib
import os
import xml.etree.ElementTree as ET

import pygame

from engine import res
from engine.skel import Skeleton, parse_anim, parse_sheet


# 动画名 → (sheet 列表, 动画 xml 路径)
# 从各僵尸的 XML 里读，不硬编码。
def _zombie_dir(name):
    """zombie_9 → "09"，zombie_19 → "19"，boss_1 → "01"（boss 用僵尸体型）"""
    num = name.split("_")[-1]
    try:
        n = int(num)
    except ValueError:
        n = 1
    if name.startswith("boss_"):
        # boss 的贴图在 pic/zombies/boss_NN/
        return "boss_%02d" % n
    return "%02d" % n


class ZombieSprite:
    """一种僵尸的全部动画状态。"""

    def __init__(self, name):
        self.name = name
        self.anims = {}  # state → (Skeleton, frame_count)
        self.scale = 1.0
        self._half_w = None
        self.durations = {}  # state → 播放一遍的秒数（XML duration）
        self.shadow = None  # 脚下影子：dict(tex, dx, dy)
        self.damage_swaps = []  # [(part, max_ratio, tex_path)] 按血量换部件贴图
        self._swap_cache = {}  # (part, tex_path) → Surface
        self._orig_images = {}  # 部件原始贴图（换过之后要还原）
        self._load()

    def _load(self):
        """按 zombies/<name>.xml 里的 <animation> 定义加载。

        每个 <animation name="walk_upper"> 可含多条 <Flash>（boss_4 是左右
        两套贴图叠加），每条给出 sheet_xml + animatioin_xml + zorder。
        同名的 walk_lower/stand_lower/death_lower 是下半身，一起并入。
        """
        txt = None
        for d in ("zombies", "config/zombies"):
            try:
                txt = res.load_xml("%s/%s.xml" % (d, self.name))
            except Exception:
                txt = None
            if txt:
                break
        if not txt:
            return
        try:
            root = ET.fromstring(txt)
        except ET.ParseError:
            return
        node = root if root.tag == "zombie" else root.find("zombie")
        if node is None:
            return

        # 掉血换部件贴图：<ChangeSprite sprite_name="tou" new_tex="..." max_blood_ratio="0.8" status="unburned"/>
        # 只在未燃烧状态生效（burned 那套被火烧时才用，这里不做燃烧）。
        for cs in node.findall("ChangeSprite"):
            if (cs.get("status") or "unburned") != "unburned":
                continue
            part = cs.get("sprite_name")
            tex = cs.get("new_tex")
            ratio = cs.get("max_blood_ratio")
            if not part or not tex or ratio is None:
                continue
            try:
                r = float(ratio)
            except ValueError:
                continue
            self.damage_swaps.append((part, r, tex))
        # 阈值从高到低，第一次命中就停（原版顺序应用，后面的覆盖前面的）
        self.damage_swaps.sort(key=lambda x: -x[1])

        # 脚下影子：<Shadow offset_x offset_y tex="pic/zombies/yinying.png"/>
        sh = node.find("Shadow")
        if sh is not None and sh.get("tex"):
            self.shadow = dict(
                tex=sh.get("tex"),
                dx=float(sh.get("offset_x") or 0),
                dy=float(sh.get("offset_y") or 0),
            )

        # state → [(sheet_xml, anim_xml, zorder)]
        groups = {"walk": [], "attack": [], "death": []}
        for anim in node.findall("animation"):
            aname = anim.get("name") or ""
            if aname.startswith("walk"):
                st = "walk"
            elif aname.startswith(("attack", "stand")):
                st = "attack"
            elif aname.startswith("death"):
                st = "death"
            else:
                continue
            dur = anim.get("duration")
            if dur:
                with contextlib.suppress(ValueError):
                    self.durations[st] = float(dur)
            for fl in anim.findall("Flash"):
                sheet = fl.get("sheet_xml")
                axml = fl.get("animatioin_xml") or fl.get("animation_xml")
                if not sheet or not axml:
                    continue
                groups[st].append((sheet, axml, int(float(fl.get("zorder", "0")))))

        for st, layers in groups.items():
            if not layers:
                continue
            # 多图层：把所有 sheet 并到一个 Skeleton 里（同名字部件后者覆盖，
            # boss_4 的左右两套部件名不冲突），动画取第一层的（同源）。
            sheets = []
            for sheet, _a, _z in layers:
                if sheet not in sheets:
                    sheets.append(sheet)
            axml = layers[0][1]
            try:
                sk = Skeleton(sheets, axml)
            except Exception:
                continue
            if sk.images and sk.frame_count > 0:
                self.anims[st] = sk

        # zombie_4 这类残缺条目：原版 XML 里就没有 death_lower/death_upper，
        # 用 01 的死亡动画兜底（部件名一致，贴图仍用自己那套）。
        if "death" not in self.anims:
            sheets = []
            for st in ("walk", "attack"):
                for sheet, _a, _z in groups.get(st, []):
                    if sheet not in sheets:
                        sheets.append(sheet)
            fallback = "pic/zombies/01/death_animations.xml"
            if sheets and res.load_xml(fallback):
                try:
                    sk = Skeleton(sheets, fallback)
                except Exception:
                    sk = None
                if sk is not None and sk.images and sk.frame_count > 0:
                    self.anims["death"] = sk
                    # 兜底用 01 的死亡动画，时长也照 01 的 1.8s
                    self.durations.setdefault("death", 1.8)

        # 记下每个部件的原始贴图（walk 那套为准），供掉血换图后还原
        base = self.anims.get("walk") or self.anims.get("attack")
        if base is not None:
            self._orig_images = dict(base.images)

        self._unify_bbox()

    def _unify_bbox(self):
        """所有状态共用一套包围盒 + 一条接地线。

        各状态各算并集时底边不一样（zombie_1 walk 底 260.4、death 底 315.0），
        render 又是「包围盒底边贴 ground_y」⇒ 切到死亡动画的瞬间整只被抬升
        54px，画面上就是「僵尸一死就飞起来」。原版所有动画在同一个 Flash
        坐标系里，不存在这种跳变。

        接地线取 **walk** 的：僵尸一直是在走的状态，死亡时躺倒本来就该比
        站立低，但不能改变原点。死亡帧里脚（或身体）落到 walk 脚线以下
        时，画面会比地面低一点 —— 那是躺倒，属于正常。
        """
        boxes = [sk.bbox for sk in self.anims.values() if sk.bbox]
        if not boxes:
            return
        u = (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )
        walk = self.anims.get("walk") or next(iter(self.anims.values()))
        g = walk.ground_flash
        for sk in self.anims.values():
            sk.set_bbox(u)
            sk.set_ground(g)

    def frames(self, state):
        sk = self.anims.get(state) or self.anims.get("walk")
        return sk.frame_count if sk else 1

    def edge_offset(self):
        """anchor(screen_x) 到身体**左边缘**的距离（未缩放，逻辑像素，正数）。

        Skeleton.render 把包围盒按 screen_x 居中，但僵尸面朝左、身体整体
        偏在 anchor 左侧；战斗逻辑要跟原版 stand_distance（身体边缘到士兵
        中心）对齐，就得知道这个偏移。渲染一帧量 alpha 包围盒最准。
        """
        if self._half_w is None:
            sk = self.anims.get("walk") or self.anims.get("attack")
            off = 0.0
            if sk is not None:
                import numpy as _np

                surf = pygame.Surface((1200, 800), pygame.SRCALPHA)
                sk.render(surf, 0, 600, 700, 1.0, flip=False)
                xs = _np.nonzero(pygame.surfarray.array_alpha(surf) > 8)[0]
                if len(xs):
                    off = float(600 - xs.min())
            self._half_w = off
        return self._half_w

    def draw_shadow(self, surf, screen_x, ground_y, scale=1.0, alpha=255):
        """画脚下椭圆影子。

        贴图 yinying.png 164x65 本身就是柔边椭圆（alpha 峰值 203），
        不需要二次压 alpha，否则会淡到看不见。只按 scale 缩尺寸。
        offset 是 cocos 坐标（y 向上），影子贴脚底。
        """
        if not self.shadow:
            return
        im = res.load_img(self.shadow["tex"])
        if im is None:
            return
        w = max(1, int(im.get_width() * scale))
        h = max(1, int(im.get_height() * scale))
        im2 = pygame.transform.smoothscale(im, (w, h))
        if alpha < 255:
            im2 = im2.copy()
            im2.set_alpha(alpha)
        x = int(screen_x + self.shadow["dx"] * scale - w / 2)
        y = int(ground_y - h * 0.52)
        surf.blit(im2, (x, y))

    def _swapped_images(self, blood_ratio):
        """返回 {部件: (受伤贴图, 原贴图)}，只含本次需要替换的部件。

        规则来自 XML 的 <ChangeSprite>：血量比例 <= max_blood_ratio 时换图。
        阈值已按从高到低排好，每个部件只取第一条命中的。
        """
        if not self.damage_swaps or blood_ratio >= 1.0:
            return {}
        out = {}
        for part, max_ratio, tex in self.damage_swaps:
            if blood_ratio > max_ratio or part in out:
                continue
            if part not in self._orig_images:
                continue
            key = (part, tex)
            im = self._swap_cache.get(key)
            if im is None:
                im = res.load_img(tex)
                self._swap_cache[key] = im
            if im is not None:
                out[part] = im
        return out

    def render(
        self, surf, state, t, screen_x, ground_y, scale=1.0, flip=True, blood_ratio=1.0, alpha=1.0
    ):
        """按状态和时间画一帧。death 播完返回 True。

        frameCount 帧均匀分布在 XML 的 duration 秒内（原版 Flash2Cocos2D
        就是按 duration 平均分配帧时长，不是固定 fps）。

        alpha < 1 时整只僵尸按比例淡出 —— 对应原版死亡动画播完后
        ZombieCharacter::onDeathAnimationFinished 给每个子节点挂的
        CCFadeOut(2.0)。
        """
        sk = self.anims.get(state)
        if sk is None:
            sk = self.anims.get("walk")
            state = "walk"
        if sk is None or sk.frame_count <= 0:
            return False
        n = sk.frame_count
        dur = self.durations.get(state) or (n / 12.0)
        if dur <= 0:
            dur = n / 12.0
        # 帧号是**小数**：Skeleton 会在相邻两帧之间插值，60 fps 下才顺滑
        if state == "death":
            ff = t / dur * n
            fi = min(float(n - 1), ff)
            done = ff >= n - 1
        else:
            fi = (t % dur) / dur * n
            done = False
        swaps = self._swapped_images(blood_ratio)
        if swaps:
            # 临时替换各状态的同名部件贴图（死亡动画也要用受伤版）
            touched = []
            for st_sk in self.anims.values():
                for part, im in swaps.items():
                    if part in st_sk.images:
                        touched.append((st_sk, part, st_sk.images[part]))
                        st_sk.images[part] = im
            try:
                sk.render(surf, fi, screen_x, ground_y, scale, flip=flip)
            finally:
                for st_sk, part, old_im in touched:
                    st_sk.images[part] = old_im
        elif alpha >= 0.999:
            sk.render(surf, fi, screen_x, ground_y, scale, flip=flip)
        else:
            # 淡出：先画到临时层再整体降 alpha（直接改各部件的 alpha
            # 会按叠加顺序露出接缝，整体压一层才是干净的淡出）。
            layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            sk.render(layer, fi, screen_x, ground_y, scale, flip=flip)
            layer.set_alpha(max(0, int(255 * alpha)))
            surf.blit(layer, (0, 0))
        return done


_cache = {}


def get(name):
    """取（并缓存）某种僵尸的精灵。"""
    if name not in _cache:
        _cache[name] = ZombieSprite(name)
    return _cache[name]


def preload(names):
    for n in names:
        if n not in _cache:
            try:
                _cache[n] = ZombieSprite(n)
            except Exception:
                _cache[n] = ZombieSprite("__missing__")
