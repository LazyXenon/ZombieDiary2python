"""战斗背景（视差滚动层）—— 原版 ScrollBackground。

反编译依据（D:\\Code\\dsh\\full_dump\\all_merged.c）：

  MapLayer::getMissionBgConfigXml @ 0x1224dc
      任务类型 → 背景配置文件名 "level/bg_<zone>_<1|2>.xml"
        kill_mission / kill_time_mission : randInt(10) <= 3 → _2.xml 否则 _1.xml
        distance/hostage/collect(+time)   : 恒 _1.xml
        guard_mission                     : 恒 _2.xml
        其它                             : randInt(10) <= 7 → _2.xml 否则 _1.xml

  BackgroundDefParser::startElement @ 0x17249c
      <parallax_background> → <scroll_background zorder speed_ratio [bg_seq]>
      <scroll_background>  → <background bg_tex= odds=>
      <bg_animations>      → <animation bg_index duration offset_x offset_y ...>

  ScrollBackgroundDef::setScrollBg @ 0x173a24
      zorder / speed_ratio / bg_seq（"0, 1, 3, 2, 4" 拆成 int 序列）/ is_in_water / water_type

  ScrollBackgroundDef::addBgTexture @ 0x1741e8
      bg_tex 存进 vector<string>，odds 存进 vector<int>（每个 <background> 都要有 odds）

  ScrollBackground::composeBackgroundList @ 0x173748   ← 背景节点排布
      变量 v30 = 累积 x 偏移，起始 0.0
      对 bg_seq 里的每个下标 i：
          BgNode = getBgNode(bg_tex[i])
          BgNode.setPosition(v30, H*0.5)          ← 锚点 (0, 0.5)
          BgNode.setVisible(false)
          v30 += BgNode.getContentSize().width - 1.0     ← ★ 步长 = 图宽 - 1
      this[308] = v30                                ← 背景层总宽
      初始 offset = v30*0.5 - this.getContentSize().width*0.5
      然后 updateBackgroundList(offset)

  ScrollBackground::updateBackgroundList @ 0x1736d4
      对每个背景节点：pos.x += offset；再按可见性裁剪

  ScrollBackground::onUpdateOffsetX @ 0x173748
      offset 变化 = a2 * speed_ratio

  ScrollBackground::init @ 0x1741e8 之后的 init 里：
      背景贴图 scale 恒 2.0（节点树实测 sz=[400,480] / 原图 200x240）

  背景资源表（assets/raw/level/bg_<zone>_<1|2>.xml）实测：
      hospital→hospital_01..05   bridge→bridge_01..05     bankside→bankside_01..05
      cemetery→cemetery_01..05   country→country_01..04     drainage→drainage_01..04
      forest→forest_01..05       jailbreak→jailbreak_01..04 lab→factory_01..05
      metro→metro_01..05         prison→prison_01..04

节点树实测（data/node_tree_battle.json，ScrollBackground 子节点）：
  子节点 i 的 pos.x = -770.833 + i*399.0，anchor(0, 0.5)
  第 0 个 sz=[800, 480]，其余 sz=[400, 480]
  贴图 scale 恒为 2.0 —— 即 200x240 的原图纵向拉到 480、横向也乘 2
  → 每张背景图显示宽 = 原图宽 * 2（hospital_01 原图 400 宽 → 800；其余 200 → 400）
  步长 = 显示宽 - 1 ⇒ 800-1=799, 400-1=399 ✓ 与节点树 -770.833 + i*399 吻合
"""

import os
import xml.etree.ElementTree as ET

import pygame

from engine import res


# 背景图缩放倍数（节点树实测：原图 200x240 → 节点 sz 400x480）
BG_SCALE = 2.0

# 设计分辨率宽（原版 EzGameScene::s_LogicSize.width = 853.333）
# ScrollBackground::init 把自己 contentSize 设成 s_LogicSize，
# composeBackgroundList 的居中计算用的就是它 ⇒ base = -(total*0.5 - 853.333*0.5)
LOGIC_W = 853.333

# 背景图缩放缓存：BG_SCALE 是常量，缩放尺寸固定，但每帧 smoothscale
# 一张接近屏宽的大图要 1~2ms，是战斗渲染最大的一笔开销。
_bg_scaled_cache = {}


def _scaled_bg(im, w, h):
    key = (id(im), w, h)
    hit = _bg_scaled_cache.get(key)
    if hit is not None and hit[0] is im:  # 同 id 必须是同一对象，防 id 复用串图
        return hit[1]
    out = im if im.get_size() == (w, h) else pygame.transform.smoothscale(im, (w, h))
    if len(_bg_scaled_cache) > 64:
        _bg_scaled_cache.clear()
    _bg_scaled_cache[key] = (im, out)
    return out


# zone → 背景资源前缀（XML 里写的是这个前缀）
ZONE_BG_PREFIX = {
    "hospital": "hospital",
    "bridge": "bridge",
    "bankside": "bankside",
    "cemetery": "cemetery",
    "country": "country",
    "drainage": "drainage",
    "forest": "forest",
    "jailbreak": "jailbreak",
    "lab": "factory",
    "metro": "metro",
    "prison": "prison",
}

# 任务类型 → 背景配置选择（MapLayer::getMissionBgConfigXml）
#   None 表示走随机分支
_MISSION_BG_RULE = {
    "kill_mission": "rand_le3",  # randInt(10) <= 3 → _2
    "kill_time_mission": "rand_le3",
    "distance_mission": "one",
    "distance_time_mission": "one",
    "hostage_mission": "one",
    "hostage_time_mission": "one",
    "collect_mission": "one",
    "collect_time_mission": "one",
    "guard_mission": "two",
}
# 其它类型：randInt(10) <= 7 → _2 否则 _1
_DEFAULT_RULE = "rand_le7"


def _rule_for(mission_type):
    return _MISSION_BG_RULE.get(mission_type, _DEFAULT_RULE)


def pick_bg_config(zone, mission_type, rng=None):
    """返回背景配置文件名（不含 "level/" 前缀），如 "bg_hospital_1.xml"。

    randInt(10) 的语义：返回 0..9，`<= 3` 即 4/10 概率。
    用调用方 rng（random.Random）以便测试可复现。
    """
    if rng is None:
        import random

        rng = random
    rule = _rule_for(mission_type)
    if rule == "one":
        idx = 1
    elif rule == "two":
        idx = 2
    elif rule == "rand_le3":
        idx = 2 if rng.randint(0, 9) <= 3 else 1
    else:
        idx = 2 if rng.randint(0, 9) <= 7 else 1
    # 配置文件名按 zone（bg_lab_1.xml），但 lab 的贴图是 factory_*（见 XML 内容）
    return "bg_%s_%d.xml" % (zone, idx)


class ScrollBackground:
    """按 XML 描述的滚动背景层。

    属性：
      textures  贴图路径列表（已按 bg_seq 重排）
      seq       bg_seq（None 表示不重排）
      zorder    层序
      speed_ratio 滚动速度比
    """

    def __init__(self, cfg_name):
        self.cfg_name = cfg_name
        self.textures = []
        self.seq = None
        self.zorder = 1
        self.speed_ratio = 1.0
        self.animations = []
        self._load()

    def _load(self):
        txt = res.load_xml("level/" + self.cfg_name)
        if not txt:
            return
        try:
            root = ET.fromstring(txt)
        except ET.ParseError:
            return
        for sb in root.iter("scroll_background"):
            self.zorder = int(sb.get("zorder", 1))
            self.speed_ratio = float(sb.get("speed_ratio", 1.0))
            seq = sb.get("bg_seq")
            if seq:
                self.seq = [int(x) for x in seq.replace(" ", "").split(",") if x != ""]
            for bg in sb.findall("background"):
                tex = bg.get("bg_tex")
                if tex:
                    self.textures.append(tex)
        for anim in root.iter("animation"):
            self.animations.append(
                dict(
                    bg_index=int(anim.get("bg_index", 0)),
                    duration=float(anim.get("duration", 1.0)),
                    offset_x=float(anim.get("offset_x", 0.0)),
                    offset_y=float(anim.get("offset_y", 0.0)),
                    sheet_xml=anim.get("sheet_xml", ""),
                    animation_xml=anim.get("animatioin_xml", "") or anim.get("animation_xml", ""),
                )
            )

    def ordered(self):
        """按 bg_seq 重排后的贴图列表。

        bg_seq 是「图片下标序列」，可能比贴图数多（可重复），
        例如 drainage_2 的 "1, 2, 0, 3, 1" 有 5 项而贴图只有 4 张。
        序列下标超出贴图数时按末尾元素循环取用。
        """
        if not self.seq:
            return list(self.textures)
        out = []
        n = len(self.textures)
        if n == 0:
            return out
        for i in self.seq:
            out.append(self.textures[min(i, n - 1)])
        return out

    def layout(self):
        """按 composeBackgroundList 的公式算出每个背景节点的 (贴图, x, 显示宽)。

        返回 [(tex_path, x, disp_w), ...]，x 是 cocos 局部坐标（锚点 (0,0.5)）。
        """
        import pygame

        out = []
        x = 0.0
        for t in self.ordered():
            im = res.load_img(t)
            if im is None:
                continue
            disp_w = im.get_width() * BG_SCALE
            out.append((t, x, disp_w))
            x += disp_w - 1.0
        return out

    def total_width(self):
        """背景层总宽 this[308] = v30。

        composeBackgroundList 里 v30 是逐步累加的：
            v30 = 0;  对每张图 v30 += 显示宽 - 1
        hospital 一组：799 + 399*4 = 2395
        """
        items = self.layout()
        if not items:
            return 0.0
        return sum(dw - 1.0 for _t, _x, dw in items)

    def draw(self, surf, offset_x=0.0, W=854, H=480, dim=0):
        """把背景层画到 surf。

        几何照抄 composeBackgroundList：
          x[0] = 0，x[i+1] = x[i] + 显示宽 - 1
          初始 offset = 总宽*0.5 - 屏宽*0.5（居中）
          相机右移 offset_x 时，背景左移 offset_x * speed_ratio

        参数 offset_x 是「相机已右移的距离」（逻辑像素）。
        """
        import pygame

        items = self.layout()
        if not items:
            return
        total = self.total_width()
        # 初始偏移：composeBackgroundList 里是
        #   v28 = v30*0.5 - 屏宽*0.5
        #   updateBackgroundList(COERCE_FLOAT(v28 + 0x80000000))  ← +0x80000000 是浮点取负
        # 即 offset = -(total*0.5 - W*0.5)
        base = -(total * 0.5 - LOGIC_W * 0.5)
        off = base - offset_x * self.speed_ratio

        # ★ 铺底兜底：贴图缺失 / 配置异常时也不能露纯黑。首图拉伸到整屏，
        #   正常情况下会被下面的真实节点完全盖住（初始 off≈-770.8，
        #   覆盖 [-770.8, 1624] ⊇ [0, W]），故已对拍过的初始画面零影响。
        first = res.load_img(items[0][0])
        if first is not None:
            surf.blit(_scaled_bg(first, int(W), int(H)), (0, 0))
        else:
            surf.fill((22, 32, 42))

        # ★ 滚动边界：背景层总宽 total 有限（hospital ≈2395），相机右移
        #   超过 total*0.5 - W*0.5 ≈ 771px 后最后一张图也滑出屏幕，右侧
        #   露出未绘制区（实测 cam=1400 黑 629px、cam=2400 全黑）。
        #   原版 ScrollBackground::updateBackgroundList 会循环复用节点；
        #   这里把 off 回卷进一个周期（等价于夹取滚动边界），再按
        #   off / off+total 铺两遍，任意相机位置 [0, W] 都落在背景上。
        #   off % total - total 在初始 off=-770.8 时仍等于 -770.8（不变）。
        period = total if total > 0 else 0.0
        if period > 0:
            off = off % period - period
            reps = (0.0, period)
        else:
            reps = (0.0,)
        for rep in reps:
            for t, x, disp_w in items:
                im = res.load_img(t)
                if im is None:
                    continue
                w = max(1, int(round(disp_w)))
                h = max(1, int(round(im.get_height() * BG_SCALE)))
                # 缩放尺寸固定，每帧 smoothscale 一张大图要 1~2ms；缓存结果。
                img = _scaled_bg(im, w, h)
                sx = int(round(x + off + rep))
                if sx + img.get_width() > 0 and sx < W:
                    surf.blit(img, (sx, 0))
        if dim:
            d = pygame.Surface((W, H), pygame.SRCALPHA)
            d.fill((0, 0, 0, dim))
            surf.blit(d, (0, 0))


def load_scroll_background(zone, mission_type, rng=None):
    """按 zone + 任务类型载入滚动背景；配置缺失时返回 None。"""
    cfg = pick_bg_config(zone, mission_type, rng)
    path = os.path.join("level", cfg)
    txt = res.load_xml(path)
    if not txt:
        return None
    return ScrollBackground(cfg)
