"""One-off script to render the GuardianPD launcher icon assets.

Not part of the app build — run once to produce icon.png (legacy/full-bleed,
purple background baked in) and icon_foreground.png (transparent, for the
Android adaptive icon), which flutter_launcher_icons then expands into every
mipmap size. Shield = guardian/protection; "PD" = GuardianPD.
"""

import math

from PIL import Image, ImageDraw, ImageFont

SIZE = 1024
PURPLE = (106, 79, 224, 255)  # #6A4FE0 — matches the in-app button color
WHITE = (255, 255, 255, 255)
TRANSPARENT = (0, 0, 0, 0)


def arc_points(center, radius, start_deg, end_deg, steps=16):
    pts = []
    for i in range(steps + 1):
        a = math.radians(start_deg + (end_deg - start_deg) * i / steps)
        pts.append((center[0] + radius * math.cos(a), center[1] + radius * math.sin(a)))
    return pts


def quad_bezier(p0, p1, p2, steps=16):
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1]
        pts.append((x, y))
    return pts


def shield_points(cx, cy, w, h):
    left, right, top = cx - w / 2, cx + w / 2, cy - h / 2
    corner_r = w * 0.14

    pts = []
    tl_c = (left + corner_r, top + corner_r)
    pts += arc_points(tl_c, corner_r, 180, 270)
    tr_c = (right - corner_r, top + corner_r)
    pts += arc_points(tr_c, corner_r, 270, 360)

    right_mid = (right, cy + h * 0.08)
    pts.append(right_mid)
    bottom_pt = (cx, cy + h / 2)
    pts += quad_bezier(right_mid, (right - w * 0.02, cy + h * 0.34), bottom_pt, steps=16)
    left_mid = (left, cy + h * 0.08)
    pts += quad_bezier(bottom_pt, (left + w * 0.02, cy + h * 0.34), left_mid, steps=16)
    return pts


def make_icon(with_background: bool, path: str) -> None:
    img = Image.new("RGBA", (SIZE, SIZE), PURPLE if with_background else TRANSPARENT)
    draw = ImageDraw.Draw(img)
    cx, cy = SIZE / 2, SIZE / 2 - SIZE * 0.01
    shield_w, shield_h = SIZE * 0.52, SIZE * 0.60

    pts = shield_points(cx, cy, shield_w, shield_h)
    draw.polygon(pts, fill=WHITE)

    text = "PD"
    font_size = int(shield_w * 0.46)
    font = ImageFont.truetype("arialbd.ttf", font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    text_pos = (cx - text_w / 2 - bbox[0], cy - text_h / 2 - bbox[1] - shield_h * 0.03)
    draw.text(text_pos, text, fill=PURPLE, font=font)

    img.save(path)


make_icon(True, "icon.png")
make_icon(False, "icon_foreground.png")
print("wrote icon.png + icon_foreground.png")
