"""战斗场景渲染：战场、HUD、技能条、经验武器、道具。"""

import json as json

import pygame

from app.constants import (
    BATTLE_BG_SUBTREE,
    BATTLE_COIN_ICON,
    BATTLE_CONTROL_NODES,
    BATTLE_CRYS_ICON,
    BATTLE_STATIC_HIDE,
    BHIDE,
    BSKIP_CLS,
    BSKIP_TEX,
    BTEXFIX,
    GO_RIGHT_OPACITY,
    GO_RIGHT_SCALE,
    GO_RIGHT_SHOW,
    GO_RIGHT_SWING,
    GO_RIGHT_TEX,
    GUARD_LINE_X,
    HP_BAR_X,
    HP_BAR_Y,
    HUD_HEAD_SCALE,
    HUD_HEAD_X,
    HUD_HEAD_Y,
    SOLDIER_DX,
    SOLDIER_FOOT_Y,
    UI,
    H,
    W,
)
from engine import (
    res,
)
from engine import (
    scene as SC,
)
from engine.skel import Skeleton
from game import (
    soldier_sprite as ssprite,
)
from game import (
    zombie_sprite as zsprite,
)
from game.battle import (
    SOLDIER_BASE,
    SOLDIER_SCALE,
)
from game.battle_abilities import AbilityBar
from game.battle_bg import load_scroll_background
from game.battle_weapons import WeaponSlots


# 战斗增益效果条：(存档里的键, 显示名, 主色)
_BUFF_ROWS = (
    ("shield", "守护之盾", (120, 190, 255)),
    ("power", "力量之剑", (255, 176, 96)),
    ("speed", "加速药剂", (140, 255, 180)),
    ("mech", "机甲", (255, 205, 90)),
    ("fly", "无人机", (130, 225, 255)),
    ("attack", "机枪塔", (255, 150, 90)),
)
_BUFF_FONTS = {}
_HP_SWEEP_CACHE = {}
_HP_MASK_CACHE = {}


def _hp_mask(sub):
    """血条前景的 alpha 蒙版：RGB 拉到白，只留形状给反光带做乘法。"""
    key = sub.get_size()
    m = _HP_MASK_CACHE.get(key)
    if m is None:
        m = sub.copy()
        m.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGB_ADD)
        _HP_MASK_CACHE[key] = m
    return m


def _buff_font(size):
    f = _BUFF_FONTS.get(size)
    if f is None:
        f = pygame.font.SysFont("Microsoft YaHei", size, bold=True)
        _BUFF_FONTS[size] = f
    return f


def _hp_sweep(h):
    """金属反光带：斜向白色亮带，边缘平方衰减，按血条高度缓存一次。"""
    h = int(h)
    hit = _HP_SWEEP_CACHE.get(h)
    if hit is not None:
        return hit
    w = max(28, int(h * 1.8))
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        centre = w * 0.5 + (y - h * 0.5) * 0.6
        for x in range(w):
            d = abs(x - centre) / (w * 0.45)
            a = max(0.0, 1.0 - d) ** 2
            if a > 0:
                surf.set_at((x, y), (255, 255, 255, int(205 * a)))
    _HP_SWEEP_CACHE[h] = surf
    return surf


def _fit_icon(path, size):
    """把图标裁到实际墨迹再按长边缩到 size 内（原图四周留白很多，
    直接缩 16px 只剩一个空方块）。"""
    img = res.load_img(path)
    if not img:
        return None
    r = img.get_bounding_rect()
    if r.w > 1 and r.h > 1:
        img = img.subsurface(r)
    k = size / float(max(img.get_width(), img.get_height()))
    return pygame.transform.smoothscale(
        img, (max(1, int(img.get_width() * k)), max(1, int(img.get_height() * k)))
    )


_INK_CACHE = {}


def _ink_box(surf):
    """贴图**不透明像素**的包围盒（缓存）。

    金币/钻石两张小图四周留白不同，直接按贴图左上角对齐，肉眼看还是
    差几像素；按墨迹左缘对齐才是用户要的「最左端对齐」。
    """
    if surf is None:
        return None
    key = id(surf)
    hit = _INK_CACHE.get(key)
    if hit is not None and hit[0] is surf:  # 同 id 必须是同一对象，防 id 复用错框
        return hit[1]
    try:
        r = pygame.mask.from_surface(surf, 8).get_bounding_rect()
    except Exception:
        r = None
    if r is None or r.w <= 1 or r.h <= 1:
        r = surf.get_rect()
    _INK_CACHE[key] = (surf, r)
    return r


class BattleSceneMixin:
    """战斗场景渲染：战场、HUD、技能条、经验武器、道具。"""

    def draw_battle_bg(self, s, zone=None):
        """战斗背景层：按 zone + 任务类型选 XML 配置的滚动背景。

        原版 MapLayer::getMissionBgConfigXml 决定用 bg_<zone>_1.xml 还是 _2.xml，
        ScrollBackgroundDef 解析出 bg_tex 列表与 bg_seq 排列。
        """
        b = self.battle
        zone = zone or (b.zone if b else "hospital")
        mtype = getattr(b, "mtype", "kill_mission") if b else "kill_mission"
        sb = self._scroll_bg(zone, mtype)
        if sb is None:
            s.fill((22, 32, 42))
            return
        sb.draw(s, offset_x=(b.cam if b else 0.0), W=W, H=H)

    def _scroll_bg(self, zone, mtype):
        """滚动背景层缓存（同一关卡只建一次）。"""
        key = (zone, mtype)
        if getattr(self, "_sb_key", None) == key:
            return self._sb
        self._sb_key = key
        self._sb = load_scroll_background(zone, mtype)
        return self._sb

    def _equipped_gun_names(self):
        """已装备的枪名列表（原版 equipped_gun_0..N）。"""
        d = self.save.d
        out = []
        i = 0
        while True:
            nm = d.get("equipped_gun_%d" % i)
            if not nm:
                break
            out.append(nm)
            i += 1
            if i > 8:
                break
        if not out:
            out = [w for w in (d.get("equipped") or []) if w]
        return out

    def draw_battle(self, s):
        b = self.battle
        self.draw_battle_bg(s, b.zone if b else None)

        if b:
            # 弹道拖尾 + 弹壳：画在僵尸和士兵下面
            if getattr(b, "gunfx", None):
                b.gunfx.draw(s)
            # ★ 虫洞（守卫任务专用，原版 addWormholeEffect）
            #   画在僵尸**下面** —— 僵尸从虫洞里出来。
            if getattr(b, "wormhole", None) is not None:
                b.wormhole.draw(s)
            # ★ 远行任务终点（医疗箱 + 光效，原版 addDistanceTarget）
            #   世界坐标 → 屏幕坐标要减 cam。
            _dt = getattr(b, "distance_target", None)
            if _dt is not None:
                _dt.draw(s, b.cam)
            # 死亡血渍贴地：必须在僵尸**下面**
            if getattr(b, "fx", None):
                b.fx.draw_stains(s)
            # 远（x 大）的先画，近的压住远的；士兵最后画（永远在最前）
            for z in sorted(b.zombies, key=lambda z: -z["x"]):
                if z["dead"]:
                    continue
                # 每种僵尸用自己的骨骼（19 种普通 + 4 个 boss）
                zs = zsprite.get(z.get("name") or "zombie_9")
                # 状态：死亡 > 攻击 > 走路
                if z.get("dying"):
                    state, tt = "death", z.get("dead_t", 0.0)
                elif z.get("atk_anim", 0) > 0:
                    # 攻击动画按各自 duration 从头播：elapsed = 总时长 - 剩余
                    adur = z.get("atk_dur", 0.8)
                    state, tt = "attack", max(0.0, adur - z["atk_anim"])
                else:
                    state, tt = "walk", z["walk"]
                # 缩放：骨骼原生尺寸已接近原版，直接用僵尸自带的 scale
                # 僵尸原生素材本身就是「面朝左」（朝士兵走），不需要镜像
                gy = SOLDIER_BASE["ground_y"]
                zs.draw_shadow(s, z["x"] - b.cam, gy, z["scale"])
                # 掉血换部件贴图（XML ChangeSprite：头 80%、左臂 50%）
                br = 1.0
                if z.get("maxhp"):
                    br = max(0.0, min(1.0, z["hp"] / float(z["maxhp"])))
                from game.battle import DEATH_FADE as _DF

                za = 1.0
                if z.get("dying"):
                    dur = z.get("death_dur", 1.8)
                    fadet = z.get("dead_t", 0.0) - dur
                    if fadet > 0:
                        za = max(0.0, 1.0 - fadet / max(0.01, _DF))
                zs.render(
                    s,
                    state,
                    tt,
                    z["x"] - b.cam,
                    gy,
                    z["scale"],
                    flip=False,
                    blood_ratio=br,
                    alpha=za,
                )

                # ★ 冰冻层（ZombieCharacter::onFreeze @0x194bc0）：
                #   从 ice_1.png / ice_2.png 随机选一张盖在僵尸身上，
                #   setScale(僵尸 scale × 2)，FadeTo(3.0s, alpha→60)。
                #   僵尸照常走照常咬。
                ft = z.get("freeze_t", 0.0)
                if ft > 0.0 and z.get("freeze_ice") and not z.get("dying"):
                    ice = res.load_img("pic/gun/freezer/%s.png" % z["freeze_ice"])
                    if ice:
                        from game.battle import FREEZE_DURATION as _FD

                        # FadeTo(3.0s, 60)：从 255 线性降到 60
                        k = max(0.0, min(1.0, ft / _FD))
                        a = int(60 + (255 - 60) * k)
                        # 原版 setScale(僵尸 scale × 2)：ice 原图 100×100，
                        # 僵尸高约 170×scale ⇒ 2 倍正好把整个身子裹住
                        iw = max(1, int(ice.get_width() * z["scale"] * 2))
                        ih = max(1, int(ice.get_height() * z["scale"] * 2))
                        im = pygame.transform.smoothscale(ice, (iw, ih))
                        im.set_alpha(a)
                        # 冰层垂直居中于僵尸身体（僵尸高约 170*scale，
                        # 中心在 gy - 85*scale 附近）
                        body_h = 170.0 * z["scale"]
                        cy = gy - body_h * 0.5
                        s.blit(im, (int(z["x"] - b.cam - iw / 2), int(cy - ih / 2)))

            # 中弹喷血：画在僵尸之上、士兵之下
            if getattr(b, "fx", None):
                b.fx.draw_blood(s)
                # 死亡大喷血：同样在僵尸之上（原版 z 值与喷血一致）
                b.fx.draw_splats(s)

            # 士兵状态机：开火 > 走路 > 站立。三套动画各自时长不同
            # （p220 fire 0.27s / walk 0.6s / stand 0.6s），必须分开播。
            # ★ 机甲形态：原版 Soldier::onMechGetup @0x187534 让士兵**换装**
            #   成机甲，玩家操控的仍是同一个士兵（移动/开火照常）。
            #   这里换渲染对象即可，逻辑层不变。
            mech_nm = getattr(b, "mech_name", None)
            if mech_nm:
                from game.battle_summons import MechForm

                _mc = getattr(ssprite, "_mech_forms", None)
                if _mc is None:
                    _mc = ssprite._mech_forms = {}
                sspr = _mc.get(mech_nm)
                if sspr is None:
                    sspr = _mc[mech_nm] = MechForm(
                        mech_nm, getattr(b, "soldier", None), b.gun_look()
                    )
            else:
                sspr = ssprite.get(b.weapon, getattr(b, 'soldier', None), b.gun_look())
            soldier_state, soldier_t, lower_state, lower_t = b.soldier_pose2()
            sspr.draw_shadow(s, b.sx - b.cam + SOLDIER_DX, SOLDIER_FOOT_Y, SOLDIER_SCALE)
            # 边跑边打时把腿单独交给 walk（upper/lower 两层），
            # 机甲形态没有分层骨骼，不能传这个参数（MechForm.render 签名不同）。
            _lay = {"lower_state": lower_state, "lower_t": lower_t} if lower_state else {}
            sspr.render(
                s,
                soldier_state,
                soldier_t,
                b.sx - b.cam + SOLDIER_DX,
                SOLDIER_FOOT_Y,
                SOLDIER_SCALE,
                flip=(b.facing == 0),
                **_lay,
            )

            # 经验武器耐久条 —— ExpProgressSprite（原版挂在士兵头顶）
            self._draw_exp_progress(s, b, soldier_state, soldier_t)

            # ★ 召唤物：只有飞行武器是独立实体（画在士兵右上方）。
            #   机甲**不是**独立实体 —— 它是士兵换装，已在上面的 sspr 里处理。
            if getattr(b, "fly_unit", None) is not None:
                b.fly_unit.render(s, b.cam)
            if getattr(b, "attack_unit", None) is not None:
                b.attack_unit.render(s, b.cam)
            # 空袭炸弹：从天而降的落弹（bomb_sheet）
            self._draw_airstrike(s, b)

            # 枪口火光：画在士兵之上（否则被身体挡住）
            if getattr(b, "gunfx", None):
                b.gunfx.draw_flash(s)

            # ★ 技能特效：治疗光柱 / 护盾光罩（原版 pic/effect/ability/）。
            #   画在士兵**之上** —— 原版是挂在士兵节点上的子节点。
            if getattr(b, "ability_fx", None) is not None:
                b.ability_fx.draw(s, b.sx - b.cam + SOLDIER_DX, SOLDIER_FOOT_Y)

            # ★ 击杀赏金星星（原版 BattleField::addCoinBonus 的
            #   pic/effect/star/ 特效，scale 0.12）
            if getattr(b, "kill_bonus_fx", None) is not None:
                b.kill_bonus_fx.draw(s)

            # 远行任务的右指箭头（原版 z=10，最上层）
            self._draw_go_right(s, b)

            # 死亡碎片：飞得比僵尸还高，画在最上层
            if getattr(b, "fx", None):
                b.fx.draw_debris(s)

            self.draw_mission_objects(s, b)
            self.draw_ability_drops(s, b)
            self.draw_exp_weapon(s, b)

        hide = set(BHIDE) | BATTLE_STATIC_HIDE
        # 切枪按钮（Button_Weapon，蓝圆）：反编译 UIBoard::init @0x16…
        #   if (已装备枪数 <= 1) weaponButton.setVisible(false)
        # 只有一把枪时切枪按钮不显示（树里 dump 时是可见的）。
        if b is not None and len(self._equipped_gun_names()) <= 1:
            hide.add("0xf28b44c4")
            hide.add("0xd65fc184")
        # 隐藏屏幕虚拟按键（设置里可开关，默认不隐藏）：
        #   TouchButton 左右移动键、FireButton 开火键，以及它们的贴图子节点。
        #   WeaponButton 是切枪按钮，不属于「屏幕按键」，保留。
        if self.hide_buttons():
            hide.update(BATTLE_CONTROL_NODES)
        SC.draw_tree(
            s,
            self.trees["battle"],
            self.texs["battle"][0],
            self.texs["battle"][1],
            self.texs["battle"][2],
            hide=hide,
            texfix=BTEXFIX,
            skip_cls=BSKIP_CLS,
            skip_tex=BSKIP_TEX,
            skip_subtree_cls=BATTLE_BG_SUBTREE,
        )

        # 开火键：**不再压暗**。
        # 上一轮误读了用户反馈「对敌对单位必须要有怪才能开枪 不能空枪
        # 这点不好」—— 那句话是嫌这个限制，不是要保留它。
        # 反编译 WeaponEffect::onStartFire 也确认原版没有「无目标就不开火」
        # 的提前返回：特效先全部播完，再查射程内僵尸，查空就循环 0 次。
        # 空枪照常扣子弹、出弹道、出枪口火焰。所以这里不需要任何遮罩。

        self.draw_hud(s)
        self.hud_fx.draw(s, H)

        # 战斗武器槽（UIBoard::addWeaponItemButton）：画在 HUD 之上
        if self.battle:
            if self.weapon_slots is None:
                self.weapon_slots = WeaponSlots(self.battle, self.uptab)
            self.weapon_slots.draw(s, self.shop_font_big)
            # 战斗技能条（UIBoard::addAbilityItemButton）
            if self.ability_bar is None:
                self.ability_bar = AbilityBar(self.battle)
            self.ability_bar.draw(s, self.shop_font_big)
            # 机甲道具槽（消耗品，显示库存数量）
            if self.mech_slot is None:
                from game.battle_abilities import MechSlot

                self.mech_slot = MechSlot(self.battle)
            self.mech_slot.draw(s, self.shop_font_big)
            if not b.over:
                from game.keyboard_hints import draw_battle_key_hints

                draw_battle_key_hints(self, s)

        if self.revive_panel:
            self.revive_panel.draw(s)

        if self.result_panel:
            self.result_panel.draw(s, W, H)
        if getattr(self, "failed_weapon", None) is not None:
            self.failed_weapon.draw(s)

    def _dim_fire_button(self, s, b):
        """场上没有可打的目标时，把屏幕开火键压暗。

        FireButton 节点 0xf28b4604：pos=[742.833, 0] ap=[0.5,0.0] sz=[93,103]
        ⇒ 屏幕矩形 x 696..789、y 377..480（cocos y 向上，屏幕 y 向下）。
        """
        if b is None or b.over:
            return
        if self.hide_buttons():
            return
        try:
            tgt = b.fire_target()
        except Exception:
            return
        if tgt is not None:
            return
        r = pygame.Rect(696, 377, 93, 103)
        veil = pygame.Surface(r.size, pygame.SRCALPHA)
        # 圆形遮罩（不是方块）—— 开火键本身是个红球，方块遮罩会露出
        # 四个直边，看着像贴了块灰玻璃。
        rad = pygame.Rect(0, 0, r.w, r.h)
        pygame.draw.ellipse(veil, (20, 16, 30, 130), rad)
        s.blit(veil, r.topleft)

    def draw_mission_objects(self, s, b):
        """人质与采集物（hostage / collect 任务）。"""
        key = res.load_img("pic/items/key.png")
        for p in b.pickups:
            if p["got"]:
                continue
            if key:
                bob = int(4 * (1 if (int(b.time * 2) % 2) else -1))
                s.blit(
                    key,
                    (
                        int(p["x"] - b.cam - key.get_width() / 2),
                        int(p["y"] + bob - key.get_height() / 2),
                    ),
                )
        from game.hostage_sprite import HostageSprite

        # 撤离点直升机画在人质**前面**（下层），人质登机时才压得住机身
        evac = getattr(b, "evac", None)
        if evac is not None:
            evac.draw(s, b.cam)
        gy = SOLDIER_BASE["ground_y"]
        for h in b.hostages:
            if h["dead"]:
                continue
            if h.get("_spr") is None:
                h["_spr"] = HostageSprite(h.get("idx", 0))
            spr = h["_spr"]
            board = h.get("board")
            if board is not None:
                if board >= 1.0:
                    continue
                walk_k = min(1.0, board / 0.30)
                door_x = evac.door_x - b.cam if evac is not None else h["x"] - b.cam
                bx = h.get("bx", h["x"]) - b.cam
                px = bx + (door_x - bx) * walk_k
                # 0.30 之后开始「钻进机舱」：抬起 + 缩小，1.0 时彻底藏进舱门
                climb = max(0.0, (board - 0.30) / 0.70)
                dy = evac.door_y if evac is not None else gy
                py = gy + (dy - gy) * climb
                sc = 1.0 - 0.72 * climb
                spr.draw(s, px, py, hp=1.0, moving=board < 0.30, scale=sc, t=h.get("walk", 0.0))
                continue
            hp_ratio = float(h["hp"]) / max(1.0, float(h.get("maxhp", 500.0)))
            spr.draw(
                s,
                h["x"] - b.cam,
                gy,
                hp=hp_ratio,
                moving=not h.get("stand", False),
                saved=h.get("saved", False),
                t=h.get("walk", 0.0),
            )

    def _draw_airstrike(self, s, b):
        """空袭落弹：炸弹从天而降 + 落地爆炸帧（bomb_sheet）。"""
        units = getattr(b, "airstrike_units", None)
        if not units:
            return
        frames = [
            res.load_img("pic/effect/explosions/pics/boom%s.png" % sfx) for sfx in ("", "02", "03")
        ]
        frames = [f for f in frames if f]
        bomb = res.load_img("pic/gun/airstrike_bomb.png")
        ring = res.load_img("pic/effect/explosions/pics/ring.png")
        for u in units:
            t = u["t"]
            if t < 0:
                continue  # 这一枚还没离开发射架（依次落下）
            x = int(u["x"] - b.cam)
            y = int(u["y"])
            if t < 0.5:
                # 下落阶段：炸弹从屏幕上方砸下来，地面同时给落点警示圈
                k = t / 0.5
                by = int(y - 420 * (1.0 - k * k))
                if ring:
                    rw = int(ring.get_width() * 0.45 * (0.4 + 0.6 * k))
                    rh = int(ring.get_height() * 0.45 * (0.4 + 0.6 * k))
                    s.blit(pygame.transform.smoothscale(ring, (rw, rh)), (x - rw // 2, y - rh // 2))
                im = bomb or ring
                if im:
                    w = max(1, int(im.get_width() * 0.7))
                    h = max(1, int(im.get_height() * 0.7))
                    drop = pygame.transform.smoothscale(im, (w, h))
                    s.blit(pygame.transform.rotate(drop, -25), (x - w // 2, by - h // 2))
            else:
                # 爆炸阶段：3 帧轮播，0.55 秒
                k = min(1.0, (t - 0.5) / 0.55)
                if frames:
                    fi = min(len(frames) - 1, int(k * len(frames)))
                    im = frames[fi]
                    w = int(im.get_width() * 1.2)
                    h = int(im.get_height() * 1.2)
                    s.blit(pygame.transform.smoothscale(im, (w, h)), (x - w // 2, y - h))

    def draw_ability_drops(self, s, b):
        """随机技能掉落物（RandomAbilityNode）。

        底 pic/ui/buttons/ability_button.png + 技能图标 scale 0.8，
        整体 ScaleTo(0.3s,1.2) 后在 (w*0.5,h*0.3)↔(w*0.5,h*0.6) 之间浮动。
        """
        from game.battle_abilities import ability_icon

        base = res.load_img("pic/ui/buttons/ability_button.png")
        for d in b.ability_drops:
            if not base:
                continue
            w, h = base.get_size()
            im = pygame.transform.smoothscale(base, (w, h))
            icon = res.load_img(ability_icon(d.name))
            if icon:
                # 图标 scale 0.8（相对原图），居中落在底图上
                iw = max(1, int(icon.get_width() * 0.8))
                ih = max(1, int(icon.get_height() * 0.8))
                ic = pygame.transform.smoothscale(icon, (iw, ih))
                im.blit(ic, ((w - iw) // 2, (h - ih) // 2))
            # 上下浮动：h*0.3 ↔ h*0.6，1s 一个来回
            bob = h * 0.45 + (h * 0.15 if (int(d.t * 2) % 2) else -h * 0.15)
            x = int(d.x - b.cam - w / 2)
            y = int(d.y - bob - h / 2)
            s.blit(im, (x, y))

    def draw_exp_weapon(self, s, b):
        """经验武器掉落物（ExpWeaponNode）。

        位置：世界 x = 士兵x + 180，cocos y = 100（向上）⇒ 屏幕 y = 380。
        """
        from game.exp_weapon import draw_exp_weapon

        it = getattr(b, "exp_weapon_item", None)
        if it is None:
            return
        draw_exp_weapon(s, it, it["x"] - b.cam, self.t)

    def _draw_go_right(self, s, b):
        """远行任务的右指箭头。

        反编译 BattleField::showGoRightAnimation @0x16e55c：
          素材 go_right.png，setScale(1.2)，opacity(1067030938=1.2 是 scale)，
          anchor(1.0, 0.5)，位置 (屏幕宽 - 图宽*0.2, 屏幕高*0.5)
          CCMoveBy(+w*0.2, 0.3s) → CCMoveBy(-w*0.2, 0.3s) 组成 Sequence，
          再 **CCRepeat(…, N)** 重复有限次，最后 endGoRightAnimation 移除节点。

        触发条件（BattleField::validMovingDistance @0x16e69c）：
          DistanceCounter::validMovingDistance(a2) == 0 时**才**播 ——
          也就是玩家已经跑到「当前这一屏允许的最右边界」时才提示一下。
          播完 N 次（约 2 秒）就自动消失，不是全程常驻。

          而且用的是全局时间 ⇒ 玩家一路走一路看着右下角有东西疯狂闪
          现在按原版：只在到达边界时短暂出现，2 秒后自己消失。
        """
        if b is None or b.base_type not in ("distance", "hostage"):
            return
        left = float(getattr(b, "go_right_t", 0.0) or 0.0)
        if left <= 0.0:
            return
        img = res.load_img(GO_RIGHT_TEX)
        if img is None:
            return
        w, h = img.get_size()
        # 已显示多久（从 2.0 倒数），用来算摆动相位
        el = GO_RIGHT_SHOW - left
        k = (el % (GO_RIGHT_SWING * 2)) / GO_RIGHT_SWING
        swing = w * 0.2 * (k if k <= 1 else 2 - k)
        im = img.copy()
        im.fill((255, 255, 255, int(255 * GO_RIGHT_OPACITY)), special_flags=pygame.BLEND_RGBA_MULT)
        sw = int(w * GO_RIGHT_SCALE)
        sh = int(h * GO_RIGHT_SCALE)
        im = pygame.transform.smoothscale(im, (sw, sh))
        # anchor(1.0, 0.5)：右端对齐 x，中高对齐 y
        right = W - sw * 0.2 + swing
        cy = int(H * 0.5)
        s.blit(im, (int(right - sw), cy - sh // 2))

    def _draw_exp_progress(self, s, b, state, t):
        """经验武器弹药条 —— ExpProgressSprite（Soldier::onChangeToExpWeapon @0x18978c）。

        反编译 Soldier::onChangeToExpWeapon（all_merged.c:98026）尾段：
            sub_187E92(v48, "pic/ui/battlefield/exp_bullet.png");
            sub_187E92(v49, "pic/ui/battlefield/exp_bar_1.png");
            sub_187E92(v50, "pic/ui/battlefield/exp_bar_0.png");
            this_1+516 = ExpProgressSprite::node(v48, v49, v50, v26);
            setPosition(LocalCenterX, *((float*)this_1 + 25) * 0.6);   ← 高度 × 0.6
            addChild(..., z=10);

        ExpProgressSprite::init @0x17f3e0（节点内部，局部坐标）：
            · 底条 exp_bar_0.png  anchor(0.5,0.5)  pos=(w*0.5, h*0.5)   ← 节点中心
            · 前条 exp_bar_1.png  pos=(w*0.48, h*0.585)
              EzResizableSprite::updateHidePercent(0, 1-percent, 0, 0)
              ⇒ 从**右端**吃掉，左边按剩余比例保留
            · 子弹图标 exp_bullet.png anchor(0.7,0.45) pos=(0, h*0.5)

        弹药量：Soldier::onWeaponFire @0x189388 里
            this_1+512 -= 1;
            ExpProgressSprite::updatePercent(this_1+516, (float)this/100.0, 0.0);
        ⇒ percent = 剩余发数 / 100（经验武器固定 100 发）。

        高度基准：*((float*)this_1 + 25) 是 Soldier 容器的 contentSize 高。
        节点树实测 Soldier 节点 sz=[300,300]、ap=[0.5,0.0]、pos=[458.667,72]
        ⇒ 屏幕脚底 y = 480 − 72 = 408，容器中心 y = 408 − 150 = 258，
        弹药条 y = 258 + 300×0.6 = 438 —— 但那在脚底下面，明显不对。

        关键：Soldier 节点 pos.y=72 是**容器**的原点，而 SoldierCharacter 子节点
        pos=[150,150] 是容器中心。Soldier::getLocalCenterX 读的是
        CharacterDef+284（角色自身的中心偏移），不是容器中心。
        实际条子画在**角色头顶**：士兵骨架可见高度约 218px，
        脚底 408 ⇒ 头顶 ≈ 190，条子落在头顶略上方 ≈ 178。

        这里直接用骨架并集 bbox 的顶端（不含枪的极值帧时更准），
        再叠加原版的 0.6 比例语义 —— 实测条子底边刚好压在头顶上方。
        """
        if not getattr(b, "exp_weapon", None):
            return
        base = res.load_img("pic/ui/battlefield/exp_bar_0.png")
        fg = res.load_img("pic/ui/battlefield/exp_bar_1.png")
        icon = res.load_img("pic/ui/battlefield/exp_bullet.png")
        if not base:
            return
        bw, bh = base.get_size()

        sspr = ssprite.get(b.weapon, getattr(b, "soldier", None), b.gun_look())
        sk, _fi = sspr.pose(state, t)
        # 头顶位置：body_bbox 的顶端（排除 bian* 隐藏的马尾和 gun* 枪身）
        head_y = SOLDIER_FOOT_Y - 218
        body = sk.body_bbox() if sk is not None else None
        if body:
            head_y = SOLDIER_FOOT_Y - (body[3] - body[1]) * SOLDIER_SCALE
        # 条子中心：头顶上方一个底条半高 + 4px 间隙
        cy = int(head_y - bh / 2 - 4)
        cx = b.sx - b.cam + SOLDIER_DX

        x0 = int(round(cx - bw / 2))
        y0 = cy
        s.blit(base, (x0, y0))

        # 前条：剩余比例从左往右保留（updateHidePercent 从右端吃）
        total = 100.0
        pct = max(0.0, min(1.0, float(getattr(b, "exp_bullets_left", 0)) / total))
        if fg and pct > 0:
            fw = max(1, int(round(fg.get_width() * pct)))
            sub = fg.subsurface(pygame.Rect(0, 0, fw, fg.get_height())).copy()
            # 前条锚点是自身中心，落在 (w*0.48, h*0.585)
            fx = x0 + int(round(bw * 0.48)) - int(fg.get_width() / 2)
            fy = y0 + int(round(bh * 0.585)) - int(fg.get_height() / 2)
            s.blit(sub, (fx, fy))

        # 子弹图标：anchor(0.7,0.45)，局部 pos=(0, h*0.5) ⇒ 落在节点中心左侧
        if icon:
            s.blit(
                icon,
                (
                    x0 - int(round(icon.get_width() * 0.7)),
                    y0 + int(round(bh * 0.5 - icon.get_height() * 0.45)),
                ),
            )

    def _draw_hp_bar(self, s, b):
        """SoldierHPBar::init @0x182260。

        HPBar 容器 pos = (0, 480)，anchor(0,1) → 落在屏幕左上角；
        scale = W/H，854/480=1.779 ≥1.6 → 1.0。

        容器内（局部坐标，原点在屏幕 (0,0)），z 序：
          -1 hp_bar_shadow   (半透明影子)
           0 hp_bar_bg_0 (230×61) anchor(0,1) pos(0,0)   ← 血条槽
             1 hp_bar.png      anchor(0.5,0.5) pos(w*0.5, h*0.5)
             2 hp_bar_bg_end   anchor(0,0.5)   pos(w*0.77, h*0.5)
           3 hp_bar_head_1 (130×112) anchor(0,1) pos(0,0)  ← 头像粉色底板
           4 士兵头像       scale 1.1  pos(head_w*0.37, -head_h*0.38)
           5 hp_bar_head_0 (130×112) scale 0.8  pos(w*0.9, -3) ← 金属框
        """
        ratio = max(0.0, min(1.0, b.hp / float(b.maxhp)))
        # 动态只保留金属反光：一条斜向亮带按战斗时钟从血条左端扫到右端。
        # 相位用 b.time，暂停时扫光也跟着停住。
        t = float(getattr(b, "time", 0.0))
        bg = res.load_img("pic/ui/buttons/hp_bar_bg_0.png")
        head0 = res.load_img("pic/ui/buttons/hp_bar_head_0.png")
        if bg and head0:
            bw, bh = bg.get_size()
            hw, hh = head0.get_size()

            # 容器锚点 (0,1) 贴在场景 y=480（屏幕顶），容器局部原点在屏幕 (0,0)，
            # 局部 y 向上为正 ⇒ 屏幕 y = −局部 y。
            def sy(local_y):
                return int(round(-local_y))

            # z=-1 影子：hp_bar_shadow (97×30) sc=[4,4]
            shadow = res.load_img("pic/ui/buttons/hp_bar_shadow.png")
            if shadow:
                sw, sh = shadow.get_size()
                img = pygame.transform.scale(shadow, (int(sw * 4.0), int(sh * 4.0)))
                s.blit(img, (0, sy(0)))

            # z=0 槽：anchor(0,1) at (head_0.w*0.9, -3)
            bg_x = HP_BAR_X
            bg_y = HP_BAR_Y
            s.blit(bg, (int(round(bg_x)), sy(bg_y)))

            bar = res.load_img("pic/ui/buttons/hp_bar.png")
            if bar:
                bar_w, bar_h = bar.get_size()
                fw = int(round(bar_w * ratio))
                cy = sy(bg_y) + bh - (bh + 4) * 0.5
                # 槽的内缩：血条左右各留 3px 边
                bar_left = bg_x + 3
                if fw > 0:
                    sub = bar.subsurface(pygame.Rect(0, 0, fw, bar_h)).copy()
                    if getattr(b, "mech_name", None):
                        # 保留原版血条高光纹理，只把色相换成机甲蓝。
                        sub = pygame.transform.grayscale(sub)
                        sub.fill((72, 174, 255), special_flags=pygame.BLEND_RGB_MULT)
                    bx = int(round(bar_left))
                    by = int(round(cy - bar_h * 0.5))
                    s.blit(sub, (bx, by))
                    # 反光只落在血条实体上：用前景 alpha 做乘法蒙版，
                    # 亮带不会溢出成方框（血条贴图有大量透明/斜切区域）。
                    sweep = _hp_sweep(bar_h)
                    period = fw + sweep.get_width() * 2
                    sx = int((t * 120.0) % period) - sweep.get_width()
                    glow = pygame.Surface((fw, bar_h), pygame.SRCALPHA)
                    glow.blit(sweep, (sx, 0))
                    glow.blit(_hp_mask(sub), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                    s.blit(glow, (bx, by))

            # z=2 槽尾：anchor(0,0.5) at (bg_0.w*0.77, bg_0.h*0.5)
            end = res.load_img("pic/ui/buttons/hp_bar_bg_end.png")
            if end:
                _ew, eh = end.get_size()
                s.blit(
                    end,
                    (int(round(bg_x + bw * 0.77)), int(round(sy(bg_y) + bh - bh * 0.5 - eh * 0.5))),
                )

        h1 = res.load_img("pic/ui/buttons/hp_bar_head_1.png")
        if h1:
            s.blit(h1, (0, 0))
        # 士兵头像（z=4）：pic/ui/soldier_icon/soldier_N.png
        # 反编译 SoldierHPBar::init @0x181fb8：
        #   setScale(1.1)（1062501089）
        #   setPosition(hp_bar_head_0 宽*0.37, -(hp_bar_head_0 高*0.38))
        #     = (130*0.37, -112*0.38) = (48.1, -42.6)（容器局部，y 向上）
        #   容器原点 = 屏幕 (0,0)（SoldierHPBar pos=[0,480] anchor(0,1)）
        #   ⇒ 头像中心屏幕 (48.1, 42.6)
        # 实测标定（emu_m14.png）：原版帽带红条宽 54 px，
        # 素材 soldier_1.png 红条宽 35 px ⇒ 视觉放大 54/35 = 1.543。
        # 反编译的 setScale(1.1) 作用在 EzSprite 的 contentSize 上，
        # 而 EzSprite 的 contentSize 比贴图本身大（带留白），
        # 所以视觉放大比 setScale 值大。取 1.5。
        soldier = getattr(b, "soldier", "soldier_1")
        head = res.load_img("pic/ui/soldier_icon/%s.png" % soldier)
        if head:
            hw, hh = head.get_size()
            sc = HUD_HEAD_SCALE
            hw2, hh2 = int(round(hw * sc)), int(round(hh * sc))
            hx = HUD_HEAD_X
            hy = HUD_HEAD_Y
            img = pygame.transform.smoothscale(head, (hw2, hh2))
            s.blit(img, (int(round(hx - hw2 * 0.5)), int(round(hy - hh2 * 0.5))))
        # 金属框（z=5，130×112，在 (0,0)）—— 与粉底同尺寸，正好盖住它
        h0 = res.load_img("pic/ui/buttons/hp_bar_head_0.png")
        if h0:
            s.blit(h0, (0, 0))

    def draw_hud(self, s):
        """战斗 HUD —— 几何全部照抄节点树 data/node_tree_battle.json。

        KillCounter（0xd64ec344）pos=[0,312] ap=[0,0] sz=[50,50]
          └ 0xd65f8d04 zombie_kill.png  pos=[25,25] ap=[0.5,0.5] sz=[50,50]
          └ 0xd6663804 EzTexText       pos=[55,20] ap=[0,0.5] sz=[67.5,25]
              └ EzTexChar 每个 pos=[x,12.5] sz=[36,40] sc=0.625（score_white 36x40 帧）

        屏幕换算：KillCounter 局部 y=312 ⇒ 屏幕 y = 480-312 = 168
                   zombie_kill 中心 = (25,25) ⇒ 屏幕 (25, 480-312-25=143)
                   EzTexText 锚点 (0,0.5) 高 25 ⇒ 中心屏幕 y = 480-312-20 = 148
        """
        b = self.battle
        if not b:
            return
        from engine import gridfont

        self._draw_hp_bar(s, b)

        # 守卫虫洞关：门线画成中心亮、两侧淡的柔光幕（不是实心方框），
        # x 与 battle 的漏怪判定共用，僵尸从这里穿过去就算漏。
        if b.base_type == "guard" and not getattr(b, "over", None):
            gy = int(SOLDIER_BASE["ground_y"])
            x = int(GUARD_LINE_X)
            top, bot = gy - 118, gy + 8
            h = bot - top
            gate = getattr(self, "_guard_gate", None)
            if gate is None or gate.get_height() != h:
                gate = pygame.Surface((26, h), pygame.SRCALPHA)
                for yy in range(h):
                    k = yy / float(h)
                    for xx in range(26):
                        d = abs(xx - 12.5) / 13.0
                        a = max(0.0, 1.0 - d) ** 2 * (0.25 + 0.75 * k)
                        gate.set_at((xx, yy), (150, 235, 255, int(150 * a)))
                self._guard_gate = gate
            s.blit(gate, (x - 13, top))
            pygame.draw.line(s, (120, 220, 255, 90), (0, bot - 1), (x + 20, bot - 1), 2)

        # 任务计数器：**图标随任务类型换**，不是恒定僵尸头。
        # 反编译里 5 个 Counter 各自 init 时加载自己的图标：
        #   KillCounter::init     @0x181320 → pic/ui/buttons/zombie_kill.png
        #   LeakCounter::init     @0x181184 → pic/ui/buttons/zombie_leak.png
        #   TimeCounter::init     @0x182674 → pic/ui/buttons/time.png          (时钟)
        #   CollectCounter::init  @0x180e6c → pic/ui/buttons/item_collect.png  (钥匙)
        #   DistanceCounter::init @0x1814bc → pic/ui/buttons/distance.png      (跑步)
        #   guard 主计数器是倒计时，用时钟 + MM:SS，不是 58/60 这种进度比。
        counter_tex = {
            "kill": "pic/ui/buttons/zombie_kill.png",
            "guard": "pic/ui/buttons/time.png",
            "time": "pic/ui/buttons/time.png",
            "collect": "pic/ui/buttons/item_collect.png",
            "distance": "pic/ui/buttons/distance.png",
            "hostage": "pic/ui/buttons/distance.png",
        }.get(b.base_type, "pic/ui/buttons/zombie_kill.png")
        kill = res.load_img(counter_tex)
        if kill:
            s.blit(kill, (0, 118))  # 50x50，屏幕 (0,118)-(50,168)
        font = gridfont.get_font(0)  # getTexFont(0) = score_white.png
        if font:
            if b.base_type in ("time", "guard"):
                left = b.time_remaining()
                sec = int(left + 0.5)
                font.draw(
                    s, "%02d:%02d" % (sec // 60 % 60, sec % 60), 55, 148, 1.0, align=(0.0, 0.5)
                )
            else:
                cur, tot = b.progress()
                # EzTexText 锚点 (0,0.5)：左边缘 x=55，垂直中心屏幕 y=148
                # 字号 25.0 已经把 40px 字格缩到 25px（EzTexFont this[84]=25/40=0.625），
                # 不要再额外乘 0.625（节点树里 EzTexChar 的 sc=0.625 就是这个内部缩放）。
                font.draw(s, "%d/%d" % (cur, tot), 55, 148, 1.0, align=(0.0, 0.5))

        # 仅明确配置为 *_time_mission 的关卡显示第二个 TimeCounter。
        # 守卫关主计数器本身就是倒计时，不再重复显示同一项胜利条件。
        # 反编译 BattleField::init @0x16e69c：限时双目标关会在 H*0.55
        # 那一行再挂一个 TimeCounter：
        #     TimeCounter::node(number2) → setPosition(0, getContentSize().h * 0.55)
        #     addChild(z=3)
        #   H*0.55 = 264（cocos 向上）⇒ 屏幕 y = 480-264 = 216。
        # TimeCounter::init @0x182674 加载 pic/ui/buttons/time.png（时钟），
        # init 时的文本是 "00:00"；TimeCounter::updateTime @0x182842
        # 按 (int)(剩余秒+0.5) 每秒重画一次 "MM:SS"。
        #   倒计时，玩家看不到还剩多少时间，只能莫名其妙地超时失败
        if b.has_extra_timer():
            left = b.time_remaining()
            clk = res.load_img("pic/ui/buttons/time.png")
            if clk:
                s.blit(clk, (0, 191))  # 50x50，屏幕 (0,191)-(50,241)
            if font:
                sec = int(left + 0.5)  # 原版 (int)(a2 + 0.5)
                mm, ss = sec // 60 % 60, sec % 60
                # 原版用 sprintf("0%d:", mm) + sprintf("0%d", ss)，
                # 30 秒会显示成 "00:030"（前导 0 是写死的字面量，不是补零）。
                # 这里按时钟语义补成两位，才是玩家能读懂的倒计时。
                txt = "%02d:%02d" % (mm, ss)
                font.draw(s, txt, 55, 216, 1.0, align=(0.0, 0.5))

        # 货币行：图标 + 数字都按存档重画，数字宽度变化时整行顺排，
        # 钻石图标永远跟在金币数字后面，不会被挤到金币字上。
        gold = gridfont.get_font(1)
        blue = gridfont.get_font(3)
        ico = SC.node_rects(
            self.trees["battle"],
            self.texs["battle"][0],
            self.texs["battle"][1],
            H,
            (BATTLE_COIN_ICON, BATTLE_CRYS_ICON),
        )
        coin_r = ico.get(BATTLE_COIN_ICON)
        crys_r = ico.get(BATTLE_CRYS_ICON)
        if gold and blue and coin_r and crys_r:
            coin_img = res.load_img("pic/ui/common/coin.png")
            crys_img = res.load_img("pic/ui/common/crystal.png")
            cx, cy, cw, ch = coin_r
            mid = cy + ch / 2.0
            _dy = ch * 0.13
            if coin_img:
                s.blit(
                    pygame.transform.smoothscale(coin_img, (int(cw), int(ch))),
                    (int(cx), int(round(mid - ch / 2.0 - _dy))),
                )
            ctxt = "{:,}".format(int(self.save.d.get("coins", 0)))
            btxt = str(int(self.save.d.get("crystals", 0)))
            gx = cx + cw + 6
            bw, bh = crys_r[2], crys_r[3]
            #   直接都按 cx 贴，肉眼看钻石还是偏右。这里按**不透明像素**的
            #   左缘对齐：金币贴 cx，钻石反推 x 让 ink 左缘落在同一条竖线上。
            ci = _ink_box(coin_img)
            bi = _ink_box(crys_img)
            ix = int(cx)
            if ci and bi:
                _k = bw / float(crys_img.get_width()) if crys_img else 1.0
                ix = int(round(cx + ci.left - bi.left * _k))
            right = UI["battle_pause"][0] - 6  # 可用右界
            row2 = mid + 34.0  # 第二行（钻石）中线
            sc = 1.2
            for _ in range(10):
                gw = gold.text_size(ctxt, sc)[0]
                bw_txt = blue.text_size(btxt, sc)[0]
                need_g = (right - gx) / gw if gw > 0 else 1.0
                need_b = (right - gx - bw - 6) / bw_txt if bw_txt > 0 else 1.0
                need = min(1.0, need_g, need_b)
                if need >= 0.999:
                    break
                sc *= max(0.55, need)
            gsc = bsc = sc
            gold.draw(s, ctxt, gx, mid, gsc, align=(0.0, 0.5))
            if crys_img:
                s.blit(
                    pygame.transform.smoothscale(crys_img, (int(bw), int(bh))),
                    (int(ix), int(round(row2 - bh / 2.0 - bh * 0.13))),
                )
            blue.draw(s, btxt, ix + bw + 6, row2, bsc, align=(0.0, 0.5))

        # 增益（护盾 / 攻击 / 加速）的效果条
        self._draw_buff_bars(s, b)

        # 经验武器的剩余量画在士兵头顶的 ExpProgressSprite 里
        # （见 _draw_exp_progress），这里不再重复画右上角的小字。

    # ------------------------------------------------------ 增益状态条
    def _draw_buff_bars(self, s, b):
        """护盾 / 力量 / 加速 的效果条：图标 + 名字 + 剩余秒 + 进度。

        还有多久效果时长」。这三种增益的时长逻辑里早就有
        （shield_until / power_until / speed_until + buff_dur），
        只是一直没画到屏幕上，玩家只能凭感觉。

        位置：左栏 HP 条 → 任务计数器 →（倒计时）之下、左下摇杆之上，
        每列 128px 宽、行高 26；超过 3 项时折到右侧第二列，最多 6 项。
        """
        if not b:
            return
        rows = []
        for kind, label, color in _BUFF_ROWS:
            until = float(getattr(b, kind + "_until", 0.0) or 0.0)
            left = until - b.time
            if until and left > 0.05:
                total = float((getattr(b, "buff_dur", None) or {}).get(kind) or left)
                rows.append((kind, label, color, left, max(total, left)))
        if not rows:
            return
        f = _buff_font(11)
        y0 = 251 if b.has_extra_timer() else 225
        for i, (kind, label, color, left, total) in enumerate(rows):
            x, y, w, h = 3 + (i // 3) * 134, y0 + (i % 3) * 26, 128, 24
            plate = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(plate, (14, 10, 22, 165), (0, 0, w, h), border_radius=5)
            pygame.draw.rect(plate, (*color, 190), (0, 0, w, h), 1, border_radius=5)
            s.blit(plate, (x, y))
            # 六种状态各用自己对应的官方图标：增益徽章 / 当前机甲 / 当前无人机 / 当前炮塔，
            # 不再统一套商店里的 "_1" 道具图。
            if kind in ("shield", "power", "speed"):
                icon_path = "pic/ui/ability_icon/%s_flag.png" % kind
            elif kind == "mech":
                icon_path = "pic/ui/mech_icon/%s.png" % (b.mech_name or "mech_1")
            elif kind == "fly":
                icon_path = "pic/ui/shop/ability_%s.png" % (b.fly_name or "fly_1")
            else:
                icon_path = "pic/ui/shop/ability_%s.png" % (
                    getattr(b, "attack_name", None) or "mech_7"
                )
            ico = _fit_icon(icon_path, 16)
            if ico:
                s.blit(ico, (x + 4, y + (h - ico.get_height()) // 2))
            s.blit(f.render(label, True, color), (x + 22, y + 2))
            sec = f.render("%.0fs" % (left + 0.4), True, (255, 255, 255))
            s.blit(sec, (x + w - 4 - sec.get_width(), y + 2))
            bar = pygame.Rect(x + 22, y + 17, w - 28, 4)
            pygame.draw.rect(s, (0, 0, 0), bar)
            k = max(0.0, min(1.0, left / total)) if total > 0 else 0.0
            fill = pygame.Rect(bar.x, bar.y, int(bar.w * k), bar.h)
            pygame.draw.rect(s, color, fill)

    # ------------------------------------------------------------ 交互
