"""Append a CSV row to a Google Sheet, looked up by URL, ID, or filename."""

import csv
import io

import click
import gspread


def open_sheet(gc: gspread.Client, ref: str) -> gspread.Spreadsheet:
    if ref.startswith(("http://", "https://")):
        return gc.open_by_url(ref)
    # Sheet IDs are 40+ chars of [A-Za-z0-9_-] with no spaces.
    if len(ref) >= 40 and " " not in ref and "/" not in ref:
        return gc.open_by_key(ref)
    return gc.open(ref)


@click.command()
@click.argument("sheet_ref", metavar="SHEET")
@click.argument("csv_row", metavar="CSV_ROW")
def main(sheet_ref: str, csv_row: str) -> None:
    """Append CSV_ROW as a new row to SHEET (URL, ID, or filename)."""
    # csv.reader handles quoted commas, e.g. '"hello, world",42'
    values = next(csv.reader(io.StringIO(csv_row)))

    gc = gspread.oauth()
    worksheet = open_sheet(gc, sheet_ref).sheet1
    # table_range="A1" anchors the API's table-detection at column A; without it,
    # pre-existing formatting in B+ can make appends start at column B and drop the
    # first cell of every row.
    # USER_ENTERED lets Sheets parse dates/numbers/formulas like a human would.
    worksheet.append_row(
        values, value_input_option="USER_ENTERED", table_range="A1"
    )
    click.echo(f"Appended {len(values)} cells to {sheet_ref!r}")


if __name__ == "__main__":
    main()
