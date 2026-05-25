"""End-to-end tests: run calculator.py as a subprocess against the real OpenAI API.

These tests make real API calls. They are skipped automatically if OPENAI_API_KEY
is not set (e.g. in CI without secrets). Run with:

    .venv/bin/pytest -v
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "calculator.py"

requires_api_key = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set; skipping live E2E tests",
)


def run(expression: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), expression],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=60,
    )


@requires_api_key
@pytest.mark.parametrize(
    "expression, expected",
    [
        ("2 + 2", "4"),
        ("10 - 3", "7"),
        ("6 * 7", "42"),
        ("100 / 4", "25"),
        ("(3 + 4) * 2", "14"),
        ("2 ^ 10", "1024"),
        ("sqrt(144)", "12"),
        ("sin(0)", "0"),
    ],
)
def test_valid_expressions_return_result(expression, expected):
    print("Hello World!")
    result = run(expression)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


@requires_api_key
def test_decimal_result():
    result = run("10 / 4")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "2.5"


@requires_api_key
@pytest.mark.parametrize(
    "bad_input",
    [
        "what is the capital of France",
        "write me a poem about cats",
        "tell me a joke",
        "translate hello to Spanish",
        "2 + 2 and then tell me a story",
    ],
)
def test_non_math_input_is_refused(bad_input):
    result = run(bad_input)
    # Exit code 1 == refusal; 2 == API error. Assert the refusal path specifically.
    assert result.returncode == 1, result.stderr
    assert "refused" in result.stderr


@requires_api_key
def test_empty_input_is_refused():
    result = run("")
    assert result.returncode == 1
    assert "Error" in result.stderr


@requires_api_key
def test_stdin_input():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="3 * 9",
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "27"
