"""cocos2d-x 2.1.4 语义渲染器（Python/pygame 移植）

坐标原语逐行移植自 engine/cc.js（其来源是 CCNode::nodeToParentTransform 源码）：
    m_sTransform = CCAffineTransformMake(
        cy*sx, sy*sx, -sn*sy, cx*sy, x, y)
    x = pos.x + cy*-apx*sx + -sn*-apy*sy
    y = pos.y + sn*-apx*sx +  cx*-apy*sy
    radians = -DEGREES_TO_RADIANS(rotation)   # cocos 顺时针为正

屏幕映射：screenY = H - cocosY（cocos y 向上，pygame y 向下）。

用法：
    rows = load_jsonl("data/node_tree_menu.json")
    roots = build_tree(rows)
    tex = load_tex("data/node_tex_menu9.json")
    draw_tree(surf, roots, tex)
"""

import contextlib
import json
import math
import re

import pygame

from engine import fonts as _fonts
from engine import res


# 容器类：pos 不减锚点（setIgnoreAnchorPointForPosition(true)），且不画自身贴图
# cocos2d 里 CCLayer / CCNode 默认 m_bIgnoreAnchorPointForPosition=true，
# 平移 = pos − rotate(ap*contentSize)。这里按类名判定"是否忽略锚点"。
# cocos2d-x 2.1.4 的两条事实：
#   1) CCLayer::init() 里 setIgnoreAnchorPointForPosition(true) —— Layer/Scene 系恒忽略锚点；
#   2) CCNode::setAnchorPoint() 会把 m_bIgnoreAnchorPointForPosition 置 false ——
#      任何调用过 setAnchorPoint 的普通 CCNode/CCSprite 都要走锚点公式。
# 因此"不画自己贴图"（容器）与"不做锚点偏移"（Layer 系）是两件不同的事，必须分开判。
CONT = ("Layer", "Scene", "Node", "BattleField", "UIBoard", "Dialog", "Color")
# 真正的 Layer 系：锚点不参与平移
LAYER_LIKE = ("Layer", "Scene", "BattleField", "UIBoard", "Dialog", "Color")

_MANGLE = re.compile(r"(\d+)([A-Za-z_][A-Za-z0-9_]*)")


def demangle(cls):
    """N5ezjoy8EzSpriteE -> ezjoy::EzSprite；已可读则原样返回。"""
    if not cls:
        return ""
    if "::" in cls or not cls.startswith("N"):
        return cls
    parts = _MANGLE.findall(cls[1:])
    return "::".join(p[1] for p in parts) if parts else cls


def is_container(cls):
    # 用"包含"而不是"结尾"判定：DialogLevelSelect / MainMenuScene 等类名后缀多样
    return any(t in cls for t in CONT)


def ignores_anchor(cls):
    """是否忽略锚点（平移 = pos 而不是 pos − rotate(ap*size)）。

    只有 Layer/Scene 系恒为真；普通 CCNode/CCSprite 一旦设过 anchorPoint 就是假。
    判据：类名属 Layer 系，或 size 为 0 且 anchor 为 0（无锚点可言）。
    """
    return any(t in cls for t in LAYER_LIKE)


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            with contextlib.suppress(Exception):
                rows.append(json.loads(line, strict=False))
    return rows


def load_tex(path):
    """读取 join9/glyph2 产出的贴图表：{resolved, sub, glyph}"""
    with open(path, encoding="utf-8", errors="replace") as f:
        d = json.load(f)
    return d.get("resolved", {}), d.get("sub", {}), d.get("glyph", {})


def build_tree(rows):
    """按 parent 建树。dump 的 parent 恒比真实地址小 4，故 +4/-4 都试。"""
    by = {}
    for r in rows:
        by[r.get("addr")] = r
        r["kids"] = []
    roots = []
    for r in rows:
        p = r.get("parent")
        pe = None
        if p:
            pe = by.get(p)
            if pe is None:
                try:
                    pn = int(p, 16)
                except Exception:
                    pn = None
                if pn is not None:
                    for cand in (pn + 4, pn - 4):
                        k = "0x%08x" % (cand & 0xFFFFFFFF)
                        if k in by:
                            pe = by[k]
                            break
        if pe is not None and pe is not r:
            pe["kids"].append(r)
        else:
            roots.append(r)
    # 静态字段一次性解析（局部矩阵 / 类名判定 / 可见子节点）
    for r in rows:
        prep(r, deep=False)
    return roots


def _local_matrix(n):
    """算节点自身的局部矩阵（进父空间）。纯函数，结果只依赖节点静态字段。"""
    pos = n.get("pos") or [0.0, 0.0]
    ap = n.get("ap") or [0.5, 0.5]
    sc = n.get("sc") or [1.0, 1.0]
    sz = n.get("sz") or [0.0, 0.0]
    rot = n.get("rot") or 0.0
    sx = sc[0] if sc[0] not in (None, 0) else 1.0
    sy = sc[1] if len(sc) > 1 and sc[1] not in (None, 0) else sx
    cls = demangle(n.get("cls") or "")

    r = -rot * math.pi / 180.0
    c = math.cos(r)
    s = math.sin(r)

    if ignores_anchor(cls):
        # Layer/Scene 系：锚点不参与平移
        return (c * sx, s * sx, -s * sy, c * sy, csafe(pos[0]), csafe(pos[1]))

    apx = (ap[0] or 0.0) * (sz[0] or 0.0)
    apy = (ap[1] or 0.0) * (sz[1] or 0.0)
    x = csafe(pos[0])
    y = csafe(pos[1])
    if apx == 0.0 and apy == 0.0:
        return (c * sx, s * sx, -s * sy, c * sy, x, y)
    x += c * -apx * sx + -s * -apy * sy
    y += s * -apx * sx + c * -apy * sy
    return (c * sx, s * sx, -s * sy, c * sy, x, y)


def prep(n, deep=True):
    """把节点的静态渲染字段解析一次挂到节点上。

    dump 出来的节点树在运行期**不会改**（根节点的归一化除外，见
    `_prep_root`），所以"类名去装饰 / 是否容器 / 是否 Layer 系 /
    可见子节点列表 / 局部矩阵"这些每帧都要用的东西没必要每帧重算。
    一次预算后的收益：draw_tree 里不再有正则、字符串 in 判定和 8 次
    dict.get —— 这些原本每帧占掉战斗场景约 1/4 的渲染时间。
    """
    cls = demangle(n.get("cls") or "")
    n["_cls"] = cls
    n["_cont"] = is_container(cls)
    n["_L"] = _local_matrix(n)
    kids = n.get("kids") or ()
    n["_kids"] = [k for k in kids if k.get("vis") != 0]
    if deep:
        for k in n["_kids"]:
            prep(k, True)
    return n


def node_to_parent(n):
    L = n.get("_L")
    if L is not None:
        return [L[0], L[1], L[2], L[3], L[4], L[5]]
    return list(_local_matrix(n))


def csafe(v):
    try:
        return float(v) if v is not None else 0.0
    except Exception:
        return 0.0


def mul(A, B):
    """子 ⊗ 父（行向量约定，与 cc.js 一致）"""
    return [
        A[0] * B[0] + A[1] * B[2],
        A[0] * B[1] + A[1] * B[3],
        A[2] * B[0] + A[3] * B[2],
        A[2] * B[1] + A[3] * B[3],
        A[4] * B[0] + A[5] * B[2] + B[4],
        A[4] * B[1] + A[5] * B[3] + B[5],
    ]


IDENT = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]


_sub_cache = {}


def _sub_image(im, sub):
    key = (id(im), tuple(sub))
    hit = _sub_cache.get(key)
    # 命中前要确认还是同一张贴图对象：只按 id 缓存会踩「对象被回收后 id 复用」，
    # 表现为偶发的错图/1 像素级色差（GC 时机不同，结果就不同）。
    if hit is not None and hit[0] is im:
        return hit[1]
    try:
        x, y, w, h = [int(round(v)) for v in sub]
        rect = pygame.Rect(x, y, max(1, w), max(1, h))
        out = im.subsurface(rect.clip(im.get_rect())).copy()
    except Exception:
        out = im
    if len(_sub_cache) > 512:
        _sub_cache.clear()
    _sub_cache[key] = (im, out)  # 同时保活原图，锁死 id 不被复用
    return out


# 变换结果缓存：节点树每帧重绘，同一张贴图 + 同一个缩放尺寸会重复
# smoothscale（双线性插值，实测占 draw_battle 约 60% 的时间）。
# 缓存键 = (贴图 id, 目标宽, 目标高, 翻转标志, alpha)。
# 贴图对象是 res.load_img 的单例，id 稳定；res.clear_cache() 会换新对象，
# 所以对象被回收后缓存自然失效（key 里带 id，不会串图）。
_scaled_cache = {}


def _scaled(im, tw, th, flip_x=False, flip_y=False, alpha=255):
    key = (id(im), tw, th, flip_x, flip_y, alpha)
    hit = _scaled_cache.get(key)
    if hit is not None and hit[0] is im:  # 同 id 必须是同一对象，防 id 复用串图
        return hit[1]
    img = im
    if (tw, th) != im.get_size():
        img = pygame.transform.smoothscale(img, (tw, th))
    if flip_x:
        img = pygame.transform.flip(img, True, False)
    if flip_y:
        img = pygame.transform.flip(img, False, True)
    if alpha < 255:
        img = img.copy()
        img.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
    # 缓存只留最近的一批，避免无限增长
    if len(_scaled_cache) > 512:
        _scaled_cache.clear()
    _scaled_cache[key] = (im, img)  # 同时保活原图
    return img


def scaled(im, w, h):
    """smoothscale 的记忆版：贴图对象与目标尺寸都不变时直接复用上次的结果。

    界面上大量小图标（金币/钻石/子弹/武器）每帧都在按同一个尺寸重算缩放，
    单次 smoothscale 虽小，商店一帧 40 次就能吃掉近 30% 的帧时间。
    """
    if im.get_width() == w and im.get_height() == h:
        return im
    return _scaled(im, w, h)


def clear_scaled_cache():
    _scaled_cache.clear()
    _sub_cache.clear()


def blit_matrix(surf, im, W, sz, design_h, alpha=255):
    """把「贴图（含 sub）」按 cocos 世界矩阵 W 贴到 surf。

    贴图在 cocos 局部空间覆盖 (0,0)-(w,h)（y 向上，行 0 在 y=h 即顶部）；
    屏幕 y 向下，所以轴对齐时直接把行 0 贴到较小 screen y 即可。
    """
    a, b, c, d, tx, ty = W
    im_w = im.get_width()
    im_h = im.get_height()
    if not im_w or not im_h:
        # 空贴图（字形图集里没切到、子矩形被裁成 0 面积）：没有像素可画。
        # 旧实现会把它 smoothscale 成 1x1 再贴出去，那 1 个像素的内容是
        # 未定义的（实测每次运行颜色都可能不同），算「画了」但不产生画面。
        return True
    w = sz[0] if sz and sz[0] else im_w
    h = sz[1] if sz and sz[1] else im_h

    # 快速路径：轴对齐 + 无缩放 + 无旋转（界面节点里占绝大多数）。
    # 省掉 4 点变换、hypot、以及平滑缩放的查表开销，直接算出落点。
    if a == 1.0 and b == 0.0 and c == 0.0 and d == 1.0:
        x0 = int(round(tx))
        y0 = int(round(design_h - ty - h))
        if alpha == 255:
            img = im
        else:
            img = _scaled(im, im_w, im_h, False, False, alpha)
        bounds = surf.get_rect()
        if (
            x0 + img.get_width() <= bounds.left
            or x0 >= bounds.right
            or y0 + img.get_height() <= bounds.top
            or y0 >= bounds.bottom
        ):
            return True  # 整块在屏外：不用画（但不算缺失贴图）
        surf.blit(img, (x0, y0))
        return True

    pts = []
    for lx, ly in ((0, 0), (w, 0), (w, h), (0, h)):
        X = a * lx + c * ly + tx
        Y = b * lx + d * ly + ty
        pts.append((X, design_h - Y))

    sx = math.hypot(a, b)
    sy = math.hypot(c, d)
    if sx < 1e-6 or sy < 1e-6:
        return False

    tw = max(1, int(round(im.get_width() * sx)))
    th = max(1, int(round(im.get_height() * sy)))
    flip_x = a < 0
    flip_y = d < 0
    img = _scaled(im, tw, th, flip_x, flip_y, alpha)

    axis = abs(b) < 1e-4 and abs(c) < 1e-4
    if axis:
        x0 = min(p[0] for p in pts)
        y0 = min(p[1] for p in pts)
        dx, dy = int(round(x0)), int(round(y0))
        bounds = surf.get_rect()
        if (
            dx + img.get_width() <= bounds.left
            or dx >= bounds.right
            or dy + img.get_height() <= bounds.top
            or dy >= bounds.bottom
        ):
            return True
        surf.blit(img, (dx, dy))
    else:
        ang = -math.degrees(math.atan2(b, a))
        img = pygame.transform.rotate(img, ang)
        cx = sum(p[0] for p in pts) / 4.0
        cy = sum(p[1] for p in pts) / 4.0
        # 落点按「中心 - 半宽」取整（与工程其它地方一致）；用 get_rect(center=)
        # 时 SDL 走的是 center - w//2，奇数尺寸会差 1px。
        surf.blit(
            img, (int(round(cx - img.get_width() / 2.0)), int(round(cy - img.get_height() / 2.0)))
        )
    return True


_rects_cache = {}


def node_rects(roots, texmap, submap=None, design_h=480, want=()):
    """返回指定 addr 的屏幕矩形 {addr: (x, y, w, h)}，供 UI 依图标真实位置排版。

    节点树是静态的，结果只跟 (树, want, design_h) 有关 —— 顶栏每帧都问
    同一个问题，把答案记住即可，别每帧重新走一遍全树 + 查贴图。
    """
    key = (id(roots), id(texmap), design_h, tuple(want))
    hit = _rects_cache.get(key)
    if hit is not None and hit[0] is roots:
        return dict(hit[1])
    want = set(want)
    submap = submap or {}
    out = {}
    for r in roots:
        r["sc"] = [1.0, 1.0]
        r["pos"] = [0.0, 0.0]
        r["ap"] = [0.0, 0.0]
        r["rot"] = 0.0
        prep(r, deep=False)  # 根节点字段被改写后要重算局部矩阵

    def walk(n, pm):
        L = n.get("_L")
        if L is None:
            L = _local_matrix(n)
        pa, pb, pc, pd, ptx, pty = pm
        a = L[0] * pa + L[1] * pc
        b = L[0] * pb + L[1] * pd
        c = L[2] * pa + L[3] * pc
        d = L[2] * pb + L[3] * pd
        tx = L[4] * pa + L[5] * pc + ptx
        ty = L[4] * pb + L[5] * pd + pty
        addr = n.get("addr")
        if addr in want:
            im = res.load_img(texmap.get(addr) or "")
            w = im.get_width() if im else 0
            h = im.get_height() if im else 0
            sub = submap.get(addr)
            if sub:
                w, h = sub[2], sub[3]
            sz = n.get("sz") or [0.0, 0.0]
            w = sz[0] if sz[0] else w
            h = sz[1] if len(sz) > 1 and sz[1] else h
            xs, ys = [], []
            for lx, ly in ((0, 0), (w, 0), (w, h), (0, h)):
                xs.append(a * lx + c * ly + tx)
                ys.append(design_h - (b * lx + d * ly + ty))
            out[addr] = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        kids = n.get("_kids")
        if kids is None:
            kids = n.get("kids") or ()
        for k in kids:
            walk(k, (a, b, c, d, tx, ty))

    for r in roots:
        walk(r, IDENT)
    if len(_rects_cache) > 64:
        _rects_cache.clear()
    _rects_cache[key] = (roots, dict(out))  # 存 roots 引用，防 id 复用串图
    return out


def draw_tree(
    surf,
    roots,
    texmap,
    submap=None,
    glyphmap=None,
    design_h=480,
    hide=None,
    texfix=None,
    skip_addr=None,
    bg_tex=None,
    nine=None,
    nine_margin=40,
    skip_cls=(),
    skip_tex=(),
    only=None,
    exclude=None,
    opa_fn=None,
    skip_subtree_cls=(),
):
    """渲染整棵树。返回绘制计数。

    only    只绘制该 addr 子树（祖先仍参与变换），用于「弹窗层」单独一遍。
    exclude 跳过该 addr 及其整棵子树，用于「主城层」单独一遍。
    """
    submap = submap or {}
    glyphmap = glyphmap or {}
    hide = hide or set()
    texfix = texfix or {}
    skip_addr = skip_addr or set()
    skip_cls = tuple(skip_cls or ())
    skip_tex = tuple(skip_tex or ())
    skip_subtree_cls = tuple(skip_subtree_cls or ())
    only = only or None
    exclude = exclude or set()
    stats = {"drawn": 0, "missing": []}

    if bg_tex:
        im = res.load_img(bg_tex)
        if im:
            # 背景整屏拉伸走缓存：同一张底图每帧缩放结果完全一样，
            # 而 427x240→854x480 的 smoothscale 单次约 0.9ms，是纯浪费。
            surf.blit(_scaled(im, surf.get_width(), surf.get_height()), (0, 0))

    # 根场景是竖屏残留（sz=[540,1920] sc=[0,2.25] pos=[2.25,1200]），必须钳成单位变换
    for r in roots:
        r["sc"] = [1.0, 1.0]
        r["pos"] = [0.0, 0.0]
        r["ap"] = [0.0, 0.0]
        r["rot"] = 0.0
        prep(r, deep=False)  # 根字段被改写后要重算局部矩阵

    _blit = blit_matrix
    _load = res.load_img
    _sub = _sub_image
    _nine = _draw_nine

    def walk(n, pm, under=False):
        addr = n.get("addr")
        if addr in hide or n.get("_hide") or addr in exclude:
            return
        cls = n.get("_cls")
        if cls is None:
            cls = demangle(n.get("cls") or "")
        # 整棵子树都不画（如战斗的视差背景层，改由调用方按关卡动态绘制）
        for t in skip_subtree_cls:
            if cls.endswith(t):
                return
        if only is not None and addr == only:
            under = True
        L = n.get("_L")
        if L is None:
            L = _local_matrix(n)
        pa, pb, pc, pd, ptx, pty = pm
        a = L[0] * pa + L[1] * pc
        b = L[0] * pb + L[1] * pd
        c = L[2] * pa + L[3] * pc
        d = L[2] * pb + L[3] * pd
        tx = L[4] * pa + L[5] * pc + ptx
        ty = L[4] * pb + L[5] * pd + pty
        W = (a, b, c, d, tx, ty)

        do_self = addr not in skip_addr and (only is None or under)
        cont = n.get("_cont")
        if cont is None:
            cont = is_container(cls)
        if do_self:
            # 骨骼部件由 Skeleton 统一绘制，节点树里不画
            for t in skip_cls:
                if cls.endswith(t):
                    do_self = False
                    break

        if do_self:
            sz = n.get("sz") or [0.0, 0.0]
            drew = False
            g = glyphmap.get(addr)
            if g:
                im = _load(g["font"])
                if im:
                    drew = _blit(surf, _sub(im, [g["cx"], 0, g["cw"], g["ch"]]), W, sz, design_h)
            elif not cont:
                tex = texfix.get(addr) or texmap.get(addr)
                if tex and skip_tex:
                    for s in skip_tex:
                        if s in tex:
                            tex = None
                            break
                if tex:
                    im = _load(tex)
                    if im:
                        sub = submap.get(addr)
                        if sub:
                            im = _sub(im, sub)
                        alpha = 255
                        if opa_fn:
                            a2 = opa_fn(n, tex)
                            if a2 is not None:
                                alpha = max(0, min(255, int(a2)))
                        drew = _blit(surf, im, W, sz, design_h, alpha)
                elif nine and addr in nine:
                    drew = _nine(surf, nine[addr], W, sz, design_h, nine_margin)
            if drew:
                stats["drawn"] += 1
            elif not cont and addr not in glyphmap:
                stats["missing"].append(addr)

        kids = n.get("_kids")
        if kids is None:
            kids = [k for k in (n.get("kids") or ()) if k.get("vis") != 0]
        for k in kids:
            walk(k, W, under)

    for r in roots:
        walk(r, IDENT, False)
    return stats


def _draw_nine(surf, tex, W, sz, design_h, margin):
    """九宫格：四角 + 四边 + 中心，共 9 次贴图。"""
    im = res.load_img(tex)
    if not im:
        return False
    a, b, c, d, tx, ty = W
    w, h = sz[0], sz[1]
    tw, th = im.get_width(), im.get_height()
    m = max(1, min(margin, min(tw, th) // 2))
    if w < m * 2 or h < m * 2:
        return blit_matrix(surf, im, W, sz, design_h)

    # 九宫格在局部 (0,0)-(w,h) 内分 3x3
    oxs = [0, m, w - m]
    oys = [0, m, h - m]
    ews = [m, max(1.0, w - 2 * m), m]
    ehs = [m, max(1.0, h - 2 * m), m]
    sxs = [0, m, tw - m]
    sys = [0, m, th - m]
    sws = [m, max(1, tw - 2 * m), m]
    shs = [m, max(1, th - 2 * m), m]
    ok = False
    for i in range(3):
        for j in range(3):
            if ews[i] <= 0 or ehs[j] <= 0:
                continue
            try:
                piece = im.subsurface(pygame.Rect(sxs[i], sys[j], sws[i], shs[j])).copy()
            except Exception:
                continue
            piece = pygame.transform.smoothscale(piece, (max(1, int(ews[i])), max(1, int(ehs[j]))))
            # 该格的局部原点（在 cocos 局部坐标里 y 向上：格 y 起点 = h - (oys[j]+ehs[j])）
            lx = oxs[i]
            ly = h - (oys[j] + ehs[j])
            X = a * lx + c * ly + tx
            Y = b * lx + d * ly + ty
            surf.blit(piece, (int(round(X)), int(round(design_h - Y - ehs[j]))))
            ok = True
    return ok
