# PM 라우팅 구조

현재 구조에서 총괄 PM은 `game_production_pm` MCP 서버입니다.

중요한 점은 MCP PM이 채팅창을 직접 조작하는 방식이 아니라, 허브에 작업과 dispatch 지시서를 만들고 Codex 쪽 dispatcher가 그 지시서를 기존 채팅창으로 전달하는 구조라는 점입니다.

```text
Codex 오케스트라
  ↓ MCP tool 호출
game_production_pm MCP 서버
  ↓ 로컬 허브 API 호출
FastAPI Hub / DB / Dashboard
  ↓ 승인된 dispatch 생성
Codex Dispatcher
  ↓ 기존 thread_id로 prompt 전송
작업 채팅창
  - 게임 개발 기획
  - 게임 개발 디자인
  - 게임개발
```

## 역할

| 구성 요소 | 역할 |
| --- | --- |
| `game_production_pm` MCP | 작업 생성, 상태 조회, 중지/재개, dispatch 준비 |
| FastAPI Hub | DB, 대시보드, 승인, QA, dispatch 큐, 런타임 보고서 보관 |
| Codex Dispatcher | dispatch 큐의 prompt를 기존 Codex 채팅창으로 전달 |
| Worker Chat | 기획, 디자인, 게임개발 작업 수행 |

## 현재 운영 모드

- Dispatcher 자동화는 사용자가 중지했다.
- 따라서 dispatch 처리는 사용자가 명시적으로 요청할 때만 수동으로 진행한다.
- `game_development`는 사용자가 “게임개발 시작”이라고 말할 때까지 `PAUSED`로 둔다.
- `planning_research`는 아직 실제 thread_id가 없어 dispatch는 차단되고 handoff package 생성만 가능하다.

## 기획 연결 완료 조건

`config/agents.json`의 `planning_research.thread_id`를 실제 `게임 개발 기획` 채팅 ID로 교체해야 한다.

그 전까지 PM은 기획 작업 명세를 만들 수 있지만, 실제 기획 채팅창으로 자동 전달하지 않는다.
