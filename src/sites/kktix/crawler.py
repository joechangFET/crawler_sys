import asyncio
import re
import random
import time
import pandas as pd
from dataclasses import asdict
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path
from playwright.async_api import TimeoutError as PWTimeout, Error as PWError

from core.base import BaseCrawler
from core.human_behavior import (
    human_scroll,
    human_click,
    human_type,
    jitter
)
from sites.utils import safe_text
from sites.kktix.map import SeatsMap
from config.config_reader import ConfigReader
from config.env_loader import env
from model.enums import ResultCode

class KktixCrawler(BaseCrawler):
    def __init__(self, context, page, logger, metrics):
        super().__init__(context, page, logger, metrics)
        self.env_config = env
        self.config = ConfigReader("sites/config/kktix.yaml").load()
        self.ticket_page = None
        self.seats_map_client = SeatsMap(page, self.config, self.logger)
        self.target_nth_order = None

    async def navigate(self):
        step_start = time.perf_counter()
        await self.page.goto(self.config['setting']['main_url'], wait_until="domcontentloaded")
        await self.page.wait_for_timeout(random.uniform(1500, 3000))
        await self.page.mouse.move(200, 300)
        await self.page.mouse.wheel(0, random.randint(300, 800))
        await self.page.wait_for_timeout(random.uniform(1000, 2000))
        await self._save_storage_state(path="sites/states/kktix.json")
        elapsed = time.perf_counter() - step_start
        self.step_metrics["navigate"].update({"total": elapsed, "max": elapsed, "count": 1})

    async def login(self):
        if await self.page.locator('text="登入"').is_visible():   
            step_start = time.perf_counter()     
            await human_scroll(self.page, total=1200)

            await self.page.click('text="登入"')

            await self.page.wait_for_selector("#user_login", timeout=30_000)
            await self.page.wait_for_selector("#user_password", timeout=30_000)

            user_locator = self.page.locator("#user_login")
            pwd_locator = self.page.locator("#user_password")
            commit_button = self.page.locator("input[name='commit'][type='submit']")

            # 逐字輸入帳號（模擬人類）
            await human_click(user_locator, page=self.page)   # focus by moving + clicking (optional)
            await human_type(user_locator, self.env_config.KKTIX_USER)

            # 稍微停一下再輸入密碼（人類會有短延遲）
            await asyncio.sleep(jitter(300) / 1000)

            # 逐字輸入密碼（示範用，實際請使用 env var）
            await human_click(pwd_locator, page=self.page)
            await human_type(pwd_locator, self.env_config.KKTIX_PASSWORD)

            # 等按鈕可見並用人類點擊流程
            await commit_button.wait_for(state="visible", timeout=30_000)
            await human_click(commit_button, page=self.page)

            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(jitter(500) / 1000)

            elapsed = time.perf_counter() - step_start
            self.step_metrics["login"].update({"total": elapsed, "max": elapsed, "count": 1})
        else:
            self.logger.info("Already logged in, skipping login step.")

    async def collect(self):
        step_start = time.perf_counter()  
        # Choose the event category
        for item in self.config['setting']['category']:
                    await self.page.get_by_role("link", name=item, exact=True).click()
                    self.logger.info(f"活動類別: {item}")

        pages = self.config['setting']['page']
        self.metrics.pages = pages
        self.logger.info(f"Crawl {pages} pages")
        for times in range(pages):
            # 直接把所有 <a.cover> 的絕對網址取回    list[str]
            href = await self.page.locator("ul.events li.type-selling a.cover").evaluate_all(
                "els => els.map(a => a.href)"       # a.href 會自動轉成絕對網址
            )
            self.url_list.extend(href)
            try: 
                await self.page.click("a[rel='next']", timeout=5000)
            except Exception as e:
                self.logger.warning(f"Error clicking next page: {e}")
                break
        self.logger.info(f"Total {len(self.url_list)} Urls")
        elapsed = time.perf_counter() - step_start
        self.step_metrics["collect"].update({"total": elapsed, "max": elapsed, "count": 1})

    async def crawl(self):
        self.page_info.title, self.page_info.schedule, self.page_info.location = await self._get_event_title_time_and_location()
        self.logger.info(
            "Event Info\n"
            f"  Title: {self.page_info.title}\n"
            f"  Schedule: {self.page_info.schedule}\n"
            f"  Location: {self.page_info.location}"
        )
        await self._click_next_step()
        if not await self._check_if_allocated():
            self._save_page_info()
        else:
            if await self._get_ticket_info() in [ResultCode.Computer.value, ResultCode.STANDING.value, ResultCode.VIP.value, ResultCode.DISABLE.value]:
                self._save_page_info()
            else:
                self.ticket_page = self.page.url
                await self._add_ticket()
                if await self._check_message_box():
                    self._save_page_info()
                else:
                    await self._click_agree_terms()
                    if await self._click_next_step_and_check_capcha():
                        self.page_info.event_type = ResultCode.RECAPCHA.value
                        self._save_page_info()
                        self.logger.info("reCAPTCHA detected, please solve it manually.")
                    else:
                        await self._get_seats_map_info(max_retry=self.config['setting']['max_retry'])
                        self._save_page_info()
        

    async def persist(self):
        step_start = time.perf_counter() 
        self.logger.info("Persisting data...")
        self.logger.info(self.result)
        output_dir = Path("result")
        output_dir.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame([asdict(p) for p in self.result])
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        df.to_csv(f"{output_dir}/{self.config['setting']['site_name']}_{timestamp}.csv", index=False, encoding="utf-8-sig")
        elapsed = time.perf_counter() - step_start
        self.step_metrics["persist"].update({"total": elapsed, "max": elapsed, "count": 1})

    ############################################# Private Function #############################################
    def _save_page_info(self):
        self.page_info.elapsed_time = time.perf_counter() - self.start_time
        self.result.append(self.page_info)
        self.logger.info(f"Event Type: {self.page_info.event_type}")
        self.logger.info(f"{self.page_info.url} 爬取完成，用時 {self.page_info.elapsed_time:.2f} 秒")
        self.logger.info(self.page_info)

    async def _save_storage_state(self, path:str):
        await self.page.context.storage_state(path=path)
    
    
    async def _get_event_title_time_and_location(self):
        """
        Extract the event start time and location from the event detail page.

        This method checks a couple of known KKTIX page layouts and reads the first two
        text entries from the info section:
          - texts[0]: event time (or date/time range)
          - texts[1]: event location/venue

        Returns:
            tuple[str, str] | None:
                (event_time, event_location) if found; otherwise None.
        """
        title = await self.page.title()
        texts = []
        if await self.page.locator("ul.info li").count() > 0:
            info = self.page.locator("ul.info li")
            for i in range(await info.count()):
                text = await info.nth(i).inner_text()
                if text:
                    texts.append(text)
        elif await self.page.locator(".side-inner .section").count() > 0:
            info = self.page.locator(".side-inner .section")
            for i in range(await info.count()):
                text = await info.nth(i).inner_text()
                if text:
                    texts.append(text)
        schedule = texts[0] if len(texts) > 0 else None
        location = texts[1] if len(texts) > 1 else None
        return title, schedule, location
    
    async def _click_next_step(self):
        if await self.page.locator("a.btn-point").count() > 0:
            btns = self.page.locator("a.btn-point")
            last_btn = btns.nth(await btns.count() - 1)
            await last_btn.wait_for(state="visible")
            await last_btn.scroll_into_view_if_needed()
            await last_btn.click()
        elif await self.page.locator("a.btn-ticket").count() > 0:
            btns = self.page.locator("a.btn-ticket")
            last_btn = btns.nth(0)
            await last_btn.wait_for(state="visible")
            await last_btn.scroll_into_view_if_needed()
            await last_btn.click()
        else:
            self.logger.warning("⚠️ 沒有找到任何 a.btn-point 元素")
    
    async def _check_if_allocated(self):
        await self.page.wait_for_selector(".step-bar-wrapper .step-bar", timeout=15000)
        names = await self.page.locator(".step-bar-wrapper ul li span:not(.step)").all_inner_texts()
        clean_names = [n.split("\n", 1)[-1].strip() for n in names]

        if '劃位' not in clean_names:
            self.logger.warning("⚠️ 沒有找到劃位步驟，可能是已經劃位或頁面結構變更")
            return False
        else:
            return True
    
    async def _get_ticket_info(self):
        # 新增可選位票券
        await self.page.wait_for_selector(".ticket-unit", timeout=15000)
        units = self.page.locator(".ticket-unit")
        tickets = []
        target_ticket_order = 0
        nth_order = 0
        is_target = False
        for order in range(await units.count()):
            unit = units.nth(order)
            name = await safe_text(unit, ".ticket-name, .title, h3")
            seat = await safe_text(unit, ".ticket-seat, .title")
            price = await safe_text(unit, ".ticket-price, .price")
            soldout = await unit.locator(":text('已售完')").count() > 0
            
            if not is_target:
                if "電腦" not in seat and "VIP" not in seat and not any(word in name for word in self.config['contents']['disable_keywords']) and "優惠" not in name:
                    if not soldout:
                        is_target = True
                else:
                    target_ticket_order += 1
                    nth_order += 1
                    if soldout:
                        nth_order -= 1

            self.logger.debug(f"{target_ticket_order}- {name} - {seat} - {price} - Soldout: {soldout} - is_target: {is_target}")
            tickets.append(
                {
                    "name": name,
                    "seat": seat,
                    "price": price,
                    "soldout": soldout,
                    "list_order": order,
                }
            )
        self.page_info.tickets = tickets

        if target_ticket_order >= len(tickets):
            self.logger.warning("No eligible ticket found; all tickets are filtered or sold out.")
            return None
        target_ticket = tickets[target_ticket_order]
        self.target_nth_order = nth_order
        # 電腦選位判定
        if "電腦" in tickets[target_ticket.get("list_order")].get("seat"):
            self.page_info.event_type = ResultCode.Computer.value
            return ResultCode.Computer.value
        # 站立坐位判定
        if "站席" in tickets[target_ticket.get("list_order")].get("seat"):
           self.page_info.event_type = ResultCode.STANDING.value
           return ResultCode.STANDING.value 
        # VIP坐位判定
        if "vip" in tickets[target_ticket.get("list_order")].get("name", "").lower():
            self.page_info.event_type = ResultCode.VIP.value
            return ResultCode.VIP.value
        # 身障做位判定
        if any(word in tickets[target_ticket.get("list_order")].get("name") for word in self.config['contents']['disable_keywords']):
            self.page_info.event_type = ResultCode.DISABLE.value
            return ResultCode.DISABLE.value
        return None

    async def _add_ticket(self):
        """
        Add a ticket by clicking the button at the specified order.
        """
        self.logger.debug(f"Adding ticket at order {self.target_nth_order}")
        btn = self.page.locator("button.btn-default.plus").nth(self.target_nth_order)
        await btn.wait_for(state="visible")
        await btn.scroll_into_view_if_needed()
        await btn.click()
        
    async def _check_message_box(self):
        try:
            dlg = self.page.locator(".custom-captcha-inner").first

            await dlg.wait_for(state="visible", timeout=3000)
            self.page_info.event_type = ResultCode.MESSAGEBOX.value
            return True
        except Exception as e:
            self.logger.warning(f"對話框未出現或已關閉: {e}")
            return False

    async def _click_agree_terms(self):
        await self.page.locator("#person_agree_terms").check()
        self.logger.debug("已勾選同意條款")
    
    async def _click_next_step_and_check_capcha(self):
        btn = self.page.locator("button.btn-primary").nth(0)

        try:
            await btn.click(timeout=5000)
        except (PWTimeout, PWError) as e:
            self.logger.warning(f"Next step button click failed: {e}")
            return False
        await self.page.wait_for_timeout(1500)

        has_captcha = await self.recaptcha_solver.detect_recaptcha_v2()
        if not has_captcha:
            return False
        sitekey = await self.recaptcha_solver.get_recaptcha_sitekey()
        if not sitekey:
            raise RuntimeError("reCAPTCHA detected but sitekey not found")
        self.logger.info(f"reCAPTCHA sitekey: {sitekey}")
        return True
    
    async def _get_seats_map_info(self, max_retry: int):
        step_start = time.perf_counter() 
        # open seat map panel (keep your logic)
        btn = self.page.locator("button.btn-primary.pull-right").nth(0)
        await btn.wait_for(state="visible")
        await btn.scroll_into_view_if_needed()
        await btn.click()

        await self.page.wait_for_selector("#registrationsShowApp", state="attached", timeout=30000)

        # collect sections
        sections = await self.seats_map_client.page.evaluate(self.seats_map_client.config["js"]["extract"])
        sections = (sections or {}).get("areas") or []

        non_candidates = [{"alt": s.get("alt"), "chooseable": s.get("chooseable")} for s in sections if not s.get("chooseable")]
        candidates = [
            {
                "alt": s.get("alt"),
                "spec_id": s.get("spec_id"),
                "count": s.get("count_est"),
                "chooseable": s.get("chooseable"),
            }
            for s in sections
            if s.get("chooseable")
        ]

        self.logger.debug({"non_candidates": non_candidates})
        self.logger.debug({"candidates": candidates})

        seat_stats: List[Dict[str, Any]] = []
        seat_total = 0
        seat_avl = 0
        seat_unavl = 0

        # include non-candidates in report if you want
        seat_stats.extend(non_candidates)

        try:
            await self.page.locator("#infoModal button.close").click()
        except PWError:
            self.logger.info("No info modal found or already closed")
       
        try:
            for s in candidates:
                for times in range(max_retry):
                    try:
                        alt = (s.get("alt") or "").strip()
                        if not alt:
                            continue

                        self.logger.debug(f"[loop] alt={alt}, spec_id={s.get('spec_id')}, count={s.get('count')}, chooseable={s.get('chooseable')}")

                        # # 2) click area -> table
                        await self.seats_map_client.click_section_by_alt(alt, timeout=20000)

                        try:
                            await self.page.locator("#seatTipModal button.close").click()
                        except PWError:
                            self.logger.info("No seat tip modal found or already closed")

                        await self.page.evaluate("""
                        () => {
                        document.querySelectorAll('.modal').forEach(m => {
                            m.classList.remove('in');
                            m.style.display = 'none';
                        });
                        document.body.classList.remove('modal-open');
                        document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
                        }
                        """)


                        await self.page.wait_for_function("""
                        () => {
                        const area = document.querySelector(".seats-table:not(.ng-hide) .seats-area");
                        if (!area) return false;
                        const nodes = area.querySelectorAll(
                            ".seat, [kk-seat], [data-seat-id], a[ng-click], [class*='seat-']"
                        );
                        return nodes.length > 0;
                        }
                        """, timeout=240000)


                        # 3) stats
                        stats = await self.page.evaluate(self.seats_map_client.config["js"]["seat_table_stats"])
                        self.logger.debug(f"[{alt}] seat_table_stats: {stats}")
                        # if not stats or not stats.get("ok"):
                        #     self.logger.debug(f"[{alt}] seat_table_stats failed: {stats.get('reason') if stats else 'no stats'}")
                        #     await self.seats_map_client.back_to_map_if_needed()
                        #     continue

                        seat_stat = {
                            "area": alt,
                            "total": int(stats["total"]),
                            "able": int(stats["able"]),
                            "not_able": int(stats["not_able"]),
                            "already": int(stats["already"]),
                            "unknown": int(stats["unknown"]),
                        }

                        seat_total += seat_stat["total"]
                        seat_avl += seat_stat["able"] + seat_stat["already"] + seat_stat["unknown"]
                        seat_unavl += seat_stat["not_able"]

                        seat_stats.append(seat_stat)
                        self.logger.info(seat_stat)
                        back_btns = [
                            self.page.get_by_role("link", name=re.compile("票區圖")),
                            self.page.locator(".seats-table-area-display a", has_text=re.compile("票區圖")),
                            self.page.locator(".seats-table-area-display a[ng-click='back()']"),
                            self.page.locator("a.btn.btn-minor", has_text=re.compile("票區圖")),
                        ]
                        for btn in back_btns:
                            if await btn.count():
                                await btn.first.click()
                                # 等 Map 影像出現、且 Table 消失
                                await self.page.wait_for_function(
                                    "() => document.querySelector('img[usemap=\"#background\"]') && document.querySelectorAll('map[name=\"background\"] area').length > 0",
                                    timeout=6000
                                )
                                self.logger.debug(f"Back to map successfully for area {alt} by clicking {btn}")
                                break
                        break
                    except Exception as e:
                        self.fail_metrics["seat_map"]["times"] += time.perf_counter() - step_start
                        self.fail_metrics["seat_map"]["count"] += 1
                        # 發生錯誤時拍照紀錄，但不中斷整體迴圈
                        state = await self.page.evaluate("""
                            () => {
                            if (!window.angular) return { angular:false };
                            const inj = angular.element(document.body).injector?.();
                            if (!inj) return { angular:true, injector:false };
                            const $http = inj.get('$http');
                            return { angular:true, injector:true, pending:$http.pendingRequests.length };
                            }
                        """)
                        self.logger.error(f"第{times + 1}次嘗試 處理區域 {alt} 時發生異常 Angular State: {state}: {e}", exc_info=True)
                        await self.page.evaluate("""
                            () => {
                            const tableEl = document.querySelector('[ng-controller="SeatsTableCtrl"]');
                            if (!tableEl || !window.angular) return;

                            const s = angular.element(tableEl).scope();

                            // common patterns in KKTIX
                            if (typeof s.backToMap === 'function') s.backToMap();
                            else if (typeof s.changeSection === 'function') s.changeSection();
                            else {
                                s.tableVisible = false;
                                s.mapVisible = true;
                            }

                            s.$applyAsync();
                            }
                        """)
                        self.logger.debug(f"Current ticket page: {self.ticket_page}")
                        await self.page.goto(self.ticket_page, wait_until="domcontentloaded")
                        await asyncio.sleep(30)
                        await self._add_ticket()
                        await self._click_agree_terms()
                        await self._click_next_step_and_check_capcha()
                        try:
                            await self.page.locator("#infoModal button.close").click()
                        except PWError:
                            self.logger.info("No info modal found or already closed")
        except PWError as e:
            self.logger.warning(f"Error during seat map processing: {e}", exc_info=True)
            pass
        self.page_info.seat_stats = seat_stats
        self.page_info.seat_total = seat_total
        self.page_info.seat_avl = seat_avl
        self.page_info.seat_unavl = seat_unavl
        
 