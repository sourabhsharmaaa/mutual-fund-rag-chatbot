"""
indmoney_scraper.py
-------------------
Scrapes IndMoney mutual-fund detail pages (React SPA).

Handles:
  URL 1  — PPFCF  scheme page
  URL 2  — PPTSF  scheme page
  URL 3  — PPCHF  scheme page
  URL 4  — PPLF   scheme page
  URL 13 — PPFAS AMC overview page
"""

from __future__ import annotations

import re
from typing import Any

from playwright.async_api import Page

from .base_scraper import BaseScraper, SELECTOR_TIMEOUT_MS


class IndMoneySchemeScraper(BaseScraper):
    """
    Scraper for IndMoney individual mutual-fund pages.
    These pages are React SPAs; data is injected after network calls settle.

    Strategy:
      1. Wait for a stable anchor text ("Expense Ratio") to appear.
      2. Walk the DOM using XPath / text-locators — NO hardcoded CSS classes.
      3. For each target label, grab the adjacent sibling value element.
    """

    # Labels exactly as they appear on IndMoney fund pages
    FIELD_LABELS = [
        ("expense_ratio",  "Expense Ratio"),
        ("exit_load",      "Exit Load"),
        ("min_sip_amount", "Min. SIP Amount"),
        ("fund_size_aum",  "Fund Size"),
        ("riskometer",     "Risk"),
        ("benchmark",      "Benchmark"),
        ("fund_manager",   "Fund Manager"),
        ("category",       "Category"),
        ("lock_in_period", "Lock-in Period"),
    ]

    async def extract(self, page: Page, url: str) -> dict[str, Any]:
        data: dict[str, Any] = {field: "NA" for field, _ in self.FIELD_LABELS}

        # Wait for page to hydrate — Expense Ratio label is a reliable anchor
        try:
            await page.wait_for_selector(
                "text=Expense Ratio",
                state="visible",
                timeout=SELECTOR_TIMEOUT_MS,
            )
        except Exception:
            # If page never shows this label, return all NA
            return data

        for field_key, label_text in self.FIELD_LABELS:
            data[field_key] = await self._extract_labeled_value(page, label_text)

        # Fund Manager may be a list — try to collect all names
        data["fund_manager"] = await self._extract_fund_managers(page)

        return data

    async def _extract_labeled_value(self, page: Page, label_text: str) -> str:
        """
        Pattern: <element>Label Text</element><element>Value</element>
        Uses text-locator then XPath sibling traversal.
        Falls back through several XPath strategies.
        """
        strategies = [
            # Strategy 1: exact text match → next sibling (skip script/style)
            (
                "xpath",
                f"//*[normalize-space(text())='{label_text}']/following-sibling::*[not(self::script or self::style)][1]",
            ),
            # Strategy 2: element containing the text → parent → second child
            (
                "xpath",
                f"//*[normalize-space(text())='{label_text}']/../*[2]",
            ),
            # Strategy 3: get_by_text (Playwright built-in) → parent's last child
            (
                "playwright",
                label_text,
            ),
        ]

        for strategy_type, selector in strategies:
            try:
                if strategy_type == "xpath":
                    loc = page.locator(f"xpath={selector}")
                    val = await self.safe_text(loc)
                    if val != "NA" and val != label_text:
                        return val
                elif strategy_type == "playwright":
                    # walk up to parent and grab adjacent text
                    parent = page.get_by_text(selector, exact=True).locator("..")
                    count = await parent.count()
                    if count > 0:
                        # Get all direct child text nodes
                        children = parent.locator("> *")
                        n = await children.count()
                        for i in range(1, n):  # skip first child (the label)
                            val = await BaseScraper.safe_text(children.nth(i))
                            if val != "NA" and val != selector:
                                return val
            except Exception:  # noqa: BLE001
                continue

        return "NA"

    async def _extract_fund_managers(self, page: Page) -> list[str] | str:
        """
        Fund manager names may appear as separate spans under a single parent.
        Try to collect all names; fall back to single-string extraction.
        """
        try:
            # Locate the Fund Manager label container
            label = page.get_by_text("Fund Manager", exact=True)
            count = await label.count()
            if count == 0:
                return "NA"

            # Try getting all sibling/child text elements
            parent = label.locator("xpath=../..")
            manager_texts = await parent.locator("xpath=.//*[not(self::script)][normalize-space(text())]").all_text_contents()

            names = []
            skip_next = False
            for t in manager_texts:
                t = t.strip()
                if not t:
                    continue
                if "Fund Manager" in t:
                    skip_next = False
                    continue
                # Heuristic: manager names are typically 2–4 words, title-case
                if re.match(r"^[A-Z][a-z]+(?:\s[A-Z][a-z]+){1,3}$", t):
                    names.append(t)

            if names:
                return names

        except Exception:  # noqa: BLE001
            pass

        # Fallback: return as plain string
        return await self._extract_labeled_value(page, "Fund Manager")


class IndMoneyAmcScraper(BaseScraper):
    """
    Scraper for the IndMoney AMC overview page (URL 13).
    Extracts AMC-level information and scheme list.
    """

    async def extract(self, page: Page, url: str) -> dict[str, Any]:
        data: dict[str, Any] = {
            "amc_name": "NA",
            "aum_total": "NA",
            "schemes_listed": [],
        }

        # Wait for page to render
        try:
            await page.wait_for_selector(
                "text=Parag Parikh",
                state="visible",
                timeout=SELECTOR_TIMEOUT_MS,
            )
        except Exception:
            return data

        # AMC name — look for largest heading
        try:
            h1 = page.locator("h1").first
            data["amc_name"] = await self.safe_text(h1, "Parag Parikh Mutual Fund")
        except Exception:
            data["amc_name"] = "Parag Parikh Mutual Fund"

        # AUM total from the page stats
        data["aum_total"] = await self._extract_labeled_value(page, "AUM")

        # Scheme names listed on the AMC page
        try:
            scheme_links = page.get_by_text("Parag Parikh", exact=False)
            data["schemes_listed"] = await self.safe_all_text(scheme_links)
        except Exception:
            pass

        return data

    async def _extract_labeled_value(self, page: Page, label_text: str) -> str:
        try:
            xpath = f"xpath=//*[normalize-space(text())='{label_text}']/following-sibling::*[not(self::script or self::style)][1]"
            loc = page.locator(xpath)
            return await self.safe_text(loc)
        except Exception:
            return "NA"
