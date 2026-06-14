from __future__ import annotations

import ctypes
from pathlib import Path

from litlaunch.browsers import BrowserKind
from litlaunch.platforms import PlatformDetector
from litlaunch.windowing import (
    NoopWindowMonitor,
    WindowInfo,
    WindowMonitorConfig,
    WindowMonitorStatus,
    WindowsChromiumWindowMonitor,
    WindowsWindowProvider,
    WindowTarget,
    apply_windows_window_app_identity,
    apply_windows_window_icon,
    create_window_monitor,
    is_chromium_window,
)


class FakeUser32:
    def __init__(self, windows):
        self.windows = windows

    def EnumWindows(self, callback, lparam):
        for hwnd in self.windows:
            callback(hwnd, lparam)
        return 1

    def IsWindowVisible(self, hwnd):
        return bool(self.windows[hwnd]["visible"])

    def GetWindowTextLengthW(self, hwnd):
        return len(self.windows[hwnd]["title"])

    def GetWindowTextW(self, hwnd, buffer, size):
        buffer.value = self.windows[hwnd]["title"][: size - 1]
        return len(buffer.value)

    def GetClassNameW(self, hwnd, buffer, size):
        buffer.value = self.windows[hwnd]["class_name"][: size - 1]
        return len(buffer.value)

    def GetWindowThreadProcessId(self, hwnd, pid_ref):
        pid_ref._obj.value = self.windows[hwnd]["pid"]
        return 1


class FakeKernel32:
    def __init__(self, path_by_pid=None):
        self.path_by_pid = path_by_pid or {}
        self.closed_handles = []

    def OpenProcess(self, access, inherit_handle, pid):
        return pid if pid in self.path_by_pid else 0

    def QueryFullProcessImageNameW(self, handle, flags, buffer, size_ref):
        path = self.path_by_pid.get(handle)
        if path is None:
            return 0
        buffer.value = path
        size_ref._obj.value = len(path)
        return 1

    def CloseHandle(self, handle):
        self.closed_handles.append(handle)
        return 1


class FakeIconUser32:
    def __init__(self):
        self.loaded = []
        self.messages = []

    def LoadImageW(self, instance, path, image_type, width, height, flags):
        self.loaded.append((path, image_type, width, height, flags))
        return width + height

    def SendMessageW(self, hwnd, message, icon_type, icon):
        self.messages.append((hwnd, message, icon_type, icon))
        return 1


def fake_windows():
    return {
        100: {
            "visible": True,
            "title": "LitLaunch Example App",
            "class_name": "Chrome_WidgetWin_1",
            "pid": 400,
        },
        200: {
            "visible": False,
            "title": "Hidden App",
            "class_name": "Chrome_WidgetWin_1",
            "pid": 500,
        },
        300: {
            "visible": True,
            "title": "Plain Utility",
            "class_name": "Notepad",
            "pid": 600,
        },
    }


def windows_info():
    return PlatformDetector(
        system_func=lambda: "Windows",
        machine_func=lambda: "AMD64",
    ).detect()


def linux_info():
    return PlatformDetector(
        system_func=lambda: "Linux",
        machine_func=lambda: "x86_64",
    ).detect()


def test_windows_provider_import_safe_when_not_windows():
    provider = WindowsWindowProvider(is_windows=False)

    assert provider.capture(WindowTarget("LitLaunch")) == ()


def test_windows_provider_collects_visible_window_metadata():
    user32 = FakeUser32(fake_windows())
    kernel32 = FakeKernel32({400: r"C:\Program Files\Edge\Application\msedge.exe"})
    provider = WindowsWindowProvider(
        user32=user32,
        kernel32=kernel32,
        is_windows=True,
    )

    windows = provider.capture(WindowTarget("LitLaunch"))

    assert windows == (
        WindowInfo(
            handle="100",
            title="LitLaunch Example App",
            class_name="Chrome_WidgetWin_1",
            pid=400,
            process_name="msedge",
        ),
        WindowInfo(
            handle="300",
            title="Plain Utility",
            class_name="Notepad",
            pid=600,
            process_name=None,
        ),
    )
    assert kernel32.closed_handles == [400]


def test_windows_provider_missing_process_name_does_not_crash():
    provider = WindowsWindowProvider(
        user32=FakeUser32(fake_windows()),
        kernel32=FakeKernel32(),
        is_windows=True,
    )

    windows = provider.capture(WindowTarget("LitLaunch"))

    assert windows[0].process_name is None


def test_chromium_window_matching_uses_class_and_process_name():
    assert is_chromium_window(WindowInfo("1", class_name="Chrome_WidgetWin_1"))
    assert is_chromium_window(WindowInfo("2", process_name="msedge.exe"))
    assert is_chromium_window(
        WindowInfo("3", process_name="chrome"),
        BrowserKind.CHROME,
    )
    assert not is_chromium_window(
        WindowInfo("4", process_name="msedge"),
        BrowserKind.CHROME,
    )
    assert not is_chromium_window(WindowInfo("5", class_name="Notepad"))


def test_windows_chromium_monitor_filters_to_chromium_windows():
    provider = WindowsWindowProvider(
        user32=FakeUser32(fake_windows()),
        kernel32=FakeKernel32(),
        is_windows=True,
    )
    monitor = WindowsChromiumWindowMonitor(provider)

    windows = monitor.capture(WindowTarget("LitLaunch"))

    assert windows == (
        WindowInfo(
            handle="100",
            title="LitLaunch Example App",
            class_name="Chrome_WidgetWin_1",
            pid=400,
            process_name=None,
        ),
    )


def test_windows_chromium_monitor_uses_existing_polling_close_behavior():
    captures = iter(
        [
            (WindowInfo("1", "LitLaunch App", "Chrome_WidgetWin_1"),),
            (),
        ]
    )

    class Provider:
        def capture(self, target):
            return next(captures)

    monitor = WindowsChromiumWindowMonitor(
        Provider(),
        sleeper=lambda seconds: None,
    )

    result = monitor.wait_for_close(
        WindowTarget("LitLaunch"),
        backend_is_running=lambda: True,
        config=WindowMonitorConfig(stable_poll_count=1),
    )

    assert result.status == WindowMonitorStatus.WINDOW_CLOSED
    assert result.closed is True


def test_create_window_monitor_returns_windows_monitor_for_windows():
    monitor = create_window_monitor(
        windows_info(),
        provider=WindowsWindowProvider(is_windows=False),
    )

    assert isinstance(monitor, WindowsChromiumWindowMonitor)


def test_create_window_monitor_returns_noop_for_non_windows():
    monitor = create_window_monitor(linux_info())

    assert isinstance(monitor, NoopWindowMonitor)


def test_windows_api_choices_are_windows_10_compatible_and_observational():
    doc = WindowsWindowProvider.__doc__ or ""

    assert "Windows 10" in doc
    assert "EnumWindows" in doc
    assert "IsWindowVisible" in doc
    assert "GetWindowTextW" in doc
    assert "GetClassNameW" in doc
    assert "GetWindowThreadProcessId" in doc
    assert "QueryFullProcessImageNameW" in doc
    assert "never controls" in doc


def test_windows_monitor_has_no_browser_or_window_control_surface():
    provider = WindowsWindowProvider(is_windows=False)
    monitor = WindowsChromiumWindowMonitor(provider)

    for instance in (provider, monitor):
        assert not hasattr(instance, "kill_browser")
        assert not hasattr(instance, "stop_browser")
        assert not hasattr(instance, "terminate_browser")
        assert not hasattr(instance, "close_window")
        assert not hasattr(instance, "send_close")


def test_windows_provider_fake_path_does_not_require_real_winfuntype(monkeypatch):
    monkeypatch.delattr(ctypes, "WinDLL", raising=False)
    monkeypatch.delattr(ctypes, "WINFUNCTYPE", raising=False)

    provider = WindowsWindowProvider(
        user32=FakeUser32(fake_windows()),
        is_windows=True,
        process_name_provider=lambda pid: "msedge",
    )

    assert provider.capture(WindowTarget("LitLaunch"))[0].process_name == "msedge"


def test_apply_windows_window_icon_uses_win32_messages(tmp_path):
    icon = tmp_path / "app.ico"
    icon.write_bytes(b"icon")
    user32 = FakeIconUser32()

    assert apply_windows_window_icon("100", icon, user32=user32, is_windows=True)

    assert len(user32.loaded) == 2
    assert [message[2] for message in user32.messages] == [0, 1]


def test_apply_windows_window_icon_rejects_non_ico(tmp_path):
    icon = tmp_path / "app.svg"
    icon.write_text("<svg />", encoding="utf-8")

    assert not apply_windows_window_icon(
        "100",
        icon,
        user32=FakeIconUser32(),
        is_windows=True,
    )


def test_apply_windows_window_app_identity_invokes_shell_property_script(tmp_path):
    icon = tmp_path / "app.ico"
    icon.write_bytes(b"icon")
    calls = []

    def runner(command, **kwargs):
        script = Path(command[5]).read_text(encoding="utf-8")
        calls.append((command, kwargs, script))

    assert apply_windows_window_app_identity(
        "100",
        "LatticeFoundry.LitLaunch.App.123",
        icon_path=icon,
        is_windows=True,
        runner=runner,
    )

    command, kwargs, script = calls[0]
    assert command[:5] == (
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
    )
    assert command[-3:] == (
        "100",
        "LatticeFoundry.LitLaunch.App.123",
        str(icon),
    )
    assert kwargs == {"check": True, "capture_output": True, "text": True}
    assert "SHGetPropertyStoreForWindow" in script


def test_apply_windows_window_app_identity_rejects_invalid_handle():
    assert not apply_windows_window_app_identity(
        "not-a-handle",
        "LatticeFoundry.LitLaunch.App.123",
        is_windows=True,
    )
