from __future__ import annotations

import hashlib, json
from pathlib import Path
from PIL import Image

ROOT=Path(r"C:\Users\kukl3\Documents\게임 개발 프로젝트")
MANIFESTS=[
 ROOT/"05_sprites/work/PROLOGUE_MONSTERS_SPRITE_QA_MANIFEST.json",
 ROOT/"05_sprites/work/CHR_PROTAGONIST_BASE_01/STAGE01_PROTAGONIST_SPRITE_QA_MANIFEST.json",
 ROOT/"04_concepts/work/NPC_BARI_GUIDE_PORTRAIT_01/STAGE01_BARI_PORTRAIT_QA_MANIFEST.json",
 ROOT/"07_cinematics/work/STAGE_01_CRACKED_SEAL_ROAD/background_layers/STAGE01_BACKGROUND_QA_MANIFEST.json",
 ROOT/"05_sprites/work/STAGE01_COMBAT_EFFECTS/STAGE01_COMBAT_EFFECTS_QA_MANIFEST.json",
 ROOT/"05_sprites/work/STAGE01_REWARD_ICONS/STAGE01_REWARD_ICONS_QA_MANIFEST.json",
]
DIRS=[
 ROOT/"04_concepts/work/CHR_PROTAGONIST_BASE_01",
 ROOT/"04_concepts/work/NPC_BARI_GUIDE_PORTRAIT_01",
 ROOT/"05_sprites/work/CHR_PROTAGONIST_BASE_01",
 ROOT/"05_sprites/work/STAGE01_COMBAT_EFFECTS",
 ROOT/"05_sprites/work/STAGE01_REWARD_ICONS",
 ROOT/"07_cinematics/work/STAGE_01_CRACKED_SEAL_ROAD/background_layers",
]

def sha(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for c in iter(lambda:f.read(1024*1024),b""): h.update(c)
 return h.hexdigest()

bundles=[]
for p in MANIFESTS:
 d=json.loads(p.read_text(encoding="utf-8"))
 bundles.append({"manifest":str(p),"schema":d.get("schema"),"overall_pass":bool(d.get("overall_pass")),"sha256":sha(p)})

assets=[]; residue_fail=[]; gif_fail=[]
for folder in DIRS:
 for p in sorted(folder.rglob("*")):
  if not p.is_file() or "chroma_source" in p.name or p.suffix.lower() not in (".png",".gif",".jpg"): continue
  item={"path":str(p),"sha256":sha(p),"bytes":p.stat().st_size}
  if p.suffix.lower()==".png":
   im=Image.open(p).convert("RGBA"); item.update({"size":list(im.size),"mode":"RGBA"})
   exact_green=exact_magenta=0
   for r,g,b,a in im.getdata():
    if a>16 and g>245 and r<20 and b<40: exact_green+=1
    if a>16 and r>245 and b>240 and g<30: exact_magenta+=1
   item["key_residue_pixels"]={"green":exact_green,"magenta":exact_magenta}
   # Up to ten exact-key pixels can arise from Lanczos resampling of bright
   # cyan/violet subject highlights; larger areas indicate actual key residue.
   if exact_green + exact_magenta > 10: residue_fail.append(str(p))
  elif p.suffix.lower()==".gif":
   im=Image.open(p); frames=getattr(im,"n_frames",1); durations=[]
   for i in range(frames): im.seek(i); durations.append(im.info.get("duration",0))
   item.update({"frames":frames,"duration_ms_unique":sorted(set(durations))})
   if frames not in (8,12,16) or not all(160<=d<=175 for d in durations): gif_fail.append(str(p))
  assets.append(item)

master={
 "schema":"danmaek.stage01.image_package_master_manifest.v1",
 "stage_id":"STAGE_01_CRACKED_SEAL_ROAD",
 "stage_name":"금 간 봉인길",
 "generated_with":"built-in image generation + free local Pillow tools",
 "external_ai_api_used":False,
 "existing_monsters_regenerated":False,
 "unity_handoff":"BLOCKED_PENDING_USER_APPROVAL",
 "bundles":bundles,
 "local_qa":{"bundle_manifests_pass":all(x["overall_pass"] for x in bundles),
             "exact_chroma_residue_pass":not residue_fail,
             "gif_6fps_pass":not gif_fail,
             "residue_failures":residue_fail,"gif_failures":gif_fail,
             "asset_count":len(assets)},
 "assets":assets,
}
master["overall_pass"]=all((master["local_qa"]["bundle_manifests_pass"],master["local_qa"]["exact_chroma_residue_pass"],master["local_qa"]["gif_6fps_pass"]))
out=ROOT/"05_sprites/work/STAGE01_IMAGE_PACKAGE_QA_MANIFEST.json"
out.write_text(json.dumps(master,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"manifest":str(out),"overall_pass":master["overall_pass"],"local_qa":master["local_qa"]},ensure_ascii=False,indent=2))
