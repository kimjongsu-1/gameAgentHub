# 테스트버전

포트폴리오 확인용으로 선별한 대표 산출물입니다. 전체 작업 산출물 중에서 이미지 후처리, 스프라이트 시트화, GIF 미리보기, 런타임 리포트 흐름을 가장 짧게 보여주는 파일만 추렸습니다.

## 포함 파일

### assets

- `hero_base_clean.png`
  - 크로마키 제거 및 투명화가 완료된 캐릭터 기준 이미지
- `hero_walk_8f_sheet.png`
  - 캐릭터 8프레임 걷기 스프라이트 시트
- `monster_base_clean.png`
  - 크로마키 제거 및 투명화가 완료된 몬스터 기준 이미지
- `monster_walk_8f_sheet.png`
  - 몬스터 8프레임 걷기 스프라이트 시트

### gifs

- `hero_walk_8f_6fps.gif`
  - 캐릭터 걷기 6fps 미리보기
- `monster_walk_8f_6fps.gif`
  - 몬스터 걷기 6fps 미리보기

### captures

- `motion_validation_capture.png`
  - 로컬 검증 화면 캡처

### reports

- `unity_character_monster_runtime_report.json`
  - 캐릭터/몬스터 런타임 검증 리포트 예시
- `unity_subset_motion_report.json`
  - 부분 모션 검증 리포트 예시

## 이 폴더의 목적

전체 개발 산출물을 모두 열어보지 않아도 다음 기술 흐름을 빠르게 확인할 수 있도록 구성했습니다.

```text
생성 이미지
→ 로컬 후처리
→ 투명 PNG
→ 8프레임 스프라이트 시트
→ 6fps GIF 미리보기
→ 런타임 검증 리포트
```

이 폴더는 데모/포트폴리오용 축약본이며, 원본 작업 파일은 각 작업 디렉터리에 보존되어 있습니다.
