"""Tests for the splash screen browser launcher."""

import os
import socket
from unittest.mock import MagicMock

import pytest

from pikaraoke.lib.browser import DEFAULT_DISPLAY, Browser


@pytest.fixture
def browser():
    return Browser(MagicMock())


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

        env, ozone = browser._configure_ssh_display()

        assert ozone == "wayland"
        assert env == {"XDG_RUNTIME_DIR": "/run/user/1000", "WAYLAND_DISPLAY": "wayland-0"}
        # The process environment is never mutated; overrides apply to the subprocess only.
        assert "WAYLAND_DISPLAY" not in os.environ
        assert "DISPLAY" not in os.environ

    def test_falls_back_to_x_display_without_wayland(self, browser, monkeypatch):
        self._as_ssh_linux(monkeypatch)
        monkeypatch.setattr(browser, "_find_wayland_socket", lambda _: None)

        env, ozone = browser._configure_ssh_display()

        assert ozone is None
        assert env == {"DISPLAY": DEFAULT_DISPLAY}
        assert "DISPLAY" not in os.environ

    def test_redirects_forwarded_x_display_to_local_screen(self, browser, monkeypatch):
        self._as_ssh_linux(monkeypatch)
        monkeypatch.setenv("DISPLAY", "localhost:10.0")
        monkeypatch.setattr(browser, "_find_wayland_socket", lambda _: None)

        env, ozone = browser._configure_ssh_display()

        assert ozone is None
        assert env == {"DISPLAY": DEFAULT_DISPLAY}

    def test_warns_when_external_monitor_requested_under_wayland(self, monkeypatch, caplog):
        browser = Browser(MagicMock(), external_monitor=True)
        self._as_ssh_linux(monkeypatch)
        monkeypatch.setattr(browser, "_find_wayland_socket", lambda _: "wayland-0")

        with caplog.at_level("WARNING"):
            browser._configure_ssh_display()

        assert any("external-monitor" in r.message for r in caplog.records)

    def test_leaves_existing_local_display_untouched(self, browser, monkeypatch):
        monkeypatch.setattr("pikaraoke.lib.browser.is_linux", lambda: True)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.setenv("DISPLAY", ":1")

        assert browser._configure_ssh_display() == (None, None)
        assert os.environ["DISPLAY"] == ":1"

    def test_leaves_existing_wayland_session_untouched(self, browser, monkeypatch):
        monkeypatch.setattr("pikaraoke.lib.browser.is_linux", lambda: True)
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

        assert browser._configure_ssh_display() == (None, None)
        assert "DISPLAY" not in os.environ

    def test_no_op_off_linux(self, browser, monkeypatch):
        monkeypatch.setattr("pikaraoke.lib.browser.is_linux", lambda: False)
        monkeypatch.delenv("DISPLAY", raising=False)

        assert browser._configure_ssh_display() == (None, None)
        assert "DISPLAY" not in os.environ


class TestFindWaylandSocket:
    """Locating a live Wayland socket in the runtime directory."""

    @staticmethod
    def _listening_socket(path):
        """Bind a Unix socket that accepts connections, as a compositor would."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(path))
        sock.listen(1)
        return sock

    def test_returns_live_socket_ignoring_lock(self, browser, tmp_path):
        sock = self._listening_socket(tmp_path / "wayland-0")
        (tmp_path / "wayland-0.lock").touch()
        try:
            assert browser._find_wayland_socket(str(tmp_path)) == "wayland-0"
        finally:
            sock.close()

    def test_skips_stale_socket_for_live_one(self, browser, tmp_path):
        (tmp_path / "wayland-0").touch()  # stale: plain file, nothing listening
        sock = self._listening_socket(tmp_path / "wayland-1")
        try:
            assert browser._find_wayland_socket(str(tmp_path)) == "wayland-1"
        finally:
            sock.close()

    def test_returns_none_when_only_stale_socket(self, browser, tmp_path):
        (tmp_path / "wayland-0").touch()

        assert browser._find_wayland_socket(str(tmp_path)) is None

    def test_returns_none_when_absent(self, browser, tmp_path):
        assert browser._find_wayland_socket(str(tmp_path)) is None

    def test_returns_none_when_dir_missing(self, browser):
        assert browser._find_wayland_socket("/no/such/runtime/dir") is None
