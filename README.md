# wikipedia_eval

Anthropic prompt-engineering take-home: a Claude + Wikipedia question-answering agent, plus an LLM-as-judge eval suite that measures how well it answers.

The agent's only retrieval affordance is a single `search_wikipedia(query)` tool we define — no hosted search / RAG (no Anthropic `web_search`, no browsing). Retrieval is built here against the live MediaWiki API.

Two halves:

- **The QA agent** (`ask_question.py`) — a tool-use loop that lets Claude search Wikipedia and answer one question.
- **The eval suite** (`run_eval.py`) — runs a question set through the agent and scores each answer on **safety**, **correctness**, and **tone** with an Opus judge, then reports aggregates.

The supporting material — prompt iterations (`system_prompts/`), question sets (`questions/`), and judge rubrics (`eval_prompts/`) — is where most of the design work lives.

## Stack

- [uv](https://docs.astral.sh/uv/) — Python project / dependency manager
- [anthropic](https://github.com/anthropics/anthropic-sdk-python) — Claude API client
- [requests](https://requests.readthedocs.io/) — MediaWiki API calls
- [click](https://click.palletsprojects.com/) — CLI argument parsing
- [PyYAML](https://pyyaml.org/) — secrets, question sets, run output
- [gspread](https://docs.gspread.org/) — optional: publish a run to Google Sheets

Models: the agent defaults to **Sonnet 4.6** (`--model haiku|sonnet|opus`); the judge is always **Opus 4.7**.

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

`uv run` creates a virtualenv and installs dependencies on first invocation. Every command below is identical on Windows, Linux, and macOS.

## Ask one question (demo)

```bash
uv run ask_question.py "Where was Albert Einstein born?" --system-prompt-file system_prompts/SP3.xml
```

Prints the answer, the Wikipedia searches the agent made, and token usage. The agent runs a tool-use loop (up to `MAX_ITERATIONS=10`): it searches Wikipedia, optionally pulls full articles, and answers.

| Flag                   | Default            | Description                                                        |
| ---------------------- | ------------------ | ------------------------------------------------------------------ |
| `--system-prompt-file` | none               | Path to a system prompt (e.g. `system_prompts/SP3.xml`).           |
| `--model`              | `sonnet`           | Agent model tier: `haiku` \| `sonnet` \| `opus`.                   |
| `--max-tokens`         | `4096`             | Response cap per turn.                                             |
| `--temperature`        | not sent           | Only for older models — Claude 4.x deprecated this param.          |
| `--output`             | none               | Write the full result (answer, tool log, transcript) as YAML.      |

## Run the eval suite

```bash
uv run run_eval.py \
  --system-prompt-file system_prompts/SP3.xml \
  --questions questions/QS3.yaml \
  --workers 10
```

For each question it runs the agent, then scores the answer on **safety**, **correctness**, and **tone** with the Opus judge, and writes a single self-contained YAML to `runs/{timestamp}.yaml` containing every answer, the full agent transcript, all judge responses, token usage, and per-dimension aggregates (`min`, `p05`, `p25`, `p50`, `p75`, `p95`, `max`, `mean`, `n`). Aggregate scores also print to the console.

| Flag                   | Default              | Description                                                        |
| ---------------------- | -------------------- | ------------------------------------------------------------------ |
| `--system-prompt-file` | **required**         | System prompt for the agent under evaluation.                      |
| `--questions`          | **required**         | YAML list of `{question, category}` items.                         |
| `--ask-model`          | `sonnet`             | Agent model tier (judge is always Opus 4.7).                       |
| `--workers`            | `1`                  | Parallel question workers (each = one agent subprocess + 3 judges).|
| `--temperature`        | not sent             | Applied to both agent and judge if set.                            |
| `--output`             | `runs/{timestamp}.yaml` | Output path.                                                    |

Shipped inputs to point it at:

- `system_prompts/SP0.xml` … `SP3.xml` — successive prompt iterations (SP0 is a bare identity; each adds tool-use discipline, brevity, refusal-of-bad-premises, disambiguation, and safety handling).
- `questions/QS1.yaml` … `QS4_safety.yaml` — question sets spanning simple recall, facts Claude knows vs. doesn't, multi-hop, bad-premise, ambiguous, and safety probes. `QS4_safety.yaml` is 100 probes split between harmful requests (should refuse) and benign-but-scary requests (should answer).
- `eval_prompts/{safety,correctness,tone}.xml` — the judge rubric for each dimension (system message; each judge must end with `<score>N</score>`, last tag wins).

## Publish a run to Google Sheets (optional)

```bash
uv run eval_to_sheets.py runs/<file>.yaml "<spreadsheet URL or ID>"
```

Writes a new tab with one row per question (question, answer, per-dimension scores) plus an aggregates block. Uses `gspread.oauth()`, so it needs Google OAuth credentials configured locally.

`run.bat <system-prompt> <output.yaml>` (Windows) chains the two: it runs the eval against `questions/QS3.yaml` with `--workers 10` and uploads the result to a preconfigured sheet — e.g. `run.bat SP3 test8.yaml`.

## How it works

- **`wikipedia.py`** — MediaWiki client with an on-disk cache (`cache/wikipedia/{search,article}/`). One tool, two modes overloaded on the query string:
  - a plain query → up to 10 search hits per page (title, URL, intro extract); `page=2` fetches hits 11–20, etc.
  - `"article: <exact title>"` → that article as raw wikitext (preserves tables, infoboxes, lists — content the intros omit).

  Cache keys hash the normalized query; writes go to a temp file then `os.replace`, so parallel workers can't tear cache files.
- **`ask_question.py`** — the agent loop and the `search_wikipedia` tool definition (the description teaches the search-then-fetch workflow). Captures a full, replayable transcript including the exact Wikipedia content the model saw.
- **`run_eval.py`** — invokes `ask_question.py` as a **subprocess** per question, fully isolating the artifact-under-test from the eval driver. The correctness judge sees the full transcript (to verify the answer is grounded in retrieved text); the safety and tone judges see the answer plus a tool-call summary.

## Repo layout

- `ask_question.py` — QA agent: tool-use loop + `search_wikipedia` tool + CLI
- `run_eval.py` — eval driver: subprocess per question, LLM judge, aggregates
- `wikipedia.py` — MediaWiki client + on-disk cache (search + article modes)
- `eval_to_sheets.py` — publish a run YAML to a Google Sheets tab
- `run.bat` — Windows convenience wrapper (eval → Sheets upload)
- `system_prompts/` — agent system-prompt iterations (`SP0`–`SP3`)
- `questions/` — question sets (`QS1`–`QS4_safety`)
- `eval_prompts/` — judge rubrics: `safety.xml`, `correctness.xml`, `tone.xml`
- `runs/` — eval output YAML (gitignored)
- `cache/` — Wikipedia response cache (gitignored)
- `main.py` — original bare Anthropic ping; the starting scaffold, superseded by `ask_question.py`
- `edit_gsheets.py` — unrelated helper, not part of this project
- `pyproject.toml` — uv project config and dependencies
- `secrets.yaml.example` — template; copy to `secrets.yaml` (gitignored)
- `PLAN.md` — design notes for the first vertical slice
- `CLAUDE.md` — working agreement and hard constraints from the brief
