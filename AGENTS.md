# AGENTS.md

## Source Of Truth
- Trust `pyproject.toml`, `tinyrecorder.py`, `scripts/install_local_desktop.py`, and the unit tests over prose. `README.md` is intentionally short and human-facing, not exhaustive implementation documentation.

## Real Entrypoints
- The actual app is the single-file root script `tinyrecorder.py`.
- Use `uv run --script tinyrecorder.py` when you want the runtime path that matches the local desktop launcher.
- `uv run poe app` also works because it runs `python -m tinyrecorder`, but the packaging metadata is currently stale: `[project.scripts]` and Hatch still point at `src/tinyrecorder`, and there is no `src/` tree.
- Local desktop integration is handled by `scripts/install_local_desktop.py`; the convenience command is `uv run poe install_local_desktop`.

## Verification Commands
- Full sweep: `uv run poe lint_full`
- Core app tests: `uv run pytest tests/unit/test_tinyrecorder.py -n0`
- Desktop installer tests: `uv run pytest tests/unit/test_local_desktop_install.py -n0`
- `pytest` defaults to xdist via `pyproject.toml` (`-n auto --dist worksteal -m "not e2e"`). Use `-n0` for deterministic debugging.

## Important Layout
- `tinyrecorder.py`: current app boundary; UI, tray logic, state machine, recorder wrapper, config/history, and OpenAI-compatible transcription all live here.
- `scripts/install_local_desktop.py`: creates the user-local launcher/icon install by symlinking the script and icon, and generating the final `.desktop` file.
- `resources/desktop/tinyrecorder.desktop.in` and `resources/icons/tinyrecorder.svg`: installer inputs. Edit these, not the generated files in `~/.local/share/...`.
- `tests/unit/test_tinyrecorder.py` covers app regressions and helper behavior; `tests/unit/test_local_desktop_install.py` intentionally tests the installer script itself rather than the Poe wrapper.

## Gotchas
- If you add imports to `tinyrecorder.py`, keep both dependency declarations aligned: the PEP 723 header for `uv run --script` and `pyproject.toml` for project-env test runs.
- Transcription uses an OpenAI-compatible HTTP protocol. Keep `AppConfig.api_base_url` and `api.base_url` in TOML working; do not re-hardcode `https://api.openai.com/v1` at call sites.
- `uv run poe install_local_desktop` writes to real user-local XDG paths (`~/.local/bin`, `~/.local/share/applications`, `~/.local/share/icons/hicolor/scalable/apps`). Prefer the installer tests over ad hoc local installs while iterating.
- Runtime support is Linux-tested. Windows has a minimal compatibility path (`APPDATA`/`LOCALAPPDATA` app dirs and no Linux portal env var) and should at least start, but tray/audio behavior is not yet verified on a real Windows host.

## Future
- Current version is MVP implementation
- In future complex rewrite will come from plans in `docs/`
