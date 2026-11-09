"""资源路径解析：assets/images（图）+ assets/raw（数据表/音频）。"""

import contextlib
import os

from engine import fonts as _fonts


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, "assets", "images")
RAW = os.path.join(ROOT, "assets", "raw")


def img_path(name):
    """贴图路径：pic_png/ -> pic/，兼容 / 与 \\ 分隔。"""
    if not name or not isinstance(name, str):
        return ""  # 调用方传 None / tuple 时不要拼出目录本身
    name = name.replace("pic_png/", "pic/").replace("\\", "/")
    return os.path.join(IMG, name.replace("/", os.sep))


def raw_path(name):
    if not name or not isinstance(name, str):
        return ""
    name = name.replace("\\", "/")
    return os.path.join(RAW, name.replace("/", os.sep))


_cache = {}


def _ensure_display():
    """convert_alpha() 需要先有 display surface；无头模式下给一个 1x1 占位。"""
    import pygame

    if not pygame.get_init():
        pygame.init()
    if not pygame.display.get_init():
        pygame.display.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))


_jpeg_ready = False


def _preload_codec_dlls():
    """预加载 pygame 自带的 libjpeg / zlib。

    Windows 上如果 Python 装在带「装入点（mount point）」的盘符里，
    SDL_image 内部按全路径 LoadLibrary 会被系统拒掉，报
    `Failed loading libjpeg-9.dll: ...包含不受信任的装入点`，
    结果所有 .jpg 背景直接崩。先用 ctypes 把 dll 以普通方式载入，
    后续 SDL_image 再取同一个模块就不会走那条受限路径。
    """
    global _jpeg_ready
    if _jpeg_ready:
        return
    _jpeg_ready = True
    if os.name != "nt":
        return
    try:
        import ctypes

        import pygame

        d = os.path.dirname(os.path.abspath(pygame.__file__))
        for n in ("libjpeg-9.dll", "zlib1.dll"):
            p = os.path.join(d, n)
            if os.path.exists(p):
                with contextlib.suppress(OSError):
                    ctypes.WinDLL(p)
    except Exception:
        pass


def load_img(name):
    if not name or not isinstance(name, str):
        return None
    if name in _cache:
        return _cache[name]
    p = img_path(name)
    if not p:
        return None
    import pygame

    im = None
    if os.path.exists(p):
        _preload_codec_dlls()
        _ensure_display()
        im = pygame.image.load(p).convert_alpha()
    _cache[name] = im
    return im


def load_xml(name):
    if not name or not isinstance(name, str):
        return None
    p = raw_path(name)
    if p and os.path.exists(p):
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    # 回退：可能在 images 下（sheets 里的 path 直接是 pic/...）
    return None


def exists_img(name):
    if not name or not isinstance(name, str):
        return False
    return os.path.exists(img_path(name))


def exists_raw(name):
    if not name or not isinstance(name, str):
        return False
    return os.path.exists(raw_path(name))
