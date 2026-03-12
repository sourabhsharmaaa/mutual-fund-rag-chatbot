"""
base_scraper.py
---------------
Abstract base class for all PPFAS RAG chatbot scrapers.
Uses Playwright async API with a headless Chromium browser.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any

from playwright.async_api import (
    async_playwright,
    Page,
    Browser,
    BrowserContext,
    TimeoutError as PlaywrightTimeoutError,
)

# Default user-agent to avoid trivial bot-detection
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Shared timeout values (ms)
NAVIGATION_TIMEOUT_MS = 60_000
SELECTOR_TIMEOUT_MS = 30_000


class ScrapeResult:
    """Standardised container returned by every scraper."""

    def __init__(self, url: str):
        self.source_url: str = url
        self.status: str = "ok"          # "ok" | "error" | "404" | "timeout"
        self.data: dict[str, Any] = {}
        self.error_message: str = ""
        self.elapsed_ms: float = 0.0
        self.field_count: int = 0

    def to_dict(self) -> dict:
        return {
            "source_url": self.source_url,
            "status": self.status,
            "data": self.data,
            "error_message": self.error_message,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "field_count": self.field_count,
        }


class BaseScraper(ABC):
    """
    Abstract async Playwright scraper.

    Subclasses implement `extract(page, url) -> dict`.
    Call `await scraper.scrape(url)` to get a ScrapeResult.
    """

    async def scrape(self, url: str) -> ScrapeResult:
        result = ScrapeResult(url)
        t0 = time.monotonic()

        async with async_playwright() as pw:
            browser: Browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context: BrowserContext = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 900},
                locale="en-IN",
            )
            # Mask webdriver presence
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page: Page = await context.new_page()
            page.set_default_timeout(NAVIGATION_TIMEOUT_MS)

            try:
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=NAVIGATION_TIMEOUT_MS,
                )
                # Small wait for React/hydration
                await page.wait_for_timeout(2_000)

                if response is None or response.status == 404:
                    result.status = "404"
                    result.error_message = f"HTTP {response.status if response else 'None'}"
                elif response.status >= 400:
                    result.status = "error"
                    result.error_message = f"HTTP {response.status}"
                else:
                    extracted = await self.extract(page, url)
                    result.data = extracted
                    # Count non-"NA" values as successful fields
                    result.field_count = sum(
                        1 for v in extracted.values() if v not in ("NA", "", None, [], {})
                    )

            except PlaywrightTimeoutError as e:
                result.status = "timeout"
                result.error_message = str(e)[:200]
            except Exception as e:  # noqa: BLE001
                result.status = "error"
                result.error_message = str(e)[:200]
            finally:
                result.elapsed_ms = (time.monotonic() - t0) * 1000
                await browser.close()

        return result

    @abstractmethod
    async def extract(self, page: Page, url: str) -> dict[str, Any]:
        """
        Extract relevant data from `page` (already navigated to `url`).
        Return a flat dict. Use "NA" for any field that cannot be found.
        """
        ...

    # ---------------------------------------------------------------
    # Helpers available to all subclasses
    # ---------------------------------------------------------------

    @staticmethod
    async def safe_text(locator: Locator, default: str = "NA") -> str:
        """Read .text_content() from a locator; return default on any failure or junk."""
        try:
            # Low timeout for sub-elements: if it's not there, don't hang
            text = await locator.first.text_content(timeout=200)
            val = (text or "").strip()
            
            # Aggressive check: if it looks like CSS string, reject it.
            # CSS often has property: value; or { ... } or .class-name {
            if not val:
                return default
            import re
            # Check for common CSS patterns: { followed by properties like color:, background:, etc.
            if re.search(r'\{[^}]+\}', val) or re.search(r'\.[a-zA-Z0-9_-]+\s*\{', val) or "function()" in val or "{\n\t    color:" in val or "{ \n        margin-top:" in val:
                return default
            return val
        except Exception:  # noqa: BLE001
            return default

    @staticmethod
    async def safe_inner_text(locator, default: str = "NA") -> str:
        """Read .inner_text() from a locator; return default on any failure."""
        try:
            text = await locator.first.inner_text(timeout=SELECTOR_TIMEOUT_MS)
            return (text or "").strip() or default
        except Exception:  # noqa: BLE001
            return default

    @staticmethod
    async def safe_all_text(locator, default: list | None = None) -> list[str]:
        """Read text_content() for all matching elements."""
        try:
            items = await locator.all_text_contents()
            return [t.strip() for t in items if t.strip()]
        except Exception:  # noqa: BLE001
            return default or []

    @staticmethod
    async def get_sibling_value(page: Page, label_text: str, default: str = "NA") -> str:
        """
        Generic text-locator pattern:
        Find the element whose *exact* text matches `label_text`,
        then return the text of the immediately following sibling element (that is not a script/style).
        """
        try:
            # Try XPath: find element matching label, skip script/style siblings, take first
            xpath = f"xpath=//*[normalize-space(text())='{label_text}']/following-sibling::*[not(self::script or self::style)][1]"
            value_locator = page.locator(xpath)
            return await BaseScraper.safe_text(value_locator, default)
        except Exception:  # noqa: BLE001
            return default
