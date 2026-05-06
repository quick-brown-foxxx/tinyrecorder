# TinyRecorder

TinyRecorder is a small Linux/Windows tray app for speech-to-text.

Press record, talk, and get text back. It is built for quick everyday use: tray controls, microphone selection, file import, transcript history, and simple desktop integration.

This repo is still an early MVP, but it already works as a real app.

## Run It

The only dependency is `uv`.

```bash
./tinyrecorder.py

# or on other platforms
uv run poe app
```

## Install It Into Your Desktop

```bash
# linux only rn
scripts/install_local_desktop.py
```

That installs a launcher, icon, and menu entry for your local user account.

## What You Need

- Linux tested; Windows should at least start, but is not yet fully verified
- a microphone
- an OpenAI API key, or a local OpenAI-compatible endpoint

Open Settings to change the API base URL. The default is OpenAI, but local providers such as Ollama-style OpenAI-compatible servers can use their own `/v1` URL.

## Where It Keeps Things

- Config: `~/.config/tinyrecorder/config.toml`
- Cached audio: `~/.cache/tinyrecorder/audio/`
- Transcript history: `~/.local/share/tinyrecorder/history.jsonl`

## Current Shape

- single-file app
- Linux-first
- tray-based workflow
- still moving fast
