# wikipedia_eval

Take-home: build a Claude + Wikipedia question-answering system and an eval suite that measures how well it works. Brief in `Prompt_Eng_Take-Home_Assignment.pdf`.

## Working agreement

- **The user drives technical decisions.** Surface options and tradeoffs; do not pick architecture, libraries, eval methodology, or data sources unilaterally. Implement once they choose.
- **Language: Python.** Managed with `uv` (see `pyproject.toml`). Run scripts via `uv run …`.
- **Scope discipline.** The brief targets 1–2 hours of work (8h hard limit). Prefer the smallest thing that demonstrates the idea over breadth. Depth on prompt quality and eval design beats sprawling features.

## Hard constraints from the brief

- Must use an **Anthropic model via the Anthropic API**. Record which model is used in the writeup.
- **Must NOT use hosted search / RAG tools** (Anthropic `web_search`, OpenAI browsing, Perplexity, etc.). The retrieval layer has to be built here.
- The model's only retrieval affordance is a `search_wikipedia(query: str)` tool we define.
- Wikipedia source is open (live MediaWiki API, dump, local index, …) — user chooses.
- Focus is **prompt quality and eval design**, not a production-grade search stack.

## Deliverables to keep in mind

1. Runnable prototype (CLI / script / notebook) with setup instructions and a demo mode.
2. Code in this repo.
3. Design rationale (short written doc + ~5 min video) covering prompt approach, eval design, what worked / failed, iterations, time spent.

Also submit Claude Code / Claude.ai transcripts — keep work attributable.

## Repo state

- `main.py` — current scaffold: thin CLI that sends a prompt to Claude. Starting point, not the final shape.
- `secrets.yaml` (gitignored) holds `anthropic_api_key`; template in `secrets.yaml.example`.
- `edit_gsheets.py` — unrelated helper, ignore unless asked.
