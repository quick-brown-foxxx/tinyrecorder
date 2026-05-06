# Task 8: Transcription Provider (protocol + OpenAI)

**Phase:** 3 (parallel with: Task 4, Task 5, Task 7)
**Dependencies:** Task 2, Task 3
**Skills:** `writing-python-code`, `testing-python`
**Files to create:** `src/transcription/__init__.py`, `src/transcription/provider.py`, `src/transcription/openai_provider.py`
**Test files:** `tests/integration/test_openai_provider.py`
**Estimated complexity:** medium

---

**Goal:** Create the transcription protocol and OpenAI provider with retry logic, cost estimation, and integration tests using a real HTTP mock server.

> **Note:** Uses the openai Python SDK (not raw httpx) for built-in retry, multipart upload, and type safety.

#### Steps

- [ ] **8.1** Create `tests/integration/test_openai_provider.py` with all tests (failing):

```python
# tests/integration/test_openai_provider.py
"""Integration tests for the OpenAI transcription provider.

Uses pytest-httpserver to create a real HTTP server mimicking the OpenAI API.
No unittest.mock.patch is used on the openai SDK.
"""

import json
import wave
from pathlib import Path

import numpy as np
import pytest
from pytest_httpserver import HTTPServer
from rusty_results import Err, Ok
from werkzeug.wrappers import Request, Response

from tinyrecorder.audio.recorder import build_wav_header
from tinyrecorder.transcription.openai_provider import OpenAIProvider, estimate_cost
from tinyrecorder.transcription.provider import TranscriptionResult


def _create_wav_file(path: Path, duration_sec: float = 1.0) -> Path:
    """Create a valid WAV file for testing."""
    sample_rate = 16000
    num_samples = int(sample_rate * duration_sec)
    t = np.arange(num_samples, dtype=np.float64) / sample_rate
    samples = (10000 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.int16)
    pcm_data = samples.tobytes()
    header = build_wav_header(
        data_size=len(pcm_data),
        sample_rate=sample_rate,
        channels=1,
        bits_per_sample=16,
    )
    path.write_bytes(header + pcm_data)
    return path


class TestTranscriptionProviderSuccess:
    """Tests for successful transcription flow."""

    @pytest.mark.asyncio
    async def test_transcription_returns_ok(self, httpserver: HTTPServer, tmp_path: Path) -> None:
        """Provider returns Ok(TranscriptionResult) on successful API response."""
        response_body = json.dumps({
            "text": "Hello world",
            "task": "transcribe",
            "language": "en",
            "duration": 5.0,
        })
        httpserver.expect_request(
            "/v1/audio/transcriptions",
            method="POST",
        ).respond_with_data(response_body, content_type="application/json")

        provider = OpenAIProvider(
            api_key="sk-test-key-12345",
            base_url=httpserver.url_for("/v1"),
        )

        wav_path = _create_wav_file(tmp_path / "test.wav", duration_sec=5.0)
        result = await provider.transcribe(
            audio_path=wav_path,
            language="en",
            model="gpt-4o-mini-transcribe",
        )

        assert isinstance(result, Ok)
        transcription = result.unwrap()
        assert transcription.text == "Hello world"
        assert transcription.language == "en"
        assert transcription.duration_sec == 5.0
        assert transcription.model == "gpt-4o-mini-transcribe"
        assert transcription.cost_estimate > 0.0

    @pytest.mark.asyncio
    async def test_request_contains_audio_file(self, httpserver: HTTPServer, tmp_path: Path) -> None:
        """Provider sends the audio file as multipart form data."""
        received_requests: list[Request] = []

        def _handler(request: Request) -> Response:
            received_requests.append(request)
            body = json.dumps({
                "text": "test",
                "task": "transcribe",
                "language": "en",
                "duration": 1.0,
            })
            return Response(body, content_type="application/json")

        httpserver.expect_request(
            "/v1/audio/transcriptions",
            method="POST",
        ).respond_with_handler(_handler)

        provider = OpenAIProvider(
            api_key="sk-test-key-12345",
            base_url=httpserver.url_for("/v1"),
        )

        wav_path = _create_wav_file(tmp_path / "test.wav")
        await provider.transcribe(audio_path=wav_path, language="en", model="whisper-1")

        assert len(received_requests) == 1
        req = received_requests[0]
        assert req.content_type is not None
        assert "multipart/form-data" in req.content_type

    @pytest.mark.asyncio
    async def test_auto_language_omits_parameter(self, httpserver: HTTPServer, tmp_path: Path) -> None:
        """When language is 'auto', the language parameter is omitted from the request."""
        received_requests: list[Request] = []

        def _handler(request: Request) -> Response:
            received_requests.append(request)
            body = json.dumps({
                "text": "Bonjour",
                "task": "transcribe",
                "language": "fr",
                "duration": 1.0,
            })
            return Response(body, content_type="application/json")

        httpserver.expect_request(
            "/v1/audio/transcriptions",
            method="POST",
        ).respond_with_handler(_handler)

        provider = OpenAIProvider(
            api_key="sk-test-key-12345",
            base_url=httpserver.url_for("/v1"),
        )

        wav_path = _create_wav_file(tmp_path / "test.wav")
        result = await provider.transcribe(audio_path=wav_path, language="auto", model="whisper-1")
        assert isinstance(result, Ok)

        req = received_requests[0]
        form_data = req.form
        assert "language" not in form_data


class TestTranscriptionProviderRetry:
    """Tests for retry behavior on server errors."""

    @pytest.mark.asyncio
    async def test_retries_on_500_then_succeeds(self, httpserver: HTTPServer, tmp_path: Path) -> None:
        """Provider retries on 500 and succeeds on subsequent 200."""
        call_count: list[int] = [0]

        def _handler(request: Request) -> Response:
            call_count[0] += 1
            if call_count[0] <= 2:
                return Response(
                    json.dumps({"error": {"message": "Internal server error"}}),
                    status=500,
                    content_type="application/json",
                )
            body = json.dumps({
                "text": "Recovered",
                "task": "transcribe",
                "language": "en",
                "duration": 1.0,
            })
            return Response(body, content_type="application/json")

        httpserver.expect_request(
            "/v1/audio/transcriptions",
            method="POST",
        ).respond_with_handler(_handler)

        provider = OpenAIProvider(
            api_key="sk-test-key-12345",
            base_url=httpserver.url_for("/v1"),
            max_retries=3,
            initial_backoff_sec=0.01,
        )

        wav_path = _create_wav_file(tmp_path / "test.wav")
        result = await provider.transcribe(audio_path=wav_path, language="en", model="whisper-1")

        assert isinstance(result, Ok)
        assert result.unwrap().text == "Recovered"
        assert call_count[0] == 3

    @pytest.mark.asyncio
    async def test_exhausts_retries_on_persistent_500(self, httpserver: HTTPServer, tmp_path: Path) -> None:
        """Provider returns Err after exhausting all retry attempts on 500."""
        call_count: list[int] = [0]

        def _handler(request: Request) -> Response:
            call_count[0] += 1
            return Response(
                json.dumps({"error": {"message": "Internal server error"}}),
                status=500,
                content_type="application/json",
            )

        httpserver.expect_request(
            "/v1/audio/transcriptions",
            method="POST",
        ).respond_with_handler(_handler)

        provider = OpenAIProvider(
            api_key="sk-test-key-12345",
            base_url=httpserver.url_for("/v1"),
            max_retries=3,
            initial_backoff_sec=0.01,
        )

        wav_path = _create_wav_file(tmp_path / "test.wav")
        result = await provider.transcribe(audio_path=wav_path, language="en", model="whisper-1")

        assert isinstance(result, Err)
        assert call_count[0] == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_400(self, httpserver: HTTPServer, tmp_path: Path) -> None:
        """Provider does NOT retry on 400 (bad request)."""
        call_count: list[int] = [0]

        def _handler(request: Request) -> Response:
            call_count[0] += 1
            return Response(
                json.dumps({"error": {"message": "Bad request"}}),
                status=400,
                content_type="application/json",
            )

        httpserver.expect_request(
            "/v1/audio/transcriptions",
            method="POST",
        ).respond_with_handler(_handler)

        provider = OpenAIProvider(
            api_key="sk-test-key-12345",
            base_url=httpserver.url_for("/v1"),
            max_retries=3,
            initial_backoff_sec=0.01,
        )

        wav_path = _create_wav_file(tmp_path / "test.wav")
        result = await provider.transcribe(audio_path=wav_path, language="en", model="whisper-1")

        assert isinstance(result, Err)
        assert call_count[0] == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_401(self, httpserver: HTTPServer, tmp_path: Path) -> None:
        """Provider does NOT retry on 401 (unauthorized)."""
        call_count: list[int] = [0]

        def _handler(request: Request) -> Response:
            call_count[0] += 1
            return Response(
                json.dumps({"error": {"message": "Invalid API key"}}),
                status=401,
                content_type="application/json",
            )

        httpserver.expect_request(
            "/v1/audio/transcriptions",
            method="POST",
        ).respond_with_handler(_handler)

        provider = OpenAIProvider(
            api_key="sk-bad-key",
            base_url=httpserver.url_for("/v1"),
            max_retries=3,
            initial_backoff_sec=0.01,
        )

        wav_path = _create_wav_file(tmp_path / "test.wav")
        result = await provider.transcribe(audio_path=wav_path, language="en", model="whisper-1")

        assert isinstance(result, Err)
        assert "api key" in result.unwrap_err().lower() or "401" in result.unwrap_err()
        assert call_count[0] == 1


class TestCostEstimation:
    """Tests for transcription cost estimation."""

    def test_whisper_cost_60_seconds(self) -> None:
        """whisper-1 costs $0.006 per minute: 60s = $0.006."""
        cost = estimate_cost(model="whisper-1", duration_sec=60.0)
        assert cost == pytest.approx(0.006, abs=0.0001)

    def test_whisper_cost_30_seconds(self) -> None:
        """whisper-1: 30s = $0.003."""
        cost = estimate_cost(model="whisper-1", duration_sec=30.0)
        assert cost == pytest.approx(0.003, abs=0.0001)

    def test_whisper_cost_zero_seconds(self) -> None:
        """whisper-1: 0s = $0.0."""
        cost = estimate_cost(model="whisper-1", duration_sec=0.0)
        assert cost == 0.0

    def test_gpt4o_mini_transcribe_cost(self) -> None:
        """gpt-4o-mini-transcribe costs $0.003/min: 60s = $0.003."""
        cost = estimate_cost(model="gpt-4o-mini-transcribe", duration_sec=60.0)
        assert cost == pytest.approx(0.003, abs=0.0001)

    def test_gpt4o_transcribe_cost(self) -> None:
        """gpt-4o-transcribe costs $0.006/min: 60s = $0.006."""
        cost = estimate_cost(model="gpt-4o-transcribe", duration_sec=60.0)
        assert cost == pytest.approx(0.006, abs=0.0001)

    def test_gpt4o_mini_is_half_gpt4o(self) -> None:
        """gpt-4o-mini-transcribe costs half of gpt-4o-transcribe for same duration."""
        duration = 120.0
        cost_mini = estimate_cost(model="gpt-4o-mini-transcribe", duration_sec=duration)
        cost_full = estimate_cost(model="gpt-4o-transcribe", duration_sec=duration)
        assert cost_mini == pytest.approx(cost_full / 2.0, rel=0.01)


class TestTranscriptionResponseFormat:
    """Tests for model-dependent response_format selection."""

    @pytest.mark.asyncio
    async def test_transcription_uses_correct_response_format_per_model(
        self, httpserver: HTTPServer, tmp_path: Path
    ) -> None:
        """whisper-1 sends verbose_json; gpt-4o-mini-transcribe sends json."""
        received_formats: dict[str, str] = {}

        def _handler(request: Request) -> Response:
            model = request.form.get("model", "")
            fmt = request.form.get("response_format", "")
            received_formats[model] = fmt
            body = json.dumps({
                "text": "test",
                "task": "transcribe",
                "language": "en",
                "duration": 1.0,
            })
            return Response(body, content_type="application/json")

        httpserver.expect_request(
            "/v1/audio/transcriptions",
            method="POST",
        ).respond_with_handler(_handler)

        provider = OpenAIProvider(
            api_key="sk-test-key-12345",
            base_url=httpserver.url_for("/v1"),
        )

        wav_path = _create_wav_file(tmp_path / "test.wav")

        await provider.transcribe(audio_path=wav_path, language="en", model="whisper-1")
        await provider.transcribe(audio_path=wav_path, language="en", model="gpt-4o-mini-transcribe")

        assert received_formats["whisper-1"] == "verbose_json"
        assert received_formats["gpt-4o-mini-transcribe"] == "json"


class TestProviderProtocol:
    """Tests that OpenAIProvider fulfills the TranscriptionProvider protocol."""

    def test_has_transcribe_method(self) -> None:
        """OpenAIProvider has a transcribe method."""
        provider = OpenAIProvider(api_key="sk-test", base_url="http://localhost:9999/v1")
        assert hasattr(provider, "transcribe")
        assert callable(provider.transcribe)

    def test_has_supported_models(self) -> None:
        """OpenAIProvider has supported_models method returning non-empty list."""
        provider = OpenAIProvider(api_key="sk-test", base_url="http://localhost:9999/v1")
        models = provider.supported_models()
        assert isinstance(models, list)
        assert len(models) > 0
        assert "whisper-1" in models

    def test_has_supported_languages(self) -> None:
        """OpenAIProvider has supported_languages method returning non-empty list."""
        provider = OpenAIProvider(api_key="sk-test", base_url="http://localhost:9999/v1")
        languages = provider.supported_languages()
        assert isinstance(languages, list)
        assert "en" in languages
        assert "auto" in languages
```

- [ ] **8.2** Run tests to confirm they fail:

```bash
python -m pytest tests/integration/test_openai_provider.py -v 2>&1 | head -40
```

- [ ] **8.3** Create `src/transcription/__init__.py`:

```python
# src/transcription/__init__.py
"""Transcription providers for speech-to-text."""
```

- [ ] **8.4** Create `src/transcription/provider.py`:

```python
# src/transcription/provider.py
"""Transcription provider protocol and shared data types."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from rusty_results import Result


@dataclass(frozen=True)
class TranscriptionResult:
    """Result of a successful transcription.

    Attributes:
        text: The transcribed text.
        language: Detected or specified language code (ISO 639-1).
        duration_sec: Audio duration in seconds.
        model: Model identifier used for transcription.
        cost_estimate: Estimated cost in USD.
    """

    text: str
    language: str
    duration_sec: float
    model: str
    cost_estimate: float


@runtime_checkable
class TranscriptionProvider(Protocol):
    """Protocol for any speech-to-text provider."""

    async def transcribe(
        self,
        audio_path: Path,
        language: str,
        model: str,
    ) -> Result[TranscriptionResult, str]:
        """Transcribe an audio file.

        Args:
            audio_path: Path to the audio file (WAV or MP3).
            language: Language code ("auto", "en", "ru") -- "auto" for auto-detection.
            model: Model identifier (e.g. "whisper-1", "gpt-4o-mini-transcribe").

        Returns:
            Ok(TranscriptionResult) on success, Err(message) on failure.
        """
        ...

    def supported_models(self) -> list[str]:
        """Return the list of supported model identifiers."""
        ...

    def supported_languages(self) -> list[str]:
        """Return the list of supported language codes."""
        ...
```

- [ ] **8.5** Create `src/transcription/openai_provider.py`:

> **Note (prototype finding):** The `create()` method returns `Transcription | TranscriptionVerbose | TranscriptionDiarized | str | AsyncStream[...]`. For basedpyright strict, we need isinstance narrowing on the return type. The `json` response format (used by gpt-4o models) does NOT include `duration` or `language` fields. We estimate duration from the WAV file header. Language falls back to the user's selected language or 'unknown' for auto-detect.

```python
# src/transcription/openai_provider.py
"""OpenAI transcription provider using the Audio Transcriptions API.

Supports whisper-1, gpt-4o-transcribe, and gpt-4o-mini-transcribe models.
Uses the openai Python SDK (not raw httpx) for built-in retry, multipart upload,
and type safety.
"""

from pathlib import Path

import openai
from openai.types.audio.transcription import Transcription
from openai.types.audio.transcription_verbose import TranscriptionVerbose
from rusty_results import Err, Ok, Result

from tinyrecorder.constants import SUPPORTED_LANGUAGES, SUPPORTED_MODELS
from tinyrecorder.transcription.provider import TranscriptionResult

# Cost per minute in USD for each model
_COST_PER_MINUTE: dict[str, float] = {
    "whisper-1": 0.006,
    "gpt-4o-transcribe": 0.006,
    "gpt-4o-mini-transcribe": 0.003,
}


def estimate_cost(model: str, duration_sec: float) -> float:
    """Estimate the transcription cost in USD.

    Args:
        model: Model identifier.
        duration_sec: Audio duration in seconds.

    Returns:
        Estimated cost in USD. Returns 0.0 for unknown models.
    """
    rate = _COST_PER_MINUTE.get(model, 0.0)
    return rate * duration_sec / 60.0


def _estimate_duration_from_file(audio_path: Path) -> float:
    """Estimate audio duration from WAV file header when API doesn't return it."""
    try:
        import wave
        with wave.open(str(audio_path), "rb") as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 0.0


class OpenAIProvider:
    """Transcription provider using the OpenAI Audio API.

    Uses the openai AsyncOpenAI SDK for built-in retry, multipart upload,
    and type safety. The base_url parameter allows pointing to a mock server
    in tests.

    Args:
        api_key: OpenAI API key.
        base_url: Base URL for the API (default: "https://api.openai.com/v1").
        max_retries: Maximum number of retry attempts for retryable errors (default: 3).
        initial_backoff_sec: Unused (kept for API compat); SDK handles backoff internally.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        max_retries: int = 3,
        initial_backoff_sec: float = 1.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=max_retries,
        )

    async def transcribe(
        self,
        audio_path: Path,
        language: str,
        model: str,
    ) -> Result[TranscriptionResult, str]:
        """Transcribe an audio file via the OpenAI Audio Transcriptions API.

        The SDK handles retry with exponential backoff for 429/500/502/503 errors.
        400/401/403/413 errors are caught and returned as Err immediately.

        Args:
            audio_path: Path to the audio file.
            language: Language code ("auto" omits the parameter for auto-detection).
            model: Model identifier.

        Returns:
            Ok(TranscriptionResult) on success, Err(message) on failure.
        """
        if not audio_path.exists():
            return Err(f"Audio file not found: {audio_path}")

        if model not in SUPPORTED_MODELS:
            return Err(f"Unsupported model: {model}. Supported: {', '.join(SUPPORTED_MODELS)}")
        if language not in SUPPORTED_LANGUAGES:
            return Err(f"Unsupported language: {language}. Supported: {', '.join(SUPPORTED_LANGUAGES)}")

        # whisper-1 supports verbose_json (returns duration, language);
        # gpt-4o-transcribe and gpt-4o-mini-transcribe only support json/text.
        response_format = "verbose_json" if model == "whisper-1" else "json"

        try:
            with open(audio_path, "rb") as audio_file:
                kwargs: dict[str, object] = {
                    "model": model,
                    "file": audio_file,
                    "response_format": response_format,
                }
                if language != "auto":
                    kwargs["language"] = language

                response = await self._client.audio.transcriptions.create(**kwargs)  # type: ignore[arg-type]  # rationale: kwargs dict has dynamic keys from conditional language param

            return self._parse_response(response, model, audio_path, language)

        except openai.BadRequestError as exc:
            return Err(f"Bad request (400): {exc.message}")
        except openai.AuthenticationError as exc:
            return Err(f"Invalid API key (401): {exc.message}")
        except openai.PermissionDeniedError as exc:
            return Err(f"Permission denied (403): {exc.message}")
        except openai.APIStatusError as exc:
            return Err(f"API error ({exc.status_code}): {exc.message}")
        except openai.APIConnectionError as exc:
            return Err(f"Connection error: {exc}")
        except Exception as exc:
            return Err(f"Unexpected error: {exc}")

    def _parse_response(
        self, response: object, model: str, audio_path: Path, language: str,
    ) -> Result[TranscriptionResult, str]:
        """Parse a successful API response into a TranscriptionResult.

        Uses isinstance narrowing to handle the wide union return type from
        the OpenAI SDK: Transcription | TranscriptionVerbose | str | ...
        """
        try:
            # Narrow the wide return type for strict typing
            if isinstance(response, TranscriptionVerbose):
                # whisper-1 with verbose_json: has duration, language, segments
                return Ok(TranscriptionResult(
                    text=response.text,
                    language=response.language,
                    duration_sec=response.duration,
                    model=model,
                    cost_estimate=estimate_cost(model, response.duration),
                ))
            elif isinstance(response, Transcription):
                # gpt-4o models with json: text only, no duration/language
                duration_estimate = _estimate_duration_from_file(audio_path)
                return Ok(TranscriptionResult(
                    text=response.text,
                    language=language if language != "auto" else "unknown",
                    duration_sec=duration_estimate,
                    model=model,
                    cost_estimate=estimate_cost(model, duration_estimate),
                ))
            elif isinstance(response, str):
                # text format: plain string
                duration_estimate = _estimate_duration_from_file(audio_path)
                return Ok(TranscriptionResult(
                    text=response,
                    language=language if language != "auto" else "unknown",
                    duration_sec=duration_estimate,
                    model=model,
                    cost_estimate=estimate_cost(model, duration_estimate),
                ))
            else:
                return Err(f"Unexpected response type: {type(response).__name__}")
        except Exception as exc:
            return Err(f"Failed to parse API response: {exc}")

    def supported_models(self) -> list[str]:
        """Return the list of supported model identifiers."""
        return list(SUPPORTED_MODELS)

    def supported_languages(self) -> list[str]:
        """Return the list of supported language codes."""
        return list(SUPPORTED_LANGUAGES)
```

- [ ] **8.6** Run tests to confirm they pass:

```bash
python -m pytest tests/integration/test_openai_provider.py -v
```

- [ ] **8.7** Commit: `feat(transcription): add provider protocol and OpenAI implementation`
