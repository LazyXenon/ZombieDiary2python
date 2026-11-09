"""游戏全局常量与节点树配置。

集中存放原版节点树（data/node_tree_*.json）的几何量、贴图修正表、
场景常量，以及各类只读的静态配置。

只放常量与配置表；不放任何类的 re-export。各模块需要某个类时
直接从它自己的源模块导入（`from game.result import ResultPanel`）。
"""

import os

from game.constants import GUARD_LINE_X as GUARD_LINE_X


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 地平线：士兵与僵尸共用一条。战斗几何全部以此为基准。
GROUND_Y = 392.0

W, H = 854, 480
DATA = os.path.join(ROOT_DIR, "data")

SCREENS = {
    "menu": ("node_tree_menu.json", "node_tex_menu9.json"),
    "map": ("node_tree_map.json", "node_tex_map12.json"),
    "level": ("node_tree_level.json", "node_tex_level9.json"),
    "battle": ("node_tree_battle.json", "node_tex_battle10.json"),
    "shop": ("node_tree_shop.json", "node_tex_shop9.json"),
}

BSKIP_CLS = ("F2CSprite", "F2CAnimation")

# 士兵在战斗场景里的整体位置（逻辑像素）。
# 节点树 dump：Soldier 节点 pos=[458.667, 72.0] sz=[300,300] ap=[0.5,0.0]
#   ⇒ 节点底边屏幕 y = 480 − 72 = 408。
# 精灵在节点内还有自身偏移，参考帧脚底（白鞋底）比节点底边高约 7 逻辑像素 ⇒ 401。
# 注意：帽带高度会随站立动画的呼吸相位浮动 ±20 物理像素，
# 不能拿帽子位置标定竖向位置，只能用脚底。
#   模拟器参考帧 emu_b4_s.png（854×480）里士兵鞋底在屏幕 y = 392。
#   画面上就是「角色和僵尸不在一条线上」。
SOLDIER_FOOT_Y = GROUND_Y

# 远行任务的「向右走」指示箭头。
# 原版 BattleField::showGoRightAnimation @0x16e55c（all_merged.c:9064）：
#   素材 pic/ui/battlefield/go_right.png（153x44），opacity 0.9，anchor(1.0, 0.5)，
#   位置 = (屏幕宽 - 图宽*0.2, 屏幕高*0.5)，z=10，
#   动画：MoveBy(±图宽*0.2, 0) 往返 0.3 秒，无限循环。
#   触发：任务类型是 distance / hostage（有 DistanceCounter）。
GO_RIGHT_TEX = "pic/ui/battlefield/go_right.png"
GO_RIGHT_OPACITY = 0.9
GO_RIGHT_SWING = 0.3
# 反编译 showGoRightAnimation @0x16e55c：setScale(1067030938) = 1.2
GO_RIGHT_SCALE = 1.2
# 提示总共显示多久（原版 CCRepeat(N)，播完 endGoRightAnimation 移除）。
# 一个来回 0.6 秒，N≈3 ⇒ 1.8~2 秒。
GO_RIGHT_SHOW = 2.0
# 水平：Skeleton.render 把含枪的包围盒居中在 screen_x，
# 而原版 Soldier 节点锚点是精灵中心（头中心 427.3、脚部 458.667），
# 参考帧标定（emu_ref3.png / emu_m14.png，站立帧）：
#   原版鞋红 x 627..637，本复刻 667..677 ⇒ 偏右 40 物理 = 27 逻辑
#   扫 16 帧 × 脚底 y × scale × x 后最优 x = 449 逻辑
#   ⇒ SOLDIER_DX = 449 − SOLDIER_SCREEN_X(458.667) = −9.7
SOLDIER_DX = -10.0

# 战斗 HUD 左侧的士兵头像（SoldierHPBar 的 z=4 子节点）。
# 节点树 dump（data/node_tree_battle.json 第 28 行，原版实机抓的）：
#   pos = [48.1, -42.56]  sz = [96, 85]  ap = [0.5, 0.5]  sc = [0.83, 0.83]
#   tex = AutoLoad_PreBuild/Block_85.png（= pic/ui/soldier_icon/soldier_N.png，96×85）
# ⇒ 贴图 96×85 本身，节点 scale 0.83 ⇒ 显示 79.7×70.6，中心屏幕 (48.1, 42.56)。
# 注意反编译 setScale(1.1) 是 EzSprite 的 contentSize 缩放（contentSize 含留白），
# 与节点树的 0.83 不是一回事 —— **以节点树为准**。
HUD_HEAD_SCALE = 0.83
HUD_HEAD_X = 48.1
HUD_HEAD_Y = 42.56

# 血条槽（hp_bar_bg_0，230×61）的屏幕位置（逻辑像素，左上角）。
# 反编译 SoldierHPBar::init：anchor(0,1) at (head_0.w*0.9, -3) = (117, -3)。
HP_BAR_X = 117.0
HP_BAR_Y = -3.0

# 地图树里 zone 名牌 + 任务气泡 + 焦点特效根节点是**静态 dump 残留**
# （dump 那一刻只有 hospital 一个 zone、一个 mission）。
# 原版这些节点是按当前进度动态创建的（MapLayer::initLevelMissions），
# 所以树里这批要跳过，改由 game/map_points.py 按反编译公式动态画。
MAP_SKIP = {
    "0xd64c0484",  # zone_hospital.png
    "0xd69fd004",  # map_bg_mission.png（气泡底板）
    "0xd64bff84",  # map_bg_mission.png（气泡底板，子）
    "0xd64c0204",  # map_mission_kill.png
    "0xd69fd184",  # focus_level_effect 根
    # ★ focus 根节点只跳自身不跳子树（engine/scene.py 的 skip_addr 语义），
    #   6 个子孙贴图残留照画 ⇒ 地图上多一圈「莫名光晕」。
    #   原版 focus 是 initLevelMissions 运行时动态创建的（all_merged.c:78766），
    #   dump 树里这批全是静态残留，整组跳过。
    "0xcc5d9f44",  # focus b01
    "0xcc5da2c4",  # focus b03
    "0xcc5da104",  # focus paopao
    "0xd64c0704",  # focus r01
    "0xd64c0984",  # focus r02
    "0xd64c0c04",  # focus r03
    # 成就按钮的红角标：反编译 MapLayer::checkAchievementEffect 硬编码
    # addNewAchievementEffect(0) ⇒ count<=0 时角标恒隐藏。树里是 dump 时的静态残留。
    "0xc7dfb504",  # count_bg.png（成就角标底）
    "0xd07b0e84",  # EzTexText（成就角标数字）
    "0xc7dfc184",  # EzTexChar（成就角标数字）
    # 每日任务角标：树里是 dump 时的静态残留（count_bg + 数字），整组跳过，
    # 改由 _draw_map_buttons 按实际未领取数自绘。
    "0xc7dfc904",  # count_bg.png（每日任务角标底）
    "0xcc5e1784",  # EzTexText（每日任务角标数字）
    "0xd64c0e84",  # EzTexChar（每日任务角标数字）
}

# 地图顶栏 map_up_bar.png 节点 —— 它在 EzAdLayer 的暗化遮罩**之上**
MAP_UPBAR = "0xd079f284"

# 顶栏里 dump 时烘死的静态数字。不隐藏的话，通关后顶栏永远显示
# 「3.000 / 5 / 第 1 天」，玩家会以为进度根本没推进、关卡没解锁。
MAP_STATIC_HIDE = {
    "0xf2938784",  # 「第 N 天」的数字
    "0xf2939ac4",  # 金币数
    "0xf2939c84",  # 钻石数
    # 绿「+」按钮：树里贴着钻石图标，数字没地方写。挪到右侧自己画。
    "0xc7dff384",
    "0xcc5e2b04",
}

COIN_ICON = "0xc7dfda84"
CRYS_ICON = "0xc7dfec04"
# 金币/钻石图标也交给 _draw_dynamic_topbar 顺排：钱位数变多时图标要跟着文字走，
# 否则长数字会压在图标上、文字被挤成一小坨。
MAP_STATIC_HIDE.update({COIN_ICON, CRYS_ICON})
MAP_PLUS_X = 566.0
MAP_PLUS_Y = 29.0
MAP_PLUS_SIZE = 40
BATTLE_STATIC_HIDE = {
    "0xd6b579c4",  # 战斗 HUD 金币数
    "0xd6b57b84",  # 战斗 HUD 钻石数
    # 图标也一起重画：钱位数变多时整行右移，静态图标会被金币数字压住。
    "0xd65fa104",  # 战斗 HUD 金币图标
    "0xd65fb284",  # 战斗 HUD 钻石图标
    "0xd65fa604",
    "0xd65fa884",
    "0xd65fab04",
    "0xd65fad84",
    "0xd65fb004",
    "0xd65fb784",
    "0xd65f8f84",
    "0xd65f9204",
    "0xd65f9484",
    "0xd65f9704",
}

BATTLE_COIN_ICON = "0xd65fa104"
BATTLE_CRYS_ICON = "0xd65fb284"

# 战斗屏幕虚拟按键（设置里「隐藏屏幕按键」时整组不画）。
#  0xd64eb944 / 0xf28b4384  TouchButton（左/右移动）
#  0xf28b4604               FireButton（开火）
#  子节点带同一张贴图，父节点隐藏后子节点仍会被遍历到，所以一并列出来。
BATTLE_CONTROL_NODES = {
    "0xd64eb944",
    "0xf28b4384",
    "0xf28b4604",
    "0xd65fbc84",
    "0xd65fbf04",
    "0xd65fc404",
}

# 节点树里 8 个「墓地散点灯」的贴图被误映射成 shop/up_bar.png
# （反编译 MapLayer::addCemeteryEffect @0x123738 用的是
#  pic/ui/map/map_cemetery_light.png，7x14，anchor(0.5,0.0)）
MAP_TEXFIX = {
    "0xc7dff884": "pic/ui/map/map_cemetery_light.png",
    "0xc7dffb04": "pic/ui/map/map_cemetery_light.png",
    "0xec050004": "pic/ui/map/map_cemetery_light.png",
    "0xec050284": "pic/ui/map/map_cemetery_light.png",
    "0xec050504": "pic/ui/map/map_cemetery_light.png",
    "0xec050784": "pic/ui/map/map_cemetery_light.png",
    "0xec050a04": "pic/ui/map/map_cemetery_light.png",
    "0xec050c84": "pic/ui/map/map_cemetery_light.png",
    # 老虎机按钮上的文字：MapLayer::updateSlotButton @0x121178
    #   free_spin_0 <= 0 → text_slot.png（「限免」）
    #   free_spin_0 >  0 → text_free_slot.png
    "0xc7dfd304": "pic/ui/map/text_slot.png",
}

BSKIP_TEX = (
    "freezer_wave",
    "mech/03/youtui03",
    "mech/10/tou",
    "mech/05/penghuofadongji01",
    "ui/shop/select_box",
    "ui/shop/ability_shield",
    "ui/battlefield/chat_dialog",
    "ui/buttons/distance",
    "ui/dialog/failed_bg",
)
BHIDE = {
    "0xd0740784",
    "0xcb8de784",
    "0xcb8d6d04",
    "0xcb8d4504",
    "0xcc471304",
    "0xd6b57804",
    "0xd64ec344",
    # ExpWeaponNode（经验武器掉落物）：树里 pos=[606.667,100] 是 dump 那一刻的
    # 世界坐标，位置随相机变。掉落物由 game/exp_weapon.py 按
    # ExpWeaponNode::init 的几何动态画（枪 + item_light 光柱 + item_ring 光环）。
    #  0xcb8d6d04  枪图标          （已在上面）
    #  0xcb8d4504  ItemEffect 发射器（同上）
    #  0xcb8ff004  item_ring 光环  ← 漏了！道具被捡走后它仍钉在原地，
    #  0xcc6b9e04  item_light 光柱 ← 同上
    "0xcb8ff004",
    "0xcc6b9e04",
    # 血条两端的头像框：dump 时 parent 断开、pos=(0,0)，
    # 直接画会糊在屏幕左上角（看上去像个白色手掌）。
    # 头像由 draw_hud 按正确位置自己画。
    "0xd65f8584",
    "0xd65f8a84",
    # 新手引导手指：isVisible=false（vis bit0=0），是 EzSprite 的引导提示，
    # 只在 UserGuide 流程里 setVisible(true)。这里恒画出来会压住左移动键。
    "0xcb8e1704",
    # 操控按钮的 EzSprite 子节点（Button_L/R/Weapon/Act）：
    # 父节点 TouchButton/WeaponButton/FireButton 已经带同一张贴图且位置一致，
    # 子节点再画一遍就是「两个三角叠在一起」——move 键重合的根因。
    "0xd65fbc84",
    "0xd65fbf04",
    "0xd65fc184",
    "0xd65fc404",
    # ComboKillEffect（连杀横幅 combo.png）：
    # 反编译 ComboKillEffect::init @0x182b0c 末尾 setVisible(false)，
    # 树里 dump 时是可见的（dump 那一刻正好在连杀）。
    # 连杀数由 game/hud_fx.py 按实际击杀数自己画，这里跳过树里的静态残留。
    "0xd64ec204",
    "0xd65f9c04",
    "0xd6663984",
    # WeaponItemButton（右上角武器槽）：
    # node_tex_battle10 把 0xf28b4744（槽本体）解析成了 wp_select_box.png，
    # 把子节点 0xd65fc904（选中框）解析成了 shop/select_box.png（绿色箭头），
    # 两者都错 —— 树里枪图标 0xd65fc684 也被解析成 mech/05/penghuofadongji01。
    # 武器槽整组由 game/battle_weapons.py 按反编译几何自绘（支持动态槽数）。
    "0xf28b4744",
    "0xd65fc904",
}

# 战斗的视差背景层：节点树里锁死了抓 dump 时那一关的背景，
# 改由 draw_battle_bg 按当前关卡的 zone 动态绘制。
BATTLE_BG_SUBTREE = ("ScrollBackground", "TiledCloud")
BTEXFIX = {
    "0xd65f8084": "pic/ui/buttons/hp_bar_bg_0.png",
    "0xd65f7e04": "pic/ui/buttons/hp_bar.png",
    "0xd65f8804": "pic/soldier/01/tou.png",
    "0xd65f8584": "pic/ui/buttons/hp_bar_head_1.png",
    "0xd65f8a84": "pic/ui/buttons/hp_bar_head_0.png",
    # 战斗操作按钮（原版 Button_L / Button_R / Button_Act / Button_Weapon）
    # walker 实测父节点：左(0,0) 右(132,0) 开火(742.833,0) 武器(813.333,113.3)
    # node_tex_battle10 把 0xf28b4384 也解析成了 Button_L，实际是右键，这里修正。
    "0xf28b4384": "pic/ui/buttons/Button_R.png",
    "0xd65fbc84": "pic/ui/buttons/Button_L.png",
    "0xd65fbf04": "pic/ui/buttons/Button_R.png",
    "0xf28b44c4": "pic/ui/buttons/Button_Weapon.png",
    "0xd65fc184": "pic/ui/buttons/Button_Weapon.png",
    "0xf28b4604": "pic/ui/buttons/Button_Act.png",
    "0xd65fc404": "pic/ui/buttons/Button_Act.png",
    "0xd65fcb84": "pic/ui/buttons/button_pause.png",
    "0xcb8d6d04": "pic/ui/weapon_icon/gun_uzi.png",
    "0xcb8d4504": "pic/ui/shop/gun_sonic.png",
    "0xd65fc684": "pic/ui/weapon_icon/gun_p220.png",
}

LEVEL_DIALOG = "0xcc54fa04"

# 军火库动态层：ScrollNode 里的 GunItem 随存档变化、详情面板文字随选中枪变化、
# 底部按钮随状态切换 —— 这些都交给 game/shopui.py 按反编译几何重建，
# 静态层（背景/顶栏/返回/货币条）仍由节点树渲染。
SHOP_EXCLUDE = {
    "0xd6623b84",  # property_bg（详情面板）
    "0xd6620804",  # ScrollNode（30 张 GunItem）
    "0xec0b4244",
    "0xec0b4384",
    "0xec0b44c4",
    "0xec0b4604",  # 4 个装备槽
    "0xd6620984",
    "0xd6620b04",
    "0xd6620c84",
    "0xd6620e04",  # 4 个详情按钮
    "0xd6620f84",  # 弹药购买条（gun_buy_bullet_bg）
    "0xd6620684",  # 加钻石按钮（货币行自绘）
    "0xd6435d84",
    "0xd07f7004",  # detail 按钮的贴图子节点
    "0xcc5b8804",
    "0xcc5b8a04",
    "0xd07f7284",
    "0xd07f7504",
    "0xd6435384",
    "0xd6435604",
    "0xd6435884",
    "0xd6435b04",  # 槽位 item_panel
    "0xd6634704",  # 槽位机枪火焰特效
    "0xd6623404",  # back 按钮贴图子节点
    "0xd661fa84",
    "0xd661fc04",
    "0xd6620084",
    "0xd6620204",
    "0xd6620384",  # 顶栏页签
    "0xd6634984",
    "0xd660dd44",
    "0xd660df04",  # 货币行：金币图 / 两个数字
    "0xcbc94284",
    "0xd660e0c4",  # 货币行：钻石图 / 数字
    "0xd6623184",  # up_bar 及其 5 个页签（双态贴图，按选中态裁切）
    "0xd6620504",  # back 按钮（按反编译 setScale 重画）
}

UI = {
    "menu_play": (282, 288, 572, 382),
    "map_mission": (455, 193, 564, 252),
    "map_shop": (630, 18, 787, 66),
    "map_back": (0, 402, 88, 466),
    "level_accept": (154, 373, 404, 442),
    "level_close": (427, 143, 499, 189),
    "battle_left": (0, 352, 132, 480),
    "battle_right": (132, 352, 264, 480),
    "battle_weapon": (773, 287, 853, 367),
    "battle_fire": (696, 377, 789, 480),
    "battle_pause": (316, 56, 376, 116),
}

ZONE_BG = {}  # zone → [hospital_01.jpg ...]，运行时扫描


def _scan_zone_bgs():
    import glob

    root = os.path.join(ROOT_DIR, "assets", "images", "pic_bg", "background")
    zones = {}
    if os.path.isdir(root):
        for f in sorted(os.listdir(root)):
            if f.endswith(".jpg") and "_" in f:
                zone = f.rsplit("_", 1)[0]
                zones.setdefault(zone, []).append(f)
    return zones
