from pathlib import Path

import click
import yaml
from anthropic import Anthropic

SECRETS_PATH = Path(__file__).parent / "secrets.yaml"
DEFAULT_MODEL = "claude-opus-4-7"


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


@click.command()
@click.argument("prompt")
@click.option("--model", default=DEFAULT_MODEL, show_default=True, help="Claude model ID.")
@click.option("--max-tokens", default=1024, show_default=True, type=int)
def cli(prompt: str, model: str, max_tokens: int) -> None:
    """Send PROMPT to Claude and print the reply."""
    client = Anthropic(api_key=load_api_key())
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "text":
            click.echo(block.text)


if __name__ == "__main__":
    cli()
