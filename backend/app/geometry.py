from __future__ import annotations

import math
from collections.abc import Sequence

from .rules import Shape

Point = tuple[float, float]


def heading_vector(heading_deg: float) -> Point:
    rad = math.radians(heading_deg)
    return math.sin(rad), -math.cos(rad)


def bearing(from_pt: Point, to_pt: Point) -> float:
    dx, dy = to_pt[0] - from_pt[0], to_pt[1] - from_pt[1]
    return math.degrees(math.atan2(dx, -dy)) % 360


def angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def _segment_nearest(p: Point, a: Point, b: Point) -> Point:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return a
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length2))
    return ax + t * dx, ay + t * dy


def nearest_point(p: Point, shape: Shape) -> Point:
    if shape.type == "rect":
        return (min(max(p[0], shape.x), shape.x + shape.w), min(max(p[1], shape.y), shape.y + shape.h))
    if shape.type == "circle":
        d = math.dist(p, (shape.x, shape.y))
        if d <= shape.r or d == 0:
            return p
        k = shape.r / d
        return shape.x + (p[0] - shape.x) * k, shape.y + (p[1] - shape.y) * k
    pts = shape.points or []
    best, best_d = pts[0], math.inf
    for a, b in zip(pts, pts[1:], strict=False):
        q = _segment_nearest(p, a, b)
        d = math.dist(p, q)
        if d < best_d:
            best, best_d = q, d
    return best


def distance_to(p: Point, shape: Shape) -> float:
    d = math.dist(p, nearest_point(p, shape))
    if shape.type == "line":
        return max(0.0, d - shape.width / 2)
    return d


def contains(shape: Shape, p: Point) -> bool:
    return distance_to(p, shape) == 0


def point_in_polygon(p: Point, poly: Sequence[Sequence[float]]) -> bool:
    x, y = p
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def to_latlon(p: Point, origin: dict[str, float]) -> tuple[float, float]:
    lat0, lon0 = origin["lat"], origin["lon"]
    lat = lat0 - p[1] / 111_320
    lon = lon0 + p[0] / (111_320 * math.cos(math.radians(lat0)))
    return lat, lon


def format_latlon(p: Point, origin: dict[str, float]) -> str:
    lat, lon = to_latlon(p, origin)
    return f"{abs(lat):.4f}°{'N' if lat >= 0 else 'S'} {abs(lon):.4f}°{'W' if lon < 0 else 'E'}"
