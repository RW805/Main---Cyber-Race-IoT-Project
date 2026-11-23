"""
Track definition -- pure Python (no pygame), so it can be unit tested headlessly.

The circuit is described by a handful of CONTROL_POINTS that a closed
centripetal Catmull-Rom spline is drawn through. That spline is resampled into evenly
spaced centreline samples, and everything else is derived from those samples:

  * Road:      any point within HALF_WIDTH of the centreline is "on track".
  * Grass:     a verge GRASS_WIDTH px wide runs along both sides of the road.
               It's drivable but slow.
  * Walls:     a hard barrier runs round the whole circuit at the outer edge of
               the grass (and round the edge of the screen). The car is pushed
               back and slides along it. Where two parts of the circuit run
               close together the verges merge and a single wall runs between them.
  * Laps:      ordered checkpoint gates around the centreline (see LapCounter).
               Works for any shape and either driving direction as long as the
               car follows the order the centreline is defined in.

To change the circuit, edit CONTROL_POINTS. Run `python3 track.py` to re-check that it doesn't overlap itself.
"""
import math

# --- Circuit definition ------------------------------------------------------
# (x, y) in screen pixels on a 1280x800 window. Listed in driving order; the
# first points form the start/finish straight along the bottom, driven left->right.
CONTROL_POINTS = [
    (330, 700), (620, 705), (900, 700),            # start/finish straight
    (1060, 685), (1155, 628), (1192, 540),         # T1: fast right-hand sweeper
    (1176, 446), (1110, 390), (1010, 402),         # T2: bends back into the infield
    (940, 455), (850, 470), (770, 415),            # T3-T4: chicane
    (760, 325), (830, 262), (940, 244),            # T5: climbing right
    (1060, 240), (1124, 216), (1150, 154),         # T6: hairpin at the top right
    (1120, 100), (1060, 82), (950, 86),
    (800, 110), (650, 160), (520, 110),            # top straight with a dip
    (380, 90), (265, 122), (185, 215),             # T7: sweeping left
    (200, 310), (280, 368), (345, 430),            # T8-T9: S-bend
    (350, 485), (312, 527), (250, 556),
    (185, 585), (150, 640), (174, 697),            # T10: big left-hander onto the straight
    (230, 722),
]

HALF_WIDTH = 48          # road is 96px wide
SAMPLE_SPACING = 6.0     # px between resampled centreline points
CAR_RADIUS = 10          # used for wall collisions

GRASS_WIDTH = 20         # px of grass between the road edge and the wall
WALL_THICKNESS = 6       # how thick the wall is drawn (px)
SCREEN_W, SCREEN_H = 1280, 800
SCREEN_WALL = 6          # wall drawn round the screen edge, same thickness

NUM_GATES = 16           # checkpoints per lap (gate 0 is the start/finish line)


# --- Spline helpers ------------------------------------------------------------
def _catmull_rom(p0, p1, p2, p3, t, alpha=0.5):
    """Centripetal Catmull-Rom (Barry-Goldman form). Unlike the uniform version it
    doesn't overshoot or loop when control points are unevenly spaced."""
    t0 = 0.0
    t1 = t0 + math.dist(p0, p1) ** alpha
    t2 = t1 + math.dist(p1, p2) ** alpha
    t3 = t2 + math.dist(p2, p3) ** alpha
    tt = t1 + t * (t2 - t1)

    def lerp(a, b, ta, tb):
        w = (tt - ta) / (tb - ta)
        return tuple(a[i] * (1 - w) + b[i] * w for i in (0, 1))

    a1, a2, a3 = lerp(p0, p1, t0, t1), lerp(p1, p2, t1, t2), lerp(p2, p3, t2, t3)
    b1, b2 = lerp(a1, a2, t0, t2), lerp(a2, a3, t1, t3)
    return lerp(b1, b2, t1, t2)


def _dense_closed_spline(points, steps=30):
    n = len(points)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = points[(i - 1) % n], points[i], points[(i + 1) % n], points[(i + 2) % n]
        for s in range(steps):
            out.append(_catmull_rom(p0, p1, p2, p3, s / steps))
    return out


def _resample_closed(poly, spacing):
    """Resample a closed polyline into points spaced `spacing` apart by arc length."""
    n = len(poly)
    seg_len = [math.dist(poly[i], poly[(i + 1) % n]) for i in range(n)]
    total = sum(seg_len)
    count = max(8, int(total / spacing))
    step = total / count
    out, seg, acc, target = [], 0, 0.0, 0.0
    for _ in range(count):
        while acc + seg_len[seg] < target:
            acc += seg_len[seg]
            seg += 1
        f = (target - acc) / seg_len[seg] if seg_len[seg] else 0.0
        a, b = poly[seg], poly[(seg + 1) % n]
        out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
        target += step
    return out


# --- Track ---------------------------------------------------------------------
class Track:
    def __init__(self, control_points=None, half_width=HALF_WIDTH, grass_width=GRASS_WIDTH,
                 spacing=SAMPLE_SPACING, num_gates=NUM_GATES, screen=(SCREEN_W, SCREEN_H),
                 track_id="neon-circuit", name="NEON CIRCUIT"):
        pts = control_points if control_points is not None else CONTROL_POINTS
        self.track_id = track_id      # identifies the level (each level needs its own)
        self.name = name              # shown on the level intro screen
        self.half_width = half_width
        self.grass_width = grass_width
        self.wall_dist = half_width + grass_width   # centreline -> inner face of the wall
        self.screen = screen
        self.samples = _resample_closed(_dense_closed_spline(pts), spacing)
        self.n = len(self.samples)
        self.spacing = spacing

        # Unit tangents and left-hand normals at each sample.
        self.tangents, self.normals = [], []
        for i in range(self.n):
            a, b = self.samples[(i - 1) % self.n], self.samples[(i + 1) % self.n]
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy) or 1.0
            tx, ty = dx / length, dy / length
            self.tangents.append((tx, ty))
            self.normals.append((ty, -tx))

        self.gates = [round(i * self.n / num_gates) % self.n for i in range(num_gates)]

    # -- geometry ---------------------------------------------------------------
    def nearest(self, x, y, hint=None, window=60):
        """Index of the closest centreline sample, and the distance to it.

        With a `hint` (last known index) only a window around it is searched,
        which is faster and stops the result jumping to a different part of the
        track that happens to be nearby. Falls back to a full search if the
        windowed result is far from the road (e.g. the car is deep in the grass).
        """
        samples, n = self.samples, self.n
        best_i, best_d2 = 0, float("inf")
        if hint is not None:
            for k in range(-window, window + 1):
                i = (hint + k) % n
                sx, sy = samples[i]
                d2 = (sx - x) ** 2 + (sy - y) ** 2
                if d2 < best_d2:
                    best_i, best_d2 = i, d2
            if best_d2 <= (self.half_width * 3) ** 2:
                return best_i, math.sqrt(best_d2)
            best_d2 = float("inf")
        for i, (sx, sy) in enumerate(samples):
            d2 = (sx - x) ** 2 + (sy - y) ** 2
            if d2 < best_d2:
                best_i, best_d2 = i, d2
        return best_i, math.sqrt(best_d2)

    def is_on_track(self, x, y, hint=None):
        return self.nearest(x, y, hint)[1] <= self.half_width

    def resolve_wall(self, x, y, idx, radius=CAR_RADIUS):
        """Keep the car inside the walls.

        The wall runs at `wall_dist` from the centreline, so the car's centre may be
        at most `wall_dist - radius` from its nearest centreline sample. Returns
        (x, y, idx, normal): the corrected position, nearest sample, and the outward
        wall normal if a wall was hit (None if not).
        """
        limit = self.wall_dist - radius
        cx, cy = self.samples[idx]
        dist = math.hypot(x - cx, y - cy)
        normal = None
        if dist > limit:
            # The windowed search can miss a closer section of the circuit next
            # door (where verges merge), so confirm with a full search first.
            idx, dist = self.nearest(x, y)
            cx, cy = self.samples[idx]
        if dist > limit and dist > 0:
            nx, ny = (x - cx) / dist, (y - cy) / dist
            x, y = cx + nx * limit, cy + ny * limit
            normal = (nx, ny)

        # Wall round the edge of the screen.
        w, h = self.screen
        lo = SCREEN_WALL + radius
        if x < lo:
            x, normal = lo, (-1.0, 0.0)
        elif x > w - lo:
            x, normal = w - lo, (1.0, 0.0)
        if y < lo:
            y, normal = lo, (0.0, -1.0)
        elif y > h - lo:
            y, normal = h - lo, (0.0, 1.0)
        return x, y, idx, normal

    def edge_point(self, idx, side, offset=0.0):
        """Point on the left (+1) or right (-1) road edge, `offset` px beyond it."""
        cx, cy = self.samples[idx % self.n]
        nx, ny = self.normals[idx % self.n]
        d = self.half_width + offset
        return cx + nx * d * side, cy + ny * d * side

    def start_pose(self, behind=14):
        """Grid position `behind` samples before the start line, facing along the track."""
        i = (-behind) % self.n
        tx, ty = self.tangents[i]
        x, y = self.samples[i]
        return x, y, math.atan2(ty, tx), i

    def circ_delta(self, a, b):
        """Signed shortest index distance from a to b around the loop."""
        d = (b - a) % self.n
        return d - self.n if d > self.n // 2 else d


# --- Lap counting --------------------------------------------------------------
class LapCounter:
    """Counts laps with ordered checkpoint gates.

    Gate 0 is the start/finish line. A lap only counts once the car has driven
    forward across every gate in order and then back across gate 0, so reversing
    over the line, jittering on it, or cutting across the infield can't add laps.
    The first time the car crosses the line from the grid doesn't count as a lap.
    """

    def __init__(self, track):
        self.track = track
        self.laps = 0
        self.expected = 0       # next gate the car must cross
        self.started = False    # becomes True when the car first crosses the line
        self.last_lap_idx = None
        self._prev = None

    def update(self, idx):
        prev, self._prev = self._prev, idx
        if prev is None:
            return self.laps
        t = self.track
        step = t.circ_delta(prev, idx)
        if step == 0 or abs(step) > t.n // 4:   # no movement, or a discontinuity: ignore
            return self.laps
        # Several gates can be crossed in a single update if the step is large.
        for _ in range(len(t.gates)):
            gate = t.gates[self.expected]
            d_prev = t.circ_delta(gate, prev)
            d_cur = t.circ_delta(gate, idx)
            if d_prev < 0 <= d_cur:     # crossed forward over this gate
                if self.expected == 0:
                    if self.started:
                        self.laps += 1
                    self.started = True
                self.expected = (self.expected + 1) % len(t.gates)
            else:
                break
        return self.laps


def min_corner_radius(track, k=6):
    """Tightest corner radius (px) on the centreline, from circles through
    samples k steps either side. Too small and the road edge pinches shut."""
    best = float("inf")
    for i in range(track.n):
        a, b, c = track.samples[(i - k) % track.n], track.samples[i], track.samples[(i + k) % track.n]
        area2 = abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]))
        if area2:
            best = min(best, math.dist(a, b) * math.dist(b, c) * math.dist(c, a) / (2 * area2))
    return best


def _self_check(track):
    """Return the smallest distance between parts of the centreline that are far
    apart along the lap. Must exceed the road width or the track overlaps itself."""
    pts, n = track.samples, track.n
    gap = int(4 * track.half_width / track.spacing)  # ignore neighbours along the lap
    worst = float("inf")
    for i in range(0, n, 2):
        for j in range(i + gap, n, 2):
            if min(j - i, n - (j - i)) < gap:
                continue
            worst = min(worst, math.dist(pts[i], pts[j]))
    return worst


# --- Levels ----------------------------------------------------------------------
# Every player races these three, in this order. They're fixed data, so every
# player on every machine gets exactly the same tracks.
# Every level needs its own id.
LEVELS = [
    {"id": "neon-circuit", "name": "NEON CIRCUIT", "half_width": 48,   # easy: the original track
     "points": CONTROL_POINTS},
    {"id": "data-drift", "name": "DATA DRIFT", "half_width": 44,       # medium: narrower, one big hairpin
     "points": [
         (400, 700), (660, 702), (920, 698),
         (1075, 688), (1165, 625), (1190, 525),
         (1170, 410), (1120, 300), (1030, 215), (920, 185),
         (800, 205), (720, 275), (650, 360), (560, 400), (470, 365),
         (440, 280), (390, 230), (300, 250),
         (215, 320), (170, 420), (170, 530), (200, 615), (250, 680), (300, 700),
     ]},
    {"id": "firewall", "name": "FIREWALL", "half_width": 40,           # hard: narrowest, chicanes everywhere
     "points": [
         (380, 712), (640, 714), (900, 708),
         (1060, 696), (1160, 640), (1190, 560),
         (1150, 498), (1060, 480), (985, 425), (1010, 340), (1100, 310), (1170, 250),
         (1150, 175), (1060, 140), (950, 150), (870, 210), (790, 250), (700, 220),
         (620, 160), (530, 150), (450, 200), (420, 290),
         (480, 370), (510, 450), (450, 520), (350, 520), (260, 470), (180, 520),
         (150, 610), (190, 690), (280, 715),
     ]},
]

TRACKS = [Track(lv["points"], half_width=lv["half_width"], track_id=lv["id"], name=lv["name"])
          for lv in LEVELS]

# The first level is also the default track (car.py and older code use TRACK).
TRACK = TRACKS[0]

HUD_AREA = (0, 0, 330, 215)   # top-left corner the HUD covers -- best kept clear of road


def check_track(t):
    """Check a track is fair and drivable. Raises AssertionError saying what's wrong.

    Run for every level by `python3 track.py`."""
    label = f"[{t.name}]"

    # 1) The circuit must not overlap itself and must fit on a 1280x800 screen.
    gap = _self_check(t)
    assert gap > 2 * t.half_width + 12, f"{label} track sections overlap -- move some control points"
    # Where two sections run side by side there must be room for both grass
    # verges and a visible wall between them.
    assert gap >= 2 * t.wall_dist + WALL_THICKNESS, f"{label} sections too close for grass + wall between them"
    # ...with room for the grass verge and the wall on screen too
    room = t.wall_dist + WALL_THICKNESS + 2
    for (x, y) in t.samples:
        assert room < x < SCREEN_W - room, f"{label} too close to the screen edge x={x:.0f}"
        assert room < y < SCREEN_H - room, f"{label} too close to the screen edge y={y:.0f}"

    radius = min_corner_radius(t)
    assert radius >= t.half_width + 6, f"{label} a corner is too tight -- the inside edge would pinch shut"

    # 2) The start/finish line needs a straight run-up (the grid is 14 samples behind it).
    gx, gy, gh, gi = t.start_pose()
    turn = abs(math.atan2(*t.tangents[0][::-1]) - gh)
    assert min(turn, 2 * math.pi - turn) < 0.35, f"{label} start line isn't on a straight"

    # 3) Walls: everywhere round the circuit, the car is stopped at the outer edge
    #    of the grass -- never on the road, never beyond the grass.
    limit = t.wall_dist - CAR_RADIUS
    for idx in range(0, t.n, 5):
        cx, cy = t.samples[idx]
        for side in (+1, -1):
            nx, ny = t.normals[idx]
            nx, ny = nx * side, ny * side
            # a car well inside the grass verge doesn't touch the wall
            gx, gy = cx + nx * (t.half_width + 5), cy + ny * (t.half_width + 5)
            *_, hit = t.resolve_wall(gx, gy, idx)
            assert hit is None, f"{label} wall hit on the grass at sample {idx}"
            # a car pushed just past the wall is brought back to it (skip spots
            # where that point is actually on a neighbouring part of the circuit)
            ox, oy = cx + nx * (t.wall_dist + 4), cy + ny * (t.wall_dist + 4)
            if t.nearest(ox, oy)[1] <= limit:
                continue
            px, py, j, hit = t.resolve_wall(ox, oy, idx)
            assert hit is not None, f"{label} no wall at sample {idx}"
            assert t.nearest(px, py)[1] <= limit + 1e-6
            assert t.nearest(px, py)[1] > t.half_width - CAR_RADIUS, f"{label} wall must leave grass by the road"

    # 4) Laps: driving the centreline for 3.5 laps from the grid counts exactly 3,
    #    for a slow driver (step 1) and a fast one (step 7).
    grid = t.start_pose()[3]
    for step in (1, 7):
        lc = LapCounter(t)
        prev = 0
        for i in range(grid, grid + int(3.5 * t.n), step):
            lc.update(i % t.n)
            assert lc.laps - prev in (0, 1)
            prev = lc.laps
        assert lc.laps == 3, f"{label} laps counted wrong"

    # Reversing back and forth over the start line adds nothing.
    lc = LapCounter(t)
    for i in list(range(grid, grid + 60)) + list(range(grid + 60, grid - 5, -1)) * 3:
        lc.update(i % t.n)
    assert lc.laps == 0, f"{label} reversing over the line counted a lap"

    # Cutting across the infield (skipping gates) gives no lap.
    lc = LapCounter(t)
    for i in list(range(grid, grid + 60)) + [t.n // 2 + k for k in range(40)] + list(range(t.n - 40, t.n + 40)):
        lc.update(i % t.n)
    assert lc.laps == 0, f"{label} skipping checkpoints must not count"

    hud = [p for p in t.samples if HUD_AREA[0] <= p[0] < HUD_AREA[2] and HUD_AREA[1] <= p[1] < HUD_AREA[3]]
    return {"length": t.n * t.spacing, "gap": gap, "corner": radius, "under_hud": len(hud)}


if __name__ == "__main__":
    for i, t in enumerate(TRACKS, 1):
        info = check_track(t)
        warn = f"  (note: {info['under_hud']} samples run under the HUD)" if info["under_hud"] else ""
        print(f"Level {i} {t.name:13s} {info['length']:5.0f}px long, road {2 * t.half_width}px wide, "
              f"tightest corner {info['corner']:.0f}px, closest sections {info['gap']:.0f}px{warn}")
    ids = [t.track_id for t in TRACKS]
    assert len(set(ids)) == len(ids), "every level needs its own id"
    print(f"OK: all {len(TRACKS)} levels fit, don't overlap, have walls all round, and count laps correctly.")
