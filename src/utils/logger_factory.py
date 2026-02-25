import logging
import sys
import os
from datetime import datetime

class IconFormatter(logging.Formatter):
    ICONS = {
        'DEBUG': '🐛',
        'INFO': '✅',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🔥',
    }

    def format(self, record: logging.LogRecord) -> str:
        icon = self.ICONS.get(record.levelname, '')
        record.levelicon = icon
        return super().format(record)

class LoggerFactory:

    @staticmethod
    def create(
        *,
        name: str,
        log_dir: str | None = None,
        level: str = "INFO",
    ) -> logging.Logger:

        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        logger.propagate = False

        if logger.handlers:
            return logger

        formatter = IconFormatter(
            "%(asctime)s | %(levelicon)s %(levelname)-8s | %(name)s | "
            "%(funcName)s:%(lineno)d | %(message)s"
        )

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        logger.addHandler(console)

        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d")
            log_file = f"{name}_{ts}.log"
            file_path = os.path.join(
                log_dir,
                log_file
            )
            file_handler = logging.FileHandler(file_path, encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        return logger
