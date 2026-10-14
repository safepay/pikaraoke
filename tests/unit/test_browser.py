"""Tests for the splash screen browser launcher."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pikaraoke.lib.browser import DEFAULT_DISPLAY, Browser


def _fake_karaoke(**overrides) -> SimpleNamespace:
    defaults = {
        "url": "http://192.168.1.50:5555",
        "port": 5555,
        "is_raspberry_pi": False,
        "log_level": 20,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def browser():
    return Browser(MagicMock())


def test_splash_url_uses_loopback_not_the_advertised_url():
    browser = Browser(_fake_karaoke())
    assert browser.splash_url == "http://127.0.0.1:5555/splash"


def test_splash_url_ignores_url_override_and_base_path():
    karaoke = _fake_karaoke(url="https://karaoke.example.com/karaoke", port=5555)
    browser = Browser(karaoke)
    assert browser.splash_url == "http://127.0.0.1:5555/splash"


def test_splash_url_follows_the_configured_port():
    browser = Browser(_fake_karaoke(url="http://192.168.1.50:8080", port=8080))
    assert browser.splash_url == "http://127.0.0.1:8080/splash"


class TestConfigureSSHDisplay:
    """Display selection so SSH launches reach the attached screen."""

    def _as_ssh_linux(self, monkeypatch):
        """Simulate a Linux SSH shell: on Linux, no display inherited."""
        monkeypatch.setattr("pikaraoke.lib.browser.is_linux", lambda: True)
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")

    def test_prefers_wayland_when_socket_present(self, browser, monkeypatch):
        self._as_ssh_linux(monkeypatch)
        monkeypatch.setattr(browser, "_find_wayland_socket", lambda _: "wayland-0")

        assert browser._configure_ssh_display() == "wayland"
        assert os.environ["WAYLAND_DISPLAY"] == "wayland-0"
        assert "DISPLAY" not in os.environ

    def test_falls_back_to_x_display_without_wayland(self, browser, monkeypatch):
        self._as_ssh_linux(monkeypatch)
        monkeypatch.setattr(browser, "_find_wayland_socket", lambda _: None)

        assert browser._configure_ssh_display() is None
        assert os.environ["DISPLAY"] == DEFAULT_DISPLAY

    def test_leaves_existing_display_untouched(self, browser, monkeypatch):
        monkeypatch.setattr("pikaraoke.lib.browser.is_linux", lambda: True)
        monkeypatch.setenv("DISPLAY", ":1")

        assert browser._configure_ssh_display() is None
        assert os.environ["DISPLAY"] == ":1"

    def test_leaves_existing_wayland_session_untouched(self, browser, monkeypatch):
        monkeypatch.setattr("pikaraoke.lib.browser.is_linux", lambda: True)
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

        assert browser._configure_ssh_display() is None
        assert "DISPLAY" not in os.environ

    def test_no_op_off_linux(self, browser, monkeypatch):
        monkeypatch.setattr("pikaraoke.lib.browser.is_linux", lambda: False)
        monkeypatch.delenv("DISPLAY", raising=False)

        assert browser._configure_ssh_display() is None
        assert "DISPLAY" not in os.environ


class TestFindWaylandSocket:
    """Locating a Wayland socket in the runtime directory."""

    def test_returns_socket_ignoring_lock(self, browser, tmp_path):
        (tmp_path / "wayland-0").touch()
        (tmp_path / "wayland-0.lock").touch()

        assert browser._find_wayland_socket(str(tmp_path)) == "wayland-0"

    def test_returns_none_when_absent(self, browser, tmp_path):
        assert browser._find_wayland_socket(str(tmp_path)) is None

    def test_returns_none_when_dir_missing(self, browser):
        assert browser._find_wayland_socket("/no/such/runtime/dir") is None
