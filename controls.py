"""
Input abstraction over pygame.

On a Raspberry Pi with a USB joystick plugged in, pygame.joystick picks it up
automatically (no extra config needed for a standard HID gamepad/joystick).
This module reads from it if present; otherwise it falls back to the keyboard
so you can develop and test on a laptop with no hardware attached.

Mapping (adjust AXIS/BUTTON indices to match your exact joystick -- run
`python3 controls.py` to print raw axis/button values and find the right
numbers for your device):

    Steering   -> joystick axis 0 (left stick X)   | keyboard LEFT/RIGHT or A/D
    Throttle   -> joystick axis 1 (left stick Y)    | keyboard UP/DOWN or W/S
    Answer T   -> joystick button 1                 | keyboard T
    Answer F   -> joystick button 2                 | keyboard F
    Pause/quit -> joystick button 9 (start, if any)  | keyboard ESC
"""
import pygame

AXIS_STEER = 0
AXIS_THROTTLE = 1
BUTTON_TRUE = 1
BUTTON_FALSE = 2
DEADZONE = 0.15


class Controls:
    def __init__(self):
        pygame.joystick.init()
        self.joystick = None
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
        self._true_pressed_last = False
        self._false_pressed_last = False

    @property
    def has_joystick(self):
        return self.joystick is not None

    def _axis(self, index, default=0.0):
        if self.joystick is None:
            return default
        try:
            value = self.joystick.get_axis(index)
        except pygame.error:
            return default
        return value if abs(value) > DEADZONE else 0.0

    def _button(self, index):
        if self.joystick is None:
            return False
        try:
            return bool(self.joystick.get_button(index))
        except pygame.error:
            return False

    def get_drive_input(self):
        """Returns (throttle, steer), each in [-1, 1]."""
        keys = pygame.key.get_pressed()

        if self.joystick is not None:
            steer = self._axis(AXIS_STEER)
            throttle = -self._axis(AXIS_THROTTLE)  # most sticks report "up" as negative
        else:
            steer = 0.0
            throttle = 0.0

        # Keyboard always works too, so it can supplement or fully replace the joystick.
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            steer = -1.0
        elif keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            steer = 1.0
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            throttle = 1.0
        elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
            throttle = -1.0

        return throttle, steer

    # Questions pop up automatically at the end of each lap; these answer them.
    # Edge-triggered: True only on the frame the button/key goes down.
    def true_pressed(self):
        keys = pygame.key.get_pressed()
        pressed_now = self._button(BUTTON_TRUE) or keys[pygame.K_t]
        edge = pressed_now and not self._true_pressed_last
        self._true_pressed_last = pressed_now
        return edge

    def false_pressed(self):
        keys = pygame.key.get_pressed()
        pressed_now = self._button(BUTTON_FALSE) or keys[pygame.K_f]
        edge = pressed_now and not self._false_pressed_last
        self._false_pressed_last = pressed_now
        return edge


if __name__ == "__main__":
    # Diagnostic tool: run this on the Pi with the joystick plugged in to see
    # live axis/button numbers, so you can correct AXIS_*/BUTTON_* above if
    # your controller maps them differently.
    pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        print("No joystick detected. Plug one in via USB and re-run this file.")
    else:
        js = pygame.joystick.Joystick(0)
        js.init()
        print(f"Found: {js.get_name()}")
        print(f"Axes: {js.get_numaxes()}  Buttons: {js.get_numbuttons()}")
        print("Move the stick / press buttons -- Ctrl+C to stop.")
        clock = pygame.time.Clock()
        try:
            while True:
                pygame.event.pump()
                axes = [round(js.get_axis(i), 2) for i in range(js.get_numaxes())]
                buttons = [js.get_button(i) for i in range(js.get_numbuttons())]
                print(f"\raxes={axes} buttons={buttons}   ", end="", flush=True)
                clock.tick(15)
        except KeyboardInterrupt:
            print("\nStopped.")
