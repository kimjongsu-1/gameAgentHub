# 아키텍처

```text
사용자
  |
  v
현재 오케스트레이터 ----> 작업/승인/API 비용 DB
  |                              |
  +----> 게임 개발 디자인        +----> 로컬 대시보드
  |         |
  |         +----> 16프레임 + manifest + QA 미리보기
  |                              |
  +<-----------------------------+
  |
  +---- 사용자 승인 ----> 게임개발 ----> Unity 런타임 캡처
```

## 경계

통합 허브는 상태와 전달 계약을 관리한다. Codex 채팅 자체의 대화 기록이나 이미지 바이너리를 DB에 복제하지 않는다. 오케스트레이터가 채팅 고유 ID를 이용해 작업을 전달하고, 결과 파일은 manifest 경로로 참조한다.

## 상태 전이

```text
PLANNED -> READY -> RUNNING
RUNNING -> DESIGNING -> SPRITE_GENERATING -> QA_RUNNING
QA_RUNNING -> REVISION_REQUIRED -> DESIGNING
QA_RUNNING -> WAITING_USER_APPROVAL -> APPROVED
APPROVED -> INTEGRATING -> RUNTIME_QA -> COMPLETED
모든 실행 상태 -> WAITING_API_RESET | WAITING_BUDGET_RESET | FAILED
```

상태 전이는 API에서 허용 목록을 검사한다. 단계별 세부 전이 제약은 2단계 작업 스케줄러에서 추가한다.
