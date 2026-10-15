"""Inspect CAPTCHA site keys in a browser without submitting solver tasks."""

import re
import asyncio
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright


target_url = "https://kktix.com/events/kieas/registrations/new"

async def debug_sitekey(url: str):
    """Print site-key candidates from attributes, scripts and iframe URLs."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # 先用可視化 debug
        page = await browser.new_page()

        await page.goto(url, wait_until="networkidle")

        # A) 直接找所有帶 data-sitekey 的元素（recaptcha/hcaptcha/turnstile 都常用）
        keys = await page.eval_on_selector_all(
            "[data-sitekey]",
            "els => els.map(e => e.getAttribute('data-sitekey'))"
        )
        keys = [k for k in keys if k]
        print("Found [data-sitekey]:", keys)

        # B) 掃 script src：reCAPTCHA v3 常見 api.js?render=SITEKEY
        scripts = await page.eval_on_selector_all(
            "script[src]",
            "els => els.map(e => e.src)"
        )
        recaptcha_scripts = [s for s in scripts if "recaptcha" in s.lower()]
        print("reCAPTCHA scripts:", recaptcha_scripts)

        for s in recaptcha_scripts:
            m = re.search(r"[?&]render=([^&]+)", s)
            if m:
                print("Found render sitekey:", m.group(1))

        # C) 掃 iframe src：reCAPTCHA v2 常見 anchor?k=SITEKEY
        iframes = await page.eval_on_selector_all(
            "iframe[src]",
            "els => els.map(e => e.src)"
        )
        cap_iframes = [f for f in iframes if any(x in f.lower() for x in ["recaptcha", "hcaptcha", "turnstile"])]
        print("Captcha-related iframes:", cap_iframes)

        for f in cap_iframes:
            qs = parse_qs(urlparse(f).query)
            if "k" in qs and qs["k"]:
                print("Found iframe k= sitekey:", qs["k"][0])

        await browser.close()


if __name__ == "__main__":
    asyncio.run(debug_sitekey(target_url))
