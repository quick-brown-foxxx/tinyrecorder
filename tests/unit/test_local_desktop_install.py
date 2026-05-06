"""Tests for the local desktop integration installer."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def test_local_install_script_creates_launcher_and_icon_links(tmp_path: Path) -> None:
    home_dir = tmp_path / "home"
    xdg_data_home = tmp_path / "data"
    home_dir.mkdir()
    xdg_data_home.mkdir()

    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "install_local_desktop.py"
    uv_path = shutil.which("uv")
    assert uv_path is not None

    result = subprocess.run(  # noqa: S603  # trusted local uv + repo-local installer under test
        [uv_path, "run", "--script", str(script_path)],
        capture_output=True,
        text=True,
        check=False,
        env={
            "HOME": str(home_dir),
            "PATH": "/usr/bin:/bin",
            "XDG_DATA_HOME": str(xdg_data_home),
        },
    )

    assert result.returncode == 0

    launcher_path = home_dir / ".local" / "bin" / "tinyrecorder"
    desktop_path = xdg_data_home / "applications" / "tinyrecorder.desktop"
    icon_path = xdg_data_home / "icons" / "hicolor" / "scalable" / "apps" / "tinyrecorder.svg"

    assert launcher_path.is_symlink()
    assert desktop_path.exists()
    assert icon_path.is_symlink()


def test_local_install_script_writes_desktop_entry_with_explicit_exec(tmp_path: Path) -> None:
    home_dir = tmp_path / "home"
    xdg_data_home = tmp_path / "data"
    home_dir.mkdir()
    xdg_data_home.mkdir()

    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "install_local_desktop.py"
    uv_path = shutil.which("uv")
    assert uv_path is not None

    result = subprocess.run(  # noqa: S603  # trusted local uv + repo-local installer under test
        [uv_path, "run", "--script", str(script_path)],
        capture_output=True,
        text=True,
        check=False,
        env={
            "HOME": str(home_dir),
            "PATH": "/usr/bin:/bin",
            "XDG_DATA_HOME": str(xdg_data_home),
        },
    )

    assert result.returncode == 0

    desktop_path = xdg_data_home / "applications" / "tinyrecorder.desktop"
    desktop_text = desktop_path.read_text(encoding="utf-8")

    assert "Exec=" in desktop_text
    assert str(home_dir / ".local" / "bin" / "tinyrecorder") in desktop_text
    assert "Icon=tinyrecorder" in desktop_text
    assert "Terminal=false" in desktop_text
    assert "Type=Application" in desktop_text
    assert "StartupWMClass=tinyrecorder" in desktop_text
