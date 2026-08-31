from __future__ import annotations

import colorsys
import json
import math
from pathlib import Path
from statistics import mean

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = ROOT / "04_concepts/work/MONSTER_30_CATALOG"
OUT = ROOT / "05_sprites/work/MONSTER_30_ANIMATIONS"
SHEET = 1024
CELL = 256
GRID = 4
SAFE_MIN = 32
SAFE_MAX = 224
AXIS_X = 128
BASELINE = 224
FPS = 6


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    bbox = image.getchannel("A").point(lambda value: 255 if value >= 16 else 0).getbbox()
    if bbox is None:
        raise ValueError("empty frame")
    return bbox


def alpha_center_x(image: Image.Image) -> float:
    alpha = image.getchannel("A")
    pixels = alpha.load()
    total = weighted = 0
    for y in range(image.height):
        for x in range(image.width):
            value = pixels[x, y]
            if value >= 16:
                total += value
                weighted += x * value
    return weighted / total if total else AXIS_X


def accent_color(palette: str) -> tuple[int, int, int, int]:
    hues = {"ABYSS": 0.76, "EMBER": 0.02, "FROST": 0.56, "VENOM": 0.29, "GOLD": 0.13, "BLOOD": 0.90}
    r, g, b = colorsys.hsv_to_rgb(hues[palette], 0.88, 1.0)
    return round(r * 255), round(g * 255), round(b * 255), 180


def prepare_source(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    crop = image.crop(alpha_bbox(image))
    # Reserve asymmetric head/weapon room so the visual mass axis can sit at
    # x=128 without violating the 32px cell safety margin.
    scale = min(160 / crop.width, 160 / crop.height)
    crop = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.Resampling.LANCZOS)
    return crop.crop(alpha_bbox(crop))


def motion_parameters(motion: str, frame: int) -> tuple[float, float]:
    phase = 2 * math.pi * frame / 16
    if motion == "run":
        return 1.0 + 0.025 * math.sin(phase * 2), 0.0
    if motion == "hit":
        recoil = [0, 0, 0, 0.01, 0.035, 0.06, 0.075, 0.055, 0.035, 0.02, 0.01, 0, 0, 0, 0, 0][frame]
        return 1.0 - recoil, recoil
    charge = [0, 0.005, 0.01, 0.018, 0.025, 0.015, -0.02, -0.045, -0.055, -0.035, -0.02, -0.01, 0, 0, 0, 0][frame]
    return 1.0 - charge, max(0.0, -charge)


def tint_hit(sprite: Image.Image, strength: float) -> Image.Image:
    if strength <= 0:
        return sprite
    overlay = Image.new("RGBA", sprite.size, (255, 100, 100, 255))
    tinted = Image.blend(sprite, overlay, min(0.55, strength * 6.5))
    tinted.putalpha(sprite.getchannel("A"))
    return tinted


def make_frame(source: Image.Image, motion: str, index: int, palette: str) -> tuple[Image.Image, Image.Image]:
    scale_y, intensity = motion_parameters(motion, index)
    sprite = source.resize((source.width, max(1, round(source.height * scale_y))), Image.Resampling.LANCZOS)
    sprite = sprite.crop(alpha_bbox(sprite))
    if motion == "hit":
        sprite = tint_hit(sprite, intensity)

    body = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
    body.alpha_composite(sprite, (round(AXIS_X - alpha_center_x(sprite)), BASELINE - sprite.height))
    frame = body.copy()
    effect = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
    draw = ImageDraw.Draw(effect)
    color = accent_color(palette)

    if motion == "run":
        puff = abs(math.sin(2 * math.pi * index / 8))
        if puff > 0.18:
            radius = round(4 + 5 * puff)
            y = BASELINE - 8
            draw.ellipse((AXIS_X - 25 - radius, y - radius // 2, AXIS_X - 25 + radius, y + radius // 2), fill=(*color[:3], round(70 * puff)))
            draw.ellipse((AXIS_X + 25 - radius, y - radius // 2, AXIS_X + 25 + radius, y + radius // 2), fill=(*color[:3], round(70 * puff)))
    elif motion == "attack" and intensity > 0:
        radius = round(42 + intensity * 420)
        radius = min(76, radius)
        alpha = round(min(170, 80 + intensity * 1400))
        draw.ellipse((AXIS_X - radius, 128 - radius, AXIS_X + radius, 128 + radius), outline=(*color[:3], alpha), width=4)

    frame.alpha_composite(effect)
    return frame, body


def build_sheet(source: Image.Image, motion: str, palette: str) -> tuple[Image.Image, list[Image.Image], dict]:
    frames = []
    body_frames = []
    for index in range(16):
        frame, body = make_frame(source, motion, index, palette)
        frames.append(frame)
        body_frames.append(body)

    sheet = Image.new("RGBA", (SHEET, SHEET), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        sheet.alpha_composite(frame, ((index % GRID) * CELL, (index // GRID) * CELL))

    centers = [alpha_center_x(body) for body in body_frames]
    body_bounds = [alpha_bbox(body) for body in body_frames]
    full_bounds = [alpha_bbox(frame) for frame in frames]
    baseline_values = [bounds[3] for bounds in body_bounds]
    widths = [bounds[2] - bounds[0] for bounds in full_bounds]
    heights = [bounds[3] - bounds[1] for bounds in full_bounds]
    margins = [min(bounds[0], bounds[1], CELL - bounds[2], CELL - bounds[3]) for bounds in full_bounds]
    qa = {
        "status": "PASS",
        "sheet": [SHEET, SHEET],
        "grid": [GRID, GRID],
        "cell": [CELL, CELL],
        "frames": 16,
        "fps": FPS,
        "mode": "RGBA",
        "body_center_x_range_px": round(max(centers) - min(centers), 4),
        "body_center_x_average": round(mean(centers), 4),
        "baseline_range_px": max(baseline_values) - min(baseline_values),
        "max_frame_width": max(widths),
        "max_frame_height": max(heights),
        "minimum_safe_margin": min(margins),
        "cell_invasion": False,
    }
    qa["status"] = "PASS" if (
        qa["body_center_x_range_px"] <= 0.25
        and qa["baseline_range_px"] == 0
        and qa["max_frame_width"] <= 192
        and qa["max_frame_height"] <= 192
        and qa["minimum_safe_margin"] >= 32
    ) else "FAIL"
    return sheet, frames, qa


def gif_preview(frames: list[Image.Image], path: Path) -> None:
    backdrop = Image.new("RGBA", (CELL, CELL), (34, 38, 48, 255))
    previews = []
    for frame in frames:
        image = backdrop.copy()
        image.alpha_composite(frame)
        previews.append(image.convert("P", palette=Image.Palette.ADAPTIVE))
    previews[0].save(path, save_all=True, append_images=previews[1:], duration=167, loop=0, disposal=2)


def main() -> None:
    manifest = json.loads((CATALOG_ROOT / "MONSTER_30_MANIFEST.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    output_entries = []
    motion_previews: dict[str, list[Image.Image]] = {motion: [Image.new("RGB", (768, 640), (18, 21, 28)) for _ in range(16)] for motion in ("run", "hit", "attack")}

    for asset_index, entry in enumerate(manifest["entries"]):
        source = prepare_source(ROOT / entry["file_path"])
        asset_dir = OUT / entry["asset_id"]
        asset_dir.mkdir(parents=True, exist_ok=True)
        for motion in ("run", "hit", "attack"):
            sheet, frames, qa = build_sheet(source, motion, entry["palette"])
            stem = f"{entry['asset_id']}_{motion}_16f_4x4"
            sheet_path = asset_dir / f"{stem}.png"
            gif_path = asset_dir / f"{entry['asset_id']}_{motion}_6fps.gif"
            qa_path = asset_dir / f"{entry['asset_id']}_{motion}_qa.json"
            sheet.save(sheet_path, "PNG", optimize=True)
            gif_preview(frames, gif_path)
            qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")

            row, col = divmod(asset_index, 6)
            for frame_index, frame in enumerate(frames):
                card = Image.new("RGBA", (128, 128), (28, 32, 42, 255))
                thumb = frame.crop(alpha_bbox(frame))
                thumb.thumbnail((110, 104), Image.Resampling.LANCZOS)
                card.alpha_composite(thumb, ((128 - thumb.width) // 2, 18 + (104 - thumb.height) // 2))
                motion_previews[motion][frame_index].paste(card.convert("RGB"), (col * 128, row * 128))

            output_entries.append({
                "asset_id": f"{entry['asset_id']}_{motion.upper()}_V01",
                "monster_id": entry["asset_id"],
                "family": entry["family"],
                "palette": entry["palette"],
                "motion": motion,
                "sheet_path": sheet_path.relative_to(ROOT).as_posix(),
                "gif_path": gif_path.relative_to(ROOT).as_posix(),
                "qa_path": qa_path.relative_to(ROOT).as_posix(),
                "qa": qa,
            })

    for motion, previews in motion_previews.items():
        gif_path = OUT / f"MONSTER_30_{motion.upper()}_6FPS_PREVIEW.gif"
        converted = [frame.convert("P", palette=Image.Palette.ADAPTIVE) for frame in previews]
        converted[0].save(gif_path, save_all=True, append_images=converted[1:], duration=167, loop=0, disposal=2)
        previews[7].save(OUT / f"MONSTER_30_{motion.upper()}_CATALOG.png", "PNG", optimize=True)

    summary = {
        "title": "단맥 몬스터 30종 run/hit/attack 애니메이션",
        "sheet_standard": {"size": [1024, 1024], "grid": [4, 4], "cell": [256, 256], "frames": 16, "fps": 6, "safe_margin": 32, "max_subject": [192, 192], "format": "transparent RGBA PNG"},
        "total_monsters": 30,
        "motions": ["run", "hit", "attack"],
        "total_sheets": len(output_entries),
        "all_qa_pass": all(item["qa"]["status"] == "PASS" for item in output_entries),
        "max_horizontal_drift_px": max(item["qa"]["body_center_x_range_px"] for item in output_entries),
        "entries": output_entries,
    }
    (OUT / "MONSTER_30_ANIMATION_MANIFEST.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"total_sheets": len(output_entries), "all_qa_pass": summary["all_qa_pass"], "max_horizontal_drift_px": summary["max_horizontal_drift_px"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
