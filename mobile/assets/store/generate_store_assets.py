"""One-off script to render Play Console store-listing assets — the
512x512 high-res icon and the 1024x500 feature graphic. Neither ships in
the app itself (unlike assets/icon/), they're just uploaded once to Play
Console. Reuses the same shield+PD mark and brand purple as the real
launcher icon (assets/icon/generate_icon.py) for visual consistency.
"""

import math
import os

from PIL import Image, ImageDraw, ImageFont

PURPLE = (106, 79, 224, 255)  # #6A4FE0
WHITE = (255, 255, 255, 255)

_ICON_SOURCE = os.path.join(os.path.dirname(__file__), "..", "icon", "icon.png")


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


def draw_shield_pd(draw, cx, cy, size, purple=PURPLE):
    shield_w, shield_h = size * 0.68, size * 0.78
    pts = shield_points(cx, cy, shield_w, shield_h)
    draw.polygon(pts, fill=WHITE)

    font = ImageFont.truetype("arialbd.ttf", int(shield_w * 0.46))
    text = "PD"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pos = (cx - text_w / 2 - bbox[0], cy - text_h / 2 - bbox[1] - shield_h * 0.03)
    draw.text(pos, text, fill=purple, font=font)


def make_high_res_icon(path: str) -> None:
    img = Image.open(_ICON_SOURCE).convert("RGB").resize((512, 512), Image.LANCZOS)
    img.save(path)


def make_feature_graphic(path: str) -> None:
    W, H = 1024, 500
    img = Image.new("RGB", (W, H), PURPLE[:3])
    draw = ImageDraw.Draw(img)

    badge_cx, badge_cy, badge_size = 190, H / 2, 260
    draw_shield_pd(draw, badge_cx, badge_cy, badge_size)

    title_font = ImageFont.truetype("arialbd.ttf", 72)
    tagline_font = ImageFont.truetype("arial.ttf", 30)

    text_x = 370
    draw.text((text_x, 175), "GuardianPD", fill=WHITE, font=title_font)
    draw.text((text_x, 275), "Secure QR-based school", fill=WHITE, font=tagline_font)
    draw.text((text_x, 315), "pickup & drop-off attendance", fill=WHITE, font=tagline_font)

    img.save(path)


if __name__ == "__main__":
    out_dir = os.path.dirname(__file__)
    make_high_res_icon(os.path.join(out_dir, "play_store_icon.png"))
    make_feature_graphic(os.path.join(out_dir, "feature_graphic.png"))
    print("wrote play_store_icon.png + feature_graphic.png")
