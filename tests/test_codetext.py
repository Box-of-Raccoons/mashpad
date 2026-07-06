"""Tests for mashpad.codetext — pure logic, no pygame."""

import sys

import pytest

from mashpad import config, paths
from mashpad.codetext import (
    SOURCE_FILES,
    CodeStream,
    Token,
    color_for,
    load_position,
    save_position,
    take,
    tokenize_source,
)


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------

def test_codetext_no_pygame():
    import mashpad.codetext  # noqa: F401
    assert "pygame" not in sys.modules, "codetext imported pygame!"


# ---------------------------------------------------------------------------
# tokenize_source — category coverage
# ---------------------------------------------------------------------------

def test_tokenize_source_categories():
    source = "def foo(x):  # hi\n    return 'bar' + 42\n"
    tokens = tokenize_source(source)
    assert tokens, "expected at least one token"

    # Every token must have non-empty text (structural tokens dropped).
    for t in tokens:
        assert t.text, f"empty-text token: {t!r}"

    categories = {t.category for t in tokens}
    assert "keyword" in categories, "expected keyword category"
    assert "name" in categories, "expected name category"
    assert "op" in categories, "expected op category"
    assert "string" in categories, "expected string category"
    assert "number" in categories, "expected number category"
    assert "comment" in categories, "expected comment category"

    texts = {t.text for t in tokens}
    # Keywords
    assert "def" in texts
    assert "return" in texts
    # Names
    assert "foo" in texts
    assert "x" in texts
    # Ops
    assert "(" in texts
    assert "+" in texts
    # String
    assert "'bar'" in texts
    # Number
    assert "42" in texts
    # Comment
    assert "# hi" in texts


def test_multiline_string_splits_into_per_line_tokens():
    # A triple-quoted docstring is ONE tokenize token spanning several source
    # lines. It must be split into one Token per physical line, else the code
    # panel (which reserves one line_height per token) stacks the tall glyph
    # over the lines below it. Regression: the BabyIDE "text overlapping" bug.
    src = 'def f():\n    """line one\n    line two\n    line three"""\n    return 1\n'
    toks = tokenize_source(src)
    # No token may contain a newline — each Token is exactly one visual line.
    offenders = [t.text for t in toks if "\n" in t.text]
    assert not offenders, f"tokens still contain newlines: {offenders}"
    # The three docstring lines become three separate string-category tokens
    # on consecutive, increasing rows.
    string_toks = [t for t in toks if t.category == "string"]
    assert len(string_toks) == 3
    rows = [t.row for t in string_toks]
    assert rows == sorted(rows) and len(set(rows)) == 3


# ---------------------------------------------------------------------------
# color_for — known and unknown categories
# ---------------------------------------------------------------------------

def test_color_for_known_category():
    for cat in ("keyword", "string", "comment", "number", "name", "op"):
        assert color_for(cat) == config.BABYIDE_TOKEN_COLORS[cat]


def test_color_for_unknown_category_falls_back_to_name():
    assert color_for("totally_unknown") == config.BABYIDE_TOKEN_COLORS["name"]


# ---------------------------------------------------------------------------
# CodeStream — helpers
# ---------------------------------------------------------------------------

_SIMPLE_SOURCES = {
    "a.py": "x = 1\n",
    "b.py": "y = 2\n",
}

def _reader(sources):
    """Return a reader callable backed by a dict of {name: source}."""
    def read(name):
        if name in sources:
            return sources[name]
        raise FileNotFoundError(name)
    return read


def _drain(stream, limit=200):
    """Collect up to *limit* tokens from *stream*, returning the list."""
    tokens = []
    for _ in range(limit):
        t = stream.next()
        if t is None:
            break
        tokens.append(t)
    return tokens


# ---------------------------------------------------------------------------
# Test 4: one-token-per-next, correct order
# ---------------------------------------------------------------------------

def test_codestream_one_token_per_next():
    stream = CodeStream(["a.py", "b.py"], _reader(_SIMPLE_SOURCES))
    expected_a = tokenize_source("x = 1\n")
    expected_b = tokenize_source("y = 2\n")
    assert expected_a, "a.py should produce tokens"
    assert expected_b, "b.py should produce tokens"

    # Consume a.py tokens
    for expected in expected_a:
        tok = stream.next()
        assert tok is not None
        assert tok.text == expected.text
        assert tok.category == expected.category

    # Consume b.py tokens
    for expected in expected_b:
        tok = stream.next()
        assert tok is not None
        assert tok.text == expected.text
        assert tok.category == expected.category


# ---------------------------------------------------------------------------
# Test 5: EOF advances file + current_file
# ---------------------------------------------------------------------------

def test_eof_advances_file_and_current_file():
    stream = CodeStream(["a.py", "b.py"], _reader(_SIMPLE_SOURCES))
    tokens_a = tokenize_source("x = 1\n")

    # Drain all of a.py
    for _ in tokens_a:
        stream.next()

    # The next token should be from b.py
    tok = stream.next()
    assert tok is not None
    assert tok.text == tokenize_source("y = 2\n")[0].text
    assert stream.current_file == "b.py"


# ---------------------------------------------------------------------------
# Test 6: loop after last file wraps to first
# ---------------------------------------------------------------------------

def test_loop_after_last_file():
    stream = CodeStream(["a.py", "b.py"], _reader(_SIMPLE_SOURCES))
    tokens_a = tokenize_source("x = 1\n")
    tokens_b = tokenize_source("y = 2\n")
    total = len(tokens_a) + len(tokens_b)

    # Drain a.py and b.py completely
    for _ in range(total):
        stream.next()

    # Next call wraps back to a.py's first token
    tok = stream.next()
    assert tok is not None
    assert tok.text == tokens_a[0].text
    assert tok.category == tokens_a[0].category


# ---------------------------------------------------------------------------
# Test 7: missing / unreadable file is skipped without error
# ---------------------------------------------------------------------------

def test_missing_file_skipped(capsys):
    sources = {
        "a.py": "x = 1\n",
        # "b.py" raises
        "c.py": "z = 3\n",
    }
    stream = CodeStream(["a.py", "b.py", "c.py"], _reader(sources))
    tokens = _drain(stream, limit=100)

    # Should see tokens from a.py and c.py, nothing from b.py
    texts = [t.text for t in tokens]
    assert "x" in texts
    assert "z" in texts
    # No crash — capsys captures any warnings printed, but we don't assert on them


# ---------------------------------------------------------------------------
# Test 8: resume roundtrip + bad/missing → None
# ---------------------------------------------------------------------------

def test_resume_roundtrip(tmp_path):
    p = tmp_path / "babyide_state.json"
    assert save_position(("b.py", 1), p) is True
    assert load_position(p) == ("b.py", 1)


def test_resume_load_missing_file_returns_none(tmp_path):
    assert load_position(tmp_path / "does_not_exist.json") is None


def test_resume_load_bad_json_returns_none(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{ not json", encoding="utf-8")
    assert load_position(p) is None


def test_resume_load_non_dict_returns_none(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("[1, 2]", encoding="utf-8")
    assert load_position(p) is None


def test_resume_load_missing_fields_returns_none(tmp_path):
    import json
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"file": "a.py"}), encoding="utf-8")
    assert load_position(p) is None


def test_resume_load_negative_index_returns_none(tmp_path):
    import json
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"file": "a.py", "token_index": -1}), encoding="utf-8")
    assert load_position(p) is None


def test_resume_load_bool_index_returns_none(tmp_path):
    import json
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"file": "a.py", "token_index": True}), encoding="utf-8")
    assert load_position(p) is None


def test_save_atomic_leaves_no_tmp(tmp_path):
    p = tmp_path / "babyide_state.json"
    save_position(("a.py", 0), p)
    assert p.exists()
    assert not (tmp_path / "babyide_state.json.tmp").exists()


def test_save_returns_false_when_parent_is_file(tmp_path):
    bad_dir = tmp_path / "f"
    bad_dir.write_text("not a directory", encoding="utf-8")
    result = save_position(("a.py", 0), bad_dir / "state.json")
    assert result is False


# ---------------------------------------------------------------------------
# Test 9: resume validation — unknown file resets; out-of-range clamps to 0
# ---------------------------------------------------------------------------

def test_resume_unknown_file_starts_at_first():
    stream = CodeStream(
        ["a.py", "b.py"],
        _reader(_SIMPLE_SOURCES),
        position=("nope.py", 0),
    )
    # Should start at the first token of a.py
    tok = stream.next()
    expected = tokenize_source("x = 1\n")[0]
    assert tok is not None
    assert tok.text == expected.text


def test_resume_out_of_range_clamps_to_zero():
    stream = CodeStream(
        ["a.py", "b.py"],
        _reader(_SIMPLE_SOURCES),
        position=("a.py", 999),
    )
    # 999 is out of range for a.py (has 3 tokens), so clamp → a.py index 0
    tok = stream.next()
    expected = tokenize_source("x = 1\n")[0]
    assert tok is not None
    assert tok.text == expected.text


# ---------------------------------------------------------------------------
# take() — the per-keypress burst (BabyIDE reveals 2-10 tokens per press)
# ---------------------------------------------------------------------------

def test_take_returns_count_in_order_and_advances():
    stream = CodeStream(["a.py", "b.py"], _reader(_SIMPLE_SOURCES))
    first = take(stream, 2)
    assert [t.text for t in first] == ["x", "="]
    # a second burst continues where the first left off, crossing a.py -> b.py
    second = take(stream, 2)
    assert [t.text for t in second] == ["1", "y"]


def test_take_non_positive_returns_empty_and_leaves_cursor():
    stream = CodeStream(["a.py", "b.py"], _reader(_SIMPLE_SOURCES))
    assert take(stream, 0) == []
    assert take(stream, -3) == []
    # cursor untouched: the next token is still a.py's first
    tok = stream.next()
    assert tok is not None and tok.text == "x"


def test_take_on_empty_stream_returns_empty_without_hanging():
    # every file unreadable → stream yields None → take stops, no infinite loop
    stream = CodeStream(["x.py"], _reader({}))
    assert take(stream, 5) == []


def test_babyide_tokens_per_key_range_is_sane():
    # min ≥ 1 (every press reveals something) and min ≤ max (rng.randint won't raise)
    assert config.BABYIDE_TOKENS_PER_KEY_MIN >= 1
    assert config.BABYIDE_TOKENS_PER_KEY_MIN <= config.BABYIDE_TOKENS_PER_KEY_MAX


# ---------------------------------------------------------------------------
# Drift guard — every curated source file must actually exist on disk, so a
# rename/move surfaces here as a red test instead of a blank BabyIDE panel.
# ---------------------------------------------------------------------------

def test_source_files_all_exist():
    src = paths.source_dir()
    missing = [name for name in SOURCE_FILES if not (src / name).is_file()]
    assert not missing, f"SOURCE_FILES references files not on disk: {missing}"
