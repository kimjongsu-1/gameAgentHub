# 스타일 검증 샘플 저장본 V03

## 목적
- 기존 전투 흐름은 유지한다.
- 캐릭터/몬스터 시트만 재제작한다.
- 각 모션을 16프레임으로 통일한다.
- 프레임 내부에 다른 이미지가 섞이지 않도록 넓은 셀로 분리한다.
- 프레임 재생 시 좌우/상하 흔들림이 적도록 발 기준점을 고정한다.

## 구성
- 캐릭터 `서있기`: `quarter_hero_idle_16_v03.png`
- 캐릭터 `걷기`: `quarter_hero_walk_16_v03.png`
- 캐릭터 `공격`: `quarter_hero_attack_16_v03.png`
- 몬스터 `서있기`: `quarter_monster_idle_16_v03.png`
- 몬스터 `걷기`: `quarter_monster_walk_16_v03.png`
- 몬스터 `공격`: `quarter_monster_attack_16_v03.png`
- 몬스터 `히트`: `quarter_monster_hit_16_v03.png`

## 적용 규칙
- 모든 시트는 4x4, 총 16프레임
- 각 프레임 셀은 넓게 확보
- 맵과 전투 반복 로직은 기존 테스트 흐름 유지
- 위치 이동 중 불필요한 상하 출렁임 제거

## 유니티 리소스명
- `Resources/Sprites/TestQuarterHeroIdle16V03`
- `Resources/Sprites/TestQuarterHeroWalk16V03`
- `Resources/Sprites/TestQuarterHeroAttack16V03`
- `Resources/Sprites/TestQuarterMonsterIdle16V03`
- `Resources/Sprites/TestQuarterMonsterWalk16V03`
- `Resources/Sprites/TestQuarterMonsterAttack16V03`
- `Resources/Sprites/TestQuarterMonsterHit16V03`
- `Resources/Maps/TestQuarterStageShrineV03`
