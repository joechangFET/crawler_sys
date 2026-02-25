from dataclasses import dataclass, field
from datetime import datetime
import time
from typing import TypedDict, Dict, Any


class StepMetric(TypedDict, total=False):
    login: Dict[str, Any]
    navigate: Dict[str, Any]
    collect: Dict[str, Any]
    crawl: Dict[str, Any]
    persist: Dict[str, Any]


class FailureMetric(TypedDict, total=False):
    crawl: Dict[str, Any]
    seat_map: Dict[str, Any]