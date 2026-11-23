# CyberRace

A top-down arcade racer with **true/false cybersecurity questions**. Every time
you cross the start/finish line a question pops up (the race clock pauses while
it's on screen):

- **Right answer:** a 10-second speed boost. The car goes about 35% faster
  (260 -> ~350 px/s) and turns sharper to match, so it handles the same.
  It turns yellow and a countdown bar shows how much boost is left.
- **Wrong answer:** 10 seconds added to your race time.

There are **three levels**, raced in order: NEON CIRCUIT (easy), DATA DRIFT
(medium) and FIREWALL (hard). Each is 3 laps, so 3 questions per level and 9 per
go, with no repeats (the last question on each level, at the finish, can only
cost you time). The **lowest total time over all three levels** (driving +
penalties) wins. When you finish all three, your name and totals are sent to a
**MySQL database** so a separate display can show the scoreboard on a big screen
for everyone to see.

Built as a runnable prototype now, structured to move onto a Raspberry Pi +
joystick with no code changes.

---

## 1. Stack, and why

| Piece | Choice | Why |
|---|---|---|
| Game engine | **Python 3 + pygame** | Runs identically on a laptop and a Raspberry Pi; `pygame.joystick` reads USB joysticks/gamepads with no extra driver config. |
| Physics/logic | Plain Python (`car.py`, `track.py`, `questions.py`) | No pygame dependency in the logic itself, so it's fast to unit test and easy to reason about. |
| Scoreboard | **MySQL**, via **PyMySQL** (`scoreboard.py`) | The scoreboard is shown on a big external screen, so scores go to one central database that the display reads. PyMySQL is pure Python, so it installs on a Raspberry Pi with no compiling. The game keeps no database of its own, so scores are never shown in two places. |

## 2. Project layout

```
cyberrace/
├── main.py               # game loop: menu -> 3 levels -> run summary, and all the screens
├── theme.py              # the look: colour modes, fonts, glow / panel / scanline effects
├── settings.py           # accessibility settings (colour mode, text size, effects), saved to settings.json
├── cvd.py                # colour-blindness simulation, used to check the colour modes
├── fonts/                # Orbitron + Share Tech Mono (free, SIL Open Font License)
├── car.py                # car physics (accel, steering, friction, 10s boost, grass, wall collisions)
├── track.py              # the three levels, grass verge and walls, nearest-road lookup, lap counter, check_track()
├── controls.py           # joystick input, with keyboard fallback
├── questions.py          # cybersecurity true/false question bank
├── scoreboard.py         # sends each finished score to the MySQL scoreboard (in the background, retries if offline)
├── scoreboard_config.json # MySQL connection details -- fill this in (keep it private: it holds the password)
├── test_game_logic.py    # AI driver + real physics + lap counter (no pygame needed)
├── test_race_loop.py     # runs main.run_race() with a stand-in for pygame
├── test_accessibility.py # colour modes vs colour blindness, every setting draws, menu works + saves
└── requirements.txt
```

## 3. How to run it

```bash
pip install -r requirements.txt --break-system-packages   # or use a venv
python3 main.py
```

No joystick plugged in? It still runs — steer with **arrow keys / WASD**,
throttle with **up/down / W/S**, **T** or **F** to answer a question when one
pops up, **ESC** to quit. Press **TAB** (or click the button in the top-right
of the start screen) for the accessibility settings.

Everything except the actual drawing can be tested on any machine, no display or
joystick needed:
```bash
python3 track.py             # circuit fits the screen, doesn't overlap, corners drivable, laps count
python3 car.py               # physics, grass slowdown, walls stop the car all round
python3 test_game_logic.py   # an AI driver completes 3 laps of every level; boosted car still holds the road
python3 test_race_loop.py    # the real race loop on every level: questions, boost, penalty, no repeats
python3 settings.py          # settings save/load, and survive a missing or corrupt file
python3 test_accessibility.py # colour modes checked against colour blindness, all 24 setting combos, the menu
python3 questions.py         # 30 questions: short enough, balanced True/False
python3 scoreboard.py        # scoreboard sending (with a pretend MySQL), then checks your real connection
```

## 3a. The look

A neon "cyber" style: a dark circuit-board grid, cyan glowing road edges, a green
data-grid verge (the grass), magenta glowing walls, scanlines, and a glowing car
with a light trail (cyan normally, yellow while boosted). Questions appear as a
"SECURITY CHALLENGE" terminal; answers show **ACCESS GRANTED** or **ACCESS DENIED**.

- All colours are at the top of `theme.py` -- change them there to re-skin the game.
- The two fonts are bundled in `fonts/` so it looks the same on a Pi as on a
  laptop. Both are free to use and share (SIL Open Font License, files included).
  If they're missing, a system monospace font is used instead.
- The expensive effects (glow, scanlines, background) are drawn once at start-up,
  so a frame is mostly simple blits -- well under 1 ms per frame on a laptop,
  comfortably inside 60 fps on a Raspberry Pi 4.

## 3c. Accessibility settings

Open them from the start screen: press **TAB**, click the **ACCESSIBILITY**
button in the top-right corner, or press DOWN to select it and ENTER. In the
menu: UP/DOWN to choose, LEFT/RIGHT (or ENTER, or a mouse click) to change,
ESC to go back. Changes show straight away, with a live preview of the colours,
and are saved to `settings.json` so they stick between games and reboots.

| Setting | Options | What it does |
|---|---|---|
| **Colour mode** | Standard, Red-green friendly, Blue-yellow friendly, High contrast | Swaps the whole palette. Red-green friendly makes right/wrong blue/orange and the walls amber; blue-yellow friendly makes right/wrong cyan/red and the boosted car white; high contrast uses plain black with white road edges and orange walls. |
| **Text size** | Normal, Large (120%), Extra large (140%) | Makes all reading text bigger -- questions, the HUD, menus, the run summary. Boxes resize to fit, and the answer banner stays up a little longer. |
| **Reduce flashing & effects** | Off / On | Turns off blinking prompts, the screen flash when you hit a wall, scanlines, glow and colour fringing. Good for anyone sensitive to flashing or who finds the effects distracting. |

Right and wrong never rely on colour alone: answers always show a **tick** or
**cross** as well as the words ACCESS GRANTED / ACCESS DENIED.

**How the colour modes were checked:** `cvd.py` simulates the three main types
of colour blindness (Machado et al., 2009) and `test_accessibility.py` checks
that the colours that matter -- right vs wrong, road edge vs wall, car vs
boosted car, grass vs road -- stay clearly different (delta-E 20 or more) for
the people each mode is for. The standard neon palette scores only about 21 for
road edge vs wall with deuteranopia (the most common type), which is why the
red-green mode exists; in that mode the smallest difference is 45.

## 3d. Levels

Every player races the same three tracks in the same order. The tracks are fixed
data in `track.py` (the `LEVELS` list), not generated at random, so every player
on every machine gets exactly the same layouts.

| Level | Track | Road width | Lap length | What makes it harder |
|---|---|---|---|---|
| 1 | NEON CIRCUIT | 96 px | 3,978 px | The original track: wide road, flowing corners |
| 2 | DATA DRIFT | 88 px | 2,826 px | Narrower road, one tight hairpin |
| 3 | FIREWALL | 80 px | 3,360 px | Narrowest road, chicanes all the way round |

Before each level an intro screen shows the level number, the track and your
time so far (ENTER to start, ESC to go back to the start screen). The HUD shows
LEVEL 2/3 during the race. After the third level, the player's totals are sent
to the scoreboard (section 6); a player who stops early sends nothing.

**Adding or changing a track:** edit `LEVELS` in `track.py`, then run
`python3 track.py`. It checks every level fits on screen, doesn't overlap
itself, has room for grass and walls, has drivable corners, starts on a
straight and counts laps correctly, and tells you which level failed and why.
If you change a track, scores on the scoreboard from before the change were set
on the old layout, so consider clearing the table.

## 3b. The track, walls and lap counting

**The circuit** is a closed spline through the `CONTROL_POINTS` list in `track.py`:
a long start/finish straight along the bottom, a fast sweeper, a chicane, a climb,
a hairpin at the top right, a dip along the top, an S-bend, and a big left-hander back
onto the straight. About 4,000px per lap, 96px wide.
Run `python3 track.py` after editing the points -- it fails if the road overlaps
itself, leaves the screen, or has a corner so tight the inside edge pinches shut.

**Grass and walls** go all the way round. Each side of the tarmac has a strip of
grass `GRASS_WIDTH` px wide (20px by default). It's drivable but slow. Behind the
grass is a hard wall: the car can't get past it, slides along it, loses some speed,
and "WALL!" flashes. Where two parts of the circuit run side by side, the grass
strips meet and a single wall runs between them, so you can't cut across. There's
also a wall round the edge of the screen as a backstop. To change how much grass
there is, edit `GRASS_WIDTH` in `track.py`. Then run `python3 track.py`, which
checks there's still room for grass and a wall between close sections and at the
screen edges.

**Laps** are counted with 16 ordered checkpoint gates around the circuit. A lap only
counts when the car crosses every gate in order and then the start line, so reversing
over the line, shunting back and forth on it, or cutting across the infield can't add
laps. Driving the wrong way round gives no laps either.

---

## 4. Hardware and software needed

- **Any joystick/gamepad with buttons**, connected via USB (or Bluetooth if
  paired as a standard HID controller). Standard USB flight-stick-style
  joysticks with at least 2 buttons work well (one for True, one for False).
  No special driver is needed — pygame reads any
  device the OS recognises as a joystick.
- **Raspberry Pi** (3B+ or newer recommended; a 4 handles the display more
  comfortably) running **Raspberry Pi OS**, with a monitor/TV attached (HDMI).
- Python 3.9+ and the packages in `requirements.txt`.

## 5. How the Raspberry Pi is used

The Pi is the whole game console here:
- It runs `main.py` directly — the Pi's own CPU/GPU renders the track, car,
  and question overlay via pygame/SDL, so there's no separate server or PC involved.
- The joystick plugs into one of the Pi's USB ports; pygame enumerates it as
  `Joystick(0)` automatically on boot of the script.
- When a player finishes, the Pi sends their score over the network (Wi-Fi or
  Ethernet) to the MySQL scoreboard database. It needs to be able to reach the
  MySQL server on its port (usually 3306).
- For a "kiosk" setup (e.g. at a school open day), you'd typically set
  `main.py` to auto-launch on boot (a systemd service or a line in
  `~/.config/lxsession/LXDE-pi/autostart`) so it's ready the moment the Pi
  powers on.

**Finding your joystick's exact button/axis numbers:** different controllers
number their buttons differently. Run this on the Pi with the joystick
plugged in:
```bash
python3 controls.py
```
It prints live axis and button values as you move the stick and press
buttons — use that to correct the `AXIS_STEER`, `AXIS_THROTTLE`,
`BUTTON_TRUE`, `BUTTON_FALSE` constants at the top of
`controls.py` if your device numbers them differently from the defaults.

---

## 6. The digital scoreboard (MySQL)

The scoreboard is shown on a **large external screen** for everyone to see, so
finished scores are sent to a MySQL database that the display reads. The game
itself keeps **no database**: there is no in-game leaderboard, so scores never
appear in two places.

**What's sent:** one row per player, when they finish **all three levels**. A
player who quits part-way (ESC) sends nothing.

| Column | Type | What the game puts in it | Example |
|---|---|---|---|
| `id` | auto increment | set by MySQL | 42 |
| `username` | VARCHAR(99) | the player's name (max 16 characters, cleaned) | `Reece` |
| `time` | VARCHAR(99) | total time over all three levels, as text | `174.52s` |
| `penalty` | VARCHAR(99) | total penalty seconds, as text | `+30s` |
| `correct` | TEXT | questions right / questions asked | `7/9` |
| `isshown` | INT | always `1` | `1` |

`time` and `penalty` are stored as **text**, formatted exactly as the game
shows them. To sort the scoreboard fastest-first, order by the number inside
the text, e.g. `ORDER BY CAST(REPLACE(time, 's', '') AS DECIMAL(10,2))`,
because sorting the text itself puts `99.00s` after `174.52s`.

**Setting it up:**
1. `pip install pymysql` (already in `requirements.txt`).
2. Fill in `scoreboard_config.json`: `host`, `port`, `user`, `password` and
   `table`. `database` can be left blank: the game then finds the database this
   user can see that holds the scoreboard table, and the check in step 3 prints
   its name (copy it in to skip the search). Set `"ssl": true` if your host
   requires encrypted connections.
3. Run `python3 scoreboard.py`. It connects, checks the table has every column
   and says how many rows it has. It sends nothing, so no test row appears on
   the big screen.

**After the last level** a RUN COMPLETE screen shows each level's result, the
TOTAL row exactly as sent, and whether it got there: SENDING..., ON THE
SCOREBOARD, SCOREBOARD OFFLINE -- WILL RETRY (with the reason), or SCOREBOARD
NOT SET UP.

**If the database can't be reached** (Wi-Fi down, wrong password), the game
carries on. Sending happens in the background, so the game never freezes, and
the score is kept in memory and sent again when the next player starts or
finishes. Scores still waiting are lost if the game is closed before the
connection comes back.

**Security:** the password lives only in `scoreboard_config.json`, never in the
code, so don't share or upload that file. Give the game its own MySQL user that
can only `INSERT` into the scoreboard table. Player names are sent as query
parameters, never pasted into the SQL, so nothing typed as a name can change the
query (SQL injection).

## 7. Cybersecurity questions (true/false)

30 questions live in `questions.py`, written for players **aged 8-18**: short
statements in plain language (no jargon), on things young people actually come
across online -- passwords, scams and fake messages, strangers and oversharing,
downloads and viruses, and telling a trusted adult when something's wrong.
There are 15 True and 15 False, so just pressing the same button every time
doesn't pay off.

Each question has a one-line explanation, shown under the ACCESS GRANTED /
ACCESS DENIED message after answering, so players learn something even when
they get it wrong. `QuestionDeck` shuffles through the whole pool before
repeating any question.

To add more, append to the `QUESTIONS` list and run `python3 questions.py` --
it checks each question is short enough (72 characters max), the explanation
fits (80 max), and the True/False mix stays balanced.

## 8. Data: what's collected, how it's processed, stored, and shared

**Collected**, once per player who finishes all three levels:
- Player name (typed in at the start; capped at 16 characters, non-printable
  characters stripped)
- Total time over the three levels (driving plus penalties)
- Total penalty seconds (10s per wrong answer)
- Questions answered correctly / total asked (e.g. `7/9`)

**Processed:** on the device, in memory, while the race is running. Lap count,
timer and penalties are computed locally frame by frame. Nothing is sent
during play.

**Stored:** in the **MySQL scoreboard database** only, as one row per finished
player (section 6). The game keeps no database or file of results on the
device. The accessibility settings are saved separately in `settings.json`:
just the three choices, nothing personal.

**Shared:** the name and score are sent over the network to the MySQL server,
and shown on the big-screen scoreboard to everyone in the room. Players should
know that before they type their name.

**Privacy note (players aged 8-18):** names leave the device and are shown in
public, so ask players to use a first name or nickname, and sign-post this at
the kiosk. Use `isshown = 0` to hide a row from the display (e.g. an
inappropriate name) without deleting it, and clear the table after a public
event. Under UK GDPR, a name tied to a score is personal data: keep it only as
long as the event needs it.

---

## 9. What I'd extend first

Roughly in order of "most bang for the least effort":

1. **Difficulty scaling / question categories.** Split the question bank into
   easy/medium/hard, and get harder as laps progress, or let the player pick a
   category (passwords, phishing, malware, network basics) at the name-entry screen.
2. **A countdown and a rolling-start timer**, so the clock starts at "GO" and the
   grid has a proper lights sequence.
3. **A second car (AI ghost or 2-player)** using a second joystick -- `controls.py`
   already works with `Joystick(0)`; accept an index to support `Joystick(1)`.
4. **Keep unsent scores across restarts** -- write the scoreboard's waiting
   queue to a small file, so a score survives the game being closed while the
   network is down.
5. **Sound** -- engine hum, a "access granted / denied" chime, and a synth soundtrack.
