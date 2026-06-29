import argparse
import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class UnityBridgeError(ValueError):
    pass


SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
SAFE_RESOURCE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class UnityImportConfig:
    resource_name: str
    columns: int = 4
    rows: int = 4
    frame_count: int = 16
    fps: float = 12
    loop: bool = True
    pixels_per_unit: float = 200
    pivot_x: float = 0.5
    pivot_y: float = 0.05


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UnityBridgeError(f"Unable to read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise UnityBridgeError(f"JSON root must be an object: {path}")
    return value


def validate_inputs(manifest: dict[str, Any], qa: dict[str, Any], config: UnityImportConfig) -> None:
    asset_id = str(manifest.get("asset_id", ""))
    if not SAFE_ID.fullmatch(asset_id):
        raise UnityBridgeError("asset_id may contain only letters, digits, underscore and hyphen")
    if manifest.get("status") != "APPROVED":
        raise UnityBridgeError("Only APPROVED assets can be staged for Unity")
    if qa.get("status") != "PASS":
        raise UnityBridgeError("Sprite QA must be PASS before Unity staging")
    if not SAFE_RESOURCE.fullmatch(config.resource_name):
        raise UnityBridgeError("resource_name must be a safe C# resource identifier")
    if config.columns * config.rows != config.frame_count:
        raise UnityBridgeError("columns multiplied by rows must equal frame_count")
    if config.fps <= 0 or config.pixels_per_unit <= 0:
        raise UnityBridgeError("fps and pixels_per_unit must be positive")
    if not (0 <= config.pivot_x <= 1 and 0 <= config.pivot_y <= 1):
        raise UnityBridgeError("pivot values must be normalized between 0 and 1")


def stage_unity_import(
    manifest_path: Path,
    qa_result_path: Path,
    output_root: Path,
    config: UnityImportConfig,
) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    qa = load_json(qa_result_path)
    validate_inputs(manifest, qa, config)

    source_value = manifest.get("file_path") or qa.get("source_path")
    if not source_value:
        raise UnityBridgeError("Manifest must contain file_path")
    source = Path(source_value)
    if not source.is_absolute():
        candidates = [(parent / source).resolve() for parent in manifest_path.parents]
        source = next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
    if not source.is_file() or source.suffix.lower() != ".png":
        raise UnityBridgeError(f"Approved PNG does not exist: {source}")
    expected_checksum = manifest.get("checksum")
    actual_checksum = sha256_file(source)
    if expected_checksum and expected_checksum != actual_checksum:
        raise UnityBridgeError("Source checksum does not match the approved manifest")

    asset_id = manifest["asset_id"]
    package_dir = output_root / asset_id
    if package_dir.exists():
        raise UnityBridgeError(f"Unity package already exists: {package_dir}")
    package_dir.mkdir(parents=True)
    destination_png = package_dir / f"{config.resource_name}.png"
    shutil.copy2(source, destination_png)

    request = {
        "schema_version": 1,
        "asset_id": asset_id,
        "status": "APPROVED",
        "qa_status": "PASS",
        "source_file": destination_png.name,
        "resource_name": config.resource_name,
        "columns": config.columns,
        "rows": config.rows,
        "frame_count": config.frame_count,
        "fps": config.fps,
        "loop": config.loop,
        "pixels_per_unit": config.pixels_per_unit,
        "pivot": {"x": config.pivot_x, "y": config.pivot_y},
        "source_checksum": actual_checksum,
        "character_version": manifest.get("character_version", ""),
        "style_version": manifest.get("style_version", ""),
    }
    request_path = package_dir / "request.json"
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    receipt = {
        "asset_id": asset_id,
        "package_dir": package_dir.as_posix(),
        "request_path": request_path.as_posix(),
        "source_path": destination_png.as_posix(),
        "source_checksum": actual_checksum,
        "config": asdict(config),
    }
    (package_dir / "staging_receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage an approved sprite package for Unity")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("qa_result", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--resource-name", required=True)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--rows", type=int, default=4)
    parser.add_argument("--frames", type=int, default=16)
    parser.add_argument("--fps", type=float, default=12)
    parser.add_argument("--no-loop", action="store_true")
    parser.add_argument("--pixels-per-unit", type=float, default=200)
    parser.add_argument("--pivot-x", type=float, default=0.5)
    parser.add_argument("--pivot-y", type=float, default=0.05)
    args = parser.parse_args()
    receipt = stage_unity_import(
        args.manifest.resolve(),
        args.qa_result.resolve(),
        args.output_root.resolve(),
        UnityImportConfig(
            resource_name=args.resource_name,
            columns=args.columns,
            rows=args.rows,
            frame_count=args.frames,
            fps=args.fps,
            loop=not args.no_loop,
            pixels_per_unit=args.pixels_per_unit,
            pivot_x=args.pivot_x,
            pivot_y=args.pivot_y,
        ),
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
