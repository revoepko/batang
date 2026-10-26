# 프로젝트 프로필

프로필은 프로젝트별 조정값을 기록하지만 새 권한을 만들지 않는다. 실제 값이 없으면 `미정: 이유·담당·해결 시점`으로 남긴다.

- project_id / owner:
- profile_version / status / reviewed_at:
- verification_policy_version: 선택 `1`; 없으면 기존 `check_scope` 계약을 유지:
- 목표 / 포함 범위 / 제외 범위:
- 로컬 정책·승인 근거 / 금지 행동:
- `knowledge_root` 절대 경로 / `active_index` root 기준 상대 경로:
- `backup_root` / Graphify 실제 실행 위치 / `graph_output`:
- vault 읽기·쓰기 권한 / 활성 목록 생성·수정에 필요한 사용자 승인:
- Archify 실제 실행 위치 / 요청된 설명 산출물 범위:
- 스킬 실제 경로 기준: Batang `skills/batang` / 내부 마디 절차 `skills/batang/components/madi/workflow.md`가 같은 고정 checkout인지:
- checkout root `SHA256SUMS` 경로 / 검증 후 bundle identity(SHA256SUMS 자체 SHA-256) / 새 run 고정 경로:
- 관리 방식: `common-managed` / `independent-fork`; 기존 profile 이행 여부·근거:
- 현재 pin / 기존 run snapshot / 자동 전환 금지 근거:
- 설치 시 checker 권장 규약 선택: `기존 규약 유지` / `대상 프로젝트 적용` / `미선택`; 제시한 대상·정확한 변경안·충돌·사용자 선택 근거:
- 선택 적용한 프로젝트 정책의 실제 경로·변경 전후 SHA-256; 미적용이면 변경 없음 / 기존 전역 규약 보존:
- 필수 단계 / 제외 단계·이유·근거:
- 필수 acceptance / 검증 방법·허용 환경:
- v1 검증 분류 기준: 실제 구성요소 실행 필요 여부 / 경계 우회·취약 동작 재현 필요 여부 / `exploit_reproduction`의 `real_components_insufficient_reason`:
- v1 실행 경계: `recorded` / `needs_confirmation` / `blocked`; authority_basis / scope; 기록은 실제 권한 인증·플랫폼 승인 아님:
- 보안 검증 기본값: 정적 위험·방어 조건·수정·`code_conditions` 또는 격리된 `real_components` 기능 시험·충분성 검토:
- 예외적 공격 재현: 기본 check 자동 생성 금지 / 방어 검증 불충분 이유·구체 범위·사전 사용자 질문·동의·플랫폼 허용:
- 릴리즈 적용 여부 / 게이트 / 위험 예외 승인 주체:
- 품질·보안 검토 경로: `quality_checker` 일반 모드 `gpt-6.1-sol/high` 여부 / Daybreak의 실제 접근·호환·모드 / 보안 `gpt-6-sol/high` 또는 일반 `gpt-6.1-sol/high` 선택 / 동일 후보 전체 범위 확인:
- 차단 미정 / 비차단 질문·담당·시점:

| 역할 | 책임·파일 범위 | provider | model | invocation·가용성 | 배정 근거 |
|---|---|---|---|---|---|
| planner |  |  |  |  |  |
| quality_checker | 정합성·상태 전이·운영 계약; 일반 모드 |  | gpt-6.1-sol/high |  |  |
| security_checker_daybreak 또는 동등한 호스트 호출 | 접근·모드 확인 후 고정 최종 후보 전체 독립 읽기 전용 보안 검토 |  | gpt-6-sol/high |  |  |
| security_checker 또는 동등한 호스트 호출 | Daybreak 접근 불가 시 일반 모드로 동일 후보 전체 독립 읽기 전용 보안 검토 |  | gpt-6.1-sol/high |  |  |

부모만 서브에이전트를 생성하며 깊이는 1이다. 실제 provider·model·일반/Daybreak 모드와 호출 가능 여부는 호스트에서 확인한다. 이 표는 모델 선택 기준이며 패키지가 호출기나 Daybreak 권한을 제공한다는 뜻이 아니다. 접근 거부 뒤 일반 경로를 선택하면 기존 오류를 보존한다. 필수 검토를 수행할 수 없으면 해당 게이트를 `BLOCKED`로 기록한다.
