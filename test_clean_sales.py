import csv
from pathlib import Path

from clean_sales import clean_file, clean_rows, normalise_category, normalise_country, parse_date, parse_price


def test_parsers_and_normalisers():
    assert parse_date("19 Apr 2026") == "2026-04-19"
    assert parse_date("04-07-2026") == "2026-04-07"
    assert parse_price("£5.00") == 5
    assert parse_price("12.5 GBP") == 12.50
    assert normalise_category("ELECTRNICS") == "Electronics"
    assert normalise_country("uk") == "United Kingdom"


def test_clean_rows_deletes_invalid_quantities_and_exact_duplicates():
    rows = [
        {
            "order_id": "1",
            "customer_name": " A PERSON ",
            "email": "A.PERSON@example.com",
            "order_date": "08/03/2026",
            "product": "Notebook",
            "category": "stationary",
            "quantity": "2",
            "unit_price": "£3.25",
            "country": "UK",
        },
        {
            "order_id": "1",
            "customer_name": " A PERSON ",
            "email": "A.PERSON@example.com",
            "order_date": "08/03/2026",
            "product": "Notebook",
            "category": "stationary",
            "quantity": "2",
            "unit_price": "£3.25",
            "country": "UK",
        },
        {
            "order_id": "2",
            "customer_name": "B Person",
            "email": "",
            "order_date": "2026-03-08",
            "product": "Notebook",
            "category": "Stationery",
            "quantity": "-1",
            "unit_price": "3.25",
            "country": "United Kingdom",
        },
    ]
    cleaned, log = clean_rows(rows)
    assert len(cleaned) == 1
    assert cleaned[0]["customer_name"] == "A Person"
    assert cleaned[0]["unit_price"] == "3.25"
    assert sum(item["action"] == "delete" for item in log) == 2


def test_clean_file_writes_outputs(tmp_path: Path):
    source = tmp_path / "source.csv"
    source.write_text(
        "order_id,customer_name,email,order_date,product,category,quantity,unit_price,country\n"
        "1,A Person,a.person@example.com,2026-03-08,Notebook,Stationery,1,3.25,UK\n",
        encoding="utf-8",
    )
    output = tmp_path / "cleaned.csv"
    log_output = tmp_path / "log.csv"
    clean_file(source, output, log_output)
    with output.open(newline="", encoding="utf-8") as handle:
        assert list(csv.DictReader(handle))[0]["country"] == "United Kingdom"
    assert log_output.exists()


def test_identity_and_uncertain_value_rules_are_logged():
    rows = [
        {
            "order_id": "1008",
            "customer_name": "Different Person",
            "email": "hassan.ali@example.com",
            "order_date": "03-24-2026",
            "product": "Notebook",
            "category": "stationary",
            "quantity": "1",
            "unit_price": "3.25",
            "country": "United Kingdom",
        },
        {
            "order_id": "1033",
            "customer_name": "amira khan",
            "email": "amira.khanexample.com",
            "order_date": "04/04/2026",
            "product": "Notebook",
            "category": "Stationery",
            "quantity": "1",
            "unit_price": "89999.00",
            "country": "United Kingdom",
        },
    ]
    cleaned, log = clean_rows(rows)
    corrected = next(row for row in cleaned if row["order_id"] == "1008")
    outlier = next(row for row in cleaned if row["order_id"] == "1033")
    assert corrected["customer_name"] == "Hassan Ali"
    assert outlier["email"] == ""
    assert outlier["unit_price"] == "89999.00"
    assert any(item["action"] == "correct" for item in log)
    assert any(item["action"] == "flag" and item["column"] == "unit_price" for item in log)
