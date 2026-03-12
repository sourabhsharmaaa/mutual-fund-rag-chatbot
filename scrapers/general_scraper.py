"""
general_scraper.py
------------------
Scrapes general article / knowledge pages.

Handles:
  URL 14 — IndMoney taxation article
           https://www.indmoney.com/articles/mutual-funds/mutual-fund-taxation
"""

from __future__ import annotations

import re
from typing import Any

from playwright.async_api import Page

from .base_scraper import BaseScraper, SELECTOR_TIMEOUT_MS


class TaxationArticleScraper(BaseScraper):
    """
    Scraper for the IndMoney mutual-fund taxation article.
    Extracts STCG rate, LTCG rate, ELSS tax benefit, and article summary.
    """

    # Regex patterns to find tax rates in plain text
    LTCG_PATTERNS = [
        r"(?:LTCG|long.?term capital gains?)[^.]*?(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%[^.]*?(?:LTCG|long.?term)",
    ]
    STCG_PATTERNS = [
        r"(?:STCG|short.?term capital gains?)[^.]*?(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%[^.]*?(?:STCG|short.?term)",
    ]

    async def extract(self, page: Page, url: str) -> dict[str, Any]:
        data: dict[str, Any] = {
            "article_title": "NA",
            "ltcg_rate":     "NA",
            "ltcg_details":  "NA",
            "stcg_rate":     "NA",
            "stcg_details":  "NA",
            "elss_tax_benefit": "NA",
            "article_summary":  "NA",
            "source_url": url,
        }

        # Wait for article content to load (React page)
        try:
            await page.wait_for_selector(
                "text=taxation",
                state="visible",
                timeout=SELECTOR_TIMEOUT_MS,
            )
        except Exception:
            # Try waiting just for DOM to be ready
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=20_000)
            except Exception:
                return data

        # Article title
        for title_sel in ["h1", "h2", "[class*='title']", "[class*='heading']"]:
            try:
                loc = page.locator(title_sel).first
                count = await page.locator(title_sel).count()
                if count > 0:
                    t = (await loc.text_content(timeout=5_000) or "").strip()
                    if 5 < len(t) < 200:
                        data["article_title"] = t
                        break
            except Exception:
                continue

        # Full article text for regex extraction
        body_text = "NA"
        for content_sel in ["article", "main", ".article-content", ".content", "body"]:
            try:
                count = await page.locator(content_sel).count()
                if count > 0:
                    body_text = (
                        await page.locator(content_sel).first.inner_text(timeout=15_000) or ""
                    ).strip()
                    if len(body_text) > 200:
                        break
            except Exception:
                continue

        if body_text and body_text != "NA":
            # Article summary — first 500 chars of article body
            data["article_summary"] = body_text[:500]

            # LTCG extraction
            for pattern in self.LTCG_PATTERNS:
                m = re.search(pattern, body_text, re.IGNORECASE)
                if m:
                    data["ltcg_rate"] = f"{m.group(1)}%"
                    # Grab surrounding sentence for context
                    start = max(0, m.start() - 50)
                    end = min(len(body_text), m.end() + 200)
                    data["ltcg_details"] = body_text[start:end].strip()
                    break

            # STCG extraction
            for pattern in self.STCG_PATTERNS:
                m = re.search(pattern, body_text, re.IGNORECASE)
                if m:
                    data["stcg_rate"] = f"{m.group(1)}%"
                    start = max(0, m.start() - 50)
                    end = min(len(body_text), m.end() + 200)
                    data["stcg_details"] = body_text[start:end].strip()
                    break

            # ELSS / Section 80C benefit
            elss_idx = body_text.lower().find("80c")
            if elss_idx == -1:
                elss_idx = body_text.lower().find("elss")
            if elss_idx > 0:
                data["elss_tax_benefit"] = body_text[
                    max(0, elss_idx - 50): elss_idx + 300
                ].strip()

        return data
