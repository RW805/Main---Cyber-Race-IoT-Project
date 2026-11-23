"""
Simple top-down arcade car physics. No pygame dependency here, so it can be
unit tested headlessly -- pygame is only used later to draw and read input.

The car asks the Track two things every frame:
  * where am I relative to the road?  (on tarmac, or on slow grass)
  * have I hit a wall?                (round the outside of the grass verge)
It remembers its nearest centreline index (`track_idx`) so the lap counter and
the track lookup don't need to search the whole circuit each frame.
"""
import math
from track import TRACK, CAR_RADIUS

MAX_SPEED = 260.0          # px/s on-track
GRASS_MAX_SPEED = 110.0    # px/s off-track (penalty)
ACCEL = 220.0              # px/s^2
BRAKE = 320.0              # px/s^2
FRICTION = 140.0           # px/s^2, natural deceleration when coasting
TURN_RATE = 3.0            # radians/s at full steering, scales down at low speed
BOOST_MULTIPLIER = 1.35    # top speed during a boost (260 -> ~350 px/s)
BOOST_ACCEL = 1.5          # stronger acceleration during a boost, so it kicks in quickly
BOOST_DURATION = 10.0      # seconds -- earned by a correct answer at the end of a lap
WALL_GRIP = 0.8            # fraction of the along-wall speed kept after a scrape


class Car:
    def __init__(self, x, y, heading=0.0, track_idx=None):
        self.x = x
        self.y = y
        self.heading = heading  # radians, 0 = facing +x
        self.speed = 0.0
        self.boost_timer = 0.0
        self.track_idx = track_idx   # nearest centreline sample (search hint + lap counting)
        self.on_track = True
        self.wall_hit = False        # True for the frame in which the car hit a wall

    def apply_boost(self):
        self.boost_timer = BOOST_DURATION

    def _bounce(self, normal):
        """Remove the part of the velocity pointing into the wall so the car
        slides along it, and scrub off some speed for the scrape."""
        nx, ny = normal
        vx = math.cos(self.heading) * self.speed
        vy = math.sin(self.heading) * self.speed
        into_wall = vx * nx + vy * ny
        if into_wall <= 0:
            return
        vx -= into_wall * nx
        vy -= into_wall * ny
        along = math.hypot(vx, vy)
        if along < 1.0:
            self.speed = 0.0
            return
        forward = self.speed >= 0
        self.heading = math.atan2(vy, vx) if forward else math.atan2(-vy, -vx)
        self.speed = along * WALL_GRIP * (1 if forward else -1)

    def update(self, dt, throttle, steer, track=TRACK):
        """
        throttle: -1.0 (full brake/reverse) .. 1.0 (full accelerate)
        steer:    -1.0 (full left) .. 1.0 (full right)
        dt:       seconds since last update
        Returns True if the car ends the frame on the road.
        """
        throttle = max(-1.0, min(1.0, throttle))
        steer = max(-1.0, min(1.0, steer))

        top_speed = MAX_SPEED if self.on_track else GRASS_MAX_SPEED
        accel = ACCEL
        if self.boost_timer > 0:
            top_speed *= BOOST_MULTIPLIER
            accel *= BOOST_ACCEL
            self.boost_timer = max(0.0, self.boost_timer - dt)

        if throttle > 0:
            self.speed += accel * throttle * dt
        elif throttle < 0:
            self.speed += BRAKE * throttle * dt
        else:
            # coast to a stop
            if self.speed > 0:
                self.speed = max(0.0, self.speed - FRICTION * dt)
            elif self.speed < 0:
                self.speed = min(0.0, self.speed + FRICTION * dt)

        if self.speed > top_speed:
            # Over the limit (boost just ended, or ran onto the grass): ease back
            # down to it rather than snapping, as if braking hard.
            self.speed = max(top_speed, self.speed - BRAKE * dt)
        self.speed = max(-top_speed * 0.5, self.speed)

        # Steering scales with speed so the car can't spin in place at a standstill.
        # Above normal top speed (i.e. boosting) it scales up too, so the turning
        # circle stays the same as at normal top speed and the car stays controllable.
        speed_factor = min(1.0, abs(self.speed) / (MAX_SPEED * 0.3))
        speed_factor *= max(1.0, abs(self.speed) / MAX_SPEED)
        self.heading += steer * TURN_RATE * speed_factor * dt

        self.x += math.cos(self.heading) * self.speed * dt
        self.y += math.sin(self.heading) * self.speed * dt

        # Where are we now? Handle walls first, then work out road vs grass.
        idx, dist = track.nearest(self.x, self.y, self.track_idx)
        self.wall_hit = False
        x, y, idx, normal = track.resolve_wall(self.x, self.y, idx, CAR_RADIUS)
        if normal is not None:
            self.x, self.y = x, y
            self._bounce(normal)
            self.wall_hit = True
            cx, cy = track.samples[idx]
            dist = math.hypot(self.x - cx, self.y - cy)
        self.track_idx = idx
        self.on_track = dist <= track.half_width
        return self.on_track


if __name__ == "__main__":
    t = TRACK
    sx, sy, sh, sidx = t.start_pose()

    # Full throttle along the straight should approach but not exceed MAX_SPEED.
    car = Car(sx, sy, sh, sidx)
    for _ in range(150):
        car.update(0.01, 1.0, 0.0)
    assert 0 < car.speed <= MAX_SPEED + 1e-6, car.speed
    assert car.on_track

    # Boost lets it exceed the normal top speed (checked over a few short steps
    # so it can't leave the road while we measure).
    boost_car = Car(sx, sy, sh, sidx)
    boost_car.speed = MAX_SPEED
    boost_car.apply_boost()
    for _ in range(5):
        boost_car.update(0.01, 1.0, 0.0)
    assert boost_car.speed > MAX_SPEED, boost_car.speed

    # On the grass verge the car is limited to the slower grass top speed.
    gi = 300
    gx, gy = t.samples[gi]
    gnx, gny = t.normals[gi]
    grass_car = Car(gx + gnx * (t.half_width + 6), gy + gny * (t.half_width + 6), math.atan2(gny, gnx), gi)
    for _ in range(150):
        grass_car.update(0.01, 1.0, 0.0)
    assert not grass_car.on_track
    assert grass_car.speed <= GRASS_MAX_SPEED + 1e-6, grass_car.speed

    # Coasting with no throttle decelerates to a stop.
    coast_car = Car(sx, sy, sh, sidx)
    coast_car.speed = 100.0
    for _ in range(500):
        coast_car.update(0.01, 0.0, 0.0)
    assert coast_car.speed == 0.0, coast_car.speed

    # Driving straight off the road at several points round the lap: the car
    # crosses the grass, hits the wall, and never gets beyond it.
    limit = t.wall_dist - 10
    for wall_idx in range(0, t.n, t.n // 12):
        for side in (+1, -1):
            wx, wy = t.samples[wall_idx]
            nx, ny = t.normals[wall_idx]
            crash = Car(wx, wy, math.atan2(ny * side, nx * side), wall_idx)
            crash.speed = 200.0
            hit = went_on_grass = False
            for _ in range(200):
                crash.update(0.01, 1.0, 0.0)
                hit = hit or crash.wall_hit
                went_on_grass = went_on_grass or not crash.on_track
                _, d = t.nearest(crash.x, crash.y)
                assert d <= limit + 1e-6, f"car got through the wall (distance {d:.1f})"
            assert went_on_grass, "car should cross the grass before reaching the wall"
            assert hit, f"car never hit a wall at sample {wall_idx}"

    print("OK: car accelerates, boosts, slows on grass, coasts, and is stopped by walls behind the grass all round.")
