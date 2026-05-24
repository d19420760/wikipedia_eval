# Plan: end-to-end Claude + Wikipedia QA + eval skeleton

## Context

The take-home brief (`Prompt_Eng_Take-Home_Assignment.pdf`) asks for a Claude agent with a `search_wikipedia(query: str)` tool, plus an eval suite. Right now the repo is just scaffolding: a bare `main.py` that pings the Anthropic API with no system prompt and no tools.

The goal of this plan is the **first vertical slice only**: a working agent loop, a single-question driver, and a multi-question eval driver that scores with an LLM judge. The question set, judge rubric, eval categories, and prompt iterations are all explicit follow-up work the user will drive once this skeleton runs.

Working agreement: user makes the design calls; Claude implements. See `CLAUDE.md`.

## Decisions locked in

- **Wikipedia source:** live MediaWiki API + on-disk cache keyed on the query. Cache makes re-running the suite cheap and reproducible.
- **Grading:** LLM-as-judge. Rubric and categories deferred to a later step.
- **Language / tooling:** Python via `uv` (already set up).
- **Model:** parameterized via a `--model` flag; default `claude-sonnet-4-6` for a reasonable cost/quality point during eval iteration. Easy to swap.

## Approach

Three units of code, sharing one agent loop:

1. **`wikipedia.py`** — `search_wikipedia(query: str) -> list[dict]`
   - Hit the MediaWiki REST/Action API: search endpoint for top-N hits, plus a follow-up call (or `prop=extracts`) to grab the lead extract for each hit so the model has enough text to answer in one tool call.
   - Wrap the call with a file-based cache: `cache/wikipedia/{sha256(normalized_query)}.json`. Cache hit → return cached payload; miss → fetch, write, return.
   - `cache/` gets gitignored.

2. **`agent.py`** — the shared tool-use loop
   - Defines the `search_wikipedia` tool schema for the Anthropic API.
   - Holds a placeholder system prompt (short, plain — "answer using Wikipedia, cite sources, say when you can't find it"). Deliberately under-engineered; the user will iterate on this against eval results.
   - Runs the loop: send messages → if response has `tool_use`, execute via `wikipedia.search_wikipedia`, append `tool_result`, repeat → stop when the model returns a final text reply or a max-iteration cap is hit.
   - Returns the final answer plus a structured trace (tool calls made, queries used, iteration count) so callers can show "whether search was used" — which the brief explicitly asks for.

3. **`ask_question.py`** — single-question CLI driver
   - `uv run ask_question.py "Who wrote Beloved?"`
   - Prints the answer and a compact trace (tools called, queries).
   - Replaces the current `main.py` (delete or repurpose it — the bare-call scaffold is no longer needed).

4. **`run_eval.py`** — eval suite driver
   - Reads `questions.yaml` (created as an empty stub here — populated by the user in the next step).
   - Question schema (kept loose so the user can extend with `category`, `expected`, etc. without churn):
     ```yaml
     - id: q1
       question: "..."
       notes: "..."   # optional, fed to judge as reference
     ```
   - For each question: run the agent → call the LLM judge → collect score + judge reasoning + trace.
   - Judge: a separate Anthropic call with a minimal placeholder rubric (pass/fail + 1-sentence reason). Explicit TODO comment that the user will replace this with the real rubric and dimensions.
   - Output: a JSON/JSONL results file under `runs/{timestamp}.jsonl` plus a brief stdout summary (counts, pass rate). JSONL so future runs are easy to diff.

### File layout after this slice

```
wikipedia_eval/
  agent.py            # tool-use loop + tool schema + (placeholder) system prompt
  wikipedia.py        # search_wikipedia + disk cache
  ask_question.py     # single-question CLI (replaces main.py)
  run_eval.py         # eval-suite CLI
  questions.yaml      # stub; user fills in
  cache/              # gitignored
  runs/               # gitignored
  pyproject.toml      # add: requests (for MediaWiki). Keep anthropic/click/pyyaml.
  .gitignore          # add cache/ and runs/
```

The existing `secrets.yaml` loader logic in `main.py` is the only reusable piece — lift it into `agent.py` (or a 5-line `secrets.py`) and drop `main.py`.

## Explicitly out of scope for this slice

- Writing the question set (user does this after the skeleton runs).
- Defining categories.
- Designing the real judge rubric / dimensions.
- Iterating on the system prompt.
- Pruning `gspread` from `pyproject.toml` (cosmetic; do later when readying the deliverable).

These are the user's next steps after this slice — the plan ordering matches their stated workflow.

## Verification

End-to-end smoke test once implemented:

1. `uv sync` (picks up `requests`).
2. `uv run ask_question.py "What year did the Eiffel Tower open?"` — should produce an answer, show ≥1 `search_wikipedia` tool call in the trace, and create a file under `cache/wikipedia/`.
3. Re-run the same question → second run should be visibly faster and add no new cache files (cache hit).
4. Add 2 placeholder rows to `questions.yaml`, then `uv run run_eval.py` — should produce a `runs/*.jsonl` with one record per question, each containing answer + judge verdict + trace.
5. Inspect the JSONL by hand to confirm shape is sane for downstream analysis.

If all five pass, the skeleton is ready for the user's next phase (question set → category design → judge rubric → prompt iteration).
