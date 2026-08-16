#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "rusty-results>=1.1.1",
#   "typer>=0.15.2",
#   "httpx>=0.28.1",
# ]
# ///

"""Simulate TinyRecorder's LLM post-processing call (chat/completions).

Reads the same TOML config the app uses, then prints the request and the
response instead of building the curl command by hand.

Usage:
  uv run --script scripts/llm_debug.py "raw transcript text"
  cat some_transcript.txt | uv run --script scripts/llm_debug.py -

Mirrors tinyrecorder.py: LLMPostProcessor.postprocess() -> build_llm_url().
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final, TypeGuard

import httpx
import typer
from rusty_results.prelude import Err, Ok, Result

APP_NAME: Final = "TinyRecorder"
DEFAULT_API_BASE_URL: Final = "https://api.openai.com/v1"
DEFAULT_LLM_MODEL: Final = "gpt-4o-mini"
DEFAULT_LLM_PROMPT: Final = (
    "You are an assistant that improves speech-to-text transcripts. "
    "Sometimes transcripts have no punctuation at all, or punctuation is incorrect, or there are no "
    "sentence/paragpraph breaks, "
    "and the text is one giant blob of words."
    "But sometimes text is OK and you do not have to apply any modifications. "
    "If needed, add punctuation and sentence/paragraph breaks to make the text readable: "
    "split text into normal sentences, consider normal punctuation. "
    "Do not change, add, or remove any words. Preserve the original language and meaning. "
    "Return only the final transcript."
)

type AppResult[T] = Result[T, str]


@dataclass(frozen=True, slots=True)
class LLMSettings:
    api_key: str
    api_base_url: str
    model: str
    prompt: str


def _load_toml_object(text: str) -> object:
    return tomllib.loads(text)


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_object_iterable(value: object) -> TypeGuard[Iterable[object]]:
    return isinstance(value, Iterable)


def _coerce_object_sequence(value: object) -> list[object] | None:
    if _is_object_list(value):
        return value
    if _is_object_mapping(value):
        return None
    if not _is_object_iterable(value):
        return None
    return list(value)


def _coerce_table(value: object) -> dict[str, object] | None:
    if not _is_object_mapping(value):
        return None

    result: dict[str, object] = {}
    for raw_key, raw_item in value.items():
        result[str(raw_key)] = raw_item
    return result


def _load_json_object(text: str) -> object:
    return json.loads(text)  # pyright: ignore[reportAny]  # rationale: stdlib returns Any; re-validated below


def _normalize_api_base_url(value: object) -> str:
    text = str(value).strip() if value is not None else ""
    return text.rstrip("/") if text else DEFAULT_API_BASE_URL


def _normalize_llm_model(value: object) -> str:
    text = str(value).strip() if value is not None else ""
    return text if text else DEFAULT_LLM_MODEL


def resolve_llm_prompt(value: object) -> str:
    text = str(value).strip() if value is not None else ""
    return text if text else DEFAULT_LLM_PROMPT


def resolve_config_path() -> AppResult[Path]:
    """Resolve the config path the same way tinyrecorder.resolve_app_paths() does."""

    config_home = os.environ.get("XDG_CONFIG_HOME")
    config_dir = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    config_path = config_dir / APP_NAME.lower() / "config.toml"
    if not config_path.exists():
        return Err(f"Config not found: {config_path}")
    return Ok(config_path)


def load_llm_settings(config_path: Path) -> AppResult[LLMSettings]:
    """Read the [llm] section of the app config."""

    try:
        payload_obj = _load_toml_object(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return Err(f"Cannot read config {config_path}: {exc}")

    payload = _coerce_table(payload_obj)
    if payload is None:
        return Err(f"Invalid TOML in {config_path}")
    llm = _coerce_table(payload.get("llm", {}))
    if llm is None:
        return Err(f"Invalid [llm] section in {config_path}")

    return Ok(
        LLMSettings(
            api_key=str(llm.get("key", "")).strip(),
            api_base_url=_normalize_api_base_url(llm.get("base_url")),
            model=_normalize_llm_model(llm.get("model")),
            prompt=resolve_llm_prompt(llm.get("prompt")),
        )
    )


def can_postprocess_with_config(settings: LLMSettings) -> bool:
    """Mirror tinyrecorder.can_postprocess_with_config() for the LLM section."""

    return bool(settings.api_key.strip()) or settings.api_base_url != DEFAULT_API_BASE_URL


def build_llm_url(settings: LLMSettings) -> str:
    """Mirror tinyrecorder.build_llm_url()."""

    return f"{_normalize_api_base_url(settings.api_base_url)}/chat/completions"


def mask_api_key(key: str) -> str:
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


def format_response_body(response: httpx.Response) -> str:
    """Pretty-print the JSON body, falling back to raw text."""

    try:
        parsed = _load_json_object(response.text)
    except json.JSONDecodeError:
        return response.text
    return json.dumps(parsed, ensure_ascii=False, indent=2)


def extract_llm_answer(response: httpx.Response) -> AppResult[str]:
    """Mirror tinyrecorder.LLMPostProcessor: pull the text from choices[0].message.content."""

    try:
        payload_obj = _load_json_object(response.text)
    except json.JSONDecodeError as exc:
        return Err(f"Invalid LLM response: {exc}")
    payload = _coerce_table(payload_obj)
    if payload is None:
        return Err("Invalid LLM response shape")
    choices = _coerce_object_sequence(payload.get("choices", []))
    if choices is None or not choices:
        return Err("Invalid LLM response: missing choices")
    first_choice = _coerce_table(choices[0])
    if first_choice is None:
        return Err("Invalid LLM response: malformed choice")
    message = _coerce_table(first_choice.get("message", {}))
    if message is None:
        return Err("Invalid LLM response: missing message")
    content = str(message.get("content", "")).strip()
    if not content:
        return Err("LLM returned an empty transcript")
    return Ok(content)


def send_request(
    url: str,
    headers: dict[str, str],
    payload: dict[str, object],
) -> AppResult[list[str]]:
    """POST the chat completions request and return printable response lines."""

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        return Err(f"Network error: {exc}")

    lines = [f"-> HTTP {response.status_code}"]
    for header_name, header_value in response.headers.items():
        lines.append(f"{header_name}: {header_value}")
    lines.append("")
    lines.append(format_response_body(response))
    lines.append("")
    lines.append(">> final output:")
    answer_result = extract_llm_answer(response)
    if answer_result.is_err:
        lines.append(f"(could not extract answer: {answer_result.unwrap_err()})")
    else:
        lines.append(answer_result.unwrap())
    return Ok(lines)


def run_llm_debug(transcript: str) -> AppResult[list[str]]:
    """Print the request TinyRecorder would send and the server response."""

    if not transcript.strip():
        return Err('No transcript provided. Pass text as an argument or "-" to read stdin.')

    config_path_result = resolve_config_path()
    if config_path_result.is_err:
        return Err(config_path_result.unwrap_err())
    settings_result = load_llm_settings(config_path_result.unwrap())
    if settings_result.is_err:
        return Err(settings_result.unwrap_err())
    settings = settings_result.unwrap()

    if not can_postprocess_with_config(settings):
        return Err("Missing LLM API key. Open Settings and add one.")

    url = build_llm_url(settings)
    payload: dict[str, object] = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": settings.prompt},
            {"role": "user", "content": transcript},
        ],
        "temperature": 0,
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.api_key}",
    }

    lines = [f"POST {url}", f"Content-Type: {headers['Content-Type']}"]
    lines.append(f"Authorization: Bearer {mask_api_key(settings.api_key)}")
    lines.append(f"Body: {json.dumps(payload, ensure_ascii=False)}")
    lines.append("")

    response_lines = send_request(url, headers, payload)
    if response_lines.is_err:
        return Err(response_lines.unwrap_err())
    return Ok(lines + response_lines.unwrap())


def read_transcript(value: str) -> AppResult[str]:
    if value != "-":
        return Ok(value)
    try:
        return Ok(sys.stdin.read())
    except OSError as exc:
        return Err(f"Cannot read stdin: {exc}")


app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


@app.command()
def main(
    transcript: Annotated[str, typer.Argument(help="Raw transcript text. Use '-' to read from stdin.")],
) -> None:
    transcript_result = read_transcript(transcript)
    if transcript_result.is_err:
        typer.echo(f"Error: {transcript_result.unwrap_err()}", err=True)
        raise typer.Exit(1)

    result = run_llm_debug(transcript_result.unwrap())
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
