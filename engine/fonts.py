"""字体对象与文本渲染缓存。

项目里到处是「在 draw 里现取字体、现 render 文字」的写法。`pygame.font.SysFont`
每次调用都会重新解析字体文件并构造 Font 对象（实测约 0.45 ms），商店一帧要取
4 个字体、渲染 5 段文字，合起来占掉该场景约 40% 的帧时间。

这里做两件事：

1. `SysFont` 换成带记忆的版本（同一个 name/size/bold/italic 只构造一次）；
2. 返回的字体是 `_TextFont`，它的 `render()` 按「文字 + 抗锯齿 + 颜色 + 背景」
   记忆渲染结果，重复绘制同一段文字不再走字形栅格化。

注意：`render()` 返回的是**缓存对象**，调用方不得就地修改它（`set_alpha` /
`fill` 之类要先 `.copy()`），否则会污染后续所有同文案的绘制。

挂载方式是在本模块 import 时替换 `pygame.font.SysFont`，所以引擎侧
（`engine/scene.py`、`engine/res.py`）都会先 import 本模块，业务代码无需改动。
"""

import pygame


_REAL_SYSFONT = pygame.font.SysFont


class _TextFont(pygame.font.Font):
    """带文本渲染缓存的字体对象。"""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._tex = {}
        self._limit = 256

    def render(self, text, antialias=True, color=(0, 0, 0), background=None):
        key = (text, antialias, color if isinstance(color, tuple) else tuple(color), background)
        hit = self._tex.get(key)
        if hit is not None:
            return hit
        surf = pygame.font.Font.render(self, text, antialias, color, background)
        if len(self._tex) >= self._limit:
            self._tex.clear()
        self._tex[key] = surf
        return surf


_fonts = {}


def _ctor(fontpath, size, bold, italic):
    try:
        return _TextFont(fontpath, size, bold, italic)
    except TypeError:  # 老版本 pygame 的 Font 只吃 (file, size)
        return _TextFont(fontpath, size)


def sysfont(name, size, bold=False, italic=False, **_kw):
    """`pygame.font.SysFont` 的记忆版。"""
    key = (name, size, bold, italic)
    f = _fonts.get(key)
    if f is None:
        try:
            f = _REAL_SYSFONT(name, size, bold, italic, constructor=_ctor)
        except TypeError:
            f = _REAL_SYSFONT(name, size, bold, italic)
        _fonts[key] = f
    return f


def clear():
    """清空字体缓存（测试用；正常游戏不需要）。"""
    _fonts.clear()


pygame.font.SysFont = sysfont
