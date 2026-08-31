from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean

from PIL import Image, ImageDraw


GRID = 4
SHEET = 1024
CELL = 256
SAFE_MIN = 32
SAFE_MAX = 224
MAX_SIZE = 192
AXIS_X = 128
BASELINE_Y = 224


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    bbox = image.getchannel("A").point(lambda value: 255 if value >= 16 else 0).getbbox()
    if bbox is None:
        raise ValueError("empty frame")
    return bbox


def split_frames(sheet: Image.Image) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for row in range(GRID):
        y0 = round(row * sheet.height / GRID)
        y1 = round((row + 1) * sheet.height / GRID)
        for col in range(GRID):
            x0 = round(col * sheet.width / GRID)
            x1 = round((col + 1) * sheet.width / GRID)
            frame = sheet.crop((x0, y0, x1, y1))
            frames.append(frame.crop(alpha_bbox(frame)))
    return frames


def visual_anchor(image: Image.Image) -> tuple[float, float]:
    """Weighted head/torso anchor that ignores most weapons and limb extremes."""
    alpha = image.getchannel("A")
    width, height = image.size
    pixels = alpha.load()
    total = x_total = y_total = 0.0
    for y in range(height):
        yn = y / max(1, height - 1)
        if yn > 0.80:
            continue
        for x in range(width):
            value = pixels[x, y]
            if value < 16:
                continue
            xn = x / max(1, width - 1)
            # Head and central torso dominate; far-side weapons/arms have low weight.
            center_weight = max(0.12, 1.0 - abs(xn - 0.5) * 1.65)
            vertical_weight = 1.35 if yn < 0.48 else 0.85
            weight = value * center_weight * vertical_weight
            total += weight
            x_total += x * weight
            y_total += y * weight
    if total == 0:
        return width / 2, height / 2
    return x_total / total, y_total / total


def common_scale(crops: list[Image.Image]) -> float:
    constraints = []
    for crop in crops:
        anchor_x, _ = visual_anchor(crop)
        side_extent = max(anchor_x, crop.width - anchor_x)
        constraints.append((MAX_SIZE / crop.height, (MAX_SIZE / 2) / side_extent))
    return min(min(pair) for pair in constraints)


def render(source: Path, output: Path, gif_path: Path, report_path: Path, guide_path: Path) -> dict:
    original = Image.open(source).convert("RGBA")
    crops = split_frames(original)
    scale = common_scale(crops)
    target_height = min(MAX_SIZE, round(mean(crop.height * scale for crop in crops)))
    prepared: list[Image.Image] = []
    for crop in crops:
        resized = crop.resize(
            (max(1, round(crop.width * scale)), target_height),
            Image.Resampling.LANCZOS,
        )
        prepared.append(resized.crop(alpha_bbox(resized)))
    target_anchor_distance = min(image.height - visual_anchor(image)[1] for image in prepared)
    frames: list[Image.Image] = []
    metrics: list[dict] = []

    for index, base in enumerate(prepared, start=1):
        _, base_anchor_y = visual_anchor(base)
        vertical_scale = target_anchor_distance / max(1.0, base.height - base_anchor_y)
        predicted_height = max(1, min(MAX_SIZE, round(base.height * vertical_scale)))
        candidates: list[Image.Image] = []
        for height in range(max(1, predicted_height - 1), min(MAX_SIZE, predicted_height + 1) + 1):
            candidate = base.resize((base.width, height), Image.Resampling.LANCZOS)
            candidates.append(candidate.crop(alpha_bbox(candidate)))
        resized = min(
            candidates,
            key=lambda image: abs((image.height - visual_anchor(image)[1]) - target_anchor_distance),
        )
        anchor_x, anchor_y = visual_anchor(resized)
        x = round(AXIS_X - anchor_x)
        x = max(SAFE_MIN, min(x, SAFE_MAX - resized.width))
        y = BASELINE_Y - resized.height
        frame = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
        frame.alpha_composite(resized, (x, y))
        bounds = alpha_bbox(frame)
        final_crop = frame.crop(bounds)
        local_anchor_x, local_anchor_y = visual_anchor(final_crop)
        final_anchor_x = bounds[0] + local_anchor_x
        final_anchor_y = bounds[1] + local_anchor_y
        frames.append(frame)
        metrics.append(
            {
                "frame": index,
                "bbox": list(bounds),
                "width": bounds[2] - bounds[0],
                "height": bounds[3] - bounds[1],
                "visual_anchor": [round(final_anchor_x, 3), round(final_anchor_y, 3)],
                "baseline_y": bounds[3],
                "margins": [bounds[0], bounds[1], CELL - bounds[2], CELL - bounds[3]],
            }
        )

    sheet = Image.new("RGBA", (SHEET, SHEET), (0, 0, 0, 0))
    guide = Image.new("RGBA", (SHEET, SHEET), (24, 27, 34, 255))
    draw = ImageDraw.Draw(guide)
    for index, frame in enumerate(frames):
        ox = (index % GRID) * CELL
        oy = (index // GRID) * CELL
        sheet.alpha_composite(frame, (ox, oy))
        guide.alpha_composite(frame, (ox, oy))
        draw.rectangle((ox + SAFE_MIN, oy + SAFE_MIN, ox + SAFE_MAX, oy + SAFE_MAX), outline=(80, 160, 255, 100))
        draw.line((ox + AXIS_X, oy + SAFE_MIN, ox + AXIS_X, oy + SAFE_MAX), fill=(255, 80, 80, 170), width=1)
        draw.line((ox + SAFE_MIN, oy + BASELINE_Y, ox + SAFE_MAX, oy + BASELINE_Y), fill=(80, 255, 120, 170), width=1)

    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, "PNG", optimize=True)
    guide.save(guide_path, "PNG", optimize=True)
    gif_frames = []
    backdrop = Image.new("RGBA", (CELL, CELL), (34, 38, 48, 255))
    for frame in frames:
        preview = backdrop.copy()
        preview.alpha_composite(frame)
        gif_frames.append(preview.convert("P", palette=Image.Palette.ADAPTIVE))
    gif_frames[0].save(gif_path, save_all=True, append_images=gif_frames[1:], duration=167, loop=0, disposal=2)

    xs = [item["visual_anchor"][0] for item in metrics]
    ys = [item["visual_anchor"][1] for item in metrics]
    heights = [item["height"] for item in metrics]
    report = {
        "source": str(source),
        "output": str(output),
        "sheet": [SHEET, SHEET],
        "grid": [GRID, GRID],
        "cell": [CELL, CELL],
        "frames": 16,
        "fps": 6,
        "mode": "RGBA",
        "safe_area": [MAX_SIZE, MAX_SIZE],
        "axis_x": AXIS_X,
        "baseline_y": BASELINE_Y,
        "common_scale": scale,
        "target_frame_height": target_height,
        "target_visual_anchor_distance_from_baseline": target_anchor_distance,
        "visual_anchor_x_range_px": round(max(xs) - min(xs), 3),
        "visual_anchor_y_range_px": round(max(ys) - min(ys), 3),
        "bbox_height_variation_percent": round((max(heights) - min(heights)) / mean(heights) * 100, 3),
        "metrics": metrics,
    }
    report["technical_pass"] = (
        all(max(item["width"], item["height"]) <= MAX_SIZE for item in metrics)
        and all(min(item["margins"]) >= SAFE_MIN for item in metrics)
        and all(item["baseline_y"] == BASELINE_Y for item in metrics)
        and report["visual_anchor_x_range_px"] <= 1.0
        and report["visual_anchor_y_range_px"] <= 1.0
        and report["bbox_height_variation_percent"] <= 2.0
    )
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gif", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--guide", type=Path, required=True)
    args = parser.parse_args()
    report = render(args.input, args.output, args.gif, args.report, args.guide)
    print(json.dumps({
        "output": report["output"],
        "technical_pass": report["technical_pass"],
        "visual_anchor_x_range_px": report["visual_anchor_x_range_px"],
        "visual_anchor_y_range_px": report["visual_anchor_y_range_px"],
        "bbox_height_variation_percent": report["bbox_height_variation_percent"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
