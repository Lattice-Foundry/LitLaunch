from litlaunch.browsers.chrome import ChromeAdapter
from litlaunch.browsers.edge import EdgeAdapter


def test_edge_adapter_builds_chromium_app_command():
    command = EdgeAdapter("C:/Edge/msedge.exe").build_launch_command(
        "http://127.0.0.1:8501",
        title="Example",
    )

    assert command == ("C:/Edge/msedge.exe", "--app=http://127.0.0.1:8501")


def test_chrome_adapter_builds_chromium_app_command():
    command = ChromeAdapter("C:/Chrome/chrome.exe").build_launch_command(
        "http://127.0.0.1:8501",
        title="Example",
    )

    assert command == (
        "C:/Chrome/chrome.exe",
        "--app=http://127.0.0.1:8501",
    )


def test_extra_browser_args_are_preserved():
    command = EdgeAdapter("C:/Edge/msedge.exe").build_launch_command(
        "http://127.0.0.1:8501",
        title="Example",
        extra_args=["--new-window", "--disable-extensions"],
    )

    assert command == (
        "C:/Edge/msedge.exe",
        "--app=http://127.0.0.1:8501",
        "--new-window",
        "--disable-extensions",
    )


def test_browser_command_is_not_shell_string():
    command = ChromeAdapter("C:/Chrome/chrome.exe").build_launch_command(
        "http://127.0.0.1:8501",
        title="Example",
    )

    assert isinstance(command, tuple)
    assert not isinstance(command, str)
