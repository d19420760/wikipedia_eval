# wikipedia_eval

Anthropic prompt-engineering take-home: build a Claude + Wikipedia question-answering system (model gets a single `search_wikipedia(query)` tool — no hosted search / RAG) and an eval suite that measures how well it works. **This README describes the current state of the repo, not the finished system.**

## Status

Pre-implementation. The repo is scaffolding only:

- `main.py` is a bare Anthropic API call — no system prompt, no tools, no Wikipedia, no eval.
- The planned first vertical slice (agent loop, `ask_question.py`, `run_eval.py`, MediaWiki client with cache, LLM judge) is described in [`PLAN.md`](PLAN.md).
- Project context and the hard constraints from the brief are in [`CLAUDE.md`](CLAUDE.md).

## Stack

- [uv](https://docs.astral.sh/uv/) — Python project / dependency manager
- [click](https://click.palletsprojects.com/) — argument parsing
- [PyYAML](https://pyyaml.org/) — reads the local secrets file
- [anthropic](https://github.com/anthropics/anthropic-sdk-python) — Claude API client

## Setup

1. Install `uv` if you don't have it:

   **Windows (PowerShell):**

   ```powershell
   winget install --id=astral-sh.uv -e
   ```

   **Linux / macOS:**

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   See the [uv install docs](https://docs.astral.sh/uv/getting-started/installation/) for other options (Homebrew, pipx, etc.).

2. Create your secrets file from the template and paste in your Anthropic API key:

   **Windows (PowerShell):**

   ```powershell
   Copy-Item secrets.yaml.example secrets.yaml
   notepad secrets.yaml
   ```

   **Linux / macOS:**

   ```bash
   cp secrets.yaml.example secrets.yaml
   $EDITOR secrets.yaml
   ```

   `secrets.yaml` is gitignored — it will never be committed.

## What runs today

Only the bare scaffold:

```bash
uv run main.py "Why is the sky blue?"
```

`uv run` creates a virtualenv and installs dependencies on first invocation. The command is identical on Windows, Linux, and macOS.

### Options

| Flag           | Default            | Description       |
| -------------- | ------------------ | ----------------- |
| `--model`      | `claude-opus-4-7`  | Claude model ID.  |
| `--max-tokens` | `1024`             | Response cap.     |

The Wikipedia tool, agent loop, and eval driver described in `PLAN.md` are not implemented yet — don't expect `ask_question.py` or `run_eval.py` to exist on disk.

## Repo layout

- `main.py` — current entry point; bare Anthropic ping (placeholder, will be replaced per `PLAN.md`)
- `PLAN.md` — planned first vertical slice (agent + eval skeleton)
- `CLAUDE.md` — working agreement and hard constraints from the assignment brief
- `pyproject.toml` — uv project config and dependencies
- `secrets.yaml.example` — template; copy to `secrets.yaml`
- `secrets.yaml` — your real key (gitignored)
- `edit_gsheets.py` — unrelated helper, not part of this project
- `.gitignore` — ignores `secrets.yaml` and the assignment PDF
