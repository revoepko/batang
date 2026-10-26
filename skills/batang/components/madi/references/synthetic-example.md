# 완성된 합성 예시: Markdown 근거 기반 계획

이 문서의 사용자·경로·결정·상태는 형식 설명용 합성 자료다. 실제 vault, 설치, 모델 호출, 검증 결과, 공개 승인으로 사용하지 않는다.

## 요청과 전제

가상 요청 `U-DEMO`: “사용자가 지정한 Markdown 목록을 검토하는 계획을 작성해 줘. 설치나 vault 생성은 하지 마.”

가상 프로젝트 설정은 `knowledge_root`와 root 기준 `active_index`를 제공한다. 목록에는 두 Markdown 경로만 있고 vault 전체 탐색 권한은 없다. Graphify와 Archify의 실행 위치는 설정돼 있으며, 이 계획은 설명 산출물을 요청하지 않는다.

## 계획 요약

- `D1` `user_confirmed`: 지정 목록의 두 파일만 읽는다. vault·목록·Graphify 결과는 수정하지 않는다.
- `D2` `delegated_ai`: 새 run이면 단일 bundle snapshot의 `skills/batang`과 내부 마디 절차 경로, `SHA256SUMS` 자체의 hash, profile hash를 기록한다.
- `A1` `assumption`: Graphify의 준비 상태는 호스트에서 확인해야 한다. 경로를 확인하지 못하면 준비는 `BLOCKED`이고 다른 도구를 설치하거나 찾지 않는다.

| 요구 | acceptance | 예정 검증 |
|---|---|---|
| R1 | 지정 목록 외 문서를 자동 편입하지 않는다 | 목록·경로를 검토해 대상 두 파일만 기록 |
| R2 | 기존 vault와 활성 목록을 변경하지 않는다 | 실행 전후 실제 호스트 관찰로 변경 여부를 확인 |
| R3 | 설치·link 전환·rollback을 수행하지 않는다 | 계획 범위와 실행 명령을 대조 |

계획 담당자는 요구·소유·acceptance·검증 방법이 연결됐다는 근거를 확인한 뒤에만 계획 상태를 기록한다. 이 예시는 어떤 상태도 자동 판정하지 않는다. 작업 완료와 릴리즈 준비는 별도 근거가 필요하다.

기존 API가 필요한 가상 run이 발견되면 그 run의 지침·snapshot·기록을 보존한다. 공개판 bundle로 자동 이관하지 않는다. 일반 지식 작업에는 내부 마디 절차를 강제하지 않는다.
