"""Manage a persistent Chromium context and limit concurrently active pages.

Pages share profile data, cookies and local storage. Each acquired page must
be released with close_page() to return its semaphore slot.
"""
import asyncio
from typing import Tuple

from playwright.async_api import (
    async_playwright,
    BrowserContext,
    Page,
)
from playwright_stealth import Stealth


class BrowserManager:
    """
    Strategy:
    - Single Playwright instance
    - Single persistent Browser context
    - Multiple pages with semaphore-based concurrency limit
    """

    def __init__(
        self,
        *,
        max_contexts: int = 2,
        headless: bool = False,
        channel: str = "chrome",
        proxy: dict | None = None,
        persist_dir: str = "web",
    ):
        """Configure the persistent profile, launch options and page concurrency limit."""
        self.max_contexts = max_contexts
        self.headless = headless
        self.channel = channel
        self.proxy = proxy
        self.persist_dir = persist_dir

        self._pw_cm = Stealth().use_async(async_playwright())
        self._sem = asyncio.Semaphore(max_contexts)

        self.p = None
        self.browser: BrowserContext | None = None

    async def __aenter__(self):
        """Start Playwright and launch the persistent Chromium context."""
        self.p = await self._pw_cm.__aenter__()

        self.browser = await self.p.chromium.launch_persistent_context(
            user_data_dir=self.persist_dir,
            headless=self.headless,
            channel=self.channel,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 800},
            proxy=self.proxy,
        )

        return self

    async def __aexit__(self, exc_type, exc, tb):
        """Close the persistent context and exit the Playwright manager."""
        if self.browser:
            await asyncio.wait_for(self.browser.close(), timeout=15)
        await self._pw_cm.__aexit__(exc_type, exc, tb)

    async def new_context_page(self) -> Tuple[BrowserContext, Page]:
        """
        Acquire a concurrency slot and create a new page.
        Caller MUST call close_page() when done.
        """
        await self._sem.acquire()

        try:
            context = self.browser
            page = await context.new_page()
            return context, page

        except Exception:
            self._sem.release()
            raise

    async def close_page(self, page: Page):
        """
        Close the page and release the concurrency slot.
        Does NOT close the persistent browser context.
        """
        try:
            if not page.is_closed():
                await page.close()
        finally:
            self._sem.release()
