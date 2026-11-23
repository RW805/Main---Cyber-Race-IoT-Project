"""
Tests for the accessibility settings. Runs headless (no window needed).

  1. Colour modes really work for colour-blind players: key colour pairs are
     checked with a colour-blindness simulation (cvd.py) and must stay clearly
     different for the people each mode is for.
  2. Every combination of settings (4 colour modes x 3 text sizes x effects
     on/off) draws every screen without crashing, and the in-race boxes fit on
     screen.
  3. The menu works like a player would use it: TAB / the button opens it,
     arrow keys and mouse clicks change settings, ESC goes back, and the
     choices are saved and loaded again next time.

Run:  python3 test_accessibility.py
"""
import os
import sys
import tempfile
import types

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame  # noqa: E402

pygame.init()
SCREEN = pygame.display.set_mode((1280, 800))

import main  # noqa: E402
import settings as settings_mod  # noqa: E402
import theme  # noqa: E402
from car import Car  # noqa: E402
from cvd import seen_difference  # noqa: E402

CLEARLY_DIFFERENT = 20   # delta-E: 20+ is an obvious difference at a glance

PAIRS = [("GREEN", "RED", "right vs wrong"),
         ("CYAN", "MAGENTA", "road edge vs wall"),
         ("CAR", "CAR_BOOST", "car vs boosted car"),
         ("VERGE", "ROAD", "grass vs road")]

# who each colour mode is for
MODE_USERS = {
    "red_green": ["normal", "protan", "deutan"],
    "blue_yellow": ["normal", "tritan"],
    "high_contrast": ["normal", "protan", "deutan", "tritan"],
}


def test_colour_modes_work_for_colour_blind_players():
    for mode, kinds in MODE_USERS.items():
        pal = theme.PALETTES[mode]
        worst = min((seen_difference(pal[a], pal[b], k), name, k) for a, b, name in PAIRS for k in kinds)
        assert worst[0] >= CLEARLY_DIFFERENT, f"{mode}: {worst[1]} too similar for {worst[2]} ({worst[0]:.0f})"
        print(f"  {mode:14s} smallest difference {worst[0]:5.1f} ({worst[1]}, {worst[2]} vision)")
    # and show why the modes are needed: standard is weakest for red-green colour blindness
    std = theme.PALETTES["standard"]
    d = seen_difference(std["CYAN"], std["MAGENTA"], "deutan")
    print(f"  (standard mode: road edge vs wall for deuteranopia is only {d:.0f})")


def _settings(mode="standard", size="normal", reduce=False):
    return {"colour_mode": mode, "text_size": size, "reduce_effects": reduce}


def _draw_all_race_screens():
    f = main.fonts()
    car = Car(800, 700, 0.0, 120)
    car.speed, car.boost_timer = 330, 7.3
    main.draw_track(SCREEN)
    main.draw_car(SCREEN, car, theme.P.CAR_BOOST, [(800 - k * 9, 700) for k in range(22)])
    main.draw_hud(SCREEN, f["small"], "Sixteen_chars_ab", 2, 18.4, 10, car)
    fb = ("ACCESS GRANTED", theme.P.GREEN, [("Correct -- 10s speed boost!", theme.P.GREEN),
                                            ("Even if someone guesses your password, they still need the code.",
                                             theme.P.WHITE)], 99, True)
    main.draw_feedback_banner(SCREEN, fb, f["small"])
    q = {"text": "A message saying 'You've won a prize! Click here!' could be a scam.", "answer": True}
    main.question_overlay(SCREEN, f["big"], f["small"], q, 1, 0.0)
    main.draw_finish(SCREEN, f["big"], f["small"], f["huge"], "Sixteen_chars_ab", 67.68, 47.68, 20, 1, 3, fb, 0.0)


def test_every_combination_draws():
    combos = 0
    for mode, _, _ in settings_mod.COLOUR_MODES:
        for size, _, scale in settings_mod.TEXT_SIZES:
            for reduce in (False, True):
                main.apply_settings(_settings(mode, size, reduce))
                _draw_all_race_screens()
                w, h, _ = main.hud_size()
                assert 14 + w < 1280 // 2 and 14 + h < 800 // 2, f"HUD too big at {size}"
                combos += 1
    # text really gets bigger
    main.apply_settings(_settings(size="normal"))
    normal = main.fonts()["big"].get_height()
    main.apply_settings(_settings(size="extra_large"))
    big = main.fonts()["big"].get_height()
    assert big >= normal * 1.3, (normal, big)
    main.apply_settings(_settings())
    print(f"  {combos} combinations drawn; question text {normal}px -> {big}px at extra large")


class Stop(Exception):
    pass


def _key(key, uni=""):
    return types.SimpleNamespace(type=pygame.KEYDOWN, key=key, unicode=uni)


def _click(pos):
    return types.SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=pos)


def _run_events(batches, fn):
    """Feed batches of events to a screen loop, one batch per frame."""
    batches = list(batches)
    real_get, real_flip = pygame.event.get, pygame.display.flip
    pygame.event.get = lambda: batches.pop(0) if batches else (_ for _ in ()).throw(Stop())
    pygame.display.flip = lambda: None
    try:
        return fn()
    except Stop:
        return None
    finally:
        pygame.event.get, pygame.display.flip = real_get, real_flip


class Clock:
    def tick(self, fps):
        return 16


def test_menu_with_keyboard_and_saving():
    tmp = os.path.join(tempfile.mkdtemp(), "settings.json")
    real_save = settings_mod.save
    settings_mod.save = lambda s, path=tmp: real_save(s, tmp)
    try:
        s = settings_mod.load(tmp)
        main.apply_settings(s)
        name = _run_events([
            [_key(pygame.K_TAB)],                       # open the menu from the start screen
            [_key(pygame.K_RIGHT)],                     # colour mode -> red-green
            [_key(pygame.K_RIGHT)],                     # -> blue-yellow
            [_key(pygame.K_DOWN)], [_key(pygame.K_RIGHT)],   # text size -> large
            [_key(pygame.K_DOWN)], [_key(pygame.K_RETURN)],  # reduce effects -> on
            [_key(pygame.K_ESCAPE)],                    # back to start screen
            [_key(0, c) for c in "Ava"], [_key(pygame.K_RETURN)],
        ], lambda: main.get_player_name(SCREEN, Clock(), settings=s))
        assert name == "Ava", name
        assert s == _settings("blue_yellow", "large", True), s
        assert settings_mod.load(tmp) == s, "settings should be saved"
        assert theme.S.mode == "blue_yellow" and theme.S.text_scale == 1.2 and theme.S.reduce_effects
        assert main.blink(0.6) is True, "nothing blinks when effects are reduced"

        # reset to defaults from the menu
        _run_events([[_key(pygame.K_UP)], [_key(pygame.K_UP)], [_key(pygame.K_RETURN)], [_key(pygame.K_ESCAPE)]],
                    lambda: main.accessibility_menu(SCREEN, Clock(), s))
        assert s == settings_mod.DEFAULTS and settings_mod.load(tmp) == settings_mod.DEFAULTS
        print("  TAB -> change colour / size / effects -> ESC -> race: works, saved, reset works")
    finally:
        settings_mod.save = real_save
        main.apply_settings(settings_mod.DEFAULTS)


def test_menu_with_mouse():
    tmp = os.path.join(tempfile.mkdtemp(), "settings.json")
    real_save = settings_mod.save
    settings_mod.save = lambda s, path=tmp: real_save(s, tmp)
    try:
        s = dict(settings_mod.DEFAULTS)
        main.apply_settings(s)
        button = main.access_button_rect()
        # rows start at y=130+20 in the menu; click the middle of the first row (colour mode)
        f = main.fonts()
        row_h = max(main.lh(f["mid"]), main.lh(f["label"])) + main.sz(18)
        row0 = (640, 150 + row_h // 2)
        _run_events([[_click(button.center)], [_click(row0)], [_click(row0)], [_key(pygame.K_ESCAPE)]],
                    lambda: main.get_player_name(SCREEN, Clock(), settings=s))
        assert s["colour_mode"] == "blue_yellow", s
        print("  clicking the start-screen button opens the menu; clicking a setting changes it")
    finally:
        settings_mod.save = real_save
        main.apply_settings(settings_mod.DEFAULTS)


if __name__ == "__main__":
    real_exit = sys.exit
    sys.exit = lambda *a: (_ for _ in ()).throw(Stop())   # ESC on the start screen quits the game
    tests = [test_colour_modes_work_for_colour_blind_players, test_every_combination_draws,
             test_menu_with_keyboard_and_saving, test_menu_with_mouse]
    for fn in tests:
        print(fn.__name__)
        fn()
    sys.exit = real_exit
    print(f"\nOK: {len(tests)} accessibility tests passed.")
