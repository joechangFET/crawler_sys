"""Click KKTIX image-map sections with native and viewport-based strategies.

Prefer native area clicks, then try fixed offsets around the extracted
viewport centroid. Temporary bubble pointer-event changes are restored
in a finally block. Diagnostic helpers log failures on a best-effort basis.
"""
from datetime import datetime
from typing import Any, Callable, Optional

class SeatsMap:
    """Coordinate section clicks and diagnostics for a configured KKTIX seat map."""
    def __init__(self, page, config, logger):
        """Bind the active page, site configuration and diagnostic logger."""
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
        """Click a section matched by its alt label and return the current page.

        Exact labels take precedence over substring matches. A native area click
        is attempted before fixed viewport offsets; obvious overlays are skipped.
        Bubble pointer-event styles are restored even when clicking fails.
        The returned page does not guarantee that a seat table has appeared.

        Args:
            alt: Section label to match; blank or unknown labels are ignored.
            timeout: Retained for caller compatibility; currently unused.
        """
        alt = (alt or "").strip()
        if not alt:
            return self.page

        data = await self.page.evaluate(self.config["js"]["extract"])
        areas = data.get("areas") or []

        target = (
            next((a for a in areas if (a.get("alt") or "").strip() == alt), None)
            or next((a for a in areas if alt in (a.get("alt") or "")), None)
        )

        if not target:
            self.logger.debug(f"[click_section_by_alt] alt '{alt}' not found in areas.")
            return self.page

        img_sel = self.config["selectors"]["img"]

        # ---- Minimal DOM patch (safe + reversible) ----
        async def _pre_patch():
            try:
                await self.page.evaluate(
                    """() => {
                    // remove bootstrap-like backdrops
                    document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());

                    // bubbles sometimes sit above the map; disable pointer events temporarily
                    document.querySelectorAll('.map-inner .amount.bubble').forEach(b => {
                        b.dataset._pe = b.style.pointerEvents || "";
                        b.style.pointerEvents = "none";
                    });
                    }"""
                )
            except Exception:
                pass

        async def _post_patch():
            try:
                await self.page.evaluate(
                    """() => {
                    document.querySelectorAll('.map-inner .amount.bubble').forEach(b => {
                        b.style.pointerEvents = b.dataset._pe || "";
                        delete b.dataset._pe;
                    });
                    }"""
                )
            except Exception:
                pass

        # ---- install a one-shot click probe to see if the map actually receives the click ----
        async def _arm_click_probe():
            try:
                await self.page.evaluate(
                    """() => {
                    window.__kktixLastClick = null;
                    window.__kktixClickProbe = (e) => {
                        const t = e.target;
                        window.__kktixLastClick = {
                        tag: t?.tagName || null,
                        id: t?.id || null,
                        cls: (t?.className && t.className.toString()) || null,
                        time: Date.now(),
                        };
                    };
                    document.addEventListener('click', window.__kktixClickProbe, {capture:true, once:true});
                    }"""
                )
            except Exception:
                pass

        async def _read_click_probe():
            try:
                return await self.page.evaluate("() => window.__kktixLastClick")
            except Exception:
                return None

        # ---- 1) Best: click the <area> by alt (native image-map behavior) ----
        async def _click_area_by_alt() -> bool:
            await _arm_click_probe()
            try:
                ok = await self.page.evaluate(
                    """(alt) => {
                    const areas = [...document.querySelectorAll('map[name="background"] area')];
                    const a = areas.find(x => (x.getAttribute('alt')||'').trim() === alt)
                            || areas.find(x => ((x.getAttribute('alt')||'').includes(alt)));
                    if (!a) return false;

                    // native click on <area>
                    a.click();
                    return true;
                    }""",
                    alt,
                )
                probe = await _read_click_probe()
                self.logger.debug(f"[click_section_by_alt] area.click issued={ok}, probe={probe}")
                return bool(ok)
            except Exception as e:
                self.logger.debug(f"[click_section_by_alt] area.click failed: {e}")
                return False

        # ---- 2) Fallback: click viewport coords with jitter ----
        async def _click_by_viewport_jitter() -> bool:
            vp = target.get("centroidViewport") or {}
            cx0 = float(vp.get("x", 0))
            cy0 = float(vp.get("y", 0))

            jitters = [
                (0, 0), (6, 0), (-6, 0), (0, 6), (0, -6),
                (10, 10), (-10, 10), (10, -10), (-10, -10),
                (14, 0), (-14, 0), (0, 14), (0, -14),
            ]

            last_err = None

            for dx, dy in jitters:
                cx, cy = cx0 + dx, cy0 + dy

                # Debug hit-test path
                info = await self.page.evaluate(
                    """({x,y}) => {
                    const el = document.elementFromPoint(x,y);
                    if (!el) return { ok:false, reason:"no element", x, y };
                    const path = [];
                    let cur = el;
                    for (let i=0; i<6 && cur; i++){
                        path.push({
                        tag: cur.tagName,
                        id: cur.id || null,
                        cls: (cur.className && cur.className.toString()) || null
                        });
                        cur = cur.parentElement;
                    }
                    return { ok:true, x, y, hit: path };
                    }""",
                    {"x": cx, "y": cy},
                )
                self.logger.debug(f"[click_section_by_alt] hit-test: {info}")

                # Reject obvious overlays
                ok = await self.page.evaluate(
                    """({x,y}) => {
                    const el = document.elementFromPoint(x,y);
                    if (!el) return false;
                    if (el.closest('.modal, .modal-backdrop, .loading, .spinner')) return false;
                    return true;
                    }""",
                    {"x": cx, "y": cy},
                )
                if not ok:
                    continue

                await _arm_click_probe()
                try:
                    # Use real mouse click (lets browser do imagemap hit testing)
                    await self.page.mouse.click(cx, cy)
                    probe = await _read_click_probe()
                    self.logger.debug(f"[click_section_by_alt] mouse.click probe={probe}")
                    return True
                except Exception as e:
                    last_err = e

            self.logger.debug(f"[click_section_by_alt] viewport jitter click failed: {last_err}")
            return False

        # ---- Execute with patch guard ----
        await _pre_patch()
        try:
            # Ensure image is in view (helps viewport coords)
            try:
                await self.page.locator(img_sel).scroll_into_view_if_needed()
            except Exception:
                pass

            # Prefer native area click
            if await _click_area_by_alt():
                return self.page

            # Fallback: viewport + jitter
            await _click_by_viewport_jitter()
            return self.page
        finally:
            await _post_patch()
