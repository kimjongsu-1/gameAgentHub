# PM 라우팅 구조

현재 구조에서 총괄 PM 역할은 `game_production_pm` MCP 서버와 로컬 FastAPI 허브가 함께 담당한다.

중요한 점은 MCP PM이 Codex 채팅창을 직접 조작하는 방식이 아니라는 것이다. MCP PM은 허브 API를 통해 작업, 상태, 승인, dispatch 지시서를 만들고, 실제 채팅 전달은 사용자가 명시적으로 요청했을 때 Codex dispatcher가 처리한다.

```text
User
  ├─ 기획/자료조사 직접 작성
  v
Current Codex PM chat
  └─ MCP tool 호출
game_production_pm MCP server
  └─ Local FastAPI Hub API 호출
FastAPI Hub / DB / Dashboard
  ├─ 작업 상태 관리
  ├─ 무료 로컬 QA 실행/기록
  ├─ 사용자 승인 관리
  └─ dispatch 지시서 생성
Codex Dispatcher
  └─ 사용자가 허가한 dispatch만 기존 worker chat으로 전달
Worker chats
  ├─ 게임 개발 디자인
  └─ 게임개발
```

## 역할

| 구성 요소 | 역할 |
| --- | --- |
| User | 기획과 자료조사를 직접 수행하고 최종 승인한다. |
| Current Codex PM chat | 사용자의 지시를 받아 PM 판단과 파이프라인 운영을 진행한다. |
| `game_production_pm` MCP | 허브 API를 호출하는 PM tool 표면이다. |
| FastAPI Hub | DB, 대시보드, 승인, 무료 로컬 QA, dispatch 큐, 런타임 보고서를 관리한다. |
| Design Orchestra | 캐릭터 디자인, 16프레임 스프라이트, 애니메이션 소스 제작을 담당한다. |
| Local Free QA | Sprite QA, GIF 미리보기, 컨택트시트, 어니언스킨, 런타임 보고서 검사를 담당한다. |
| Game Development | 사용자가 게임개발 시작을 허가한 뒤 승인 에셋만 Unity에 적용한다. |

## 현재 운영 모드

- `planning_mode = user_direct`
- `repeated_qa_mode = free_local_tools`
- `external_ai_calls_enabled = false`
- Dispatcher 자동화는 사용자가 요청할 때만 수동으로 처리한다.
- `game_development`는 사용자가 “게임개발 시작”이라고 말하기 전까지 진행하지 않는다.

## 공식 흐름

```text
사용자 직접 기획
→ 총괄 PM 작업 지시서 정리
→ 게임 개발 디자인
→ 무료 로컬 반복 QA
→ 사용자 승인
→ 게임개발
```

기획/자료조사 전용 worker는 제거되었다. PM은 사용자가 제공한 기획을 정리하고 전달할 뿐, 별도 기획 채팅으로 자동 dispatch하지 않는다.
