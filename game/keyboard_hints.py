"""战斗桌面上的可关闭键位提示，与教程共用实体键帽样式。"""

import pygame

from game.dialog_game_intro import draw_keycap
from game.save import key_display_name


def _text(s, text, pos, size=11):
    font = pygame.font.SysFont("Microsoft YaHei", size, bold=True)
    shadow = font.render(text, True, (15, 12, 12))
    image = font.render(text, True, (244, 231, 198))
    s.blit(shadow, (pos[0] + 1, pos[1] + 1))
    s.blit(image, pos)


def _cap(s, x, y, text, width=25, height=23):
    draw_keycap(s, pygame.Rect(x, y, width, height), text, size=10 if len(text) > 2 else 12)


def _key_name(code):
    return key_display_name(pygame.key.name(code))


def draw_battle_key_hints(app, s):
    """槽位数字/字母加底部操作键；设置关闭后整组不绘制。"""
    st = app.save.d.get("settings") or {}
    if not st.get("key_hints", True) or not st.get("keyboard", True):
        return
    # 触屏与键盘提示互斥；这里只控制绘制，不禁用物理键盘输入。
    if not st.get("hide_buttons", True):
        return

    kb = app.keybinds()
    slots = getattr(app, "weapon_slots", None)
    for i, (r, _name) in enumerate(getattr(slots, "rects", [])[:4]):
        label = _key_name(kb["weapon_%d" % (i + 1)])
        _cap(s, r.x + 3, r.y + 3, label, max(23, min(52, len(label) * 8 + 9)), 21)

    bar = getattr(app, "ability_bar", None)
    for i, (r, name) in enumerate(getattr(bar, "rects", [])[:3]):
        label = _key_name(kb["ability_%d" % (i + 1)])
        if "shield" in name or "armor" in name:
            label += "/" + _key_name(kb["armor"])
        _cap(s, r.x + 2, r.y + 2, label, max(23, min(58, len(label) * 8 + 9)), 21)

    # 机甲按钮和武器/道具槽一样，键帽贴在按钮左上角。
    mech = getattr(app, "mech_slot", None)
    if mech is not None and mech.visible():
        r = mech.rect
        label = _key_name(kb["mech"])
        _cap(s, r.x + 2, r.y + 2, label, max(23, min(52, len(label) * 8 + 9)), 21)

    left = _key_name(kb["left"])
    right = _key_name(kb["right"])
    fire = _key_name(kb["fire"])
    cycle = "Shift" if kb["cycle"] in (pygame.K_LSHIFT, pygame.K_RSHIFT) else _key_name(kb["cycle"])
    y = 435
    x = 14
    for label, width in ((left, 25), (right, 25)):
        _cap(s, x, y, label, width)
        x += width + 5
    _text(s, "移动", (x + 2, y + 5))
    x += 42
    cycle_w = max(40, min(64, len(cycle) * 9 + 10))
    _cap(s, x, y, cycle, cycle_w)
    _text(s, "换枪", (x + cycle_w + 6, y + 5))
    x += cycle_w + 47
    _cap(s, x, y, fire, max(52, 12 * len(fire)))
    _text(s, "攻击", (x + max(52, 12 * len(fire)) + 6, y + 5))
