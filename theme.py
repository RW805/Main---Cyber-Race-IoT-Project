"""
The neon "cyber" look: colours, fonts and the glow / panel / scanline effects.

Everything expensive (blurred glows, scanlines, the background grid) is drawn once
and cached, so each frame is mostly plain blits -- that keeps it smooth on a
Raspberry Pi.

Fonts are bundled in fonts/ (both SIL Open Font License, see the OFL files there):
  * Orbitron        -- titles and labels
  * Share Tech Mono -- questions, HUD values, everything you read
If a font file is missing, a system monospace font is used instead.
"""
import os
import random

import pygame

WIDTH, HEIGHT = 1280, 800
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

# --- Palette -----------------------------------------------------------------
# Every colour the game draws comes from P, so switching colour mode (see
# settings.py) just swaps P's values. Always read colours as P.NAME at draw time.
PALETTES = {
    "standard": dict(
        BG=(5, 6, 18), GRID=(14, 22, 48), GRID_BRIGHT=(24, 38, 80), TRACE=(20, 44, 78),
        ROAD=(16, 18, 36), ROAD_LINE=(0, 105, 140),
        VERGE=(6, 62, 38), VERGE_GRID=(40, 200, 110),      # the "grass": a green data field
        CYAN=(0, 235, 255),        # road edges, main accent
        MAGENTA=(255, 40, 190),    # walls, second accent
        GREEN=(60, 255, 150),      # right answer
        RED=(255, 60, 95),         # wrong answer, penalties
        YELLOW=(255, 220, 60),     # boost, "clock paused"
        WHITE=(230, 245, 255), DIM=(110, 130, 175), PANEL=(7, 11, 28),
        CAR=(0, 235, 255), CAR_BOOST=(255, 220, 60),
    ),
    # Red-green colour blindness: right/wrong become blue/orange, walls amber.
    "red_green": dict(
        BG=(5, 6, 18), GRID=(14, 22, 48), GRID_BRIGHT=(24, 38, 80), TRACE=(20, 44, 78),
        ROAD=(16, 18, 36), ROAD_LINE=(70, 120, 170),
        VERGE=(60, 70, 20), VERGE_GRID=(170, 190, 60),
        CYAN=(110, 220, 255), MAGENTA=(255, 190, 0),
        GREEN=(40, 150, 255), RED=(255, 150, 0), YELLOW=(255, 230, 90),
        WHITE=(235, 240, 255), DIM=(140, 150, 180), PANEL=(7, 11, 28),
        CAR=(30, 140, 255), CAR_BOOST=(255, 230, 90),
    ),
    # Blue-yellow colour blindness: right/wrong become cyan/red, walls pink-red,
    # boosted car white instead of yellow.
    "blue_yellow": dict(
        BG=(5, 6, 18), GRID=(14, 22, 48), GRID_BRIGHT=(24, 38, 80), TRACE=(20, 44, 78),
        ROAD=(16, 18, 36), ROAD_LINE=(0, 105, 140),
        VERGE=(6, 62, 38), VERGE_GRID=(40, 200, 110),
        CYAN=(0, 235, 255), MAGENTA=(255, 40, 120),
        GREEN=(0, 215, 255), RED=(255, 50, 60), YELLOW=(255, 220, 60),
        WHITE=(235, 245, 255), DIM=(130, 145, 180), PANEL=(7, 11, 28),
        CAR=(0, 235, 255), CAR_BOOST=(255, 255, 255),
    ),
    # High contrast: plain black, white road edges, bright orange walls, and
    # blue/orange for right/wrong so it works for colour-blind players too.
    "high_contrast": dict(
        BG=(0, 0, 0), GRID=(0, 0, 0), GRID_BRIGHT=(0, 0, 0), TRACE=(0, 0, 0),
        ROAD=(30, 30, 30), ROAD_LINE=(200, 200, 200),
        VERGE=(0, 85, 0), VERGE_GRID=(0, 85, 0),
        CYAN=(255, 255, 255), MAGENTA=(255, 140, 0),
        GREEN=(60, 170, 255), RED=(255, 140, 0), YELLOW=(255, 230, 0),
        WHITE=(255, 255, 255), DIM=(215, 215, 215), PANEL=(0, 0, 0),
        CAR=(0, 255, 255), CAR_BOOST=(255, 230, 0),
    ),
}


class _Palette:
    pass


P = _Palette()
P.__dict__.update(PALETTES["standard"])


class _Options:
    mode = "standard"
    text_scale = 1.0          # 1.0 normal, 1.2 large, 1.4 extra large
    reduce_effects = False    # no blinking, flashes, scanlines or glow


S = _Options()


def apply_settings(settings):
    """Switch colour mode / text size / effects. Clears every cached drawing so
    the next frame is redrawn in the new style."""
    from settings import text_scale
    S.mode = settings["colour_mode"]
    S.text_scale = text_scale(settings)
    S.reduce_effects = settings["reduce_effects"]
    P.__dict__.update(PALETTES[S.mode])
    _cache.clear()


# --- Fonts -------------------------------------------------------------------
def _font(file, size):
    try:
        return pygame.font.Font(os.path.join(FONT_DIR, file), size)
    except Exception:
        return pygame.font.SysFont("dejavusansmono,consolas,couriernew,monospace", size)


def load_fonts():
    """Titles stay the same size; everything you read scales with the text size setting."""
    k = S.text_scale
    return {
        "title": _font("Orbitron-Black.ttf", 88),
        "huge": _font("Orbitron-Black.ttf", 56),
        "head": _font("Orbitron-Bold.ttf", round(30 * k)),
        "label": _font("Orbitron-Bold.ttf", round(15 * k)),
        "button": _font("Orbitron-Bold.ttf", round(19 * k)),
        "big": _font("ShareTechMono-Regular.ttf", round(36 * k)),
        "mid": _font("ShareTechMono-Regular.ttf", round(27 * k)),
        "small": _font("ShareTechMono-Regular.ttf", round(21 * k)),
    }


# --- Effects -----------------------------------------------------------------
def blur(surf, size, factor=4, passes=2):
    """Cheap blur: shrink and grow back up with smoothscale."""
    w, h = size
    small = (max(1, w // factor), max(1, h // factor))
    for _ in range(passes):
        surf = pygame.transform.smoothscale(pygame.transform.smoothscale(surf, small), (w, h))
    return surf


def scale(colour, k):
    return tuple(max(0, min(255, int(c * k))) for c in colour)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


_cache = {}


def glow_sprite(colour, radius=36):
    """Soft round glow, for blitting with BLEND_ADD under the car."""
    key = ("glow", colour, radius)
    if key not in _cache:
        s = pygame.Surface((radius * 2, radius * 2))
        s.fill((0, 0, 0))
        for r in range(radius, 0, -2):
            k = (1 - r / radius) ** 2 * 0.5
            pygame.draw.circle(s, scale(colour, k), (radius, radius), r)
        _cache[key] = s
    return _cache[key]


def glow_text(font, s, colour, pad=26):
    """(glow surface, crisp text surface, pad) -- blit glow with BLEND_ADD at -pad."""
    key = ("gtext", id(font), s, colour)
    if key not in _cache:
        txt = font.render(s, True, colour)
        w, h = txt.get_size()
        size = (w + 2 * pad, h + 2 * pad)
        base = pygame.Surface(size)
        base.fill((0, 0, 0))
        base.blit(font.render(s, True, colour, (0, 0, 0)), (pad, pad))
        _cache[key] = (blur(base, size, 4, 3), txt, pad)
    return _cache[key]


def draw_glow_title(surface, font, s, colour, center):
    if S.reduce_effects:
        txt = font.render(s, True, colour)
        rect = txt.get_rect(center=center)
        surface.blit(txt, rect)
        return rect
    glow, txt, pad = glow_text(font, s, colour)
    rect = txt.get_rect(center=center)
    for _ in range(2):
        surface.blit(glow, (rect.x - pad, rect.y - pad), special_flags=pygame.BLEND_ADD)
    # chromatic split: faint magenta / cyan ghosts either side
    # (rendered on black so BLEND_ADD only adds the letters, not a box)
    surface.blit(font.render(s, True, scale(P.MAGENTA, 0.8), (0, 0, 0)), (rect.x - 3, rect.y),
                 special_flags=pygame.BLEND_ADD)
    surface.blit(font.render(s, True, scale(P.CYAN, 0.6), (0, 0, 0)), (rect.x + 3, rect.y),
                 special_flags=pygame.BLEND_ADD)
    surface.blit(txt, rect)
    return rect


def chamfer_points(x, y, w, h, c=14):
    return [(x + c, y), (x + w, y), (x + w, y + h - c), (x + w - c, y + h), (x, y + h), (x, y + c)]


def panel(surface, rect, border=None, alpha=215, cut=14):
    """Translucent dark panel with cut corners and a neon edge."""
    x, y, w, h = (int(v) for v in rect)
    border = border or P.CYAN
    if S.mode == "high_contrast":
        alpha = 255          # solid panels: nothing showing through behind the text
    key = ("panel", w, h, border, alpha, cut)
    if key not in _cache:
        s = pygame.Surface((w + 1, h + 1), pygame.SRCALPHA)
        pts = chamfer_points(0, 0, w, h, cut)
        pygame.draw.polygon(s, P.PANEL + (alpha,), pts)
        edge = border if S.mode == "high_contrast" else scale(border, 0.55)
        pygame.draw.polygon(s, edge + (255,), pts, 2)
        # bright accents on the two cut corners
        pygame.draw.line(s, border, (0, cut + 18), (0, cut), 3)
        pygame.draw.line(s, border, (0, cut), (cut, 0), 3)
        pygame.draw.line(s, border, (cut, 0), (cut + 40, 0), 3)
        pygame.draw.line(s, border, (w, h - cut - 18), (w, h - cut), 3)
        pygame.draw.line(s, border, (w, h - cut), (w - cut, h), 3)
        pygame.draw.line(s, border, (w - cut, h), (w - cut - 40, h), 3)
        _cache[key] = s
    surface.blit(_cache[key], (x, y))


def scanlines():
    if "scan" not in _cache:
        s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        if S.reduce_effects or S.mode == "high_contrast":
            _cache["scan"] = s      # left blank: no scanlines
            return s
        for y in range(0, HEIGHT, 3):
            pygame.draw.line(s, (0, 0, 0, 55), (0, y), (WIDTH, y))
        _cache["scan"] = s
    return _cache["scan"]


def dim_overlay(alpha=200):
    key = ("dim", alpha)
    if key not in _cache:
        s = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        s.fill(P.BG + (alpha,))
        s.blit(scanlines(), (0, 0))
        _cache[key] = s
    return _cache[key]


def draw_background(surf, seed=7):
    """Dark grid with faint circuit-board traces (plain black in high contrast)."""
    surf.fill(P.BG)
    if S.mode == "high_contrast":
        return
    for x in range(0, WIDTH + 1, 32):
        pygame.draw.line(surf, P.GRID_BRIGHT if x % 128 == 0 else P.GRID, (x, 0), (x, HEIGHT))
    for y in range(0, HEIGHT + 1, 32):
        pygame.draw.line(surf, P.GRID_BRIGHT if y % 128 == 0 else P.GRID, (0, y), (WIDTH, y))
    rng = random.Random(seed)
    for _ in range(70):
        x, y = rng.randrange(0, WIDTH, 16), rng.randrange(0, HEIGHT, 16)
        pts = [(x, y)]
        for _ in range(rng.randint(2, 4)):
            d = rng.choice([(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)])
            n = rng.randint(2, 6) * 16
            x, y = x + d[0] * n, y + d[1] * n
            pts.append((x, y))
        pygame.draw.lines(surf, P.TRACE, False, pts, 2)
        pygame.draw.circle(surf, P.TRACE, pts[0], 4, 2)
        pygame.draw.circle(surf, P.TRACE, pts[-1], 3)


def menu_background():
    if "menu_bg" not in _cache:
        s = pygame.Surface((WIDTH, HEIGHT))
        draw_background(s, seed=11)
        s.blit(scanlines(), (0, 0))
        _cache["menu_bg"] = s
    return _cache["menu_bg"]


def draw_menu_background(surface, now):
    surface.blit(menu_background(), (0, 0))
    if S.reduce_effects or S.mode == "high_contrast":
        return
    # a slow scan bar sweeping down the screen
    if "scanbar" not in _cache:
        bar = pygame.Surface((WIDTH, 40))
        bar.fill((0, 0, 0))
        for k in range(40):
            pygame.draw.line(bar, scale(P.CYAN, 0.10 * (k / 40) ** 2), (0, k), (WIDTH, k))
        _cache["scanbar"] = bar
    y = int((now * 140) % (HEIGHT + 200)) - 100
    surface.blit(_cache["scanbar"], (0, y), special_flags=pygame.BLEND_ADD)


def draw_tick(surface, center, size, colour, width=4):
    """A tick mark -- so 'right' never relies on colour alone."""
    x, y = center
    pygame.draw.lines(surface, colour, False,
                      [(x - size * 0.5, y), (x - size * 0.15, y + size * 0.4), (x + size * 0.5, y - size * 0.45)], width)


def draw_cross(surface, center, size, colour, width=4):
    """A cross -- so 'wrong' never relies on colour alone."""
    x, y = center
    d = size * 0.42
    pygame.draw.line(surface, colour, (x - d, y - d), (x + d, y + d), width)
    pygame.draw.line(surface, colour, (x - d, y + d), (x + d, y - d), width)
