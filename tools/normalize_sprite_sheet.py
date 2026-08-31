from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw


SHEET_SIZE = 1024
GRID = 4
CELL_SIZE = 256
SAFE_MARGIN = 32
MAX_SUBJECT = 192
CENTER_X = CELL_SIZE // 2
BASELINE_Y = CELL_SIZE - SAFE_MARGIN


def remove_green(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    cleaned = []
    for r, g, b, _ in rgba.getdata():
        non_green = max(r, b)
        distance = max(r, 255 - g, b)
        alpha = max(0, min(255, round((distance - 24) / 81 * 255)))
        if g > 70 and g > non_green * 1.25 and g - non_green > 25:
            cleaned.append((0, 0, 0, 0))
            continue
        if alpha < 255:
            g = min(g, non_green + 8)
        cleaned.append((r, g, b, alpha))
    rgba.putdata(cleaned)
    return rgba


def split_frames(image: Image.Image) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for row in range(GRID):
        y0 = round(row * image.height / GRID)
        y1 = round((row + 1) * image.height / GRID)
        for col in range(GRID):
            x0 = round(col * image.width / GRID)
            x1 = round((col + 1) * image.width / GRID)
            frames.append(image.crop((x0, y0, x1, y1)))
    return frames


def keep_largest_component(frame: Image.Image, threshold: int = 16) -> Image.Image:
    alpha = frame.getchannel("A")
    width, height = frame.size
    mask = alpha.point(lambda value: 255 if value >= threshold else 0)
    center = (width // 2, height // 2)
    if mask.getpixel(center) == 0:
        bbox = mask.getbbox()
        if bbox is None:
            return frame
        active = [
            ((x - center[0]) ** 2 + (y - center[1]) ** 2, x, y)
            for y in range(bbox[1], bbox[3])
            for x in range(bbox[0], bbox[2])
            if mask.getpixel((x, y))
        ]
        _, x, y = min(active)
        center = (x, y)
    ImageDraw.floodfill(mask, center, 128, thresh=0)
    keep = mask.point(lambda value: 255 if value == 128 else 0)
    alpha = ImageChops.multiply(alpha, keep)
    cleaned = frame.copy()
    cleaned.putalpha(alpha)
    return cleaned


def alpha_bbox(frame: Image.Image) -> tuple[int, int, int, int]:
    alpha = frame.getchannel("A").point(lambda value: 255 if value >= 16 else 0)
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError("A frame became empty after chroma-key removal")
    return bbox


def normalize(source: Path, output: Path, gif_path: Path | None, report_path: Path | None) -> dict:
    keyed = remove_green(Image.open(source))
    raw_frames = [keep_largest_component(frame) for frame in split_frames(keyed)]
    crops = [frame.crop(alpha_bbox(frame)) for frame in raw_frames]
    max_width = max(frame.width for frame in crops)
    max_height = max(frame.height for frame in crops)
    scale = min(MAX_SUBJECT / max_width, MAX_SUBJECT / max_height, 1.0)

    normalized: list[Image.Image] = []
    metrics: list[dict] = []
    for index, crop in enumerate(crops, start=1):
        size = (max(1, round(crop.width * scale)), max(1, round(crop.height * scale)))
        sprite = crop.resize(size, Image.Resampling.LANCZOS)
        # Lanczos can leave a sub-threshold transparent rim. Trim it again so
        # measured visual bounds, center and baseline match the final pixels.
        sprite = sprite.crop(alpha_bbox(sprite))
        cell = Image.new("RGBA", (CELL_SIZE, CELL_SIZE), (0, 0, 0, 0))
        x = CENTER_X - sprite.width // 2
        y = BASELINE_Y - sprite.height
        cell.alpha_composite(sprite, (x, y))
        bbox = alpha_bbox(cell)
        normalized.append(cell)
        metrics.append(
            {
                "frame": index,
                "bbox": list(bbox),
                "width": bbox[2] - bbox[0],
                "height": bbox[3] - bbox[1],
                "center_x": (bbox[0] + bbox[2]) / 2,
                "baseline_y": bbox[3],
                "margins": {
                    "left": bbox[0],
                    "top": bbox[1],
                    "right": CELL_SIZE - bbox[2],
                    "bottom": CELL_SIZE - bbox[3],
                },
            }
        )

    sheet = Image.new("RGBA", (SHEET_SIZE, SHEET_SIZE), (0, 0, 0, 0))
    for index, frame in enumerate(normalized):
        sheet.alpha_composite(frame, ((index % GRID) * CELL_SIZE, (index // GRID) * CELL_SIZE))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="PNG", optimize=True)

    if gif_path:
        preview = []
        checker = Image.new("RGBA", (CELL_SIZE, CELL_SIZE), (34, 38, 48, 255))
        for frame in normalized:
            composite = checker.copy()
            composite.alpha_composite(frame)
            preview.append(composite.convert("P", palette=Image.Palette.ADAPTIVE))
        preview[0].save(gif_path, save_all=True, append_images=preview[1:], duration=167, loop=0, disposal=2)

    report = {
        "source": str(source),
        "output": str(output),
        "sheet": [sheet.width, sheet.height],
        "grid": [GRID, GRID],
        "cell": [CELL_SIZE, CELL_SIZE],
        "frame_count": len(normalized),
        "fps": 6,
        "mode": sheet.mode,
        "max_subject": [MAX_SUBJECT, MAX_SUBJECT],
        "safe_margin": SAFE_MARGIN,
        "center_x_target": CENTER_X,
        "baseline_y_target": BASELINE_Y,
        "scale": scale,
        "frames": metrics,
    }
    report["pass"] = (
        sheet.size == (SHEET_SIZE, SHEET_SIZE)
        and sheet.mode == "RGBA"
        and len(normalized) == 16
        and all(item["width"] <= MAX_SUBJECT and item["height"] <= MAX_SUBJECT for item in metrics)
        and all(min(item["margins"].values()) >= SAFE_MARGIN for item in metrics)
        and all(item["baseline_y"] == BASELINE_Y for item in metrics)
    )
    if report_path:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gif", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    print(json.dumps(normalize(args.input, args.output, args.gif, args.report), ensure_ascii=False))


if __name__ == "__main__":
    main()
