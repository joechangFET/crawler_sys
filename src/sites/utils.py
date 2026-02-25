import re
from typing import Tuple, Sequence

async def safe_text(unit, selector, timeout=3000):
        loc = unit.locator(selector)
        if await loc.count() == 0:
            return ""
        try:
            return (await loc.text_content(timeout=timeout) or "").strip()
        except Exception:
            return ""

def parse_coords(coords: str) -> Sequence[int]:
    # 允許空白、換行；只抓整數（image map coords 只會是整數）
    return [int(m) for m in re.findall(r"-?\d+", coords or "")]

def centroid(coords: str) -> Tuple[float, float]:
    """
    依 coords 長度判斷 shape:
      - circle: x,y,r  -> (x,y)
      - rect:   x1,y1,x2,y2 -> ((x1+x2)/2, (y1+y2)/2)
      - poly:   x1,y1,x2,y2,...,xn,yn -> 多邊形重心
    """
    nums = parse_coords(coords)
    n = len(nums)

    if n == 3:
        # circle
        x, y, _ = nums
        return float(x), float(y)

    if n == 4:
        # rect
        x1, y1, x2, y2 = nums
        return (x1 + x2) / 2.0, (y1 + y2) / 2.0

    if n >= 6 and n % 2 == 0:
        # polygon
        pts = list(zip(nums[0::2], nums[1::2]))
        A = Cx = Cy = 0.0
        for i in range(len(pts)):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % len(pts)]
            cross = x1 * y2 - x2 * y1
            A += cross
            Cx += (x1 + x2) * cross
            Cy += (y1 + y2) * cross
        if A != 0:
            A *= 0.5
            return Cx / (6 * A), Cy / (6 * A)

    # 萬一格式怪異：回退到所有點的幾何中心（平均）
    if n >= 2 and n % 2 == 0:
        xs = nums[0::2]; ys = nums[1::2]
        return sum(xs) / (n // 2), sum(ys) / (n // 2)

    raise ValueError(f"Bad coords: {coords!r}")