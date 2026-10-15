"""Pointer-safe Win32 parenting for Wallpaper Engine and independent desktop mode."""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
HWND = wintypes.HWND
LPARAM = wintypes.LPARAM
RECT = wintypes.RECT
CALLBACK = ctypes.WINFUNCTYPE(wintypes.BOOL, HWND, LPARAM)
for name, args, result in [
    ("IsWindow", [HWND], wintypes.BOOL),
    ("GetParent", [HWND], HWND),
    ("GetClientRect", [HWND, ctypes.POINTER(RECT)], wintypes.BOOL),
    ("SetParent", [HWND, HWND], HWND),
    ("SetWindowPos", [HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.BOOL),
    ("FindWindowW", [wintypes.LPCWSTR, wintypes.LPCWSTR], HWND),
    ("FindWindowExW", [HWND, HWND, wintypes.LPCWSTR, wintypes.LPCWSTR], HWND),
    ("EnumWindows", [CALLBACK, LPARAM], wintypes.BOOL),
    ("SendMessageTimeoutW", [HWND, wintypes.UINT, wintypes.WPARAM, LPARAM, wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)], LPARAM),
]:
    fn = getattr(user32, name)
    fn.argtypes, fn.restype = args, result
_get = user32.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.GetWindowLongW
_set = user32.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.SetWindowLongW
_get.argtypes, _get.restype = [HWND, ctypes.c_int], ctypes.c_ssize_t
_set.argtypes, _set.restype = [HWND, ctypes.c_int, ctypes.c_ssize_t], ctypes.c_ssize_t


def attach(child: int, parent: int):
    if not user32.IsWindow(parent):
        raise RuntimeError("壁纸宿主窗口已经关闭")
    style = _get(child, -16)
    _set(child, -16, (style & ~0x80CF0000) | 0x40000000)
    ctypes.set_last_error(0)
    old_parent = user32.SetParent(child, parent)
    error = ctypes.get_last_error()
    if not old_parent and error:
        raise ctypes.WinError(error)
    if user32.GetParent(child) != parent:
        raise RuntimeError("无法连接到壁纸宿主窗口")


def client_size(parent: int):
    rect = RECT()
    if not user32.GetClientRect(parent, ctypes.byref(rect)):
        return None
    return rect.right - rect.left, rect.bottom - rect.top


def place(child: int, x: int, y: int, width: int, height: int):
    # SWP_NOACTIVATE | SWP_NOZORDER | SWP_FRAMECHANGED | SWP_SHOWWINDOW
    if width > 0 and height > 0:
        user32.SetWindowPos(child, None, x, y, width, height, 0x74)


def desktop_parent():
    progman = user32.FindWindowW("Progman", None)
    if not progman:
        raise RuntimeError("找不到 Windows 桌面，请先启动资源管理器")
    result = ctypes.c_size_t()
    user32.SendMessageTimeoutW(progman, 0x052C, 0, 0, 2, 1000, ctypes.byref(result))
    candidates = []

    @CALLBACK
    def enum(hwnd, _):
        if user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
            worker = user32.FindWindowExW(None, hwnd, "WorkerW", None)
            if worker:
                candidates.append(worker)
        return True

    user32.EnumWindows(enum, 0)
    if candidates:
        return int(candidates[0])
    # Windows 11 can host WorkerW below Progman rather than as a top-level window.
    worker = user32.FindWindowExW(progman, None, "WorkerW", None)
    if worker:
        return int(worker)
    raise RuntimeError("此 Windows 桌面结构暂不支持独立模式，请使用 Wallpaper Engine 导入 EXE 或 Web 版")
