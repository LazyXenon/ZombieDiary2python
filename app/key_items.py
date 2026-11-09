"""按界面收集「键盘可以选中的矩形」。

为什么集中在这里，而不是让每个界面类自己实现 key_items()：
  1. 各界面本来就把可点区域存成了 rect / rects 字段（那是绘制时算的），
     直接反射取出来最省事，也不用为了键盘去改十几个类；
  2. 新增界面自动就能被键盘选中（`_auto_items` 扫 `*_rect` / `*_rects`），
     不会出现「新加的按钮鼠标能点、键盘选不到」这种长期漏项。

清单只决定「框画在哪、回车点哪」，触发一律走 App.click(rect.center)，
所以键盘与鼠标的行为永远一致。
"""

import pygame

from app.constants import UI
from app.keynav import as_rect


_SKIP_WORDS = ("bg", "mask", "cover", "panel", "fullscr", "layer", "shadow")


def _ok_name(name):
    low = name.lower()
    return not any(w in low for w in _SKIP_WORDS)


def _collect(val, depth=0):
    """从「Rect / 四元组 / list / dict」里把所有矩形挖出来。"""
    if depth > 2:
        return []
    r = as_rect(val)
    if r is not None:
        return [r]
    out = []
    if isinstance(val, dict):
        for v in val.values():
            out.extend(_collect(v, depth + 1))
    elif isinstance(val, (list, tuple)):
        for v in val:
            out.extend(_collect(v, depth + 1))
    return out


def _auto_items(obj, skip=()):
    """反射收集 obj 上的 `*_rect` / `*_rects`（字段或方法）。"""
    if obj is None:
        return []
    names = list(getattr(obj, "__dict__", {}))
    # 方法不算实例属性，得再从类上补一遍：设置面板的开关行 / 改键框就是
    # `_switch_rects()` / `_keybind_rects()` 这种无参方法算出来的。
    for cls in type(obj).__mro__:
        for n in getattr(cls, "__dict__", {}):
            if n.endswith("_rects") and n not in names:
                names.append(n)
    out = []
    for name in names:
        if name in skip or not _ok_name(name):
            continue
        if name.endswith("_rects"):
            label = name[:-6]
        elif name.endswith("_rect"):
            label = name[:-5]
        else:
            continue
        try:
            val = getattr(obj, name, None)
            if callable(val):
                if not name.endswith("_rects"):
                    continue
                val = val()
        except Exception:
            # 依赖状态的矩形方法可能暂时算不出来，跳过即可，
            # 绝不能让键盘清单把一帧渲染搞崩。
            continue
        for r in _collect(val):
            out.append((r, label))
    # 去重：同一个按钮常常既有 `spin_rects` 又有 `_spin_button_rects()`，
    # 两个都要留着（不同界面用到不同那个），但焦点清单里只能出现一次，
    # 否则方向键会在同一个按钮上「原地走三步」。
    uniq, seen = [], set()
    for r, label in out:
        key = (r.x, r.y, r.w, r.h)
        if key in seen:
            continue
        seen.add(key)
        uniq.append((r, label))
    return uniq


def _dialog_items(dlg):
    """弹窗 / 覆盖面板：按钮统一来自 buttons（DButton 自带 rect / enabled）。"""
    # 复杂界面（设置页 / 签到页 / 结算面板）自己知道「当前页哪些东西真的能点」，
    # 反射会把别的页签里的控件也算进来，框会悬在看不见的地方。
    custom = getattr(dlg, "key_items", None)
    if callable(custom):
        try:
            return custom()
        except Exception:
            pass
    out = []
    for b in getattr(dlg, "buttons", ()) or ():
        if not getattr(b, "enabled", True):
            continue
        r = as_rect(getattr(b, "rect", None))
        if r is not None:
            out.append((r, getattr(b, "name", "") or "button"))
    # 除了标准按钮，还有手绘的（僵尸商店的兑换项、签到页的领取键…）
    out.extend(_auto_items(dlg, skip=("buttons",)))
    return out


def _main_menu_items(mm):
    out = []
    for name, label in (
        ("play_rect", "开始游戏"),
        ("intro_rect", "玩法介绍"),
        ("more_rect", "更多游戏"),
        ("music_rect", "音乐"),
        ("sound_rect", "音效"),
    ):
        r = as_rect(getattr(mm, name, None))
        if r is not None:
            out.append((r, label))
    return out


def _map_items(app):
    out = []
    # 顶栏 / 侧边 8 个图标按钮
    btns = getattr(getattr(app, "map_buttons", None), "rects", None) or {}
    for name, r in btns.items():
        rr = as_rect(r)
        if rr is not None:
            out.append((rr, name))
    # 关卡任务点（MapPoint.rect 是四元组）
    for p in getattr(app, "map_points", ()) or ():
        rr = as_rect(getattr(p, "rect", None))
        if rr is not None:
            label = "第%d关" % getattr(p, "mission_id", 0)
            if getattr(p, "locked", False):
                label += "(未解锁)"
            out.append((rr, label))
    # 商店 / 返回
    for key, label in (("map_shop", "军火库"), ("map_back", "返回")):
        r = UI.get(key)
        if r:
            out.append((pygame.Rect(r[0], r[1], r[2] - r[0], r[3] - r[1]), label))
    return out


def _shop_items(app):
    # 与 scene_shop._click_fx_hit 同样的六组矩形：页签 / 列表卡片 /
    # 详情按钮 / 机甲槽 / 货币加号 / 顶栏按钮。全是可点元素，没有背景板。
    out = []
    for attr in (
        "shop_tab_rects",
        "shop_rects",
        "shop_btn_rects",
        "shop_slot_rects",
        "money_rects",
    ):
        for r in _collect(getattr(app, attr, None)):
            out.append((r, attr))
    return out


class KeyItemsMixin:
    """把「当前界面有哪些可点矩形」提供给 KeyNav。"""

    @property
    def _key_overlay(self):
        # 顺序必须和 App.click 的判定顺序一致：面板 → 引导 → 弹窗 →
        # 当前场景。不一致的话，引导和弹窗同时在场时焦点框会挂在
        # 「回车点不到」的那一层上。
        for attr in (
            "achievement_panel",
            "slot_panel",
            "result_panel",
            "revive_panel",
            "failed_weapon",
        ):
            obj = getattr(self, attr, None)
            if obj is not None:
                return attr, obj
        if getattr(self, "guide", None) is not None:
            return "guide", self.guide
        if getattr(self, "dialog", None) is not None:
            return "dialog", self.dialog
        return None, None

    def key_signature(self):
        """界面签名：变化时清掉旧焦点。"""
        attr, obj = self._key_overlay
        return (
            self.scene,
            attr,
            type(obj).__name__ if obj is not None else "",
            getattr(self, "shop_tab", ""),
        )

    def key_items(self):
        """当前界面可被方向键选中的矩形清单 [(rect, label)]。"""
        _attr, obj = self._key_overlay
        if obj is not None:
            # 覆盖面板（结算 / 复活 / 成就 / 老虎机 / 引导）与弹窗走同一套：
            # 先问它自己 key_items()，再退到 buttons + 反射。
            return _dialog_items(obj)
        sc = self.scene
        if sc == "menu":
            mm = getattr(self, "main_menu", None)
            return _main_menu_items(mm) if mm is not None else []
        if sc == "map":
            return _map_items(self)
        if sc == "level":
            dlg = getattr(self, "level_dialog", None)
            return _auto_items(dlg) if dlg is not None else []
        if sc == "shop":
            return _shop_items(self)
        # 战斗：方向键 / 空格 是移动与开火，不做焦点导航
        return []
