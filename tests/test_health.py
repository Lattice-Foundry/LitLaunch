from urllib.error import URLError

from litlaunch.health import (
    HealthChecker,
    build_streamlit_app_url,
    build_streamlit_health_url,
)


class FakeResponse:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def test_health_url_builds_correctly():
    assert (
        build_streamlit_health_url("127.0.0.1", 8501)
        == "http://127.0.0.1:8501/_stcore/health"
    )


def test_app_url_builds_correctly():
    assert build_streamlit_app_url("127.0.0.1", 8501) == "http://127.0.0.1:8501"


def test_check_once_true_on_successful_response():
    checker = HealthChecker(opener=lambda url, timeout: FakeResponse(204))

    assert checker.check_once("http://127.0.0.1:8501/_stcore/health") is True


def test_check_once_false_on_exception_or_non_200():
    failing_checker = HealthChecker(
        opener=lambda url, timeout: (_ for _ in ()).throw(URLError("nope"))
    )
    unhealthy_checker = HealthChecker(opener=lambda url, timeout: FakeResponse(500))

    assert failing_checker.check_once("url") is False
    assert unhealthy_checker.check_once("url") is False


def test_wait_until_healthy_succeeds_after_retries():
    calls = []
    clock = FakeClock()

    def opener(url, timeout):
        calls.append(url)
        if len(calls) < 3:
            raise URLError("not yet")
        return FakeResponse(200)

    checker = HealthChecker(
        opener=opener,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )

    assert checker.wait_until_healthy("health-url", timeout_seconds=1.0) is True
    assert calls == ["health-url", "health-url", "health-url"]
    assert clock.sleeps == [0.25, 0.25]


def test_wait_until_healthy_times_out_cleanly():
    clock = FakeClock()
    checker = HealthChecker(
        opener=lambda url, timeout: (_ for _ in ()).throw(URLError("nope")),
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )

    assert checker.wait_until_healthy("health-url", timeout_seconds=0.5) is False
    assert clock.now >= 0.5
