import importlib
from src.core.browser import BrowserManager
from src.core.human_behavior import _mouse_positions
from src.utils.env_loader import env
from src.utils.logger_factory import LoggerFactory
from src.utils.metrics import CrawlMetrics


def load_crawler(site_name: str):
    module = importlib.import_module(f"src.sites.{site_name}.crawler")
    class_name = f"{site_name.title().replace('_', '')}Crawler"
    return getattr(module, class_name)


async def run_crawler(site: str, bm: BrowserManager):
    """
    Dynamically load and run the crawler for the given site name.

    Args:
        site: Site identifier (e.g. "kktix"). Must match a module under sites/<site>/crawler.py.
        bm:   Shared BrowserManager instance.
    """
    crawler_logger = LoggerFactory.create(
        name=site,
        log_dir=f"logs/crawler/{site}",
        level=env.LOG_LEVEL,
    )
    metrics = CrawlMetrics(site=site)
    crawler_logger.info(f"Starting crawler for {site}")

    context, page = await bm.new_context_page()

    try:
        CrawlerCls = load_crawler(site)
        crawler = CrawlerCls(context, page, logger=crawler_logger, metrics=metrics)
        await crawler.run()

    except Exception:
        crawler_logger.exception(f"Error occurred while running crawler for {site}")

    finally:
        await bm.close_page(page)
        _mouse_positions.pop(id(page), None)
        metrics.finish()
        crawler_logger.info(f"Crawl metrics for {site}: {metrics}")
        crawler_logger.info(f"Finished crawler for {site}")
