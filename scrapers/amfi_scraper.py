"""
amfi_scraper.py
---------------
Scrapes AMFI India knowledge-center pages.

Handles:
  URL 11 — CAS statement page (may return 404 — handled gracefully)
  URL 12 — Riskometer definitions page (may return 404 — handled gracefully)
  URL 15 — Expense ratio definitions page (may return 404 — handled gracefully)

If a page is unavailable (404 / error), the scraper records status in the
log and returns empty data with "NA" fields — no crash.
"""

from __future__ import annotations

from typing import Any

from playwright.async_api import Page

from .base_scraper import BaseScraper


class AMFIKnowledgeScraper(BaseScraper):
    """
    Scraper for AMFI India knowledge-center / investor-corner pages.
    These are standard HTML pages when reachable.
    Falls back gracefully on 404 (handled in BaseScraper.scrape).
    """

    async def extract(self, page: Page, url: str) -> dict[str, Any]:
        data: dict[str, Any] = {
            "page_title": "NA",
            "main_content": "NA",
            "key_points": [],
            "source_url": url,
        }

        try:
            await page.wait_for_load_state("domcontentloaded", timeout=30_000)
        except Exception:
            return data

        # Page title
        try:
            title = await page.title()
            data["page_title"] = (title or "").strip() or "NA"
        except Exception:
            pass

        # Main content — try article, main, or body fallback
        content_text = "NA"
        for selector in ["article", "main", ".content", "#content", "body"]:
            try:
                loc = page.locator(selector).first
                count = await page.locator(selector).count()
                if count > 0:
                    content_text = (await loc.inner_text(timeout=10_000) or "").strip()
                    if len(content_text) > 100:
                        break
            except Exception:
                continue

        data["main_content"] = content_text[:3000] if content_text != "NA" else "NA"

        # Key bullet points — li elements in the content
        try:
            items = page.locator("li")
            texts = await self.safe_all_text(items)
            data["key_points"] = [t for t in texts if 5 < len(t) < 300][:30]
        except Exception:
            pass

        # For CAS page: look for specific procedure steps
        if "cas" in url.lower() or "statement" in url.lower():
            data["cas_procedure"] = await self._extract_cas_procedure(page)

        # For riskometer page: extract risk level definitions
        if "riskometer" in url.lower():
            data["risk_levels"] = await self._extract_risk_levels(page)

        # For expense-ratio page: extract TER/expense ratio definition
        if "expense-ratio" in url.lower() or "expense_ratio" in url.lower():
            data["expense_ratio_definition"] = await self._extract_definition(
                page, ["expense ratio", "TER", "total expense"]
            )

        return data

    async def _extract_cas_procedure(self, page: Page) -> str:
        """Extract the CAS (Consolidated Account Statement) download procedure."""
        try:
            # Look for ordered list near "CAS" or "Consolidated" heading
            heading = page.get_by_text("Consolidated Account Statement", exact=False)
            count = await heading.count()
            if count > 0:
                # Grab the following sibling ol/ul
                steps_loc = heading.locator("xpath=following::ol[1]")
                scount = await steps_loc.count()
                if scount > 0:
                    return (await steps_loc.first.inner_text(timeout=8_000) or "NA").strip()

            # Fallback: look for numbered steps in body text
            body = await page.inner_text("body")
            # Extract text near "statement" keyword
            idx = body.lower().find("statement")
            if idx > 0:
                return body[max(0, idx - 100): idx + 800].strip()
        except Exception:
            pass
        return "NA"

    async def _extract_risk_levels(self, page: Page) -> list[str]:
        """Extract the 6 SEBI riskometer levels and their definitions."""
        risk_levels = [
            "Low", "Low to Moderate", "Moderate",
            "Moderately High", "High", "Very High",
        ]
        found = []
        try:
            body = await page.inner_text("body")
            for level in risk_levels:
                if level.lower() in body.lower():
                    # Find the sentence containing this level
                    idx = body.lower().find(level.lower())
                    sentence = body[max(0, idx - 50): idx + 200].strip()
                    found.append(f"{level}: {sentence}")
        except Exception:
            pass
        return found or ["Very High", "High", "Moderately High", "Moderate", "Low to Moderate", "Low"]

    async def _extract_definition(self, page: Page, keywords: list[str]) -> str:
        """Extract text paragraphs that contain any of the given keywords."""
        try:
            body = await page.inner_text("body")
            for kw in keywords:
                idx = body.lower().find(kw.lower())
                if idx > 0:
                    return body[max(0, idx - 50): idx + 500].strip()
        except Exception:
            pass
        return "NA"
