#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "rusty-results>=1.1.1",
#   "typer>=0.15.2",
# ]
# ///

"""Install TinyRecorder desktop integration into the current user's XDG paths."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import typer
from rusty_results.prelude import Err, Ok, Result

APP_SLUG: Final = "tinyrecorder"
DESKTOP_ENTRY_NAME: Final = f"{APP_SLUG}.desktop"
ICON_NAME: Final = f"{APP_SLUG}.svg"


@dataclass(frozen=True, slots=True)
class InstallPaths:
    repo_root: Path
    launcher_source: Path
    desktop_template: Path
    icon_source: Path
    bin_dir: Path
    launcher_target: Path
    applications_dir: Path
    desktop_target: Path
    icons_dir: Path
    icon_target: Path


type AppResult[T] = Result[T, str]


def resolve_install_paths(script_path: Path) -> AppResult[InstallPaths]:
    repo_root = script_path.resolve().parents[1]
    home_dir = Path.home()
    bin_dir = Path(os.environ.get("LOCAL_BIN_DIR", str(home_dir / ".local" / "bin"))).expanduser()
    data_home = Path(os.environ.get("XDG_DATA_HOME", str(home_dir / ".local" / "share"))).expanduser()

    launcher_source = repo_root / "tinyrecorder.py"
    desktop_template = repo_root / "resources" / "desktop" / "tinyrecorder.desktop.in"
    icon_source = repo_root / "resources" / "icons" / ICON_NAME

    missing_paths = [path for path in (launcher_source, desktop_template, icon_source) if not path.exists()]
    if missing_paths:
        missing_text = ", ".join(str(path) for path in missing_paths)
        return Err(f"Missing install asset(s): {missing_text}")

    applications_dir = data_home / "applications"
    icons_dir = data_home / "icons" / "hicolor" / "scalable" / "apps"

    return Ok(
        InstallPaths(
            repo_root=repo_root,
            launcher_source=launcher_source,
            desktop_template=desktop_template,
            icon_source=icon_source,
            bin_dir=bin_dir,
            launcher_target=bin_dir / APP_SLUG,
            applications_dir=applications_dir,
            desktop_target=applications_dir / DESKTOP_ENTRY_NAME,
            icons_dir=icons_dir,
            icon_target=icons_dir / ICON_NAME,
        )
    )


def ensure_directories(paths: InstallPaths) -> AppResult[None]:
    for directory in (paths.bin_dir, paths.applications_dir, paths.icons_dir):
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return Err(f"Cannot create directory {directory}: {exc}")
    return Ok(None)


def replace_with_symlink(source: Path, target: Path) -> AppResult[None]:
    try:
        if target.exists() or target.is_symlink():
            target.unlink()
        target.symlink_to(source)
    except OSError as exc:
        return Err(f"Cannot create symlink {target} -> {source}: {exc}")
    return Ok(None)


def render_desktop_entry(template_path: Path, launcher_target: Path) -> AppResult[str]:
    try:
        template_text = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        return Err(f"Cannot read desktop template {template_path}: {exc}")
    return Ok(template_text.replace("@EXEC_PATH@", str(launcher_target)))


def write_desktop_entry(target: Path, desktop_text: str) -> AppResult[None]:
    try:
        target.write_text(desktop_text, encoding="utf-8")
    except OSError as exc:
        return Err(f"Cannot write desktop entry {target}: {exc}")
    return Ok(None)


def install_local_desktop(script_path: Path) -> AppResult[list[str]]:
    resolved = resolve_install_paths(script_path)
    if resolved.is_err:
        return Err(resolved.unwrap_err())
    paths = resolved.unwrap()

    ensured = ensure_directories(paths)
    if ensured.is_err:
        return Err(ensured.unwrap_err())

    launcher_linked = replace_with_symlink(paths.launcher_source, paths.launcher_target)
    if launcher_linked.is_err:
        return Err(launcher_linked.unwrap_err())

    icon_linked = replace_with_symlink(paths.icon_source, paths.icon_target)
    if icon_linked.is_err:
        return Err(icon_linked.unwrap_err())

    rendered = render_desktop_entry(paths.desktop_template, paths.launcher_target)
    if rendered.is_err:
        return Err(rendered.unwrap_err())

    written = write_desktop_entry(paths.desktop_target, rendered.unwrap())
    if written.is_err:
        return Err(written.unwrap_err())

    return Ok(
        [
            f"Installed TinyRecorder launcher to {paths.desktop_target}",
            f"Installed TinyRecorder icon to {paths.icon_target}",
            f"Installed TinyRecorder executable link to {paths.launcher_target}",
        ]
    )


app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


@app.callback(invoke_without_command=True)
def main() -> None:
    result = install_local_desktop(Path(__file__))
    if result.is_err:
        typer.echo(f"Error: {result.unwrap_err()}", err=True)
        raise typer.Exit(1)
    for line in result.unwrap():
        typer.echo(line)


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        raise SystemExit(130) from None
