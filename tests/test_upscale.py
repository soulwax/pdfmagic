import subprocess

import pytest

from pdfbetter.upscale import (
    RealesrganFailedError,
    RealesrganNotFoundError,
    find_realesrgan,
    upscale_directory,
)


def test_find_realesrgan_prefers_explicit_path():
    assert find_realesrgan(explicit_path="/custom/path/realesrgan") == "/custom/path/realesrgan"


def test_find_realesrgan_uses_env_var(monkeypatch):
    monkeypatch.setenv("PDFBETTER_REALESRGAN_PATH", "/env/path/realesrgan")
    assert find_realesrgan() == "/env/path/realesrgan"


def test_find_realesrgan_falls_back_to_path_lookup(monkeypatch):
    monkeypatch.delenv("PDFBETTER_REALESRGAN_PATH", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/realesrgan-ncnn-vulkan")
    assert find_realesrgan() == "/usr/local/bin/realesrgan-ncnn-vulkan"


def test_find_realesrgan_raises_when_not_found(monkeypatch):
    monkeypatch.delenv("PDFBETTER_REALESRGAN_PATH", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(RealesrganNotFoundError):
        find_realesrgan()


def test_upscale_directory_invokes_expected_command_with_defaults(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, text):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    upscale_directory("in_dir", "out_dir", binary_path="/path/to/realesrgan")

    assert captured["cmd"] == [
        "/path/to/realesrgan",
        "-i",
        "in_dir",
        "-o",
        "out_dir",
        "-n",
        "realesrgan-x4plus",
        "-s",
        "2",
        "-t",
        "0",
        "-j",
        "1:2:2",
    ]


def test_upscale_directory_appends_tta_flag_when_enabled(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, text):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    upscale_directory("in_dir", "out_dir", binary_path="/path/to/realesrgan", tta=True)

    assert captured["cmd"][-1] == "-x"


def test_upscale_directory_passes_custom_tile_and_threads(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, text):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    upscale_directory("in_dir", "out_dir", binary_path="/path/to/realesrgan", tile=256, threads="2:4:4")

    assert "256" in captured["cmd"]
    assert "2:4:4" in captured["cmd"]


def test_upscale_directory_raises_on_failure(monkeypatch):
    def fake_run(cmd, capture_output, text):
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RealesrganFailedError, match="boom"):
        upscale_directory("in_dir", "out_dir", binary_path="/path/to/realesrgan")
