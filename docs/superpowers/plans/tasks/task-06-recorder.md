# Task 6: Audio Recorder (sounddevice + crash-safe recording)

**Phase:** 4 (sequential, after Task 5)
**Dependencies:** Task 1, Task 5
**Skills:** `writing-python-code`, `building-qt-apps`, `testing-python`
**Files to create:** `src/audio/recorder.py`
**Test files:** `tests/unit/test_recorder.py`, `tests/integration/test_crash_recovery.py`
**Estimated complexity:** large

---

**Goal:** Create `src/audio/recorder.py` with PCM recording, WAV conversion, RMS level computation, orphaned PCM recovery, and the `AudioRecorder` class.

> **Note:** `recover_orphaned_pcm` lives here in `recorder.py`. It uses constants for sample_rate (no extra parameter needed). Task 12 imports it as `from tinyrecorder.audio.recorder import recover_orphaned_pcm`.

#### Steps

- [ ] **6.1** Create `tests/unit/test_recorder.py` with all tests (failing):

```python
# tests/unit/test_recorder.py
"""Tests for audio recording helpers: WAV header, RMS, PCM-to-WAV conversion."""

import math
import struct
import wave
from pathlib import Path

import numpy as np
import pytest

from tinyrecorder.audio.recorder import build_wav_header, compute_rms, convert_pcm_to_wav, rms_to_db


class TestBuildWavHeader:
    """Tests for manual WAV header construction."""

    def test_header_starts_with_riff(self) -> None:
        """WAV header begins with RIFF magic bytes."""
        header = build_wav_header(data_size=1000, sample_rate=16000, channels=1, bits_per_sample=16)
        assert header[:4] == b"RIFF"

    def test_header_contains_wave_marker(self) -> None:
        """WAV header contains WAVE format marker."""
        header = build_wav_header(data_size=1000, sample_rate=16000, channels=1, bits_per_sample=16)
        assert header[8:12] == b"WAVE"

    def test_header_contains_fmt_chunk(self) -> None:
        """WAV header contains fmt subchunk."""
        header = build_wav_header(data_size=1000, sample_rate=16000, channels=1, bits_per_sample=16)
        assert b"fmt " in header

    def test_header_contains_data_chunk(self) -> None:
        """WAV header contains data subchunk marker."""
        header = build_wav_header(data_size=1000, sample_rate=16000, channels=1, bits_per_sample=16)
        assert b"data" in header

    def test_header_is_44_bytes(self) -> None:
        """Standard PCM WAV header is exactly 44 bytes."""
        header = build_wav_header(data_size=1000, sample_rate=16000, channels=1, bits_per_sample=16)
        assert len(header) == 44

    def test_header_file_size_field(self) -> None:
        """RIFF chunk size = data_size + 36."""
        data_size = 32000
        header = build_wav_header(data_size=data_size, sample_rate=16000, channels=1, bits_per_sample=16)
        riff_size = struct.unpack_from("<I", header, 4)[0]
        assert riff_size == data_size + 36

    def test_header_sample_rate(self) -> None:
        """Sample rate field is correctly encoded."""
        header = build_wav_header(data_size=1000, sample_rate=16000, channels=1, bits_per_sample=16)
        sample_rate = struct.unpack_from("<I", header, 24)[0]
        assert sample_rate == 16000

    def test_header_channels(self) -> None:
        """Channel count field is correctly encoded."""
        header = build_wav_header(data_size=1000, sample_rate=16000, channels=1, bits_per_sample=16)
        num_channels = struct.unpack_from("<H", header, 22)[0]
        assert num_channels == 1

    def test_header_bits_per_sample(self) -> None:
        """Bits per sample field is correctly encoded."""
        header = build_wav_header(data_size=1000, sample_rate=16000, channels=1, bits_per_sample=16)
        bits = struct.unpack_from("<H", header, 34)[0]
        assert bits == 16

    def test_header_data_size_field(self) -> None:
        """Data subchunk size matches the provided data_size."""
        data_size = 32000
        header = build_wav_header(data_size=data_size, sample_rate=16000, channels=1, bits_per_sample=16)
        data_chunk_size = struct.unpack_from("<I", header, 40)[0]
        assert data_chunk_size == data_size

    def test_header_audio_format_pcm(self) -> None:
        """Audio format field is 1 (PCM)."""
        header = build_wav_header(data_size=1000, sample_rate=16000, channels=1, bits_per_sample=16)
        audio_format = struct.unpack_from("<H", header, 20)[0]
        assert audio_format == 1

    def test_header_byte_rate(self) -> None:
        """Byte rate = sample_rate * channels * bits_per_sample / 8."""
        header = build_wav_header(data_size=1000, sample_rate=16000, channels=1, bits_per_sample=16)
        byte_rate = struct.unpack_from("<I", header, 28)[0]
        assert byte_rate == 16000 * 1 * 16 // 8

    def test_header_block_align(self) -> None:
        """Block align = channels * bits_per_sample / 8."""
        header = build_wav_header(data_size=1000, sample_rate=16000, channels=1, bits_per_sample=16)
        block_align = struct.unpack_from("<H", header, 32)[0]
        assert block_align == 1 * 16 // 8


class TestComputeRms:
    """Tests for RMS level calculation."""

    def test_silence_rms_is_zero(self) -> None:
        """All-zero buffer produces RMS of 0."""
        chunk = np.zeros(1600, dtype=np.int16)
        assert compute_rms(chunk) == 0.0

    def test_full_scale_dc(self) -> None:
        """Constant max-value buffer produces RMS equal to that value."""
        chunk = np.full(1600, 1000, dtype=np.int16)
        rms = compute_rms(chunk)
        assert rms == pytest.approx(1000.0, rel=1e-3)

    def test_known_sine_wave(self) -> None:
        """Sine wave RMS is approximately amplitude / sqrt(2)."""
        amplitude = 10000
        t = np.arange(1600, dtype=np.float64) / 16000.0
        sine = (amplitude * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.int16)
        rms = compute_rms(sine)
        expected = amplitude / math.sqrt(2.0)
        assert rms == pytest.approx(expected, rel=0.05)


class TestRmsToDb:
    """Tests for RMS-to-dB conversion."""

    def test_unity_rms_is_zero_db(self) -> None:
        """RMS of 1.0 maps to 0 dB."""
        assert rms_to_db(1.0) == pytest.approx(0.0, abs=0.01)

    def test_zero_rms_is_negative_infinity(self) -> None:
        """RMS of 0.0 maps to -infinity (clamped to -100 dB)."""
        result = rms_to_db(0.0)
        assert result <= -96.0

    def test_half_rms_is_about_minus_6_db(self) -> None:
        """RMS of 0.5 maps to approximately -6.02 dB."""
        assert rms_to_db(0.5) == pytest.approx(-6.02, abs=0.1)


class TestConvertPcmToWav:
    """Tests for PCM-to-WAV file conversion."""

    def test_creates_valid_wav_file(self, tmp_path: Path) -> None:
        """Converted WAV file is readable by the wave module."""
        pcm_path = tmp_path / "test.pcm"
        num_samples = 16000
        samples = np.zeros(num_samples, dtype=np.int16)
        pcm_path.write_bytes(samples.tobytes())

        wav_path = convert_pcm_to_wav(pcm_path, sample_rate=16000, channels=1, bits_per_sample=16)

        assert wav_path.suffix == ".wav"
        assert wav_path.exists()
        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            assert wf.getnframes() == num_samples

    def test_audio_data_preserved(self, tmp_path: Path) -> None:
        """Audio data in the WAV matches the original PCM bytes."""
        pcm_path = tmp_path / "test.pcm"
        t = np.arange(16000, dtype=np.float64) / 16000.0
        samples = (10000 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.int16)
        pcm_data = samples.tobytes()
        pcm_path.write_bytes(pcm_data)

        wav_path = convert_pcm_to_wav(pcm_path, sample_rate=16000, channels=1, bits_per_sample=16)

        wav_bytes = wav_path.read_bytes()
        assert wav_bytes[44:] == pcm_data

    def test_original_pcm_file_preserved(self, tmp_path: Path) -> None:
        """Original PCM file is not deleted after conversion."""
        pcm_path = tmp_path / "test.pcm"
        pcm_path.write_bytes(np.zeros(1600, dtype=np.int16).tobytes())

        convert_pcm_to_wav(pcm_path, sample_rate=16000, channels=1, bits_per_sample=16)

        assert pcm_path.exists()

    def test_truncated_pcm_odd_bytes(self, tmp_path: Path) -> None:
        """PCM file with odd byte count is handled gracefully (truncated to even)."""
        pcm_path = tmp_path / "test_odd.pcm"
        # 16001 bytes = odd, not aligned to 2-byte int16 samples
        pcm_path.write_bytes(b"\x00" * 16001)

        wav_path = convert_pcm_to_wav(pcm_path, sample_rate=16000, channels=1, bits_per_sample=16)

        assert wav_path.exists()
        assert wav_path.suffix == ".wav"
        # WAV should be readable — data is either truncated to even or padded
        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            # Should have 8000 frames (16000 bytes / 2) — last odd byte truncated or ignored
```

- [ ] **6.2** Create `tests/integration/test_crash_recovery.py` (failing):

```python
# tests/integration/test_crash_recovery.py
"""Integration tests for crash recovery of orphaned PCM files."""

import wave
from pathlib import Path

import numpy as np
import pytest

from tinyrecorder.audio.recorder import recover_orphaned_pcm


class TestCrashRecovery:
    """Tests for orphaned PCM file recovery."""

    def test_recovers_orphaned_pcm(self, tmp_path: Path) -> None:
        """Orphaned .pcm file is converted to a valid .wav file."""
        pcm_path = tmp_path / "rec_20260408_120000.pcm"
        num_samples = 16000
        samples = np.zeros(num_samples, dtype=np.int16)
        pcm_path.write_bytes(samples.tobytes())

        recovered = recover_orphaned_pcm(tmp_path)

        assert len(recovered) == 1
        wav_path = recovered[0]
        assert wav_path.suffix == ".wav"
        assert wav_path.exists()
        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000

    def test_skips_pcm_with_existing_wav(self, tmp_path: Path) -> None:
        """PCM files that already have a matching .wav are not recovered again."""
        pcm_path = tmp_path / "rec_20260408_120000.pcm"
        wav_path = tmp_path / "rec_20260408_120000.wav"
        samples = np.zeros(16000, dtype=np.int16)
        pcm_path.write_bytes(samples.tobytes())
        wav_path.write_bytes(b"RIFF" + b"\x00" * 40)

        recovered = recover_orphaned_pcm(tmp_path)

        assert len(recovered) == 0

    def test_recovers_multiple_orphaned_files(self, tmp_path: Path) -> None:
        """Multiple orphaned .pcm files are all recovered."""
        samples = np.zeros(16000, dtype=np.int16).tobytes()
        (tmp_path / "rec_20260408_120000.pcm").write_bytes(samples)
        (tmp_path / "rec_20260408_130000.pcm").write_bytes(samples)
        (tmp_path / "rec_20260408_140000.pcm").write_bytes(samples)

        recovered = recover_orphaned_pcm(tmp_path)

        assert len(recovered) == 3
        for wav_path in recovered:
            assert wav_path.suffix == ".wav"
            assert wav_path.exists()

    def test_skips_empty_pcm_file(self, tmp_path: Path) -> None:
        """Empty .pcm files are skipped (no audio data to recover)."""
        pcm_path = tmp_path / "rec_20260408_120000.pcm"
        pcm_path.write_bytes(b"")

        recovered = recover_orphaned_pcm(tmp_path)

        assert len(recovered) == 0

    def test_no_pcm_files_returns_empty(self, tmp_path: Path) -> None:
        """Returns empty list when cache dir has no .pcm files."""
        recovered = recover_orphaned_pcm(tmp_path)
        assert recovered == []
```

- [ ] **6.3** Run tests to confirm they fail:

```bash
python -m pytest tests/unit/test_recorder.py tests/integration/test_crash_recovery.py -v 2>&1 | head -60
```

- [ ] **6.4** Create `src/audio/recorder.py`:

```python
# src/audio/recorder.py
"""Audio recording with crash-safe PCM writing and WAV conversion.

Recording uses sounddevice's callback API to push audio chunks into an asyncio
queue. Raw PCM is appended to disk immediately for crash safety. On stop, a
WAV header is prepended. On crash, orphaned .pcm files can be recovered.
"""

import asyncio
import logging
import math
import struct
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Protocol

import numpy as np
from rusty_results import Err, Ok, Result

from tinyrecorder.constants import BLOCK_SIZE, CHANNELS, DTYPE, SAMPLE_RATE


class _AudioStream(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...


def build_wav_header(data_size: int, sample_rate: int, channels: int, bits_per_sample: int) -> bytes:
    """Construct a 44-byte WAV header for PCM audio data.

    Builds the canonical RIFF/WAVE header manually without using the wave module,
    so it works on raw bytes without seeking.

    Args:
        data_size: Size of the raw audio data in bytes.
        sample_rate: Sample rate in Hz (e.g. 16000).
        channels: Number of audio channels (e.g. 1 for mono).
        bits_per_sample: Bits per sample (e.g. 16).

    Returns:
        44 bytes of WAV header.
    """
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        data_size + 36,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header


def compute_rms(chunk: np.ndarray[tuple[int], np.dtype[np.int16]]) -> float:
    """Compute the root-mean-square level of an int16 audio chunk.

    Args:
        chunk: 1-D numpy array of int16 audio samples.

    Returns:
        RMS level as a float (in the same scale as the input samples).
    """
    float_data = chunk.astype(np.float64)
    mean_sq: np.floating[object] = np.mean(float_data ** 2)
    return float(np.sqrt(mean_sq))


def rms_to_db(rms: float) -> float:
    """Convert an RMS level to decibels.

    Args:
        rms: RMS level (linear scale). Must be >= 0.

    Returns:
        Level in dB. Clamped to -100.0 for zero/near-zero input.
    """
    if rms <= 0.0:
        return -100.0
    db = 20.0 * math.log10(rms)
    return max(db, -100.0)


def convert_pcm_to_wav(
    pcm_path: Path,
    sample_rate: int = SAMPLE_RATE,
    channels: int = CHANNELS,
    bits_per_sample: int = 16,
) -> Path:
    """Convert a raw PCM file to WAV by prepending a header.

    The original PCM file is preserved. The WAV file is written alongside
    with the same stem and a .wav extension.

    Args:
        pcm_path: Path to the raw PCM file.
        sample_rate: Sample rate in Hz.
        channels: Number of channels.
        bits_per_sample: Bits per sample.

    Returns:
        Path to the created WAV file.
    """
    pcm_data = pcm_path.read_bytes()
    header = build_wav_header(
        data_size=len(pcm_data),
        sample_rate=sample_rate,
        channels=channels,
        bits_per_sample=bits_per_sample,
    )
    wav_path = pcm_path.with_suffix(".wav")
    wav_path.write_bytes(header + pcm_data)
    return wav_path


def recover_orphaned_pcm(cache_dir: Path) -> list[Path]:
    """Scan for orphaned .pcm files and recover them to .wav.

    An orphaned .pcm file is one that has no matching .wav file in the same
    directory. Empty .pcm files are skipped. Uses constants SAMPLE_RATE and
    CHANNELS for the WAV header.

    Args:
        cache_dir: Directory to scan for .pcm files.

    Returns:
        List of paths to recovered .wav files.
    """
    recovered: list[Path] = []
    for pcm_path in sorted(cache_dir.glob("*.pcm")):
        wav_path = pcm_path.with_suffix(".wav")
        if wav_path.exists():
            continue
        if pcm_path.stat().st_size == 0:
            continue
        converted = convert_pcm_to_wav(pcm_path)
        recovered.append(converted)
    return recovered


class AudioRecorder:
    """Records audio from a sounddevice input stream with crash-safe PCM writing.

    Audio chunks are received via the sounddevice callback, pushed into an asyncio
    queue, and written to a .pcm file on disk. On stop, the .pcm is converted to .wav.

    Attributes:
        is_recording: Whether a recording session is currently active.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[bytes] | None = None
        self._pcm_path: Path | None = None
        self._pcm_file: BinaryIO | None = None
        self._stream: _AudioStream | None = None
        self._record_task: asyncio.Task[None] | None = None
        self._rms_callback: Callable[[float], None] | None = None
        self.is_recording: bool = False

    def start_recording(
        self,
        device_index: int | None,
        cache_dir: Path,
        rms_callback: Callable[[float], None] | None = None,
    ) -> Result[None, str]:
        """Start recording audio from the specified device.

        Opens a sounddevice InputStream that pushes chunks into an asyncio queue.
        Raw PCM is written to a timestamped .pcm file for crash safety.

        Args:
            device_index: Sounddevice device index, or None for system default.
            cache_dir: Directory to write PCM cache files.
            rms_callback: Optional callable(float) invoked with RMS level per chunk.

        Returns:
            Ok(None) on success, Err(message) on failure.
        """
        if self.is_recording:
            return Err("Already recording")

        try:
            import sounddevice as sd  # pyright: ignore[reportMissingModuleSource]

            cache_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
            self._pcm_path = cache_dir / f"rec_{timestamp}.pcm"
            self._pcm_file = open(self._pcm_path, "wb")  # noqa: SIM115
            self._queue = asyncio.Queue()
            self._rms_callback = rms_callback

            loop = asyncio.get_event_loop()

            def _callback(
                indata: np.ndarray[tuple[int, int], np.dtype[np.int16]],
                frames: int,
                time_info: object,
                status: object,
            ) -> None:
                if self._queue is not None:
                    loop.call_soon_threadsafe(self._queue.put_nowait, bytes(indata))

            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                blocksize=BLOCK_SIZE,
                device=device_index,
                callback=_callback,
            )
            self._stream.start()
            self.is_recording = True
            self._record_task = asyncio.ensure_future(self._write_loop())
            return Ok(None)
        except Exception as exc:
            self._cleanup()
            return Err(f"Failed to start recording: {exc}")

    async def _write_loop(self) -> None:
        """Consume audio chunks from the queue and write to PCM file."""
        try:
            while self.is_recording and self._queue is not None:
                try:
                    data = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                except TimeoutError:
                    continue
                if self._pcm_file is not None:
                    self._pcm_file.write(data)
                    self._pcm_file.flush()  # crash-safe: data hits OS buffer
                if self._rms_callback is not None:
                    chunk_array = np.frombuffer(data, dtype=np.int16)
                    rms = compute_rms(chunk_array)
                    try:
                        self._rms_callback(rms)
                    except Exception:
                        pass  # Don't crash recording loop on callback error
        except Exception:
            logging.getLogger(__name__).exception("Recording write loop crashed")
            self.is_recording = False

    def stop_recording(self) -> Result[Path, str]:
        """Stop recording and convert the PCM file to WAV.

        Returns:
            Ok(wav_path) on success, Err(message) on failure.
        """
        if not self.is_recording:
            return Err("Not recording")

        self.is_recording = False

        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            logging.getLogger(__name__).debug("Error stopping audio stream", exc_info=True)

        if self._record_task is not None:
            self._record_task.cancel()

        if self._pcm_file is not None:
            self._pcm_file.close()

        if self._pcm_path is None or not self._pcm_path.exists():
            self._cleanup()
            return Err("No PCM data recorded")

        try:
            wav_path = convert_pcm_to_wav(self._pcm_path)
            self._cleanup()
            return Ok(wav_path)
        except Exception as exc:
            self._cleanup()
            return Err(f"Failed to convert PCM to WAV: {exc}")

    def cancel_recording(self) -> None:
        """Cancel the current recording without converting to WAV.

        The PCM file is preserved in the cache directory for potential recovery.
        """
        self.is_recording = False

        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            logging.getLogger(__name__).debug("Error stopping audio stream during cancel", exc_info=True)

        if self._record_task is not None:
            self._record_task.cancel()

        if self._pcm_file is not None:
            self._pcm_file.close()

        self._cleanup()

    def _cleanup(self) -> None:
        """Reset internal state after recording ends."""
        self._stream = None
        self._queue = None
        self._pcm_file = None
        self._pcm_path = None
        self._record_task = None
        self._rms_callback = None
```

- [ ] **6.5** Run tests to confirm they pass:

```bash
python -m pytest tests/unit/test_recorder.py tests/integration/test_crash_recovery.py -v
```

- [ ] **6.6** Commit: `feat(audio): add crash-safe recorder with PCM-to-WAV conversion`
