"""Input handling for loop.live: control chars are stripped, empties ignored."""

from loop.live import _clean_line


def test_clean_line_strips_controls():
    assert _clean_line("give me the knife") == "give me the knife"
    assert _clean_line("  wave hi  ") == "wave hi"
    assert _clean_line("\x16") == ""  # pasted ^V
    assert _clean_line("\x00\x01\x02") == ""
    assert _clean_line("  \x16  ") == ""
    assert _clean_line("") == ""
    assert _clean_line("pour\x00 water") == "pour water"
    assert _clean_line("quit") == "quit"
