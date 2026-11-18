"""Hi-fi skin assets for PotentialBox.

Everything here is drawn with numpy + Pillow at run time and cached by the caller, so there are no image files to
ship and nothing to keep in sync. If Pillow is missing the app falls back to its plain vector drawing.
"""
from __future__ import annotations

import numpy as np

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageChops
    HAVE = True
except Exception:  # Pillow not installed: the app still runs, just flat
    HAVE = False

SS = 3          # supersampling for the sprites
KEY_MARGIN = 3  # px of transparent surround round a key sprite, for its drop shadow


def rgb(c):
    c = str(c).lstrip("#")
    return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def knob(size, face, hi, ring, spec=1.0, shadow=True):
    """A round encoder as an RGBA image `size` px across (plus a little margin for its shadow)."""
    if not HAVE:
        return None
    n = max(10, int(size * SS))
    R = n / 2.0
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    dx = (x + 0.5 - R) / R
    dy = (y + 0.5 - R) / R
    d = np.sqrt(dx * dx + dy * dy)

    base, light, rim_col = rgb(face), rgb(hi), rgb(ring)
    z = np.sqrt(np.clip(1.0 - d * d, 0.0, 1.0))
    lam = np.clip(dx * -0.42 + dy * -0.52 + z * 0.95, 0.0, 1.6)     # light from the top left
    radial = np.clip(1.0 - d, 0.0, 1.0) ** 0.85
    col = base + (light - base) * (0.14 + 0.52 * radial)[..., None]
    col *= (0.62 + 0.52 * lam)[..., None]
    # tight specular highlight, a touch above the hub
    sp = np.exp(-(((dx + 0.30) ** 2 + (dy + 0.38) ** 2) / (2 * 0.16 ** 2)))
    col += sp[..., None] * (44.0 * spec)
    # edge falloff and a thin bezel ring
    edge = np.clip((d - 0.78) / 0.22, 0.0, 1.0)
    col *= (1.0 - 0.42 * edge)[..., None]
    col[d > 0.963] = rim_col
    alpha = (d <= 1.0).astype(np.float32) * 255.0

    arr = np.dstack([np.clip(col, 0, 255), alpha]).astype(np.uint8)
    body = Image.fromarray(arr, "RGBA").resize((int(size), int(size)), Image.LANCZOS)
    if not shadow:
        return body
    margin = int(size * 0.24)
    total = int(size) + margin * 2
    out = Image.new("RGBA", (total, total), (0, 0, 0, 0))
    sh = Image.new("RGBA", (total, total), (0, 0, 0, 0))
    off = int(size * 0.075)
    ImageDraw.Draw(sh).ellipse([margin - 1, margin + off, margin + size + 1, margin + size + off],
                               fill=(0, 0, 0, 140))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(max(1.0, size * 0.055))))
    out.alpha_composite(body, (margin, margin))
    return out


def pointer(size, color, angle_deg, hub=0.18, width=0.17):
    """The cream pointer + hub, pre-rotated. `angle_deg` is clockwise from 12 o'clock."""
    if not HAVE:
        return None
    n = max(10, int(size * SS))
    R = n / 2.0
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w0 = R * width
    d.polygon([(R - w0 * 0.5, R - R * 0.10), (R + w0 * 0.5, R - R * 0.10),
               (R + w0 * 0.30, R - R * 0.86), (R - w0 * 0.30, R - R * 0.86)], fill=color)
    hr = R * hub
    d.ellipse([R - hr, R - hr, R + hr, R + hr], fill=color)
    img = img.rotate(-angle_deg, resample=Image.BICUBIC, center=(R, R))
    return img.resize((int(size), int(size)), Image.LANCZOS)


def key(w, h, radius, fill, outline=None, light=1.13, dark=0.84):
    """A moulded plastic key: soft drop shadow, vertical gradient, lit top edge, shaded bottom edge.

    The returned image is KEY_MARGIN px larger than w x h on every side; draw it at (x - KEY_MARGIN, y - KEY_MARGIN).
    """
    if not HAVE:
        return None
    ss = 2
    W, H = max(2, int(round(w)) * ss), max(2, int(round(h)) * ss)
    R = max(0.0, min(float(radius) * ss, W / 2.0, H / 2.0))
    M = KEY_MARGIN * ss
    tw, th = W + M * 2, H + M * 2
    base = rgb(fill)

    # body: a vertical gradient through a rounded-rect mask
    t = np.linspace(0.0, 1.0, H, dtype=np.float32)[:, None, None]
    grad = base * light * (1.0 - t) + base * dark * t
    grad = np.repeat(grad, W, axis=1)
    body = Image.fromarray(np.dstack([np.clip(grad, 0, 255), np.full((H, W), 255.0)]).astype(np.uint8), "RGBA")
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=R, fill=255)
    body.putalpha(mask)

    out = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    off = max(1, int(round(2.0 * ss)))
    sh = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([M, M + off, M + W - 1, M + H - 1 + off], radius=R, fill=(0, 0, 0, 105))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(max(1.0, 1.5 * ss))))
    out.alpha_composite(body, (M, M))

    lw = max(1, ss)
    lite = tuple(int(v) for v in np.clip(base * 1.55 + 18, 0, 255)) + (255,)
    darkc = tuple(int(v) for v in np.clip(base * 0.52, 0, 255)) + (255,)
    box = [M, M, M + W - 1, M + H - 1]
    inner = [M + lw, M + lw, M + W - 1 - lw, M + H - 1 - lw]

    def band(colour, y0, y1):
        layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle(inner, radius=max(0.0, R - lw), outline=colour, width=lw)
        clip = Image.new("L", (tw, th), 0)
        ImageDraw.Draw(clip).rectangle([0, y0, tw, y1], fill=255)
        layer.putalpha(ImageChops.multiply(layer.getchannel("A"), clip))
        out.alpha_composite(layer)

    split = M + int(H * 0.52)
    band(lite, 0, split)                    # light catches the top edge
    band(darkc, split, th)                  # shadow along the bottom edge
    ImageDraw.Draw(out).rounded_rectangle(box, radius=R, outline=darkc, width=lw)
    if outline:
        oc = tuple(int(v) for v in rgb(outline)) + (255,)
        ImageDraw.Draw(out).rounded_rectangle([M - 1, M - 1, M + W, M + H], radius=R, outline=oc, width=max(1, ss))
    return out.resize((int(round(w)) + KEY_MARGIN * 2, int(round(h)) + KEY_MARGIN * 2), Image.LANCZOS)


def screen(w, h, glass, scan=True):
    """A display window: dark glass with a soft centre glow, faint scanlines and a bevelled inner edge."""
    if not HAVE:
        return None
    w, h = max(4, int(round(w))), max(4, int(round(h)))
    base = rgb(glass)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    u = (x / max(1.0, w - 1) - 0.5) * 2.0
    v = (y / max(1.0, h - 1) - 0.5) * 2.0
    glow = np.clip(1.0 - (u * u * 0.55 + v * v * 0.75), 0.0, 1.0) ** 1.4
    col = base[None, None, :] * (0.92 + 0.70 * glow)[..., None]
    col += np.array([7.0, 24.0, 13.0], dtype=np.float32)[None, None, :] * glow[..., None]
    if scan:
        lines = (np.arange(h, dtype=np.float32) % 3.0) < 1.0
        col *= (1.0 - 0.055 * lines.astype(np.float32))[:, None, None]
    # inner shadow along the top and sides, like glass set into a bezel
    edge = np.minimum.reduce([x, y, w - 1 - x, h - 1 - y]).astype(np.float32)
    col *= (0.62 + 0.38 * np.clip(edge / 4.0, 0.0, 1.0))[..., None]
    arr = np.dstack([np.clip(col, 0, 255), np.full((h, w), 255.0)]).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def _wood(w, h, base_hex, seed, vertical=True):
    """A grain tile: sinusoidal figure plus fine noise, shaded darker at the outer edge."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    t = x if vertical else y          # grain runs along the long axis of the band
    grain = (np.sin(t / 3.5 + 1.3) * 0.45 + np.sin(t / 9.0 + 4.1) * 0.32
             + np.sin(t / 26.0 + 2.2) * 0.23)
    grain += rng.normal(0.0, 0.05, (h, w))
    v = np.clip(0.80 + 0.34 * grain, 0.52, 1.28)[..., None]
    col = rgb(base_hex)[None, None, :] * v
    return np.dstack([np.clip(col, 0, 255), np.full((h, w), 255.0)]).astype(np.uint8)


def cabinet(w, h, band, wood_hex, wood_dark, panel_top, panel_bot, accent_hex):
    """The whole window backdrop: walnut cabinet, brushed plate inside, pinstripe."""
    if not HAVE:
        return None
    w, h, band = int(w), int(h), max(1, int(band))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    # cheeks (vertical grain) then rails (horizontal grain)
    img.paste(Image.fromarray(_wood(w, h, wood_hex, 11), "RGBA"), (0, 0))
    strip_w = 1200
    rail_top = Image.fromarray(_wood(strip_w, band, wood_hex, 3, vertical=False), "RGBA")
    for x0 in range(0, w, strip_w):
        img.paste(rail_top, (x0, 0))
        img.paste(rail_top, (x0, h - band))
    # darken the outer edge of the cabinet
    edge = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ed = ImageDraw.Draw(edge)
    for i in range(band):
        a = int(120 * (1 - i / max(1, band)))
        ed.rectangle([i, i, w - 1 - i, h - 1 - i], outline=(20, 12, 6, a))
    img.alpha_composite(edge)

    # brushed plate
    pw, ph = w - band * 2, h - band * 2
    if pw > 4 and ph > 4:
        top, bot = rgb(panel_top), rgb(panel_bot)
        t = np.linspace(0.0, 1.0, ph, dtype=np.float32)[:, None, None]
        plate = (top[None, None, :] * (1 - t) + bot[None, None, :] * t) + 0.5
        plate = np.repeat(plate, pw, axis=1)
        rng = np.random.default_rng(5)
        plate += rng.normal(0.0, 1.6, (ph, pw, 1))
        # faint horizontal brushing
        brush = (np.sin(np.arange(ph, dtype=np.float32)[:, None] * 2.1) * 0.8)[..., None]
        plate += brush
        arr = np.dstack([np.clip(plate, 0, 255), np.full((ph, pw), 255.0)]).astype(np.uint8)
        img.paste(Image.fromarray(arr, "RGBA"), (band, band))
        d = ImageDraw.Draw(img)
        d.rectangle([band, band, w - band - 1, h - band - 1], outline=(16, 12, 8, 255), width=2)
        d.line([band, h - band - 4, w - band, h - band - 4], fill=accent_hex, width=2)
    return img
