"""Describe dictionaries used for successful-step and failure statistics."""
from typing import TypedDict, Dict, Any


class StepMetric(TypedDict, total=False):
    """Map lifecycle step names to total time, maximum time and execution count."""
    login: Dict[str, Any]
    navigate: Dict[str, Any]
    collect: Dict[str, Any]
    crawl: Dict[str, Any]
    persist: Dict[str, Any]


class FailureMetric(TypedDict, total=False):
    """Map failure categories to accumulated elapsed time and occurrence count."""
    crawl: Dict[str, Any]
    seat_map: Dict[str, Any]
