from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean

from PIL import Image, ImageDraw


GRID = 4
CELL = 256
SHEET = 1024
SAFE_MIN = 32
SAFE_MAX = 224
TARGET_HEIGHT = 188
AXIS_X = 128
BASELINE_Y = 224
ALPHA_THRESHOLD = 16


def bbox(image: Image.Image) -> tuple[int, int, int, int]:
    result = image.getchannel("A").point(lambda value: 255 if value >= ALPHA_THRESHOLD else 0).getbbox()
    if result is None:
        raise ValueError("empty frame")
    return result


def crop_subject(image: Image.Image) -> Image.Image:
    return image.crop(bbox(image))


def weighted_center_x(image: Image.Image, top: float, bottom: float, center_bias: bool = True) -> float:
    alpha = image.getchannel("A")
    pixels = alpha.load()
    y0 = max(0, round(image.height * top))
    y1 = min(image.height, round(image.height * bottom))
    total = weighted = 0.0
    for y in range(y0, y1):
        for x in range(image.width):
            value = pixels[x, y]
            if value < ALPHA_THRESHOLD:
                continue
            weight = float(value)
            if center_bias:
                weight *= max(0.18, 1.0 - abs(x / max(1, image.width - 1) - 0.5) * 1.5)
            total += weight
            weighted += x * weight
    return weighted / total if total else image.width / 2


def prepare(frame: Image.Image) -> Image.Image:
    subject = crop_subject(frame)
    width = max(1, round(subject.width * TARGET_HEIGHT / subject.height))
    if width > SAFE_MAX - SAFE_MIN:
        width = SAFE_MAX - SAFE_MIN
    resized = subject.resize((width, TARGET_HEIGHT), Image.Resampling.LANCZOS)
    resized = crop_subject(resized)
    # The threshold crop after resampling can remove one edge pixel. Restore a
    # truly constant visual height before placement.
    width = max(1, round(resized.width * TARGET_HEIGHT / resized.height))
    return resized.resize((width, TARGET_HEIGHT), Image.Resampling.LANCZOS)


def stabilize(source: Path, output: Path, gif: Path, guide: Path, report_path: Path) -> dict:
    sheet_source = Image.open(source).convert("RGBA")
    frames: list[Image.Image] = []
    metrics: list[dict] = []
    for index in range(16):
        col, row = index % GRID, index // GRID
        x0 = round(col * sheet_source.width / GRID)
        x1 = round((col + 1) * sheet_source.width / GRID)
        y0 = round(row * sheet_source.height / GRID)
        y1 = round((row + 1) * sheet_source.height / GRID)
        subject = prepare(sheet_source.crop((x0, y0, x1, y1)))
        anchor = weighted_center_x(subject, 0.0, 0.72)
        x = round(AXIS_X - anchor)
        x = max(SAFE_MIN, min(x, SAFE_MAX - subject.width))
        y = BASELINE_Y - TARGET_HEIGHT
        frame = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
        frame.alpha_composite(subject, (x, y))
        bounds = bbox(frame)
        final = frame.crop(bounds)
        head_x = bounds[0] + weighted_center_x(final, 0.0, 0.43)
        torso_x = bounds[0] + weighted_center_x(final, 0.30, 0.72)
        mass_x = bounds[0] + weighted_center_x(final, 0.0, 0.72)
        frames.append(frame)
        metrics.append({
            "frame": index + 1,
            "bbox": list(bounds),
            "width": bounds[2] - bounds[0],
            "height": bounds[3] - bounds[1],
            "baseline_y": bounds[3],
            "mass_center_x": round(mass_x, 3),
            "head_center_x": round(head_x, 3),
            "torso_center_x": round(torso_x, 3),
            "margins": [bounds[0], bounds[1], CELL - bounds[2], CELL - bounds[3]],
        })

    sheet = Image.new("RGBA", (SHEET, SHEET), (0, 0, 0, 0))
    guide_image = Image.new("RGBA", (SHEET, SHEET), (25, 29, 38, 255))
    draw = ImageDraw.Draw(guide_image)
    for index, frame in enumerate(frames):
        ox, oy = (index % GRID) * CELL, (index // GRID) * CELL
        sheet.alpha_composite(frame, (ox, oy))
        guide_image.alpha_composite(frame, (ox, oy))
        draw.rectangle((ox + SAFE_MIN, oy + SAFE_MIN, ox + SAFE_MAX, oy + SAFE_MAX), outline=(70, 155, 255, 130))
        draw.line((ox + AXIS_X, oy + SAFE_MIN, ox + AXIS_X, oy + SAFE_MAX), fill=(255, 70, 70, 190))
        draw.line((ox + SAFE_MIN, oy + BASELINE_Y, ox + SAFE_MAX, oy + BASELINE_Y), fill=(80, 255, 120, 190))

    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, "PNG", optimize=True)
    guide_image.save(guide, "PNG", optimize=True)
    backdrop = Image.new("RGBA", (CELL, CELL), (34, 38, 48, 255))
    previews = []
    for frame in frames:
        preview = backdrop.copy()
        preview.alpha_composite(frame)
        previews.append(preview.convert("P", palette=Image.Palette.ADAPTIVE))
    previews[0].save(gif, save_all=True, append_images=previews[1:], duration=167, loop=0, disposal=2)

    def spread(key: str) -> float:
        values = [item[key] for item in metrics]
        return round(max(values) - min(values), 3)

    heights = [item["height"] for item in metrics]
    report = {
        "asset_id": "CHR_PROTAGONIST_REBUILD_V01_WALK_SOUTH",
        "source": str(source),
        "output": str(output),
        "sheet": [SHEET, SHEET],
        "grid": [GRID, GRID],
        "cell": [CELL, CELL],
        "frames": 16,
        "fps": 6,
        "mode": "RGBA",
        "baseline_range_px": max(item["baseline_y"] for item in metrics) - min(item["baseline_y"] for item in metrics),
        "height_variation_percent": round((max(heights) - min(heights)) / mean(heights) * 100, 3),
        "mass_center_x_range_px": spread("mass_center_x"),
        "head_center_x_range_px": spread("head_center_x"),
        "torso_center_x_range_px": spread("torso_center_x"),
        "minimum_safe_margin": min(min(item["margins"]) for item in metrics),
        "metrics": metrics,
    }
    report["status"] = "PASS" if (
        report["baseline_range_px"] == 0
        and report["height_variation_percent"] <= 2.0
        and report["mass_center_x_range_px"] <= 1.0
        and report["head_center_x_range_px"] <= 1.5
        and report["torso_center_x_range_px"] <= 1.5
        and report["minimum_safe_margin"] >= SAFE_MIN
    ) else "FAIL"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gif", type=Path, required=True)
    parser.add_argument("--guide", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = stabilize(args.input, args.output, args.gif, args.guide, args.report)
    print(json.dumps({key: report[key] for key in ("status", "mass_center_x_range_px", "head_center_x_range_px", "torso_center_x_range_px", "height_variation_percent", "minimum_safe_margin")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
