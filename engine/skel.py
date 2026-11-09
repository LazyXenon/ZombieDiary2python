"""骨骼动画引擎（cocos2d-x / Flash2Cocos2D 语义，公式已用 POC 验证零扭曲）。

XML 结构：
  *_sheets.xml:   <Texture name width height path registrationPointX/Y zIndex/>
  *_animations.xml: <Animation ...><Part name><Frame x y rotation index scaleX scaleY/>...</Part></Animation>

渲染公式（内存实测 ap_x=regX/w, ap_y=1+regY/h 反推）：
  anchor = (regX/w, 1+regY/h)，注册点在图顶上方 regY 像素 = 关节在肢体顶端。
  y 向下为 Flash 正方向，转 cocos y-up 时 pos=(x, -y)。
"""

import math
import os
import xml.etree.ElementTree as ET

import pygame

from engine import res


def parse_sheet(xml_text):
    t = ET.fromstring(xml_text)
    parts = {}
    for tex in t.iter("Texture"):
        nm = tex.get("name")
        parts[nm] = dict(
            w=int(float(tex.get("width"))),
            h=int(float(tex.get("height"))),
            regX=float(tex.get("registrationPointX", "0")),
            regY=float(tex.get("registrationPointY", "0")),
            z=int(float(tex.get("zIndex", "99"))),
            path=tex.get("path"),
        )
    return parts


def parse_anim(xml_text):
    t = ET.fromstring(xml_text)
    out = {}
    for part in t.iter("Part"):
        pn = part.get("name")
        fr = []
        for f in part.iter("Frame"):
            fr.append(
                dict(
                    x=float(f.get("x", "0")),
                    y=float(f.get("y", "0")),
                    rot=float(f.get("rotation", "0")),
                    sx=float(f.get("scaleX", "1")),
                    sy=float(f.get("scaleY", "1")),
                )
            )
        # 同一部件名在 XML 里可能重复出现 —— 有的僵尸（如 zombie_02/11）
        # 会把「每个骨骼一整套 9 个 Part」重复 8 次，只有其中一套带 Frame，
        # 其余 7 套是空壳。这里只接受真正带帧的那一套，空的不能覆盖。
        if (fr and (pn not in out or not out[pn])) or pn not in out:
            out[pn] = fr
    return out


# 部件变换缓存：scale → flip → rotate 的组合结果。
# 骨骼每帧要画十几个部件，每个都要 smoothscale（+ flip + rotate）。
# 同一批部件在同一 scale 下反复做同样的变换，实测占战斗 render 约 40%。
# 缓存键 = (贴图 id, 宽, 高, 水平镜像, 旋转角)；贴图是 res.load_img 的单例，
# id 稳定。res 清缓存后贴图对象换新，id 变化 ⇒ 旧条目自然失效。
_part_cache = {}


def _lerp_frame(a, b, s):
    """两帧之间线性插值。

    ★ 素材里的动作是按 20~24 fps 导出的关键帧（站立 2~12 帧、走路 8 帧），
      是动态但是帧率也太低了」/「要有动画但是动画务必流畅」。
      这里把帧号当成**小数**用：整数部分取当前帧、小数部分做插值，
      骨骼位移 / 缩放直接线性插，角度走最短弧（避免 179°→-179° 时整个人
      原地转一圈）。
    """
    if s <= 0.0 or a is b:
        return a
    dr = b["rot"] - a["rot"]
    if dr > 180.0:
        dr -= 360.0
    elif dr < -180.0:
        dr += 360.0
    return dict(
        x=a["x"] + (b["x"] - a["x"]) * s,
        y=a["y"] + (b["y"] - a["y"]) * s,
        rot=a["rot"] + dr * s,
        sx=a["sx"] + (b["sx"] - a["sx"]) * s,
        sy=a["sy"] + (b["sy"] - a["sy"]) * s,
    )


def _frame_at(fr, fi):
    """按（可能带小数的）帧号取该部件的帧，必要时与下一帧插值。"""
    n = len(fr)
    if n <= 1:
        return fr[0] if fr else None
    i0 = int(fi) % n
    s = fi - int(fi)
    if s <= 0.001:
        return fr[i0]
    return _lerp_frame(fr[i0], fr[(i0 + 1) % n], s)


def _part_img(img, w, h, flip_x, rot_deg):
    if (w, h) != img.get_size():
        out = pygame.transform.smoothscale(img, (w, h))
    else:
        out = img
    if flip_x:
        out = pygame.transform.flip(out, True, False)
    if abs(rot_deg) > 0.01:
        out = pygame.transform.rotate(out, rot_deg)
    return out


def _part_img_cached(img, w, h, flip_x, rot_deg):
    # 角度量化到 0.5°：帧间插值后角度是连续小数，不量化的话缓存永远不命中
    # （每帧十几个部件都要现做 smoothscale + rotate），量化带来的视觉差异
    # 在半度以内，肉眼看不出来。
    rot_deg = round(rot_deg * 2.0) / 2.0
    key = (id(img), w, h, flip_x, rot_deg)
    hit = _part_cache.get(key)
    # 命中必须确认还是同一张贴图对象：res.clear_cache() 之后 id 会被复用，
    # 只按 id 认会拿到别的部件的图（表现为偶发错图 / 1 像素级色差）。
    if hit is not None and hit[0] is img:
        return hit[1]
    out = _part_img(img, w, h, flip_x, rot_deg)
    if len(_part_cache) > 2048:
        _part_cache.clear()
    _part_cache[key] = (img, out)  # 同时保活原图，锁死 id 不被复用
    return out


def clear_part_cache():
    _part_cache.clear()


class Skeleton:
    def __init__(self, sheet_paths, anim_path, override_parts=None, exclude_parts=None):
        """sheet_paths: 一个或多个 sheets.xml（upper+lower 合并）。

        anim_path: 一个 animations.xml，或按先后覆盖的多个动画源：
          · str              —— 整套部件帧；
          · (path, names)    —— 只取 names 里的部件，覆盖前面同名的帧。
        为什么需要多源：机甲 fire 的 weapon XML 只列 fire_upper（上半身），
        腿层只存在于 stand/walk 的 *_lower sheets + stand_animations.xml。
        补上腿的 sheets 后还得让腿用站立帧（否则 fire_animations.xml 里那套
        腿帧会把腿甩成开火姿态），于是合成
        [fire_animations.xml, (stand_animations.xml, 腿部件名)] 两个源。

        override_parts: {部件名: sheets 路径} —— 只用该路径的贴图覆盖同名部件，
        其它部件保持原样。原版 SoldierCharacter::initCharacter 只把当前武器的
        upper 贴图（gun02）盖到通用 lower 上，角色本体仍用 de_sheets。

        exclude_parts: 要从部件表里剔掉的部件名集合。用于原版素材里"串了别的
        角色部件"的情况（如 soldier_1 的 upper_sheets 混进 girl_02 的辫子），
        必须在算 bbox / 接地基准之前剔，否则角色会被那两个部件撑偏。

        ★ 贴图路径是**相对于 sheets.xml 所在目录**的（如
          pic/effect/star/star_sheets.xml 里写 "paopao/s01.png"，
          实际文件在 assets/images/pic/effect/star/paopao/s01.png）。
          骨骼的 images 为空 ⇒ 整个动画画不出来（星星 / 聚焦光圈都不显示）。
        """
        self.parts = {}
        base_dir = ""
        for sp in sheet_paths:
            s = res.load_xml(sp)
            if s:
                got = parse_sheet(s)
                if not base_dir:
                    base_dir = sp.rsplit("/", 1)[0] + "/" if "/" in sp else ""
                self.parts.update(got)
        for pname, sp in (override_parts or {}).items():
            s = res.load_xml(sp)
            if s:
                got = parse_sheet(s)
                if pname in got:
                    self.parts[pname] = got[pname]
        self.anim = {}
        specs = anim_path if isinstance(anim_path, (list, tuple)) else [anim_path]
        for spec in specs:
            if isinstance(spec, (list, tuple)):
                ap, only = spec[0], set(spec[1])
            else:
                ap, only = spec, None
            a = res.load_xml(ap)
            if not a:
                continue
            for pn, fr in parse_anim(a).items():
                if only is not None and pn not in only:
                    continue
                self.anim[pn] = fr
        # 只保留 sheet 与 anim 都有的部件，并剔掉串进来的其它角色部件
        drop = exclude_parts or ()
        self.parts = {k: v for k, v in self.parts.items() if k in self.anim and k not in drop}
        self.images = {}
        for nm, p in self.parts.items():
            path = p["path"]
            im = res.load_img(path)
            if im is None and base_dir and not path.startswith("pic/"):
                # 贴图路径相对于 sheets 所在目录
                im = res.load_img(base_dir + path)
            if im:
                self.images[nm] = im
        # 固定基准包围盒：所有帧所有部件的并集。
        # 逐帧算包围盒会让整个角色随动作上下左右跳（走路时高度能差 30px），
        # 看起来就像骨骼散架。用并集锁死，位置才稳定。
        self.bbox = self._union_bbox()
        # 接地基准线（Flash 坐标）。竖直定位只看它，不看 bbox。
        self.ground_flash = self._ground_flash()

    def set_bbox(self, bbox):
        """覆盖基准包围盒（多状态共用一套时用）。

        每个状态各算一套并集 bbox 会让角色在切状态瞬间整体位移：
        僵尸 walk 脚底贴地、death 的并集底边更靠下 ⇒ 死亡瞬间整只升空 55px，
        玩家看到的就是「死了直接飞起来」。多个状态统一用一套 bbox 才不会跳。
        """
        if bbox is not None:
            self.bbox = bbox

    def set_ground(self, ground_flash):
        """覆盖接地基准线（多状态共用一条时用）。

        同一角色的 walk / stand / death 必须用同一条接地线，否则切状态的
        那一帧脚会跳一下。死亡动画可以比接地线更低（躺在地上），
        但不能改变原点，否则整只又会飘起来。
        """
        if ground_flash is not None:
            self.ground_flash = ground_flash

    @staticmethod
    def _rot_bounds(p, f):
        """部件绕注册点旋转后的 Flash 包围盒 (l, t, r, b)，y 向下。

        和 render 的绘制口径一致（不乘 f.sx/f.sy —— render 也没乘）。
        """
        regX, regY = p["regX"], p["regY"]
        w, h = p["w"], p["h"]
        rad = math.radians(f["rot"])
        c, s = math.cos(rad), math.sin(rad)
        l = t = 1e9
        r = b = -1e9
        for cx, cy in ((0.0, 0.0), (w, 0.0), (0.0, h), (w, h)):
            dx = cx - regX
            dy = cy + regY
            x = f["x"] + dx * c - dy * s
            y = f["y"] + dx * s + dy * c
            if x < l:
                l = x
            if x > r:
                r = x
            if y < t:
                t = y
            if y > b:
                b = y
        return l, t, r, b

    def _ground_flash(self):
        """接地基准线 = 旋转后最深的那一帧的底边（Flash 坐标 y 向下）。

        ★ 这里必须是**旋转后**的底边。早先用未考虑旋转的并集底边当基准：
          · 士兵 youtui 第 0 帧 rot=-64.13°，未旋转矩形底边 317.45，
            旋转后实际只到 297.0 —— 多算 20px，整个人被抬高 20px；
          · 僵尸死亡动画躺倒，未旋转底边 315、旋转后只有 243.8。
        多算的高度全变成「脚离地」，玩家看到的就是「角色和僵尸在天上飞」。
        """
        best = None
        n = self.frame_count
        for i in range(n):
            b = -1e9
            for nm, p in self.parts.items():
                fr = self.anim.get(nm)
                if not fr:
                    continue
                bb = self._rot_bounds(p, fr[i % len(fr)])[3]
                if bb > b:
                    b = bb
            if b > -1e8 and (best is None or b > best):
                best = b
        return best if best is not None else 0.0

    def _union_bbox(self):
        """全部帧全部部件、**旋转后**的并集。水平居中就靠它。"""
        min_x = min_y = 1e9
        max_x = max_y = -1e9
        for nm, p in self.parts.items():
            fr = self.anim.get(nm)
            if not fr:
                continue
            for f in fr:
                l, t, r, b = self._rot_bounds(p, f)
                if l < min_x:
                    min_x = l
                if r > max_x:
                    max_x = r
                if t < min_y:
                    min_y = t
                if b > max_y:
                    max_y = b
        if min_x > max_x:
            return None
        return (min_x, min_y, max_x, max_y)

    def body_bbox(self, exclude_prefixes=("bian", "gun")):
        """排除指定前缀部件后的并集包围盒（身体本体）。

          · bian01/bian02 —— 女角色（girl_02）的马尾资源，被错配到通用士兵身上，
            渲染时已经隐藏，但它们在 y≈92 的位置把 bbox 顶端撑高了 35px；
          · gun*         —— 枪。枪朝一侧伸出去，会把 bbox 的水平中心推偏，
            而「角色中心」应该按身体算。
        所以头顶高度用 body_bbox 的上边，身体中心用 body_bbox 的中心。
        """
        min_x = min_y = 1e9
        max_x = max_y = -1e9
        for nm, p in self.parts.items():
            if any(nm.startswith(pfx) for pfx in exclude_prefixes):
                continue
            fr = self.anim.get(nm)
            if not fr:
                continue
            for f in fr:
                l, t, r, b = self._rot_bounds(p, f)
                if l < min_x:
                    min_x = l
                if r > max_x:
                    max_x = r
                if t < min_y:
                    min_y = t
                if b > max_y:
                    max_y = b
        if min_x > max_x:
            return None
        return (min_x, min_y, max_x, max_y)

    @property
    def frame_count(self):
        return max((len(fr) for fr in self.anim.values()), default=1)

    def _collect(self, frame_idx, flip):
        """收集本帧要画的部件，返回 (items, cx)。

        frame_idx 可以是小数（见 _frame_at）：整数部分选帧、小数部分插值。
        item = (part, img, frame, regx)。regx 是**实际生效的**注册点 x 偏移：
        水平镜像时贴图本身左右翻转，注册点在翻转后的图里跑到 `w - regX`。
        """
        items = []
        for nm, p in self.parts.items():
            fr = self.anim.get(nm)
            if not fr:
                continue
            f = _frame_at(fr, frame_idx)
            img = self.images.get(nm)
            if not img:
                continue
            items.append((p, img, f, p["regX"]))

        if not flip or not items:
            return items, None

        # 镜像中心用固定基准（并集）而不是当前帧，否则翻转时也会抖
        if self.bbox:
            cx = (self.bbox[0] + self.bbox[2]) / 2.0
        else:
            xs = [f["x"] for _p, _i, f, _r in items]
            cx = (min(xs) + max(xs)) / 2.0

        return (
            [
                (p, img, dict(f, x=2 * cx - f["x"], rot=-f["rot"]), p["w"] - p["regX"])
                for p, img, f, _r in items
            ],
            cx,
        )

    def part_box(self, name, frame_idx, screen_x, ground_y, scale=1.0, flip=False):
        """某个部件（未旋转近似）在屏幕上的位置，供枪口定位用。

        返回 dict：left/top（屏幕像素，未含旋转）、w/h（缩放后像素）、
        regx（生效注册点，镜像后已换算到翻转图的坐标）。
        """
        items, _cx = self._collect(frame_idx, flip)
        target = None
        for p, _img, f, regx in items:
            if self.parts.get(name) is p:
                target = (p, f, regx)
                break
        if target is None or not self.bbox:
            return None
        p, f, regx = target
        min_x, _min_y, max_x, max_y = self.bbox
        gf = self.ground_flash if self.ground_flash is not None else max_y
        px = screen_x - (max_x - min_x) / 2.0 + (f["x"] - regx - min_x)
        py = ground_y - (gf - (f["y"] + p["regY"]))
        return dict(
            left=screen_x + (px - screen_x) * scale,
            top=ground_y - (ground_y - py) * scale,
            w=p["w"] * scale,
            h=p["h"] * scale,
            regx=regx * scale,
            regy=p["regY"] * scale,
        )

    def part_point(self, name, frame_idx, screen_x, ground_y, u, v, scale=1.0, flip=False):
        """取部件贴图内 (u,v) 比例点（0..1，镜像后坐标系）的屏幕坐标。

        和 render 用同一套 缩放/镜像/绕注册点旋转 的变换，所以算出来的点
        一定落在画出来的那张图上（枪口定位靠这个）。
        """
        items, _cx = self._collect(frame_idx, flip)
        target = None
        for p, _img, f, regx in items:
            if self.parts.get(name) is p:
                target = (p, f, regx)
                break
        if target is None or not self.bbox:
            return None
        p, f, regx = target
        min_x, _min_y, max_x, max_y = self.bbox
        gf = self.ground_flash if self.ground_flash is not None else max_y
        px = screen_x - (max_x - min_x) / 2.0 + (f["x"] - regx - min_x)
        py = ground_y - (gf - (f["y"] + p["regY"]))
        spx = screen_x + (px - screen_x) * scale
        spy = ground_y - (ground_y - py) * scale

        w = max(1, int(round(p["w"] * scale)))
        h = max(1, int(round(p["h"] * scale)))
        rx = regx * scale
        ry = p["regY"] * scale
        dx = u * w - rx
        dy = v * h + ry
        rad = math.radians(f["rot"])
        dx2 = dx * math.cos(rad) - dy * math.sin(rad)
        dy2 = dx * math.sin(rad) + dy * math.cos(rad)
        return (spx + rx + dx2, spy - ry + dy2)

    def render(self, surf, frame_idx, screen_x, ground_y, scale=1.0, flip=False, only=None):
        """把骨骼画到 surf。screen_x=水平中心, ground_y=脚底(屏幕y-down)。

        only: 只画这些部件名（set/None）。开火动画只有上半身时，用同一个
        Skeleton 的坐标系统再补画一次站立动画的腿，靠这个参数挑部件。
        """
        items, _cx = self._collect(frame_idx, flip)
        if only is not None:
            ids = [id(p) for nm, p in self.parts.items() if nm in only]
            items = [it for it in items if id(it[0]) in ids]
        if not items:
            return

        # 包围盒：用整个动画的并集（self.bbox），不是当前帧。
        # 镜像时包围盒不变 —— 反射区间 [a,b] 关于自身中点对称后仍是 [a,b]。
        if self.bbox:
            min_x, min_y, max_x, max_y = self.bbox
        else:
            min_x = min_y = 1e9
            max_x = max_y = -1e9
            for p, _img, f, regx in items:
                l = f["x"] - regx
                r = l + p["w"]
                t = f["y"] + p["regY"]
                b = t + p["h"]
                min_x = min(min_x, l)
                max_x = max(max_x, r)
                min_y = min(min_y, t)
                max_y = max(max_y, b)

        cw = max_x - min_x
        ch = max_y - min_y
        if cw <= 0 or ch <= 0:
            return

        # 水平：包围盒居中在 screen_x。
        # 竖直：**接地基准线**贴 ground_y（不是包围盒底边）。
        #   bbox 底边只用于算高度余量，不能用来贴地：它混着旋转前的矩形，
        #   会把脚「垫高」（见 _ground_flash 的说明）。
        origin_x = screen_x - cw / 2  # 包围盒左边界（未缩放）
        gf = self.ground_flash if self.ground_flash is not None else max_y

        for p, img, f, regx in sorted(items, key=lambda q: q[0]["z"]):
            # 部件左上角（未缩放，y 向下）。
            # 包围盒 min_x/min_y 是按「部件左上角 = f.x − regX」算的
            # （见 _union_bbox），所以这里也必须减掉 regX/regY，否则不是
            # 每个部件都被平移了它自己的注册点。士兵和 zombie_9 的
            # regX=regY=2 只偏 2px 不明显；但 zombie_2 的 guo 是 regY=−25、
            # zombie_3 的 tou 是 regX=6、zuobi 是 regY=−14.35 ——
            # 部件直接错开十几二十像素，看起来就是「模型散架」。
            px = origin_x + (f["x"] - regx - min_x)
            py = ground_y - (gf - (f["y"] + p["regY"]))
            # 整体缩放绕脚下中心 (screen_x, ground_y)
            spx = screen_x + (px - screen_x) * scale
            spy = ground_y - (ground_y - py) * scale

            w = max(1, int(round(p["w"] * scale)))
            h = max(1, int(round(p["h"] * scale)))
            rx = regx * scale
            ry = p["regY"] * scale
            rot = f["rot"]  # Flash 顺时针角（已在 flip 分支里取反）
            # pygame.rotate(+a) 在屏幕上是**逆时针**（实测：右上红点转到左上），
            # Flash 的 rotation 正值是**顺时针** → 传 -rot 给 pygame。
            img2 = _part_img_cached(img, w, h, flip, -rot)
            if abs(rot) > 0.01:
                # 绕注册点（关节）旋转。
                # 注册点在图像坐标系（y 向下）里是 (rx, -ry) ——
                # 由 cocos 锚点公式 anchor = (regX/w, 1+regY/h) 反推：
                #   锚点距底部 = (1+regY/h)*h = h+regY → 换成图像坐标 = -regY。
                # 所以注册点相对图像中心的向量 d = (rx - w/2, -ry - h/2)。
                W2, H2 = img2.get_size()
                rad = math.radians(rot)
                dx = rx - w / 2.0
                dy = -ry - h / 2.0
                # Flash 顺时针矩阵（y 向下）：(x,y)->(x cos - y sin, x sin + y cos)
                dx2 = dx * math.cos(rad) - dy * math.sin(rad)
                dy2 = dx * math.sin(rad) + dy * math.cos(rad)
                # 旋转后注册点在新图里的位置 = 新中心 + (dx2, dy2)
                # 要让它落在屏幕上的 (spx + rx, spy - ry)
                blit_x = int(round(spx + rx - (W2 / 2.0 + dx2)))
                blit_y = int(round(spy - ry - (H2 / 2.0 + dy2)))
            else:
                blit_x = int(round(spx))
                blit_y = int(round(spy))

            surf.blit(img2, (blit_x, blit_y))
