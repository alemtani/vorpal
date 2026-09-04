"""The .env loader. A key file the operator writes once, read at startup."""

from __future__ import annotations

from pathlib import Path

import pytest

from vorpal.cli import load_dotenv


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(body, encoding="utf-8")
    return path


def test_a_missing_file_is_not_an_error(tmp_path: Path) -> None:
    """No .env is the normal case for someone who exports by hand."""
    env: dict[str, str] = {}
    assert load_dotenv(tmp_path / ".env", env) == ()
    assert env == {}


def test_keys_and_values_load(tmp_path: Path) -> None:
    env: dict[str, str] = {}
    path = _write(tmp_path, "ANTHROPIC_API_KEY=sk-abc\nFANTASYPROS_API_KEY=fp-123\n")
    assert load_dotenv(path, env) == ("ANTHROPIC_API_KEY", "FANTASYPROS_API_KEY")
    assert env == {"ANTHROPIC_API_KEY": "sk-abc", "FANTASYPROS_API_KEY": "fp-123"}


def test_the_real_environment_wins(tmp_path: Path) -> None:
    """A key already exported beats the file, so a one-off override still works.

    `ANTHROPIC_API_KEY=other uv run vorpal ...` has to mean what it says.
    """
    env = {"ANTHROPIC_API_KEY": "from-the-shell"}
    path = _write(tmp_path, "ANTHROPIC_API_KEY=from-the-file\nOTHER=x\n")
    assert load_dotenv(path, env) == ("OTHER",)
    assert env["ANTHROPIC_API_KEY"] == "from-the-shell"


def test_comments_blank_lines_and_export_prefix(tmp_path: Path) -> None:
    """The file people actually write, pasted from a shell session."""
    env: dict[str, str] = {}
    path = _write(
        tmp_path,
        "# keys for draft night\n"
        "\n"
        "export ANTHROPIC_API_KEY=sk-abc\n"
        "   \n"
        "  FANTASYPROS_API_KEY=fp-123  \n"
        "# LANGSMITH_API_KEY=not-set-yet\n",
    )
    assert load_dotenv(path, env) == ("ANTHROPIC_API_KEY", "FANTASYPROS_API_KEY")
    assert env["ANTHROPIC_API_KEY"] == "sk-abc"
    assert env["FANTASYPROS_API_KEY"] == "fp-123"


def test_quotes_are_stripped_only_when_they_match(tmp_path: Path) -> None:
    """A quoted value is unquoted. A key that really contains a quote is not."""
    env: dict[str, str] = {}
    path = _write(
        tmp_path,
        'A="sk-abc"\nB=\'fp-123\'\nC="lopsided\nD=sk-with=equals\nE=\n',
    )
    load_dotenv(path, env)
    assert env == {
        "A": "sk-abc",
        "B": "fp-123",
        "C": '"lopsided',
        "D": "sk-with=equals",
        "E": "",
    }


def test_a_line_with_no_equals_warns_and_does_not_stop_the_draft(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A typo must be loud but must not cost the operator the draft.

    Skipping in silence would hand them a missing-key failure ten minutes
    later with nothing pointing at the file.
    """
    env: dict[str, str] = {}
    path = _write(tmp_path, "ANTHROPIC_API_KEY sk-abc\nFANTASYPROS_API_KEY=fp-123\n")
    assert load_dotenv(path, env) == ("FANTASYPROS_API_KEY",)
    err = capsys.readouterr().err
    assert "line 1" in err
    assert "sk-abc" not in err, "a warning must never echo a secret"


def test_no_value_is_ever_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Names are safe to show. Values are not, on any path."""
    env: dict[str, str] = {}
    path = _write(tmp_path, "ANTHROPIC_API_KEY=sk-secret-value\nbroken line\n")
    load_dotenv(path, env)
    captured = capsys.readouterr()
    assert "sk-secret-value" not in captured.out + captured.err


TEMPLATE = Path(__file__).resolve().parents[1] / ".env.example"

# Every key the operator has to supply. `ANTHROPIC_API_KEY` is read by the
# Anthropic SDK rather than by us, which is exactly why it belongs here: it is
# the one nothing in this repo would otherwise name.
REQUIRED_KEYS = ("ANTHROPIC_API_KEY", "FANTASYPROS_API_KEY")
OPTIONAL_KEYS = ("LANGSMITH_API_KEY", "LANGSMITH_PROJECT")

# A committed file with a value against one of these names is a leaked key.
SECRET_KEYS = ("ANTHROPIC_API_KEY", "FANTASYPROS_API_KEY", "LANGSMITH_API_KEY")


def test_the_template_names_every_key() -> None:
    """A template missing a key is worse than no template.

    Copying it then hitting a missing-key failure is the exact papercut the
    file is here to remove.
    """
    parsed: dict[str, str] = {}
    load_dotenv(TEMPLATE, parsed)
    assert set(parsed) == set(REQUIRED_KEYS + OPTIONAL_KEYS)


def test_the_template_carries_no_secret() -> None:
    """It is committed, so every secret slot must be empty.

    `LANGSMITH_PROJECT` is a label, not a credential, so it keeps its default.
    """
    parsed: dict[str, str] = {}
    load_dotenv(TEMPLATE, parsed)
    for key in SECRET_KEYS:
        assert parsed[key] == "", f"{key} has a value in a committed file"


def test_the_template_is_what_the_loader_reads() -> None:
    """The template is checked with the real parser, not a second one here."""
    assert TEMPLATE.is_file()
    assert "cp .env.example .env" in TEMPLATE.read_text(encoding="utf-8")
