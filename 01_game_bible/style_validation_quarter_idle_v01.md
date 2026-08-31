# 스타일 검증 샘플 저장본 V01

## 목적
- 기존 게임 설정과 리소스는 건드리지 않고, 방치형에 맞춘 단순화된 쿼터뷰 전투 연출을 별도 샘플로 검증한다.

## 이번 샘플 구성
- 캐릭터 1개: `quarter_hero_hunter_v01.png`
- 몬스터 1개: `quarter_monster_dokkaebi_v01.png`
- 맵 1개: `quarter_stage_shrine_v01.png`

## 검증 방향
- 화면 가독성을 우선한다.
- 맵은 정보량을 줄이고 전투 중심부가 비어 보이도록 유지한다.
- 캐릭터는 작은 화면에서도 실루엣이 바로 읽히는 형태를 유지한다.
- 몬스터는 색과 외곽선 대비로 위협도를 확보한다.
- 애니메이션은 프레임 수보다 포즈 차이와 상하 이동 연출로 효율을 확보한다.

## 저장 위치
- 원본 보관: `C:\Users\kukl3\Documents\게임 개발 프로젝트\05_sprites\style_validation_quarter_idle_v01`
- 유니티 테스트 적용처: `C:\game\character_pipeline\IdleBattleUnity_SubsetTest_20260701`

## 유니티 테스트 리소스명
- 영웅: `Resources/Sprites/TestQuarterHeroHunterV01`
- 몬스터: `Resources/Sprites/TestQuarterMonsterDokkaebiV01`
- 맵: `Resources/Maps/TestQuarterStageShrineV01`

## 판별 기준
- 캐릭터와 몬스터가 한 화면에서 겹치지 않고 읽히는가
- 맵이 과하게 튀지 않고 전투 중심을 받쳐주는가
- 방치형 기준으로 연출이 가볍고 반복 재생에 무리가 없는가
