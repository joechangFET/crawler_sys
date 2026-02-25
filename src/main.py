import asyncio
from core.browser import BrowserManager
from core.runner import run_crawler
from config.env_loader import env
from utils.logger_factory import LoggerFactory


async def main():
    system_logger = LoggerFactory.create(
        name="CrawlerSystem",
        log_dir="logs/system",
        level="INFO"
    )
    system_logger.info("Starting Crawler System")

    sites = ["kktix"]

    async with BrowserManager(max_contexts=1, headless=env.HEADLESS) as bm:
        tasks = [
            run_crawler(site, bm)
            for site in sites
        ]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
