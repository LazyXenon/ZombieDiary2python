"""士兵骨骼：按当前武器加载 walk / stand / fire 三套动画。

原来只用了 `de_stand_animations.xml` 一套，走路和开火都是同一帧，
所以看起来「站着滑行」。实际每把枪在 weapon/<gun>.xml 里都声明了
三套动画（walk_upper / stand_upper / fire_upper）及各自 duration：

    p220  → de_walk / de_stand / de_fire      （0.6 / 0.6 / 0.27）
    ak47  → ak47_walk / ak47_stand / ak47_fire

这里直接读 weapon/<gun>.xml 的 <animation>，不猜文件名。
"""

import contextlib
import xml.etree.ElementTree as ET
from typing import ClassVar

import pygame

from engine import res
from engine.skel import Skeleton


# 士兵脚下影子贴图。素材库里有 pic/soldier/yinying.png（164×65 柔边椭圆），
# 士兵的骨骼 XML 没声明 <Shadow>，但原版参考帧有影子，所以这里固定用这张。
SHADOW_TEX = "pic/soldier/yinying.png"


class SoldierSprite:
    """一个武器对应的一套士兵动画。"""

    def __init__(self, gun="p220", soldier=None, look=0):
        self.gun = gun
        self.soldier = soldier or "soldier_1"
        self.look = int(look or 0)
        self.anims = {}  # state → Skeleton
        self.durations = {}  # state → 秒
        self._load()
        self._apply_look()

    def _soldier_sheets(self):
        """士兵自己的上半身贴图集（soldier_2..7 各有专属造型）。"""
        from game.shop_character import SOLDIER_SKEL

        spec = SOLDIER_SKEL.get(self.soldier)
        return list(spec[0]) if spec else None

    def _load(self):
        txt = res.load_xml("weapon/%s.xml" % self.gun)
        if not txt:
            txt = res.load_xml("weapon/p220.xml")
        if not txt:
            return
        try:
            root = ET.fromstring(txt)
        except ET.ParseError:
            return
        node = root if root.tag == "soldier" else root.find("soldier")
        if node is None:
            node = root

        # 每个 <animation name="walk_upper"> 里有若干 <Flash>
        groups = {"walk": [], "stand": [], "fire": []}
        for anim in node.findall("animation"):
            aname = anim.get("name") or ""
            if aname.startswith("walk"):
                st = "walk"
            elif aname.startswith("stand"):
                st = "stand"
            elif aname.startswith("fire"):
                st = "fire"
            else:
                continue
            dur = anim.get("duration")
            if dur:
                with contextlib.suppress(ValueError):
                    self.durations[st] = float(dur)
            for fl in anim.findall("Flash"):
                sheet = fl.get("sheet_xml")
                axml = fl.get("animatioin_xml") or fl.get("animation_xml")
                if sheet and axml:
                    groups[st].append((sheet, axml))

        own_sheets = self._soldier_sheets()
        own_mode = bool(own_sheets) and self.soldier != "soldier_1"
        # 全部状态的 sheet 并集 —— 开火动画（fire_upper）在武器 XML 里只声明了
        # upper_sheets，但 fire 动画 XML 里腿的帧是齐全的（zuotui/youtui 坐标
        # 和 stand 完全一致），只是贴图没加载 ⇒ 开火时下半身整个消失。
        # 原版 upper/lower 是两层同时跑的，这里给每个状态都补齐另一层的 sheet。
        all_sheets = []
        for layers in groups.values():
            for sheet, _a in layers:
                if sheet not in all_sheets:
                    all_sheets.append(sheet)
        extra_sheets = [sh for sh in all_sheets if "lower" in sh.lower()]
        for st, layers in groups.items():
            if not layers:
                continue
            sheets = []
            for sheet, _a in layers:
                if sheet not in sheets:
                    sheets.append(sheet)
            for sheet in extra_sheets:
                if sheet not in sheets:
                    sheets.append(sheet)
            axml = layers[0][1]
            upper = [sh for sh in sheets if "upper_sheets" in sh]
            # ★ 专属造型的角色（soldier_2..7）：
            #   每个角色自家的骨骼部件名都不一样（girl_02 是 youbi02/zuoshou02，
            #   robocop 是 zuoshou03…），自家动作文件也都是「举着自家武器」的
            #   `_swap_soldier_weapon` 把当前武器的贴图硬塞进自家武器部件名，
            #   贴图换了、可**帧坐标/注册点/旋转还是电锯的**，枪会被画到手外，
            #   现在统一走**当前武器的动作**（和 soldier_1 同一套 rig 部件名），
            #   身体贴图仍用角色自己的（_inject_body），武器贴图用当前武器的
            #   upper sheet（_inject_weapon）—— 手、枪、动作三者同一坐标系。
            if own_mode:
                try:
                    sk = Skeleton(own_sheets, axml)
                except Exception:
                    continue
                self._inject_body(sk, own_sheets)
                self._inject_weapon(sk, upper)
                sk.bbox = sk._union_bbox()
                sk.ground_flash = sk._ground_flash()
                if sk.images and sk.frame_count > 0:
                    self.anims[st] = sk
                continue
            # ★ 换枪时手上武器必须跟着变（用户反馈「角色手上不管怎样
            #   都只能拿一个武器、是贴图错误」）：
            #   Skeleton 按 sheets 顺序 `parts.update`，**后加载者覆盖同名部件**。
            #   上面补齐 all_sheets 时，通用 lower / 其它状态的 upper 会排在
            #   本状态 upper 之后，把 `gun02` / `qiubang` 换回默认手枪贴图。
            #   原版 SoldierCharacter::initCharacter 就是把**当前武器的
            #   upper 贴图盖到通用 lower 上**，这里用 override_parts 复刻
            #   这个覆盖，并把 upper 排到列表末尾做双保险。
            overrides = {}
            if upper:
                from engine.skel import parse_sheet

                for sh in upper:
                    stxt = res.load_xml(sh)
                    if not stxt:
                        continue
                    try:
                        for pn in parse_sheet(stxt):
                            overrides[pn] = sh
                    except Exception:
                        continue
                sheets = [sh for sh in sheets if sh not in upper] + upper
            foreign = {"bian01", "bian02"} if self.soldier == "soldier_1" else None
            try:
                sk = Skeleton(sheets, axml, override_parts=overrides, exclude_parts=foreign)
            except Exception:
                continue
            if sk.images and sk.frame_count > 0:
                self.anims[st] = sk

        self._drop_gun_when_melee()

        self._unify_bbox()

    # 部件名别名：各角色的骨架 rig 是同一套骨骼，但导出时部件名不同
    # （girl_02 的右臂叫 youbi02、左手叫 zuoshou02；robocop 是 zuoshou03…）。
    # 当前武器的动作 XML 用的是标准名（youbi / zuoshou），所以要把角色自己的
    # 贴图挂到标准名上，动作才能对齐。
    _RIG_ALIAS: ClassVar[dict] = {
        "youbi02": "youbi",
        "youbi03": "youbi",
        # ★ 前手（左手）必须映射到 rig 里**真实存在**的部件名 `zuoshou03`。
        #   `canon not in sk.anim` 判空后直接 continue ⇒ 除了 soldier_1
        #   （手来自武器 upper sheet），**其它 6 个角色的前手全都没画出来**：
        #   枪/扳手悬在身体前面的空气里，看着就是「所有角色的模型都有问题」。
        "zuoshou02": "zuoshou03",
        "zuoshou03": "zuoshou03",
        "zuoshou04": "zuoshou03",
    }

    @classmethod
    def _pick_name(cls, nm, anim):
        """把「角色自家部件名」映射到**这套骨架里真实存在**的同义部件名。

        ★ 近战武器的 rig 和枪不一样：斧头用的是 youbi02 + zuoshou02，
          而枪/刀/扳手用的是 youbi + zuoshou03。
          拿着斧头时，这套骨架里根本没有 zuoshou03（斧头是 zuoshou02），
          `canon not in sk.anim` 直接 continue ⇒ **前手整只消失**、前臂也被
          改到不存在的 youbi 上 ⇒ 斧子悬在空气里，看着就是「手翻了」。
          这里改成：先试首选名，不存在就回到同族（去掉尾部数字）里挑一个。
        """
        pref = cls._RIG_ALIAS.get(nm)
        if pref and pref in anim:
            return pref
        family = nm.rstrip("0123456789")
        cands = [k for k in anim if k != nm and k.rstrip("0123456789") == family]
        if not cands:
            return pref if pref in anim else None
        if pref:
            cands.sort(key=lambda k: k != pref)
        return cands[0]

    def _load_part_img(self, path, base_dir=""):
        im = res.load_img(path)
        if im is None and base_dir and not (path or "").startswith("pic/"):
            im = res.load_img(base_dir + path)
        return im

    def _inject_body(self, sk, own_sheets):
        """把角色自己的**身体**贴图挂到标准 rig 部件名上（soldier_2..7）。"""
        from engine.skel import parse_sheet

        for sh in own_sheets:
            txt = res.load_xml(sh)
            if not txt:
                continue
            base = sh.rsplit("/", 1)[0] + "/" if "/" in sh else ""
            try:
                got = parse_sheet(txt)
            except Exception:
                continue
            for nm, p in got.items():
                if nm not in self._BODY and nm not in self._RIG_ALIAS:
                    continue  # 自家武器（dianju / gun04…）不要
                canon = nm if nm in sk.anim else self._pick_name(nm, sk.anim)
                if not canon or canon not in sk.anim:
                    continue
                # 同一具骨架里不要被「同族的另一张图」覆盖（youbi 与 youbi02
                # 会同族）：精确同名优先，其次先到先得。
                if canon in sk.images and nm != canon:
                    continue
                im = self._load_part_img(p.get("path"), base)
                if im is None:
                    continue
                if canon.startswith("zuoshou"):
                    # ★ 前手必须画在**手臂之上**。各角色自家 sheet 里这只手的
                    #   z 只有 1~2，而 youbi（前臂）是 9 —— 手被自己的袖子盖住，
                    #   手拿武器还是有点奇怪」）。抬到 95：盖住前后臂与头，
                    #   但仍低于 99 那层披风/后臂。
                    p = dict(p)
                    p["z"] = max(int(p.get("z", 0) or 0), 95)
                sk.parts[canon] = p
                sk.images[canon] = im

    def _inject_weapon(self, sk, upper_sheets):
        """把**当前武器**的部件（gun02 / qiubang / fuzi…）挂进来。"""
        from engine.skel import parse_sheet

        for sh in upper_sheets:
            txt = res.load_xml(sh)
            if not txt:
                continue
            base = sh.rsplit("/", 1)[0] + "/" if "/" in sh else ""
            try:
                got = parse_sheet(txt)
            except Exception:
                continue
            for nm, p in got.items():
                if nm in self._BODY or nm not in sk.anim:
                    continue
                im = self._load_part_img(p.get("path"), base)
                if im is None:
                    continue
                sk.parts[nm] = p
                sk.images[nm] = im

    def _apply_look(self):
        """按武器等级换手中那把枪的贴图（gun_<name>_1 / _2）。

        骨骼的 sheets.xml 只写了原始贴图，武器升级后原版会去
        pic/soldier/0N/gun_<name>_<look>.png 换图，模型本身不动。
        """
        if self.look <= 0:
            return
        for sk in self.anims.values():
            for nm, p in list(sk.parts.items()):
                if nm in self._BODY:  # ★ 原来写裸 _BODY（类属性）→ NameError
                    continue
                path = (p.get("path") or "").replace("pic_png/", "pic/")
                if not path.endswith(".png"):
                    continue
                alt = "%s_%d.png" % (path[:-4], self.look)
                im = res.load_img(alt)
                if im is not None and nm in sk.images:
                    sk.images[nm] = im

    def _drop_gun_when_melee(self):
        """武器 upper sheet 没有 gun02 时，把拼进来的通用枪去掉。"""
        txt = res.load_xml("weapon/%s.xml" % self.gun)
        if not txt:
            return
        try:
            root = ET.fromstring(txt)
        except ET.ParseError:
            return
        node = root if root.tag == "soldier" else root.find("soldier")
        if node is None:
            return
        # 找 walk_upper 的 <Flash> 的 sheet_xml（代表性的一条）
        upper_sheets = []
        for anim in node.findall("animation"):
            for fl in anim.findall("Flash"):
                sh = fl.get("sheet_xml")
                if sh and sh not in upper_sheets:
                    upper_sheets.append(sh)
        if not upper_sheets:
            return
        # 这些 sheet 里只要有任何一个声明了 gun02，就说明这把枪有「枪」部件
        has_gun = False
        for sh in upper_sheets:
            s = res.load_xml(sh)
            if s and "gun02" in s:
                has_gun = True
                break
        if has_gun:
            return
        for sk in self.anims.values():
            sk.parts.pop("gun02", None)
            sk.images.pop("gun02", None)

    # 身体部件白名单：不在表里的部件就是「手里的武器」，换枪时要跟着换。
    # 名字取自 pic/soldier/<角色>/*_sheets.xml 的实际部件表。
    _BODY = frozenset(
        (
            "tou",
            "qungan",
            "zuobi",
            "youbi",
            "youbi02",
            "youbi03",
            "zuoshou",
            "zuoshou02",
            "zuoshou03",
            "zuoshou04",
            "zuotui",
            "youtui",
            "bian01",
            "bian02",
            "majiazuo",
            "majiayou",
            "sunzi",
        )
    )

    def _unify_bbox(self):
        """所有状态共用一套包围盒 + 一条接地线。

        各状态各算并集会带来两个可见 bug：
          · 开火动画没有下半身 ⇒ 并集矮 40px ⇒ 一开枪整个人往下沉；
          · 僵尸死亡动画躺倒 ⇒ 并集底边下移 ⇒ 一死整只飞起来。
        原版所有动画在同一个 Flash 坐标系里，不存在这种跳变。

        接地线取 **walk** 的：站立时脚本来就在这条线上，走路是主线状态。
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

    def state_frame_count(self, state):
        sk = self.anims.get(state)
        return sk.frame_count if sk else 0

    def duration(self, state):
        sk = self.anims.get(state)
        n = sk.frame_count if sk else 0
        return self.durations.get(state) or (n / 20.0 if n else 0.6)

    def pose(self, state, t):
        """返回该状态下时间 t 对应的帧号。

        站立/走路是循环；开火是「一枪一循环」——t 是本次开火已经过去的秒数。
        """
        sk = self.anims.get(state) or self.anims.get("stand")
        if sk is None or sk.frame_count <= 0:
            return None, None
        n = sk.frame_count
        dur = self.duration(state if state in self.anims else "stand")
        if dur <= 0:
            dur = 0.6
        # ★ 返回**小数**帧号：Skeleton 会在相邻两帧之间插值（见 skel._frame_at）。
        fi = (t % dur) / dur * n
        return sk, fi % n

    def muzzle_point(self, state, t, screen_x, ground_y, scale=1.0, flip=False):
        """枪口在屏幕上的位置（用来放枪口火光）。

        枪是骨骼里的 gun* 部件，枪口就是**枪部件朝向的那一端**。
        直接用 Skeleton.part_point —— 它跑的是和 render 完全相同的
        缩放/镜像/绕注册点旋转变换，所以火光的落点必然贴着画出来的枪管。
        """
        sk, fi = self.pose(state, t)
        if sk is None:
            return None
        gun = None
        for nm, p in sk.parts.items():
            if nm.startswith("gun") and p["w"] > 40:
                gun = nm
                break
        if gun is None:
            return None
        # flip 时贴图左右翻转，枪口在翻转图的左端（u=0）；否则在右端（u=1）
        return sk.part_point(gun, fi, screen_x, ground_y, 0.0 if flip else 1.0, 0.42, scale, flip)

    def gun_box(self, state, t, screen_x, ground_y, scale=1.0, flip=False):
        """枪部件在屏幕上的包围盒（弹壳从枪膛抛出要用）。

        和 muzzle_point 同一套坐标（Skeleton.part_box），所以弹壳的
        起点永远在画出来的枪身上，不会从半空或脚底冒出来。
        """
        sk, fi = self.pose(state, t)
        if sk is None:
            return None
        for nm, p in sk.parts.items():
            if nm.startswith("gun") and p["w"] > 40:
                return sk.part_box(nm, fi, screen_x, ground_y, scale, flip)
        return None

    def draw_shadow(self, surf, screen_x, ground_y, scale=1.0, alpha=255):
        """画脚下椭圆影子。

        士兵的骨骼 XML 里**没有** <Shadow> 节点（僵尸有，见
        assets/raw/zombies/zombie_9.xml），但原版参考帧（emu_b4_s.png 脚下
        那块深色椭圆）明确有影子 —— 没有影子角色就像浮在半空，
        这是「感觉不在地上」的主因。

        复用素材库自带的 pic/soldier/yinying.png（164×65 柔边椭圆，
        alpha 峰值 203），和僵尸用的是同一张图，只是位置/尺寸不同：
          · 士兵的脚比僵尸窄（士兵包围盒半宽 106，僵尸约 115），
            影子略窄一点，缩到 0.8；
          · 贴脚底：椭圆中心比脚底略高一点（人站在地上的投影
            是被身体挡住的，露出来的是脚周围那一圈）。
        """
        im = res.load_img(SHADOW_TEX)
        if im is None:
            return
        w = max(1, int(im.get_width() * scale * 0.8))
        h = max(1, int(im.get_height() * scale * 0.8))
        im2 = pygame.transform.smoothscale(im, (w, h))
        if alpha < 255:
            im2 = im2.copy()
            im2.set_alpha(alpha)
        x = int(screen_x - w / 2)
        y = int(ground_y - h * 0.46)
        surf.blit(im2, (x, y))

    # 下半身部件（腿）。upper/lower 分层动画用：边跑边打时腿走 walk、上身 fire。
    LOWER = frozenset(("zuotui", "youtui"))

    def render(
        self,
        surf,
        state,
        t,
        screen_x,
        ground_y,
        scale=1.0,
        flip=False,
        lower_state=None,
        lower_t=None,
    ):
        sk, fi = self.pose(state, t)
        if sk is None:
            return False
        if lower_state and lower_state in self.anims:
            lo = self.anims[lower_state]
            if lo is not sk:
                self._render_split(
                    surf,
                    sk,
                    fi,
                    lower_state,
                    lower_t if lower_t is not None else t,
                    screen_x,
                    ground_y,
                    scale,
                    flip,
                )
                return True
        # 枪口火焰 bian01/bian02：**不画**。
        #   这两个精灵在 XML 里的时间轴坐标是 girl_02（女角色）的马尾位置，
        #   右端手工画了一团火，结果开火时头顶冒出一坨橘色，反而更像散架。
        #   模拟器参考帧（emu_battle_fire.png / emu_battle_fire2.png）确认：
        #   原版开火时枪口和头顶都没有任何火焰。所以隐藏即可，不补画。
        hidden = {}
        if self.soldier == "soldier_1":
            hidden = {k: v for k, v in sk.images.items() if k.startswith("bian")}
        for k in hidden:
            sk.images.pop(k, None)
        try:
            sk.render(surf, fi, screen_x, ground_y, scale, flip=flip)
        finally:
            sk.images.update(hidden)
        return True

    def _render_split(self, surf, up_sk, up_fi, lo_state, lo_t, screen_x, ground_y, scale, flip):
        """上半身用 up_sk 的帧、下半身用 lo_state（walk）的帧。

        原版 Soldier 的 upper / lower 是两层动画同时跑的。两套 Skeleton 的
        部件名、bbox、接地线在 _unify_bbox 里已经统一过，所以分开画也能
        严丝合缝地拼在同一个坐标系里：
          1. 先画腿（walk 帧，z 最低，压在身体下面）；
          2. 再画上半身（fire 帧，剔除腿部件，避免重叠抖动）。
        """
        lo_sk, lo_fi = self.pose(lo_state, lo_t)
        if lo_sk is None or lo_fi is None:
            up_sk.render(surf, up_fi, screen_x, ground_y, scale, flip=flip)
            return
        hidden = {}
        if self.soldier == "soldier_1":
            hidden = {k: v for k, v in up_sk.images.items() if k.startswith("bian")}
            for k in hidden:
                up_sk.images.pop(k, None)
        try:
            lo_sk.render(surf, lo_fi, screen_x, ground_y, scale, flip=flip, only=self.LOWER)
            upper = {nm for nm in up_sk.parts if nm not in self.LOWER}
            up_sk.render(surf, up_fi, screen_x, ground_y, scale, flip=flip, only=upper)
        finally:
            up_sk.images.update(hidden)


_cache = {}


def get(gun, soldier=None, look=0):
    key = (gun or "p220", soldier or "soldier_1", int(look or 0))
    if key not in _cache:
        _cache[key] = SoldierSprite(key[0], key[1], key[2])
    return _cache[key]


def clear():
    _cache.clear()
