"""D-19: custom sticky-note text parsing + staging."""

import numpy as np
import pytest

from perception.reader import (
    ATTACK_LINES,
    parse_note_lines,
    stage_note_text,
)


def test_parse_blank_means_default():
    assert parse_note_lines(None) is None
    assert parse_note_lines("") is None
    assert parse_note_lines("  \n  ") is None


def test_parse_splits_and_strips():
    assert parse_note_lines("robot: wave\ntwice") == ["robot: wave",
                                                      "twice"]
    assert parse_note_lines("  one  \n\n  two  ") == ["one", "two"]
    assert parse_note_lines("single") == ["single"]


def test_parse_caps_lines_and_chars():
    with pytest.raises(ValueError, match="at most 2 lines"):
        parse_note_lines("a\nb\nc")
    with pytest.raises(ValueError, match="at most 42"):
        parse_note_lines("x" * 43)


def test_default_attack_lines_shape():
    assert len(ATTACK_LINES) == 2
    assert all(len(ln) <= 42 for ln in ATTACK_LINES)


def test_stage_note_text_draws_custom_lines():
    rgb = np.full((120, 120, 3), 200, dtype=np.uint8)
    out = stage_note_text(rgb, (60, 60), ["robot: wave", "twice"])
    assert out.shape == rgb.shape
    assert (np.asarray(out) != rgb).any()  # text landed on pixels
