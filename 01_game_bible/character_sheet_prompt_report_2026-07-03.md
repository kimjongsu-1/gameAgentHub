# 캐릭터 시트 생성 프롬프트 보고서

작성일: 2026-07-03

## 목적
- 지금까지 이 채팅에서 사용한 남자 주인공 캐릭터 시트 생성 프롬프트를 정리한다.
- 제미나이 나노바나나에서 동일한 주인공 느낌으로 캐릭터 시트 생성을 테스트할 수 있게 한다.

## 목표 캐릭터 요약
- 현대 한국 판타지 분위기의 남자 주인공
- 치비 비율
- 쿼터뷰
- 검은 머리
- 검은 후드 집업
- 검은 이너
- 검은 바지
- 검은 운동화
- 무표정에 가까운 차분한 인상
- 모바일 방치형 RPG에 맞는 가독성 높은 실루엣

## 대표 참조 이미지
- 단일 캐릭터 원본:
  [hero_base_clean_v03.png](/C:/Users/kukl3/Documents/게임%20개발%20프로젝트/05_sprites/style_validation_quarter_idle_v03_clean16/hero_base_clean_v03.png)
- 최근 8프레임 캐릭터 걷기 시트:
  [hero_walk_8_v07_sheet.png](/C:/Users/kukl3/Documents/게임%20개발%20프로젝트/05_sprites/style_validation_quarter_idle_v03_clean16/hero_walk_8_v07_sheet.png)

## 실제 사용했던 핵심 프롬프트

### 1. 단일 캐릭터 원본 생성
```text
Create one single clean game sprite concept for a chibi quarter-view male fantasy hunter hero, Korean modern-fantasy vibe, black hoodie, dark pants, compact readable silhouette, neutral standing pose, facing front-right, polished 2D mobile idle RPG style, thick outline, transparent background, centered, no extra characters, no duplicated figure, no text, no checkerboard pattern baked in.
```

### 2. 16프레임 걷기 시트 생성
```text
Create a professional 2D game sprite sheet for a chibi quarter-view male hunter hero walk cycle. 16 frames arranged in a 4x4 grid. Absolute requirements: every frame must show the same character at exactly the same scale, same camera distance, same body proportions, same head size, same baseline foot height, same full-body framing, and the character must stay centered inside each frame. Only the pose changes for walking. Large transparent padding around the character in every frame. No frame overlap, no extra fragments, no duplicated stray parts, no text, no checkerboard baked in. Korean modern fantasy vibe, black hoodie, dark pants, polished mobile idle RPG art, thick outline, facing front-right.
```

### 3. 8프레임 걷기 시트 생성
```text
Create a professional 2D game sprite sheet for a chibi quarter-view male hunter hero WALK cycle only. 8 frames arranged in a 4 columns by 2 rows grid. Every frame must be a true walking pose with one foot advancing or passing; no idle, no standing-neutral foot placement anywhere. Absolute requirements: same character scale, same body proportions, same head size, same camera distance, same baseline foot height, same centered full-body framing, same clothing details in every frame. Large transparent padding in every frame. Korean modern fantasy vibe, black hoodie, dark pants, polished mobile idle RPG art, thick outline, facing front-right. Transparent background only, no checkerboard baked in, no text, no stray fragments, no frame overlap.
```

### 4. 8프레임 걷기 시트 보정 프롬프트
```text
Create a professional 2D game sprite sheet for a chibi quarter-view male hunter hero WALK cycle only. 8 frames arranged in a 4 columns by 2 rows grid. Critical correction: frame 1 must also be a walking contact pose, not a neutral standing pose. In all 8 frames, at least one leg must clearly be stepping forward or passing. No idle or standing frames anywhere. Absolute requirements: same character scale, same body proportions, same head size, same camera distance, same baseline foot height, same centered full-body framing, same clothing details in every frame. Large transparent padding in every frame. Korean modern fantasy vibe, black hoodie, dark pants, polished mobile idle RPG art, thick outline, facing front-right. Transparent background only, no checkerboard baked in, no text, no stray fragments, no frame overlap.
```

## 나노바나나 테스트용 최종 권장 프롬프트

아래 프롬프트를 그대로 먼저 테스트하는 것을 권장한다.

```text
Create a professional 2D game sprite sheet for one chibi quarter-view male protagonist walk cycle.

Character identity:
- Korean modern fantasy male protagonist
- black medium-length parted hair
- calm serious expression
- black zip-up hoodie
- black inner shirt
- black cargo-style pants
- black sneakers
- compact readable silhouette for a mobile idle RPG

Sprite sheet requirements:
- 8 frames only
- 4 columns by 2 rows
- every frame must be a true walking pose
- no idle pose
- no neutral standing pose
- frame 1 must also be a walking contact pose
- at least one leg must clearly advance or pass in every frame
- clear alternating leg stride and arm swing

Consistency requirements:
- same character in every frame
- exactly the same scale in every frame
- exactly the same body proportions in every frame
- exactly the same head size in every frame
- exactly the same camera distance in every frame
- exactly the same baseline foot height in every frame
- exactly the same centered full-body framing in every frame
- same costume details in every frame
- same face design in every frame
- same hair shape and silhouette in every frame

Layout requirements:
- large transparent padding inside every frame
- no frame overlap
- no extra fragments
- no duplicated stray parts
- no text
- no watermark
- no checkerboard baked into the background
- transparent background only

Art direction:
- polished 2D mobile idle RPG sprite art
- thick clean outline
- soft cel shading
- readable game-production-ready pose silhouettes
- facing front-right quarter view
```

## 나노바나나용 짧은 보정 프롬프트

첫 결과가 흔들리거나 서있는 포즈가 섞이면 아래 보정 문장을 추가한다.

```text
Correction:
- remove all idle-looking frames
- do not use any standing-neutral pose
- keep the same character size across all 8 frames
- keep the feet aligned to the same baseline
- keep the head size identical across all frames
- only change pose, never change scale
```

## 참조 이미지와 함께 넣을 때 추천 문장

원본 캐릭터 이미지를 같이 넣고 싶다면 아래 문장을 프롬프트 앞부분에 추가한다.

```text
Use the attached reference image as the identity reference for the protagonist.
Keep the same hairstyle, same outfit, same face feeling, and same overall silhouette.
Do not redesign the character into a different person.
Only convert this exact character into a consistent 8-frame walk cycle sprite sheet.
```

## 실패 패턴
- 첫 프레임이나 마지막 프레임이 서있는 포즈로 바뀜
- 2행 일부 프레임에서 크기가 작아지거나 커짐
- 머리 크기가 프레임마다 달라짐
- 발 기준선이 흔들려서 위아래로 튐
- 프레임 밖 조각이 남음
- 체크보드 배경이 실제 그림에 포함됨

## 재시도 지시 예시

```text
Retry with stricter consistency.
Do not change character scale between frames.
Do not include any idle frame.
All 8 frames must be walking poses only.
Keep the feet aligned to one exact baseline.
Keep the same head size and same body width across the whole sheet.
```

## 참고
- 이 문서는 캐릭터 시트 생성 기록과 제미나이 나노바나나 테스트용 프롬프트를 함께 정리한 파일이다.
- 모델 특성상 완전 동일한 캐릭터가 한 번에 나오지 않을 수 있으므로, 참조 이미지를 함께 넣는 것이 가장 안정적이다.
