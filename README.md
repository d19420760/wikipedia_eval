# claude-simple

Minimal Python CLI that sends a string prompt to Claude and prints the reply.

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

## Usage

```bash
uv run main.py "Why is the sky blue?"
```

`uv run` creates a virtualenv and installs dependencies on first invocation. The command is identical on Windows, Linux, and macOS.

### Options

| Flag           | Default            | Description       |
| -------------- | ------------------ | ----------------- |
| `--model`      | `claude-opus-4-7`  | Claude model ID.  |
| `--max-tokens` | `1024`             | Response cap.     |

Example:

```bash
uv run main.py --model claude-sonnet-4-6 --max-tokens 256 "Summarize Hamlet in one sentence."
```

## Files

- `main.py` — CLI entry point
- `pyproject.toml` — uv project config and dependencies
- `secrets.yaml.example` — template; copy to `secrets.yaml`
- `secrets.yaml` — your real key (gitignored)
- `.gitignore` — ignores `secrets.yaml`
