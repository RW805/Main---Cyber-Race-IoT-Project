"""
End-to-end headless tests (no pygame needed): a simple AI driver steers the
real Car through the real Track while the real LapCounter watches.

Run:  python3 test_game_logic.py
"""
import math

from car import Car, MAX_SPEED, BOOST_MULTIPLIER
from track import TRACK, TRACKS, LapCounter

DT = 1 / 60


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def drive(track, target_speed=130.0, lookahead=12, max_seconds=400, reverse=False,
          laps_wanted=3, crash_window=None, always_boost=False):
    """Follow the centreline. Returns (laps, seconds, wall_hits, frames_off_road).

    crash_window=(t0, t1) makes the driver steer hard into the nearest wall
    between those times (only bites where walls exist), then carry on racing.
    """
    x, y, heading, idx = track.start_pose()
    if reverse:
        heading += math.pi
    car = Car(x, y, heading, idx)
    counter = LapCounter(track)
    counter.update(car.track_idx)
    step = -lookahead if reverse else lookahead

    t, wall_hits, off_frames = 0.0, 0, 0
    while t < max_seconds and counter.laps < laps_wanted:
        if always_boost:
            car.apply_boost()
        tx, ty = track.samples[(car.track_idx + step) % track.n]
        desired = math.atan2(ty - car.y, tx - car.x)
        if crash_window and crash_window[0] <= t < crash_window[1]:
            nx, ny = track.normals[car.track_idx]
            desired = math.atan2(ny, nx)                  # aim at the wall
        steer = max(-1.0, min(1.0, wrap(desired - car.heading) * 3.0))
        throttle = 1.0 if car.speed < target_speed else -0.2
        car.update(DT, throttle, steer, track)
        counter.update(car.track_idx)
        wall_hits += car.wall_hit
        off_frames += (not car.on_track)
        t += DT
    return counter.laps, t, wall_hits, off_frames


def test_three_laps_with_real_physics():
    laps, secs, hits, off = drive(TRACK)
    assert laps == 3, f"AI driver should finish 3 laps, got {laps} after {secs:.0f}s"
    print(f"  3 laps in {secs:.1f}s ({secs / 3:.1f}s/lap), wall hits={hits}, frames off-road={off}")


def test_laps_increment_one_at_a_time():
    x, y, h, idx = TRACK.start_pose()
    car, counter = Car(x, y, h, idx), LapCounter(TRACK)
    counter.update(car.track_idx)
    seen, t = [], 0.0
    while t < 200 and counter.laps < 2:
        tx, ty = TRACK.samples[(car.track_idx + 12) % TRACK.n]
        steer = max(-1, min(1, wrap(math.atan2(ty - car.y, tx - car.x) - car.heading) * 3))
        car.update(DT, 1.0 if car.speed < 130 else -0.2, steer, TRACK)
        before = counter.laps
        counter.update(car.track_idx)
        if counter.laps != before:
            seen.append((counter.laps, round(t, 1)))
        t += DT
    assert [s[0] for s in seen] == [1, 2], seen
    print(f"  lap 1 at {seen[0][1]}s, lap 2 at {seen[1][1]}s")


def test_hitting_the_wall_does_not_break_lap_counting():
    # Drive into the barrier on the first straight (t=2s..4s), recover, keep racing.
    clean = drive(TRACK)[1]
    laps, secs, hits, off = drive(TRACK, crash_window=(2.0, 4.0))
    assert hits > 0, "the test driver never actually hit a wall"
    assert laps == 3, f"after a wall crash the driver should still finish 3 laps, got {laps}"
    assert secs > clean, "a wall crash should cost time"
    print(f"  wall crash: {hits} hit-frames, still 3 laps, {secs - clean:.1f}s slower than a clean run")


def test_boosted_car_is_faster_but_still_controllable():
    # Flat out at normal top speed vs flat out with the boost on the whole time.
    _, normal, n_hits, n_off = drive(TRACK, target_speed=MAX_SPEED, laps_wanted=1)
    laps, boosted, b_hits, b_off = drive(TRACK, target_speed=MAX_SPEED * BOOST_MULTIPLIER,
                                         laps_wanted=1, always_boost=True)
    assert laps == 1
    assert boosted < normal * 0.85, f"boost should be clearly faster ({boosted:.1f}s vs {normal:.1f}s)"
    assert b_hits == 0 and b_off == 0, f"boosted car should still hold the road (walls={b_hits}, off={b_off})"
    print(f"  flat-out lap: {normal:.1f}s normal, {boosted:.1f}s boosted, boosted car stayed on the road")


def test_every_level_can_be_finished():
    # Every level: 3 clean laps at a normal pace, and a flat-out boosted lap that
    # still stays on the road. Catches a new track that's impossible to drive.
    for t in TRACKS:
        laps, secs, hits, off = drive(t)
        assert laps == 3, f"{t.name}: AI driver should finish 3 laps, got {laps}"
        _, boosted, b_hits, b_off = drive(t, target_speed=MAX_SPEED * BOOST_MULTIPLIER,
                                          laps_wanted=1, always_boost=True)
        assert b_hits == 0 and b_off == 0, f"{t.name}: boosted car left the road (walls={b_hits}, off={b_off})"
        laps, *_ = drive(t, reverse=True, max_seconds=40)
        assert laps == 0, f"{t.name}: driving backwards must not count laps"
        print(f"  {t.name:13s} 3 laps in {secs:5.1f}s, boosted lap {boosted:4.1f}s on the road, reverse = 0 laps")


def test_wrong_way_gives_no_laps():
    laps, secs, hits, off = drive(TRACK, reverse=True, max_seconds=60)
    assert laps == 0, f"driving backwards must not count laps (got {laps})"
    print("  driving the wrong way for 60s: 0 laps (correct)")


def test_sitting_on_the_line_gives_no_laps():
    x, y, h, idx = TRACK.start_pose()
    car, counter = Car(x, y, h, idx), LapCounter(TRACK)
    for i in range(600):
        car.update(DT, 1.0 if i % 120 < 60 else -1.0, 0.0, TRACK)   # shunt back and forth
        counter.update(car.track_idx)
    assert counter.laps == 0
    print("  shunting back and forth over the line: 0 laps (correct)")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        print(fn.__name__)
        fn()
    print(f"\nOK: {len(tests)} end-to-end tests passed.")
