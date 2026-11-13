"""Window thumbnails for the picker (no Qt): raw BGRA pixels via PrintWindow.

PW_RENDERFULLCONTENT asks DWM for the composed surface, so GPU-rendered apps
(Chrome, Electron) work and covered windows still render. Minimized windows
have no surface and return None.
"""

import ctypes
from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

PW_CLIENTONLY = 0x1
PW_RENDERFULLCONTENT = 0x2

_user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
_user32.GetDC.restype = wintypes.HDC
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_user32.IsHungAppWindow.argtypes = [wintypes.HWND]
_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p,
                                    wintypes.UINT,
                                    ctypes.POINTER(ctypes.c_void_p),
                                    wintypes.HANDLE, wintypes.DWORD]
_gdi32.CreateDIBSection.restype = wintypes.HBITMAP
_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi32.SelectObject.restype = wintypes.HGDIOBJ
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.DeleteDC.argtypes = [wintypes.HDC]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


def capture(hwnd, max_pixels=1920 * 1200):
    """Return (width, height, bgra_bytes) of the window's client area.

    None when the window is minimized, hung, empty, or rendering failed.
    """
    hwnd = wintypes.HWND(hwnd)
    if _user32.IsIconic(hwnd) or _user32.IsHungAppWindow(hwnd):
        return None
    rect = wintypes.RECT()
    if not _user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w < 16 or h < 16 or w * h > max_pixels * 4:
        return None

    screen_dc = _user32.GetDC(None)
    mem_dc = _gdi32.CreateCompatibleDC(screen_dc)
    bmi = _BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.biWidth, bmi.biHeight = w, -h          # top-down rows
    bmi.biPlanes, bmi.biBitCount = 1, 32
    bits = ctypes.c_void_p()
    bmp = _gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), 0,
                                  ctypes.byref(bits), None, 0)
    try:
        if not bmp or not bits:
            return None
        old = _gdi32.SelectObject(mem_dc, bmp)
        ok = _user32.PrintWindow(hwnd, mem_dc,
                                 PW_CLIENTONLY | PW_RENDERFULLCONTENT)
        _gdi32.SelectObject(mem_dc, old)
        if not ok:
            return None
        data = ctypes.string_at(bits, w * h * 4)
        # an all-black surface means the app gave us nothing to show
        if not any(data[i] for i in range(0, len(data), 4 * 997)):
            return None
        return w, h, data
    finally:
        if bmp:
            _gdi32.DeleteObject(bmp)
        _gdi32.DeleteDC(mem_dc)
        _user32.ReleaseDC(None, screen_dc)


_user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
_user32.GetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetClassLongPtrW.restype = ctypes.c_size_t


def icon_handle(hwnd):
    """The window's own HICON (what the taskbar shows), or 0.

    Works for Store apps where the exe path gives no icon. The handle belongs
    to the window, never destroy it.
    """
    hwnd = wintypes.HWND(hwnd)
    out = ctypes.c_size_t(0)
    for kind in (1, 2, 0):          # ICON_BIG, ICON_SMALL2, ICON_SMALL
        if _user32.SendMessageTimeoutW(hwnd, 0x007F, kind, 0, 0x0002, 100,
                                       ctypes.byref(out)) and out.value:
            return out.value
    for index in (-14, -34):        # GCLP_HICON, GCLP_HICONSM
        h = _user32.GetClassLongPtrW(hwnd, index)
        if h:
            return h
    return 0
