# Unity Approved Asset Bridge

이 브리지는 기존 Unity 게임 코드를 직접 수정하지 않고 승인된 16프레임 에셋을 별도 패키지로 전달한다.

## 안전 조건

- manifest 상태가 `APPROVED`
- Sprite QA 결과가 `PASS`
- PNG 체크섬이 manifest와 일치
- 16프레임 그리드와 Unity 리소스 이름이 유효

## 패키지 생성

```powershell
docker compose exec api python -m app.unity_bridge `
  /workspace/manifests/CHR_EXAMPLE_WALK.json `
  /workspace/05_sprites/qa/CHR_EXAMPLE_WALK/qa_result.json `
  /workspace/06_game/approved_imports `
  --resource-name ExampleWalk --fps 12 --pixels-per-unit 200
```

생성된 에셋 폴더와 `request.json`을 Unity의 `Assets/Game/ApprovedImports/<asset_id>`에 복사한다. `ApprovedAssetImporter.cs`는 Unity 프로젝트의 `Assets/Game/Editor`에 추가한다.

Unity 메뉴 `Tools > Game Production > Import Approved Assets`를 실행하면 다음을 생성한다.

- `Assets/Game/Resources/Sprites/<resource_name>.png`
- `Assets/Game/Resources/Animation/Approved/<resource_name>.anim`
- `Build/Reports/approved-import-<asset_id>.json`

기존 Animator나 게임 상태 코드는 자동으로 덮어쓰지 않는다. 실제 연결은 `게임개발` 채팅에서 런타임 화면을 확인하며 수행한다.
