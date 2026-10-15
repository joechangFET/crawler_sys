"""Represent one event's metadata, ticket details and aggregated seat results."""
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class PageResult:
    """Store one event result; ticket and seat-stat lists are independent per instance."""
    url: Optional[str] = None
    title: Optional[str] = None
    schedule: Optional[str] = None
    location: Optional[str] = None
    organizer: Optional[str] = None
    booking_start_time: Optional[str] = None
    booking_end_time: Optional[str] = None
    elapsed_time: Optional[float] = None
    event_type: Optional[str] = None
    tickets: list[dict] = field(default_factory=list)
    seat_stats: list[dict] = field(default_factory=list)
    seat_total: int = 0
    seat_avl: int = 0
    seat_unavl: int = 0
