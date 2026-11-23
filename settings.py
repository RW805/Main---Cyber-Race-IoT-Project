"""
Accessibility settings: colour mode, text size, and reduced flashing/effects.

Saved to settings.json next to the game, so whoever sets up the machine (or a
player who needs them) only has to choose once -- they stick between games and
after a reboot. Nothing personal is stored here.

Run `python3 settings.py` to check loading/saving works.
"""
import json
import os

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

# (id, name shown in the menu, one-line description)
COLOUR_MODES = [
    ("standard", "Standard", "The full neon look."),
    ("red_green", "Red-green friendly", "For red-green colour blindness (protanopia, deuteranopia)."),
    ("blue_yellow", "Blue-yellow friendly", "For blue-yellow colour blindness (tritanopia)."),
    ("high_contrast", "High contrast", "Brightest colours on plain black. Easiest to see."),
]

# (id, name shown in the menu, how much bigger than normal)
TEXT_SIZES = [
    ("normal", "Normal", 1.0),
    ("large", "Large", 1.2),
    ("extra_large", "Extra large", 1.4),
]

DEFAULTS = {
    "colour_mode": "standard",
    "text_size": "normal",
    "reduce_effects": False,   # no blinking, no screen flashes, no scanlines or glow
}


def _valid(key, value):
    if key == "colour_mode":
        return value in [m[0] for m in COLOUR_MODES]
    if key == "text_size":
        return value in [t[0] for t in TEXT_SIZES]
    if key == "reduce_effects":
        return isinstance(value, bool)
    return False


def load(path=SETTINGS_PATH):
    """Saved settings, falling back to the defaults for anything missing or broken."""
    settings = dict(DEFAULTS)
    try:
        with open(path) as f:
            saved = json.load(f)
        for key, value in saved.items():
            if key in DEFAULTS and _valid(key, value):
                settings[key] = value
    except (OSError, ValueError, AttributeError):
        pass   # no file yet, or it's corrupt: just use the defaults
    return settings


def save(settings, path=SETTINGS_PATH):
    try:
        with open(path, "w") as f:
            json.dump({k: settings[k] for k in DEFAULTS}, f, indent=2)
    except OSError:
        pass   # read-only SD card etc. -- settings still apply for this session


def text_scale(settings):
    return next(scale for sid, _, scale in TEXT_SIZES if sid == settings["text_size"])


def cycle(settings, key, step=1):
    """Move a setting to its next (or previous) value, wrapping round."""
    if key == "reduce_effects":
        settings[key] = not settings[key]
        return
    options = [o[0] for o in (COLOUR_MODES if key == "colour_mode" else TEXT_SIZES)]
    i = options.index(settings[key])
    settings[key] = options[(i + step) % len(options)]


if __name__ == "__main__":
    import tempfile
    tmp = os.path.join(tempfile.mkdtemp(), "settings.json")

    assert load(tmp) == DEFAULTS, "missing file -> defaults"
    s = load(tmp)
    cycle(s, "colour_mode")
    cycle(s, "text_size", -1)
    cycle(s, "reduce_effects")
    save(s, tmp)
    assert load(tmp) == {"colour_mode": "red_green", "text_size": "extra_large", "reduce_effects": True}
    assert text_scale(load(tmp)) == 1.4

    with open(tmp, "w") as f:
        f.write("{ not json")
    assert load(tmp) == DEFAULTS, "corrupt file -> defaults"
    with open(tmp, "w") as f:
        json.dump({"colour_mode": "rainbow", "text_size": "large", "hacker": 1}, f)
    assert load(tmp) == dict(DEFAULTS, text_size="large"), "bad values ignored, good ones kept"
    print("OK: settings load, save, cycle, and survive missing/corrupt/bad files.")
