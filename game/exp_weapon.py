"""战斗中的经验武器（限时白给的强枪）—— 原版 ExpWeaponItemManager / ExpWeaponNode。

反编译依据（D:\\Code\\dsh\\full_dump\\all_merged.c）：

  ExpWeaponItemManager::checkAndCreatItem @0x1867d0
      按关卡 day 决定今天掉落哪把枪，生成位置 (士兵x + LOGIC*180, LOGIC*100)。
      每天最多两把：第一把用 <key> 标记，第二把用 <key>_1 标记。
      标记已置 1 表示那把已经出现过。

  ExpWeaponItemManager::checkIfAddExpWeapon @0x186cac
      同一张表，但只判断不生成。

  ExpWeaponNode::onUpdate @0x186f9c
      道具向左移动（跟着士兵）；
      |士兵x - 道具x| / 2 <= 道具宽 * 0.5 时触发 hitAnimation → hitItemNode。

  ExpWeaponItemManager::hitItemNode @0x186b3c
      若是 mech_* → 直接召唤机甲（CallMechAbility）；
      否则 Soldier::onChangeToExpWeapon(name)：
          经验武器子弹 = 100，写存档 <name>_bullet = 100；
          置「经验武器模式」标志；存档标记置 1；记录当前经验武器名。

  Soldier::onWeaponFire @0x189388
      经验武器模式下每开一枪递减剩余发数；归零时结束经验武器、换回原枪并放爆炸特效。
"""

# 关卡 level → [(标记 key, 枪名), ...]
# 反编译 checkAndCreatItem @0x1867d0 的 n2 = ExpWeaponItemManager 构造时传入的
# 关卡 level（BattleField::init 里 `ExpWeaponItemManager(this, KeyValue)`，
# KeyValue 来自 level_list.xml 的 level 字段），不是 day：
#     n2 == 1 → "exp_weapon_day_3" → uzi
#     n2 == 2 → "exp_weapon_day_4" → colt_anaconda
#     n2 == 3 → "exp_weapon_day_5_0" → bubble / "exp_weapon_day_5_1" → mech_3
#     n2 == 4 → "exp_weapon_day_6" → freezer
#     n2 == 5 → "exp_weapon_day_7_0" → rocket / "exp_weapon_day_7_1" → mech_8
#     n2 == 6 → "exp_weapon_day_8" → m4
#     n2 == 7 → "exp_weapon_day_9_0" → sonic / "exp_weapon_day_9_1" → mech_10
#     n2 == 8 → "exp_weapon_day_10" → laser
#     n2 == 9 → "exp_weapon_day_11_0" → thunder / "exp_weapon_day_11_1" → mech_5
# 存档 key 里的 "day_N" 是原版的命名习惯（N = level + 2）。
# 每关最多两把：第一把用 <key>，第二把用 <key>_1。标记已置 1 表示那把已出现过。
# 模拟器参考帧（emu_battle_clean.png，level 1 关）：地上有一把 uzi
# （贴图 69x56 = gun_uzi 的尺寸，带 item_light 光柱 + item_ring 光环）✓
EXP_WEAPON_TABLE = {
    1: [("exp_weapon_day_3", "uzi")],
    2: [("exp_weapon_day_4", "colt_anaconda")],
    3: [("exp_weapon_day_5_0", "bubble"), ("exp_weapon_day_5_1", "mech_3")],
    4: [("exp_weapon_day_6", "freezer")],
    5: [("exp_weapon_day_7_0", "rocket"), ("exp_weapon_day_7_1", "mech_8")],
    6: [("exp_weapon_day_8", "m4")],
    7: [("exp_weapon_day_9_0", "sonic"), ("exp_weapon_day_9_1", "mech_10")],
    8: [("exp_weapon_day_10", "laser")],
    9: [("exp_weapon_day_11_0", "thunder"), ("exp_weapon_day_11_1", "mech_5")],
}

EXP_BULLETS = 100  # 经验武器的子弹数（Soldier::onChangeToExpWeapon 写死 100）
# 节点几何（ExpWeaponNode::init @0x186358）：
#   contentSize = (s_fLogicUnitLen*150, s_fLogicUnitLen*200)，锚点 (0.5, 0.0)
#   枪图标子节点 pos = (w*0.5, h*0.9) = (75, 180)，在 h*0.9 ↔ h*0.95 之间循环
#   节点世界 y = s_fLogicUnitLen*100（cocos 向上）⇒ 屏幕底边 y = 480 - 100 = 380
# s_fLogicUnitLen = 1.0 / contentScaleFactor（all_merged.c:48994）。
# Android 设备 1280x720 上 contentScaleFactor = 1（设计分辨率 853.33x480，
# 1.5 倍放大由 EzGameScene::s_fLogicScaleFactor 做，不是 contentScaleFactor）。
# 证据：节点树 dump 里 ExpWeaponNode 的 sz = [150, 200]（= LOGIC*150/200，LOGIC=1），
#      且 itemX = 士兵中心(427.3) + LOGIC*180 = 607.3 与节点树 pos.x=606.667 吻合。
LOGIC = 1.0
ITEM_OFFSET_X = 180.0 * LOGIC  # 生成位置：士兵x + LOGIC*180
ITEM_Y = 100.0 * LOGIC  # 节点世界 y（cocos 向上，= createItem 的 LOGIC*100）
ITEM_W = 150.0  # ExpWeaponNode contentSize 宽（节点树实测）
ITEM_H = 200.0  # ExpWeaponNode contentSize 高
GUN_LOCAL_Y = 180.0  # 枪图标在节点内的 y（h*0.9），在 180..190 之间上下浮动
#   节点树实测 189.148（浮动到 h*0.95 那一端）
#   模拟器参考帧（emu_battle_clean.png）：枪身中心 (606.9, 195.1)
#   ⇒ 局部 y = 节点底边(480 - 100 = 380) - 195.1 = 184.9  （在 180..190 内）


def exp_weapon_for_day(day):
    """今天还没出现过的经验武器（标记, 枪名）；没有则 None。"""
    return EXP_WEAPON_TABLE.get(int(day))


def gun_icon_width(gun):
    """枪图标精灵的 contentSize 宽 —— 拾取判定用的「道具宽」。

    反编译 ExpWeaponNode::onUpdate 用的是节点 +96 处的 float，
    那是枪图标精灵的宽（gun_uzi = 69），不是节点 contentSize（150）。
    """
    from engine import res

    if str(gun).startswith("mech"):
        path = "pic/ui/mech_icon/%s.png" % gun
    else:
        path = "pic/ui/weapon_icon/gun_%s.png" % gun
    im = res.load_img(path)
    return float(im.get_width()) if im else 69.0


def pick_exp_weapon(save_d, level):
    """ExpWeaponItemManager::checkAndCreatItem：挑一把该关还没用过的经验武器。

    返回 (标记 key, 枪名) 或 None。
    """
    entries = exp_weapon_for_day(level)
    if not entries:
        return None
    for entry in entries:
        key = entry[0]
        if not int(save_d.get(key, 0) or 0):
            return entry
    return None


# ------------------------------------------------------------ 绘制
LIGHT_TEX = "pic/items/item_light.png"
RING_TEX = "pic/items/item_ring.png"

# 动画表网格（EzSprite::animationWithResName @0x1b8a60）：
#   帧宽 = texW / 列数，帧高 = texH / 行数；总帧数 = 列数 * 行数
#   item_light.png 240x300  6 列 2 行 ⇒ 12 帧，每帧 40x150
#   item_ring.png  400x200  4 列 2 行 ⇒  8 帧，每帧 100x100
# 节点树实测的当前帧 sub 也能对上：
#   item_light sub=[200,150,40,150] ⇒ 第 5 列第 1 行 = 帧序号 11
#   item_ring  sub=[300,100,100,100] ⇒ 第 3 列第 1 行 = 帧序号 7
# 网格布局：反编译 EzSprite::animationWithResName(name, "", 6u, 0, ...)
# 的第 3 参数是**列数**，第 4 参数 0 = 行数自动（单行）。
# 拿到的是「光环上半 + 光柱下半」拼起来的图，
# 屏幕上就是那个金色方块。
# 实测：item_light.png 240x300 = 6 列 x 2 行（每帧 40x150）
#       item_ring.png  400x200 = 4 列 x 2 行（每帧 100x100）
LIGHT_FRAME = (40, 150)  # 贴图每帧尺寸（240x300 → 6列x2行）
LIGHT_CONTENT = (40, 150)  # cocos contentSize（节点树实测）
LIGHT_COLS, LIGHT_ROWS = 6, 2
LIGHT_FRAMES = LIGHT_COLS * LIGHT_ROWS
LIGHT_SCALE = (2.0, 1.35)  # ★ 原版节点树 sc=[2.6,1.6]（104×240），在暗场景里
LIGHT_ALPHA = 105  # 光柱整体透明度（原版不透明，这里压到 ~41%）
LIGHT_START = 0  # 起始帧（取帧方式修正后重新标定）
RING_FRAME = (100, 100)  # 贴图每帧尺寸（400x200 → 4列x2行）
RING_CONTENT = (100, 100)  # cocos contentSize（节点树实测）
RING_COLS, RING_ROWS = 4, 2
RING_FRAMES = RING_COLS * RING_ROWS
RING_SCALE = (1.3, 1.0)  # 节点树实测 sc = [1.3, 1.0]
RING_ALPHA = 150  # 地上光环也压淡一点，别和光柱一起烧屏
RING_START = 0  # 起始帧（模拟器参考帧标定）
FX_CYCLE = 1.6  # ★ 光柱/光环一轮动画的时长。原版 0.8s，


def _frame(sheet, fw, fh, index, cols, rows):
    """从网格动画表里取第 index 帧。"""
    import pygame

    w, h = sheet.get_size()
    fw = min(fw, w)
    fh = min(fh, h)
    idx = index % (cols * rows)
    cx, cy = idx % cols, idx // cols
    rect = pygame.Rect(cx * fw, cy * fh, fw, fh)
    if not sheet.get_rect().contains(rect):
        return None
    return sheet.subsurface(rect).copy()


def _blit_anchor(s, img, ax, ay, x, y):
    """按 cocos 锚点贴图：锚点落在屏幕 (x, y)。

    cocos 的 ay 从下往上：ay=0 是底边，ay=1 是顶边。
    """
    w, h = img.get_size()
    s.blit(img, (int(round(x - ax * w)), int(round(y - (1.0 - ay) * h))))


SPARK_TEX = "pic_particle/spark_3.png"
# ItemEffect::initWithTotalParticles @0x185f80 的粒子参数
# （偏移由 cocos2d::CCParticleSystem 的 getXXX 访问器反查确定）：
#   this+81  startRadius  = 30        this+82  startRadiusVar = 0
#   this+83  endRadius    = 50        this+84  endRadiusVar   = 0
#   this+93  duration     = -1（无限） this+75  speed = 0（未写）
#   this+96  life         = 0.7       this+99  lifeVar = 0
#   this+100 angle         = 360       this+101 angleVar = 0
#   this+103 startSize     = 25        this+104 startSizeVar = 2
#   this+105 endSize       = 0         this+106 endSizeVar   = 0
#   this+107..110 startColor = (1,1,1,1)   纹理 = pic_particle/spark_3.png
#   重力 / radialAccel / tangentialAccel 均未写 ⇒ 全 0
# 语义：粒子出生在半径 30 的圆周上（角度 0~360 均匀随机），寿命 0.7s 内
# 半径扩到 50、尺寸从 25 缩到 0。发射器节点 scale = 1.3
# （ExpWeaponNode::init 里 setScale(v42, 1.3)），故实际星芒约 25×1.3 ≈ 33 物理像素。
SPARK_COUNT = 50
SPARK_LIFE = 0.7  # m_fLifeTime
# 粒子系统的半径是「发射器节点局部」单位；节点 scale=1.3 ⇒ 屏幕半径 ×1.3
# （实测标定：半径乘 1.3 时径向直方图与原版最吻合，L1 0.197 vs 未乘的 0.481）
SPARK_START_RADIUS = 30.0 * 1.3  # m_fStartRadius × 节点 scale
SPARK_END_RADIUS = 50.0 * 1.3  # m_fEndRadius   × 节点 scale
SPARK_START_SIZE = 25.0  # m_fStartSize
SPARK_SIZE_VAR = 2.0  # m_fStartSizeVar
SPARK_END_SIZE = 0.0  # m_fEndSize
SPARK_EMITTER_SCALE = 1.3  # 发射器节点缩放
# 枪图标的显示缩放。反编译 ExpWeaponNode::init 用 setScale(1.3)，
# 实测扫 1.0/1.15/1.3/1.45/1.6 也是 1.3 最优（枪周区 32.1%）。
GUN_SCALE = 1.3
# 同时可见的粒子数（原版共 50 粒，但稳态下只有一部分清晰可见 ——
# 老粒子已缩到 endSize=0 附近，参考帧只见约 15~20 颗独立大星）
SPARK_VISIBLE = 12
SPARK_ALPHA = 70


def _draw_sparks(s, cx, cy, t=0.0):
    """画经验武器掉落物的星芒粒子（ItemEffect）。

    原版是 cocos 粒子系统（CCParticleSystemQuad，50 粒 spark_3.png）：
    粒子出生在半径 30 的圆周上，0.7 秒内半径扩到 50、尺寸从 25 缩到 0，
    角度在 0~360° 间均匀随机。发射器节点 scale=1.3。
    这里用确定性伪随机复现同样的观感。
    """
    import math

    import pygame

    from engine import res

    sp = res.load_img(SPARK_TEX)
    if sp is None:
        return
    sw, sh = sp.get_size()
    for i in range(min(SPARK_COUNT, SPARK_VISIBLE)):
        # 每个粒子的相位错开，形成连续不断的星环。
        # 相位步进用与角度不同的无理数，避免两者相关导致粒子挤成一束。
        life = (t / SPARK_LIFE + i * 0.3819660113) % 1.0
        # 出射角：0~360° 均匀分布（黄金比例步进保证分散）
        ang = math.radians(360.0 * ((i * 0.6180339887) % 1.0))
        # 半径 30 → 50；尺寸 25 → 0（起始尺寸带 ±2 抖动）
        r = SPARK_START_RADIUS + (SPARK_END_RADIUS - SPARK_START_RADIUS) * life
        size = SPARK_START_SIZE + SPARK_SIZE_VAR * (((i * 0.37) % 1.0) - 0.5) * 2.0
        size *= 1.0 - life
        w = max(1, int(round(sw * size / 36.0 * SPARK_EMITTER_SCALE)))
        h = max(1, int(round(sh * size / 36.0 * SPARK_EMITTER_SCALE)))
        px = cx + math.cos(ang) * r
        py = cy - math.sin(ang) * r
        # 粒子按出射角旋转（cocos 粒子 m_fRotatePerSecond=0，但四角星方向
        # 随出射角走才与参考帧一致）。用最近邻缩放保留锐利的星芒边缘，
        # 再用加色混合（cocos 粒子默认 CC_BLEND_ADD）叠到底图上。
        # 粒子**不旋转**：反编译 init 里 this+85 = 0（m_fRotatePerSecond = 0），
        # 角速度为 0 时 cocos 不给粒子加旋转角。
        # 用 scale（最近邻）而非 smoothscale，保留四角星的锐利边缘；
        # pygame 的 rotate 会做双线性插值，把星芒糊成光斑，与参考帧不符。
        # 原版 startColor/endColor 的 alpha 都是 1.0 ⇒ 粒子**不淡出**，
        # 只靠 endSize=0 缩小消失。所以这里保持 alpha=255。
        # ★ 但整体要压暗一档：模拟器参考帧（emu_b4_s.png）里道具周围
        #   只是一圈很淡的星芒，20 颗全亮度叠起来会变成刺眼的亮环，
        #   还会盖住 item_light 帧顶部自带的横向花纹环，看着就是
        #   「光圈多了一层、很奇怪」。
        img = pygame.transform.scale(sp, (w, h)).copy()
        img.fill((255, 255, 255, SPARK_ALPHA), special_flags=pygame.BLEND_RGBA_MULT)
        s.blit(img, (int(round(px - img.get_width() / 2)), int(round(py - img.get_height() / 2))))


def draw_exp_weapon(s, item, screen_x, t=0.0):
    """画经验武器掉落物（枪 + 光柱 + 光环）。

    ExpWeaponNode::init @0x186358：
      枪图标   pic/ui/weapon_icon/gun_<name>.png
               anchor(0.5,0.5)，在节点局部 (w*0.5, h*0.9)，上下 0.9↔0.95 循环（1s）
      光柱     pic/items/item_light.png  scale 2.6/1.6，anchor(0.4,0.12)
      光环     pic/items/item_ring.png   scale 1.3/1.0，anchor(0.5,0.5)

    节点 contentSize = LOGIC*150 x LOGIC*200，锚点 (0.5,0.0)，世界 y = LOGIC*100（cocos 向上）
    ⇒ 屏幕：节点原点 y = 480 - ITEM_Y，节点中心 x = screen_x。
    实测（emu_battle_clean.png）：光环中心 (610.3, 378.3)、枪身中心 (606.4, 194.8)。
    """
    if item is None or item.get("taken"):
        return
    import pygame

    from engine import res

    gun = item["gun"]
    if gun.startswith("mech"):
        icon_path = "pic/ui/mech_icon/%s.png" % gun
    else:
        icon_path = "pic/ui/weapon_icon/gun_%s.png" % gun

    node_w = ITEM_W
    node_h = ITEM_H
    # 节点锚点 (0.5,0.0) ⇒ 节点原点在屏幕 y = 480 - ITEM_Y；原点 x = screen_x
    base_y = 480.0 - ITEM_Y
    node_left = screen_x - node_w * 0.5
    node_cx = node_left + node_w * 0.5

    # 枪图标：局部 (w*0.5, h*0.9)，上下 0.9↔0.95 循环（1s 一个来回）
    phase = (t % 1.0) / 0.5
    k = phase if phase <= 1.0 else 2.0 - phase
    icon = res.load_img(icon_path)
    gy = base_y - (GUN_LOCAL_Y + node_h * 0.05 * k)
    if icon:
        iw = max(1, int(round(icon.get_width() * GUN_SCALE)))
        ih = max(1, int(round(icon.get_height() * GUN_SCALE)))
        _blit_anchor(s, pygame.transform.smoothscale(icon, (iw, ih)), 0.5, 0.5, node_cx, gy)

    # 星芒粒子（ItemEffect::initWithTotalParticles @0x185f80）：
    #   50 粒子，贴图 pic_particle/spark_3.png（36×36 黄色四角星）
    #   发射器位置 = 枪精灵的位置（ExpWeaponNode::init 里 v43(v42, 枪的 getPosition())），
    #   发射器节点 scale 1.3，addChild z=-1（在枪与光柱下面）
    _draw_sparks(s, node_cx, gy, t)

    # 光柱：item_light.png，scale 2.6/1.6（节点树 sc 实值），anchor(0.4,0.12)，在 (w*0.5, 0)
    # 动画：CCAnimate 0.8s 播一轮（12 帧）。
    # 起始帧 6 由模拟器参考帧标定（emu_battle_clean.png 那一刻的帧）。
    light = res.load_img(LIGHT_TEX)
    if light:
        fi = (LIGHT_START + int(t / FX_CYCLE * LIGHT_FRAMES)) % LIGHT_FRAMES
        fr = _frame(light, LIGHT_FRAME[0], LIGHT_FRAME[1], fi, LIGHT_COLS, LIGHT_ROWS)
        if fr and LIGHT_ALPHA < 255:
            fr = fr.copy()
            fr.fill((255, 255, 255, LIGHT_ALPHA), special_flags=pygame.BLEND_RGBA_MULT)
        if fr:
            # 节点树实测：item_light 的 contentSize = [40,150]、sc = [2.6,1.6]
            # → 显示尺寸 104x240。cocos 会把贴图缩放到 contentSize，
            # 所以先把帧缩到 (40,150)，再按 sc 放大。
            lw = max(1, int(round(LIGHT_CONTENT[0] * LIGHT_SCALE[0])))
            lh = max(1, int(round(LIGHT_CONTENT[1] * LIGHT_SCALE[1])))
            _blit_anchor(s, pygame.transform.smoothscale(fr, (lw, lh)), 0.4, 0.12, node_cx, base_y)

    # 光环：item_ring.png，scale 1.3/1.0（节点树 sc 实值），anchor(0.5,0.5)，在 (w*0.5, 0)
    # 动画：CCAnimate 0.8s 播一轮（8 帧）。
    ring = res.load_img(RING_TEX)
    if ring:
        fi = (RING_START + int(t / FX_CYCLE * RING_FRAMES)) % RING_FRAMES
        fr = _frame(ring, RING_FRAME[0], RING_FRAME[1], fi, RING_COLS, RING_ROWS)
        if fr and RING_ALPHA < 255:
            fr = fr.copy()
            fr.fill((255, 255, 255, RING_ALPHA), special_flags=pygame.BLEND_RGBA_MULT)
        if fr:
            # 节点树实测：item_ring 的 contentSize = [100,100]、sc = [1.3,1.0]
            # → 显示尺寸 130x100。先缩到 (100,100)再放大。
            rw = max(1, int(round(RING_CONTENT[0] * RING_SCALE[0])))
            rh = max(1, int(round(RING_CONTENT[1] * RING_SCALE[1])))
            _blit_anchor(s, pygame.transform.smoothscale(fr, (rw, rh)), 0.5, 0.5, node_cx, base_y)
