"""Tests for ansi_strip — remove ANSI escape codes."""

from __future__ import annotations

from harness.tools.ansi_strip import strip_ansi


class TestStripAnsi:
    def test_plain_text_passes_through(self):
        assert strip_ansi("hello world") == "hello world"

    def test_strips_sgr_codes(self):
        assert strip_ansi("\x1b[31mred\x1b[0m") == "red"

    def test_strips_cursor_moves(self):
        assert strip_ansi("\x1b[2J\x1b[Hclean") == "clean"

    def test_strips_multiple_codes(self):
        result = strip_ansi("\x1b[1m\x1b[32mbold green\x1b[0m")
        assert result == "bold green"

    def test_empty_string(self):
        assert strip_ansi("") == ""

    def test_no_ansi(self):
        assert strip_ansi("plain text\nwith newlines") == "plain text\nwith newlines"
