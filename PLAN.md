# Plan: end-to-end Claude + Wikipedia QA + eval skeleton

## Context

The take-home brief (`Prompt_Eng_Take-Home_Assignment.pdf`) asks for a Claude agent with a `search_wikipedia(query: str)` tool, plus an eval suite. This plan covers the **first vertical slice**: agent loop + eval driver. Question set, judge rubrics, and prompt iterations are explicit follow-up work the user drives.

Working agreement: user makes the design calls; Claude implements. See `CLAUDE.md`.

## Decisions locked in

- **Wikipedia source:** live MediaWiki API + on-disk cache (`cache/wikipedia/{search,article}/`).
- **Tool surface:** single `search_wikipedia(query: str)` per the brief. The query string is overloaded inside the one tool: plain query → search-with-intros (top 5); `"article: <title>"` → full-text article fetch. Tool description teaches the workflow.
- **Models:** `ask_question` defaults to Sonnet 4.6 (`--model haiku|sonnet|opus`). The judge in `run_eval` always uses Opus 4.7.
- **Grading:** LLM-as-judge, one prompt file per dimension under `eval_prompts/` (e.g. `safety.xml`, `correctness.xml`, `tone.xml`). The judge MUST end its response with `<score>N</score>`; `run_eval` extracts the last such tag. Range chosen by the prompt author per dimension.
- **Eval architecture:** `run_eval` invokes `ask_question.py` as a **subprocess** per question. Buys full isolation between the eval and the artifact-under-test (no shared HTTP clients, no shared module globals, no shared cache handles), trivial parallelism via subprocess pool, contained crashes, and a clean black-box contract (the YAML output schema).
- **Language / tooling:** Python via `uv`.

## Components

### ✅ `wikipedia.py`
Two modes inside one tool. Plain query → top-5 search hits with intro extracts (`generator=search`, `exintro=true`). `"article: <title>"` → full plain-text article (`titles=`, no `exintro`, `redirects=1` so common variants resolve). File cache keyed on `sha256(strip+lower(query))`, split by mode.

### ✅ `ask_question.py`
Single-question CLI. Tool-use loop with `MAX_ITERATIONS=10`. Inputs: `prompt`, `--system-prompt-file` (optional), `--model haiku|sonnet|opus`, `--max-tokens`, `--output` (YAML). Output payload: response, tool log, usage, stop reason, iteration count, the system prompt, the model ID.

### ← `run_eval.py` (this slice)

Inputs:
- `--system-prompt-file <path>` (required) — passed through unchanged to each subprocess `ask_question` call.
- `--questions <path>` (required) — YAML list of `{question, category}` (both required per item).
- `--ask-model haiku|sonnet|opus` (optional, default sonnet) — passed through to `ask_question`. The judge model is hardcoded to Opus.
- `--output <path>` (optional, defaults to `runs/{timestamp}.yaml`).

Per question:
1. `subprocess.run([sys.executable, "ask_question.py", question, "--system-prompt-file", ..., "--model", ..., "--output", tmpfile])`. Parse the tmpfile YAML.
2. For each eval type in `EVAL_TYPES = ["safety", "correctness", "tone"]`:
   - Opus judge call. System message = the XML file's verbatim contents. User message = a structured `<question>...</question><category>...</category><answer>...</answer><tool_calls>...</tool_calls>` block built by `run_eval`.
   - Extract `<score>N</score>` (last tag wins; `None` if unparseable — judge text preserved for inspection).

Output YAML:
```yaml
meta:
  timestamp: ...
  ask_model: claude-sonnet-4-6
  judge_model: claude-opus-4-7
  system_prompt_file: ...
  system_prompt: |
    <verbatim file contents>
  questions_file: ...
  eval_prompts:
    safety: |
      <verbatim>
    correctness: |
      <verbatim>
    tone: |
      <verbatim>
results:
  - question: ...
    category: ...
    answer: ...
    tool_log: [...]
    ask_usage: {input_tokens, output_tokens}
    ask_stop_reason: ...
    ask_iterations: ...
    scores: {safety: 4, correctness: 5, tone: 3}
    judge_responses: {safety: "...", correctness: "...", tone: "..."}
    judge_usage: {safety: {...}, correctness: {...}, tone: {...}}
aggregates:
  safety: {min, p05, p25, p50, p75, p95, max, mean, n}
  correctness: {...}
  tone: {...}
```

## File layout

```
wikipedia_eval/
  wikipedia.py            ✅ MediaWiki client + cache
  ask_question.py         ✅ agent loop + CLI
  run_eval.py             ← this slice
  eval_prompts/           ← user authors; placeholders shipped for smoke test
    safety.xml
    correctness.xml
    tone.xml
  questions.yaml          ← user authors; placeholder shipped
  system_prompt.txt       ← user authors; placeholder shipped
  cache/, runs/           gitignored
```

## Out of scope for this slice

- Authoring real eval prompts, real question set, real system prompt — placeholders only.
- Iterating on the system prompt against eval results — done after the skeleton runs.
- Parallel subprocess execution — sequential first cut. Before turning on `--workers N`, harden `wikipedia.py` cache writes (write-tmp-then-`os.replace`) so concurrent subprocesses can't tear cache files.
- Cosmetic cleanup: dropping `gspread` dep, deleting `main.py`.

## Verification

1. `uv run run_eval.py --system-prompt-file system_prompt.txt --questions questions.yaml` — completes, writes `runs/*.yaml`, prints aggregate scores.
2. Inspect the YAML: every question has scores for safety/correctness/tone; aggregates compute; tool transcripts present; system prompt and all three eval prompts inlined verbatim under `meta`.
3. Delete `cache/`, re-run, confirm equivalent results (cache fills fresh).
