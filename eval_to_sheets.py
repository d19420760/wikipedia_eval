"""Publish an eval run YAML to a new tab in a Google Spreadsheet.

Layout in the new tab:
  A1:           absolute path to the eval run file
  Row 3:        Question | Answer | <one column per eval type>
  Rows 4..:     one row per question
  (blank)
  Heading:      Aggregates
  Sub-header:   stat | <one column per eval type>
  One row per stat: min, p05, p25, p50, p75, p95, max, mean, n
"""

from pathlib import Path

import click
import gspread
import yaml

STATS = ("min", "p05", "p25", "p50", "p75", "p95", "max", "mean", "n")


def open_sheet(gc: gspread.Client, ref: str) -> gspread.Spreadsheet:
    if ref.startswith(("http://", "https://")):
        return gc.open_by_url(ref)
    # Sheet IDs are 40+ chars of [A-Za-z0-9_-] with no spaces.
    if len(ref) >= 40 and " " not in ref and "/" not in ref:
        return gc.open_by_key(ref)
    return gc.open(ref)


def _col_letter(n: int) -> str:
    """1 -> A, 26 -> Z, 27 -> AA."""
    s = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        s = chr(ord("A") + rem) + s
    return s


def _cell(v):
    """Normalize a value for a Sheets cell."""
    if v is None:
        return ""
    if isinstance(v, float):
        if v.is_integer():
            return int(v)
        return round(v, 3)
    return v


def build_rows(eval_file: Path) -> tuple[list[list], int]:
    """Build the rectangular row matrix for the eval YAML. Returns (rows, n_questions)."""
    data = yaml.safe_load(eval_file.read_text(encoding="utf-8"))
    eval_types = (
        list(data.get("meta", {}).get("eval_prompts", {}).keys())
        or list(data.get("aggregates", {}).keys())
    )
    results = data.get("results", [])
    aggregates = data.get("aggregates", {})

    rows: list[list] = [
        [str(eval_file.resolve())],
        [],
        ["Question", "Answer", *eval_types],
    ]
    for r in results:
        rows.append(
            [
                r.get("question", ""),
                r.get("answer", ""),
                *[_cell(r.get("scores", {}).get(et)) for et in eval_types],
            ]
        )
    rows.append([])
    rows.append(["Aggregates"])
    rows.append(["stat", *eval_types])
    for stat in STATS:
        rows.append(
            [stat, *[_cell(aggregates.get(et, {}).get(stat)) for et in eval_types]]
        )

    max_cols = max((len(r) for r in rows), default=1)
    rows = [r + [""] * (max_cols - len(r)) for r in rows]
    return rows, len(results)


@click.command()
@click.argument("eval_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("sheet_ref", metavar="SHEET")
@click.option(
    "--sheet-name",
    default=None,
    help="Name for the new worksheet tab. Default: stem of EVAL_FILE.",
)
def main(eval_file: Path, sheet_ref: str, sheet_name: str | None) -> None:
    """Publish EVAL_FILE to a new tab in SHEET (URL, ID, or filename)."""
    rows, n_questions = build_rows(eval_file)
    max_cols = len(rows[0])

    gc = gspread.oauth()
    spreadsheet = open_sheet(gc, sheet_ref)

    base_name = sheet_name or eval_file.stem
    existing = {ws.title for ws in spreadsheet.worksheets()}
    tab_name = base_name
    n = 1
    while tab_name in existing:
        n += 1
        tab_name = f"{base_name} ({n})"

    worksheet = spreadsheet.add_worksheet(
        title=tab_name, rows=len(rows) + 5, cols=max_cols + 1
    )
    worksheet.update(
        values=rows,
        range_name=f"A1:{_col_letter(max_cols)}{len(rows)}",
        value_input_option="USER_ENTERED",
    )

    click.echo(f"Wrote {n_questions} questions + aggregates to tab {tab_name!r}")
    click.echo(f"URL: {spreadsheet.url}")


if __name__ == "__main__":
    main()
