import argparse
import hashlib
import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


class SpriteQAError(ValueError):
    pass


@dataclass(frozen=True)
class QAConfig:
    columns: int = 4
    rows: int = 4
    expected_frames: int = 16
    fps: float = 12
    loop: bool = True
    chroma_key: str | None = None
    chroma_tolerance: int = 45
    alpha_threshold: int = 8
    jitter_ratio: float = 0.035
    scale_variation_ratio: float = 0.15


def parse_hex_color(value: str) -> tuple[int, int, int]:
    normalized = value.strip().lstrip("#")
    if len(normalized) != 6:
        raise SpriteQAError("chroma_key must use #RRGGBB format")
    try:
        return tuple(int(normalized[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError as exc:
        raise SpriteQAError("chroma_key must use #RRGGBB format") from exc


def remove_chroma(image: Image.Image, color: tuple[int, int, int], tolerance: int) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = []
    tolerance_sq = tolerance * tolerance
    for red, green, blue, alpha in rgba.getdata():
        distance = (red - color[0]) ** 2 + (green - color[1]) ** 2 + (blue - color[2]) ** 2
        pixels.append((red, green, blue, 0 if distance <= tolerance_sq else alpha))
    rgba.putdata(pixels)
    return rgba


def split_sheet(source: Path, config: QAConfig) -> tuple[list[Image.Image], tuple[int, int]]:
    try:
        sheet = Image.open(source).convert("RGBA")
    except OSError as exc:
        raise SpriteQAError(f"Unable to read sprite sheet: {source}") from exc
    if sheet.width % config.columns or sheet.height % config.rows:
        raise SpriteQAError(
            f"Sheet size {sheet.width}x{sheet.height} is not divisible by {config.columns}x{config.rows}"
        )
    count = config.columns * config.rows
    if count != config.expected_frames:
        raise SpriteQAError(f"Grid contains {count} frames, expected {config.expected_frames}")
    cell_width = sheet.width // config.columns
    cell_height = sheet.height // config.rows
    chroma = parse_hex_color(config.chroma_key) if config.chroma_key else None
    frames = []
    for row in range(config.rows):
        for column in range(config.columns):
            box = (
                column * cell_width,
                row * cell_height,
                (column + 1) * cell_width,
                (row + 1) * cell_height,
            )
            frame = sheet.crop(box)
            frames.append(remove_chroma(frame, chroma, config.chroma_tolerance) if chroma else frame)
    return frames, (cell_width, cell_height)


def frame_metrics(frame: Image.Image, alpha_threshold: int) -> dict[str, Any]:
    alpha = frame.getchannel("A")
    mask = alpha.point(lambda value: 255 if value > alpha_threshold else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return {"empty": True, "bbox": None, "center": None, "bottom": None, "coverage": 0.0, "touches_edge": False}
    left, top, right, bottom = bbox
    opaque = mask.histogram()[255]
    return {
        "empty": False,
        "bbox": [left, top, right, bottom],
        "center": [(left + right) / 2, (top + bottom) / 2],
        "bottom": bottom,
        "coverage": opaque / (frame.width * frame.height),
        "touches_edge": left <= 0 or top <= 0 or right >= frame.width or bottom >= frame.height,
        "width": right - left,
        "height": bottom - top,
    }


def analyze_frames(frames: list[Image.Image], cell_size: tuple[int, int], config: QAConfig) -> dict[str, Any]:
    metrics = [frame_metrics(frame, config.alpha_threshold) for frame in frames]
    nonempty = [item for item in metrics if not item["empty"]]
    issues: list[dict[str, Any]] = []

    empty_frames = [index + 1 for index, item in enumerate(metrics) if item["empty"]]
    if empty_frames:
        issues.append({"code": "EMPTY_FRAME", "severity": "ERROR", "frames": empty_frames, "message": "비어 있는 프레임이 있습니다."})

    edge_frames = [index + 1 for index, item in enumerate(metrics) if item["touches_edge"]]
    if edge_frames:
        issues.append({"code": "EDGE_CLIPPING_RISK", "severity": "WARNING", "frames": edge_frames, "message": "캐릭터가 셀 가장자리에 닿아 잘림 가능성이 있습니다."})

    hashes: dict[str, list[int]] = {}
    for index, frame in enumerate(frames, start=1):
        digest = hashlib.sha256(frame.tobytes()).hexdigest()
        hashes.setdefault(digest, []).append(index)
    duplicate_groups = [indices for indices in hashes.values() if len(indices) > 1]
    if duplicate_groups:
        issues.append({"code": "DUPLICATE_FRAMES", "severity": "WARNING", "frames": duplicate_groups, "message": "완전히 동일한 프레임이 있습니다."})

    jitter_frames: list[int] = []
    scale_frames: list[int] = []
    if nonempty:
        median_x = statistics.median(item["center"][0] for item in nonempty)
        median_bottom = statistics.median(item["bottom"] for item in nonempty)
        median_height = statistics.median(item["height"] for item in nonempty)
        jitter_limit = max(2.0, cell_size[0] * config.jitter_ratio)
        for index, item in enumerate(metrics, start=1):
            if item["empty"]:
                continue
            item["pivot_delta"] = [round(item["center"][0] - median_x, 2), round(item["bottom"] - median_bottom, 2)]
            if max(abs(item["pivot_delta"][0]), abs(item["pivot_delta"][1])) > jitter_limit:
                jitter_frames.append(index)
            if median_height and abs(item["height"] - median_height) / median_height > config.scale_variation_ratio:
                scale_frames.append(index)
        if jitter_frames:
            issues.append({"code": "PIVOT_JITTER", "severity": "WARNING", "frames": jitter_frames, "message": "몸 중심 또는 발 기준점 변화가 큽니다."})
        if scale_frames:
            issues.append({"code": "SCALE_VARIATION", "severity": "WARNING", "frames": scale_frames, "message": "프레임 간 캐릭터 높이 변화가 큽니다."})

    status = "REDRAW" if any(issue["severity"] == "ERROR" for issue in issues) else "FIXABLE" if issues else "PASS"
    return {
        "status": status,
        "frame_count": len(frames),
        "cell_size": {"width": cell_size[0], "height": cell_size[1]},
        "issues": issues,
        "frames": metrics,
        "manual_review_required": ["얼굴·체형·의상·무기 일관성", "동작의 타격감", "첫 프레임과 마지막 프레임의 루프 연결"],
    }


def save_preview(frames: list[Image.Image], path: Path, config: QAConfig) -> None:
    duration = max(1, round(1000 / config.fps))
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0 if config.loop else 1,
        disposal=2,
        transparency=0,
    )


def save_contact_sheet(frames: list[Image.Image], path: Path, config: QAConfig) -> None:
    label_height = 22
    width, height = frames[0].size
    canvas = Image.new("RGBA", (width * config.columns, (height + label_height) * config.rows), (16, 24, 39, 255))
    draw = ImageDraw.Draw(canvas)
    for index, frame in enumerate(frames):
        column = index % config.columns
        row = index // config.columns
        x = column * width
        y = row * (height + label_height)
        checker = Image.new("RGBA", frame.size, (45, 55, 72, 255))
        canvas.alpha_composite(checker, (x, y))
        canvas.alpha_composite(frame, (x, y))
        draw.text((x + 6, y + height + 4), f"F{index + 1:02d}", fill=(237, 242, 255, 255))
    canvas.convert("RGB").save(path, quality=95)


def save_onion_skin(frames: list[Image.Image], path: Path, config: QAConfig) -> None:
    onion_frames = []
    for index, current in enumerate(frames):
        previous = frames[index - 1].copy()
        alpha = previous.getchannel("A").point(lambda value: int(value * 0.28))
        previous.putalpha(alpha)
        canvas = Image.new("RGBA", current.size, (0, 0, 0, 0))
        canvas.alpha_composite(previous)
        canvas.alpha_composite(current)
        onion_frames.append(canvas)
    duration = max(1, round(1000 / config.fps))
    onion_frames[0].save(path, save_all=True, append_images=onion_frames[1:], duration=duration, loop=0, disposal=2)


def write_report(result: dict[str, Any], output_dir: Path, source: Path, config: QAConfig) -> None:
    (output_dir / "qa_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    issue_lines = [
        f"- [{issue['severity']}] {issue['code']}: {issue['message']} 프레임={issue['frames']}"
        for issue in result["issues"]
    ] or ["- 자동 검사에서 기술적 오류가 발견되지 않았습니다."]
    manual_lines = [f"- {item}" for item in result["manual_review_required"]]
    report = "\n".join(
        [
            "# Sprite QA Report",
            "",
            f"- Source: `{source.as_posix()}`",
            f"- Result: **{result['status']}**",
            f"- Frames: {result['frame_count']}",
            f"- Grid: {config.columns}x{config.rows}",
            f"- FPS: {config.fps}",
            "",
            "## Automatic checks",
            "",
            *issue_lines,
            "",
            "## Manual review required",
            "",
            *manual_lines,
            "",
        ]
    )
    (output_dir / "qa_report.md").write_text(report, encoding="utf-8")


def run_sprite_qa(source: Path, output_dir: Path, config: QAConfig) -> dict[str, Any]:
    if not source.is_file():
        raise SpriteQAError(f"Sprite sheet does not exist: {source}")
    output_dir.mkdir(parents=True, exist_ok=True)
    frames, cell_size = split_sheet(source, config)
    result = analyze_frames(frames, cell_size, config)
    result.update(
        {
            "source_path": source.as_posix(),
            "output_dir": output_dir.as_posix(),
            "config": asdict(config),
            "outputs": {
                "preview": (output_dir / "preview.gif").as_posix(),
                "contact_sheet": (output_dir / "contact_sheet.png").as_posix(),
                "onion_skin": (output_dir / "onion_skin.gif").as_posix(),
                "report": (output_dir / "qa_report.md").as_posix(),
                "result": (output_dir / "qa_result.json").as_posix(),
            },
        }
    )
    save_preview(frames, output_dir / "preview.gif", config)
    save_contact_sheet(frames, output_dir / "contact_sheet.png", config)
    save_onion_skin(frames, output_dir / "onion_skin.gif", config)
    write_report(result, output_dir, source, config)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run technical QA on a sprite sheet")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--rows", type=int, default=4)
    parser.add_argument("--frames", type=int, default=16)
    parser.add_argument("--fps", type=float, default=12)
    parser.add_argument("--no-loop", action="store_true")
    parser.add_argument("--chroma-key")
    parser.add_argument("--chroma-tolerance", type=int, default=45)
    args = parser.parse_args()
    config = QAConfig(
        columns=args.columns,
        rows=args.rows,
        expected_frames=args.frames,
        fps=args.fps,
        loop=not args.no_loop,
        chroma_key=args.chroma_key,
        chroma_tolerance=args.chroma_tolerance,
    )
    result = run_sprite_qa(args.source.resolve(), args.output.resolve(), config)
    print(json.dumps({"status": result["status"], "outputs": result["outputs"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
