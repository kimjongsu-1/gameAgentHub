from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


SHEET = 1024
CELL = 256
GRID = 4
CENTER_X = 128
BASELINE_Y = 224
TARGET_MAX_WIDTH = 192
SAFE_MARGIN = 32


def bbox(frame: Image.Image) -> tuple[int, int, int, int]:
    bounds = frame.getchannel("A").point(lambda value: 255 if value >= 16 else 0).getbbox()
    if bounds is None:
        raise ValueError("empty sprite frame")
    return bounds


def widen(source: Path, output: Path, gif_path: Path | None, report_path: Path | None) -> dict:
    sheet = Image.open(source).convert("RGBA")
    if sheet.size != (SHEET, SHEET):
        raise ValueError(f"expected {SHEET}x{SHEET}, got {sheet.size}")

    crops: list[Image.Image] = []
    for index in range(16):
        x = (index % GRID) * CELL
        y = (index // GRID) * CELL
        frame = sheet.crop((x, y, x + CELL, y + CELL))
        crops.append(frame.crop(bbox(frame)))

    widest = max(crop.width for crop in crops)
    x_scale = TARGET_MAX_WIDTH / widest
    frames: list[Image.Image] = []
    metrics: list[dict] = []
    for index, crop in enumerate(crops, start=1):
        wide = crop.resize((round(crop.width * x_scale), crop.height), Image.Resampling.LANCZOS)
        wide = wide.crop(bbox(wide))
        frame = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
        frame.alpha_composite(wide, (CENTER_X - wide.width // 2, BASELINE_Y - wide.height))
        bounds = bbox(frame)
        frames.append(frame)
        metrics.append(
            {
                "frame": index,
                "bbox": list(bounds),
                "width": bounds[2] - bounds[0],
                "height": bounds[3] - bounds[1],
                "center_x": (bounds[0] + bounds[2]) / 2,
                "baseline_y": bounds[3],
                "margins": {
                    "left": bounds[0],
                    "top": bounds[1],
                    "right": CELL - bounds[2],
                    "bottom": CELL - bounds[3],
                },
            }
        )

    result = Image.new("RGBA", (SHEET, SHEET), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        result.alpha_composite(frame, ((index % GRID) * CELL, (index // GRID) * CELL))
    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output, format="PNG", optimize=True)

    if gif_path:
        preview = []
        backdrop = Image.new("RGBA", (CELL, CELL), (34, 38, 48, 255))
        for frame in frames:
            composite = backdrop.copy()
            composite.alpha_composite(frame)
            preview.append(composite.convert("P", palette=Image.Palette.ADAPTIVE))
        preview[0].save(gif_path, save_all=True, append_images=preview[1:], duration=167, loop=0, disposal=2)

    report = {
        "source": str(source),
        "output": str(output),
        "sheet": [SHEET, SHEET],
        "grid": [GRID, GRID],
        "cell": [CELL, CELL],
        "frame_count": 16,
        "fps": 6,
        "mode": result.mode,
        "prompt_changed": False,
        "original_max_width": widest,
        "x_scale": x_scale,
        "target_max_width": TARGET_MAX_WIDTH,
        "safe_margin": SAFE_MARGIN,
        "frames": metrics,
    }
    report["pass"] = (
        result.size == (SHEET, SHEET)
        and result.mode == "RGBA"
        and max(item["width"] for item in metrics) <= TARGET_MAX_WIDTH
        and all(min(item["margins"].values()) >= SAFE_MARGIN for item in metrics)
        and all(item["baseline_y"] == BASELINE_Y for item in metrics)
        and max(item["center_x"] for item in metrics) - min(item["center_x"] for item in metrics) <= 0.5
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
    print(json.dumps(widen(args.input, args.output, args.gif, args.report), ensure_ascii=False))


if __name__ == "__main__":
    main()
