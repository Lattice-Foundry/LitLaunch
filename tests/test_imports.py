import re
from importlib.metadata import version

import litlaunch
from litlaunch import (
    THEME_COLORS,
    Architecture,
    BackendCommand,
    BackendCommandContext,
    BackendCommandProvider,
    BrowserCapability,
    BrowserChoice,
    BrowserError,
    BrowserKind,
    BrowserLauncher,
    BrowserLaunchResult,
    BrowserResolution,
    CommandBuildError,
    ConfigurationError,
    ConsoleMode,
    ConsolePhase,
    ConsoleRenderer,
    ConsoleTheme,
    DiagnosticCollector,
    DiagnosticItem,
    DiagnosticSection,
    DiagnosticsReport,
    DiagnosticStatus,
    HealthChecker,
    HTMLDiagnosticsRenderer,
    JSONDiagnosticsRenderer,
    LauncherConfig,
    LauncherRuntime,
    LaunchEvent,
    LaunchMode,
    LaunchPlan,
    LaunchProfile,
    LaunchResult,
    LaunchState,
    LitLaunchError,
    ManagedProcess,
    MonitoredRunResult,
    NoopWindowMonitor,
    OperatingSystem,
    PlatformDetector,
    PlatformInfo,
    PollingWindowMonitor,
    PortError,
    PortManager,
    ProcessError,
    ProcessManager,
    RuntimeSession,
    SanitizedBundleRenderer,
    ShutdownClient,
    ShutdownConfig,
    ShutdownHook,
    ShutdownHookRegistry,
    ShutdownHookResult,
    ShutdownRequestResult,
    ShutdownResult,
    StreamlitBackendCommandProvider,
    StreamlitCommandBuilder,
    StreamlitLauncher,
    TextDiagnosticsRenderer,
    ThemeColor,
    WindowInfo,
    WindowMonitor,
    WindowMonitorConfig,
    WindowMonitorEvent,
    WindowMonitorResult,
    WindowMonitorStatus,
    WindowsChromiumWindowMonitor,
    WindowsWindowProvider,
    WindowTarget,
    __version__,
    create_window_monitor,
    get_theme_color,
    is_chromium_window,
    is_hex_color,
    is_theme_color_name,
    load_profile,
    load_profiles,
    run_monitored_webapp,
    run_profile,
)


def test_public_imports_are_available():
    assert LauncherConfig(app_path="app.py").mode == LaunchMode.BROWSER
    assert BackendCommand(("python",)).command == ("python",)
    assert BackendCommandContext
    assert BackendCommandProvider
    assert BrowserChoice.AUTO.value == "auto"
    assert BrowserKind.EDGE.value == "edge"
    assert BrowserCapability
    assert BrowserLaunchResult
    assert BrowserLauncher
    assert BrowserResolution
    assert issubclass(BrowserError, LitLaunchError)
    assert issubclass(CommandBuildError, LitLaunchError)
    assert ConsoleMode.NORMAL.value == "normal"
    assert ConsolePhase.BACKEND.value == "Backend"
    assert ConsoleRenderer
    assert ConsoleTheme
    assert DiagnosticCollector
    assert DiagnosticItem
    assert DiagnosticSection
    assert DiagnosticStatus.OK.value == "ok"
    assert DiagnosticsReport
    assert HTMLDiagnosticsRenderer
    assert HealthChecker
    assert JSONDiagnosticsRenderer
    assert issubclass(ConfigurationError, LitLaunchError)
    assert LaunchState.CREATED.value == "created"
    assert LaunchEvent
    assert LaunchPlan
    assert LaunchProfile
    assert LaunchResult
    assert MonitoredRunResult
    assert OperatingSystem.WINDOWS.value == "windows"
    assert Architecture.X64.value == "x64"
    assert PlatformDetector
    assert PlatformInfo
    assert ManagedProcess
    assert NoopWindowMonitor
    assert PortManager
    assert issubclass(PortError, LitLaunchError)
    assert PollingWindowMonitor
    assert issubclass(ProcessError, LitLaunchError)
    assert ProcessManager
    assert RuntimeSession
    assert SanitizedBundleRenderer
    assert LauncherRuntime
    assert ShutdownClient
    assert ShutdownConfig
    assert ShutdownHook
    assert ShutdownHookRegistry
    assert ShutdownHookResult
    assert ShutdownRequestResult
    assert ShutdownResult
    assert StreamlitBackendCommandProvider
    assert StreamlitCommandBuilder
    assert StreamlitLauncher
    assert THEME_COLORS["streamlit_blue"].hex == "#1c83e1"
    assert TextDiagnosticsRenderer
    assert ThemeColor
    assert WindowsChromiumWindowMonitor
    assert WindowsWindowProvider
    assert WindowInfo
    assert WindowMonitor
    assert WindowMonitorConfig
    assert WindowMonitorEvent
    assert WindowMonitorResult
    assert WindowMonitorStatus.WINDOW_CLOSED.value == "window_closed"
    assert WindowTarget
    assert create_window_monitor
    assert get_theme_color("streamlit_blue")
    assert is_chromium_window
    assert is_hex_color("#1c83e1")
    assert is_theme_color_name("streamlit_blue")
    assert load_profile
    assert load_profiles
    assert run_monitored_webapp
    assert run_profile


def test_public_all_is_explicit():
    expected = [
        "Architecture",
        "BackendCommand",
        "BackendCommandContext",
        "BackendCommandProvider",
        "BrowserCapability",
        "BrowserChoice",
        "BrowserError",
        "BrowserKind",
        "BrowserLaunchResult",
        "BrowserLauncher",
        "BrowserResolution",
        "CommandBuildError",
        "ConfigurationError",
        "ConsoleMode",
        "ConsolePhase",
        "ConsoleRenderer",
        "ConsoleTheme",
        "DiagnosticCollector",
        "DiagnosticItem",
        "DiagnosticSection",
        "DiagnosticStatus",
        "DiagnosticsReport",
        "HTMLDiagnosticsRenderer",
        "HealthChecker",
        "JSONDiagnosticsRenderer",
        "LaunchEvent",
        "LaunchMode",
        "LaunchPlan",
        "LaunchProfile",
        "LaunchResult",
        "LaunchState",
        "LauncherConfig",
        "LauncherRuntime",
        "LitLaunchError",
        "ManagedProcess",
        "MonitoredRunResult",
        "NoopWindowMonitor",
        "OperatingSystem",
        "PlatformDetector",
        "PlatformInfo",
        "PollingWindowMonitor",
        "PortError",
        "PortManager",
        "ProcessError",
        "ProcessManager",
        "RuntimeSession",
        "run_monitored_webapp",
        "run_profile",
        "SanitizedBundleRenderer",
        "ShutdownClient",
        "ShutdownConfig",
        "ShutdownHook",
        "ShutdownHookRegistry",
        "ShutdownHookResult",
        "ShutdownRequestResult",
        "ShutdownResult",
        "StreamlitBackendCommandProvider",
        "StreamlitCommandBuilder",
        "StreamlitLauncher",
        "THEME_COLORS",
        "TextDiagnosticsRenderer",
        "ThemeColor",
        "WindowInfo",
        "WindowMonitor",
        "WindowMonitorConfig",
        "WindowMonitorEvent",
        "WindowMonitorResult",
        "WindowMonitorStatus",
        "WindowTarget",
        "WindowsChromiumWindowMonitor",
        "WindowsWindowProvider",
        "__version__",
        "create_window_monitor",
        "get_theme_color",
        "is_chromium_window",
        "is_hex_color",
        "is_theme_color_name",
        "load_profile",
        "load_profiles",
    ]
    assert sorted(litlaunch.__all__) == sorted(expected)
    assert not hasattr(litlaunch, "ConsoleColor")


def test_version_is_public_and_internal_baseline():
    assert litlaunch.__version__ == "0.85.0"
    assert __version__ == "0.85.0"
    assert re.fullmatch(r"\d+\.\d+\.\d+", litlaunch.__version__)


def test_package_metadata_version_matches_public_version():
    assert version("litlaunch") == litlaunch.__version__
