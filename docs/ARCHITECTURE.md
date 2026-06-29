# 아키텍처

```text
사용자
  |
  |  기획/자료조사 직접 입력
  v
현재 Codex 총괄 PM 채팅
  |
  |  MCP tool 호출
  v
game_production_pm MCP 서버
  |
  |  로컬 API 호출
  v
FastAPI 통합 허브 / DB / Dashboard
  |
  +--> 게임 개발 디자인 채팅
  |      |
  |      +--> 캐릭터 디자인 / 16프레임 스프라이트 / manifest
  |
  +<-- 결과 파일 경로와 승인 요청
  |
  +--> 무료 로컬 반복 QA
  |      |
  |      +--> Sprite QA / GIF / 컨택트시트 / 어니언스킨 / 런타임 보고서
  |
  +--> 사용자 승인
  |
  +--> 게임개발 채팅
         |
         +--> 사용자가 게임개발 시작을 허가한 뒤 Unity 적용
```

## 핵심 정책

- 기획/자료조사는 사용자가 직접 수행한다.
- PM은 사용자의 기획을 작업 지시서로 정리한다.
- 반복 검사는 무료 로컬 도구를 우선 사용한다.
- 외부 AI API는 기본 차단한다.
- 승인되지 않은 에셋은 게임개발로 전달하지 않는다.
- 게임개발은 사용자가 명시적으로 시작을 허가하기 전까지 진행하지 않는다.

## 상태 전이

```text
PLANNED -> READY -> RUNNING
RUNNING -> DESIGNING -> SPRITE_GENERATING -> QA_RUNNING
QA_RUNNING -> REVISION_REQUIRED -> DESIGNING
QA_RUNNING -> WAITING_USER_APPROVAL -> APPROVED
APPROVED -> INTEGRATING -> RUNTIME_QA -> COMPLETED
모든 실행 상태 -> WAITING_API_RESET | WAITING_BUDGET_RESET | FAILED | PAUSED
```

## 무료 로컬 QA 범위

- 16프레임/그리드 검사
- GIF 미리보기 생성
- 컨택트시트 생성
- 어니언스킨 생성
- 투명도/배경 기초 검사
- Unity 런타임 보고서 등록

로컬 QA는 기술 검사에 집중한다. 미적 판단, 재미 판단, 캐릭터 매력 판단은 사용자 승인 단계에서 처리한다.
