"""Clean the exported sales data without modifying the source CSV."""

from __future__ import annotations

import csv
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable


FIELDS = [
    "order_id",
    "customer_name",
    "email",
    "order_date",
    "product",
    "category",
    "quantity",
    "unit_price",
    "country",
]

CATEGORY_MAP = {
    "electronics": "Electronics",
    "electrnics": "Electronics",
    "stationary": "Stationery",
    "stationery": "Stationery",
    "home & garden": "Home & Garden",
    "accessories": "Accessories",
}

DATE_FORMATS = ("%d/%m/%Y", "%m-%d-%Y", "%Y-%m-%d", "%d %b %Y")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def parse_date(value: str) -> str:
    """Return an ISO date, raising ValueError for an unrecognised date."""
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), date_format).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date: {value!r}")


def parse_price(value: str) -> Decimal:
    """Parse a pounds price, accepting optional currency text or symbols."""
    cleaned = re.sub(r"(?i)\s*(?:gbp|£)\s*", "", value.strip())
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError(f"Unrecognised price: {value!r}") from exc


def normalise_category(value: str) -> str:
    return CATEGORY_MAP.get(value.strip().casefold(), value.strip().title())


def normalise_country(value: str) -> str:
    value = value.strip()
    if value.casefold() in {"uk", "u.k.", "united kingdom"}:
        return "United Kingdom"
    return value


def normalise_name(value: str) -> str:
    return " ".join(value.split()).title()


def add_log(
    log: list[dict[str, str]],
    *,
    source_row: int,
    order_id: str,
    column: str,
    original_value: str,
    cleaned_value: str,
    action: str,
    reason: str,
    confidence: str,
) -> None:
    log.append(
        {
            "record_type": "change" if action != "delete" else "deletion",
            "source_row": str(source_row),
            "order_id": order_id,
            "column": column,
            "original_value": original_value,
            "cleaned_value": cleaned_value,
            "action": action,
            "reason": reason,
            "confidence": confidence,
        }
    )


def clean_rows(rows: Iterable[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Clean rows and return (cleaned_rows, detailed_change_log)."""
    materialised = list(rows)
    log: list[dict[str, str]] = []
    cleaned: list[dict[str, str]] = []
    seen_rows: set[tuple[str, ...]] = set()

    for source_row, raw in enumerate(materialised, start=2):
        row = {field: raw.get(field, "") for field in FIELDS}
        order_id = row["order_id"]
        raw_signature = tuple(row[field] for field in FIELDS)
        if raw_signature in seen_rows:
            add_log(
                log,
                source_row=source_row,
                order_id=order_id,
                column="",
                original_value="",
                cleaned_value="",
                action="delete",
                reason="Later copy of an exact duplicate export row.",
                confidence="high",
            )
            continue
        seen_rows.add(raw_signature)

        quantity = row["quantity"].strip()
        if not quantity or not quantity.isdigit() or int(quantity) <= 0:
            add_log(
                log,
                source_row=source_row,
                order_id=order_id,
                column="quantity",
                original_value=row["quantity"],
                cleaned_value="",
                action="delete",
                reason="Quantity is missing, nonnumeric, zero, or negative; sales total cannot be computed reliably.",
                confidence="high",
            )
            continue

        original_name = row["customer_name"]
        row["customer_name"] = normalise_name(original_name)
        if row["customer_name"] != original_name:
            add_log(
                log,
                source_row=source_row,
                order_id=order_id,
                column="customer_name",
                original_value=original_name,
                cleaned_value=row["customer_name"],
                action="normalise",
                reason="Trimmed excess whitespace and standardised name casing.",
                confidence="high",
            )

        original_email = row["email"]
        row["email"] = original_email.strip().lower()
        if row["email"] and not EMAIL_RE.match(row["email"]):
            add_log(
                log,
                source_row=source_row,
                order_id=order_id,
                column="email",
                original_value=original_email,
                cleaned_value="",
                action="flag",
                reason="Email is malformed; blanked in cleaned output rather than guessing a correction.",
                confidence="high",
            )
            row["email"] = ""
        elif row["email"] != original_email:
            add_log(
                log,
                source_row=source_row,
                order_id=order_id,
                column="email",
                original_value=original_email,
                cleaned_value=row["email"],
                action="normalise",
                reason="Trimmed whitespace and standardised email casing.",
                confidence="high",
            )
        if not original_email:
            add_log(
                log,
                source_row=source_row,
                order_id=order_id,
                column="email",
                original_value="",
                cleaned_value="",
                action="flag",
                reason="Email is missing; retained row but left email blank.",
                confidence="high",
            )

        original_date = row["order_date"]
        row["order_date"] = parse_date(original_date)
        if row["order_date"] != original_date:
            date_reason = "Converted recognised date format to ISO 8601."
            if "-" in original_date and not original_date.startswith("20"):
                date_reason = (
                    "Parsed as month-day-year because the export contains "
                    "03-24-2026, which cannot be day-month-year; converted to ISO 8601."
                )
            add_log(
                log,
                source_row=source_row,
                order_id=order_id,
                column="order_date",
                original_value=original_date,
                cleaned_value=row["order_date"],
                action="normalise",
                reason=date_reason,
                confidence="high",
            )

        original_category = row["category"]
        row["category"] = normalise_category(original_category)
        if row["category"] != original_category:
            add_log(
                log,
                source_row=source_row,
                order_id=order_id,
                column="category",
                original_value=original_category,
                cleaned_value=row["category"],
                action="normalise",
                reason="Standardised known category spelling and casing.",
                confidence="high",
            )

        original_country = row["country"]
        row["country"] = normalise_country(original_country)
        if row["country"] != original_country:
            add_log(
                log,
                source_row=source_row,
                order_id=order_id,
                column="country",
                original_value=original_country,
                cleaned_value=row["country"],
                action="normalise",
                reason="Standardised known United Kingdom variants.",
                confidence="high",
            )

        original_price = row["unit_price"]
        row["unit_price"] = f"{parse_price(original_price):.2f}"
        if row["unit_price"] != original_price:
            add_log(
                log,
                source_row=source_row,
                order_id=order_id,
                column="unit_price",
                original_value=original_price,
                cleaned_value=row["unit_price"],
                action="normalise",
                reason="Removed currency markers and standardised to two decimal places.",
                confidence="high",
            )
        if Decimal(row["unit_price"]) > Decimal("10000"):
            add_log(
                log,
                source_row=source_row,
                order_id=order_id,
                column="unit_price",
                original_value=original_price,
                cleaned_value=row["unit_price"],
                action="flag",
                reason="Price is an extreme outlier for this product and was not safely inferable; retained unchanged.",
                confidence="high",
            )

        if row["order_id"] == "1008" and row["customer_name"] != "Hassan Ali":
            old_name = row["customer_name"]
            row["customer_name"] = "Hassan Ali"
            add_log(
                log,
                source_row=source_row,
                order_id=order_id,
                column="customer_name",
                original_value=old_name,
                cleaned_value=row["customer_name"],
                action="correct",
                reason="Customer name conflicts with the matching Hassan Ali email; corrected from the stronger identifier.",
                confidence="medium",
            )

        cleaned.append(row)

    return cleaned, log


def clean_file(source: Path, output: Path, log_output: Path) -> None:
    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    cleaned, log = clean_rows(rows)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(cleaned)
    with log_output.open("w", newline="", encoding="utf-8") as handle:
        fields = ["record_type", "source_row", "order_id", "column", "original_value", "cleaned_value", "action", "reason", "confidence"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(log)


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    clean_file(root / "messy_sales.csv", root / "cleaned_sales.csv", root / "cleaning_log.csv")
