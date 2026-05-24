"""Run the eval suite: subprocess ask_question.py per question, score with an LLM judge.

Architecture: each question is answered by `ask_question.py` invoked as a subprocess,
keeping the artifact-under-test fully isolated from the eval driver. The judge runs
in-process here (the evaluator, not the artifact). Judge always uses Opus.
"""

import re
import statistics
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import click
import yaml
from anthropic import Anthropic

from ask_question import DEFAULT_TEMPERATURE, MODEL_IDS, load_api_key

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


def _str_block_representer(dumper, data):
    """Render multi-line strings as block scalars (|) instead of escaped one-liners."""
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(str, _str_block_representer, Dumper=yaml.SafeDumper)

ROOT = Path(__file__).parent
ASK_QUESTION_PATH = ROOT / "ask_question.py"
EVAL_PROMPT_DIR = ROOT / "eval_prompts"
RUNS_DIR = ROOT / "runs"

JUDGE_MODEL = "claude-opus-4-7"
JUDGE_MAX_TOKENS = 2048
EVAL_TYPES = ["safety", "correctness", "tone"]
DEFAULT_ASK_MODEL = "sonnet"
DEFAULT_WORKERS = 1
SCORE_RE = re.compile(r"<score>\s*(-?\d+(?:\.\d+)?)\s*</score>", re.IGNORECASE)


def _extract_score(text: str) -> float | None:
    matches = SCORE_RE.findall(text)
    if not matches:
        return None
    try:
        return float(matches[-1])
    except ValueError:
        return None


def _aggregates(values: list) -> dict:
    clean = [v for v in values if v is not None]
    keys = ("min", "p05", "p25", "p50", "p75", "p95", "max", "mean")
    if not clean:
        out = {k: None for k in keys}
        out["n"] = 0
        return out
    if len(clean) == 1:
        v = clean[0]
        return {k: v for k in keys} | {"n": 1}
    qs = statistics.quantiles(clean, n=100, method="inclusive")
    return {
        "min": min(clean),
        "p05": qs[4],
        "p25": qs[24],
        "p50": qs[49],
        "p75": qs[74],
        "p95": qs[94],
        "max": max(clean),
        "mean": statistics.fmean(clean),
        "n": len(clean),
    }


def _run_ask_question(
    question: str,
    system_prompt_file: Path,
    ask_model: str,
    temperature: float | None,
) -> dict:
    """Run ask_question.py as a subprocess; return its parsed YAML payload or an error dict."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tf:
        tmp_path = Path(tf.name)
    try:
        args = [
            sys.executable,
            str(ASK_QUESTION_PATH),
            question,
            "--system-prompt-file", str(system_prompt_file),
            "--model", ask_model,
            "--output", str(tmp_path),
        ]
        if temperature is not None:
            args.extend(["--temperature", str(temperature)])
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode != 0:
            return {
                "_error": f"ask_question exited {proc.returncode}",
                "_stderr": (proc.stderr or "").strip(),
            }
        try:
            return yaml.safe_load(tmp_path.read_text(encoding="utf-8")) or {}
        except FileNotFoundError:
            return {
                "_error": "ask_question produced no output file",
                "_stderr": (proc.stderr or "").strip(),
            }
    finally:
        tmp_path.unlink(missing_ok=True)


def _build_judge_user_message(question: dict, ask_payload: dict) -> str:
    tool_log = ask_payload.get("tool_log") or []
    if not tool_log:
        tool_lines = ["(no Wikipedia searches were performed)"]
    else:
        tool_lines = []
        for i, call in enumerate(tool_log, start=1):
            titles = ", ".join(call.get("result_titles") or []) or "(no results)"
            tool_lines.append(
                f"{i}. query={call.get('query')!r} -> {call.get('num_results', 0)} hits: {titles}"
            )
    parts = [
        "<question>", question["question"], "</question>",
        "",
        "<category>", str(question.get("category", "")), "</category>",
        "",
        "<answer>", ask_payload.get("response") or "(empty)", "</answer>",
        "",
        "<tool_calls>",
        *tool_lines,
        "</tool_calls>",
    ]
    return "\n".join(parts)


def _judge(
    client: Anthropic,
    eval_prompt: str,
    user_message: str,
    temperature: float | None,
) -> dict:
    kwargs = {
        "model": JUDGE_MODEL,
        "max_tokens": JUDGE_MAX_TOKENS,
        "system": eval_prompt,
        "messages": [{"role": "user", "content": user_message}],
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    resp = client.messages.create(**kwargs)
    text = "\n".join(b.text for b in resp.content if b.type == "text")
    return {
        "score": _extract_score(text),
        "response": text,
        "usage": {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
        },
    }


def _process_one(
    q: dict,
    system_prompt_file: Path,
    ask_model: str,
    temperature: float | None,
    eval_prompts: dict[str, str],
    judge_client: Anthropic,
) -> tuple[dict, dict]:
    """Run a single question end-to-end. Returns (result_record, ask_payload)."""
    ask_payload = _run_ask_question(q["question"], system_prompt_file, ask_model, temperature)
    result = {
        "question": q["question"],
        "category": q["category"],
        "answer": ask_payload.get("response"),
        "tool_log": ask_payload.get("tool_log") or [],
        "ask_usage": ask_payload.get("usage"),
        "ask_stop_reason": ask_payload.get("stop_reason"),
        "ask_iterations": ask_payload.get("iterations"),
        "ask_error": ask_payload.get("_error"),
        "scores": {},
        "judge_responses": {},
        "judge_usage": {},
    }
    if "_error" in ask_payload:
        for et in EVAL_TYPES:
            result["scores"][et] = None
    else:
        user_message = _build_judge_user_message(q, ask_payload)
        for et in EVAL_TYPES:
            judge_result = _judge(judge_client, eval_prompts[et], user_message, temperature)
            result["scores"][et] = judge_result["score"]
            result["judge_responses"][et] = judge_result["response"]
            result["judge_usage"][et] = judge_result["usage"]
    return result, ask_payload


@click.command()
@click.option(
    "--system-prompt-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="System prompt for the agent being evaluated.",
)
@click.option(
    "--questions",
    "questions_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="YAML list of {question, category} items.",
)
@click.option(
    "--ask-model",
    type=click.Choice(list(MODEL_IDS), case_sensitive=False),
    default=DEFAULT_ASK_MODEL,
    show_default=True,
    help="Model used by ask_question (the artifact under evaluation). The judge always uses Opus.",
)
@click.option(
    "--temperature",
    default=DEFAULT_TEMPERATURE,
    type=float,
    help="Sampling temperature; applied to both the agent and the judge. Default: not sent (Claude 4.x deprecated this param).",
)
@click.option(
    "--workers",
    default=DEFAULT_WORKERS,
    show_default=True,
    type=int,
    help="Max parallel question workers (each is a subprocess + 3 judge calls).",
)
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="YAML output path. Default: runs/{timestamp}.yaml.",
)
def cli(
    system_prompt_file: Path,
    questions_file: Path,
    ask_model: str,
    temperature: float | None,
    workers: int,
    output: Path | None,
) -> None:
    """Run the eval suite."""
    eval_prompts: dict[str, str] = {}
    for et in EVAL_TYPES:
        path = EVAL_PROMPT_DIR / f"{et}.xml"
        if not path.exists():
            raise click.ClickException(f"Missing eval prompt: {path}")
        eval_prompts[et] = path.read_text(encoding="utf-8")

    questions = yaml.safe_load(questions_file.read_text(encoding="utf-8"))
    if not isinstance(questions, list) or not questions:
        raise click.ClickException(f"{questions_file} must be a non-empty YAML list")
    for i, q in enumerate(questions, start=1):
        if not isinstance(q, dict) or "question" not in q or "category" not in q:
            raise click.ClickException(
                f"Question {i} in {questions_file} must have `question` and `category` fields"
            )

    system_prompt_text = system_prompt_file.read_text(encoding="utf-8")
    # Anthropic SDK uses httpx under the hood, which is thread-safe; one client
    # is fine across worker threads.
    judge_client = Anthropic(api_key=load_api_key())

    results: list = [None] * len(questions)
    n = len(questions)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = {
            ex.submit(
                _process_one,
                q, system_prompt_file, ask_model, temperature, eval_prompts, judge_client,
            ): (i, q)
            for i, q in enumerate(questions)
        }
        for fut in as_completed(futures):
            i, q = futures[fut]
            try:
                result, ask_payload = fut.result()
            except Exception as e:
                result = {
                    "question": q["question"],
                    "category": q["category"],
                    "answer": None,
                    "tool_log": [],
                    "ask_usage": None,
                    "ask_stop_reason": None,
                    "ask_iterations": None,
                    "ask_error": f"worker exception: {e!r}",
                    "scores": {et: None for et in EVAL_TYPES},
                    "judge_responses": {},
                    "judge_usage": {},
                }
                ask_payload = {"_error": str(e)}
            results[i] = result
            # Single echo call to avoid interleaving lines across worker threads.
            header = f"[{i+1}/{n}] ({q['category']}) {q['question'][:80]}"
            if "_error" in ask_payload:
                err = ask_payload["_error"]
                stderr = (ask_payload.get("_stderr") or "")[:200]
                click.echo(f"{header}\n  FAILED: {err}" + (f"\n  stderr: {stderr}" if stderr else ""))
            else:
                scores_summary = "  ".join(
                    f"{et}={result['scores'][et]}" for et in EVAL_TYPES
                )
                click.echo(f"{header}\n  {scores_summary}")

    aggregates = {
        et: _aggregates([r["scores"].get(et) for r in results])
        for et in EVAL_TYPES
    }

    if output is None:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        output = RUNS_DIR / f"{timestamp}.yaml"

    payload = {
        "meta": {
            "timestamp": datetime.now().isoformat(),
            "ask_model": MODEL_IDS[ask_model],
            "judge_model": JUDGE_MODEL,
            "temperature": temperature,
            "workers": workers,
            "system_prompt_file": str(system_prompt_file),
            "system_prompt": system_prompt_text,
            "questions_file": str(questions_file),
            "eval_prompts": eval_prompts,
        },
        "results": results,
        "aggregates": aggregates,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True)

    click.echo(f"\nWrote {output}")
    click.echo("\n=== Aggregate scores ===")
    for et in EVAL_TYPES:
        a = aggregates[et]
        if a["n"] == 0:
            click.echo(f"  {et}: (no scores)")
        else:
            click.echo(
                f"  {et}: n={a['n']} mean={a['mean']:.2f} "
                f"p50={a['p50']} range=[{a['min']}, {a['max']}]"
            )


if __name__ == "__main__":
    cli()
