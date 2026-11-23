"""
CyberRace -- a top-down arcade racer with true/false cybersecurity questions.

There are three levels -- NEON CIRCUIT, DATA DRIFT and FIREWALL -- raced in
order; the overall winner has the lowest total time. When a player finishes all
three, their total is sent to the MySQL scoreboard (scoreboard.py) for display
on a big screen; the game itself keeps no database. Every time you cross the
start/finish line a true/false question pops up (the race clock pauses while
it's on screen). Right answer: a 10-second speed boost.
Wrong answer: 10 seconds added to your race time. Fastest total time wins.

Run:  python3 main.py
Controls: joystick if plugged in, otherwise arrow keys / WASD.
T / F to answer questions. ESC to quit at any time.
TAB (or the button on the start screen) opens the accessibility settings.

The look (colours, fonts, glow effects) lives in theme.py; accessibility
settings (colour mode, text size, reduced effects) in settings.py.
"""
import math
import sys
import time
from collections import deque

import pygame

import settings as settings_mod
import theme
from theme import WIDTH, HEIGHT, P
from car import Car, MAX_SPEED, BOOST_DURATION, BOOST_MULTIPLIER
from controls import Controls
from scoreboard import Scoreboard, make_row, sanitise_name
from questions import QuestionDeck
from track import TRACK, TRACKS, LapCounter, WALL_THICKNESS, SCREEN_WALL

FPS = 60
TOTAL_LAPS = 3
WRONG_ANSWER_PENALTY = 10.0  # seconds added to the race time for a wrong answer

_track_surfaces = {}     # track_id -> the circuit drawn once
_fonts = {}


def fonts():
    """All fonts, sized for the current text-size setting. Loaded after pygame.init()."""
    if not _fonts:
        _fonts.update(theme.load_fonts())
    return _fonts


def apply_settings(settings):
    """Switch to new accessibility settings: new palette, fonts and track drawing."""
    theme.apply_settings(settings)
    _fonts.clear()
    _track_surfaces.clear()


# --- Layout helpers ------------------------------------------------------------
def sz(v):
    """Scale a size by the text-size setting, so boxes grow with their text."""
    return int(round(v * theme.S.text_scale))


def lh(font):
    return int(font.get_linesize())


def tw(font, s):
    return int(font.size(s)[0])


def fit(font, s, max_width):
    """Trim `s` with '...' so it fits in max_width."""
    if tw(font, s) <= max_width:
        return s
    while s and tw(font, s + "...") > max_width:
        s = s[:-1]
    return s + "..."


def wrap_lines(font, s, max_width):
    words, lines, line = s.split(), [], ""
    for w in words:
        trial = f"{line} {w}".strip()
        if tw(font, trial) <= max_width or not line:
            line = trial
        else:
            lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def draw_lines(surface, font, lines, center_x, top_y, color, line_gap=4):
    y = top_y
    for ln in lines:
        img = font.render(ln, True, color)
        surface.blit(img, img.get_rect(midtop=(center_x, y)))
        y += lh(font) + line_gap
    return y


def wrapped_text(surface, font, s, center_x, top_y, max_width, color=None, line_gap=4):
    """Draw `s` centred, word-wrapped to `max_width`. Returns the y below the last line."""
    return draw_lines(surface, font, wrap_lines(font, s, max_width), center_x, top_y,
                      color or P.WHITE, line_gap)


def text(surface, font, s, pos, color=None, center=False, right=False):
    img = font.render(s, True, color or P.WHITE)
    rect = img.get_rect()
    if center:
        rect.center = pos
    elif right:
        rect.topright = pos
    else:
        rect.topleft = pos
    surface.blit(img, rect)
    return rect


def neon_text(surface, font, s, pos, color, center=True):
    """Text with a faint magenta/cyan split behind it (plain when effects are reduced)."""
    if not theme.S.reduce_effects and theme.S.mode != "high_contrast":
        text(surface, font, s, (pos[0] - 2, pos[1]), theme.scale(P.MAGENTA, 0.7), center=center)
        text(surface, font, s, (pos[0] + 2, pos[1]), theme.scale(P.CYAN, 0.6), center=center)
    return text(surface, font, s, pos, color, center=center)


def blink(now, rate=2.0):
    """On/off for blinking prompts -- always on when flashing is turned off."""
    return theme.S.reduce_effects or int(now * rate) % 2 == 0


def answer_icon(surface, correct, center, size):
    if correct:
        theme.draw_tick(surface, center, size, P.GREEN, max(3, size // 7))
    else:
        theme.draw_cross(surface, center, size, P.RED, max(3, size // 7))


# --- Track -------------------------------------------------------------------
def build_track_surface(track):
    """Draw the whole circuit once so each frame is a single blit.

    Layered circles give the outline of the walls and road edges for free: a
    wall-coloured band at wall_dist..wall_dist+thickness, covered by the green
    verge within wall_dist of any part of the circuit, then the road edge and the
    road. Where two sections run close, their verges merge and one wall is left
    between them -- exactly where the collision code puts it. The neon lines are
    then drawn again on a separate layer, blurred, and added on top as a glow
    (skipped in high contrast or with effects reduced)."""
    W, H = WIDTH, HEIGHT
    hw, wd = track.half_width, track.wall_dist
    pts = track.samples[::2]
    plain = theme.S.reduce_effects or theme.S.mode == "high_contrast"

    surf = pygame.Surface((W, H))
    theme.draw_background(surf)

    for x, y in pts:
        pygame.draw.circle(surf, P.MAGENTA, (x, y), wd + WALL_THICKNESS)
    for x, y in pts:
        pygame.draw.circle(surf, P.VERGE, (x, y), wd)

    # data-grid texture on the verge only (masked to the verge shape)
    if P.VERGE_GRID != P.VERGE:
        pattern = pygame.Surface((W, H), pygame.SRCALPHA)
        for gx in range(0, W, 12):
            pygame.draw.line(pattern, P.VERGE_GRID + (255,), (gx, 0), (gx, H))
        for gy in range(0, H, 12):
            pygame.draw.line(pattern, P.VERGE_GRID + (255,), (0, gy), (W, gy))
        mask = pygame.Surface((W, H), pygame.SRCALPHA)
        mask.fill((0, 0, 0, 0))
        for x, y in pts:
            pygame.draw.circle(mask, (255, 255, 255, 70), (x, y), wd - 1)
        pattern.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(pattern, (0, 0))

    for x, y in pts:
        pygame.draw.circle(surf, P.CYAN, (x, y), hw + 3)
    for x, y in pts:
        pygame.draw.circle(surf, P.ROAD, (x, y), hw)

    # centre dashes
    for i in range(0, track.n - 4, 8):
        pygame.draw.line(surf, P.ROAD_LINE, track.samples[i], track.samples[i + 3], 2)

    # start/finish line: checks
    squares = 8
    left, right = track.edge_point(0, +1), track.edge_point(0, -1)
    tx, ty = track.tangents[0]
    for row in (0, 1):
        for k in range(squares):
            f0, f1 = k / squares, (k + 1) / squares
            p0 = (left[0] + (right[0] - left[0]) * f0, left[1] + (right[1] - left[1]) * f0)
            p1 = (left[0] + (right[0] - left[0]) * f1, left[1] + (right[1] - left[1]) * f1)
            ox, oy = tx * 7 * row, ty * 7 * row
            colour = P.WHITE if (k + row) % 2 == 0 else P.BG
            pygame.draw.polygon(surf, colour, [
                (p0[0] + ox, p0[1] + oy), (p1[0] + ox, p1[1] + oy),
                (p1[0] + ox + tx * 7, p1[1] + oy + ty * 7), (p0[0] + ox + tx * 7, p0[1] + oy + ty * 7)])

    # wall round the edge of the screen
    pygame.draw.rect(surf, P.MAGENTA, (0, 0, W, H), SCREEN_WALL)

    if not plain:
        # glow layer: just the neon lines, blurred and added on top
        glow = pygame.Surface((W, H))
        glow.fill((0, 0, 0))
        for x, y in pts:
            pygame.draw.circle(glow, P.MAGENTA, (x, y), wd + WALL_THICKNESS)
        for x, y in pts:
            pygame.draw.circle(glow, (0, 0, 0), (x, y), wd)
        for x, y in pts:
            pygame.draw.circle(glow, theme.scale(P.CYAN, 0.75), (x, y), hw + 3)
        for x, y in pts:
            pygame.draw.circle(glow, (0, 0, 0), (x, y), hw)
        pygame.draw.rect(glow, P.MAGENTA, (0, 0, W, H), SCREEN_WALL)
        pygame.draw.line(glow, P.WHITE, left, right, 6)
        glow = theme.blur(glow, (W, H), factor=3, passes=2)
        surf.blit(glow, (0, 0), special_flags=pygame.BLEND_ADD)
        surf.blit(theme.scanlines(), (0, 0))
    return surf


def draw_track(surface, track=TRACK):
    if track.track_id not in _track_surfaces:
        _track_surfaces[track.track_id] = build_track_surface(track)
    surface.blit(_track_surfaces[track.track_id], (0, 0))


# --- Car ---------------------------------------------------------------------
CAR_SHAPE = [(17, 0), (7, 8), (-12, 9), (-15, 5), (-15, -5), (-12, -9), (7, -8)]
COCKPIT = [(7, 0), (0, 4.5), (-5, 4), (-5, -4), (0, -4.5)]


def _rotate(shape, car):
    c, s = math.cos(car.heading), math.sin(car.heading)
    return [(car.x + dx * c - dy * s, car.y + dx * s + dy * c) for dx, dy in shape]


def draw_trail(surface, trail, colour):
    """Light trail behind the car: fades from the car colour to the road colour."""
    n = len(trail)
    for i in range(1, n):
        t = i / n
        pygame.draw.line(surface, theme.lerp(P.ROAD, colour, t * 0.85), trail[i - 1], trail[i], max(1, int(8 * t)))


def draw_car(surface, car, color=None, trail=None):
    color = color or P.CAR
    if trail:
        draw_trail(surface, trail, color)
    if theme.S.mode != "high_contrast":
        g = theme.glow_sprite(color, 40)
        surface.blit(g, (car.x - 40, car.y - 40), special_flags=pygame.BLEND_ADD)
        surface.blit(g, (car.x - 40, car.y - 40), special_flags=pygame.BLEND_ADD)
    body = _rotate(CAR_SHAPE, car)
    pygame.draw.polygon(surface, P.PANEL, body)
    pygame.draw.polygon(surface, color, body, 2)
    pygame.draw.polygon(surface, theme.scale(color, 0.7), _rotate(COCKPIT, car))
    rear = _rotate([(-15, 5), (-15, -5)], car)
    pygame.draw.line(surface, P.MAGENTA, rear[0], rear[1], 3)


# --- Start screen --------------------------------------------------------------
def access_button_rect():
    f = fonts()
    w = tw(f["button"], "ACCESSIBILITY   [TAB]") + 70
    h = lh(f["button"]) + 30
    return pygame.Rect(WIDTH - 24 - w, 24, w, h)


def draw_access_button(screen, focused):
    f = fonts()
    r = access_button_rect()
    theme.panel(screen, (r.x, r.y, r.w, r.h), P.YELLOW, cut=10)
    if focused:
        pygame.draw.rect(screen, P.YELLOW, r.inflate(-6, -6), 2)
    # a little "person" accessibility icon
    cx, cy = r.x + 22, r.centery
    pygame.draw.circle(screen, P.YELLOW, (cx, cy - 8), 3)
    pygame.draw.line(screen, P.YELLOW, (cx - 7, cy - 3), (cx + 7, cy - 3), 2)
    pygame.draw.line(screen, P.YELLOW, (cx, cy - 3), (cx, cy + 4), 2)
    pygame.draw.line(screen, P.YELLOW, (cx, cy + 4), (cx - 5, cy + 11), 2)
    pygame.draw.line(screen, P.YELLOW, (cx, cy + 4), (cx + 5, cy + 11), 2)
    img =f["label"].render("ACCESSIBILITY   [TAB]", True, P.YELLOW if focused else P.WHITE)
    screen.blit(img, img.get_rect(midleft=(r.x + 40, r.centery)))
    return r


def get_player_name(screen, clock, font_big=None, font_small=None, settings=None):
    """Start screen: type a callsign. Also opens the accessibility menu
    (TAB, the button in the corner, or UP/DOWN to select it and ENTER)."""
    if settings is None:
        settings = settings_mod.load()
    name = ""
    focus = "name"          # or "access"
    start = time.time()
    while True:
        f = fonts()
        button = access_button_rect()
        open_menu = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                elif event.key == pygame.K_TAB:
                    open_menu = True
                elif event.key in (pygame.K_UP, pygame.K_DOWN):
                    focus = "access" if focus == "name" else "name"
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if focus == "access":
                        open_menu = True
                    elif name.strip():
                        return sanitise_name(name)
                elif event.key == pygame.K_BACKSPACE:
                    focus = "name"
                    name = name[:-1]
                elif event.unicode and event.unicode.isprintable() and len(name) < 16:
                    focus = "name"
                    name += event.unicode
            elif event.type == pygame.MOUSEMOTION:
                if button.collidepoint(event.pos):
                    focus = "access"
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if button.collidepoint(event.pos):
                    open_menu = True

        if open_menu:
            accessibility_menu(screen, clock, settings)
            focus = "name"
            continue

        now = time.time() - start
        theme.draw_menu_background(screen, now)
        draw_access_button(screen, focus == "access")
        theme.draw_glow_title(screen, f["title"], "CYBERRACE", P.CYAN, (WIDTH // 2, 170))
        text(screen, f["label"], "//  ANSWER FAST.  DRIVE FASTER.  //", (WIDTH // 2, 235), P.MAGENTA, center=True)

        # callsign box
        bw = max(520, tw(f["big"], "> " + "W" * 16 + "_") + 80)
        bh = 22 + lh(f["label"]) + 10 + lh(f["big"]) + 8 + lh(f["label"]) + 18
        bx, by = WIDTH // 2 - bw // 2, 270
        theme.panel(screen, (bx, by, bw, bh), P.CYAN)
        if focus == "name":
            pygame.draw.rect(screen, theme.scale(P.CYAN, 0.6), (bx + 6, by + 6, bw - 12, bh - 12), 1)
        y = by + 22
        text(screen, f["label"], "ENTER CALLSIGN", (bx + 30, y), P.DIM)
        y += lh(f["label"]) + 10
        cursor = "_" if (blink(now, 2.5) and focus == "name") else " "
        text(screen, f["big"], f"> {name}{cursor}", (bx + 30, y), P.WHITE)
        y += lh(f["big"]) + 8
        text(screen, f["label"], "PRESS ENTER TO CONNECT", (bx + bw - 30, y),
             P.CYAN if blink(now, 1.2) else P.DIM, right=True)

        # how to play
        rows = [
            ("DRIVE", "Arrow keys / WASD / joystick", P.CYAN, None),
            ("ANSWER", "T = True     F = False", P.CYAN, None),
            ("EVERY LAP", "a cybersecurity question pops up -- the clock pauses", P.CYAN, None),
            ("CORRECT", f"{BOOST_DURATION:.0f} second speed boost", P.GREEN, True),
            ("WRONG", f"+{WRONG_ANSWER_PENALTY:.0f} seconds on your time", P.RED, False),
        ]
        label_w = max(tw(f["label"], r[0]) for r in rows) + 60
        rw = min(WIDTH - 40, label_w + max(tw(f["small"], r[1]) for r in rows) + 80)
        row_h = max(lh(f["small"]), lh(f["label"])) + sz(8)
        ry = by + bh + 30
        rh = 26 + row_h * len(rows) + 14
        rx = WIDTH // 2 - rw // 2
        theme.panel(screen, (rx, ry, rw, rh), P.MAGENTA)
        for k, (label, value, colour, icon) in enumerate(rows):
            y = ry + 22 + k * row_h
            lab = f["label"].render(label, True, colour)
            screen.blit(lab, lab.get_rect(midleft=(rx + 30, y + row_h // 2)))
            val = f["small"].render(value, True, P.WHITE)
            screen.blit(val, val.get_rect(midleft=(rx + 30 + label_w, y + row_h // 2)))
            if icon is not None:
                answer_icon(screen, icon, (rx + 30 + label_w - 24, y + row_h // 2), sz(16))
        pygame.display.flip()
        clock.tick(FPS)


# --- Accessibility menu ----------------------------------------------------------
MENU_ROWS = [
    ("colour_mode", "COLOUR MODE"),
    ("text_size", "TEXT SIZE"),
    ("reduce_effects", "REDUCE FLASHING & EFFECTS"),
    ("reset", "RESET TO DEFAULTS"),
    ("back", "BACK"),
]


def _menu_value(settings, key):
    if key == "colour_mode":
        return next(n for i, n, _ in settings_mod.COLOUR_MODES if i == settings[key])
    if key == "text_size":
        return next(n for i, n, _ in settings_mod.TEXT_SIZES if i == settings[key])
    if key == "reduce_effects":
        return "On" if settings[key] else "Off"
    return None


def _menu_help(settings, key):
    if key == "colour_mode":
        return next(d for i, _, d in settings_mod.COLOUR_MODES if i == settings[key])
    return {
        "text_size": "Makes all the reading text bigger -- questions, the HUD and menus.",
        "reduce_effects": "Turns off blinking, screen flashes, scanlines and glow.",
        "reset": "Put every setting back to normal.",
        "back": "Save and go back to the start screen.",
    }[key]


def _preview(screen, x, y, w, h):
    """Little samples of every colour that matters, in the current mode."""
    f = fonts()
    theme.panel(screen, (x, y, w, h), P.DIM, cut=10)
    text(screen, f["label"], "PREVIEW", (x + 24, y + 14), P.DIM)
    chips = ["ROAD EDGE", "WALL", "GRASS", "CAR", "BOOSTED", "RIGHT", "WRONG"]
    cw = (w - 48) // len(chips)
    top = y + 14 + lh(f["label"]) + 10
    ch = sz(46)
    for i, label in enumerate(chips):
        cx = x + 24 + i * cw + cw // 2
        box = pygame.Rect(cx - cw // 2 + 8, top, cw - 16, ch)
        pygame.draw.rect(screen, P.ROAD, box)
        if label == "ROAD EDGE":
            pygame.draw.line(screen, P.CYAN, (box.x + 8, box.centery), (box.right - 8, box.centery), 4)
        elif label == "WALL":
            pygame.draw.line(screen, P.MAGENTA, (box.x + 8, box.centery), (box.right - 8, box.centery), 6)
        elif label == "GRASS":
            pygame.draw.rect(screen, P.VERGE, box.inflate(-10, -10))
            for gx in range(box.x + 5, box.right - 5, 8):
                pygame.draw.line(screen, theme.lerp(P.VERGE, P.VERGE_GRID, 0.3), (gx, box.y + 5), (gx, box.bottom - 6))
        elif label in ("CAR", "BOOSTED"):
            fake = type("C", (), {"x": box.centerx, "y": box.centery, "heading": 0.0})()
            draw_car(screen, fake, P.CAR_BOOST if label == "BOOSTED" else P.CAR)
        else:
            answer_icon(screen, label == "RIGHT", box.center, min(ch - 12, sz(28)))
        text(screen, f["label"], label, (cx, box.bottom + 6 + lh(f["label"]) // 2), P.WHITE, center=True)
    ty = top + ch + 12 + lh(f["label"]) + 10
    sample = fit(f["big"], "Is this text easy to read?", w - 48)
    if ty + lh(f["big"]) < y + h:
        text(screen, f["big"], sample, (x + w // 2, ty + lh(f["big"]) // 2), P.WHITE, center=True)


def accessibility_menu(screen, clock, settings):
    """Choose colour mode, text size and reduced effects. Changes show straight
    away and are saved when you leave. Keyboard: UP/DOWN pick, LEFT/RIGHT or
    ENTER change, ESC back. Mouse: click a setting to change it."""
    selected = 0
    start = time.time()
    while True:
        f = fonts()
        # layout (recomputed every frame: it changes when the text size does)
        px, pw = 90, WIDTH - 180
        py = 130
        row_h = max(lh(f["mid"]), lh(f["label"])) + sz(18)
        help_lines = wrap_lines(f["small"], _menu_help(settings, MENU_ROWS[selected][0]), pw - 80)
        ph = 20 + row_h * len(MENU_ROWS) + 14 + len(help_lines) * (lh(f["small"]) + 2) + 18
        row_rects = [pygame.Rect(px + 16, py + 20 + i * row_h, pw - 32, row_h - 6) for i in range(len(MENU_ROWS))]

        def change(i, step):
            nonlocal selected
            key = MENU_ROWS[i][0]
            if key == "back":
                return "back"
            if key == "reset":
                settings.clear()
                settings.update(settings_mod.DEFAULTS)
            else:
                settings_mod.cycle(settings, key, step)
            apply_settings(settings)
            settings_mod.save(settings)
            return None

        leave = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE, pygame.K_TAB):
                    leave = True
                elif event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(MENU_ROWS)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(MENU_ROWS)
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    if MENU_ROWS[selected][0] not in ("reset", "back"):
                        change(selected, -1)
                elif event.key in (pygame.K_RIGHT, pygame.K_d, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    if change(selected, +1) == "back":
                        leave = True
            elif event.type == pygame.MOUSEMOTION:
                for i, r in enumerate(row_rects):
                    if r.collidepoint(event.pos):
                        selected = i
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, r in enumerate(row_rects):
                    if r.collidepoint(event.pos):
                        selected = i
                        # click the left half of the value to go back a step
                        step = -1 if event.pos[0] < r.right - (r.w // 4) else +1
                        if change(i, step) == "back":
                            leave = True
        if leave:
            settings_mod.save(settings)
            return

        now = time.time() - start
        f = fonts()   # may have changed size just now
        theme.draw_menu_background(screen, now)
        theme.draw_glow_title(screen, f["huge"], "ACCESSIBILITY", P.CYAN, (WIDTH // 2, 62))
        text(screen, fonts()["label"], "//  MAKE CYBERRACE WORK FOR YOU  //", (WIDTH // 2, 108), P.MAGENTA, center=True)

        theme.panel(screen, (px, py, pw, ph), P.CYAN)
        for i, (key, label) in enumerate(MENU_ROWS):
            r = row_rects[i]
            sel = i == selected
            if sel:
                pygame.draw.rect(screen, theme.scale(P.CYAN, 0.18), r)
                pygame.draw.rect(screen, P.CYAN, r, 2)
                text(screen, f["mid"], ">", (r.x + 12, r.centery - lh(f["mid"]) // 2), P.CYAN)
            colour = P.WHITE if key not in ("reset", "back") else (P.YELLOW if key == "back" else P.DIM)
            img = f["mid"].render(label, True, colour)
            screen.blit(img, img.get_rect(midleft=(r.x + 40, r.centery)))
            value = _menu_value(settings, key)
            if value is not None:
                v = f"<  {value}  >" if sel else value
                img = f["mid"].render(v, True, P.CYAN if sel else P.DIM)
                screen.blit(img, img.get_rect(midright=(r.right - 20, r.centery)))
        hy = py + 20 + row_h * len(MENU_ROWS) + 10
        draw_lines(screen, f["small"], help_lines, px + pw // 2, hy, P.DIM, line_gap=2)

        prev_y = py + ph + 14
        prev_h = HEIGHT - 52 - prev_y
        if prev_h > 60:
            _preview(screen, px, prev_y, pw, prev_h)

        text(screen, f["label"], "UP/DOWN  choose      LEFT/RIGHT  change      ESC  back",
             (WIDTH // 2, HEIGHT - 26), P.DIM, center=True)
        pygame.display.flip()
        clock.tick(FPS)


# --- In-race screens -------------------------------------------------------------
def question_overlay(screen, font_big, font_small, question, lap_done, now=0.0):
    f = fonts()
    screen.blit(theme.dim_overlay(200), (0, 0))
    pw = 1000 if theme.S.text_scale <= 1.0 else 1180
    q_lines = wrap_lines(font_big, question["text"], pw - 120)
    btn_w, btn_h = sz(300), lh(f["head"]) + sz(30)
    head_h = 26 + lh(f["label"]) + 14
    pause_h = lh(f["label"]) + 18
    q_h = len(q_lines) * (lh(font_big) + 4)
    ph = head_h + pause_h + q_h + 34 + btn_h + 30 + lh(f["label"]) + 30
    px, py = WIDTH // 2 - pw // 2, max(10, HEIGHT // 2 - ph // 2)
    theme.panel(screen, (px, py, pw, ph), P.CYAN, alpha=235)

    text(screen, f["label"], "//  SECURITY CHALLENGE", (px + 36, py + 26), P.MAGENTA)
    status = "FINAL LAP COMPLETE" if lap_done >= TOTAL_LAPS else f"LAP {lap_done}/{TOTAL_LAPS} COMPLETE"
    text(screen, f["label"], status, (px + pw - 36, py + 26), P.CYAN, right=True)
    y = py + head_h
    pygame.draw.line(screen, theme.scale(P.CYAN, 0.4), (px + 36, y - 8), (px + pw - 36, y - 8), 1)
    if blink(now, 1.5):
        text(screen, f["label"], "[ CLOCK PAUSED ]", (WIDTH // 2, y + lh(f["label"]) // 2 + 4), P.YELLOW, center=True)
    y += pause_h

    y = draw_lines(screen, font_big, q_lines, WIDTH // 2, y, P.WHITE) + 34

    gap = sz(40)
    for k, (key, label, colour, correct) in enumerate([("T", "TRUE", P.GREEN, True), ("F", "FALSE", P.RED, False)]):
        bx = WIDTH // 2 - btn_w - gap // 2 + k * (btn_w + gap)
        theme.panel(screen, (bx, y, btn_w, btn_h), colour, alpha=235, cut=12)
        answer_icon(screen, correct, (bx + sz(34), y + btn_h // 2), sz(26))
        img = f["head"].render(f"[{key}]  {label}", True, colour)
        screen.blit(img, img.get_rect(center=(bx + btn_w // 2 + sz(18), y + btn_h // 2)))
    y += btn_h + 30

    if lap_done >= TOTAL_LAPS:
        stakes = f"WRONG = +{WRONG_ANSWER_PENALTY:.0f}s ON YOUR FINAL TIME"
    else:
        stakes = f"CORRECT = {BOOST_DURATION:.0f}s BOOST        WRONG = +{WRONG_ANSWER_PENALTY:.0f}s PENALTY"
    text(screen, f["label"], stakes, (WIDTH // 2, y + lh(f["label"]) // 2), P.DIM, center=True)


def hud_size():
    f = fonts()
    w = max(sz(300), 34 + tw(f["label"], "PENALTY") + 20 + tw(f["mid"], "W" * 9) + 20)
    row = max(lh(f["mid"]), lh(f["label"])) + 4
    h = 16 + row * 6 + 14
    return w, h, row


def draw_hud(screen, font_small, player_name, lap, total_time, penalty_secs, car, level=(1, 1)):
    f = fonts()
    w, h, row = hud_size()
    theme.panel(screen, (14, 14, w, h), P.CYAN)
    vx = 34 + tw(f["label"], "PENALTY") + 20
    rows = [("PILOT", fit(f["mid"], player_name, w - vx - 16), P.WHITE),
            ("LEVEL", f"{level[0]}/{level[1]}", P.WHITE),
            ("LAP", f"{lap}/{TOTAL_LAPS}", P.WHITE),
            ("TIME", f"{total_time:0.1f}s", P.WHITE),
            ("PENALTY", f"+{penalty_secs:0.0f}s", P.RED if penalty_secs else P.DIM)]
    for k, (label, value, colour) in enumerate(rows):
        cy = 14 + 16 + k * row + row // 2
        lab = f["label"].render(label, True, P.DIM)
        screen.blit(lab, lab.get_rect(midleft=(34, cy)))
        val = f["mid"].render(value, True, colour)
        screen.blit(val, val.get_rect(midleft=(vx, cy)))

    # speed: segmented bar, segments past normal top speed light up in the boost colour
    cy = 14 + 16 + 5 * row + row // 2
    lab = f["label"].render("SPEED", True, P.DIM)
    screen.blit(lab, lab.get_rect(midleft=(34, cy)))
    top = MAX_SPEED * BOOST_MULTIPLIER
    segs, normal_segs = 20, round(20 * MAX_SPEED / top)
    seg_w = max(5, (w - vx - 20) // segs)
    lit = round(segs * min(1.0, abs(car.speed) / top))
    seg_h = sz(14)
    for s in range(segs):
        colour = (P.CAR_BOOST if s >= normal_segs else P.CYAN) if s < lit else theme.scale(P.DIM, 0.3)
        pygame.draw.rect(screen, colour, (vx + s * seg_w, cy - seg_h // 2, seg_w - 2, seg_h))

    if car.boost_timer > 0:
        bw = sz(300)
        bh = 14 + lh(f["head"]) + 10 + sz(12) + 14
        bx = WIDTH - 14 - bw
        theme.panel(screen, (bx, 14, bw, bh), P.CAR_BOOST)
        text(screen, f["head"], "BOOST", (bx + 24, 26), P.CAR_BOOST)
        text(screen, f["mid"], f"{car.boost_timer:0.1f}s", (bx + bw - 20, 26 + (lh(f["head"]) - lh(f["mid"])) // 2),
             P.WHITE, right=True)
        segs = int(BOOST_DURATION)
        lit = math.ceil(car.boost_timer)
        sw = (bw - 48) // segs
        for s in range(segs):
            colour = P.CAR_BOOST if s < lit else theme.scale(P.CAR_BOOST, 0.2)
            pygame.draw.rect(screen, colour, (bx + 24 + s * sw, 26 + lh(f["head"]) + 8, sw - 4, sz(12)))


def draw_feedback_banner(screen, feedback, font_small):
    """ACCESS GRANTED / DENIED banner after answering. Sits between the HUD and the
    boost panel if there's room, otherwise just below the HUD."""
    f = fonts()
    title, colour, lines, correct = feedback[0], feedback[1], feedback[2], feedback[4]
    hud_w, hud_h, _ = hud_size()
    room = WIDTH - 2 * (hud_w + 28)
    if room >= 600:
        w, y = min(room, sz(640)), 14
    else:
        w, y = min(WIDTH - 60, sz(760)), 14 + hud_h + 12
    wrapped = []
    for line, c in lines:
        wrapped += [(ln, c) for ln in wrap_lines(font_small, line, w - 60)]
    h = 18 + lh(f["head"]) + 8 + len(wrapped) * (lh(font_small) + 2) + 16
    x = WIDTH // 2 - w // 2
    theme.panel(screen, (x, y, w, h), colour, alpha=235)
    ty = y + 18 + lh(f["head"]) // 2
    r = neon_text(screen, f["head"], title, (WIDTH // 2 + sz(16), ty), colour)
    answer_icon(screen, correct, (WIDTH // 2 - tw(f["head"], title) // 2 - sz(12), ty), sz(26))
    ly = y + 18 + lh(f["head"]) + 8
    for ln, c in wrapped:
        img = font_small.render(ln, True, c)
        screen.blit(img, img.get_rect(midtop=(WIDTH // 2, ly)))
        ly += lh(font_small) + 2


def draw_finish(screen, font_big, font_small, font_huge, player_name, total_time, finish_time,
                penalty_secs, questions_correct, questions_total, feedback, now,
                next_prompt="PRESS ENTER TO SEND TO THE SCOREBOARD"):
    f = fonts()
    screen.blit(theme.dim_overlay(150), (0, 0))
    pw = 920 if theme.S.text_scale <= 1.0 else 1120
    summary = wrap_lines(font_small, f"driving {finish_time:0.2f}s  +  penalties {penalty_secs:0.0f}s   |   "
                                     f"questions right {questions_correct}/{questions_total}", pw - 80)
    extra = []
    if feedback:
        for line, c in feedback[2][1:]:
            extra += [(ln, c) for ln in wrap_lines(font_small, line, pw - 100)]
    ph = (26 + lh(f["label"]) + 20 + lh(font_huge) + 12 + lh(f["label"]) + 4 + lh(font_big) + 12
          + len(summary) * (lh(font_small) + 2) + 18
          + (lh(f["label"]) + 8 + len(extra) * (lh(font_small) + 2) if feedback else 0)
          + 24 + lh(f["label"]) + 26)
    px, py = WIDTH // 2 - pw // 2, max(10, HEIGHT // 2 - ph // 2)
    theme.panel(screen, (px, py, pw, ph), P.GREEN, alpha=235)
    text(screen, f["label"], "//  RACE COMPLETE", (px + 36, py + 26), P.MAGENTA)
    text(screen, f["label"], fit(f["label"], f"PILOT: {player_name}", pw // 2 - 40), (px + pw - 36, py + 26),
         P.CYAN, right=True)
    y = py + 26 + lh(f["label"]) + 20
    neon_text(screen, font_huge, "FINISHED", (WIDTH // 2, y + lh(font_huge) // 2), P.GREEN)
    y += lh(font_huge) + 12
    text(screen, f["label"], "FINAL TIME", (WIDTH // 2, y + lh(f["label"]) // 2), P.DIM, center=True)
    y += lh(f["label"]) + 4
    neon_text(screen, font_big, f"{total_time:0.2f}s", (WIDTH // 2, y + lh(font_big) // 2), P.WHITE)
    y += lh(font_big) + 12
    y = draw_lines(screen, font_small, summary, WIDTH // 2, y, P.DIM, line_gap=2) + 16
    if feedback:
        ty = y + lh(f["label"]) // 2
        text(screen, f["label"], feedback[0], (WIDTH // 2 + sz(12), ty), feedback[1], center=True)
        answer_icon(screen, feedback[4], (WIDTH // 2 - tw(f["label"], feedback[0]) // 2 - sz(6), ty), sz(16))
        y += lh(f["label"]) + 8
        for ln, c in extra:
            img = font_small.render(ln, True, c)
            screen.blit(img, img.get_rect(midtop=(WIDTH // 2, y)))
            y += lh(font_small) + 2
    text(screen, f["label"], next_prompt, (WIDTH // 2, py + ph - 26 - lh(f["label"]) // 2),
         P.CYAN if blink(now, 1.2) else P.DIM, center=True)


def level_intro(screen, clock, track, level, total_so_far=0.0):
    """'LEVEL 2 / 3  DATA DRIFT' with a preview of the track. ENTER to start,
    ESC to give up and go back to the start screen (returns False)."""
    f = fonts()
    draw_track(screen, track)                       # builds the cached drawing now, not mid-race
    preview = pygame.transform.smoothscale(_track_surfaces[track.track_id], (640, 400))
    start = time.time()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    return True
        now = time.time() - start
        theme.draw_menu_background(screen, now)
        text(screen, f["head"], f"LEVEL {level[0]} / {level[1]}", (WIDTH // 2, 70), P.MAGENTA, center=True)
        theme.draw_glow_title(screen, f["huge"], track.name, P.CYAN, (WIDTH // 2, 135))
        theme.panel(screen, (WIDTH // 2 - 330, 190, 660, 420), P.CYAN)
        screen.blit(preview, (WIDTH // 2 - 320, 200))
        info = f"road {2 * track.half_width}px wide"
        if total_so_far:
            info += f"   |   your time so far {total_so_far:0.2f}s"
        text(screen, f["small"], info, (WIDTH // 2, 640), P.DIM, center=True)
        text(screen, f["label"], "PRESS ENTER TO START        ESC = BACK TO MENU", (WIDTH // 2, 700),
             P.CYAN if blink(now, 1.2) else P.DIM, center=True)
        pygame.display.flip()
        clock.tick(FPS)


def run_race(screen, clock, controls, font_big, font_small, font_huge, player_name,
             track=TRACK, level=(1, 1), deck=None):
    """Race one level. `level` is (this level, how many levels); pass the same
    `deck` for every level so nobody sees the same question twice in one go."""
    f = fonts()
    start_x, start_y, start_heading, start_idx = track.start_pose()
    car = Car(start_x, start_y, start_heading, start_idx)   # on the grid, just behind the line
    laps = LapCounter(track)
    laps.update(car.track_idx)
    crash_flash_until = -1.0
    deck = deck or QuestionDeck()
    trail = deque(maxlen=22)

    questions_correct = 0
    questions_total = 0
    penalty_secs = 0.0
    active_question = None
    question_lap = 0      # which lap the on-screen question was triggered by
    feedback = None       # (title, colour, lines [(text, colour)], expires_at, correct)
    race_secs = 0.0       # driving time; doesn't run while a question is on screen
    finish_time = None    # driving time when the final lap was completed
    finished = False      # True once the final question has been answered
    wall_start = time.time()

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        now = time.time() - wall_start   # real time, for on-screen messages only

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return None  # bail out to menu without saving a result

        if active_question is None:
            throttle, steer = controls.get_drive_input()
            if finish_time is not None:
                throttle, steer = 0.0, 0.0          # race over: let the car roll to a stop
            else:
                race_secs += dt
            car.update(dt, throttle, steer, track)
            trail.append((car.x, car.y))
            laps_before = laps.laps
            laps.update(car.track_idx)
            if car.wall_hit:
                crash_flash_until = now + 0.4

            # Crossed the start/finish line to complete a lap: pop up a question.
            if laps.laps > laps_before and finish_time is None:
                question_lap = laps.laps
                if laps.laps >= TOTAL_LAPS:
                    finish_time = race_secs
                active_question = deck.next_question()
        else:
            correct = None
            if controls.true_pressed():
                correct = active_question["answer"] is True
            elif controls.false_pressed():
                correct = active_question["answer"] is False

            if correct is not None:
                questions_total += 1
                explain = active_question.get("explain", "")
                if correct:
                    questions_correct += 1
                    title, colour = "ACCESS GRANTED", P.GREEN
                    if question_lap < TOTAL_LAPS:
                        car.apply_boost()
                        lines = [(f"Correct -- {BOOST_DURATION:.0f}s speed boost!", P.GREEN)]
                    else:
                        lines = [("Correct -- no time penalty.", P.GREEN)]
                else:
                    penalty_secs += WRONG_ANSWER_PENALTY
                    title, colour = "ACCESS DENIED", P.RED
                    lines = [(f"Wrong -- +{WRONG_ANSWER_PENALTY:.0f}s added to your time.", P.RED)]
                if explain:
                    lines.append((explain, P.WHITE))
                # bigger text takes longer to read, so it stays up a little longer
                feedback = (title, colour, lines, now + 4.0 * theme.S.text_scale, correct)
                active_question = None
                if question_lap >= TOTAL_LAPS:
                    finished = True

        # --- draw ---
        draw_track(screen, track)
        boosting = car.boost_timer > 0
        draw_car(screen, car, P.CAR_BOOST if boosting else P.CAR, trail)

        total_time = (finish_time if finish_time is not None else race_secs) + penalty_secs
        draw_hud(screen, font_small, player_name, min(laps.laps + 1, TOTAL_LAPS), total_time, penalty_secs, car,
                 level)

        if now < crash_flash_until:
            if not theme.S.reduce_effects:
                pygame.draw.rect(screen, P.MAGENTA, (0, 0, WIDTH, HEIGHT), 10)
            neon_text(screen, f["head"], "!! IMPACT !!", (WIDTH // 2, HEIGHT - 30 - lh(f["head"]) // 2), P.MAGENTA)

        if feedback and now < feedback[3] and not finished:
            draw_feedback_banner(screen, feedback, font_small)

        if active_question is not None:
            question_overlay(screen, font_big, font_small, active_question, question_lap, now)

        if finished:
            last = level[0] >= level[1]
            draw_finish(screen, font_big, font_small, font_huge, player_name, total_time, finish_time,
                        penalty_secs, questions_correct, questions_total, feedback, now,
                        "PRESS ENTER TO SEND TO THE SCOREBOARD" if last else
                        f"PRESS ENTER FOR LEVEL {level[0] + 1}")
            keys = pygame.key.get_pressed()
            if keys[pygame.K_RETURN]:
                running = False

        pygame.display.flip()

    return {
        "time_secs": finish_time + penalty_secs,
        "race_secs": finish_time,
        "penalty_secs": penalty_secs,
        "questions_correct": questions_correct,
        "questions_total": questions_total,
    }


def run_summary(screen, clock, player_name, results, scoreboard):
    """After the last level: each level's result, the total that was sent to the
    scoreboard, and whether it got there. ENTER = next player."""
    total = sum(r["time_secs"] for r in results)
    penalty = sum(r["penalty_secs"] for r in results)
    right = sum(r["questions_correct"] for r in results)
    asked = sum(r["questions_total"] for r in results)
    start = time.time()
    while True:
        f = fonts()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return
        now = time.time() - start
        theme.draw_menu_background(screen, now)
        theme.draw_glow_title(screen, f["huge"], "RUN COMPLETE", P.CYAN, (WIDTH // 2, 70))
        text(screen, f["label"], fit(f["label"], f"//  PILOT: {player_name}  //", WIDTH - 80),
             (WIDTH // 2, 118), P.MAGENTA, center=True)

        # each level, then the total that goes to the scoreboard
        pw = min(WIDTH - 60, sz(900))
        px, py = WIDTH // 2 - pw // 2, 150
        row_h = lh(f["mid"]) + sz(12)
        ph = 18 + lh(f["label"]) + 20 + row_h * (len(results) + 1) + 24
        theme.panel(screen, (px, py, pw, ph), P.CYAN)
        col_x = [px + int(pw * c) for c in (0.045, 0.52, 0.685, 0.85)]
        hy = py + 18 + lh(f["label"]) // 2
        for h, x in zip(["LEVEL", "TIME", "PENALTY", "CORRECT"], col_x):
            img = f["label"].render(h, True, P.DIM)
            screen.blit(img, img.get_rect(midleft=(x, hy)))
        line_y = py + 18 + lh(f["label"]) + 10
        pygame.draw.line(screen, theme.scale(P.CYAN, 0.4), (px + 30, line_y), (px + pw - 30, line_y), 1)
        rows = [(f"{n}  {t.name}", r) for n, (t, r) in enumerate(zip(TRACKS, results), 1)]
        for i, (label, r) in enumerate(rows):
            y = line_y + 10 + i * row_h + (row_h - 4) // 2
            vals = [label, f"{r['time_secs']:0.2f}s", f"+{r['penalty_secs']:0.0f}s",
                    f"{r['questions_correct']}/{r['questions_total']}"]
            for k, (val, x) in enumerate(zip(vals, col_x)):
                c = P.RED if k == 2 and r["penalty_secs"] else P.WHITE
                img = f["mid"].render(val, True, c)
                screen.blit(img, img.get_rect(midleft=(x, y)))
        y = line_y + 10 + len(rows) * row_h
        pygame.draw.rect(screen, theme.lerp(P.PANEL, P.CYAN, 0.12), (px + 24, y, pw - 48, row_h - 4))
        sent = make_row(player_name, total, penalty, right, asked)
        for k, (val, x) in enumerate(zip(["TOTAL", sent["time"], sent["penalty"], sent["correct"]], col_x)):
            img = f["mid"].render(val, True, P.YELLOW)
            screen.blit(img, img.get_rect(midleft=(x, y + (row_h - 4) // 2)))

        # did it reach the scoreboard?
        status, message = scoreboard.status, scoreboard.message
        sy = py + ph + 40
        if status == "sent":
            line, colour, icon = "ON THE SCOREBOARD", P.GREEN, True
        elif status == "sending":
            dots = "." * (1 + int(now * 3) % 3)
            line, colour, icon = f"SENDING TO THE SCOREBOARD{dots}", P.YELLOW, None
        elif status == "not_set_up":
            line, colour, icon = "SCOREBOARD NOT SET UP", P.RED, False
        else:
            line, colour, icon = "SCOREBOARD OFFLINE -- WILL RETRY", P.RED, False
        r = text(screen, f["head"], line, (WIDTH // 2 + (sz(18) if icon is not None else 0), sy), colour, center=True)
        if icon is not None:
            answer_icon(screen, icon, (WIDTH // 2 - tw(f["head"], line) // 2 - sz(8), sy), sz(26))
        if message and status in ("offline", "not_set_up"):
            wrapped_text(screen, f["small"], message, WIDTH // 2, sy + lh(f["head"]) // 2 + 12, WIDTH - 160, P.DIM)

        text(screen, f["label"], "ENTER = NEXT PLAYER        ESC = QUIT", (WIDTH // 2, HEIGHT - 34),
             P.CYAN if blink(now, 1.2) else P.DIM, center=True)
        pygame.display.flip()
        clock.tick(FPS)


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN | pygame.SCALED)
    pygame.display.set_caption("CyberRace")
    clock = pygame.time.Clock()
    settings = settings_mod.load()
    apply_settings(settings)

    controls = Controls()
    print(f"Joystick detected: {controls.has_joystick}")
    scoreboard = Scoreboard()        # sends finished scores to the MySQL scoreboard

    while True:
        scoreboard.retry()              # resend any score that couldn't get through last time
        player_name = get_player_name(screen, clock, settings=settings)
        f = fonts()     # the text size may have been changed on the start screen
        deck = QuestionDeck()           # shared, so no repeated questions in one go
        results = []
        for n, track in enumerate(TRACKS, 1):
            level = (n, len(TRACKS))
            total_so_far = sum(r["time_secs"] for r in results)
            if not level_intro(screen, clock, track, level, total_so_far):
                break                   # ESC: back to the start screen
            result = run_race(screen, clock, controls, f["big"], f["small"], f["huge"], player_name,
                              track, level, deck)
            if result is None:
                break                   # ESC during the race
            results.append(result)
        if len(results) == len(TRACKS):
            # Finished every level: send ONE row to the scoreboard -- the totals.
            scoreboard.submit(make_row(
                player_name,
                sum(r["time_secs"] for r in results),
                sum(r["penalty_secs"] for r in results),
                sum(r["questions_correct"] for r in results),
                sum(r["questions_total"] for r in results),
            ))
            run_summary(screen, clock, player_name, results, scoreboard)


if __name__ == "__main__":
    main()
