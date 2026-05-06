# Task 7: Audio Processor (noise reduction + compression)

**Phase:** 3 (parallel with: Task 4, Task 5, Task 8)
**Dependencies:** Task 2, Task 2b (needs `FfmpegProvider` from platform layer), Task 3
**Skills:** `writing-python-code`, `testing-python`
**Files to create:** `src/audio/processor.py`
**Test files:** `tests/unit/test_processor.py`
**Estimated complexity:** medium

---

**Goal:** Create `src/audio/processor.py` with an `AudioProcessor` class wrapping noise reduction, MP3 compression, ffmpeg detection, and audio chunking. Free functions are kept as implementation details; the class provides the public API that Task 12 expects.

> **Note:** Task 12 imports `AudioProcessor` as a class with methods: `process_audio()`, `compress_audio()`, `chunk_audio()`, `is_ffmpeg_available()`. This task defines both the class and the underlying free functions.

> **Note (FfmpegProvider):** `AudioProcessor` should receive an `FfmpegProvider` instance (protocol from `platform/protocols.py`) instead of directly calling `shutil.which("ffmpeg")`. The `is_ffmpeg_available()` method delegates to `FfmpegProvider.is_available()`. Compression delegates to the provider for invocation. This keeps ffmpeg detection/invocation platform-agnostic in the processor code.

#### Steps

- [ ] **7.1** Create `tests/unit/test_processor.py` with all tests (failing):

```python
# tests/unit/test_processor.py
"""Tests for audio processing: noise reduction, compression, chunking."""

import struct
import wave
from pathlib import Path

import numpy as np
import pytest
from rusty_results import Err, Ok

from tinyrecorder.audio.processor import AudioProcessor, chunk_audio, compress_audio, is_ffmpeg_available, process_audio
from tinyrecorder.audio.recorder import build_wav_header
from tinyrecorder.platform.protocols import FfmpegProvider


class _StubFfmpegProvider(FfmpegProvider):
    """Stub FfmpegProvider that delegates to shutil.which for tests."""

    def is_available(self) -> bool:
        import shutil
        return shutil.which("ffmpeg") is not None


def _create_wav_file(path: Path, duration_sec: float = 1.0, sample_rate: int = 16000) -> Path:
    """Create a valid WAV file with a sine wave tone."""
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


class TestProcessAudio:
    """Tests for the process_audio function (noise reduction wrapper)."""

    def test_returns_ok_with_valid_path(self, tmp_path: Path) -> None:
        """process_audio returns Ok with a valid file path."""
        wav_path = _create_wav_file(tmp_path / "test.wav")
        result = process_audio(wav_path, noise_reduction=True)
        assert isinstance(result, Ok)
        output_path = result.unwrap()
        assert output_path.exists()
        assert output_path.suffix == ".wav"

    def test_output_is_different_file(self, tmp_path: Path) -> None:
        """When noise reduction is enabled, output is a separate file (original preserved)."""
        wav_path = _create_wav_file(tmp_path / "test.wav")
        result = process_audio(wav_path, noise_reduction=True)
        assert isinstance(result, Ok)
        output_path = result.unwrap()
        assert output_path != wav_path
        assert wav_path.exists()

    def test_output_is_readable_wav(self, tmp_path: Path) -> None:
        """Output file is a valid, readable WAV file."""
        wav_path = _create_wav_file(tmp_path / "test.wav")
        result = process_audio(wav_path, noise_reduction=True)
        assert isinstance(result, Ok)
        output_path = result.unwrap()
        with wave.open(str(output_path), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getframerate() == 16000

    def test_no_noise_reduction_returns_same_path(self, tmp_path: Path) -> None:
        """When noise reduction is disabled, returns the original path unchanged."""
        wav_path = _create_wav_file(tmp_path / "test.wav")
        result = process_audio(wav_path, noise_reduction=False)
        assert isinstance(result, Ok)
        assert result.unwrap() == wav_path

    def test_nonexistent_file_returns_err(self, tmp_path: Path) -> None:
        """Returns Err when the input file does not exist."""
        result = process_audio(tmp_path / "nonexistent.wav", noise_reduction=True)
        assert isinstance(result, Err)


class TestAudioProcessorClass:
    """Tests for the AudioProcessor class that wraps free functions."""

    def test_process_audio_delegates(self, tmp_path: Path) -> None:
        """AudioProcessor.process_audio() delegates to the free function."""
        wav_path = _create_wav_file(tmp_path / "test.wav")
        processor = AudioProcessor(_StubFfmpegProvider())
        result = processor.process_audio(wav_path, noise_reduction=False)
        assert isinstance(result, Ok)
        assert result.unwrap() == wav_path

    def test_is_ffmpeg_available_returns_bool(self) -> None:
        """AudioProcessor.is_ffmpeg_available() returns a boolean."""
        processor = AudioProcessor(_StubFfmpegProvider())
        assert isinstance(processor.is_ffmpeg_available(), bool)

    def test_chunk_audio_delegates(self, tmp_path: Path) -> None:
        """AudioProcessor.chunk_audio() delegates to the free function."""
        wav_path = _create_wav_file(tmp_path / "test.wav", duration_sec=1.0)
        processor = AudioProcessor(_StubFfmpegProvider())
        result = processor.chunk_audio(wav_path, max_size_bytes=10 * 1024 * 1024)
        assert isinstance(result, Ok)
        assert len(result.unwrap()) == 1


class TestIsFfmpegAvailable:
    """Tests for ffmpeg availability detection."""

    def test_returns_bool(self) -> None:
        """is_ffmpeg_available() returns a boolean."""
        result = is_ffmpeg_available()
        assert isinstance(result, bool)


class TestCompressAudio:
    """Tests for WAV-to-MP3 compression."""

    def test_compress_returns_mp3_path_if_ffmpeg(self, tmp_path: Path) -> None:
        """If ffmpeg is available, compress_audio returns an MP3 path."""
        if not is_ffmpeg_available():
            pytest.skip("ffmpeg not available")
        wav_path = _create_wav_file(tmp_path / "test.wav", duration_sec=2.0)
        result = compress_audio(wav_path)
        assert isinstance(result, Ok)
        mp3_path = result.unwrap()
        assert mp3_path.suffix == ".mp3"
        assert mp3_path.exists()

    def test_compress_returns_err_if_no_ffmpeg(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """If ffmpeg is not available, compress_audio returns Err."""
        monkeypatch.setattr("tinyrecorder.audio.processor.is_ffmpeg_available", lambda: False)
        wav_path = _create_wav_file(tmp_path / "test.wav")
        result = compress_audio(wav_path)
        assert isinstance(result, Err)
        assert "ffmpeg" in result.unwrap_err().lower()

    def test_compress_nonexistent_file_returns_err(self, tmp_path: Path) -> None:
        """Returns Err for non-existent file."""
        result = compress_audio(tmp_path / "nonexistent.wav")
        assert isinstance(result, Err)


class TestChunkAudio:
    """Tests for audio chunking."""

    def test_small_file_returns_single_chunk(self, tmp_path: Path) -> None:
        """File smaller than max_size returns a single-element list with original path."""
        wav_path = _create_wav_file(tmp_path / "test.wav", duration_sec=1.0)
        max_size = 10 * 1024 * 1024  # 10 MB
        result = chunk_audio(wav_path, max_size_bytes=max_size)
        assert isinstance(result, Ok)
        chunks = result.unwrap()
        assert len(chunks) == 1
        assert chunks[0] == wav_path

    def test_large_file_returns_multiple_chunks(self, tmp_path: Path) -> None:
        """File larger than max_size is split into multiple valid WAV chunks."""
        wav_path = _create_wav_file(tmp_path / "test.wav", duration_sec=5.0)
        file_size = wav_path.stat().st_size
        max_size = file_size // 3
        result = chunk_audio(wav_path, max_size_bytes=max_size)
        assert isinstance(result, Ok)
        chunks = result.unwrap()
        assert len(chunks) >= 2
        for chunk_path in chunks:
            assert chunk_path.exists()
            assert chunk_path.suffix == ".wav"
            with wave.open(str(chunk_path), "rb") as wf:
                assert wf.getnchannels() == 1
                assert wf.getframerate() == 16000

    def test_chunks_contain_all_audio_data(self, tmp_path: Path) -> None:
        """Total audio samples across chunks equals the original file's sample count."""
        wav_path = _create_wav_file(tmp_path / "test.wav", duration_sec=3.0)
        file_size = wav_path.stat().st_size
        max_size = file_size // 2
        result = chunk_audio(wav_path, max_size_bytes=max_size)
        assert isinstance(result, Ok)
        chunks = result.unwrap()
        total_frames = 0
        for chunk_path in chunks:
            with wave.open(str(chunk_path), "rb") as wf:
                total_frames += wf.getnframes()
        with wave.open(str(wav_path), "rb") as wf:
            original_frames = wf.getnframes()
        assert total_frames == original_frames

    def test_nonexistent_file_returns_err(self, tmp_path: Path) -> None:
        """Returns Err for non-existent file."""
        result = chunk_audio(tmp_path / "nonexistent.wav", max_size_bytes=1024)
        assert isinstance(result, Err)
```

```python


class TestPrepareForUpload:
    """Tests for the prepare_for_upload orchestration method."""

    def test_small_file_no_compression(self, tmp_path: Path) -> None:
        """Small file passes through without compression or chunking."""
        wav_path = _create_wav_file(tmp_path / "test.wav", duration_sec=1.0)
        processor = AudioProcessor(_StubFfmpegProvider())
        result = processor.prepare_for_upload(wav_path, noise_reduction=False)
        assert isinstance(result, Ok)
        assert result.unwrap() == wav_path

    def test_noise_reduction_applied_when_enabled(self, tmp_path: Path) -> None:
        """When noise_reduction=True, output is a different file."""
        wav_path = _create_wav_file(tmp_path / "test.wav", duration_sec=1.0)
        processor = AudioProcessor(_StubFfmpegProvider())
        result = processor.prepare_for_upload(wav_path, noise_reduction=True)
        assert isinstance(result, Ok)
        output = result.unwrap()
        assert output != wav_path
        assert output.exists()
```

- [ ] **7.2** Run tests to confirm they fail:

```bash
python -m pytest tests/unit/test_processor.py -v 2>&1 | head -40
```

- [ ] **7.3** Create `src/audio/processor.py`:

```python
# src/audio/processor.py
"""Audio processing: noise reduction, MP3 compression, and chunking.

Noise reduction uses noisereduce (pure pip). Compression uses pydub + ffmpeg
(optional, graceful degradation). Chunking splits large files for API limits.

Both free functions and an AudioProcessor class are provided. The class
delegates to the free functions and is used by Task 12's ApplicationController.
"""

from __future__ import annotations

import shutil
import wave
from pathlib import Path

import numpy as np
from rusty_results import Err, Ok, Result

from tinyrecorder.audio.recorder import build_wav_header
from tinyrecorder.platform.protocols import FfmpegProvider


def _apply_noise_reduction(
    audio_data: np.ndarray[tuple[int], np.dtype[np.int16]],
    sample_rate: int,
) -> np.ndarray[tuple[int], np.dtype[np.int16]]:
    """Apply noise reduction via noisereduce library.

    This is the sole contact point with the noisereduce library.

    Args:
        audio_data: 1-D int16 audio samples.
        sample_rate: Sample rate in Hz.

    Returns:
        Noise-reduced audio as int16 array.
    """
    # NOTE: noisereduce does not expose __version__. To check version,
    # use importlib.metadata.version('noisereduce'). Do not attempt nr.__version__.
    import noisereduce as nr  # pyright: ignore[reportMissingModuleSource]

    float_data = audio_data.astype(np.float64)
    reduced: np.ndarray[tuple[int], np.dtype[np.float64]] = nr.reduce_noise(  # pyright: ignore[reportUnknownMemberType]
        y=float_data,
        sr=sample_rate,
        stationary=False,
    )
    clipped = np.clip(reduced, -32768, 32767)
    return clipped.astype(np.int16)


def process_audio(wav_path: Path, noise_reduction: bool) -> Result[Path, str]:
    """Apply noise reduction to a WAV file if enabled.

    The original file is never modified. A new file is created with the
    suffix "_nr.wav" in the same directory.

    Args:
        wav_path: Path to the input WAV file.
        noise_reduction: Whether to apply noise reduction.

    Returns:
        Ok(path) to the processed file (or original if noise_reduction=False).
        Err(message) on failure.
    """
    if not noise_reduction:
        return Ok(wav_path)

    if not wav_path.exists():
        return Err(f"File not found: {wav_path}")

    try:
        with wave.open(str(wav_path), "rb") as wf:
            sample_rate = wf.getframerate()
            num_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            raw_data = wf.readframes(wf.getnframes())

        audio_array = np.frombuffer(raw_data, dtype=np.int16)
        reduced = _apply_noise_reduction(audio_array, sample_rate)

        output_path = wav_path.with_stem(wav_path.stem + "_nr")
        reduced_bytes = reduced.tobytes()
        header = build_wav_header(
            data_size=len(reduced_bytes),
            sample_rate=sample_rate,
            channels=num_channels,
            bits_per_sample=sample_width * 8,
        )
        output_path.write_bytes(header + reduced_bytes)
        return Ok(output_path)
    except Exception as exc:
        return Err(f"Noise reduction failed: {exc}")


def is_ffmpeg_available(ffmpeg_provider: FfmpegProvider) -> bool:
    """Check whether ffmpeg is available via the platform provider.

    Args:
        ffmpeg_provider: Platform-specific ffmpeg provider.

    Returns:
        True if ffmpeg executable is found, False otherwise.
    """
    return ffmpeg_provider.is_available()


def compress_audio(wav_path: Path, ffmpeg_provider: FfmpegProvider) -> Result[Path, str]:
    """Compress a WAV file to MP3 using pydub (requires ffmpeg).

    Output is mono 16kHz 64kbps MP3, written alongside the input file.

    Args:
        wav_path: Path to the input WAV file.
        ffmpeg_provider: Platform-specific ffmpeg provider for availability detection.

    Returns:
        Ok(mp3_path) on success, Err(message) on failure.
    """
    if not wav_path.exists():
        return Err(f"File not found: {wav_path}")

    if not is_ffmpeg_available(ffmpeg_provider):
        return Err("ffmpeg is not available — cannot compress audio")

    try:
        from pydub import AudioSegment  # pyright: ignore[reportMissingModuleSource]

        audio: object = AudioSegment.from_wav(str(wav_path))  # pyright: ignore[reportUnknownMemberType]
        mp3_path = wav_path.with_suffix(".mp3")
        if hasattr(audio, "export"):
            audio.export(  # pyright: ignore[reportAttributeAccessIssue]
                str(mp3_path),
                format="mp3",
                bitrate="64k",
                parameters=["-ac", "1", "-ar", "16000"],
            )
        else:
            return Err("pydub AudioSegment missing export method")
        return Ok(mp3_path)
    except Exception as exc:
        return Err(f"Audio compression failed: {exc}")


def chunk_audio(wav_path: Path, max_size_bytes: int) -> Result[list[Path], str]:
    """Split a WAV file into chunks that fit within a size limit.

    Each chunk is a valid WAV file with correct headers. If the file is already
    within the size limit, returns a single-element list with the original path.

    Args:
        wav_path: Path to the input WAV file.
        max_size_bytes: Maximum size per chunk in bytes (including headers).

    Returns:
        Ok(list of chunk paths) on success, Err(message) on failure.
    """
    if not wav_path.exists():
        return Err(f"File not found: {wav_path}")

    try:
        file_size = wav_path.stat().st_size
        if file_size <= max_size_bytes:
            return Ok([wav_path])

        with wave.open(str(wav_path), "rb") as wf:
            sample_rate = wf.getframerate()
            num_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            total_frames = wf.getnframes()
            all_data = wf.readframes(total_frames)

        wav_header_size = 44
        max_data_per_chunk = max_size_bytes - wav_header_size
        bytes_per_frame = num_channels * sample_width
        frames_per_chunk = max_data_per_chunk // bytes_per_frame

        if frames_per_chunk <= 0:
            return Err("max_size_bytes is too small to fit even one frame")

        chunks: list[Path] = []
        offset = 0
        chunk_index = 0

        while offset < total_frames:
            end = min(offset + frames_per_chunk, total_frames)
            chunk_frames = end - offset
            data_start = offset * bytes_per_frame
            data_end = end * bytes_per_frame
            chunk_data = all_data[data_start:data_end]

            chunk_path = wav_path.with_stem(f"{wav_path.stem}_chunk{chunk_index:03d}")
            header = build_wav_header(
                data_size=len(chunk_data),
                sample_rate=sample_rate,
                channels=num_channels,
                bits_per_sample=sample_width * 8,
            )
            chunk_path.write_bytes(header + chunk_data)
            chunks.append(chunk_path)

            offset = end
            chunk_index += 1

        return Ok(chunks)
    except Exception as exc:
        return Err(f"Audio chunking failed: {exc}")


# Upload size thresholds for API limits
MAX_UPLOAD_SIZE_BYTES: int = 24 * 1024 * 1024  # 24 MB hard limit
COMPRESS_THRESHOLD_BYTES: int = 20 * 1024 * 1024  # 20 MB trigger compression


class AudioProcessor:
    """High-level audio processor wrapping free functions.

    Provides the class-based API expected by Task 12's ApplicationController.
    Methods delegate to the module-level free functions.

    Args:
        ffmpeg_provider: Platform-specific ffmpeg provider for availability detection
            and invocation. Obtained via get_ffmpeg_provider() from the platform layer.
    """

    def __init__(self, ffmpeg_provider: FfmpegProvider) -> None:
        self._ffmpeg_provider = ffmpeg_provider

    def process_audio(self, wav_path: Path, noise_reduction: bool) -> Result[Path, str]:
        """Apply noise reduction to a WAV file if enabled.

        Delegates to the module-level process_audio() function.
        """
        return process_audio(wav_path, noise_reduction)

    def compress_audio(self, wav_path: Path) -> Result[Path, str]:
        """Compress a WAV file to MP3.

        Delegates to the module-level compress_audio() function.
        """
        return compress_audio(wav_path, self._ffmpeg_provider)

    def chunk_audio(self, wav_path: Path, max_size_bytes: int) -> Result[list[Path], str]:
        """Split a WAV file into chunks.

        Delegates to the module-level chunk_audio() function.
        """
        return chunk_audio(wav_path, max_size_bytes)

    def is_ffmpeg_available(self) -> bool:
        """Check whether ffmpeg is available.

        Delegates to the FfmpegProvider instance.
        """
        return self._ffmpeg_provider.is_available()

    def prepare_for_upload(self, wav_path: Path, noise_reduction: bool) -> Result[Path, str]:
        """Orchestrate the full processing pipeline for API upload.

        Single entry point that Task 12 calls. Steps:
        1. Apply noise reduction if enabled.
        2. Compress to MP3 if file > COMPRESS_THRESHOLD_BYTES and ffmpeg available.
        3. Chunk if file > MAX_UPLOAD_SIZE_BYTES (returns first chunk path;
           caller should handle multi-chunk transcription separately).

        Args:
            wav_path: Path to the input WAV file.
            noise_reduction: Whether to apply noise reduction.

        Returns:
            Ok(path) to the file ready for upload, Err(message) on failure.
        """
        # Step 1: noise reduction
        result = self.process_audio(wav_path, noise_reduction)
        if result.is_err:
            return result
        current_path = result.unwrap()

        # Step 2: compress if over threshold and ffmpeg available
        if current_path.stat().st_size > COMPRESS_THRESHOLD_BYTES and self.is_ffmpeg_available():
            compress_result = self.compress_audio(current_path)
            if compress_result.is_ok:
                current_path = compress_result.unwrap()

        # Step 3: chunk if still over hard limit
        if current_path.stat().st_size > MAX_UPLOAD_SIZE_BYTES:
            chunk_result = self.chunk_audio(current_path, max_size_bytes=MAX_UPLOAD_SIZE_BYTES)
            if chunk_result.is_err:
                return Err(chunk_result.unwrap_err())
            chunks = chunk_result.unwrap()
            current_path = chunks[0]  # caller handles multi-chunk via separate logic

        return Ok(current_path)
```

- [ ] **7.4** Run tests to confirm they pass:

```bash
python -m pytest tests/unit/test_processor.py -v
```

- [ ] **7.5** Commit: `feat(audio): add AudioProcessor with noise reduction, compression, and chunking`
