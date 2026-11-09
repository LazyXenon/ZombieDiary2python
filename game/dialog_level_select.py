"""关卡选择框 —— 原版 DialogLevelSelect。

反编译依据（D:\\Code\\dsh\\full_dump\\all_merged.c）：
  DialogLevelSelect::init                  @0x14b8dc
  DialogLevelSelect::initSelectBgNode      @0x14b34c
  DialogLevelSelect::addMissionDesc        @0x14bb50
  DialogLevelSelect::getMissionTextPath    @0x14b90c
  DialogLevelSelect::addMissionInfo        @0x14c4a8
  DialogLevelSelect::getBgPreviewNode      @0x14c240
  DialogLevelSelect::getBgNameNode         @0x14c0c4
  DialogLevelSelect::initTrainingMissionReward @0x14ad80
  DialogLevelSelect::initCoinAndCrystal    @0x14ae14
  DialogLevelSelect::setLevelInfo          @0x14cce4
  DialogLevelSelect::enterAnimation        @0x14a534
  DialogLevelSelect::addRecommend{Items,Gun,Ability,Mech,OfferWall}
  DialogHelper::genRecommend{Gun,Ability,Mech}, genOfferWall
  Recommender::getRecommendItems

════════════════════════════════════════════════════════════════════
节点树（initSelectBgNode，全部是 level_start_bg 的子节点）
════════════════════════════════════════════════════════════════════
bg  = level_start_bg.png        anchor(0.5,1.0)  scale k
      pos(W*0.5, H*1.06)        ← ay=1.0 是**顶边**，贴图顶边落在屏幕上方 6%
      k = 0.95（W/H<1.6）否则 1.0；854/480=1.779 → 1.0
  └ content = bg.contentSize = (558,402)   anchor 默认
       ├ rec   = recommend_bg_2.png
       │         anchor(0.5,0.0) pos(558*0.5, 0)  scale k
       │         └ 三个 button_buy.png  anchor(0.5,0.5) scale 5.0
       │            pos(recW*0.23|0.77|0.5, recH*0.4)
       ├ button_accept.png  anchor(0.5,0.5) pos(558*0.5, 402*0.18)
       ├ button_close.png   anchor(0.5,0.5) pos(558*0.83, 402*0.78)
       ├ 任务描述 / 预览框 / 地名 / 奖励（addMissionInfo）
       └ 推荐内容（addRecommendItems → addRecommendGun/Ability/Mech/OfferWall）

子节点坐标以 content 的**左下角**为原点、y 向上：
    屏幕 y = bg_rect.bottom − local_y * k

════════════════════════════════════════════════════════════════════
addMissionInfo 的四个子节点（都以 content 尺寸 v48=(558,402) 为基准）
════════════════════════════════════════════════════════════════════
  preview  preview_bg 容器   pos(w*0.33, h*0.54)   ← 无 anchor 调用 → (0,0)
  name     text_<zone>.png   pos(w*0.49, h*0.738)
  desc     addMissionDesc
  reward   text_reward.png   pos(w*0.28, h*0.32)   （training 时不画）

getBgPreviewNode：容器 contentSize = preview_bg.contentSize (213,128)
    jpg 铺满容器，再叠 preview_bg（边框）；两者 anchor(0.5,0.5) 落在容器中心
    容器自身 anchor=(0,0) → 其左下角在 pos，图向右上长

════════════════════════════════════════════════════════════════════
addMissionDesc（getMissionTextPath 决定段序列）
════════════════════════════════════════════════════════════════════
字体 = GameFonts index 4（shop_gun_number），数字 scale 0.62，段间隔 2*LOGIC
只有一段（training_mission）：
    段 pos(w*0.55, h*0.56)，anchor(0.0, 1.0) ← **左上角**
    guard/hostage：数字自动落到首段下方 h*0.56 − 首段高 − 2*LOGIC
    其它：数字接在首段右侧
两段及以上：
    首段 pos(w*0.59, h*0.59)（hostage_time 用 w*0.53），anchor(0.0,1.0)
    数字 X = 首段右沿 + 2*LOGIC，Y 与其同高
    次段接数字右沿，再串「在 N 秒内」的四段式

════════════════════════════════════════════════════════════════════
initCoinAndCrystal（非 training）
════════════════════════════════════════════════════════════════════
  整节点 scale 0.52，anchor(0.0,0.5)，pos(w*0.46, h*0.32)
  子链全部 anchor(0.0,·)，Y 统一 = coinH*0.5：
    coin   anchor(0,0.54) pos(0, coinH*0.5)                scale 1
    数字   anchor(0,0.5)  pos(coinW*1.1, coinH*0.5)        scale 1.6  font 1
    crystal anchor(0,0.5) pos(数字右沿+coinW, coinH*0.5)
    数字   anchor(0,0.5)  pos(上+coinW*0.1, ·)             scale 1.6  font 3
    gift   anchor(0,0.48) pos(上+coinW*0.1, ·)             scale 0.88
    「1」   anchor(0,0.5)  pos(gift右沿*0.88+coinW*0.1, ·)  scale 1.6  font 0
"""

import pygame

from engine import gridfont, res
from game.dialog import H, W, bg_dim


LOGIC = 1.0

BG_TEX = "pic/ui/dialog/level_start_bg.png"
REC_BG = "pic/ui/dialog/recommend_bg_2.png"
ACCEPT_TEX = "pic/ui/dialog/button_accept.png"
CLOSE_TEX = "pic/ui/dialog/button_close.png"
BUY_TEX = "pic/ui/recommend/button_buy.png"
# 原版这张贴图是 16×16 全透明占位图；按钮 setScale(5.0) 后只剩点击区。
BUY_W, BUY_H = 16, 16
OFFER_TEX = "pic/ui/recommend/offer_wall.png"
PREVIEW_TEX = "pic/ui/dialog/preview_bg.png"
REWARD_LABEL = "pic/ui/dialog/text_reward.png"
GIFT_TEX = "pic/ui/dialog/gift.png"
COIN_TEX = "pic/ui/common/coin.png"

# Recommender::getRecommendAbility @0x177a68（all_merged.c:88092-88240）
# 按**任务类型**给的候选技能表。原版从候选里挑「存档中没有」的，
# hp/power/shield/speed 是前缀 —— 实际技能 ID 要拼 "_1"/"_2"（按关卡 id）。
_RECOMMEND_ABILITIES = {
    "kill_mission": ("hp", "power", "airstrike"),
    "kill_time_mission": ("hp", "power", "airstrike"),
    "time_mission": ("shield", "hp", "airstrike"),
    "distance_mission": ("speed", "shield"),
    "distance_time_mission": ("speed", "shield"),
    "guard_mission": ("power", "mech_7", "airstrike"),
    "hostage_mission": ("fly_1", "fly_2", "airstrike"),
    "hostage_time_mission": ("fly_1", "fly_2", "airstrike"),
    "collect_mission": ("speed", "shield", "hp", "power", "mech_7", "airstrike"),
    "collect_time_mission": ("speed", "shield", "hp", "power", "mech_7", "airstrike"),
    "_default": ("hp", "power", "airstrike"),
}
CRYSTAL_TEX = "pic/ui/common/crystal.png"
TRAIN_REWARD_TEX = "pic/ui/dialog/text_kill_earn.png"

FONT_MISSION = 4  # GameFonts index 4 = shop_gun_number（白）
# 反编译 initCoinAndCrystal 金币数字传的是 index 1（score_gold），
# 但 854×480 参考帧里这一行的数字是**蓝色** score_blue —— 以画面为准用 index 3，
# 水晶数字同理取 index 1（参考帧中水晶数为 0，不渲染，无对照）。
FONT_COIN = 3  # score_blue（参考帧）
FONT_CRYSTAL = 1  # score_gold（参考帧无对照，按反编译对调）
FONT_TRAIN = 0  # score_white

BG_SCALE_NARROW = 0.95
BG_SCALE_DEFAULT = 1.0
BG_POS_Y = 1.06
BG_W, BG_H = 558.0, 402.0

REC_BUY_SCALE = 5.0
PREVIEW_JPG_SCALE = 0.532  # 1057501479
MISSION_NUM_SCALE = 0.62
REWARD_NODE_SCALE = 0.52
REWARD_FONT_SCALE = 1.6
GIFT_SCALE = 0.88
REC_ITEM_SCALE = 0.88

# getMissionTextPath：(首段, 次段)，次段空串表示只有一段
MISSION_TEXT = {
    "kill_mission": ("kill_mission_text_1.png", "kill_mission_text_2.png"),
    "time_mission": ("time_mission_text_1.png", "text_second.png"),
    "distance_mission": ("distance_mission_text_1.png", "distance_mission_text_2.png"),
    "guard_mission": ("guard_mission_text_1.png", "guard_mission_text_2.png"),
    "hostage_mission": ("hostage_mission_text_1.png", "hostage_mission_text_2.png"),
    "collect_mission": ("collect_mission_text_1.png", "collect_mission_text_2.png"),
    # 原版拼写真少个 r，贴图名就是 taining_
    "training_mission": ("taining_mission_text_1.png", ""),
}

# *_time_mission：前置「在 N 秒内」两段 + 主体两段
TIME_WRAPPER = ("text_in.png", "text_in_second.png")
TIME_WRAPPED_BODY = {
    "kill_time_mission": ("kill_mission_text_1.png", "kill_mission_text_2.png"),
    "distance_time_mission": ("distance_mission_text_1.png", "distance_mission_text_2.png"),
    "hostage_time_mission": ("hostage_mission_text_1.png", "hostage_mission_text_2.png"),
    "collect_time_mission": ("collect_mission_text_1.png", "collect_mission_text_2.png"),
}

# getBgPreviewNode / getBgNameNode 的 zone → 贴图
ZONE_PREVIEW = {
    "cemetery": "pic_bg/background/cemetery_01.jpg",
    "bridge": "pic_bg/background/bridge_01.jpg",
    "bankside": "pic_bg/background/bankside_01.jpg",
    "country": "pic_bg/background/country_01.jpg",
    "drainage": "pic_bg/background/drainage_01.jpg",
    "forest": "pic_bg/background/forest_01.jpg",
    "prison": "pic_bg/background/prison_01.jpg",
    "metro": "pic_bg/background/metro_01.jpg",
    "lab": "pic_bg/background/preview_lab.jpg",
    "hospital": "pic_bg/background/preview_hospital.jpg",
    "jailbreak": "pic_bg/background/preview_jailbreak.jpg",
}
ZONE_NAME = {
    "cemetery": "pic/ui/dialog/text_cemetery.png",
    "bridge": "pic/ui/dialog/text_bridge.png",
    "bankside": "pic/ui/dialog/text_bankside.png",
    "country": "pic/ui/dialog/text_country.png",
    "drainage": "pic/ui/dialog/text_drainage.png",
    "forest": "pic/ui/dialog/text_forest.png",
    "prison": "pic/ui/dialog/text_prison.png",
    "metro": "pic/ui/dialog/text_metro.png",
    "lab": "pic/ui/dialog/text_lab.png",
    "hospital": "pic/ui/dialog/text_hospital.png",
    "jailbreak": "pic/ui/dialog/text_jailbreak.png",
}


def bg_scale():
    """initSelectBgNode 的缩放分支：W/H < 1.6 → 0.95，否则 1.0。"""
    return BG_SCALE_NARROW if (W / float(H) if H else 1.0) < 1.6 else BG_SCALE_DEFAULT


def _nine_edges(im):
    """按贴图自身的边框暗线，估出预览框的内沿（左、上、右、下）。"""
    W, H = im.get_size()
    px = im.load()

    def dark(c):
        return c[3] > 60 and c[0] < 90 and c[1] < 85

    left = 0
    for x in range(W // 2):
        if all(dark(px[x, y]) for y in range(H // 4, H * 3 // 4, 4)):
            left = x
        else:
            break
    top = 0
    for y in range(H // 2):
        if all(dark(px[x, y]) for x in range(W // 4, W * 3 // 4, 4)):
            top = y
        else:
            break
    right = W - 1
    for x in range(W - 1, W // 2, -1):
        if all(dark(px[x, y]) for y in range(H // 4, H * 3 // 4, 4)):
            right = x
        else:
            break
    bottom = H - 1
    for y in range(H - 1, H // 2, -1):
        if all(dark(px[x, y]) for x in range(W // 4, W * 3 // 4, 4)):
            bottom = y
        else:
            break
    return left, top, right, bottom


def _cover(im, w, h):
    """按 cover 规则缩放贴图（原版 ContentScale 就是铺满，不留白）。"""
    iw, ih = im.get_size()
    k = max(w / float(iw), h / float(ih))
    return pygame.transform.smoothscale(im, (max(1, int(iw * k)), max(1, int(ih * k))))


def mission_paths(mtype):
    """getMissionTextPath：返回 (贴图名序列, 段数类别)。

    类别决定落位（addMissionDesc 的三个分支）：
      "single"  training_mission            (w*0.55, h*0.56)  无数字
      "pair"    两段，数字夹在中间           (w*0.55, h*0.56)
      "timed"   四段「在 N 秒内」+ 主体      (w*0.59, h*0.59)
                                           hostage_time 用 w*0.53
    """
    if mtype in TIME_WRAPPED_BODY:
        a, b = TIME_WRAPPED_BODY[mtype]
        return [TIME_WRAPPER[0], "num", TIME_WRAPPER[1], a, "num", b], "timed"
    pair = MISSION_TEXT.get(mtype)
    if not pair:
        return [], None
    first, second = pair
    if second:
        return [first, "num", second], "pair"
    return [first], "single"


class LevelSelectDialog:
    """关卡选择框。done = True 表示关闭；accepted = True 表示接任务。"""

    def __init__(self, app, mission_id=None):
        self.app = app
        self.mission_id = int(mission_id or getattr(app, "mission_id", 1))
        self.info = (getattr(app, "level_db", {}) or {}).get(self.mission_id, {})
        self.t = 0.0
        self.done = False
        self.accepted = False
        self.accept_rect = None
        self.close_rect = None
        self.buy_rects = []
        self.rec_hits = []  # [(kind, name, rect)] 推荐条可点区域
        self.scale = bg_scale()
        # enterAnimation：bg 从下方 20px 滑入（0.2s + 0.1s），rec 延迟 0.4s 弹入
        self.anim = 0.0

    # ---------------------------------------------------------- 数据
    def mtype(self):
        return self.info.get("type", "kill_mission")

    def zone(self):
        return self.info.get("zone", "cemetery")

    def target(self):
        """任务目标数字（MissionDesc.number，偏移 +14）。"""
        return int(self.info.get("number", 0))

    def target2(self):
        """第二目标（MissionDesc.number2，偏移 +15）。"""
        return int(self.info.get("number2", 0))

    def reward(self):
        return (int(self.info.get("reward_coin", 0)), int(self.info.get("reward_crystal", 0)))

    def day(self):
        """关卡所在天数（level_list.xml 的 level 字段）。"""
        return int(self.info.get("level", 1)) if self.info else 1

    # ---------------------------------------------------------- 交互
    def update(self, dt):
        self.t += dt
        self.anim = min(1.0, self.anim + dt / 0.3)

    def _compute_button_rects(self):
        """不依赖 draw 就能算出按钮点击区。

        插底保护：accept_rect / close_rect 原本只在 draw() 里赋值，
        玩家在第一次绘制之前点击就永远点不到。
        """
        r = self._bg_rect()
        # 滑入偏移（draw 里也是这么算的）
        slide = int(round((1.0 - min(1.0, self.anim * 3.0)) * 20 * LOGIC))
        r = r.move(0, slide)
        acc = res.load_img(ACCEPT_TEX)
        if acc and self.accept_rect is None:
            ax, ay = self._local(r, BG_W * 0.5, BG_H * 0.18)
            aw = max(1, int(round(acc.get_width() * self.scale)))
            ah = max(1, int(round(acc.get_height() * self.scale)))
            self.accept_rect = pygame.Rect(int(round(ax - aw / 2)), int(round(ay - ah / 2)), aw, ah)
        close = res.load_img(CLOSE_TEX)
        if close and self.close_rect is None:
            cx, cy = self._local(r, BG_W * 0.83, BG_H * 0.78)
            cw = max(1, int(round(close.get_width() * self.scale)))
            ch = max(1, int(round(close.get_height() * self.scale)))
            self.close_rect = pygame.Rect(int(round(cx - cw / 2)), int(round(cy - ch / 2)), cw, ch)

    def click(self, pos):
        if self.accept_rect is None or self.close_rect is None:
            self._compute_button_rects()
        if self.close_rect and self.close_rect.collidepoint(pos):
            self.done = True
            return True
        if self.accept_rect and self.accept_rect.collidepoint(pos):
            self.accepted = True
            self.done = True
            return True
        for kind, name, rect in self.rec_hits:
            if rect.collidepoint(pos):
                self._open_recommend(kind, name)
                return True
        # 旧版这里还留着三个「购买」热区，点了只会弹「没有内购」。
        # 现在推荐格统一走 _open_recommend：跳军火库并选中，不在这里购买。
        return False

    def _open_recommend(self, kind, name):
        """点推荐项 → **直接跳到军火库对应页并选中**，不当场扣钱。

        枪 → gun 页选中这把枪并滚到可见
        道具 → ability 页选中这个道具
        机甲 → mech 页选中这台机甲
        购买一律由商店里的「购买」按钮确认。
        """
        app = self.app
        try:
            app.shop_tab = {"gun": "gun", "mech": "mech"}.get(kind, "ability")
            if kind == "gun":
                from game.shopui import SCROLL_LEAD
                from game.shopui import SHOP_GUNS as _GUNS

                if name:
                    app.shop_sel = name
                idx = next((i for i, g in enumerate(_GUNS) if g["name"] == name), 0)
                app.shop_row = max(0, idx - SCROLL_LEAD)
            elif kind == "mech":
                app.shop_mech = name
            else:
                from game.shop_tabs import ABILITIES as _AB

                idx = next((i for i, it in enumerate(_AB) if it[0] == name), 0)
                app.shop_ability = idx
                app.shop_ability_scroll = 0.0
            self.done = True
            self.go_shop = True
            app.goto("shop")
            app.toast("已为你选中，确认后点「购买」")
        except Exception:
            self.done = True

    # ---------------------------------------------------------- 几何
    def _bg_rect(self):
        """bg 顶边落在屏幕 y = H − H*1.06（屏幕上方 6%），向下探出。"""
        bw = int(round(BG_W * self.scale))
        bh = int(round(BG_H * self.scale))
        left = W * 0.5 - bw / 2.0
        top = H - H * BG_POS_Y
        return pygame.Rect(int(round(left)), int(round(top)), bw, bh)

    def _local(self, r, lx, ly):
        """content 局部坐标（左下原点、y 向上）→ 屏幕坐标。"""
        return (r.x + lx * self.scale, r.bottom - ly * self.scale)

    # ---------------------------------------------------------- 绘制
    def draw(self, s):
        bg = res.load_img(BG_TEX)
        if not bg:
            return
        # 关卡弹窗只盖住中间 558×402，四周露着地图 HUD（军火库按钮、
        # 星星/奖杯、推荐气泡），不压暗的话玩家会以为那些还能点。
        bg_dim(s, 130)
        r = self._bg_rect()
        # enterAnimation：从下方 LOGIC*20 处滑入
        slide = int(round((1.0 - min(1.0, self.anim * 3.0)) * 20 * LOGIC))
        r = r.move(0, slide)

        s.blit(pygame.transform.smoothscale(bg, r.size), r.topleft)

        self._draw_mission_info(s, r)
        self._draw_reward_label(s, r)
        self._draw_reward(s, r)
        self._draw_recommend(s, r)
        self._draw_buttons(s, r)

    # ---- addMissionInfo：预览框 + 地名 ----
    def _draw_preview(self, s, r):
        """getBgPreviewNode：容器 contentSize = preview_bg 尺寸，anchor(0.5,0.5)。

        子节点顺序（tag 0 → 1）：jpg 在下、preview_bg 边框在上。
        jpg 自身 scale = n1057501479 = **0.532**（不是 1.0），
        400×240 * 0.532 = 212.8×127.7 → 正好等于容器 213×128，
        所以这一级缩放只是把 400×240 的底图压进容器尺寸，不存在 cover 裁切。
        """
        jpg = res.load_img(ZONE_PREVIEW.get(self.zone(), ""))
        frame = res.load_img(PREVIEW_TEX)
        if not frame:
            return
        cw, ch = frame.get_width(), frame.get_height()  # 容器 = 边框尺寸
        # getBgPreviewNode 里容器已 setAnchorPoint(0.5,0.5)，
        # addMissionInfo 的 pos(w*0.33, h*0.54) 落的是**容器中心**。
        cx, cy = self._local(r, BG_W * 0.33, BG_H * 0.54)
        box = pygame.Rect(0, 0, int(round(cw * self.scale)), int(round(ch * self.scale)))
        box.center = (int(round(cx)), int(round(cy)))
        # jpg / frame 都以 anchor(0.5,0.5) 落在容器中心
        if jpg:
            # 按 **cover** 铺满预览框，不写死缩放比。
            # 原版 getBgPreviewNode 用 n1057501479=0.532 是把 400×240 的底图
            # 压进 213×128 容器；但本地 pic_bg/background/preview_hospital.jpg
            # 本身就是 213×128 的成品，再乘 0.532 会缩成 113×68，
            # 预览框里露出一圈紫底 —— 参考帧对比一眼就能看出来。
            iw, ih = jpg.get_size()
            k = max(box.width / float(iw), box.height / float(ih))
            tw = max(1, int(round(iw * k)))
            th = max(1, int(round(ih * k)))
            tmp = pygame.transform.smoothscale(jpg, (tw, th))
            clip = s.get_clip()
            s.set_clip(box)
            s.blit(tmp, (box.centerx - tw // 2, box.centery - th // 2))
            s.set_clip(clip)
        s.blit(pygame.transform.smoothscale(frame, box.size), box.topleft)

    def _draw_zone_name(self, s, r):
        im = res.load_img(ZONE_NAME.get(self.zone(), ""))
        if not im:
            return
        # 普通 sprite，默认 anchor(0.5,0.5)
        x, y = self._local(r, BG_W * 0.49, BG_H * 0.738)
        s.blit(im, (int(round(x - im.get_width() / 2)), int(round(y - im.get_height() / 2))))

    def _draw_mission_info(self, s, r):
        self._draw_preview(s, r)
        self._draw_zone_name(s, r)
        self._draw_mission(s, r)

    # ---- addMissionDesc ----
    def _mission_anchor(self, r, kind):
        """addMissionDesc 三个分支的落位比例（content 局部坐标）。"""
        if kind == "timed":
            fx = 0.53 if self.mtype() == "hostage_time_mission" else 0.59
            return self._local(r, BG_W * fx, BG_H * 0.59)
        return self._local(r, BG_W * 0.55, BG_H * 0.56)

    def _draw_mission(self, s, r):
        segs, kind = mission_paths(self.mtype())
        if not segs:
            return
        font = gridfont.get_font(FONT_MISSION)
        x, ay = self._mission_anchor(r, kind)
        top = ay

        items = []
        for seg in segs:
            if seg == "num":
                txt = str(self.target())
                tw = font.text_size(txt, MISSION_NUM_SCALE)[0] if font else 0
                items.append(("num", txt, tw))
            else:
                im = res.load_img("pic/ui/dialog/" + seg)
                items.append(("img", im, im.get_width() if im else 0))
        total = sum(w for _k, _o, w in items) + 2 * LOGIC * (len(items) - 1)
        avail = r.w * 0.94
        k = 1.0
        if total > avail > 0:
            k = avail / float(total)
            x = r.x + (r.w - total * k) * 0.5

        for _kind, obj, w in items:
            if _kind == "num":
                if font:
                    font.draw(s, obj, x, top, MISSION_NUM_SCALE * k, align=(0.0, 0.0))
            elif obj:
                if k < 0.999:
                    obj = pygame.transform.smoothscale(
                        obj, (max(1, int(obj.get_width() * k)), max(1, int(obj.get_height() * k)))
                    )
                s.blit(obj, (int(round(x)), int(round(top))))
            x += (2 * LOGIC + w) * k

    # ---- text_reward.png（training 时不画） ----
    def _draw_reward_label(self, s, r):
        if self.mtype() == "training_mission":
            return
        im = res.load_img(REWARD_LABEL)
        if not im:
            return
        # 普通 sprite，默认 anchor(0.5,0.5)：pos 落在图中心
        x, y = self._local(r, BG_W * 0.28, BG_H * 0.32)
        s.blit(im, (int(round(x - im.get_width() / 2)), int(round(y - im.get_height() / 2))))

    # ---- initCoinAndCrystal / initTrainingMissionReward ----
    def _draw_reward(self, s, r):
        if self.mtype() == "training_mission":
            im = res.load_img(TRAIN_REWARD_TEX)
            if im:
                x, y = self._local(r, BG_W * 0.5, BG_H * 0.32)
                # 默认 anchor(0.5,0.5)：中心落在 pos
                s.blit(
                    im, (int(round(x - im.get_width() / 2)), int(round(y - im.get_height() / 2)))
                )
            return

        coin, crystal = self.reward()
        coin_im = res.load_img(COIN_TEX)
        if not coin_im:
            return

        # ---- 局部链路 ----
        # ★ 间距统一用 GAP，图标按自身高度**垂直居中**到行中线上。
        # 早先照抄反编译的 `lx += tw*scale + cw`（数字宽 + 一整个金币宽 50）
        cw, ch = coin_im.get_size()
        GAP = 6.0  # 图标↔数字的固定间隙（未缩放单位）
        row_y = ch * 0.5  # 行中线
        lx = 0.0
        places = []  # (kind, x_local, y_local, anchor, extra)

        places.append(("coin", 0.0, row_y, (0.0, 0.5), 1.0))
        lx = cw + GAP
        f_coin = gridfont.get_font(FONT_COIN)
        if f_coin and coin > 0:
            places.append(("coin_txt", lx, row_y, (0.0, 0.5), REWARD_FONT_SCALE))
            tw, _ = f_coin.text_size(f"{coin:,}", 1.0)
            lx += tw * REWARD_FONT_SCALE + GAP * 3
        else:
            lx += GAP

        cr_im = res.load_img(CRYSTAL_TEX)
        crw = cr_im.get_width() if cr_im else 0
        if cr_im:
            places.append(("crystal", lx, row_y, (0.0, 0.5), 1.0))
            lx += crw + GAP
        f_cr = gridfont.get_font(FONT_CRYSTAL)
        if f_cr and crystal > 0:
            places.append(("cr_txt", lx, row_y, (0.0, 0.5), REWARD_FONT_SCALE))
            tw, _ = f_cr.text_size(str(crystal), 1.0)
            lx += tw * REWARD_FONT_SCALE + GAP * 3
        elif cr_im:
            lx += GAP

        gift_im = res.load_img(GIFT_TEX)
        if gift_im:
            places.append(("gift", lx, row_y, (0.0, 0.5), GIFT_SCALE))
            lx += gift_im.get_width() * GIFT_SCALE + GAP
        # 原版这里还会 create "1"（font 0, scale 1.6）挂在 gift 右侧。
        # 参考帧 854×480 下 gift 右侧是纯背景（无字形），所以不画；
        # 保留 lx 推进以便将来对位。

        # ---- 整节点 scale 0.52、anchor(0,0.5)、pos(w*0.46, h*0.32) ----
        nx, ny = self._local(r, BG_W * 0.46, BG_H * 0.32)
        k = REWARD_NODE_SCALE

        for kind, px_, py_, (ax, ay), sc in places:
            sx = nx + px_ * k
            sy = ny - (py_ - ch * 0.5) * k
            if kind == "coin_txt":
                f_coin.draw(s, f"{coin:,}", sx, sy, REWARD_FONT_SCALE * k, align=(ax, 0.5))
            elif kind == "cr_txt":
                f_cr.draw(s, str(crystal), sx, sy, REWARD_FONT_SCALE * k, align=(ax, 0.5))
            else:
                im = {"coin": coin_im, "crystal": cr_im, "gift": gift_im}[kind]
                if not im:
                    continue
                w = max(1, int(round(im.get_width() * sc * k)))
                h = max(1, int(round(im.get_height() * sc * k)))
                s.blit(
                    pygame.transform.smoothscale(im, (w, h)),
                    (int(round(sx - w * ax)), int(round(sy - h * ay))),
                )

    # ---- addRecommendItems：三格 + offer_wall ----
    def _rec_rect(self):
        """推荐条是**对话框层**（屏幕空间）的子节点，不是 bg 的。

        initSelectBgNode：`this->addChild(rec)`，anchor(0.5,0.0)，
        pos(W*0.5, 0) —— this[24] 是屏幕逻辑宽，不是 bg 宽。
        屏幕空间原点在左下，y=0 即屏幕底边 → 条子底边贴屏幕底、向下不越界。
        """
        rec = res.load_img(REC_BG)
        if not rec:
            return None
        rw = int(round(rec.get_width() * self.scale))
        rh = int(round(rec.get_height() * self.scale))
        left = W * 0.5 - rw / 2.0
        return pygame.Rect(int(round(left)), H - rh, rw, rh)

    def _draw_recommend(self, s, r):
        """addRecommendItems + addOfferWall。

        循环只跑 2 次（n96 每次 +48 到 96 停），第 3 格是 addOfferWall(2)。
        每格内容 = genRecommend{Gun,Ability,Mech} 的容器，cell = (recW*0.2, recH*0.68)。
        三个 button_buy.png 都 setScale(5.0) 挂在推荐条上，
        但原版这张贴图本身是 16×16 **全透明**，所以画面上看不到「购买」字样；
        点击区仍然存在（onButtonBuyItem0/1/onButtonOfferwall）。
        """
        self.buy_rects = []
        self.rec_hits = []
        rec = res.load_img(REC_BG)
        if not rec:
            return
        rr = self._rec_rect()
        s.blit(pygame.transform.smoothscale(rec, rr.size), rr.topleft)

        items = self.recommend_items()
        for idx in range(2):
            # 推荐项可能只有 1 个（全买光了），别再索引越界
            if idx >= len(items):
                break
            self._draw_rec_cell(s, rr, items[idx], idx)
        offer = self._draw_offer_wall(s, rr)
        if offer is not None:
            # 中间那堆金币（原版 onButtonOfferwall）也是跳军火库的入口。
            gun = next((n for k, n in items if k == "gun"), "")
            self.rec_hits.append(("gun", gun, offer))

        # ★ 不再登记「购买」热区：推荐格只是跳军火库的入口，
        #   购买一律在商店里确认（见 _open_recommend）。
        #   旧的全透明 button_buy 热区留着只会抢点击、弹「没有内购」提示。

    def _draw_offer_wall(self, s, rr):
        """DialogHelper::genOfferWall。

        容器 contentSize = addOfferWall 传进去的 (recW*0.2, recH*0.68)，
        容器本身 anchor(0.5,0.5) 落在 (recW*0.5, recH*0.44)；
        offer_wall.png 在容器内部 pos(cw*0.5, ch*0.48)，默认 anchor(0.5,0.5)，
        再叠 ShinyStarNode（尺寸同容器，pos 容器中心）。
        """
        im = res.load_img(OFFER_TEX)
        if not im:
            return None
        ch = rr.h * 0.68
        # 图在容器内的落点 = 容器中心 + (0.5cw - 0.5cw, 0.48ch - 0.5ch) = 中心 - 0.02*ch
        iw, ih = im.get_size()
        px = rr.x + rr.w * 0.5
        py = rr.bottom - rr.h * 0.44 + (0.5 - 0.48) * ch
        rect = pygame.Rect(int(round(px - iw / 2)), int(round(py - ih / 2)), iw, ih)
        s.blit(im, rect.topleft)
        return rect.inflate(10, 10)

    def _draw_rec_cell(self, s, rr, item, idx):
        """单元格 (recW*0.2, recH*0.68)，图 anchor(0.5,0.5)。

        X：idx 0 用 recW*0.21；idx 1 枪用 0.78、技能/机甲用 0.76（addRecommendGun 0.78，其余 0.76）。
        Y：统一 recH*0.44。
        缩放：genRecommendGun   min(cellH/texH, cellW/texW*1.06)
              genRecommendAbility cellH/texH*1.05
              genRecommendMech     1.1 / 0.8 / mech_5 → 0.95
        """
        kind, name = item
        if kind == "gun":
            im = res.load_img("pic_png/ui/upgrade/gun_%s.png" % name)
        elif kind == "ability":
            im = res.load_img("pic/ui/shop/ability_%s.png" % name)
        elif kind == "mech":
            alt = res.load_img("pic/ui/mech_icon/%s.png" % name)
            im = alt or res.load_img("pic_png/mech/%s.png" % name)
        else:
            return
        if not im:
            return

        cw, ch = rr.w * 0.2, rr.h * 0.68
        if idx == 0:
            fx = 0.21
        else:
            fx = 0.78 if kind == "gun" else 0.76
        cx = rr.x + rr.w * fx
        cy = rr.bottom - rr.h * 0.44

        iw, ih = im.get_size()
        if kind == "gun":
            scale = min(ch / float(ih), cw / float(iw) * 1.06)
        elif kind == "ability":
            scale = ch / float(ih) * 1.05
        elif name in ("mech_1", "mech_3", "mech_4"):
            scale = 1.1
        elif name == "mech_5":
            scale = 0.95
        else:
            scale = 0.8
        scale *= self.scale

        w = max(1, int(round(iw * scale)))
        h = max(1, int(round(ih * scale)))
        cell = pygame.Rect(int(round(cx - w * 0.5)), int(round(cy - h * 0.5)), w, h)
        s.blit(pygame.transform.smoothscale(im, (w, h)), cell.topleft)
        self.rec_hits.append((kind, name, cell.inflate(10, 10)))

    def _draw_buy(self, s, rr, fx):
        """保留旧接口（供测试/外部调用）。

        推荐条不再提供购买入口：既不全透明贴图，也不登记点击热区，
        避免和「点推荐格 = 跳军火库选中」的新行为打架。
        """

    def recommend_items(self):
        """Recommender::getRecommendItems 的等价物：枪 + 技能/机甲两项。

        原版 Recommender::getRecommendAbility @0x177a68（all_merged.c:88092）
        按**任务类型**给候选技能，再挑「玩家还没拥有」的：
            kill_mission / kill_time_mission → hp, power, airstrike
            time_mission                      → shield, hp, airstrike
            distance_mission / distance_time  → speed, shield
            guard_mission                     → power, mech_7, airstrike
            hostage_mission / hostage_time    → fly_1, fly_2, airstrike
            collect_mission / collect_time    → speed, shield, hp, power,
                                                mech_7, airstrike
        hp/power/shield/speed 是**前缀**，原版再拼 "_1"（等级 11~20 用 "_2"）。

        挑法（all_merged.c:88230）：从候选里取存档中**没有**的；
        一个都没有 ⇒ 返回空；有多个 ⇒ 随机取一个。

          1) 完全没按任务类型区分（guard 关该推 mech_7 炮塔技能）
          2) **mech_10 不是技能 ID**（技能表里是 mech_7），
             推出来是个无效 ID，玩家点了什么都不会发生。
        """
        out = []
        save = getattr(self.app, "save", None)
        d = getattr(save, "d", {}) if save else {}

        # 当前第几天（存档 level 键）—— 技能后缀与武器解锁都用它
        try:
            from game.map_points import current_level

            day = int(current_level(save, getattr(self.app, "level_db", None)))
        except Exception:
            day = int(self.mission_id or 1)

        # ★ 用户：「已经购买的枪械就不要出现在推荐名单里面了」。
        #   原版 Recommender::getRecommendItems 只推**没买过**的商品；
        #   等于把玩家正在用的枪又推一遍 —— 点进去只能看到「已装备」。
        #   现在：未拥有 + 已达解锁等级 + 买得起，按便宜优先。
        try:
            from game.shop_table import SHOP_GUNS as _GUNS
        except Exception:
            _GUNS = []
        owned = set(d.get("owned_weapons") or [])
        for key in ("equipped_gun", "current_gun"):
            if d.get(key):
                owned.add(d[key])
        coins = int(d.get("coins") or 0)
        gems = int(d.get("crystals") or d.get("gems") or 0)
        pool = [
            g for g in _GUNS if g["name"] not in owned and int(g.get("unlock_level") or 0) <= day
        ]
        pool.sort(key=lambda g: (int(g.get("coin") or 0), int(g.get("crystal") or 0)))
        affordable = [
            g
            for g in pool
            if int(g.get("coin") or 0) <= coins and int(g.get("crystal") or 0) <= gems
        ]
        pick = affordable or pool
        if pick:
            # 原版是「随机取一个」；这里用 mission_id 取模，行为可复现，
            # 但每一关推的枪不会永远是同一把。
            out.append(("gun", pick[int(self.mission_id) % len(pick)]["name"]))

        # 第二项：按任务类型挑一个「还没拥有」的技能
        mtype = self.info.get("type", "") or ""
        cands = _RECOMMEND_ABILITIES.get(mtype)
        if not cands:
            cands = _RECOMMEND_ABILITIES["_default"]
        # hp/power/shield/speed 是**前缀**，原版拼 "_1"，
        # 但「当前第几天」在 11~20 时拼 "_2"（all_merged.c:88125
        #   `if ((unsigned int)(a3 - 11) <= 9) _M_assign(v21, "_2")`）。
        # a3 的来源：MapLayer+108 = getKeyValue("level", 1)
        #   → DialogLevelSelect::setLevelInfo(a2) → addRecommendItems(a2)
        #   → getRecommendItems(n9=a2) → getRecommendAbility(a3=n9)
        # 即**存档的 level 键（第几天）**，不是 mission_id。
        # 复刻没有独立 level 键，current_level(save, db) 与它等价。
        # （day 已在上面算好，枪推荐和技能后缀共用同一份。）
        suffix = "_2" if 11 <= day <= 20 else "_1"
        full = []
        for c in cands:
            full.append(c if c in ("airstrike", "mech_7", "fly_1", "fly_2") else c + suffix)
        own = set(d.get("owned_abilities") or [])
        missing = [n for n in full if n not in own]
        if missing:
            out.append(("ability", missing[0]))
        return out

    # ---- accept / close ----
    def _draw_buttons(self, s, r):
        """两个按钮都是 content 的子节点，anchor(0.5,0.5)。"""
        acc = res.load_img(ACCEPT_TEX)
        if acc:
            ax, ay = self._local(r, BG_W * 0.5, BG_H * 0.18)
            aw = max(1, int(round(acc.get_width() * self.scale)))
            ah = max(1, int(round(acc.get_height() * self.scale)))
            self.accept_rect = pygame.Rect(int(round(ax - aw / 2)), int(round(ay - ah / 2)), aw, ah)
            s.blit(pygame.transform.smoothscale(acc, (aw, ah)), self.accept_rect.topleft)

        close = res.load_img(CLOSE_TEX)
        if close:
            cx, cy = self._local(r, BG_W * 0.83, BG_H * 0.78)
            cw = max(1, int(round(close.get_width() * self.scale)))
            ch = max(1, int(round(close.get_height() * self.scale)))
            self.close_rect = pygame.Rect(int(round(cx - cw / 2)), int(round(cy - ch / 2)), cw, ch)
            s.blit(pygame.transform.smoothscale(close, (cw, ch)), self.close_rect.topleft)
