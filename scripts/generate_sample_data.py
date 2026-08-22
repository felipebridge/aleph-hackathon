#!/usr/bin/env python
"""Generates the demo dataset: data/bank_statement.csv + ~20 sample receipt
images under data/receipts/, covering every discrepancy type the matcher
detects, several times over and across many merchants so there's enough
volume to actually work with in the web UI. See README.md section 9 for
what each scenario exercises. QVAC does the actual OCR on these images at
run time -- no pre-baked ground truth text is shipped anywhere in this repo.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RECEIPTS_DIR = DATA_DIR / "receipts"

BANK_STATEMENT_ROWS = [
    # transaction_id, date,       amount,   merchant,           description
    ("TXN-1001", "2026-08-10", "4.75", "Starbucks", "STARBUCKS STORE #4521"),
    ("TXN-1002", "2026-08-11", "459.90", "Office Depot", "OFFICE DEPOT #221"),
    ("TXN-1003", "2026-08-12", "28.50", "Uber", "UBER TRIP HELP.UBER.COM"),
    ("TXN-1004", "2026-08-13", "152.34", "Costco Wholesale", "COSTCO WHSE #0113"),
    ("TXN-1005", "2026-08-17", "610.00", "Delta Air Lines", "DELTA AIR 0062178432"),
    ("TXN-1006", "2026-08-15", "52.00", "Shell", "SHELL OIL 57443217908"),
    ("TXN-1007", "2026-08-16", "1200.00", "Wire Transfer", "INTERNATIONAL WIRE TRF REF88213"),
    ("TXN-1008", "2026-08-18", "6.50", "Vending Co", "VENDING MACHINE #12"),
    ("TXN-1009", "2026-08-19", "34.20", "Target", "TARGET T-1187"),
    ("TXN-1010", "2026-08-20", "78.42", "Whole Foods", "WHOLEFDS MKT #10289"),
    ("TXN-1011", "2026-08-23", "12.99", "Walgreens", "WALGREENS #4410"),
    ("TXN-1012", "2026-08-21", "251.67", "Home Depot", "THE HOME DEPOT #0396"),
    ("TXN-1013", "2026-08-22", "15.49", "Netflix", "NETFLIX.COM"),
    ("TXN-1014", "2026-08-22", "10.99", "Spotify", "SPOTIFY USA"),
    ("TXN-1015", "2026-08-24", "61.10", "Chevron", "CHEVRON 00312456"),
    ("TXN-1016", "2026-08-27", "342.00", "Marriott Hotel", "MARRIOTT HTL RESORT"),
    ("TXN-1017", "2026-08-26", "28.35", "FedEx", "FEDEX OFFICE #3321"),
    ("TXN-1018", "2026-08-28", "1099.00", "Apple Store", "APPLE STORE R421"),
    ("TXN-1019", "2026-08-29", "54.10", "Trader Joes", "TRADER JOE'S #113"),
    ("TXN-1020", "2026-08-30", "89.00", "AutoPay Insurance", "GEICO AUTO INSURANCE"),
    ("TXN-1021", "2026-08-30", "4.50", "ATM Fee", "ATM WITHDRAWAL FEE"),
    ("TXN-1022", "2026-08-31", "320.00", "Unknown Overseas Merchant", "POS PURCHASE INTL"),
]


@dataclass(frozen=True)
class ReceiptScenario:
    filename: str
    lines: list[str]


RECEIPT_SCENARIOS = [
    ReceiptScenario(
        "01_starbucks.png",
        [
            "Starbucks Coffee",
            "123 Market Street, San Francisco CA",
            "Store #4521",
            "--------------------------------",
            "Grande Latte                4.25",
            "Almond Milk Sub              0.50",
            "--------------------------------",
            "Subtotal                     4.75",
            "Tax                          0.00",
            "TOTAL                       $4.75",
            "08/10/2026 09:14 AM",
            "Thank you for visiting!",
        ],
    ),
    ReceiptScenario(
        "02_office_depot.png",
        [
            "Office Depot",
            "221 Business Park Dr",
            "--------------------------------",
            "Copy Paper Case             29.99",
            "Ink Cartridge Combo         16.00",
            "--------------------------------",
            "Subtotal                    45.99",
            "Tax                          0.00",
            "TOTAL                      $45.99",
            "08/11/2026 02:47 PM",
        ],
    ),
    ReceiptScenario(
        "03_uber.png",
        [
            "Uber",
            "Trip Receipt",
            "help.uber.com",
            "--------------------------------",
            "Fare                        20.00",
            "Booking Fee                  1.50",
            "Tip                           2.00",
            "--------------------------------",
            "TOTAL                      $23.50",
            "08/12/2026 07:30 PM",
        ],
    ),
    ReceiptScenario(
        "04_amazon_web_services.png",
        [
            "Amazon Web Services",
            "Invoice",
            "--------------------------------",
            "EC2 Compute Usage           64.00",
            "S3 Storage                  25.00",
            "--------------------------------",
            "TOTAL                      $89.00",
            "08/09/2026",
            "Billing Support: aws.amazon.com/support",
        ],
    ),
    ReceiptScenario(
        "05_costco.png",
        [
            "Costco Wholesale",
            "Warehouse #0113",
            "--------------------------------",
            "Organic Eggs (2)             15.98",
            "Paper Towels                 24.99",
            "Rotisserie Chicken            4.99",
            "Bulk Almonds                 45.38",
            "Household Supplies           61.00",
            "--------------------------------",
            "Subtotal                    152.34",
            "Tax                           0.00",
            "TOTAL                     $152.34",
            "08/13/2026 11:02 AM",
            "Member #88213",
        ],
    ),
    ReceiptScenario(
        "06_delta_airlines.png",
        [
            "Delta Air Lines",
            "E-Ticket Receipt",
            "--------------------------------",
            "Flight NYC-LAX              610.00",
            "--------------------------------",
            "TOTAL                     $610.00",
            "08/14/2026",
            "Confirmation: 0062178432",
        ],
    ),
    ReceiptScenario(
        "07_shell_gas_station.png",
        [
            "Shell",
            "Gas Station",
            "--------------------------------",
            "Unleaded Fuel 14.2 gal       52.00",
            "--------------------------------",
            "TOTAL                      $52.00",
            "08/15/2026 06:10 PM",
            "Pump #4",
        ],
    ),
    ReceiptScenario(
        "08_shell_gas_station_dup.png",
        [
            "Shell",
            "Gas Station",
            "--------------------------------",
            "Unleaded Fuel 14.2 gal       52.00",
            "--------------------------------",
            "TOTAL                      $52.00",
            "08/15/2026 06:10 PM",
            "Pump #4",
        ],
    ),
    ReceiptScenario(
        "09_target.png",
        [
            "Target",
            "T-1187 Market Square",
            "--------------------------------",
            "Household Goods             21.40",
            "Snacks                       9.80",
            "Batteries                    3.00",
            "--------------------------------",
            "TOTAL                      $34.20",
            "08/19/2026 04:22 PM",
        ],
    ),
    ReceiptScenario(
        "10_whole_foods.png",
        [
            "Whole Foods Market",
            "Store #10289",
            "--------------------------------",
            "Produce                     22.14",
            "Bakery                      11.90",
            "Deli Counter                18.30",
            "Wine                        26.08",
            "--------------------------------",
            "TOTAL                      $78.42",
            "08/20/2026 06:05 PM",
        ],
    ),
    ReceiptScenario(
        "11_walgreens.png",
        [
            "Walgreens",
            "Store #4410",
            "--------------------------------",
            "Vitamins                     8.99",
            "Greeting Card                4.00",
            "--------------------------------",
            "TOTAL                      $12.99",
            "08/20/2026 10:11 AM",
        ],
    ),
    ReceiptScenario(
        "12_home_depot.png",
        [
            "The Home Depot",
            "Store #0396",
            "--------------------------------",
            "Power Drill                149.00",
            "Screws Assortment           12.67",
            "Paint Roller Kit            54.00",
            "Extension Cord              36.00",
            "--------------------------------",
            "TOTAL                     $251.67",
            "08/21/2026 01:15 PM",
        ],
    ),
    ReceiptScenario(
        "13_best_buy.png",
        [
            "Best Buy",
            "Store #221",
            "--------------------------------",
            "Wireless Headphones        249.99",
            "Extended Warranty          250.00",
            "--------------------------------",
            "TOTAL                     $499.99",
            "08/21/2026 05:40 PM",
        ],
    ),
    ReceiptScenario(
        "14_netflix.png",
        [
            "Netflix",
            "Monthly Subscription",
            "--------------------------------",
            "Premium Plan                15.49",
            "--------------------------------",
            "TOTAL                      $15.49",
            "08/22/2026",
            "netflix.com/billing",
        ],
    ),
    ReceiptScenario(
        "15_spotify.png",
        [
            "Spotify",
            "Monthly Subscription",
            "--------------------------------",
            "Premium Individual          10.99",
            "--------------------------------",
            "TOTAL                      $10.99",
            "08/22/2026",
            "spotify.com/account",
        ],
    ),
    ReceiptScenario(
        "16_chevron.png",
        [
            "Chevron",
            "Station #00312456",
            "--------------------------------",
            "Unleaded Fuel 16.1 gal       61.10",
            "--------------------------------",
            "TOTAL                      $61.10",
            "08/24/2026 08:02 AM",
            "Pump #2",
        ],
    ),
    ReceiptScenario(
        "17_marriott_hotel.png",
        [
            "Marriott Hotel & Resort",
            "Folio Receipt",
            "--------------------------------",
            "Room Charge (2 nights)      280.00",
            "Resort Fee                   40.00",
            "Parking                      22.00",
            "--------------------------------",
            "TOTAL                     $342.00",
            "08/25/2026",
            "Confirmation: MR-88213",
        ],
    ),
    ReceiptScenario(
        "18_fedex.png",
        [
            "FedEx Office",
            "Store #3321",
            "--------------------------------",
            "Overnight Shipping          24.00",
            "Packaging                    4.35",
            "--------------------------------",
            "TOTAL                      $28.35",
            "08/26/2026 03:50 PM",
        ],
    ),
    ReceiptScenario(
        "19_apple_store.png",
        [
            "Apple Store",
            "Store R421",
            "--------------------------------",
            "iPad (10th gen)            999.00",
            "AppleCare+                 100.00",
            "--------------------------------",
            "TOTAL                    $1099.00",
            "08/28/2026 12:31 PM",
        ],
    ),
    ReceiptScenario(
        "20_trader_joes.png",
        [
            "Trader Joe's",
            "Store #113",
            "--------------------------------",
            "Groceries                   41.20",
            "Flowers                     12.90",
            "--------------------------------",
            "TOTAL                      $54.10",
            "08/29/2026 05:47 PM",
        ],
    ),
    ReceiptScenario(
        "21_trader_joes_dup.png",
        [
            "Trader Joe's",
            "Store #113",
            "--------------------------------",
            "Groceries                   41.20",
            "Flowers                     12.90",
            "--------------------------------",
            "TOTAL                      $54.10",
            "08/29/2026 05:47 PM",
        ],
    ),
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Monospace font lookup that degrades gracefully -- rendering is cosmetic
    only, so a missing TTF must never break sample-data generation."""
    candidates = [
        "consola.ttf",  # Windows Consolas
        "cour.ttf",  # Windows Courier New
        "DejaVuSansMono.ttf",  # common on Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "C:/Windows/Fonts/consola.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_receipt_image(scenario: ReceiptScenario, out_dir: Path) -> Path:
    """Draw a simple receipt-style PNG for the demo to point at."""
    font = _load_font(20)
    line_height = 26
    padding = 24
    width = 420
    height = padding * 2 + line_height * len(scenario.lines)

    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (width - 1, height - 1)], outline=(200, 200, 200), width=2)

    y = padding
    for line in scenario.lines:
        draw.text((padding, y), line, fill="black", font=font)
        y += line_height

    out_path = out_dir / scenario.filename
    img.save(out_path)
    return out_path


def write_bank_statement(out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["transaction_id", "date", "amount", "merchant", "description"])
        writer.writerows(BANK_STATEMENT_ROWS)
    return out_path


def main() -> None:
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)

    bank_csv_path = write_bank_statement(DATA_DIR / "bank_statement.csv")
    print(f"Wrote {bank_csv_path} ({len(BANK_STATEMENT_ROWS)} transactions)")

    for scenario in RECEIPT_SCENARIOS:
        image_path = render_receipt_image(scenario, RECEIPTS_DIR)
        print(f"Wrote {image_path.relative_to(ROOT)}")

    print(f"\nDone. {len(RECEIPT_SCENARIOS)} sample receipts in {RECEIPTS_DIR}")


if __name__ == "__main__":
    main()
