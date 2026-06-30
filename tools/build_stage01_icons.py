from __future__ import annotations

import argparse, json, sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import build_prologue_monsters as common
from build_stage01_background import remove_magenta


def main():
    p=argparse.ArgumentParser(); p.add_argument("--root",type=Path,required=True); p.add_argument("--source",type=Path,required=True); a=p.parse_args()
    out=a.root/"05_sprites"/"work"/"STAGE01_REWARD_ICONS"; out.mkdir(parents=True,exist_ok=True)
    raw=Image.open(a.source).convert("RGBA"); raw.save(out/"STAGE01_reward_icons_chroma_source.png")
    entries=[]
    for i,(eid,korean) in enumerate((("seal_fragment","봉인 파편"),("spirit_xp_orb","영맥 경험 구슬"),("spirit_vein_stone","영맥석"))):
        x0,x1=round(raw.width*i/3),round(raw.width*(i+1)/3)
        crop=common.trim(remove_magenta(raw.crop((x0,0,x1,raw.height))))
        scale=min(440/crop.width,440/crop.height); crop=crop.resize((round(crop.width*scale),round(crop.height*scale)),Image.Resampling.LANCZOS)
        icon=Image.new("RGBA",(512,512)); icon.alpha_composite(crop,((512-crop.width)//2,(512-crop.height)//2))
        p512=out/f"ICON_STAGE01_{eid}_512.png"; p128=out/f"ICON_STAGE01_{eid}_128.png"; icon.save(p512); icon.resize((128,128),Image.Resampling.LANCZOS).save(p128)
        box=icon.getchannel("A").getbbox(); corners=((0,0),(511,0),(0,511),(511,511))
        entries.append({"id":eid,"korean_name":korean,"source_512":str(p512),"game_128":str(p128),
                        "sha256_512":common.sha256(p512),"sha256_128":common.sha256(p128),"alpha_bbox":box,
                        "transparent_corners":all(icon.getpixel(x)[3]==0 for x in corners),"size_512":list(icon.size),"size_128":list(Image.open(p128).size)})
    manifest={"schema":"danmaek.stage01.reward_icons.v1","external_ai_api_used":False,"unity_handoff":"BLOCKED_PENDING_USER_APPROVAL",
              "icons":entries,"overall_pass":all(x["transparent_corners"] and x["size_512"]==[512,512] and x["size_128"]==[128,128] for x in entries)}
    m=out/"STAGE01_REWARD_ICONS_QA_MANIFEST.json"; m.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"manifest":str(m),"overall_pass":manifest["overall_pass"]},ensure_ascii=False))


if __name__=="__main__": main()
