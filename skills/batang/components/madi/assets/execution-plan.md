# 상세 실행 계획

acceptance는 관찰 가능한 완료 기준이다. 계획의 예상 명령과 결과를 실제 실행 결과로 기록하지 않는다.

- plan_id / run_id / 작성자:
- 상태: `draft` / `PLAN_READY` / `superseded`
- 대상 프로젝트 / 요청·승인 범위:
- 목표 / 제약 / 제외:
- 작업 분류: `development` / `docs-only` / 근거:
- 기존 run·기존 API 요구의 보존 경계:
- vault·활성 목록·Graphify·Archify 전제와 실제 권한:
- profile·bundle identity·단일 skill과 내부 마디 절차의 고정 checkout 경로:
- 공개 package를 만드는 작업이면 개발 원본·허용 목록·staging 경로 / 제외할 로컬 기록 / 고정 manifest·checksum hash:
- checker 권장 규약 선택 기록 / 대상 프로젝트 정책 경로·hash / 기존 전역·프로젝트 규약과의 충돌·drift 확인:
- 품질 검토는 일반 모드 `gpt-6.1-sol/high`인지 확인 / 보안 검토는 Daybreak 접근·호환·모드 확인 시 `gpt-6-sol/high`, 접근 불가 시 일반 `gpt-6.1-sol/high` 선택 / 어느 경로든 고정 최종 후보 전체 독립 검토:

| 요구 ID | 요구·관찰 가능한 acceptance | 검증 ID·방법·환경·예상 결과 |
|---|---|---|
| R1 |  |  |

| 작업 ID | 단계·작업 | 담당 역할·소유 파일 | 입력 → 산출물 | 의존 | 연결 요구·검증 | 검증 담당 | 적용 여부·이유 |
|---|---|---|---|---|---|---|---|
| T1 |  |  |  |  |  |  | `required` / `excluded` |

- 차단 미정:
- 비차단 질문: 내용 / 담당 / 해결 시점 / 착수를 막지 않는 이유:
- v1 검증 분류 결정: 실제 구성요소 실행이 필요한가? / 경계 우회·취약 동작 재현 자체가 필요한가? / check별 category·rationale·residual_uncertainty / 재현이면 real_components_insufficient_reason:
- v1 실행 경계: check별 status·authority_basis·scope / `recorded`는 호스트 기록일 뿐 실제 권한 인증·플랫폼 승인 아님 / `needs_confirmation`·`blocked`이면 해당 check PASS 불가:
- 방어 검증 흐름: 정적 위험 → 관찰 가능한 방어 조건 → 수정 → `code_conditions` 또는 격리된 `real_components` 기능 시험 → 충분성 검토:
- 예외적 공격 재현 제안(해당 시): 방어 검증만으로 부족한 이유 / 구체 범위 / 사전 사용자 질문·동의 / 플랫폼 허용 / 기본 계획의 자동 check 생성 금지:
- 부정 이력 보존: 기존 FAIL·BLOCKED·NOT_RUN, 검토 request_changes·blocked와 finding의 category·scope를 누락·변경하지 않음:
- 중단·재분해 조건 / 재개 입력:
- 근거 예정 위치:
- 로컬 검증 기록·실패 이력의 보존 위치:
- 사용자 검토 표시: 승인 범위·영향·상태·위험·미정·미검증·상세 링크:
- 후속 구현 권한 여부와 근거:

## PLAN_READY 판단

- [ ] 모든 요구가 작업·담당·소유 파일 또는 명확한 모듈 경계·의존성과 연결됨
- [ ] 모든 acceptance에 검증 담당·방법·환경·관찰할 결과가 있음
- [ ] 착수 차단 미정 0, 비차단 질문의 담당·시점·이유 명시
- [ ] 기존 run과 API 요구를 자동 이관하지 않는 경계가 기록됨
- [ ] vault·활성 목록·Graphify·Archify의 사용자 권한과 `BLOCKED` 조건이 기록됨
- [ ] 단일 skill과 내부 마디 절차의 경로, SHA256SUMS 기반 bundle identity·profile hash 고정 방법이 있음
- 판정 / 판정자 / 실제 관찰 근거:

이 체크리스트는 호스트의 계획 판단 보조다. 기계적으로 `PLAN_READY`, `TASK_DONE`, `RELEASE_READY`를 판정하거나 전환하지 않는다.
