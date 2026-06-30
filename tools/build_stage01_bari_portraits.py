from __future__ import annotations

import argparse, json, sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import build_prologue_monsters as common


def keep_largest_component(im):
    alpha = im.getchannel("A")
    w, h = alpha.size
    data = bytearray(alpha.tobytes())
    seen = bytearray(w * h)
    largest = []
    for start, value in enumerate(data):
        if not value or seen[start]:
            continue
        stack, comp = [start], []
        seen[start] = 1
        while stack:
            pos = stack.pop(); comp.append(pos)
            x, y = pos % w, pos // w
            for nxt in (pos-1 if x else -1, pos+1 if x+1<w else -1,
                        pos-w if y else -1, pos+w if y+1<h else -1):
                if nxt >= 0 and data[nxt] and not seen[nxt]:
                    seen[nxt] = 1; stack.append(nxt)
        if len(comp) > len(largest): largest = comp
    keep = bytearray(w * h)
    for pos in largest: keep[pos] = data[pos]
    alpha.frombytes(bytes(keep)); im.putalpha(alpha)
    return im


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--source", type=Path, required=True)
    a = p.parse_args()
    cid = "NPC_BARI_GUIDE_PORTRAIT_01"
    out = a.root / "04_concepts" / "work" / cid
    out.mkdir(parents=True, exist_ok=True)
    raw = Image.open(a.source).convert("RGBA")
    raw.save(out / f"{cid}_expressions_chroma_source.png")
    files = []
    for i, mood in enumerate(("base", "warning", "relief")):
        x0, x1 = round(raw.width * i / 3), round(raw.width * (i + 1) / 3)
        crop = common.trim(keep_largest_component(common.chroma_to_alpha(raw.crop((x0, 0, x1, raw.height)))))
        scale = min(900 / crop.width, 940 / crop.height)
        crop = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (1024, 1024))
        canvas.alpha_composite(crop, ((1024 - crop.width) // 2, 1010 - crop.height))
        path = out / f"{cid}_{mood}_1024.png"
        canvas.save(path)
        box = canvas.getchannel("A").getbbox()
        files.append({"expression": mood, "path": str(path), "sha256": common.sha256(path),
                      "size": list(canvas.size), "alpha_bbox": box,
                      "transparent_corners": all(canvas.getpixel(pt)[3] == 0 for pt in ((0,0),(1023,0),(0,1023),(1023,1023)))})
    manifest = {"schema": "danmaek.stage01.bari_portrait_manifest.v1",
                "external_ai_api_used": False,
                "unity_handoff": "BLOCKED_PENDING_USER_APPROVAL",
                "character_id": cid, "expressions": files,
                "overall_pass": all(x["transparent_corners"] and x["size"] == [1024,1024] for x in files)}
    m = out / "STAGE01_BARI_PORTRAIT_QA_MANIFEST.json"
    m.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(m), "overall_pass": manifest["overall_pass"]}, ensure_ascii=False))


if __name__ == "__main__": main()
