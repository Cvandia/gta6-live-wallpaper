"""Exercise the real wallpaper process inside a native Qt parent window.

Run on Windows with the same virtual environment as the application::

    work\\.venv\\Scripts\\python.exe work\\tests\\test_embedding.py

Test a packaged one-file application, optionally using a monitor viewport::

    work\\.venv\\Scripts\\python.exe work\\tests\\test_embedding.py --exe outputs\\GTA6-LiveWallpaper\\GTA6Wallpaper.exe
    work\\.venv\\Scripts\\python.exe work\\tests\\test_embedding.py --exe outputs\\GTA6-LiveWallpaper\\GTA6Wallpaper.exe --viewport

This is an integration harness, not a mock of the embedding implementation. It
checks the actual HWND relationship, native window styles, initial client area,
resizing, and shutdown when the host window disappears. Diagnostic JSON and the
child's stdout/stderr are saved beside this file. It does not change main.py.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time


TITLE = "GTA VI · 北京时间倒计时"
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
GWL_STYLE = -16


class HarnessFailure(AssertionError):
    """An observable embedding contract did not hold."""


class NativeWindows:
    """Pointer-safe Win32 bindings for both 32-bit and 64-bit Python."""

    def __init__(self) -> None:
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # Windows LONG is 32 bits even in a 64-bit process. LPARAM and LONG_PTR
        # follow the process pointer size, so do not bind them as c_long.
        self.LONG_PTR = ctypes.c_ssize_t
        self.enum_callback = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, self.LONG_PTR
        )
        self.user32.EnumWindows.argtypes = [self.enum_callback, self.LONG_PTR]
        self.user32.EnumWindows.restype = wintypes.BOOL
        self.user32.EnumChildWindows.argtypes = [
            wintypes.HWND, self.enum_callback, self.LONG_PTR
        ]
        self.user32.EnumChildWindows.restype = wintypes.BOOL
        self.user32.GetParent.argtypes = [wintypes.HWND]
        self.user32.GetParent.restype = wintypes.HWND
        self.user32.GetClientRect.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.RECT)
        ]
        self.user32.GetClientRect.restype = wintypes.BOOL
        self.user32.GetWindowRect.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.RECT)
        ]
        self.user32.GetWindowRect.restype = wintypes.BOOL
        self.user32.ScreenToClient.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.POINT)
        ]
        self.user32.ScreenToClient.restype = wintypes.BOOL
        self.user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self.user32.GetWindowTextLengthW.restype = ctypes.c_int
        self.user32.GetWindowTextW.argtypes = [
            wintypes.HWND, wintypes.LPWSTR, ctypes.c_int
        ]
        self.user32.GetWindowTextW.restype = ctypes.c_int
        self.user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
        ]
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user32.IsWindow.argtypes = [wintypes.HWND]
        self.user32.IsWindow.restype = wintypes.BOOL
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            self.get_window_long = self.user32.GetWindowLongPtrW
            self.get_window_long.restype = self.LONG_PTR
        else:
            self.get_window_long = self.user32.GetWindowLongW
            self.get_window_long.restype = wintypes.LONG
        self.get_window_long.argtypes = [wintypes.HWND, ctypes.c_int]
        self.kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        self.kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL

        class ProcessEntry(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        self.process_entry_type = ProcessEntry
        for name in ("Process32FirstW", "Process32NextW"):
            fn = getattr(self.kernel32, name)
            fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
            fn.restype = wintypes.BOOL

    @staticmethod
    def _check(ok: int, operation: str) -> None:
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error(), operation)

    def title(self, hwnd: int) -> str:
        length = self.user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value

    def process_id(self, hwnd: int) -> int:
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def parent(self, hwnd: int) -> int:
        return int(self.user32.GetParent(hwnd) or 0)

    def style(self, hwnd: int) -> int:
        return int(self.get_window_long(hwnd, GWL_STYLE)) & 0xFFFFFFFF

    def client_size(self, hwnd: int) -> tuple[int, int]:
        rect = wintypes.RECT()
        self._check(self.user32.GetClientRect(hwnd, ctypes.byref(rect)), "GetClientRect")
        return rect.right - rect.left, rect.bottom - rect.top

    def rectangle_in_parent(self, child: int, parent: int) -> tuple[int, int, int, int]:
        rect = wintypes.RECT()
        self._check(self.user32.GetWindowRect(child, ctypes.byref(rect)), "GetWindowRect")
        origin = wintypes.POINT(rect.left, rect.top)
        self._check(self.user32.ScreenToClient(parent, ctypes.byref(origin)), "ScreenToClient")
        return origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top

    def windows_for_process(self, pid: int, parent: int) -> list[dict]:
        process_ids = self.process_tree(pid)
        # Search both scopes: a broken embed may leave the app as a top-level
        # window, while EnumWindows alone cannot find a correctly embedded app.
        handles: set[int] = set()

        @self.enum_callback
        def collect(hwnd, _lparam):
            handle = int(hwnd)
            if self.process_id(handle) in process_ids:
                handles.add(handle)
            return True

        self.user32.EnumWindows(collect, 0)
        if self.user32.IsWindow(parent):
            self.user32.EnumChildWindows(parent, collect, 0)
        return [
            {
                "hwnd": hwnd,
                "pid": self.process_id(hwnd),
                "title": self.title(hwnd),
                "parent": self.parent(hwnd),
                "style": f"0x{self.style(hwnd):08X}",
            }
            for hwnd in sorted(handles)
        ]

    def process_tree(self, root_pid: int) -> set[int]:
        # A Windows virtual-environment python.exe can be a redirector that
        # starts the real interpreter as a child. Include those descendants.
        snapshot = self.kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        parents: dict[int, int] = {}
        try:
            entry = self.process_entry_type()
            entry.dwSize = ctypes.sizeof(entry)
            has_entry = self.kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while has_entry:
                parents[entry.th32ProcessID] = entry.th32ParentProcessID
                has_entry = self.kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            self.kernel32.CloseHandle(snapshot)
        result = {root_pid}
        while True:
            additions = {pid for pid, parent in parents.items() if parent in result} - result
            if not additions:
                return result
            result.update(additions)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target_group = parser.add_mutually_exclusive_group()
    target_group.add_argument("--main", type=Path, help="Application entry point; defaults to work/src/main.py")
    target_group.add_argument("--exe", type=Path, help="Packaged one-file EXE; verify its runtime child process owns the window")
    parser.add_argument("--python", default=sys.executable, help="Python executable for the child")
    parser.add_argument("--timeout", type=float, default=25.0, help="Startup timeout in seconds")
    parser.add_argument("--viewport", action="store_true", help="Keep explicit native viewport x=80, y=40, width=800, height=450 after host resize")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("This integration test requires Windows and a graphical desktop.")

    from PySide6.QtCore import QCoreApplication, QEvent, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    output_dir = Path(__file__).resolve().parent
    work_dir = output_dir.parent
    entry = (args.exe or args.main or work_dir / "src" / "main.py").resolve()
    if not entry.is_file():
        parser.error(f"Application entry point does not exist: {entry}")
    config_dir = (work_dir / "test-config").resolve()
    native = NativeWindows()
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setQuitOnLastWindowClosed(False)
    parent = QWidget()
    parent.setWindowTitle(f"GTA VI embedding test host · {os.getpid()}")
    parent.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    parent.resize(960, 540)
    parent.show()
    parent_hwnd = int(parent.winId())
    process: subprocess.Popen | None = None
    child_hwnd = 0
    result = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "entry_point": str(entry),
        "python": None if args.exe else str(args.python),
        "target_type": "onefile_exe" if args.exe else "python_source",
        "layout_mode": "explicit_viewport" if args.viewport else "fill_host",
        "parent_hwnd": parent_hwnd,
        "checks": [],
        "passed": False,
    }

    def pump() -> None:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        time.sleep(0.02)

    def wait_for(predicate, timeout: float, failure: str) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pump()
            if predicate():
                return
        raise HarnessFailure(failure)

    def record(name: str, **details) -> None:
        result["checks"].append({"name": name, "passed": True, **details})
        print(f"PASS: {name}", flush=True)

    def require(condition: bool, message: str) -> None:
        if not condition:
            raise HarnessFailure(message)

    def expected_region() -> tuple[int, int, int, int]:
        if args.viewport:
            return 80, 40, 800, 450
        width, height = native.client_size(parent_hwnd)
        return 0, 0, width, height

    def matches_expected_region() -> bool:
        if not child_hwnd or not native.user32.IsWindow(child_hwnd):
            return False
        rect = native.rectangle_in_parent(child_hwnd, parent_hwnd)
        return all(abs(actual - expected) <= 2 for actual, expected in zip(rect, expected_region()))

    output_prefix = "embedding" + ("-exe" if args.exe else "") + ("-viewport" if args.viewport else "")
    stdout_path = output_dir / f"{output_prefix}-child.stdout.txt"
    stderr_path = output_dir / f"{output_prefix}-child.stderr.txt"
    try:
        for _ in range(5):
            pump()
        initial_width, initial_height = native.client_size(parent_hwnd)
        x, y, width, height = expected_region()
        if args.viewport:
            require(initial_width > x + width and initial_height > y + height, "Host must be larger than the explicit viewport.")
        command = ([str(entry)] if args.exe else [str(args.python), str(entry)]) + [
            "-parentHWND", str(parent_hwnd),
            "-wpe_x", str(x), "-wpe_y", str(y),
            "-wpe_w", str(width), "-wpe_h", str(height),
            "--config-dir", str(config_dir),
        ]
        result["command"] = command
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            process = subprocess.Popen(
                command,
                cwd=str(work_dir.parent),
                stdout=stdout,
                stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            result["child_pid"] = process.pid

            def find_child() -> bool:
                nonlocal child_hwnd
                if process.poll() is not None:
                    raise HarnessFailure(f"Child exited before embedding; return code {process.returncode}. See {stderr_path.name}.")
                windows = native.windows_for_process(process.pid, parent_hwnd)
                result["last_observed_windows"] = windows
                matches = [window for window in windows if window["title"] == TITLE]
                if matches:
                    child_hwnd = matches[0]["hwnd"]
                    return True
                return False

            wait_for(find_child, args.timeout, f"No native child with exact title {TITLE!r} appeared.")
            result["child_hwnd"] = child_hwnd
            record("native application window discovered", hwnd=child_hwnd, title=TITLE)
            if args.exe:
                window_pid = native.process_id(child_hwnd)
                process_tree = native.process_tree(process.pid)
                require(window_pid in process_tree and window_pid != process.pid,
                        f"Expected one-file bootloader child to own HWND; launcher PID={process.pid}, window PID={window_pid}, process tree={sorted(process_tree)}.")
                record("one-file runtime child owns HWND", launcher_pid=process.pid, runtime_pid=window_pid, process_tree=sorted(process_tree))
            # Qt may finish its own window setup after showing the window. Allow
            # this short grace period, then verify the actual parent explicitly.
            wait_for(lambda: native.parent(child_hwnd) == parent_hwnd, 8.0, "GetParent(child) does not equal the supplied -parentHWND.")
            record("GetParent matches supplied host", parent=native.parent(child_hwnd))
            style = native.style(child_hwnd)
            require(bool(style & WS_CHILD), f"WS_CHILD missing; style=0x{style:08X}")
            require(not bool(style & WS_POPUP), f"WS_POPUP remains set; style=0x{style:08X}")
            record("native child styles", style=f"0x{style:08X}")
            wait_for(matches_expected_region, 8.0, "Initial native child bounds do not match the requested region.")
            record("initial bounds match explicit viewport" if args.viewport else "initial bounds fill host", host_client=list(native.client_size(parent_hwnd)), child_bounds=list(native.rectangle_in_parent(child_hwnd, parent_hwnd)), expected_bounds=list(expected_region()))

            parent.resize(1180, 664)
            wait_for(lambda: native.client_size(parent_hwnd) != (initial_width, initial_height), 5.0, "Host window did not resize.")
            wait_for(matches_expected_region, 10.0, "Child bounds after host resize do not match the requested region.")
            record("child preserves viewport after host resize" if args.viewport else "child follows host resize", host_client=list(native.client_size(parent_hwnd)), child_bounds=list(native.rectangle_in_parent(child_hwnd, parent_hwnd)), expected_bounds=list(expected_region()))
            result["last_observed_windows"] = native.windows_for_process(process.pid, parent_hwnd)

            parent.close()
            wait_for(lambda: not native.user32.IsWindow(parent_hwnd), 5.0, "Host HWND was not destroyed on close.")
            record("host window destroyed")
            wait_for(lambda: process.poll() is not None, 10.0, "Child process remained alive after its parent HWND was destroyed.")
            require(process.returncode == 0, f"Child exited with error code {process.returncode} after host destruction.")
            record("child exits cleanly after host destruction", return_code=process.returncode)
            result["passed"] = True
    except Exception as exc:
        result["failure"] = f"{type(exc).__name__}: {exc}"
        if process and process.poll() is None and native.user32.IsWindow(parent_hwnd):
            result["last_observed_windows"] = native.windows_for_process(process.pid, parent_hwnd)
            if child_hwnd and native.user32.IsWindow(child_hwnd):
                result["last_child_bounds"] = list(native.rectangle_in_parent(child_hwnd, parent_hwnd))
                result["last_host_client"] = list(native.client_size(parent_hwnd))
        print(f"FAIL: {result['failure']}", file=sys.stderr, flush=True)
    finally:
        # Give a correctly attached app a chance to exit even after an assertion
        # failed. The host HWND belongs to this test and may be safely destroyed.
        if native.user32.IsWindow(parent_hwnd):
            parent.close()
            for _ in range(10):
                pump()
        # Windows venv launchers may own a real-interpreter child, so a failed
        # test must clean up that process tree too, not just the redirector.
        # /PID is the exact Popen created above; no global process-name kill.
        if process is not None and process.poll() is None:
            deadline = time.monotonic() + 2
            while process.poll() is None and time.monotonic() < deadline:
                pump()
        if process is not None and process.poll() is None:
            subprocess.run(
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW, check=False,
            )
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        result["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        result["stdout_path"] = str(stdout_path)
        result["stderr_path"] = str(stderr_path)
        result_path = output_dir / f"{output_prefix}-result.json"
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Diagnostics: {result_path}", flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
