"""Generate clearly labelled SYNTHETIC listings for demos and tests.

    python -m scraper.synthetic --out demo.json [--count 60] [--revision 0]

Every title starts with "[SYNTHETIC]", organisations are fictional ("Example ..."), bid
numbers use the reserved "SYN/" prefix and no record has a source URL. Dates are relative to
the generation time so a demo never shows only closed listings. ``--revision N`` re-generates
the same ids with some deadlines extended and titles amended, so importing revision 1 after
revision 0 demonstrates change detection.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import UTC, datetime, timedelta
from typing import Any

ITEMS = (
    "Office chairs",
    "LED tube lights",
    "Desktop computers",
    "Facility cleaning service",
    "Water purifiers",
    "Security guard service",
    "A4 copier paper",
    "Laboratory glassware",
    "Diesel generator AMC",
    "Ambulance hiring service",
    "Steel almirahs",
    "Network switches",
)
ORGS = (
    ("Example Ministry of Infrastructure", "Example Department of Roads"),
    ("Example Ministry of Health", "Example Directorate of Hospitals"),
    ("Example Ministry of Education", "Example Board of Schools"),
    (None, "Example Municipal Corporation"),
    ("Example Ministry of Railways", None),
)
SERVICES = {
    "Facility cleaning service",
    "Security guard service",
    "Diesel generator AMC",
    "Ambulance hiring service",
}


def generate(
    count: int = 60, revision: int = 0, now: datetime | None = None, seed: int = 20261017
) -> list[dict[str, Any]]:
    now = (now or datetime.now(tz=UTC)).replace(minute=0, second=0, microsecond=0)
    rng = random.Random(seed)  # noqa: S311 - not security sensitive
    rows: list[dict[str, Any]] = []
    for n in range(1, count + 1):
        item = ITEMS[rng.randrange(len(ITEMS))]
        ministry, department = ORGS[rng.randrange(len(ORGS))]
        published = now - timedelta(days=rng.randint(0, 10), hours=rng.randint(0, 20))
        deadline = now + timedelta(days=rng.randint(-3, 25), hours=rng.randint(0, 20))
        title = f"[SYNTHETIC] {item} — demo lot {n}"
        if revision and n % 7 == 0:
            deadline += timedelta(days=5 * revision)  # simulated deadline extension
        if revision and n % 11 == 0:
            title += f" (amended r{revision})"
        rows.append(
            {
                "source_id": f"SYN-{n:05d}",
                "bid_number": f"SYN/{now.year}/B/{n:06d}",
                "title": title,
                "ministry": ministry,
                "department": department,
                "category": "Services" if item in SERVICES else "Products",
                "listing_type": "Bid" if n % 4 else "Reverse Auction",
                # Some fields deliberately missing to exercise "Not available" handling.
                "quantity": None if n % 9 == 0 else rng.randint(1, 500),
                "published_at": published.isoformat(),
                "deadline": None if n % 13 == 0 else deadline.isoformat(),
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scraper.synthetic", description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--revision", type=int, default=0)
    args = parser.parse_args(argv)
    if not 1 <= args.count <= 5000:
        parser.error("--count must be between 1 and 5000")
    payload = {
        "notice": "SYNTHETIC DEMONSTRATION DATA. These are not real GeM listings.",
        "records": generate(args.count, args.revision),
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
