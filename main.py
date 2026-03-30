import asyncio
from src.core.browser import BrowserManager
from src.core.runner import run_crawler
from src.utils.env_loader import env
from src.utils.logger_factory import LoggerFactory


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
