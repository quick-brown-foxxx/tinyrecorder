# Task 4: History (JSONL)

**Phase:** 3 (parallel with: Task 5, Task 7, Task 8)
**Dependencies:** Task 2
**Skills:** `writing-python-code`, `testing-python`
**Files to create:** `src/history.py`
**Test files:** `tests/unit/test_history.py`
**Estimated complexity:** small

---

**Goal:** Implement JSONL-backed history with dataclass serialization, append-write, corrupt-line resilience, and a `HistoryManager` class wrapping the free functions.

#### 4a. Write failing tests

- [ ] Create `tests/unit/test_history.py`:

```python
"""Tests for JSONL history entry serialization, write/read, and corrupt-line handling."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tinyrecorder.history import HistoryEntry, HistoryManager, read_entries, write_entry


class TestHistoryEntrySerialization:
    """test_history_entry_serialization: Round-trip JSON serialization."""

    def test_round_trip_produces_equal_object(self) -> None:
        entry = HistoryEntry(
            timestamp=datetime(2026, 4, 8, 12, 30, 0, tzinfo=timezone.utc),
            audio_file="rec_20260408_123000.wav",
            transcript="Hello world",
            language="en",
            model="gpt-4o-mini-transcribe",
            duration_sec=12.5,
            noise_reduction=False,
        )
        json_str = entry.to_json()
        result = HistoryEntry.from_json(json_str)
        assert result.is_ok
        restored = result.unwrap()
        assert restored.timestamp == entry.timestamp
        assert restored.audio_file == entry.audio_file
        assert restored.transcript == entry.transcript
        assert restored.language == entry.language
        assert restored.model == entry.model
        assert restored.duration_sec == entry.duration_sec
        assert restored.noise_reduction == entry.noise_reduction

    def test_timestamp_is_iso_8601(self) -> None:
        entry = HistoryEntry(
            timestamp=datetime(2026, 4, 8, 12, 30, 0, tzinfo=timezone.utc),
            audio_file="rec.wav",
            transcript="text",
            language="en",
            model="whisper-1",
            duration_sec=1.0,
            noise_reduction=False,
        )
        json_str = entry.to_json()
        assert "2026-04-08T12:30:00" in json_str

    def test_all_fields_present_in_json(self) -> None:
        import json

        entry = HistoryEntry(
            timestamp=datetime(2026, 4, 8, 12, 30, 0, tzinfo=timezone.utc),
            audio_file="rec.wav",
            transcript="text",
            language="en",
            model="whisper-1",
            duration_sec=1.0,
            noise_reduction=True,
        )
        data = json.loads(entry.to_json())
        assert "timestamp" in data
        assert "audio_file" in data
        assert "transcript" in data
        assert "language" in data
        assert "model" in data
        assert "duration_sec" in data
        assert "noise_reduction" in data

    def test_from_json_invalid_json_returns_err(self) -> None:
        result = HistoryEntry.from_json("not json at all {{{")
        assert result.is_err

    def test_from_json_missing_fields_returns_err(self) -> None:
        result = HistoryEntry.from_json('{"timestamp": "2026-04-08T12:30:00+00:00"}')
        assert result.is_err


class TestHistoryWriteAndReadBack:
    """test_history_write_and_read_back: JSONL append and read-back."""

    def _make_entry(self, transcript: str, seconds_offset: int = 0) -> HistoryEntry:
        return HistoryEntry(
            timestamp=datetime(2026, 4, 8, 12, 30, seconds_offset, tzinfo=timezone.utc),
            audio_file=f"rec_{seconds_offset}.wav",
            transcript=transcript,
            language="en",
            model="gpt-4o-mini-transcribe",
            duration_sec=5.0,
            noise_reduction=False,
        )

    def test_write_creates_file_and_reads_back(self, tmp_path: Path) -> None:
        history_path = tmp_path / "history.jsonl"
        entry = self._make_entry("Hello world")
        write_result = write_entry(entry, history_path)
        assert write_result.is_ok

        read_result = read_entries(history_path, limit=10)
        assert read_result.is_ok
        entries = read_result.unwrap()
        assert len(entries) == 1
        assert entries[0].transcript == "Hello world"

    def test_multiple_writes_append_correctly(self, tmp_path: Path) -> None:
        history_path = tmp_path / "history.jsonl"
        for i in range(5):
            write_entry(self._make_entry(f"Entry {i}", seconds_offset=i), history_path)

        read_result = read_entries(history_path, limit=10)
        assert read_result.is_ok
        entries = read_result.unwrap()
        assert len(entries) == 5

    def test_file_is_valid_jsonl(self, tmp_path: Path) -> None:
        import json

        history_path = tmp_path / "history.jsonl"
        for i in range(3):
            write_entry(self._make_entry(f"Entry {i}", seconds_offset=i), history_path)

        lines = history_path.read_text().strip().split("\n")
        assert len(lines) == 3
        for line in lines:
            parsed = json.loads(line)
            assert isinstance(parsed, dict)

    def test_limit_restricts_returned_entries(self, tmp_path: Path) -> None:
        history_path = tmp_path / "history.jsonl"
        for i in range(10):
            write_entry(self._make_entry(f"Entry {i}", seconds_offset=i), history_path)

        read_result = read_entries(history_path, limit=3)
        assert read_result.is_ok
        entries = read_result.unwrap()
        assert len(entries) == 3

    def test_read_nonexistent_file_returns_empty(self, tmp_path: Path) -> None:
        history_path = tmp_path / "nonexistent.jsonl"
        read_result = read_entries(history_path, limit=10)
        assert read_result.is_ok
        assert read_result.unwrap() == []

    def test_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        history_path = tmp_path / "deep" / "nested" / "history.jsonl"
        entry = self._make_entry("Hello")
        result = write_entry(entry, history_path)
        assert result.is_ok
        assert history_path.exists()


class TestHistoryHandlesCorruptLines:
    """test_history_handles_corrupt_lines: Reader skips malformed lines without crashing."""

    def test_skips_invalid_json_lines(self, tmp_path: Path) -> None:
        history_path = tmp_path / "history.jsonl"
        entry = HistoryEntry(
            timestamp=datetime(2026, 4, 8, 12, 30, 0, tzinfo=timezone.utc),
            audio_file="rec.wav",
            transcript="Valid entry",
            language="en",
            model="whisper-1",
            duration_sec=5.0,
            noise_reduction=False,
        )
        valid_line = entry.to_json()
        content = f"{valid_line}\nthis is not json\n{valid_line}\n{{bad json}}\n{valid_line}\n"
        history_path.write_text(content)

        read_result = read_entries(history_path, limit=100)
        assert read_result.is_ok
        entries = read_result.unwrap()
        assert len(entries) == 3
        for e in entries:
            assert e.transcript == "Valid entry"

    def test_empty_lines_are_skipped(self, tmp_path: Path) -> None:
        history_path = tmp_path / "history.jsonl"
        entry = HistoryEntry(
            timestamp=datetime(2026, 4, 8, 12, 30, 0, tzinfo=timezone.utc),
            audio_file="rec.wav",
            transcript="text",
            language="en",
            model="whisper-1",
            duration_sec=1.0,
            noise_reduction=False,
        )
        content = f"\n\n{entry.to_json()}\n\n{entry.to_json()}\n\n"
        history_path.write_text(content)

        read_result = read_entries(history_path, limit=100)
        assert read_result.is_ok
        assert len(read_result.unwrap()) == 2

    def test_all_corrupt_returns_empty(self, tmp_path: Path) -> None:
        history_path = tmp_path / "history.jsonl"
        history_path.write_text("garbage\nnonsense\n{bad}\n")
        read_result = read_entries(history_path, limit=100)
        assert read_result.is_ok
        assert read_result.unwrap() == []


class TestHistoryManager:
    """Tests for the HistoryManager class wrapper."""

    def _make_entry(self, transcript: str, seconds_offset: int = 0) -> HistoryEntry:
        return HistoryEntry(
            timestamp=datetime(2026, 4, 8, 12, 30, seconds_offset, tzinfo=timezone.utc),
            audio_file=f"rec_{seconds_offset}.wav",
            transcript=transcript,
            language="en",
            model="gpt-4o-mini-transcribe",
            duration_sec=5.0,
            noise_reduction=False,
        )

    def test_add_entry_and_get_recent(self, tmp_path: Path) -> None:
        history_path = tmp_path / "history.jsonl"
        manager = HistoryManager(history_path)
        manager.add_entry(
            audio_file="rec.wav",
            transcript="Hello",
            language="en",
            model="whisper-1",
            duration_sec=5.0,
            noise_reduction=False,
        )
        entries = manager.get_recent(limit=10)
        assert len(entries) == 1
        assert entries[0].transcript == "Hello"

    def test_get_entry_by_index(self, tmp_path: Path) -> None:
        history_path = tmp_path / "history.jsonl"
        manager = HistoryManager(history_path)
        for i in range(3):
            manager.add_entry(
                audio_file=f"rec_{i}.wav",
                transcript=f"Entry {i}",
                language="en",
                model="whisper-1",
                duration_sec=5.0,
                noise_reduction=False,
            )
        entry = manager.get_entry(1)
        assert entry is not None
        assert entry.transcript == "Entry 1"

    def test_get_entry_out_of_range_returns_none(self, tmp_path: Path) -> None:
        history_path = tmp_path / "history.jsonl"
        manager = HistoryManager(history_path)
        assert manager.get_entry(0) is None
```

- [ ] Run tests to see them fail:

```bash
uv run pytest tests/unit/test_history.py -v -n0
```

#### 4b. Implement history module

- [ ] Create `src/history.py`:

```python
"""JSONL history: append-write entries and read them back with corrupt-line resilience."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from rusty_results import Err, Ok, Result

# Note: history_path is provided by the caller via UserDirectories.data_dir / "history.jsonl"
# There is no HISTORY_FILE constant; paths come from the platform layer.


@dataclass(slots=True)
class HistoryEntry:
    """A single transcription history record.

    Attributes:
        timestamp: When the transcription was created (UTC).
        audio_file: Filename relative to the audio cache directory.
        transcript: The transcribed text.
        language: ISO-639-1 language code or "auto".
        model: Model used for transcription.
        duration_sec: Audio duration in seconds.
        noise_reduction: Whether noise reduction was applied.
    """

    timestamp: datetime
    audio_file: str
    transcript: str
    language: str
    model: str
    duration_sec: float
    noise_reduction: bool

    def to_json(self) -> str:
        """Serialize to a single-line JSON string.

        Returns:
            JSON string with all fields, timestamp in ISO 8601 format.
        """
        return json.dumps(
            {
                "timestamp": self.timestamp.isoformat(),
                "audio_file": self.audio_file,
                "transcript": self.transcript,
                "language": self.language,
                "model": self.model,
                "duration_sec": self.duration_sec,
                "noise_reduction": self.noise_reduction,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def from_json(line: str) -> Result["HistoryEntry", str]:
        """Deserialize from a JSON string.

        Args:
            line: A single JSON line.

        Returns:
            Ok(HistoryEntry) on success, Err(str) describing the parse failure.
        """
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError) as e:
            return Err(f"Invalid JSON: {e}")
        if not isinstance(data, dict):
            return Err(f"Expected JSON object, got {type(data).__name__}")
        try:
            raw_ts = data["timestamp"]
            if not isinstance(raw_ts, str):
                return Err(f"timestamp must be a string, got {type(raw_ts).__name__}")
            timestamp = datetime.fromisoformat(raw_ts)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)

            raw_audio = data["audio_file"]
            if not isinstance(raw_audio, str):
                return Err(f"audio_file must be a string, got {type(raw_audio).__name__}")

            raw_transcript = data["transcript"]
            if not isinstance(raw_transcript, str):
                return Err(f"transcript must be a string, got {type(raw_transcript).__name__}")

            raw_lang = data["language"]
            if not isinstance(raw_lang, str):
                return Err(f"language must be a string, got {type(raw_lang).__name__}")

            raw_model = data["model"]
            if not isinstance(raw_model, str):
                return Err(f"model must be a string, got {type(raw_model).__name__}")

            raw_duration = data["duration_sec"]
            if not isinstance(raw_duration, (int, float)):
                return Err(f"duration_sec must be a number, got {type(raw_duration).__name__}")
            duration_sec = float(raw_duration)

            raw_nr = data["noise_reduction"]
            if not isinstance(raw_nr, bool):
                return Err(f"noise_reduction must be a bool, got {type(raw_nr).__name__}")

            return Ok(HistoryEntry(
                timestamp=timestamp,
                audio_file=raw_audio,
                transcript=raw_transcript,
                language=raw_lang,
                model=raw_model,
                duration_sec=duration_sec,
                noise_reduction=raw_nr,
            ))
        except KeyError as e:
            return Err(f"Missing required field: {e}")


def write_entry(entry: HistoryEntry, path: Path) -> Result[None, str]:
    """Append a history entry as a single JSONL line.

    Args:
        entry: The history entry to write.
        path: Path to the JSONL file (parent dirs created automatically).

    Returns:
        Ok(None) on success, Err(str) on I/O error.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry.to_json() + "\n")
        return Ok(None)
    except OSError as e:
        return Err(f"Failed to write history to {path}: {e}")


def read_entries(path: Path, limit: int) -> Result[list[HistoryEntry], str]:
    """Read history entries from a JSONL file, skipping corrupt lines.

    Args:
        path: Path to the JSONL file.
        limit: Maximum number of entries to return (most recent if file has more).

    Returns:
        Ok(list[HistoryEntry]) on success (empty list if file missing), Err(str) on I/O error.
    """
    if not path.exists():
        return Ok([])
    try:
        entries: list[HistoryEntry] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                result = HistoryEntry.from_json(stripped)
                if result.is_ok:
                    entries.append(result.unwrap())
        if len(entries) > limit:
            entries = entries[-limit:]
        return Ok(entries)
    except OSError as e:
        return Err(f"Failed to read history from {path}: {e}")


class HistoryManager:
    """High-level history manager wrapping free functions.

    Provides add_entry(), get_recent(), and get_entry() methods for use
    by the ApplicationController. Keeps an in-memory cache of entries.

    Args:
        history_path: Path to the JSONL history file (required, provided by caller via UserDirectories).
    """

    def __init__(self, history_path: Path) -> None:
        self._path = history_path
        self._entries: list[HistoryEntry] | None = None

    def _load(self) -> list[HistoryEntry]:
        """Load entries from disk, caching the result."""
        if self._entries is None:
            result = read_entries(self._path, limit=1000)
            self._entries = result.unwrap() if result.is_ok else []
        return self._entries

    def add_entry(
        self,
        audio_file: str,
        transcript: str,
        language: str,
        model: str,
        duration_sec: float,
        noise_reduction: bool,
    ) -> None:
        """Create and append a new history entry.

        Args:
            audio_file: Filename relative to the audio cache directory.
            transcript: The transcribed text.
            language: Language code.
            model: Model identifier.
            duration_sec: Audio duration in seconds.
            noise_reduction: Whether noise reduction was applied.
        """
        entry = HistoryEntry(
            timestamp=datetime.now(tz=timezone.utc),
            audio_file=audio_file,
            transcript=transcript,
            language=language,
            model=model,
            duration_sec=duration_sec,
            noise_reduction=noise_reduction,
        )
        write_entry(entry, self._path)
        # Invalidate cache so next read picks up the new entry
        self._entries = None

    def get_recent(self, limit: int) -> list[HistoryEntry]:
        """Get the most recent history entries.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            List of entries, most recent last.
        """
        entries = self._load()
        if len(entries) > limit:
            return entries[-limit:]
        return list(entries)

    def get_entry(self, index: int) -> HistoryEntry | None:
        """Get a specific history entry by index.

        Args:
            index: Zero-based index into the loaded entries list.

        Returns:
            The entry at the given index, or None if out of range.
        """
        entries = self._load()
        if 0 <= index < len(entries):
            return entries[index]
        return None
```

- [ ] Run tests to see them pass:

```bash
uv run pytest tests/unit/test_history.py -v -n0
```

- [ ] Run type checker and linter:

```bash
uv run basedpyright src/history.py
uv run ruff check src/history.py
```

- [ ] Commit: `feat(history): JSONL history read/write with HistoryManager class`
