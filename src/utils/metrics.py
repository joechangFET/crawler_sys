from dataclasses import dataclass, field
from datetime import datetime
from model.metrics import StepMetric, FailureMetric
import time

@dataclass
class CrawlMetrics:
    site: str

    # 人類可讀時間
    start_dt: datetime = field(default_factory=datetime.now)
    end_dt: datetime | None = None

    # 精準計時
    _start_perf: float = field(default_factory=time.perf_counter)
    _end_perf: float = 0

    event_count: int = 0
    pages: int = 0
    steps: dict[str, StepMetric] = field(default_factory=dict)
    failed: dict[str, FailureMetric] = field(default_factory=dict)
    success: bool = True
    duration: str = ""

    def finish(self):
        self.end_dt = datetime.now()
        self._end_perf = time.perf_counter()
        self.duration = self.total_time_str
    
    @property
    def total_seconds(self) -> float:
        return self._end_perf - self._start_perf

    @property
    def total_time_str(self) -> str:
        seconds = int(self.total_seconds)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h} hours {m} minutes {s} seconds"

    @property
    def start_time_str(self) -> str:
        return self.start_dt.strftime("%Y-%m-%d %H:%M:%S")

    @property
    def end_time_str(self) -> str:
        return self.end_dt.strftime("%Y-%m-%d %H:%M:%S") if self.end_dt else ""

    
