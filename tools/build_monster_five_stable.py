from __future__ import annotations

import colorsys
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "04_concepts/work/MONSTER_30_CATALOG/variants"
OUT = ROOT / "05_sprites/work/MONSTER_5_STABLE"
FAMILIES = ("INFANTRY", "BEAST", "WRAITH", "HEAVY", "GIANT")
MOTIONS = ("run", "hit", "attack")
SHEET = 1024
CELL = 256
AXIS_X = 128
BASELINE = 224
FPS = 6


def alpha_bbox(image: Image.Image, threshold: int = 16) -> tuple[int, int, int, int]:
    result = image.getchannel("A").point(lambda value: 255 if value >= threshold else 0).getbbox()
    if result is None:
        raise ValueError("empty sprite")
    return result


def alpha_center_x(image: Image.Image, threshold: int = 200) -> float:
    alpha = image.getchannel("A")
    pixels = alpha.load()
    total = weighted = 0.0
    for y in range(image.height):
        for x in range(image.width):
            value = pixels[x, y]
            if value < threshold:
                continue
            total += value
            weighted += x * value
    return weighted / total if total else image.width / 2


def prepare(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    image = image.crop(alpha_bbox(image))
    scale = min(160 / image.width, 160 / image.height)
    image = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    return image.crop(alpha_bbox(image))


def color() -> tuple[int, int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(0.76, 0.82, 1.0)
    return round(r * 255), round(g * 255), round(b * 255), 180


def body_frame(sprite: Image.Image) -> Image.Image:
    frame = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
    x = round(AXIS_X - alpha_center_x(sprite, 16))
    frame.alpha_composite(sprite, (x, BASELINE - sprite.height))
    return frame


def make_frame(base: Image.Image, motion: str, index: int) -> Image.Image:
    frame = base.copy()
    effect = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
    draw = ImageDraw.Draw(effect)
    accent = color()
    phase = 2 * math.pi * index / 16
    if motion == "run":
        pulse = abs(math.sin(phase * 2))
        if pulse > 0.08:
            radius = round(3 + 5 * pulse)
            for x in (AXIS_X - 25, AXIS_X + 25):
                draw.ellipse((x - radius, BASELINE - 7 - radius // 2, x + radius, BASELINE - 7 + radius // 2), fill=(*accent[:3], round(75 * pulse)))
    elif motion == "hit":
        flash = (0, 0, .15, .45, .8, .5, .28, .12, 0, 0, 0, 0, 0, 0, 0, 0)[index]
        if flash:
            overlay = Image.new("RGBA", frame.size, (255, 85, 95, 255))
            tinted = Image.blend(frame, overlay, flash * .55)
            tinted.putalpha(frame.getchannel("A"))
            frame = tinted
            draw.arc((76, 72, 180, 176), 205, 335, fill=(255, 220, 220, round(220 * flash)), width=4)
    else:
        swing = (0, .1, .2, .35, .55, .8, 1, .72, .4, .18, 0, 0, 0, 0, 0, 0)[index]
        if swing:
            inset = round(10 * (1 - swing))
            draw.arc((44 + inset, 44 + inset, 212 - inset, 212 - inset), 210, 338, fill=(*accent[:3], round(210 * swing)), width=5)
    frame.alpha_composite(effect)
    return frame


def metrics(frames: list[Image.Image], body: Image.Image) -> dict:
    # Effects are intentionally translucent. A near-opaque threshold isolates
    # the monster body so an attack arc cannot masquerade as body scaling.
    body_bounds = alpha_bbox(body, 250)
    centers = [alpha_center_x(frame, 250) for frame in frames]
    opaque_bounds = [alpha_bbox(frame, 250) for frame in frames]
    heights = [item[3] - item[1] for item in opaque_bounds]
    baselines = [item[3] for item in opaque_bounds]
    full_bounds = [alpha_bbox(frame) for frame in frames]
    report = {
        "status": "PASS",
        "mass_center_x_range_px": round(max(centers) - min(centers), 4),
        "baseline_range_px": max(baselines) - min(baselines),
        "height_variation_percent": round((max(heights) - min(heights)) / max(1, sum(heights) / len(heights)) * 100, 4),
        "minimum_safe_margin": min(min(b[0], b[1], CELL - b[2], CELL - b[3]) for b in full_bounds),
        "body_bbox": list(body_bounds),
        "frames": 16,
        "fps": FPS,
    }
    if report["mass_center_x_range_px"] > .25 or report["baseline_range_px"] or report["height_variation_percent"] > 2 or report["minimum_safe_margin"] < 32:
        report["status"] = "FAIL"
    return report


def save_gif(frames: list[Image.Image], path: Path) -> None:
    backdrop = Image.new("RGBA", (CELL, CELL), (34, 38, 48, 255))
    previews = []
    for frame in frames:
        image = backdrop.copy()
        image.alpha_composite(frame)
        previews.append(image.convert("P", palette=Image.Palette.ADAPTIVE))
    previews[0].save(path, save_all=True, append_images=previews[1:], duration=167, loop=0, disposal=2)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    entries = []
    for family in FAMILIES:
        monster_id = f"MON_{family}_ABYSS_V01"
        sprite = prepare(SOURCE_ROOT / f"{monster_id}.png")
        body = body_frame(sprite)
        target = OUT / monster_id
        target.mkdir(parents=True, exist_ok=True)
        for motion in MOTIONS:
            frames = [make_frame(body, motion, index) for index in range(16)]
            sheet = Image.new("RGBA", (SHEET, SHEET), (0, 0, 0, 0))
            for index, frame in enumerate(frames):
                sheet.alpha_composite(frame, ((index % 4) * CELL, (index // 4) * CELL))
            sheet_path = target / f"{monster_id}_{motion}_16f_4x4_stable.png"
            gif_path = target / f"{monster_id}_{motion}_6fps_stable.gif"
            qa_path = target / f"{monster_id}_{motion}_strict_qa.json"
            sheet.save(sheet_path, "PNG", optimize=True)
            save_gif(frames, gif_path)
            qa = metrics(frames, body)
            qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
            entries.append({
                "asset_id": f"{monster_id}_{motion.upper()}_STABLE_V01",
                "monster_id": monster_id,
                "family": family,
                "palette": "ABYSS",
                "motion": motion,
                "sheet_path": sheet_path.relative_to(ROOT).as_posix(),
                "gif_path": gif_path.relative_to(ROOT).as_posix(),
                "qa_path": qa_path.relative_to(ROOT).as_posix(),
                "checksum": "sha256:" + hashlib.sha256(sheet_path.read_bytes()).hexdigest(),
                "qa": qa,
            })
    manifest = {"bundle_id": "MONSTER_5_STABLE_V01", "monster_count": 5, "sheet_count": 15, "motions": list(MOTIONS), "fps": 6, "all_qa_pass": all(item["qa"]["status"] == "PASS" for item in entries), "entries": entries}
    (OUT / "MONSTER_5_STABLE_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"monster_count": 5, "sheet_count": 15, "all_qa_pass": manifest["all_qa_pass"], "max_center_drift": max(item["qa"]["mass_center_x_range_px"] for item in entries), "max_height_variation": max(item["qa"]["height_variation_percent"] for item in entries)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
