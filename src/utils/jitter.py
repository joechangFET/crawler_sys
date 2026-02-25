import random

def jitter(base: float, r: float = 0.4) -> float:
    # 以 base 為中心的隨機抖動（避免固定延遲）
    return max(0.05, random.uniform(base*(1-r), base*(1+r)))