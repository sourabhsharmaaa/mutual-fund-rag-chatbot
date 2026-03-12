"""
nav_fetcher.py
--------------
Fetches the latest NAV for each PPFAS fund from the AMFI public API (mfapi.in).

This is called by scrapers/runner.py during every scheduled refresh to ensure
the vector store always contains the most recent NAV data.

Scheme codes (Direct Growth plans):
  PPFCF  = 122639
  PPTSF  = 147481
  PPCHF  = 148958
  PPLF   = 143269
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# Map short_name → mfapi.in scheme code (Direct Growth plans)
SCHEME_CODES: dict[str, int] = {
    "PPFCF": 122639,   # Parag Parikh Flexi Cap Fund - Direct Growth
    "PPTSF": 147481,   # Parag Parikh ELSS Tax Saver Fund - Direct Growth
    "PPCHF": 148958,   # Parag Parikh Conservative Hybrid Fund - Direct Growth
    "PPLF":  143269,   # Parag Parikh Liquid Fund - Direct Growth
}

MFAPI_BASE = "https://api.mfapi.in/mf"


def fetch_latest_navs() -> dict[str, dict]:
    """
    Fetches the latest NAV for each PPFAS fund.

    Returns:
        {
            "PPFCF": {"nav": "89.77", "as_of": "09-Mar-2026"},
            "PPTSF": {"nav": "31.85", "as_of": "09-Mar-2026"},
            ...
        }
    """
    results: dict[str, dict] = {}

    for short_name, scheme_code in SCHEME_CODES.items():
        try:
            url = f"{MFAPI_BASE}/{scheme_code}/latest"
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())

            latest = data["data"][0]
            raw_date = latest["date"]  # Format: "09-03-2026"
            nav_value = latest["nav"]

            # Convert date to readable format: "09-Mar-2026"
            try:
                dt = datetime.strptime(raw_date, "%d-%m-%Y")
                formatted_date = dt.strftime("%d-%b-%Y")
            except ValueError:
                formatted_date = raw_date

            results[short_name] = {
                "nav": nav_value,
                "as_of": formatted_date,
            }
            logger.info("Fetched NAV for %s: ₹%s (as of %s)", short_name, nav_value, formatted_date)

        except Exception as exc:
            logger.warning("Failed to fetch NAV for %s: %s", short_name, exc)
            results[short_name] = {"nav": "NA", "as_of": "NA"}

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    navs = fetch_latest_navs()
    for fund, info in navs.items():
        print(f"{fund}: ₹{info['nav']} (as of {info['as_of']})")
