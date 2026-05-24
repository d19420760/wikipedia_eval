"""Ask Claude a single question, with access to the search_wikipedia tool."""

import sys
from pathlib import Path

import click
import yaml
from anthropic import Anthropic

from wikipedia import search_wikipedia

# Windows consoles default to cp1252 and choke on Wikipedia titles with Unicode
# (e.g. Czech, Polish). Reconfigure stdout/stderr to UTF-8 when possible.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

SECRETS_PATH = Path(__file__).parent / "secrets.yaml"
MODEL_IDS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-7",
}
DEFAULT_MODEL = "sonnet"
DEFAULT_MAX_TOKENS = 4096
MAX_ITERATIONS = 10

SEARCH_WIKIPEDIA_TOOL = {
    "name": "search_wikipedia",
    "description": (
        "Look something up on English Wikipedia. The `query` parameter has two modes:\n"
        "\n"
        "1. SEARCH (default): pass a normal search query, e.g. \"Eiffel Tower history\". "
        "Returns the top 5 matching articles with their titles, URLs, and intro extracts "
        "(typically one paragraph each). Use this first to find which articles are "
        "relevant and to learn their exact titles.\n"
        "\n"
        "2. FULL ARTICLE: pass \"article: <exact title>\", e.g. \"article: Eiffel Tower\". "
        "Returns just that one article with its full plain-text body (can be long). "
        "Use this when the intro from search mode wasn't detailed enough — typically "
        "after a search has surfaced the right title.\n"
        "\n"
        "Typical workflow: search to find the right article(s), then request the full "
        "article only if you need details beyond the intro."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "A search query, OR \"article: <exact title>\" to fetch the full article."
                ),
            },
        },
        "required": ["query"],
    },
}


def load_api_key() -> str:
    if not SECRETS_PATH.exists():
        raise click.ClickException(
            f"Missing {SECRETS_PATH.name}. Copy secrets.yaml.example to secrets.yaml "
            "and add your Anthropic API key."
        )
    with SECRETS_PATH.open("r", encoding="utf-8") as f:
        secrets = yaml.safe_load(f) or {}
    api_key = secrets.get("anthropic_api_key")
    if not api_key:
        raise click.ClickException(
            f"`anthropic_api_key` not set in {SECRETS_PATH.name}."
        )
    return api_key


def format_search_results(results: list[dict]) -> str:
    if not results:
        return "No results."
    sections = []
    for i, r in enumerate(results, start=1):
        sections.append(
            f"## Result {i}\n"
            f"Title: {r['title']}\n"
            f"URL: {r['url']}\n"
            f"Extract: {r['extract']}"
        )
    return "\n\n".join(sections)


def run_agent(
    client: Anthropic,
    prompt: str,
    system_prompt: str | None,
    model: str,
    max_tokens: int,
) -> dict:
    """Run the tool-use loop. Returns response, tool log, usage, stop_reason, iterations."""
    messages: list[dict] = [{"role": "user", "content": prompt}]
    tool_log: list[dict] = []
    usage = {"input_tokens": 0, "output_tokens": 0}
    final_text = ""
    stop_reason = None
    iteration = 0

    for iteration in range(1, MAX_ITERATIONS + 1):
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "tools": [SEARCH_WIKIPEDIA_TOOL],
            "messages": messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        resp = client.messages.create(**kwargs)
        usage["input_tokens"] += resp.usage.input_tokens
        usage["output_tokens"] += resp.usage.output_tokens
        stop_reason = resp.stop_reason

        if stop_reason != "tool_use":
            final_text = "\n".join(b.text for b in resp.content if b.type == "text")
            break

        messages.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            if block.name == "search_wikipedia":
                query = block.input.get("query", "")
                results = search_wikipedia(query)
                tool_log.append(
                    {
                        "query": query,
                        "num_results": len(results),
                        "result_titles": [r["title"] for r in results],
                    }
                )
                content = format_search_results(results)
            else:
                content = f"Unknown tool: {block.name}"
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                }
            )
        messages.append({"role": "user", "content": tool_results})
    else:
        final_text = "(stopped: reached max iterations without final answer)"

    return {
        "response": final_text,
        "tool_log": tool_log,
        "usage": usage,
        "stop_reason": stop_reason,
        "iterations": iteration,
    }


@click.command()
@click.argument("prompt")
@click.option(
    "--system-prompt-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to a text file containing the system prompt. If omitted, no system prompt is sent.",
)
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Optional path to write the full result as YAML.",
)
@click.option(
    "--model",
    type=click.Choice(list(MODEL_IDS), case_sensitive=False),
    default=DEFAULT_MODEL,
    show_default=True,
    help="Claude model tier.",
)
@click.option("--max-tokens", default=DEFAULT_MAX_TOKENS, show_default=True, type=int)
def cli(
    prompt: str,
    system_prompt_file: Path | None,
    output: Path | None,
    model: str,
    max_tokens: int,
) -> None:
    """Ask Claude PROMPT, with access to a search_wikipedia tool."""
    system_prompt = (
        system_prompt_file.read_text(encoding="utf-8") if system_prompt_file else None
    )
    model_id = MODEL_IDS[model.lower()]

    client = Anthropic(api_key=load_api_key())
    result = run_agent(
        client=client,
        prompt=prompt,
        system_prompt=system_prompt,
        model=model_id,
        max_tokens=max_tokens,
    )

    click.echo("=== Response ===")
    click.echo(result["response"])
    click.echo()
    click.echo("=== Wikipedia tool calls ===")
    if not result["tool_log"]:
        click.echo("(none)")
    else:
        for i, call in enumerate(result["tool_log"], start=1):
            titles = ", ".join(call["result_titles"]) or "(no results)"
            click.echo(
                f"{i}. query={call['query']!r} -> {call['num_results']} hits: {titles}"
            )
    click.echo()
    click.echo("=== Token usage ===")
    u = result["usage"]
    click.echo(
        f"input: {u['input_tokens']}  output: {u['output_tokens']}  "
        f"total: {u['input_tokens'] + u['output_tokens']}  "
        f"(stop_reason={result['stop_reason']}, iterations={result['iterations']})"
    )

    if output:
        payload = {
            "prompt": prompt,
            "system_prompt": system_prompt,
            "model": model_id,
            **result,
        }
        with output.open("w", encoding="utf-8") as f:
            yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True)
        click.echo(f"\nWrote {output}")


if __name__ == "__main__":
    cli()
