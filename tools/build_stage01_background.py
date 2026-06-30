from __future__ import annotations

import argparse, json, sys
from pathlib import Path
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).parent))
import build_prologue_monsters as common

SIZE = (1080, 1920)


def fit(im: Image.Image):
    scale = max(SIZE[0] / im.width, SIZE[1] / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.LANCZOS)
    x, y = (im.width - SIZE[0]) // 2, (im.height - SIZE[1]) // 2
    return im.crop((x, y, x + SIZE[0], y + SIZE[1]))


def remove_magenta(im: Image.Image):
    im = im.convert("RGBA")
    out = []
    for r, g, b, _ in im.getdata():
        dominance = min(r, b) - g
        if r > 120 and b > 90 and dominance > 25:
            a = max(0, min(255, round(255 * (1 - (dominance - 25) / 65))))
            if a < 28: a = 0
            r = min(r, g + 5)
            b = min(b, g + 8)
        else:
            a = 255
        out.append((r, g, b, a))
    im.putdata(out)
    return im


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    for n in ("far", "mid", "foreground", "fog", "spirit_fire"):
        p.add_argument(f"--{n.replace('_','-')}", dest=n, type=Path, required=True)
    a = p.parse_args()
    out = a.root / "07_cinematics" / "work" / "STAGE_01_CRACKED_SEAL_ROAD" / "background_layers"
    out.mkdir(parents=True, exist_ok=True)
    layers = {}
    far = fit(Image.open(a.far).convert("RGB")).convert("RGBA")
    layers["far"] = far
    for name in ("mid", "foreground", "fog"):
        keyed = common.chroma_to_alpha(Image.open(getattr(a, name)))
        keyed = fit(keyed)
        if name == "fog":
            alpha = keyed.getchannel("A").point(lambda x: round(x * 0.48))
            keyed.putalpha(alpha.filter(ImageFilter.GaussianBlur(1.2)))
        layers[name] = keyed
    layers["spirit_fire"] = fit(remove_magenta(Image.open(a.spirit_fire)))

    entries = []
    for name, image in layers.items():
        path = out / f"STAGE01_BG_{name}_1080x1920.png"
        image.save(path)
        alpha = image.getchannel("A")
        entries.append({"layer": name, "path": str(path), "sha256": common.sha256(path),
                        "size": list(image.size), "mode": image.mode,
                        "alpha_bbox": alpha.getbbox(),
                        "alpha_minmax": list(alpha.getextrema())})
    preview = layers["far"].copy()
    for name in ("mid", "fog", "spirit_fire", "foreground"):
        preview.alpha_composite(layers[name])
    preview_path = out / "STAGE01_BG_composite_preview_1080x1920.jpg"
    preview.convert("RGB").save(preview_path, quality=94)
    manifest = {"schema": "danmaek.stage01.background_layers.v1",
                "external_ai_api_used": False,
                "unity_handoff": "BLOCKED_PENDING_USER_APPROVAL",
                "canvas": list(SIZE), "order": ["far", "mid", "fog", "spirit_fire", "foreground"],
                "layers": entries, "composite_preview": str(preview_path),
                "overall_pass": all(x["size"] == [1080,1920] and x["mode"] == "RGBA" for x in entries)}
    m = out / "STAGE01_BACKGROUND_QA_MANIFEST.json"
    m.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(m), "overall_pass": manifest["overall_pass"]}, ensure_ascii=False))


if __name__ == "__main__": main()
