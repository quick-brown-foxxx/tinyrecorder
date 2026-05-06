# Task 3: State Machine

**Phase:** 2 (parallel with: Task 2)
**Dependencies:** Task 1
**Skills:** `writing-python-code`, `testing-python`
**Files to create:** `src/state.py`
**Test files:** `tests/unit/test_state.py`
**Estimated complexity:** small

---

**Goal:** Implement recording state enum, valid transitions, and StateMachine class with callback support.

#### 3a. Write failing tests

- [ ] Create `tests/unit/test_state.py`:

```python
"""Tests for recording state machine transitions and validation."""

from pathlib import Path

import pytest

from tinyrecorder.state import RecordingState, StateMachine, is_valid_transition


class TestStateMachineValidTransitions:
    """test_state_machine_valid_transitions: All valid state transitions from the spec are accepted."""

    def test_idle_to_recording(self) -> None:
        sm = StateMachine()
        result = sm.transition(RecordingState.RECORDING)
        assert result.is_ok
        assert sm.current_state == RecordingState.RECORDING

    def test_recording_to_processing(self) -> None:
        sm = StateMachine()
        sm.transition(RecordingState.RECORDING)
        result = sm.transition(RecordingState.PROCESSING)
        assert result.is_ok
        assert sm.current_state == RecordingState.PROCESSING

    def test_recording_to_idle(self) -> None:
        sm = StateMachine()
        sm.transition(RecordingState.RECORDING)
        result = sm.transition(RecordingState.IDLE)
        assert result.is_ok
        assert sm.current_state == RecordingState.IDLE

    def test_processing_to_success(self) -> None:
        sm = StateMachine()
        sm.transition(RecordingState.RECORDING)
        sm.transition(RecordingState.PROCESSING)
        result = sm.transition(RecordingState.SUCCESS)
        assert result.is_ok
        assert sm.current_state == RecordingState.SUCCESS

    def test_processing_to_error(self) -> None:
        sm = StateMachine()
        sm.transition(RecordingState.RECORDING)
        sm.transition(RecordingState.PROCESSING)
        result = sm.transition(RecordingState.ERROR)
        assert result.is_ok
        assert sm.current_state == RecordingState.ERROR

    def test_success_to_idle(self) -> None:
        sm = StateMachine()
        sm.transition(RecordingState.RECORDING)
        sm.transition(RecordingState.PROCESSING)
        sm.transition(RecordingState.SUCCESS)
        result = sm.transition(RecordingState.IDLE)
        assert result.is_ok
        assert sm.current_state == RecordingState.IDLE

    def test_success_to_processing(self) -> None:
        sm = StateMachine()
        sm.transition(RecordingState.RECORDING)
        sm.transition(RecordingState.PROCESSING)
        sm.transition(RecordingState.SUCCESS)
        result = sm.transition(RecordingState.PROCESSING)
        assert result.is_ok
        assert sm.current_state == RecordingState.PROCESSING

    def test_error_to_idle(self) -> None:
        sm = StateMachine()
        sm.transition(RecordingState.RECORDING)
        sm.transition(RecordingState.PROCESSING)
        sm.transition(RecordingState.ERROR)
        result = sm.transition(RecordingState.IDLE)
        assert result.is_ok
        assert sm.current_state == RecordingState.IDLE

    def test_error_to_processing(self) -> None:
        sm = StateMachine()
        sm.transition(RecordingState.RECORDING)
        sm.transition(RecordingState.PROCESSING)
        sm.transition(RecordingState.ERROR)
        result = sm.transition(RecordingState.PROCESSING)
        assert result.is_ok
        assert sm.current_state == RecordingState.PROCESSING

    def test_processing_to_idle(self) -> None:
        """Cancel during processing returns to IDLE."""
        sm = StateMachine()
        sm.transition(RecordingState.RECORDING)
        sm.transition(RecordingState.PROCESSING)
        result = sm.transition(RecordingState.IDLE)
        assert result.is_ok
        assert sm.current_state == RecordingState.IDLE

    def test_idle_to_processing_for_file_import(self) -> None:
        """File import skips RECORDING, going directly IDLE -> PROCESSING."""
        sm = StateMachine()
        result = sm.transition(RecordingState.PROCESSING)
        assert result.is_ok
        assert sm.current_state == RecordingState.PROCESSING

    def test_state_updated_after_each_transition(self) -> None:
        sm = StateMachine()
        assert sm.current_state == RecordingState.IDLE
        sm.transition(RecordingState.RECORDING)
        assert sm.current_state == RecordingState.RECORDING
        sm.transition(RecordingState.PROCESSING)
        assert sm.current_state == RecordingState.PROCESSING
        sm.transition(RecordingState.SUCCESS)
        assert sm.current_state == RecordingState.SUCCESS

    def test_callback_fires_on_valid_transition(self) -> None:
        transitions: list[tuple[RecordingState, RecordingState]] = []

        def on_change(old: RecordingState, new: RecordingState) -> None:
            transitions.append((old, new))

        sm = StateMachine(on_state_changed=on_change)
        sm.transition(RecordingState.RECORDING)
        sm.transition(RecordingState.PROCESSING)
        assert transitions == [
            (RecordingState.IDLE, RecordingState.RECORDING),
            (RecordingState.RECORDING, RecordingState.PROCESSING),
        ]

    def test_audio_file_path_preserved_across_transitions(self) -> None:
        sm = StateMachine()
        test_path = Path("/tmp/test_recording.wav")
        sm.audio_file_path = test_path
        sm.transition(RecordingState.RECORDING)
        sm.transition(RecordingState.PROCESSING)
        sm.transition(RecordingState.SUCCESS)
        assert sm.audio_file_path == test_path


class TestStateMachineInvalidTransitions:
    """test_state_machine_invalid_transitions: Invalid state transitions are rejected."""

    def test_idle_to_success(self) -> None:
        sm = StateMachine()
        result = sm.transition(RecordingState.SUCCESS)
        assert result.is_err
        assert sm.current_state == RecordingState.IDLE

    def test_idle_to_error(self) -> None:
        sm = StateMachine()
        result = sm.transition(RecordingState.ERROR)
        assert result.is_err
        assert sm.current_state == RecordingState.IDLE

    def test_recording_to_success(self) -> None:
        sm = StateMachine()
        sm.transition(RecordingState.RECORDING)
        result = sm.transition(RecordingState.SUCCESS)
        assert result.is_err
        assert sm.current_state == RecordingState.RECORDING

    def test_recording_to_error(self) -> None:
        sm = StateMachine()
        sm.transition(RecordingState.RECORDING)
        result = sm.transition(RecordingState.ERROR)
        assert result.is_err
        assert sm.current_state == RecordingState.RECORDING

    def test_processing_to_recording(self) -> None:
        sm = StateMachine()
        sm.transition(RecordingState.RECORDING)
        sm.transition(RecordingState.PROCESSING)
        result = sm.transition(RecordingState.RECORDING)
        assert result.is_err
        assert sm.current_state == RecordingState.PROCESSING

    def test_success_to_recording(self) -> None:
        sm = StateMachine()
        sm.transition(RecordingState.RECORDING)
        sm.transition(RecordingState.PROCESSING)
        sm.transition(RecordingState.SUCCESS)
        result = sm.transition(RecordingState.RECORDING)
        assert result.is_err
        assert sm.current_state == RecordingState.SUCCESS

    def test_success_to_error(self) -> None:
        sm = StateMachine()
        sm.transition(RecordingState.RECORDING)
        sm.transition(RecordingState.PROCESSING)
        sm.transition(RecordingState.SUCCESS)
        result = sm.transition(RecordingState.ERROR)
        assert result.is_err
        assert sm.current_state == RecordingState.SUCCESS

    def test_error_to_recording(self) -> None:
        sm = StateMachine()
        sm.transition(RecordingState.RECORDING)
        sm.transition(RecordingState.PROCESSING)
        sm.transition(RecordingState.ERROR)
        result = sm.transition(RecordingState.RECORDING)
        assert result.is_err
        assert sm.current_state == RecordingState.ERROR

    def test_error_to_success(self) -> None:
        sm = StateMachine()
        sm.transition(RecordingState.RECORDING)
        sm.transition(RecordingState.PROCESSING)
        sm.transition(RecordingState.ERROR)
        result = sm.transition(RecordingState.SUCCESS)
        assert result.is_err
        assert sm.current_state == RecordingState.ERROR

    def test_callback_does_not_fire_on_invalid_transition(self) -> None:
        transitions: list[tuple[RecordingState, RecordingState]] = []

        def on_change(old: RecordingState, new: RecordingState) -> None:
            transitions.append((old, new))

        sm = StateMachine(on_state_changed=on_change)
        sm.transition(RecordingState.SUCCESS)  # invalid from IDLE
        assert transitions == []


class TestStateTransitionValidationFunction:
    """test_state_transition_validation_function: Covers all 25 combinations (5x5 matrix)."""

    VALID_PAIRS: list[tuple[RecordingState, RecordingState]] = [
        (RecordingState.IDLE, RecordingState.RECORDING),
        (RecordingState.IDLE, RecordingState.PROCESSING),
        (RecordingState.RECORDING, RecordingState.PROCESSING),
        (RecordingState.RECORDING, RecordingState.IDLE),
        (RecordingState.PROCESSING, RecordingState.SUCCESS),
        (RecordingState.PROCESSING, RecordingState.ERROR),
        (RecordingState.PROCESSING, RecordingState.IDLE),
        (RecordingState.SUCCESS, RecordingState.IDLE),
        (RecordingState.SUCCESS, RecordingState.PROCESSING),
        (RecordingState.ERROR, RecordingState.IDLE),
        (RecordingState.ERROR, RecordingState.PROCESSING),
    ]

    def test_all_valid_transitions_return_true(self) -> None:
        for from_state, to_state in self.VALID_PAIRS:
            assert is_valid_transition(from_state, to_state), f"{from_state} -> {to_state} should be valid"

    def test_all_invalid_transitions_return_false(self) -> None:
        all_states = list(RecordingState)
        valid_set = set(self.VALID_PAIRS)
        for from_state in all_states:
            for to_state in all_states:
                if (from_state, to_state) not in valid_set:
                    assert not is_valid_transition(from_state, to_state), (
                        f"{from_state} -> {to_state} should be invalid"
                    )

    def test_self_transitions_are_invalid(self) -> None:
        for state in RecordingState:
            assert not is_valid_transition(state, state), f"{state} -> {state} should be invalid"
```

- [ ] Run tests to see them fail:

```bash
uv run pytest tests/unit/test_state.py -v -n0
```

#### 3b. Implement state machine

- [ ] Create `src/state.py`:

```python
"""Recording state machine with enum states and validated transitions."""

from collections.abc import Callable
from enum import Enum, auto
from pathlib import Path

from rusty_results import Err, Ok, Result


class RecordingState(Enum):
    """Possible states of the recording lifecycle."""

    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()
    SUCCESS = auto()
    ERROR = auto()


VALID_TRANSITIONS: dict[RecordingState, frozenset[RecordingState]] = {
    RecordingState.IDLE: frozenset({RecordingState.RECORDING, RecordingState.PROCESSING}),
    RecordingState.RECORDING: frozenset({RecordingState.PROCESSING, RecordingState.IDLE}),
    RecordingState.PROCESSING: frozenset({RecordingState.SUCCESS, RecordingState.ERROR, RecordingState.IDLE}),
    RecordingState.SUCCESS: frozenset({RecordingState.IDLE, RecordingState.PROCESSING}),
    RecordingState.ERROR: frozenset({RecordingState.IDLE, RecordingState.PROCESSING}),
}


def is_valid_transition(from_state: RecordingState, to_state: RecordingState) -> bool:
    """Check whether a state transition is allowed.

    Args:
        from_state: Current state.
        to_state: Desired next state.

    Returns:
        True if the transition is in the valid transitions table.
    """
    return to_state in VALID_TRANSITIONS.get(from_state, frozenset())


class StateMachine:
    """Recording state machine with callback notification.

    Args:
        on_state_changed: Optional callback invoked as (old_state, new_state) after each valid transition.
    """

    def __init__(
        self,
        on_state_changed: Callable[[RecordingState, RecordingState], None] | None = None,
    ) -> None:
        self._state: RecordingState = RecordingState.IDLE
        self._on_state_changed = on_state_changed
        self.audio_file_path: Path | None = None

    @property
    def current_state(self) -> RecordingState:
        """Current state of the machine."""
        return self._state

    def transition(self, new_state: RecordingState) -> Result[RecordingState, str]:
        """Attempt a state transition.

        Args:
            new_state: Desired next state.

        Returns:
            Ok(new_state) if transition is valid, Err(str) with explanation if not.
        """
        if not is_valid_transition(self._state, new_state):
            return Err(f"Invalid transition: {self._state.name} -> {new_state.name}")
        old_state = self._state
        self._state = new_state
        if self._on_state_changed is not None:
            self._on_state_changed(old_state, new_state)
        return Ok(new_state)
```

- [ ] Run tests to see them pass:

```bash
uv run pytest tests/unit/test_state.py -v -n0
```

- [ ] Run type checker and linter:

```bash
uv run basedpyright src/state.py
uv run ruff check src/state.py
```

- [ ] Commit: `feat(state): recording state machine with validated transitions`
