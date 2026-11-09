"""战斗中的技能按钮与技能效果 —— 原版 UIBoard 的 AbilityItemButton 一族。

反编译依据（D:\\Code\\dsh\\full_dump\\all_merged.c）：

  AbilityDefCache::AbilityDefCache      技能定义表（硬编码 18 条）
  UIBoard::addAbilityItemButton @0x167ed4  技能按钮布局（按按钮数分 3 种模式）
  UIBoard::onTouchesBeganOnAbilityButton @0x167690  点击 → 触发 + 同类进冷却
  AbilityItemButton::init               按钮结构
  AbilityItemButton::createAbility @0x1796e8  按名字分派到具体技能类
  Soldier::recoverHP / speedUp / powerUp / shieldUp   四个效果

════════════════════════════════════════════════════════════════════
技能定义表（AbilityDef(name, 参数1, 参数2)）
════════════════════════════════════════════════════════════════════
  hp_1 (0.5, 0.5)      hp_2 (1.0, 0.5)        回血 maxHp * 参数1
  shield_1 (0.5, 15.0) shield_2 (1.0, 15.0)   护盾值 = 参数1，持续 15s
  speed_1 (0.5, 15.0)  speed_2 (1.0, 15.0)    速度倍率 = 参数1 + 1
  power_1 (0.5, 15.0)  power_2 (1.0, 15.0)    伤害倍率 = 参数1 + 1
  airstrike (1.0, 3.0)                          空袭
  mech_1/3/4/5/7/8/9/10 (0.0, 30~75)          召唤机甲
  fly_1 / fly_2 (0.0, 45.0)                     飞行武器

════════════════════════════════════════════════════════════════════
效果实现
════════════════════════════════════════════════════════════════════
  Soldier::recoverHP(a)   hp = min(maxHp, hp + maxHp * a)
  Soldier::speedUp(a)     速度倍率 = a + 1.0
  Soldier::powerUp(a)     伤害倍率 = a + 1.0
  Soldier::shieldUp(a)    护盾值 = a（抵挡伤害，15s 后失效）

════════════════════════════════════════════════════════════════════
按钮
════════════════════════════════════════════════════════════════════
  AbilityItemButton::init
      底     pic/ui/buttons/ability_button.png
      图标   技能图，scale 0.8
      遮罩   pic/ui/buttons/ability_button_ready.png
      冷却秒 font 0（score_white），scale 0.8，槽内 (0.8, 0.8)
  UIBoard::onTouchesBeganOnAbilityButton
      触发后同类技能 disable(progress)，时长 = 技能持续时间 + 0.2
"""

from contextlib import suppress

import pygame

from engine import res
from game.dialog import H, W


BUTTON_TEX = "pic/ui/buttons/ability_button.png"
READY_TEX = "pic/ui/buttons/ability_button_ready.png"

# AbilityDefCache 里的 18 条定义：name → (参数1, 参数2)
ABILITY_DEFS = {
    "hp_1": (0.5, 0.5),
    "hp_2": (1.0, 0.5),
    "shield_1": (0.5, 15.0),
    "shield_2": (1.0, 15.0),
    "speed_1": (0.5, 15.0),
    "speed_2": (1.0, 15.0),
    "power_1": (0.5, 15.0),
    "power_2": (1.0, 15.0),
    "airstrike": (1.0, 3.0),
    "mech_1": (0.0, 45.0),
    "mech_3": (0.0, 30.0),
    "mech_4": (0.0, 60.0),
    "mech_5": (0.0, 75.0),
    "mech_7": (0.0, 45.0),
    "mech_8": (0.0, 60.0),
    "mech_9": (0.0, 60.0),
    "mech_10": (0.0, 60.0),
    "fly_1": (0.0, 45.0),
    "fly_2": (0.0, 45.0),
}


def ability_kind(name):
    """createAbility 的分派：按名字子串选技能类。"""
    if "hp" in name:
        return "hp"
    if "speed" in name:
        return "speed"
    if "mech" in name:
        return "mech"
    if "power" in name:
        return "power"
    if "shield" in name:
        return "shield"
    if "airstrike" in name:
        return "airstrike"
    if "fly" in name:
        return "fly"
    return None


def ability_icon(name):
    """技能/机甲统一用商店正式图标，避免七代机甲读到不存在的目录。"""
    if name.startswith("mech_"):
        primary = "pic/ui/mech_icon/%s.png" % name
        if res.load_img(primary) is not None:
            return primary
    return "pic/ui/shop/ability_%s.png" % name


def is_need_disable(button_name, triggered):
    """AbilityItemButton::isNeedDisable：同类技能互斥规则。

    按钮是 airstrike → 只有同为 airstrike 才禁用
    按钮是 fly      → 只有同为 fly 才禁用
    刚触发的是 mech → 所有按钮都禁用
    其余            → 只有同名才禁用
    """
    if button_name == "airstrike":
        return button_name == triggered
    if button_name == "fly":
        return button_name == triggered
    if triggered == "mech":
        return True
    return button_name == triggered


class MechSlot:
    """战斗里的机甲道具槽。

    机甲是消耗品：军火库买几台就有几台库存，进关卡**不会**自动变身，
    玩家点一次扣 1 台，变身持续 ABILITY_DEFS 里的时长。
    槽上永远显示剩余数量，没库存就点不动。
    """

    SIZE = 86

    def __init__(self, battle):
        self.battle = battle
        # 右上角武器槽正下方：那里永远是空的，不会压到移动/开火/技能键
        self.rect = pygame.Rect(int(W) - self.SIZE - 14, 106, self.SIZE, self.SIZE)
        self.cool = 0.0
        self.name = None
        self.icon = None
        self.reload()

    # ---------------------------------------------------------- 数据
    def reload(self):
        save = getattr(self.battle, "save", None)
        d = getattr(save, "d", {}) if save is not None else {}
        name = d.get("equipped_mech")
        if not name:
            # 买了机甲但没在军火库里点「装备」时，自动用库存里的第一台，
            # 否则玩家进关卡根本看不到道具槽。
            for nm, c in (d.get("mech_count") or {}).items():
                if isinstance(c, int) and c > 0:
                    name = nm
                    break
        self.name = name
        self.icon = res.load_img("pic/ui/mech_icon/%s.png" % self.name) if self.name else None

    def count(self):
        save = getattr(self.battle, "save", None)
        if save is None or not self.name:
            return 0
        if hasattr(save, "mech_count"):
            return int(save.mech_count(self.name) or 0)
        return 0

    # ---------------------------------------------------------- 交互
    def visible(self):
        return bool(self.name)

    def hit(self, pos):
        return self.visible() and self.rect.collidepoint(pos)

    def trigger(self):
        """返回 (是否成功, 提示语)。"""
        b = self.battle
        if b.mech_name is not None:
            return False, "机甲已在场"
        if self.cool > 0:
            return False, None
        if not self.name:
            return False, "没装备机甲"
        if self.count() <= 0:
            return False, "机甲用完了"
        dur = ABILITY_DEFS.get(self.name, (0.0, 45.0))[1]
        b.call_mech(self.name, dur)
        save = b.save
        if hasattr(save, "use_mech"):
            save.use_mech(self.name)
            save.save()
        self.cool = dur
        self.reload()
        return True, None

    def remaining(self):
        """变身剩余秒数，以 Battle 的战斗时钟为**唯一真相源**。

        三条路径（进关卡自动变身 / 经验武器拾取 / 技能栏）根本不碰
        MechSlot；槽一旦被重建（start_mission、面板返回）cool 也归零。
        实机表现就是「机甲在场却看不到倒计时」「暂停回来倒计时没了」——
        """
        b = self.battle
        if getattr(b, "mech_name", None) is None:
            return max(self.cool, 0.0)
        return max(0.0, float(getattr(b, "mech_until", 0.0)) - float(getattr(b, "time", 0.0)))

    def update(self, dt):
        b = self.battle
        if getattr(b, "mech_name", None) is not None:
            # 机甲在场：每帧跟战场对齐，任何召唤路径 / 槽重建都能恢复
            self.cool = self.remaining()
        elif self.cool > 0:
            self.cool = max(0.0, self.cool - dt)

    # ---------------------------------------------------------- 绘制
    def draw(self, s, font=None):
        if not self.visible():
            return
        r = self.rect
        base = res.load_img(BUTTON_TEX)
        if base:
            s.blit(pygame.transform.smoothscale(base, r.size), r.topleft)
        if self.icon is not None:
            im = pygame.transform.smoothscale(self.icon, (r.w - 18, r.h - 18))
            s.blit(im, (r.x + 9, r.y + 9))
        n = self.count()
        f = pygame.font.SysFont("Microsoft YaHei", 20, bold=True)
        t = f.render("×%d" % n, True, (255, 236, 170) if n > 0 else (255, 120, 110))
        pad = 4
        plate = pygame.Surface((t.get_width() + pad * 2, t.get_height() + pad), pygame.SRCALPHA)
        pygame.draw.rect(plate, (18, 14, 26, 205), plate.get_rect(), border_radius=7)
        bx = r.right - plate.get_width() - 2
        by = r.bottom - plate.get_height() - 1
        s.blit(plate, (bx, by))
        s.blit(t, (bx + pad, by + pad // 2))
        # 冷却 / 变身中：压暗 + 倒计时（直接读战场剩余时间，
        # 即使这一帧 update 没跑——比如暂停面板开着——数字也不会跳/消失）
        cd = self.remaining()
        if cd > 0:
            # ★ 不要**正方形框**：用户反馈「倒数计时被一个正方形框框住不允许」。
            #   原版只把机甲按钮贴图本身压暗 + 中间一个数字，没有整块方形
            #   遮罩。这里改成椭圆内切压暗（边缘透明），倒计时数字直接
            #   压在图标中央，视觉上再也看不到方框。
            veil = pygame.Surface(r.size, pygame.SRCALPHA)
            pygame.draw.ellipse(
                veil,
                (10, 10, 20, 120),
                pygame.Rect(int(r.w * 0.06), int(r.h * 0.06), int(r.w * 0.88), int(r.h * 0.88)),
            )
            s.blit(veil, r.topleft)
            if font is not None:
                font.draw(s, str(int(cd) + 1), r.centerx, r.centery, 0.8, align=0.5)


class AbilityBar:
    """战斗界面上的技能按钮组。"""

    def __init__(self, battle):
        self.battle = battle
        self.rects = []  # [(rect, name)]
        self.cool = {}  # name → 剩余冷却秒数
        self._build()

    def _equipped(self):
        """存档 equipped_ability_0..2，且技能要已拥有才显示。"""
        save = getattr(self.battle, "save", None)
        d = getattr(save, "d", {}) if save else {}
        owned = set(d.get("owned_abilities") or [])
        out = []
        for i in range(3):
            nm = d.get("equipped_ability_%d" % i)
            if nm and nm in owned and nm in ABILITY_DEFS:
                out.append(nm)
        if not out:
            # 存档用 owned_abilities 存已装备技能（无 equipped_ability_N 时退回）
            out = [n for n in (d.get("owned_abilities") or []) if n in ABILITY_DEFS]
        return out

    def _build(self):
        names = self._equipped()
        n = len(names)
        if n <= 0:
            return
        # 原版分支公式会把第二、三个 80px 槽放回原点附近，造成整槽重叠。
        # 保留贴底和居中布局，只按真实槽宽重排，并留出可辨识的间隙。
        slot, gap = 80, 8
        count = min(3, n)
        group_w = count * slot + (count - 1) * gap
        x = round(W * 0.54 - group_w / 2)
        for nm in names[:3]:
            r = pygame.Rect(x, H - slot, slot, slot)
            self.rects.append((r, nm))
            x += slot + gap

    # ---------------------------------------------------------- 交互
    def hit(self, pos):
        for r, nm in self.rects:
            if r.collidepoint(pos):
                if self.cool.get(nm, 0.0) > 0:
                    return None  # 冷却中
                return nm
        return None

    def trigger(self, name):
        """触发技能。返回是否成功。

        UIBoard::onTouchesBeganOnAbilityButton：触发后同类技能进冷却，
        冷却时长 = 技能持续时间 + 0.2；
        AbilityItemButton::isNeedDisable 决定哪些按钮要一起禁用。
        """
        b = self.battle
        # ★ 冷却检查必须放在 trigger 里，不能只靠 hit()：
        #   键盘 Q/E/R 走 App._fire_ability → bar.trigger(name)，**不经过 hit()**，
        #   于是持续期间可以无限叠加同一技能（数值、特效、召唤物全都叠）。
        if self.cool.get(name, 0.0) > 0:
            return False
        # ★ 道具是消耗品：买几个能用几次。原来这里只放效果不扣库存，
        #   按钮上的 ×N 永远不减少，等于无限道具。
        save = getattr(b, "save", None)
        bag = getattr(save, "d", None) if save is not None else None
        stock = bag.get("abilities") if isinstance(bag, dict) else None
        if isinstance(stock, dict):
            left = int(stock.get(name, 0) or 0)
            if left <= 0:
                return False
        else:
            left = None
        _p1, p2 = ABILITY_DEFS.get(name, (0.0, 0.0))
        kind = ability_kind(name)
        if kind == "mech":
            b.call_mech(name, p2)
            b._ability_fx_once(1.2, (255, 215, 120), ability=name)
        elif kind == "fly":
            b.fly_weapon(name, p2)
            b._ability_fx_once(1.2, (150, 210, 255), ability=name)
        elif kind in ("hp", "speed", "power", "shield", "airstrike"):
            # ★ 统一走 Battle.apply_ability：数值效果 + 原版技能特效
            #   （RecoverHPAbility 的一次性光柱 / TemporaryAbility 的循环光罩）
            if b.apply_ability(name) is None:
                return False
        else:
            return False
        # 生效后才扣 1 个；扣完立刻落盘，退出关卡也不会把数量还回来
        if left is not None:
            stock[name] = left - 1
            with suppress(Exception):
                save.save()
        # 冷却：持续时间 + 0.2（UIBoard::onTouchesBeganOnAbilityButton）
        cd = p2 + 0.2
        self.cool[name] = cd
        # 互斥：isNeedDisable 命中的按钮一起进冷却
        # （原版按钮存的是技能**类型** hp/power/shield/speed/airstrike/mech/fly，
        #   不是完整技能名 hp_1 —— 所以这里用 ability_kind 归一）
        for _r, other in self.rects:
            if other == name:
                continue
            ok = ability_kind(other)
            if ok and is_need_disable(ok, kind):
                self.cool[other] = cd
        return True

    def update(self, dt):
        for k in list(self.cool):
            self.cool[k] -= dt
            if self.cool[k] <= 0:
                del self.cool[k]

    # ---------------------------------------------------------- 绘制
    def draw(self, s, font=None):
        base = res.load_img(BUTTON_TEX)
        ready = res.load_img(READY_TEX)
        for r, nm in self.rects:
            if base:
                s.blit(pygame.transform.smoothscale(base, r.size), r.topleft)
            icon = res.load_img(ability_icon(nm))
            if icon:
                iw = max(1, int(r.w * 0.72))
                ih = max(1, int(r.h * 0.72))
                im = pygame.transform.smoothscale(icon, (iw, ih))
                s.blit(im, (r.centerx - iw // 2, r.centery - ih // 2))
            _d = getattr(getattr(self.battle, "save", None), "d", {}) or {}
            _n = int((_d.get("abilities") or {}).get(nm, 0) or 0)
            _f = pygame.font.SysFont("Microsoft YaHei", 17, bold=True)
            _txt = "×%d" % _n
            _t = _f.render(_txt, True, (255, 236, 170) if _n > 0 else (255, 120, 110))
            _sh = _f.render(_txt, True, (24, 16, 8))
            _bx = r.right - _t.get_width() - 4
            _by = r.bottom - _t.get_height() - 2
            _pl = pygame.Surface((_t.get_width() + 6, _t.get_height() + 4), pygame.SRCALPHA)
            pygame.draw.rect(_pl, (18, 14, 26, 205), _pl.get_rect(), border_radius=6)
            s.blit(_pl, (_bx - 3, _by - 2))
            s.blit(_sh, (_bx + 1, _by + 1))
            s.blit(_t, (_bx, _by))
            cd = self.cool.get(nm, 0.0)
            if cd > 0 and ready:
                im = pygame.transform.smoothscale(ready, r.size)
                im = im.copy()
                im.set_alpha(200)
                s.blit(im, r.topleft)
