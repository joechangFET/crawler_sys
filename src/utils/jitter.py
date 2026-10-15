"""Generate bounded random variations around a caller-supplied delay."""
import random

def jitter(base: float, r: float = 0.4) -> float:
    # 以 base 為中心的隨機抖動（避免固定延遲）
    """Return a random value within base * (1 +/- r), with a minimum of 0.05.

    The return value uses the same units as base; callers choose the unit.
    """
    return max(0.05, random.uniform(base*(1-r), base*(1+r)))
