"""
Colour-blindness simulation, used to check the colour modes in theme.py.

Uses the Machado, Oliveira & Fernandes (2009) model at full severity for the three
types of colour blindness, then measures how different two colours look (CIE76
delta-E in Lab space: ~2 is barely noticeable, 20+ is clearly different).
No pygame needed.
"""
MATRICES = {
    "normal": None,
    "protan": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "deutan": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "tritan": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602), (0.004733, 0.691367, 0.303900)),
}


def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gamma(c):
    c = max(0.0, min(1.0, c))
    return 255 * (12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055)


def simulate(rgb, kind):
    m = MATRICES[kind]
    if m is None:
        return tuple(rgb)
    lin = [_lin(v) for v in rgb]
    return tuple(_gamma(sum(m[r][k] * lin[k] for k in range(3))) for r in range(3))


def to_lab(rgb):
    r, g, b = (_lin(v) for v in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a, b):
    la, lb = to_lab(a), to_lab(b)
    return sum((la[i] - lb[i]) ** 2 for i in range(3)) ** 0.5


def seen_difference(a, b, kind):
    return delta_e(simulate(a, kind), simulate(b, kind))
