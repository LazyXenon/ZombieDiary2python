"""战斗界面的武器槽 —— 原版 UIBoard::addWeaponItemButton @0x168108。

反编译依据：
  UIBoard::init（武器槽创建循环）@0x14a…（all_merged.c 148595 附近）
      for i in 0..n-1:
          name = EzGameData::getKeyStringValue("equipped_gun_%d" % i)
          if name 非空:
              bullet = EzGameData::getKeyValue(name + "_bullet")
              icon  = Name2IconTex::getGunIcon(name)   → pic/ui/weapon_icon/gun_<name>.png
                                                         升级后 gun_<name>_<look>.png
              btn   = WeaponItemButton::node(icon, bullet)
              btn.setScale(v139)
              UIBoard::addWeaponItemButton(btn)
      v40 = 槽位数
      v139 = (板宽 * 0.5) >= 100 * v40 ? 1.0 : (板宽 * 0.5) / (100 * v40)

  UIBoard::addWeaponItemButton @0x168108
      anchor(1.0, 1.0)
      槽数 n = 已有槽位数；v6 = n（新增前）
      v7 = n * 槽宽（100）
      v8 = 板宽 - v7 * scale
      pos = (v8, 板高)
      ⇒ 第 i 个槽（0 起）：x = 板宽 - 100*scale*(n-i)，y = 板高

  WeaponItemButton::init @0x181f74
      contentSize = (100, 100)
      选中框 pic/ui/common/wp_select_box.png  anchor(0.5,0.5) at (w*0.5,h*0.5)
                                                 scale 0.7，初始 setVisible(false)
      枪图标     pic/ui/weapon_icon/gun_<name>.png  anchor(0.5,0.5) at (w*0.5,h*0.5)
                                                 scale 1.25
      没子弹时叠 pic/ui/buttons/bullet.png（anchor(0,0.2) at (w*0.15, 0)）
                与 pic/ui/buttons/bullet_light.png（anchor(0.5,0.5)，scale 0.6）
                子弹数 EzScoreText(getTexFont(0)=score_white) scale 0.6
                anchor(0,0) at (w*0.37, 0)

  WeaponItemButton::select → Soldier::onChangeWeapon(name)
      换枪 → 读 <name>_bullet → 写 last_equipped_gun → ScaleTo(0.1,1.75)→ScaleTo(0.1,1.25)

  板宽板高取 854×480（UIBoard 与场景同尺寸）。
"""

import pygame

from engine import res
from game.dialog import H, W


SELECT_BOX_TEX = "pic/ui/common/wp_select_box.png"
BULLET_TEX = "pic/ui/buttons/bullet.png"
BULLET_LIGHT_TEX = "pic/ui/buttons/bullet_light.png"

SLOT_SIZE = 100.0  # 单槽 100×100
SLOT_TOP = 0.0  # 板高 = 屏幕顶（anchor(1,1) 的 y）
GUN_ICON_SCALE = 1.25  # 枪图标 scale（反编译 1067450368 = 1.25）
SELECT_BOX_SCALE = 0.7  # 选中框 scale（反编译 1060320051 = 0.7）
# WeaponItemButton::init
#   bullet.png       anchor(0.0, 0.2) at (w*0.15, 0)     → 槽局部
#   bullet_light.png anchor(0.5, 0.5)
#                    x = bullet.png.contentSize.w * 0.47 + bullet.png.pos.x
#                    y = 槽高 * 0.3，scale 0.6
BULLET_POS = (0.15, 0.0)
BULLET_ANCHOR = (0.0, 0.2)
LIGHT_DX = 0.47  # × bullet.png 宽
LIGHT_Y = 0.30  # × 槽高
LIGHT_ANCHOR = (0.5, 0.5)
LIGHT_SCALE = 0.6


def gun_icon_path(name, lv, uptab):
    """Name2IconTex::getGunIcon：默认 gun_<name>.png，升级后带 _<look> 后缀。"""
    base = "pic/ui/weapon_icon/gun_%s.png" % name
    up = uptab.get(name) or {}
    looks = up.get("looks") or []
    if lv > 0 and looks:
        pick = None
        for lk in looks:
            if lv >= lk.get("min_lv", 0):
                pick = lk.get("look_index")
        if pick is not None:
            alt = "pic/ui/weapon_icon/gun_%s_%d.png" % (name, pick)
            if res.load_img(alt):
                return alt
    return base


class WeaponSlots:
    """战斗界面右上角的武器槽组。"""

    def __init__(self, battle, uptab=None):
        self.battle = battle
        self.uptab = uptab or {}
        self._sig = None
        self._build()

    def _equipped_names(self):
        """原版读存档键 equipped_gun_0 / equipped_gun_1 …（逐个直到空）。

        本复刻的存档用 equipped 列表（4 槽），同时同步 equipped_gun_N。
        注意 equipped_gun_N 里**只写非空槽**（原版就是空的槽不写），
        所以读取时不能遇到空就 break —— 要跳过继续往后找，
        否则「槽 0 空、槽 1 有枪」的情况下战斗里一把枪都没有。
        """
        save = getattr(self.battle, "save", None)
        d = getattr(save, "d", {}) if save else {}
        out = []
        for i in range(4):
            nm = d.get("equipped_gun_%d" % i)
            if nm:
                out.append(nm)
        if not out:
            out = [w for w in (d.get("equipped") or []) if w]
        if not out:
            out = [self.battle.weapon]
        return out

    def refresh(self):
        """子弹数变化后重建（子弹提示状态与存档绑定）。"""
        self._build()

    def _build(self):
        self.rects = []  # [(rect, weapon_name)]
        self.bullet = []  # [(rect, weapon_name)] 子弹不足时可点买弹
        names = self._equipped_names()
        n = len(names)
        if n <= 0:
            return
        # v139 = min(1.0, (板宽*0.5) / (100 * 槽数))
        need = SLOT_SIZE * n
        scale = 1.0 if need <= (W * 0.5) else (W * 0.5) / need

        save = getattr(self.battle, "save", None)
        d = getattr(save, "d", {}) if save else {}

        for idx, name in enumerate(names):
            iw = int(round(SLOT_SIZE * scale))
            ih = int(round(SLOT_SIZE * scale))
            # addWeaponItemButton @0x168108：
            #   v6 = **加入前**已有槽数；v7 = v6 * 按钮宽(100)
            #   pos.x = 板宽 - v7 * scale，anchor(1,1) ⇒ 右边界 = pos.x
            #   屏幕矩形 = (pos.x - 100*scale, 0) .. (pos.x, 100*scale)
            # 第一个槽 idx=0 ⇒ pos.x = 854 ⇒ 矩形 x 754..854（右上角）。
            right = W - SLOT_SIZE * scale * idx
            r = pygame.Rect(int(round(right - iw)), int(round(SLOT_TOP)), iw, ih)

            self.rects.append((r, name))

            # 子弹不足：叠子弹图标（点击可买弹）
            # ★ 原版 WeaponItemButton::init @0x181884 判断 `bullet >= 0`
            #   才建子弹节点（bullet.png / bullet_light.png / 子弹数文字）。
            #   近战武器 init_bullet 缺省 = -1（无限子弹）⇒ 槽上**没有子弹条**。
            #   （老版本 set_init_bullet 的缺省是 0）⇒ 近战槽上多出一条子弹提示
            if not self.battle.infinite_bullet(name) and int(d.get("%s_bullet" % name, 0)) == 0:
                self.bullet.append((r, name))

    def hit(self, pos):
        """返回命中的武器名或 None。"""
        for r, name in self.rects:
            if r.collidepoint(pos):
                return name
        return None

    def is_out_of_ammo(self, name):
        """子弹为 0（且该枪不是无限子弹）。"""
        return not self.battle.infinite_bullet(name) and self.battle.bullet_count(name) <= 0

    def click(self, pos):
        """武器槽点击。

        原版 WeaponItemButton::select：
          按钮的 +292 标志（"已被选过"）为 1 → 走 onBuyBullet（买弹）；
          为 0 → 走 Soldier::onChangeWeapon（换枪），并把 +292 置 1。
        即：**点当前那把枪 → 买弹；点另一把 → 换过去**。

        返回 ("buy", name) / ("switch", name) / None。
        """
        name = self.hit(pos)
        if name is None:
            return None
        b = self.battle
        if name == b.weapon:
            d = b.gun_def(name)
            if int(d.get("bullet_cost", 0)) > 0 and not d.get("inf"):
                return ("buy", name)
            return None
        return ("switch", name)

    def draw(self, s, font=None):
        # 子弹数变了（开火/买弹）就重建，刷新「子弹不足」提示
        sig = tuple(self.battle.bullet_count(n) for _, n in self.rects)
        if sig != getattr(self, "_sig", None):
            self._sig = sig
            self._build()
        cur = self.battle.weapon
        box = res.load_img(SELECT_BOX_TEX)
        num_font = font
        for r, name in self.rects:
            lv = 0
            save = getattr(self.battle, "save", None)
            if save is not None:
                lv = save.weapon_level(name)
            icon = res.load_img(gun_icon_path(name, lv, self.uptab))
            if icon:
                iw = max(1, int(round(icon.get_width() * GUN_ICON_SCALE)))
                ih = max(1, int(round(icon.get_height() * GUN_ICON_SCALE)))
                # ★ 图标不能超出槽位：原版槽是 100×100，图标 scale 1.25 只对
                #   96×85 的标准图成立；uzi 这类更宽的图会顶出槽外压到隔壁槽，
                #   最右一槽还会被屏幕边缘裁掉。这里按槽内留 6px 再收一次。
                max_w, max_h = r.w - 12, r.h - 12
                fit = min(1.0, max_w / float(iw), max_h / float(ih))
                iw = max(1, int(iw * fit))
                ih = max(1, int(ih * fit))
                icx = r.x + r.w * 0.5
                icy = r.y + r.h * 0.5
                s.blit(
                    pygame.transform.smoothscale(icon, (iw, ih)),
                    (int(round(icx - iw / 2)), int(round(icy - ih / 2))),
                )
            # 选中框：anchor(0.5,0.5) at (w*0.5,h*0.5)，scale 0.7，只有选中的槽才显示
            if box and name == cur:
                bw = max(1, int(round(box.get_width() * SELECT_BOX_SCALE)))
                bh = max(1, int(round(box.get_height() * SELECT_BOX_SCALE)))
                bcx = r.x + r.w * 0.5
                bcy = r.y + r.h * 0.5
                s.blit(
                    pygame.transform.smoothscale(box, (bw, bh)),
                    (int(round(bcx - bw / 2)), int(round(bcy - bh / 2))),
                )
            if num_font is not None:
                n = self.battle.bullet_count(name)
                if not self.battle.infinite_bullet(name) and n >= 0:
                    num_font.draw(s, str(n), r.x + r.w * 0.37, r.bottom - 6, 0.6, align=0.0)
        # 子弹不足提示（原版只在子弹为 0 时建这组节点）
        bullet = res.load_img(BULLET_TEX)
        light = res.load_img(BULLET_LIGHT_TEX)
        for r, _name in self.bullet:
            if bullet:
                bw, bh = bullet.get_size()
                lx = r.w * BULLET_POS[0]
                ly = r.h * BULLET_POS[1] + r.h * 0.22
                cx = r.x + lx + BULLET_ANCHOR[0] * bw
                cy = r.bottom - ly - BULLET_ANCHOR[1] * bh
                s.blit(bullet, (int(round(cx)), int(round(cy))))
            if light:
                lw = max(1, int(round(light.get_width() * LIGHT_SCALE)))
                lh = max(1, int(round(light.get_height() * LIGHT_SCALE)))
                if bullet:
                    bx = r.w * BULLET_POS[0]
                else:
                    bx = 0.0
                cx = r.x + bx + (bullet.get_width() * LIGHT_DX if bullet else 0.0)
                cy = r.bottom - r.h * (LIGHT_Y + 0.22)
                s.blit(
                    pygame.transform.smoothscale(light, (lw, lh)),
                    (int(round(cx - lw / 2)), int(round(cy - lh / 2))),
                )
