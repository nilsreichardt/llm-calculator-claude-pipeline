# llm-calculator

A calculator where the LLM *is* the calculator. You give it a math expression as
a string; it sends the expression to OpenAI and prints the result. Anything that
isn't a classic calculator input is refused.

## How it works

`calculator.py` sends your input to an OpenAI model (`gpt-4o-mini`, temperature 0)
with a system prompt that tells it to behave like a scientific calculator:

- **Valid math expression** → prints only the result (exit code `0`).
- **Not a calculation** (questions, prose, anything a physical calculator can't
  compute) → the model returns a `NOT_A_CALCULATION` sentinel, which becomes a
  refusal printed to stderr (exit code `1`).
- **API error** (e.g. no quota, network failure) → printed to stderr (exit code `2`).

Supported inputs include the operations a standard scientific calculator handles:
`+ - * / ^ %`, parentheses, and functions like `sqrt`, `sin`, `cos`, `tan`,
`log`, `ln`, `abs`, plus constants `pi` and `e`.

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Add your OpenAI API key to a `.env` file in the project root:

```
OPENAI_API_KEY=sk-...
```

## Usage

Pass the expression as an argument:

```sh
.venv/bin/python calculator.py "(12 + 8) * 3 / 2"
# 30
```

Or pipe it via stdin:

```sh
echo "sqrt(144)" | .venv/bin/python calculator.py
# 12
```

Non-math input is refused:

```sh
.venv/bin/python calculator.py "what's the weather in Paris"
# Error: refused: "what's the weather in Paris" is not a classic calculator input
# (exit code 1)
```

## Tests

The end-to-end tests run `calculator.py` as a subprocess against the **live**
OpenAI API. They skip automatically if `OPENAI_API_KEY` is not set.

```sh
.venv/bin/pytest -v
```

## Continuous integration

Two GitHub Actions workflows run on pull requests:

- **CI** (`.github/workflows/ci.yml`) — lint, byte-compile, import and test
  collection. It needs no secrets, so it runs automatically on every push and PR,
  **including PRs from forks**. External contributors get this feedback in
  seconds. The live E2E tests skip here (no key), but the suite is proven
  importable and green.
- **E2E (live API)** (`.github/workflows/e2e.yml`) — runs the real end-to-end
  tests against the OpenAI API.

The live tests need a paid API key, and GitHub deliberately withholds repo
secrets from fork PRs (so a malicious PR can't steal them). The E2E workflow is
therefore gated so fork contributors can still run it **safely**: a maintainer
reviews the diff and approves, which releases the key and runs the contributor's
code against the API. The key is never exposed to unreviewed fork code.

### One-time setup (maintainer)

In **Settings → Environments**, create an environment named `e2e` and:

1. Add an **environment secret** `OPENAI_API_KEY` — an *environment* secret, not a
   plain repo secret; this is what binds the key to the approval gate.
2. Add yourself / your team under **Required reviewers**.

Optionally, under **Settings → Actions → General**, enable *Require approval for
all outside collaborators* as an extra gate before any fork workflow runs.

### What a fork contributor sees

1. They open a PR; **CI** runs immediately and reports lint / compile / collection.
2. **E2E (live API)** shows as *waiting for approval*.
3. A maintainer reviews the diff and clicks **Approve**; the live tests then run
   against the contributor's code and report back on the PR.

## Files

| File                 | Purpose                                          |
| -------------------- | ------------------------------------------------ |
| `calculator.py`      | The CLI script — sends input to OpenAI.          |
| `tests/test_e2e.py`  | End-to-end tests against the live API.           |
| `requirements.txt`   | Python dependencies.                             |
| `.env`               | Holds `OPENAI_API_KEY` (not committed).          |
| `.github/workflows/ci.yml`  | Fast checks (lint, compile, collect) on every PR — no secrets. |
| `.github/workflows/e2e.yml` | Live E2E tests against the API, gated by maintainer approval.  |
