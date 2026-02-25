from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class PageResult:
    url: Optional[str] = None
    title: Optional[str] = None
    schedule: Optional[str] = None
    location: Optional[str] = None
    elapsed_time: Optional[float] = None
    event_type: Optional[str] = None
    tickets: list[dict] = field(default_factory=list)
    seat_stats: list[dict] = field(default_factory=list)
    seat_total: int = 0
    seat_avl: int = 0
    seat_unavl: int = 0
    