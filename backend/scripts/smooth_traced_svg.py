"""Smooths a VTracer polygon SVG (the travel icons in frontend/public/cover-art):
drops the 1-unit stair steps and turns the straight segments into curves
through the remaining points (Catmull-Rom as cubic Béziers), keeping real
corners (leaf tips, stems) sharp. A hairline stroke of each shape's own
colour closes the seams between stacked shapes.

Usage: python -m scripts.smooth_traced_svg in-v1.svg out-v2.svg
(write a new file: a published one is never changed in place)"""
import math, re, sys

EPS = 1.1          # stair steps below this (source pixels) are dropped
CORNER_DEG = 35    # a turn sharper than this stays a corner
MAX_BEND = 30      # degrees


def rings(d):
    out = []
    for sub in re.findall(r"M[^M]*", d):
        nums = list(map(float, re.findall(r"-?\d+(?:\.\d+)?", sub)))
        pts = [(nums[i], nums[i + 1]) for i in range(0, len(nums), 2)]
        dedup = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
        if len(dedup) > 1 and dedup[0] == dedup[-1]:
            dedup.pop()
        out.append(dedup)
    return out


def _dist(p, a, b):
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy)
    if L == 0:
        return math.hypot(x - x1, y - y1)
    return abs(dy * x - dx * y + x2 * y1 - y2 * x1) / L


def rdp(pts, eps):
    if len(pts) < 3:
        return pts
    i, dmax = max(((i, _dist(pts[i], pts[0], pts[-1])) for i in range(1, len(pts) - 1)), key=lambda t: t[1])
    if dmax <= eps:
        return [pts[0], pts[-1]]
    return rdp(pts[: i + 1], eps)[:-1] + rdp(pts[i:], eps)


def simplify_ring(pts):
    if len(pts) < 6:
        return pts
    # split the closed ring at the point farthest from the first one
    far = max(range(len(pts)), key=lambda i: math.dist(pts[0], pts[i]))
    a = rdp(pts[: far + 1], EPS)
    b = rdp(pts[far:] + [pts[0]], EPS)
    out = a[:-1] + b[:-1]
    return out if len(out) >= 4 else pts


def turn(a, b, c):
    v1 = (b[0] - a[0], b[1] - a[1]); v2 = (c[0] - b[0], c[1] - b[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 == 0 or n2 == 0:
        return 0
    cos = max(-1, min(1, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(cos))


def smooth_ring(pts):
    n = len(pts)
    corner = [turn(pts[i - 1], pts[i], pts[(i + 1) % n]) > CORNER_DEG for i in range(n)]

    def unit(v):
        L = math.hypot(*v) or 1
        return (v[0] / L, v[1] / L)

    def direction(i, toward):
        # Catmull-Rom direction; at a corner, aim along the segment instead
        if corner[i]:
            j = (i + toward) % n
            return unit(((pts[j][0] - pts[i][0]) * toward, (pts[j][1] - pts[i][1]) * toward))
        p, q = pts[i - 1], pts[(i + 1) % n]
        return unit((q[0] - p[0], q[1] - p[1]))

    def clamp(u, seg):
        # the curve leaves at most MAX_BEND off the straight segment, so a
        # long straight edge stays (almost) straight and never uncovers the
        # layer underneath
        cross = seg[0] * u[1] - seg[1] * u[0]
        dot = seg[0] * u[0] + seg[1] * u[1]
        a = math.atan2(cross, dot)
        lim = math.radians(MAX_BEND)
        if abs(a) <= lim:
            return u
        a = math.copysign(lim, a)
        return (seg[0] * math.cos(a) - seg[1] * math.sin(a), seg[0] * math.sin(a) + seg[1] * math.cos(a))

    f = lambda v: f"{v:.1f}".rstrip("0").rstrip(".")
    d = f"M{f(pts[0][0])},{f(pts[0][1])}"
    for i in range(n):
        p1, p2 = pts[i], pts[(i + 1) % n]
        # handles a third of this segment long: no overshoot next to a long one
        k = math.dist(p1, p2) / 3
        seg = unit((p2[0] - p1[0], p2[1] - p1[1]))
        u1, u2 = clamp(direction(i, 1), seg), clamp(direction((i + 1) % n, -1), seg)
        c1 = (p1[0] + u1[0] * k, p1[1] + u1[1] * k)
        c2 = (p2[0] - u2[0] * k, p2[1] - u2[1] * k)
        d += f" C{f(c1[0])},{f(c1[1])} {f(c2[0])},{f(c2[1])} {f(p2[0])},{f(p2[1])}"
    return d + " Z"


def smooth_d(d):
    return " ".join(smooth_ring(simplify_ring(r)) for r in rings(d) if len(r) >= 3)


src = open(sys.argv[1]).read()
if any("C" in d for d in re.findall(r' d="([^"]*)"', src)):
    sys.exit(f"{sys.argv[1]}: already has curves, left as is")
out = re.sub(r' d="([^"]*)"', lambda m: f' d="{smooth_d(m.group(1))}"', src)
out = re.sub(r'fill="(#[0-9A-Fa-f]{6})"', r'fill="\1" stroke="\1" stroke-width="1" stroke-linejoin="round"', out)
out = out.replace("<!-- Generator: visioncortex VTracer 0.6.12 -->", "<!-- Traced with VTracer 0.6.12, then smoothed into curves -->")
open(sys.argv[2], "w").write(out)
print(sys.argv[1], len(src), "->", len(out))
