from pathlib import Path

import pytest

from litlaunch._browser_authority import (
    BrowserLaunchStrategy,
    WindowsProcessRecord,
    create_browser_launch_authority,
)
from litlaunch._windows_shell import WindowsShellProcess
from litlaunch.browser_profiles import create_managed_browser_profile
from litlaunch.browsers import (
    BrowserCapability,
    BrowserKind,
    BrowserLauncher,
    BrowserRegistry,
    BrowserResolution,
    ChromeAdapter,
    DefaultBrowserAdapter,
    EdgeAdapter,
)
from litlaunch.config import BrowserChoice, LaunchMode


def capability(kind, executable_path):
    return BrowserCapability(
        kind=kind,
        name=kind.value.title(),
        executable_path=executable_path,
        available=True,
        supports_app_mode=kind != BrowserKind.DEFAULT,
        supports_full_browser=True,
    )


def resolution(selected):
    return BrowserResolution(
        requested=BrowserChoice.AUTO,
        selected=selected,
        fallback_chain=(selected,) if selected else (),
        message="resolved" if selected else "none",
    )


def resolution_with_chain(selected, *fallbacks, requested=BrowserChoice.AUTO):
    return BrowserResolution(
        requested=requested,
        selected=selected,
        fallback_chain=(selected, *fallbacks) if selected else tuple(fallbacks),
        message="resolved" if selected else "none",
    )


def test_edge_app_mode_launch_uses_adapter_command_without_shell_true():
    calls = []
    launcher = BrowserLauncher(
        registry=BrowserRegistry((EdgeAdapter(),)),
        popen_factory=lambda command, **kwargs: calls.append((command, kwargs)),
    )

    result = launcher.launch(
        resolution(capability(BrowserKind.EDGE, "C:/Edge/msedge.exe")),
        url="http://127.0.0.1:8501",
        mode=LaunchMode.WEBAPP,
        title="Example",
        extra_args=("--new-window",),
    )

    assert result.ok is True
    assert result.command == (
        "C:/Edge/msedge.exe",
        "--app=http://127.0.0.1:8501",
        "--new-window",
    )
    assert calls == [(result.command, {"shell": False})]


def test_chrome_app_mode_launch_uses_adapter_command():
    calls = []
    launcher = BrowserLauncher(
        registry=BrowserRegistry((ChromeAdapter(),)),
        popen_factory=lambda command, **kwargs: calls.append((command, kwargs)),
    )

    result = launcher.launch(
        resolution(capability(BrowserKind.CHROME, "/usr/bin/chrome")),
        url="http://127.0.0.1:8501",
        mode=LaunchMode.WEBAPP,
    )

    assert result.ok is True
    assert result.command == ("/usr/bin/chrome", "--app=http://127.0.0.1:8501")
    assert calls == [(result.command, {"shell": False})]


def test_default_browser_launch_uses_opener():
    opened = []
    launcher = BrowserLauncher(
        registry=BrowserRegistry((DefaultBrowserAdapter(),)),
        browser_open=lambda url: opened.append(url) or True,
    )

    result = launcher.launch(
        resolution(capability(BrowserKind.DEFAULT, None)),
        url="http://127.0.0.1:8501",
        mode=LaunchMode.BROWSER,
    )

    assert result.ok is True
    assert result.command is None
    assert opened == ["http://127.0.0.1:8501"]


def test_launch_returns_failure_when_no_browser_selected():
    launcher = BrowserLauncher()

    result = launcher.launch(
        resolution(None),
        url="http://127.0.0.1:8501",
        mode=LaunchMode.WEBAPP,
    )

    assert result.ok is False
    assert result.browser is None
    assert result.command is None


def test_launch_returns_failure_when_popen_raises():
    launcher = BrowserLauncher(
        registry=BrowserRegistry((EdgeAdapter(),)),
        popen_factory=lambda command, **kwargs: (_ for _ in ()).throw(
            RuntimeError("boom")
        ),
    )

    result = launcher.launch(
        resolution(capability(BrowserKind.EDGE, "C:/Edge/msedge.exe")),
        url="http://127.0.0.1:8501",
        mode=LaunchMode.WEBAPP,
    )

    assert result.ok is False
    assert result.command == ("C:/Edge/msedge.exe", "--app=http://127.0.0.1:8501")
    assert "boom" in result.message


def test_app_mode_launch_falls_back_to_next_chromium_candidate():
    calls = []

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        if command[0] == "C:/Edge/msedge.exe":
            raise RuntimeError("edge blocked")

    launcher = BrowserLauncher(
        registry=BrowserRegistry((EdgeAdapter(), ChromeAdapter())),
        popen_factory=popen,
    )

    result = launcher.launch(
        resolution_with_chain(
            capability(BrowserKind.EDGE, "C:/Edge/msedge.exe"),
            capability(BrowserKind.CHROME, "C:/Chrome/chrome.exe"),
        ),
        url="http://127.0.0.1:8501",
        mode=LaunchMode.WEBAPP,
    )

    assert result.ok is True
    assert result.browser is not None
    assert result.browser.kind == BrowserKind.CHROME
    assert result.command == ("C:/Chrome/chrome.exe", "--app=http://127.0.0.1:8501")
    assert "Edge launch failed; fell back to Chrome" in result.message
    assert calls == [
        (("C:/Edge/msedge.exe", "--app=http://127.0.0.1:8501"), {"shell": False}),
        (("C:/Chrome/chrome.exe", "--app=http://127.0.0.1:8501"), {"shell": False}),
    ]


def test_app_mode_launch_does_not_fall_back_to_default_browser():
    calls = []
    launcher = BrowserLauncher(
        registry=BrowserRegistry((EdgeAdapter(), DefaultBrowserAdapter())),
        popen_factory=lambda command, **kwargs: (
            calls.append((command, kwargs))
            or (_ for _ in ()).throw(RuntimeError("edge blocked"))
        ),
        browser_open=lambda url: (_ for _ in ()).throw(
            AssertionError("default browser should not open for app-mode fallback")
        ),
    )

    result = launcher.launch(
        resolution_with_chain(
            capability(BrowserKind.EDGE, "C:/Edge/msedge.exe"),
            capability(BrowserKind.DEFAULT, None),
        ),
        url="http://127.0.0.1:8501",
        mode=LaunchMode.WEBAPP,
    )

    assert result.ok is False
    assert result.browser is not None
    assert result.browser.kind == BrowserKind.EDGE
    assert "No fallback browser launch succeeded." in result.message
    assert len(calls) == 1


def test_launch_respects_strict_no_fallback_behavior():
    calls = []
    launcher = BrowserLauncher(
        registry=BrowserRegistry((EdgeAdapter(), ChromeAdapter())),
        popen_factory=lambda command, **kwargs: (
            calls.append((command, kwargs))
            or (_ for _ in ()).throw(RuntimeError("edge blocked"))
        ),
    )

    result = launcher.launch(
        resolution_with_chain(
            capability(BrowserKind.EDGE, "C:/Edge/msedge.exe"),
            capability(BrowserKind.CHROME, "C:/Chrome/chrome.exe"),
            requested=BrowserChoice.EDGE,
        ),
        url="http://127.0.0.1:8501",
        mode=LaunchMode.WEBAPP,
        allow_fallback=False,
    )

    assert result.ok is False
    assert result.browser is not None
    assert result.browser.kind == BrowserKind.EDGE
    assert "Fallback was disabled." in result.message
    assert calls == [
        (("C:/Edge/msedge.exe", "--app=http://127.0.0.1:8501"), {"shell": False}),
    ]


def test_browser_mode_launch_can_fallback_to_default_browser():
    opened = []
    calls = []
    launcher = BrowserLauncher(
        registry=BrowserRegistry((ChromeAdapter(), DefaultBrowserAdapter())),
        popen_factory=lambda command, **kwargs: (
            calls.append((command, kwargs))
            or (_ for _ in ()).throw(RuntimeError("chrome blocked"))
        ),
        browser_open=lambda url: opened.append(url) or True,
    )

    result = launcher.launch(
        resolution_with_chain(
            capability(BrowserKind.CHROME, "/usr/bin/chrome"),
            capability(BrowserKind.DEFAULT, None),
        ),
        url="http://127.0.0.1:8501",
        mode=LaunchMode.BROWSER,
    )

    assert result.ok is True
    assert result.browser is not None
    assert result.browser.kind == BrowserKind.DEFAULT
    assert result.command is None
    assert "Chrome launch failed; fell back to Default" in result.message
    assert opened == ["http://127.0.0.1:8501"]
    assert len(calls) == 1


def test_browser_mode_launch_places_extra_args_before_url():
    calls = []
    launcher = BrowserLauncher(
        registry=BrowserRegistry((EdgeAdapter(),)),
        popen_factory=lambda command, **kwargs: calls.append((command, kwargs)),
    )

    result = launcher.launch(
        resolution(capability(BrowserKind.EDGE, "C:/Edge/msedge.exe")),
        url="http://127.0.0.1:8501",
        mode=LaunchMode.BROWSER,
        extra_args=("--new-window",),
    )

    assert result.ok is True
    assert result.command == (
        "C:/Edge/msedge.exe",
        "--new-window",
        "http://127.0.0.1:8501",
    )
    assert calls == [(result.command, {"shell": False})]


def test_windows_app_mode_with_ico_launches_through_icon_shortcut(tmp_path: Path):
    icon = tmp_path / "studio.ico"
    icon.write_bytes(b"icon")
    writes = []
    opened = []

    def shortcut_writer(**kwargs):
        writes.append(kwargs)
        kwargs["shortcut_path"].write_text("shortcut", encoding="utf-8")

    launcher = BrowserLauncher(
        registry=BrowserRegistry((EdgeAdapter(),)),
        popen_factory=lambda command, **kwargs: (_ for _ in ()).throw(
            AssertionError("direct browser launch should not be used")
        ),
        shortcut_writer=shortcut_writer,
        shortcut_opener=opened.append,
        is_windows=True,
    )

    result = launcher.launch(
        resolution(capability(BrowserKind.EDGE, "C:/Edge/msedge.exe")),
        url="http://127.0.0.1:8501",
        mode=LaunchMode.WEBAPP,
        title="LitPack Studio",
        extra_args=("--new-window",),
        app_icon=icon,
        artifact_root=tmp_path,
    )

    assert result.ok is True
    assert result.command == (
        "C:/Edge/msedge.exe",
        "--app=http://127.0.0.1:8501",
        "--new-window",
    )
    assert result.message == "Launched Edge in app mode through Windows shortcut."
    assert writes[0]["target_path"] == "C:/Edge/msedge.exe"
    assert writes[0]["arguments"] == ('"--app=http://127.0.0.1:8501" "--new-window"')
    assert writes[0]["working_directory"] == tmp_path
    assert writes[0]["icon_path"] == icon
    assert writes[0]["app_user_model_id"].startswith(
        "LatticeFoundry.LitLaunch.LitPack.Studio."
    )
    assert opened == [writes[0]["shortcut_path"]]
    assert result.cleanup_callbacks
    assert writes[0]["shortcut_path"].is_file()

    result.cleanup_callbacks[0]()

    assert not writes[0]["shortcut_path"].exists()


def test_windows_icon_shortcut_failure_falls_back_to_direct_launch(tmp_path: Path):
    icon = tmp_path / "studio.ico"
    icon.write_bytes(b"icon")
    calls = []

    def shortcut_writer(**kwargs):
        raise RuntimeError("shortcut blocked")

    launcher = BrowserLauncher(
        registry=BrowserRegistry((EdgeAdapter(),)),
        popen_factory=lambda command, **kwargs: calls.append((command, kwargs)),
        shortcut_writer=shortcut_writer,
        is_windows=True,
    )

    result = launcher.launch(
        resolution(capability(BrowserKind.EDGE, "C:/Edge/msedge.exe")),
        url="http://127.0.0.1:8501",
        mode=LaunchMode.WEBAPP,
        app_icon=icon,
        artifact_root=tmp_path,
    )

    assert result.ok is True
    assert result.message == "Launched Edge in app mode."
    assert calls == [
        (("C:/Edge/msedge.exe", "--app=http://127.0.0.1:8501"), {"shell": False})
    ]


def test_browser_launcher_has_no_termination_surface():
    launcher = BrowserLauncher()

    assert not hasattr(launcher, "kill")
    assert not hasattr(launcher, "terminate")
    assert not hasattr(launcher, "stop")


def test_direct_app_launch_retains_private_nonowning_process_authority(
    tmp_path: Path,
):
    class FakeProcess:
        pid = 4321

    profile = create_managed_browser_profile(tmp_path)
    executable = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")

    def authority_factory(**kwargs):
        return create_browser_launch_authority(
            **kwargs,
            root_record_provider=lambda process_id: WindowsProcessRecord(
                process_id,
                0,
                123456,
                executable,
            ),
        )

    launcher = BrowserLauncher(
        registry=BrowserRegistry((ChromeAdapter(),)),
        popen_factory=lambda command, **kwargs: FakeProcess(),
        process_authority_factory=authority_factory,
    )
    launcher._set_process_authority_launch_id("private-channel-launch-123456")

    result = launcher.launch(
        resolution(capability(BrowserKind.CHROME, str(executable))),
        url="http://127.0.0.1:8501",
        mode=LaunchMode.WEBAPP,
        extra_args=(f"--user-data-dir={profile}",),
    )
    process_authority = launcher._process_authority_snapshot()

    assert result.ok is True
    assert process_authority is not None
    assert process_authority.root_process_id == 4321
    assert process_authority.root_creation_time_100ns == 123456
    assert process_authority.browser_kind == BrowserKind.CHROME
    assert process_authority.managed_profile_dir == profile
    assert process_authority.launch_strategy == BrowserLaunchStrategy.DIRECT
    assert process_authority.launch_id == "private-channel-launch-123456"


def test_windows_shortcut_launch_does_not_infer_process_authority(tmp_path: Path):
    icon = tmp_path / "studio.ico"
    icon.write_bytes(b"icon")

    def shortcut_writer(**kwargs):
        kwargs["shortcut_path"].write_text("shortcut", encoding="utf-8")

    launcher = BrowserLauncher(
        registry=BrowserRegistry((EdgeAdapter(),)),
        shortcut_writer=shortcut_writer,
        shortcut_opener=lambda _path: None,
        is_windows=True,
    )

    result = launcher.launch(
        resolution(capability(BrowserKind.EDGE, "C:/Edge/msedge.exe")),
        url="http://127.0.0.1:8501",
        mode=LaunchMode.WEBAPP,
        app_icon=icon,
        artifact_root=tmp_path,
    )

    assert result.ok is True
    assert launcher._process_authority_snapshot() is None
    result.cleanup_callbacks[0]()


def test_windows_shortcut_launch_retains_exact_shell_process_authority(
    tmp_path: Path,
):
    icon = tmp_path / "studio.ico"
    icon.write_bytes(b"icon")
    profile = create_managed_browser_profile(tmp_path / "runtime state")
    executable = "C:/Program Files/Microsoft/Edge/Application/msedge.exe"

    def shortcut_writer(**kwargs):
        kwargs["shortcut_path"].write_text("shortcut", encoding="utf-8")

    launcher = BrowserLauncher(
        registry=BrowserRegistry((EdgeAdapter(),)),
        shortcut_writer=shortcut_writer,
        shortcut_opener=lambda _path: WindowsShellProcess(8765, 987654321),
        is_windows=True,
    )

    result = launcher.launch(
        resolution(capability(BrowserKind.EDGE, executable)),
        url="http://127.0.0.1:8501",
        mode=LaunchMode.WEBAPP,
        title="Product Studio",
        extra_args=(f"--user-data-dir={profile}", "--new-window"),
        app_icon=icon,
        artifact_root=tmp_path,
    )
    authority = launcher._process_authority_snapshot()

    assert result.ok is True
    assert authority is not None
    assert authority.root_process_id == 8765
    assert authority.root_creation_time_100ns == 987654321
    assert authority.browser_kind == BrowserKind.EDGE
    assert authority.executable_path == Path(executable)
    assert authority.managed_profile_dir == profile
    assert authority.launch_strategy == BrowserLaunchStrategy.WINDOWS_SHORTCUT
    assert f"--user-data-dir={profile}" in result.command
    assert "--new-window" in result.command
    result.cleanup_callbacks[0]()


@pytest.mark.parametrize(
    ("browser_kind", "adapter", "executable"),
    [
        (
            BrowserKind.EDGE,
            EdgeAdapter(),
            "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
        ),
        (
            BrowserKind.CHROME,
            ChromeAdapter(),
            "C:/Program Files/Google/Chrome/Application/chrome.exe",
        ),
    ],
)
def test_windows_shortcut_authority_has_edge_chrome_parity(
    tmp_path: Path,
    browser_kind: BrowserKind,
    adapter,
    executable: str,
):
    icon = tmp_path / f"{browser_kind.value}.ico"
    icon.write_bytes(b"icon")
    profile = create_managed_browser_profile(tmp_path / browser_kind.value)

    def shortcut_writer(**kwargs):
        kwargs["shortcut_path"].write_text("shortcut", encoding="utf-8")

    launcher = BrowserLauncher(
        registry=BrowserRegistry((adapter,)),
        shortcut_writer=shortcut_writer,
        shortcut_opener=lambda _path: WindowsShellProcess(8765, 987654321),
        is_windows=True,
    )

    result = launcher.launch(
        resolution(capability(browser_kind, executable)),
        url="http://127.0.0.1:8501",
        mode=LaunchMode.WEBAPP,
        extra_args=(f"--user-data-dir={profile}",),
        app_icon=icon,
        artifact_root=tmp_path,
    )
    authority = launcher._process_authority_snapshot()

    assert result.ok is True
    assert authority is not None
    assert authority.browser_kind == browser_kind
    assert authority.executable_path == Path(executable)
    assert authority.managed_profile_dir == profile
    assert authority.launch_strategy == BrowserLaunchStrategy.WINDOWS_SHORTCUT
    result.cleanup_callbacks[0]()


def test_authority_factory_failure_does_not_break_normal_browser_launch(
    tmp_path: Path,
):
    profile = create_managed_browser_profile(tmp_path)

    class FakeProcess:
        pid = 4321

    launcher = BrowserLauncher(
        registry=BrowserRegistry((ChromeAdapter(),)),
        popen_factory=lambda command, **kwargs: FakeProcess(),
        process_authority_factory=lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("authority unavailable")
        ),
    )

    result = launcher.launch(
        resolution(capability(BrowserKind.CHROME, "C:/Chrome/chrome.exe")),
        url="http://127.0.0.1:8501",
        mode=LaunchMode.WEBAPP,
        extra_args=(f"--user-data-dir={profile}",),
    )

    assert result.ok is True
    assert launcher._process_authority_snapshot() is None
