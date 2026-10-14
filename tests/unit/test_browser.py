"""Tests for the splash screen browser launcher."""

import os
from unittest.mock import MagicMock

import pytest

from pikaraoke.lib.browser import DEFAULT_DISPLAY, Browser


@pytest.fixture
def browser():
    return Browser(MagicMock())


class TestDefaultDisplayForSSH:
    """DISPLAY defaulting so SSH launches reach the attached screen."""

    def test_sets_display_when_unset_on_linux(self, browser, monkeypatch):
        monkeypatch.setattr("pikaraoke.lib.browser.is_linux", lambda: True)
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

        browser._default_display_for_ssh()

        assert os.environ["DISPLAY"] == DEFAULT_DISPLAY

    def test_leaves_existing_display_untouched(self, browser, monkeypatch):
        monkeypatch.setattr("pikaraoke.lib.browser.is_linux", lambda: True)
        monkeypatch.setenv("DISPLAY", ":1")

        browser._default_display_for_ssh()

        assert os.environ["DISPLAY"] == ":1"

    def test_skips_wayland_sessions(self, browser, monkeypatch):
        monkeypatch.setattr("pikaraoke.lib.browser.is_linux", lambda: True)
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

        browser._default_display_for_ssh()

        assert "DISPLAY" not in os.environ

    def test_no_op_off_linux(self, browser, monkeypatch):
        monkeypatch.setattr("pikaraoke.lib.browser.is_linux", lambda: False)
        monkeypatch.delenv("DISPLAY", raising=False)

        browser._default_display_for_ssh()

        assert "DISPLAY" not in os.environ
