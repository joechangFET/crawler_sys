from playwright.async_api import TimeoutError as PWTimeout, Error as PWError
from urllib.parse import urlparse, parse_qs

RECAPTCHA_HOSTS = ("google.com/recaptcha", "recaptcha.net/recaptcha")

class Recaptcha:
    def __init__(self, page, logger):
        self.page = page
        self.logger = logger

    def _is_recaptcha_url(self, url: str) -> bool:
        return url and any(h in url for h in RECAPTCHA_HOSTS)

    async def detect_recaptcha_v2(self, timeout: int = 8000) -> bool:
        """
        Detects whether reCAPTCHA v2 (checkbox or image challenge) is present
        """
        try:
            await self.page.wait_for_function(
                """
                () => {
                    const frames = Array.from(document.querySelectorAll('iframe'));
                    return frames.some(f =>
                        f.src.includes('google.com/recaptcha') ||
                        f.src.includes('recaptcha.net/recaptcha')
                    );
                }
                """,
                timeout=timeout
            )
            return True
        except PWTimeout:
            return False

    async def get_recaptcha_sitekey(self) -> str | None:
        for frame in self.page.frames:
            if self._is_recaptcha_url(frame.url) and "anchor" in frame.url:
                # sitekey is in the iframe URL

                qs = parse_qs(urlparse(frame.url).query)
                return qs.get("k", [None])[0]
        return None

