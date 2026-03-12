"""
ppfas_scraper.py
----------------
Scrapes amc.ppfas.com pages — server-rendered HTML (not a SPA).

Handles:
  URL 5  — PPFCF scheme page
  URL 6  — PPTSF scheme page
  URL 7  — PPCHF scheme page
  URL 8  — PPLF  scheme page
  URL 9  — PPFAS FAQs (routed to per-scheme FAQ pages as fallback)
  URL 10 — SID downloads page
"""

from __future__ import annotations

import re
from typing import Any

from playwright.async_api import Page

from .base_scraper import BaseScraper, SELECTOR_TIMEOUT_MS


# ---------------------------------------------------------------------------
# Scheme page scraper (URLs 5–8)
# ---------------------------------------------------------------------------

class PPFASSchemeScraper(BaseScraper):
    """
    Scraper for individual PPFAS scheme pages.
    These pages are server-rendered HTML with structured definition tables.

    Labels come from the span/td text on the page; values are adjacent siblings.
    """

    # (output_key, label_text_on_page)
    FIELD_LABELS = [
        ("scheme_name",          "Name of the Scheme"),
        ("investment_objective", "Investment Objective"),
        ("category",             "Type of the scheme"),
        ("date_of_allotment",    "Date of Allotment"),
        ("min_lumpsum_amount",   "Minimum Application Amount"),
        ("min_sip_amount",       "Minimum SIP Amount"),
        ("exit_load",            "Exit Load"),
        ("benchmark",            "Benchmark"),
        ("lock_in_period",       "Lock-in Period"),
        ("entry_load",           "Entry Load"),
        ("fund_manager",         "Fund Manager(s)"),  # Plural/Parentheses match
    ]

    async def extract(self, page: Page, url: str) -> dict[str, Any]:
        data: dict[str, Any] = {field: "NA" for field, _ in self.FIELD_LABELS}
        data["fund_manager"] = "NA"
        data["expense_ratio"] = "NA"
        data["riskometer"] = "NA"
        data["sid_link"] = "NA"
        data["source_url"] = url

        # Wait for page content — PPFAS pages load fast (static)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=30_000)
        except Exception:
            return data

        # Extract each labeled field using XPath sibling traversal
        for field_key, label_text in self.FIELD_LABELS:
            data[field_key] = await self._extract_following_text(page, label_text)

        # Fund managers — look for "Fund Manager" section heading
        data["fund_manager"] = await self._extract_fund_managers(page)

        # Riskometer — often an image alt text or nearby text
        data["riskometer"] = await self._extract_riskometer(page)

        # Expense ratio — page usually links to TER page, capture that note
        data["expense_ratio"] = await self._extract_expense_ratio(page)

        # SID direct download link
        data["sid_link"] = await self._extract_sid_link(page)

        return data

    async def _extract_following_text(self, page: Page, label_text: str) -> str:
        """
        Walk the DOM: find element with exactly `label_text`,
        then read the following sibling's text.
        Tries multiple XPath patterns for robustness.
        """
        patterns = [
            # Definition list / table row: dt + dd, th + td (skip script/style)
            f"xpath=//*[normalize-space(text())='{label_text}']/following-sibling::*[not(self::script or self::style)][1]",
            # Same but parent-relative
            f"xpath=//*[normalize-space(text())='{label_text}']/../following-sibling::*[not(self::script or self::style)][1]",
            # General: any element containing text → next element (skip script/style)
            f"xpath=//*[contains(normalize-space(text()),'{label_text}')]/following-sibling::*[not(self::script or self::style)][1]",
        ]
        for pattern in patterns:
            try:
                loc = page.locator(pattern)
                val = await self.safe_text(loc)
                # Reject if the value is identical to the label (mis-match) or if it catches unrelated sidebar links
                if val != "NA" and val != label_text and "Terms of Issue" not in val and len(val) < 500:
                    return val
            except Exception:  # noqa: BLE001
                continue
        return "NA"

    async def _extract_fund_managers(self, page: Page) -> list[str] | str:
        """Collect fund manager names from the scheme page."""
        try:
            # PPFAS typically lists fund managers in a dedicated section
            fm_section = page.get_by_text("Fund Manager", exact=False)
            count = await fm_section.count()
            if count == 0:
                return "NA"

            # Look for linked names (fund manager profile links)
            manager_links = page.locator("a[href*='fund-manager']")
            link_texts = await self.safe_all_text(manager_links)
            if link_texts:
                # Clean up: remove generic labels
                cleaned = [t for t in link_texts if len(t) > 3 and "Fund Manager" not in t]
                if cleaned:
                    return cleaned

            # Fallback: XPath sibling of "Fund Manager" label
            return await self._extract_following_text(page, "Fund Manager")
        except Exception:
            return "NA"

    async def _extract_riskometer(self, page: Page) -> str:
        """
        Riskometer text is often near an image or a label.
        Look for known risk level strings in page content.
        """
        # Try to find riskometer label text
        risk_text = await self._extract_following_text(page, "Riskometer")
        if risk_text != "NA":
            return risk_text

        # Scan alt texts of images for riskometer
        try:
            imgs = page.locator("img[alt*='risk' i], img[alt*='Risk' i]")
            alts = await imgs.evaluate_all("els => els.map(e => e.alt)")
            if alts:
                # Filter out generic 'riskometer' or 'risk' alts
                valid_alts = [a.strip() for a in alts if a.strip() and a.strip().lower() not in ["riskometer", "risk", "risk meter"]]
                if valid_alts:
                    return "; ".join(valid_alts)
        except Exception:
            pass

        # Scan page text for risk level mentions
        try:
            body_text = await page.inner_text("body")
            risk_levels = [
                "Very High", "High", "Moderately High",
                "Moderate", "Moderately Low", "Low",
            ]
            for level in risk_levels:
                if level in body_text:
                    return level
        except Exception:
            pass

        return "NA"

    async def _extract_expense_ratio(self, page: Page) -> str:
        """
        PPFAS scheme pages link to the TER page instead of showing a number.
        Return the text near "Expense Ratio" or the TER link URL as fallback.
        """
        ter_text = await self._extract_following_text(page, "Expense Ratio")
        if ter_text != "NA":
            return ter_text

        # Look for link to TER page
        try:
            ter_link = page.locator("a[href*='total-expense-ratio']")
            count = await ter_link.count()
            if count > 0:
                href = await ter_link.first.get_attribute("href")
                return f"Refer TER page: {href}"
        except Exception:
            pass

        return "NA"

    async def _extract_sid_link(self, page: Page) -> str:
        """Grab the SID/SAI download link if present on the scheme page."""
        try:
            sid_link = page.locator(
                "a[href*='ConfirmCitizenship'], a[href*='kim-sid'], a[href*='SID']"
            )
            count = await sid_link.count()
            if count > 0:
                href = await sid_link.first.get_attribute("href")
                return href or "NA"
        except Exception:
            pass
        return "NA"


# ---------------------------------------------------------------------------
# FAQs scraper — per-scheme FAQ pages (replaces URL 9 which is 404)
# ---------------------------------------------------------------------------

class PPFASFaqScraper(BaseScraper):
    """
    Scrapes FAQ pages from PPFAS schemes and the knowledge center.
    Looks specifically for questions and answers about statement download / CAS.
    """

    FAQ_KEYWORDS = [
        "statement", "download", "CAS", "account statement",
        "portfolio statement", "consolidated", "CAMS", "NSDL", "KARVY",
    ]

    async def extract(self, page: Page, url: str) -> dict[str, Any]:
        data: dict[str, Any] = {
            "faqs": [],
            "source_url": url,
        }

        try:
            await page.wait_for_load_state("domcontentloaded", timeout=30_000)
        except Exception:
            return data

        faqs = await self._extract_all_faqs(page)
        data["faqs"] = faqs
        data["faq_count"] = len(faqs)
        data["statement_faqs"] = [
            faq for faq in faqs
            if any(kw.lower() in faq.get("question", "").lower()
                   or kw.lower() in faq.get("answer", "").lower()
                   for kw in self.FAQ_KEYWORDS)
        ]
        return data

    async def _extract_all_faqs(self, page: Page) -> list[dict]:
        """
        Attempt multiple DOM patterns for FAQ extraction:
        1. Accordion panels (most common on PPFAS)
        2. dt/dd definition lists
        3. h3/p heading+paragraph pairs
        """
        faqs = []

        # Pattern 1: Accordion — click each panel to expand, then read Q+A
        try:
            # Look for elements that have aria-expanded or role=button pattern
            toggles = page.locator(
                "[aria-expanded], .accordion-header, .faq-question, "
                "[role='button'][class*='faq'], [class*='accordion']"
            )
            count = await toggles.count()
            for i in range(min(count, 50)):
                try:
                    toggle = toggles.nth(i)
                    question = (await toggle.text_content(timeout=5_000) or "").strip()
                    if not question or len(question) > 300:
                        continue

                    # Click to expand
                    await toggle.click(timeout=5_000)
                    await page.wait_for_timeout(500)

                    # Find the answer panel that appeared
                    answer = "NA"
                    sibling_panel = toggle.locator(
                        "xpath=following-sibling::*[1]"
                    )
                    panel_count = await sibling_panel.count()
                    if panel_count > 0:
                        answer = (
                            await sibling_panel.first.inner_text(timeout=5_000) or ""
                        ).strip()

                    if question:
                        faqs.append({
                            "question": question,
                            "answer": answer or "NA",
                        })
                except Exception:
                    continue
        except Exception:
            pass

        if faqs:
            return faqs

        # Pattern 2: dt/dd pairs
        try:
            dts = page.locator("dt")
            dds = page.locator("dd")
            dt_count = await dts.count()
            dd_count = await dds.count()
            if dt_count > 0 and dd_count > 0:
                for i in range(min(dt_count, 50)):
                    try:
                        q = (await dts.nth(i).text_content(timeout=3_000) or "").strip()
                        a = (
                            (await dds.nth(i).text_content(timeout=3_000) or "").strip()
                            if i < dd_count
                            else "NA"
                        )
                        if q:
                            faqs.append({"question": q, "answer": a})
                    except Exception:
                        continue
        except Exception:
            pass

        if faqs:
            return faqs

        # Pattern 3: heading + paragraph pairs (h3/p or strong/p)
        try:
            body = await page.inner_text("body")
            # Split on lines that look like questions
            lines = body.split("\n")
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if line.endswith("?") and 10 < len(line) < 250:
                    question = line
                    answer_lines = []
                    j = i + 1
                    while j < len(lines) and not lines[j].strip().endswith("?"):
                        answer_lines.append(lines[j].strip())
                        j += 1
                        if j - i > 10:
                            break
                    answer = " ".join(l for l in answer_lines if l)
                    faqs.append({
                        "question": question,
                        "answer": answer or "NA",
                    })
                    i = j
                else:
                    i += 1
        except Exception:
            pass

        return faqs


# ---------------------------------------------------------------------------
# SID downloads page scraper (URL 10)
# ---------------------------------------------------------------------------

class PPFASSIDScraper(BaseScraper):
    """
    Scrapes the PPFAS SID/KIM downloads page.
    Extracts PDF links for all 4 schemes.
    """

    SCHEME_KEYWORDS = {
        "PPFCF": ["Flexi Cap", "Long Term Equity"],
        "PPTSF": ["Tax Saver", "ELSS"],
        "PPCHF": ["Conservative Hybrid"],
        "PPLF":  ["Liquid"],
    }

    async def extract(self, page: Page, url: str) -> dict[str, Any]:
        data: dict[str, Any] = {
            "sid_links": {k: "NA" for k in self.SCHEME_KEYWORDS},
            "source_url": url,
        }

        try:
            await page.wait_for_load_state("domcontentloaded", timeout=30_000)
        except Exception:
            return data

        # Grab all PDF/document links on the page
        try:
            links = page.locator("a[href$='.pdf'], a[href*='download'], a[href*='sid'], a[href*='SID']")
            count = await links.count()
            for i in range(min(count, 100)):
                try:
                    href = await links.nth(i).get_attribute("href", timeout=3_000) or ""
                    text = (await links.nth(i).text_content(timeout=3_000) or "").strip()

                    for scheme_key, keywords in self.SCHEME_KEYWORDS.items():
                        if any(kw.lower() in href.lower() or kw.lower() in text.lower()
                               for kw in keywords):
                            if data["sid_links"][scheme_key] == "NA":
                                data["sid_links"][scheme_key] = href
                except Exception:
                    continue
        except Exception:
            pass

        return data
