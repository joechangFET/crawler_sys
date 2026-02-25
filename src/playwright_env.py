import asyncio
import time
import pandas as pd
import argparse
import random
from dataclasses import asdict
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from core.browser import chrome_context
from sites.kktix.kktix import Kktix
from crawler.utils import safe_text
from config.config_reader import ConfigReader
from config.enum import ResultCode
from kktix_crawler_poc.utils.logger import Logger
from model.page import PageResult

Logger.setup_file_logger(log_dir="logs")

config = ConfigReader("config/kktix.yaml").load()

parser = argparse.ArgumentParser(description="Main Crawler")
parser.add_argument("-u", "--url", type=str, help="Input single url to crawl")
args = parser.parse_args()

max_retry = config['setting']['max_retry']

async def main():
    async with Stealth().use_async(async_playwright()) as p:
    #async with async_playwright() as p:
        for attempt in range(1, max_retry + 1):
            try:
                context = await chrome_context(p, persist_dir="./user-data")
                page = context.pages[0] if context.pages else await context.new_page()
    
                await page.wait_for_timeout(random.uniform(1500, 3000))
                await page.mouse.move(200, 300)
                await page.mouse.wheel(0, random.randint(300, 800))
                await page.wait_for_timeout(random.uniform(1000, 2000))

                kktix = Kktix(page)
                
                # try:
                    # Navigate to the main page
                await page.goto(config['setting']['main_url'], 
                                wait_until="domcontentloaded", 
                                timeout=60000
                            )
                print(f"Initial page title: {await page.title()}")

                #帳號登入
                if await page.locator('text="登入"').is_visible():
                    await kktix.login()

                for item in config['setting']['category']:
                    await page.get_by_role("link", name=item, exact=True).click()
                    Logger.info(f"活動類別: {item}")

                hrefs = []
                if args.url:
                    # 如果有提供 URL 參數，直接使用該 URL
                    hrefs.append(args.url)
                    Logger.info(f"Using provided URL: {args.url}")
                else:
                    Logger.info(f"Crawl {config['setting']['page']} pages")
                    for i in range(config['setting']['page']):
                        # 直接把所有 <a.cover> 的絕對網址取回    list[str]
                        href = await page.locator("ul.events li.type-selling a.cover").evaluate_all(
                            "els => els.map(a => a.href)"       # a.href 會自動轉成絕對網址
                        )
                        hrefs.extend(href)
                        try: 
                            await page.click("a[rel='next']", timeout=5000)
                        except Exception as e:
                            Logger.warning(f"Error clicking next page: {e}")
                            break
                Logger.info(f"Total {len(hrefs)} Urls")
                break
            except Exception as e:
                print(f"⚠️ Attempt {attempt} failed : {e}")
                await page.close()
                if attempt == max_retry:
                    print(f"{e}")
                    return False
                await asyncio.sleep(2)  # 等一下再試

        page_result = []
        for url in hrefs:
            for attempt in range(1, max_retry + 1):
                try:
                    Logger.info(f"開始爬取 {url}")
                    start = time.perf_counter()
                    await page.goto(url)
                    
                    #Event Info
                    title = await page.title()
                    Logger.info(title)

                    #取得活動日期與地點
                    if await page.locator("ul.info li").count() > 0:
                        info = page.locator("ul.info li")
                        texts = []
                        for i in range(await info.count()):
                            text = await info.nth(i).inner_text()
                            if text:
                                texts.append(text)
                        schedule = texts[0]
                        location = texts[1]
                    elif await page.locator(".side-inner .section").count() > 0:
                        info = page.locator(".side-inner .section")
                        texts = []
                        for i in range(await info.count()):
                            text = await info.nth(i).inner_text()
                            if text:
                                texts.append(text)
                        schedule = texts[0]
                        location = texts[1]

                    # Click 下一步
                    if await page.locator("a.btn-point").count() > 0:
                        btns = page.locator("a.btn-point")
                        last_btn = btns.nth(await btns.count() - 1)
                        await last_btn.wait_for(state="visible")
                        await last_btn.scroll_into_view_if_needed()
                        await last_btn.click()
                    elif await page.locator("a.btn-ticket").count() > 0:
                        btns = page.locator("a.btn-ticket")
                        last_btn = btns.nth(0)
                        await last_btn.wait_for(state="visible")
                        await last_btn.scroll_into_view_if_needed()
                        await last_btn.click()
                    else:
                        Logger.warning("⚠️ 沒有找到任何 a.btn-point 元素")
                

                    # 取得AngularJS 動態渲染
                    await page.wait_for_selector(".step-bar-wrapper .step-bar", timeout=15000)
                    await page.locator(".step-bar-wrapper .step-bar").inner_html()

                    names = await page.locator(".step-bar-wrapper ul li span:not(.step)").all_inner_texts()
                    clean_names = [n.split("\n", 1)[-1].strip() for n in names]

                    if '劃位' not in clean_names:
                        elapsed = time.perf_counter() - start
                        data = PageResult(
                            url=url,
                            title=title,
                            schedule=schedule,
                            location=location,
                            elapsed_time=elapsed,   
                            event_type=ResultCode.Normal.value
                        )
                        page_result.append(data)
                        Logger.info(f"{url} 爬取完成，用時 {elapsed:.2f} 秒")
                        Logger.info(data)
                        break           
                    else:
                        # 新增可選位票券
                        await page.wait_for_selector(".ticket-unit", timeout=15000)
                        units = page.locator(".ticket-unit")
                        tickets = []
                        target_ticket_order = 0
                        is_target = False
                        disable_keywords = ["身障", "身心障礙"]
                        for order in range(await units.count()):
                            unit = units.nth(order)
                            name = await safe_text(unit, ".ticket-name, .title, h3")
                            seat = await safe_text(unit, ".ticket-seat, .title")
                            price = await safe_text(unit, ".ticket-price, .price")
                            soldout = await unit.locator(":text('已售完')").count() > 0
                            
                            if "電腦" not in seat and "VIP" not in seat and not any(word in name for word in disable_keywords) and "優惠" not in name:
                                target_ticket_order += 1
                                is_target = True
                            if not soldout:
                                target_ticket_order -= 1
                            else:
                                is_target = False
                            tickets.append(
                                {
                                    "name": name, 
                                    "seat": seat, 
                                    "price": price, 
                                    "soldout": soldout, 
                                    "list_order": order, 
                                    "target_ticket_order": target_ticket_order, 
                                    "is_target": is_target
                                }
                            )
                        target_ticket = next((t for t in tickets if t.get("is_target")), tickets[-1])
                        # 電腦選位判定
                        if "電腦" in tickets[target_ticket.get("list_order")].get("seat"):
                            elapsed = time.perf_counter() - start
                            data = PageResult(
                                url=url,
                                title=title,
                                schedule=schedule,
                                location=location,
                                tickets=tickets,
                                elapsed_time=elapsed,
                                event_type=ResultCode.Computer.value
                            )
                            page_result.append(data)
                            Logger.info("電腦選位")
                            Logger.info(f"{url} 爬取完成，用時 {elapsed:.2f} 秒")
                            Logger.info(data)
                            break

                        # 站立坐位判定
                        if "站席" in tickets[target_ticket.get("list_order")].get("seat"):
                            elapsed = time.perf_counter() - start
                            data = PageResult(
                                url=url,
                                title=title,
                                schedule=schedule,
                                location=location,
                                tickets=tickets,
                                elapsed_time=elapsed,
                                event_type=ResultCode.STANDING.value
                            )
                            page_result.append(data)
                            Logger.info("全區站席")
                            Logger.info(f"{url} 爬取完成，用時 {elapsed:.2f} 秒")
                            Logger.info(data)
                            break
                        
                        # VIP坐位判定
                        if "vip" in tickets[target_ticket.get("list_order")].get("name", "").lower():
                            elapsed = time.perf_counter() - start
                            data = PageResult(
                                url=url,
                                title=title,
                                schedule=schedule,
                                location=location,
                                tickets=tickets,
                                elapsed_time=elapsed,
                                event_type=ResultCode.VIP.value
                            )
                            page_result.append(data)
                            Logger.info("VIP選位")
                            Logger.info(f"{url} 爬取完成，用時 {elapsed:.2f} 秒")
                            Logger.info(data)
                            break
                        
                        # 身障做位判定
                        if any(word in tickets[target_ticket.get("list_order")].get("name") for word in disable_keywords):
                            elapsed = time.perf_counter() - start
                            data = PageResult(
                                url=url,
                                title=title,
                                schedule=schedule,
                                location=location,
                                tickets=tickets,
                                elapsed_time=elapsed,
                                event_type=ResultCode.DISABLE.value
                            )
                            page_result.append(data)
                            Logger.info("身心障礙座位")
                            Logger.info(f"{url} 爬取完成，用時 {elapsed:.2f} 秒")
                            Logger.info(data)
                            break


                        try:
                            # 新增票券
                            btn = page.locator("button.btn-default.plus").nth(target_ticket.get("target_ticket_order"))
                            await btn.wait_for(state="visible")
                            await btn.scroll_into_view_if_needed()
                            await btn.click()

                            # Check Message Box
                            dlg = page.locator(".custom-captcha-inner").first
                            try:
                                await dlg.wait_for(state="attached", timeout=3000)
                                await dlg.wait_for(state="visible", timeout=3000)
                                elapsed = time.perf_counter() - start
                                data = PageResult(
                                    url=url,
                                    title=title,
                                    schedule=schedule,
                                    location=location,
                                    tickets=tickets,
                                    elapsed_time=elapsed,
                                    event_type=ResultCode.MESSAGEBOX.value
                                )
                                page_result.append(data)
                                Logger.info("對話框問題")
                                Logger.info(f"{url} 爬取完成，用時 {elapsed:.2f} 秒")
                                Logger.info(data)
                                break
                            except Exception:
                                Logger.warning("❌ No message box detected within 30s.")
                                pass

                            # 同意著作權
                            await page.locator("#person_agree_terms").check()

                            #取得sitekey
                            site_key = await page.evaluate("() => TIXGLOBAL.pageInfo.recaptcha.sitekeyAdvanced")

                            # 點選下一步、自行選位
                            #await page.locator("button.btn-primary").nth(0).click()
                            btn = page.locator("button.btn-primary").nth(0)
                            await btn.click()
                            site_key = await page.evaluate("() => TIXGLOBAL.pageInfo.recaptcha.sitekeyNormal")
                            
                            import capsolver
                            capsolver.api_key = 'CAP-DC02DBB6D890DC40DDD2782C3AF2D752FB00E620C27BFA3FE5584FAE7130E5A3'
                            # 2. 呼叫 CapSolver (記得 await)
                            Logger.info(f"URL = {page.url}")
                            Logger.info(f"sitekey = {site_key}")

                            task = {
                                "type": "ReCaptchaV2EnterpriseTaskProxyLess",
                                "websiteURL": page.url,
                                "websiteKey": site_key,
                            }

                            Logger.info(f"送出 Capsolver 任務: {task}")

                            try:
                                solution = capsolver.solve(task)
                                Logger.info(f"CapSolver 回應: {solution}")
                            except Exception as e:
                                Logger.error(f"CapSolver 失敗: {repr(e)}")
                                raise

                            # 3. 填入 Token 到 KKTIX 隱藏的 textarea
                            await page.evaluate(f'document.getElementById("g-recaptcha-response").innerHTML="{token}";')

                            # 4. KKTIX 特有的 Angular 觸發 (KKTIX 使用 AngularJS)
                            # 有時候只填 HTML 不夠，需要讓前端框架知道值改變了
                            await page.evaluate(f"""
                                var el = document.getElementById("g-recaptcha-response");
                                angular.element(el).scope().$apply(function(scope) {{
                                    scope.captcha_response = "{token}";
                                }});
                            """)

                            #下一步 & Recapcha Check
                            res = await kktix.click_and_skip_on_captcha(btn, click_timeout=5000, watch_timeout=5000)
                            if res is False:
                                import capsolver
                                capsolver.api_key = 'CAP-DC02DBB6D890DC40DDD2782C3AF2D752FB00E620C27BFA3FE5584FAE7130E5A3'

                                # 解决一个 reCAPTCHA v2 挑战
                                solution = await capsolver.solve({
                                    "type": "ReCaptchaV2TaskProxyLess",
                                    "websiteURL": url,
                                    "websiteKey": site_key,
                                })

                                token = solution.get("gRecaptchaResponse")
                                print(f"解碼成功，取得 Token: {token[:50]}...")

                                # 4. 將 Token 填回網頁中隱藏的 textarea (這是 reCAPTCHA 的標準作法)
                                page.evaluate(f'document.getElementById("g-recaptcha-response").innerHTML="{token}";')
                                
                                # 5. (關鍵) 觸發驗證成功的回呼函數
                                # 很多網站填入 Token 後還不會動，必須手動執行 callback
                                page.evaluate("if (typeof(onSuccess) !== 'undefined') { onSuccess(); }")
                                # 或是更通用的方式：
                                page.evaluate(f'___grecaptcha_cfg.clients[0].aa.l.callback("{token}")')
                                elapsed = time.perf_counter() - start
                                data = PageResult(
                                    url=url,
                                    title=title,
                                    schedule=schedule,
                                    location=location,
                                    tickets=tickets,
                                    elapsed_time=elapsed,
                                    event_type=ResultCode.RECAPCHA.value
                                )
                                page_result.append(data)
                                Logger.info("Recaptcha detected")
                                Logger.info(f"{url} 爬取完成，用時 {elapsed:.2f} 秒")
                                Logger.info(data)
                                break
                            elif res is True:
                                Logger.info("Clicked and success detected — proceed")
                                # 後續處理
                            else:
                                # None：不確定（點擊或等待超時等狀況）
                                raise Exception("Click result unknown — decide policy: retry / skip / raise")

                            # 同意系統通知
                            btn = page.locator("button.btn-primary.pull-right").nth(0)
                            await btn.wait_for(state="visible")
                            await btn.scroll_into_view_if_needed()
                            await btn.click()

                            # 等元素存在於 DOM
                            await page.wait_for_selector("#registrationsShowApp", state="attached", timeout=30000)
                            text = await page.locator("#registrationsShowApp").inner_html()

                            sections = await kktix.collect_all_sections()
                            
                            #已售鑿區域
                            non_candidates = [
                                {
                                    "alt": s["alt"],
                                    "chooseable": s["chooseable"]
                                }
                                for s in sections
                                if not s.get("chooseable")
                            ]
                            Logger.debug(non_candidates)

                            seat_stats = []
                            seat_total = 0
                            seat_avl = 0
                            seat_unavl = 0
                            for s in non_candidates:
                                seat_stats.append(s)

                            #可購買區域
                            candidates = [
                                {
                                    "alt": s["alt"],
                                    "spec_id": s["spec_id"],
                                    "count": s["count_est"],
                                    "chooseable": s["chooseable"]
                                }
                                for s in sections
                                if s.get("chooseable")
                            ]
                            Logger.debug(candidates)
                            
                            for s in candidates:
                                kktix.page = await kktix.back_to_map_if_needed()
                                await kktix.wait_map_ready()
                                await kktix.restore_bubble_pointer_events()

                                # 2) 重新挑下一個要點的 alt
                                alt = s.get('alt')
                                Logger.debug(alt)
                                if not alt:
                                    Logger.warning("[loop] no candidate found; break")
                                    break

                                # 3) 保險關 modal
                                await kktix.close_any_modal()

                                # 4) 點擊
                                try:
                                    await kktix.click_section_by_alt(alt)
                                except Exception as e:
                                    Logger.debug(f"[{alt}] click failed: {e}")
                                    continue  # 換下一輪

                                # 3) 保險關 modal
                                await kktix.close_any_modal()

                                # 5) 確保真的進到 Table
                                try:
                                    await kktix.ensure_table_view()
                                except Exception as e:
                                    Logger.debug(f"[{alt}] not in table: {e}")
                                    continue

                                # 6) 統計
                                stats = await kktix.seat_table_stats()
                                seat_stat = {}
                                if not stats.get("ok"):
                                    Logger.debug(f"[{alt}] seat_table_stats failed: {stats.get('reason')}")
                                else:
                                    seat_stat['area'] = alt
                                    seat_stat['total'] = int(stats['total'])
                                    seat_stat['able'] = int(stats['able'])
                                    seat_stat['not_able'] = int(stats['not_able'])
                                    seat_stat['already'] = int(stats['already'])
                                    seat_stat['unknown'] = int(stats['unknown'])
                                    Logger.debug(f"[{alt}] total={stats['total']}, able={stats['able']}, "
                                        f"not_able={stats['not_able']}, already={stats['already']}, unknown={stats['unknown']}")
                                    seat_total += seat_stat['total']
                                    seat_avl += seat_stat['able'] + seat_stat['already']+ seat_stat['unknown']
                                    seat_unavl += seat_stat['not_able']

                                    seat_stats.append(seat_stat)
                                    Logger.info(seat_stats)

                                # 7) 回 Map，下一輪
                                try:
                                    await kktix.back_to_map_if_needed()
                                    await kktix.wait_map_ready()
                                    await kktix.restore_bubble_pointer_events()
                                except Exception as e:
                                    Logger.info(f"[loop] back to map failed: {e}")
                                    continue

                        except Exception as e:
                            Logger.info(e)
                            # 整合頁面資訊
                            # elapsed = time.perf_counter() - start
                            # data = PageResult(
                            #     url=url,
                            #     title=title,
                            #     schedule=schedule,
                            #     location=location,
                            #     tickets=tickets,
                            #     elapsed_time=elapsed,
                            #     event_type=ResultCode.Complete.value
                            # )
                            # page_result.append(data)
                            # Logger.info(f"{url} 爬取完成，用時 {elapsed:.2f} 秒")
                            # Logger.info(data)
                            break
                        finally:
                            #整合頁面資訊
                            elapsed = time.perf_counter() - start
                            data = PageResult(
                                url=url,
                                title=title,
                                schedule=schedule,
                                location=location,
                                event_type=ResultCode.Complete.value,
                                tickets=tickets,
                                seat_stats=seat_stats,
                                total_seats=seat_total,
                                available_seats=seat_avl,
                                sold_seats=seat_unavl,
                                elapsed_time=elapsed
                            )
                            Logger.info(f"{url} 爬取完成，用時 {elapsed:.2f} 秒")
                            Logger.info(data)
                            page_result.append(data)
                    break
                except Exception as e:
                    Logger.warning(f"Attempt {attempt} failed for {url}: {e}")
                    await page.close()
                    if attempt == max_retry:
                        Logger.error(f"Giving up on {url}")
                        return False
                    await asyncio.sleep(2)  # 等一下再試
                    context = await chrome_context(p, persist_dir="./user-data")
                    page = context.pages[0] if context.pages else await context.new_page()

                    kktix = Kktix(page)   

        from dataclasses import asdict
        df = pd.DataFrame([asdict(p) for p in page_result])
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        df.to_csv(f"logs/output_{timestamp}.csv", index=False, encoding="utf-8-sig")
        from IPython.display import display
        display(df)
            #print(df.to_markdown(index=False))   
            #await page.wait_for_event("close", timeout=0)
                

            # finally:
            #     # Uncomment to close browser automatically
            #     await browser.close()
            #     pass


if __name__ == "__main__":
    asyncio.run(main())

