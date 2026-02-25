import re
import asyncio
from datetime import datetime
from playwright.async_api import TimeoutError as PWTimeout, Error as PWError
from typing import Any, Callable, Dict, List, Optional

class SeatsMap:
    def __init__(self, page, config, logger):
        self.page = page
        self.config = config
        self.logger = logger

    async def capture_debug_bundle(self, prefix: str) -> None:
        """Screenshot + light DOM diagnostics (safe, best-effort)."""
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"logs/{prefix}_{ts}.png"
            await self.page.screenshot(path=path, full_page=True)
            self.logger.debug(f"[debug] screenshot saved: {path}")
        except Exception as e:
            self.logger.debug(f"[debug] screenshot failed: {e}")

        try:
            url = self.page.url
            title = await self.page.title()
            self.logger.debug(f"[debug] url={url}")
            self.logger.debug(f"[debug] title={title}")
        except Exception:
            pass

        # key selector diagnostics
        try:
            img_sel = self.config["selectors"]["img"]
            area_sel = self.config["selectors"]["area"]
            img_cnt = await self.page.locator(img_sel).count()
            area_cnt = await self.page.locator(area_sel).count()
            table_ok = await self.is_table_view()
            map_ok = await self.is_map_view()
            modal_ok = await self.has_modal()
            self.logger.debug(
                f"[debug] img_cnt={img_cnt}, area_cnt={area_cnt}, map={map_ok}, table={table_ok}, modal={modal_ok}"
            )
        except Exception:
            pass
    
    # --------------------------
    # Generic helpers
    # --------------------------

    async def safe_step(
        self,
        name: str,
        fn: Callable[[], Any],
        *,
        retries: int = 2,
        retry_delay_ms: int = 250,
    ) -> Any:
        """
        Run fn() with retries; on last failure capture debug bundle and re-raise.
        """
        last_err: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            try:
                return await fn()
            except Exception as e:
                last_err = e
                self.logger.debug(f"[{name}] attempt {attempt}/{retries} failed: {e}")
                if attempt < retries:
                    await self.page.wait_for_timeout(retry_delay_ms)
                    continue
                await self.capture_debug_bundle(f"fail_{name}")
                raise
        raise last_err  # pragma: no cover

    # --------------------------
    # Clicking area by alt
    # --------------------------
    async def click_section_by_alt(self, alt: str, timeout: int = 20000):
        alt = (alt or "").strip()
        if not alt:
            return self.page

        #await self.ensure_view("map", timeout=timeout)
        #await self.close_any_modal()

        data = await self.page.evaluate(self.config["js"]["extract"])
        areas: List[Dict[str, Any]] = data.get("areas") or []

        target = next((a for a in areas if (a.get("alt") or "").strip() == alt), None)
        if not target:
            target = next((a for a in areas if alt in (a.get("alt") or "")), None)
        if not target:
            self.logger.debug(f"[click_section_by_alt] alt '{alt}' not found in areas.")
            return self.page

        img_sel = self.config["selectors"]["img"]
        img = self.page.locator(img_sel)
        await img.scroll_into_view_if_needed()

        # IMPORTANT: do NOT permanently break bubble interactions; keep patch minimal
        async def _temp_dom_patch():
            try:
                await self.page.evaluate(
                    "() => {"
                    "  document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());"
                    "}"
                )
            except Exception:
                pass

        await _temp_dom_patch()

        pos = target.get("centroidImg") or {}
        x = float(pos.get("x", 0))
        y = float(pos.get("y", 0))
        self.logger.debug(f"[click_section_by_alt] clicking alt={alt}, img-pos=({x:.1f},{y:.1f})")

        async def _do_click() -> None:
            # try normal click on img position
            try:
                await img.click(position={"x": x, "y": y}, timeout=timeout)
                return
            except Exception as e:
                self.logger.debug(f"[click_section_by_alt] img.click failed: {e}")

            # fallback: dispatch a click at client coordinates using elementFromPoint
            await self.page.evaluate(
                """
                ({imgSel, x, y}) => {
                  const img = document.querySelector(imgSel);
                  if (!img) throw new Error("img not found for fallback click");
                  const r = img.getBoundingClientRect();
                  const cx = r.left + x;
                  const cy = r.top + y;
                  const el = document.elementFromPoint(cx, cy);
                  (el || img).dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, clientX: cx, clientY: cy}));
                }
                """,
                {"imgSel": img_sel, "x": x, "y": y},
            )

        # If you have _click_and_follow, keep it; otherwise just click in-place.
        await self.safe_step(f"click_area_{alt}", _do_click, retries=2)

        return self.page