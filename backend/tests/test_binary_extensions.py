"""Tests for binary_extensions — detect binary files by extension."""

from __future__ import annotations

from harness.tools.binary_extensions import BINARY_EXTENSIONS, has_binary_extension


class TestBinaryExtensions:
    def test_png_is_binary(self):
        assert has_binary_extension("image.png")

    def test_jpg_is_binary(self):
        assert has_binary_extension("photo.jpg")
        assert has_binary_extension("photo.jpeg")

    def test_mp4_is_binary(self):
        assert has_binary_extension("video.mp4")

    def test_py_is_not_binary(self):
        assert not has_binary_extension("script.py")

    def test_ts_is_not_binary(self):
        assert not has_binary_extension("component.tsx")

    def test_md_is_not_binary(self):
        assert not has_binary_extension("readme.md")

    def test_case_insensitive(self):
        assert has_binary_extension("image.PNG")
        assert has_binary_extension("Image.JPG")

    def test_path_with_directories(self):
        assert has_binary_extension("/path/to/image.png")
        assert not has_binary_extension("/path/to/script.py")

    def test_no_extension(self):
        assert not has_binary_extension("Makefile")
        assert not has_binary_extension("Dockerfile")

    def test_dotfiles(self):
        assert not has_binary_extension(".gitignore")
        assert not has_binary_extension(".env")

    def test_zip_is_binary(self):
        assert has_binary_extension("archive.zip")

    def test_exe_is_binary(self):
        assert has_binary_extension("installer.exe")

    def test_pyc_is_binary(self):
        assert has_binary_extension("module.pyc")

    def test_binary_extensions_set_contains_common(self):
        assert ".png" in BINARY_EXTENSIONS
        assert ".jpg" in BINARY_EXTENSIONS
        assert ".zip" in BINARY_EXTENSIONS
        assert ".exe" in BINARY_EXTENSIONS
