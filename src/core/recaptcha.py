"""Inspect reCAPTCHA frames and coordinate image-classification interactions.

Challenge images are read through Playwright, downloaded images are saved
under artifacts/, and classification requests are sent to CapSolver.
"""
import requests
import base64
from playwright.async_api import TimeoutError as PWTimeout
from urllib.parse import urlparse, parse_qs

RECAPTCHA_HOSTS = ("google.com/recaptcha", "recaptcha.net/recaptcha")

class Recaptcha:
    """Keep page, credentials and image-challenge state for reCAPTCHA interactions."""
    def __init__(self, page, logger, api_key):
        """Bind the active page, logger and CapSolver API key."""
        self.page = page
        self.logger = logger
        self.api_key = api_key

    def _is_recaptcha_url(self, url: str) -> bool:
        """Check whether a URL contains a supported reCAPTCHA host/path marker."""
        return url and any(h in url for h in RECAPTCHA_HOSTS)

    async def detect_recaptcha_v2(self, timeout: int = 8000) -> bool:
        """Inspect challenge frames, classify available images and click matching tiles.

        Resets image and image_target before inspection. Errors are logged;
        the current implementation can return None rather than a success flag.
        """

        self.image = None
        self.image_target = None

        try:
            # 0) 先等任一 recaptcha iframe 出現（anchor 或 bframe）
            await self.page.wait_for_function(
                """() => Array.from(document.querySelectorAll('iframe'))
                .some(f => (f.src || '').includes('recaptcha/api2/anchor')
                        || (f.src || '').includes('recaptcha/api2/bframe'))""",
                timeout=timeout,
            )

            IFRAME_SEL = 'iframe[src*="recaptcha/api2/bframe"]'
            # 1) 如果有 bframe（圖片挑戰），嘗試取得題目
            bframes = self.page.locator(IFRAME_SEL)
            count = await bframes.count()
            self.logger.debug(f"{count} iframes matched")

            for i in range(count):
                iframe = bframes.nth(i)
                src = await iframe.get_attribute("src")
                box = await iframe.bounding_box()

                fr = self.page.frame_locator(IFRAME_SEL).nth(i)
                desc_count = await fr.locator(".rc-imageselect-desc").count()
                img_count = await fr.locator(".rc-image-tile-wrapper img").count()

                self.logger.debug(
                    f"bframe[{i}] src={src}, box={box}, desc_count={desc_count}, img_count={img_count}"
                )


            if count > 0:
                fr = await self._get_bframe_by_index(1, timeout=timeout)

                self.image = await self.get_recaptcha_images_base64(fr)
                self.logger.debug(f"Transform image to base64 successful, count: {len(self.image)}")


                # 用較穩的候選 selector（desc / wrapper / instructions）
                candidates = [
                    ".rc-imageselect-desc",
                    ".rc-imageselect-desc-wrapper",
                    ".rc-imageselect-instructions",
                ]

                for sel in candidates:
                    loc = fr.locator(sel).first
                    try:
                        await loc.wait_for(state="visible", timeout=min(timeout, 5000))
                        txt = (await loc.inner_text(timeout=2000))
                        if txt:
                            self.logger.debug(f"[recaptcha] desc={txt!r} in {sel}")
                            lines = [l.strip() for l in txt.splitlines() if l.strip()]
                            self.image_target = lines[1] if len(lines) >= 2 else None
                    except Exception:
                        continue
                res = await self._deal_iamge_challenage()
                self.logger.debug(res.get('objects'))
                tiles = fr.locator(".rc-imageselect-tile")

                for i in res.get('objects'):
                    tile = tiles.nth(i)

                    await tile.scroll_into_view_if_needed()
                    await tile.click(force=True)
                await fr.locator("#recaptcha-verify-button").click()


        except Exception as e:
            self.logger.error(e, exc_info = True)

        except PWTimeout as e:
            return False

    async def get_recaptcha_sitekey(self) -> str | None:
        """Return the k query parameter from the first matching anchor frame, or None."""
        for frame in self.page.frames:
            if self._is_recaptcha_url(frame.url) and "anchor" in frame.url:
                # sitekey is in the iframe URL

                qs = parse_qs(urlparse(frame.url).query)
                return qs.get("k", [None])[0]
        return None

    async def _deal_iamge_challenage(self):

        """Submit the first available challenge image to CapSolver and return its solution."""
        image_map = {
                "計程車": "/m/0pg52",
                "公車": "/m/01bjv",
                "校車": "/m/02yvhj",
                "摩托車": "/m/04_sv",
                "機車": "/m/04_sv",
                "拖拉機": "/m/013xlm",
                "煙囪": "/m/01jk_4",
                "行人穿越道": "/m/014xcs",
                "交通號誌": "/m/015qff",
                "自行車": "/m/0199g",
                "腳踏車": "/m/0199g",
                "停車收費表": "/m/015qbp",
                "汽車": "/m/0k4j",
                "橋樑": "/m/015kr",
                "船": "/m/019jd",
                "棕櫚樹": "/m/0cdl1",
                "山或丘陵": "/m/09d_r",
                "消防栓": "/m/01pns0",
                "樓梯": "/m/01lynh"
            }

        for i in range(len(set(self.image))):
            self.logger.info(f"{i+1} / {len(self.image)}th image")
            payload = {
                    "clientKey": self.api_key,
                    "task": {
                    "type": "ReCaptchaV2Classification",
                    "websiteURL": self.page.url,
                    "image": self.image[i],
                    "question": image_map[self.image_target]
                    }
                }
            self.logger.debug(f"目標: {self.image_target}")
            self.logger.debug(f"Payload: {payload}")
            res = requests.post(
                "https://api.capsolver.com/createTask",
                json=payload
            ).json()

            self.logger.info(f"Response: {res}")
            return res.get("solution")
        import time
        await time.sleep(300)


    async def get_recaptcha_images_base64(self, frame):
        """Read tile image sources and return data URLs or downloaded base64 payloads.

        Downloaded bytes are also written to artifacts/image_<index>.png.
        """
        results = []

        # 2️⃣ 找到所有圖片
        imgs = frame.locator(".rc-image-tile-wrapper img")

        count = await imgs.count()

        for i in range(count):
            img = imgs.nth(i)

            # 取得 src
            src = await img.get_attribute("src")

            if not src:
                continue

            # 如果已經是 data:image/base64
            if src.startswith("data:image"):
                results.append(src)
                continue


            # 否則下載後轉 base64
            response = await self.page.request.get(src)
            content = await response.body()
            encoded = base64.b64encode(content).decode()


            with open(f"artifacts/image_{i}.png", "wb") as f:
                f.write(content)

            results.append(encoded)

        return results

    async def _read_desc_from_bframe_2(self, timeout: int = 8000) -> str | None:
        """Read the first visible nonempty instruction from the second challenge frame."""
        frame = await self._get_bframe_by_index(1, timeout=timeout)
        if not frame:
            return None

        # 用較穩的候選 selector（desc / wrapper / instructions）
        candidates = [
            ".rc-imageselect-desc",
            ".rc-imageselect-desc-wrapper",
            ".rc-imageselect-instructions",
        ]

        for sel in candidates:
            loc = frame.locator(sel).first
            try:
                await loc.wait_for(state="visible", timeout=min(timeout, 5000))
                txt = (await loc.inner_text(timeout=2000)).strip()
                if txt:
                    return txt
            except Exception:
                continue

        return None

    async def _get_bframe_by_index(self, index: int, timeout: int = 8000):
        # 先確保 iframe 元素存在
        """Wait for the zero-based challenge iframe and return its content frame, or None."""
        bframes = self.page.locator('iframe[src*="recaptcha/api2/bframe"]')

        await bframes.nth(index).wait_for(state="attached", timeout=timeout)

        # 取得「具體 iframe element」
        iframe_el = await bframes.nth(index).element_handle()
        if not iframe_el:
            return None

        # 取得該 iframe 對應的 Frame（釘住）
        frame = await iframe_el.content_frame()
        return frame
