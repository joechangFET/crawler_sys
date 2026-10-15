"""Define the crawler lifecycle, per-URL retries and execution metrics.

Site implementations supply navigation, authentication, collection, extraction
and persistence. Browser ownership remains with BrowserManager.
"""
import time
from pathlib import Path
from abc import ABC, abstractmethod
from logging import Logger
from collections import Counter, defaultdict
from src.core.recaptcha import Recaptcha
from src.core.llm import ChatgptClient
from src.model.page import PageResult
from src.model.enums import ResultCode
from src.model.metrics import StepMetric, FailureMetric
from src.model.llm import LLMConfig
from src.utils.logger_factory import LoggerFactory
from src.utils.metrics import CrawlMetrics
from src.utils.env_loader import env

class BaseCrawler(ABC):
    """Abstract site crawler with shared services, results and retry accounting."""
    def __init__(self, context, page, logger: Logger, metrics: CrawlMetrics):
        """Bind browser resources, metrics and shared external service clients."""
        self.context = context
        self.page = page
        self.logger = logger
        self.step_metrics: StepMetric = defaultdict(lambda: {"max": 0.0, "total": 0.0, "count": 0})
        self.fail_metrics: FailureMetric = defaultdict(lambda: {"times": 0.0, "count": 0})
        self.metrics = metrics
        self.env_config = env

        self.page_info = None
        self.start_time = None
        self.url_list = []
        self.url_counter = 0
        self.result = []
        self.output_dir = Path("result")

        chatbot_config = LLMConfig(
            api_key=self.env_config.CHATGPT_API_KEY)
        self.logger.info(f"Initialized ChatGPT Client with model: {chatbot_config.model_name}")
        self.chatbot_client = ChatgptClient(chatbot_config)
        self.recaptcha_solver = Recaptcha(self.page, self.logger, self.env_config.CAPSOLVER_API)

    async def run(self):
        """Navigate, authenticate, collect URLs, crawl each with up to two attempts, and persist.

        Crawl exceptions are logged and counted before retrying the URL.
        Navigation, login, collection and persistence errors propagate to the runner.
        """
        await self.navigate()
        await self.login()
        await self.collect()
        self.metrics.event_count = len(self.url_list)
        try:
            for url in self.url_list:
                self.url_counter += 1
                LoggerFactory.set_url_progress(self.logger, self.url_counter, len(self.url_list))

                for try_number in range(2):
                    step_start = time.perf_counter()
                    try:
                        self.logger.info("Processing URL")
                        self.page_info = PageResult()
                        self.logger.info(f"Collecting data from {url}")
                        self.start_time = time.perf_counter()
                        await self.page.goto(url, wait_until="domcontentloaded")
                        self.page_info.url = url
                        self.page_info.event_type = ResultCode.Normal.value
                        await self.crawl()
                        elapsed = time.perf_counter() - step_start
                        self.step_metrics["crawl"]["total"] += elapsed
                        self.step_metrics["crawl"]["max"] = max(elapsed, self.step_metrics["crawl"]["max"])
                        self.step_metrics["crawl"]["count"] += 1
                        counter = Counter(r.event_type for r in self.result if r.event_type)
                        self.logger.info(f"Event Type Counts: {dict(counter)}")
                        break
                    except Exception as e:
                        self.fail_metrics["crawl"]["times"] += time.perf_counter() - step_start
                        self.fail_metrics["crawl"]["count"] += 1
                        self.logger.warning(f"Error processing URL {url}: {e}")
        finally:
            LoggerFactory.clear_url_progress(self.logger)
        self.metrics.steps = self.step_metrics
        self.metrics.failed = self.fail_metrics

        await self.persist()

    @abstractmethod
    async def navigate(self):
        """Open the site entry page and prepare it for authentication."""
        pass

    @abstractmethod
    async def login(self):
        """Authenticate when needed using the current browser session."""
        pass

    @abstractmethod
    async def collect(self):
        """Populate url_list with event URLs to process."""
        pass

    @abstractmethod
    async def crawl(self):
        """Extract the current event into page_info and record its result."""
        pass

    @abstractmethod
    async def persist(self):
        """Write accumulated results and perform site-specific reporting."""
        pass
