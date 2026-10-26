# 실행 기록

run은 한 번의 작업 실행 기록이다. 설치 link, 세션에서 실제 읽은 경로, run이 고정한 snapshot을 각각 기록하고 혼동하지 않는다.

- run_id / previous_run / 시작·종료 시각:
- 대상 revision 또는 파일별 SHA-256 목록:
- bundle identity: 검증한 root `SHA256SUMS` 파일의 SHA-256 / 단일 Batang skill 및 내부 마디 절차의 실제 checkout 경로 / 저장된 profile 파일 경로와 해당 bytes의 SHA-256:
- 공개 package를 만드는 작업이면 개발 원본 revision·hash / 승인 allowlist / 공개 버전 / 공개 변경 요약 / 지원 환경 / 의존성 버전·revision:
- 공개 release 후보 연결값: `candidate-manifest.json` hash / archive hash / staging 경로 / 개발 원본 revision·hash와 공개 버전 연결 근거. 이는 checkout bundle identity와 별개이며 기존 기록을 덮지 않는다:
- 외부 게시 후 로컬 기록: 공개 버전·tag / 게시 URL / 게시 시각 / 실제 결과:
- 현재 단계 / 작업 상태:
- 요청·권한 근거 / 결정 기록 / 계획 위치:
- vault·활성 목록·Graphify·Archify의 실제 접근 범위와 관찰:
- 실제 역할·provider·model·invocation:
- 품질 검토의 실제 일반 모드 `gpt-6.1-sol/high` / 보안 검토의 Daybreak `gpt-6-sol/high` 또는 일반 `gpt-6.1-sol/high` 선택, 접근·호환·모드 판단과 실패·후속 경로 이력:
- verification_policy_version / legacy 여부:
- 기존 API 필수 run 또는 다른 snapshot과의 관계 / 자동 전환 여부: 없음 / 별도 승인:
- 설치 시 checker 권장 규약 선택 / 대상 프로젝트 정책의 실제 경로·SHA-256 / 현재 내용과의 drift·충돌 / 재확인 결과:

| 작업·검증 ID | 적용 여부·제외 근거 | 진행 상태 | 검토 판정 | 검증 결과 | 대상·근거 ID | 유효성 |
|---|---|---|---|---|---|---|
|  | `required` / `excluded` | `pending` / `active` / `blocked` / `done` | `approve` / `request_changes` / `blocked` / 공란 | `PASS` / `FAIL` / `BLOCKED` / `NOT_RUN` |  | `current` / `stale` |

## 근거

- evidence_id / acceptance ID / 대상 / 시각:
- 명령 또는 검토 체크리스트 / 환경 / exit:
- 독립 검토별 고정 최종 후보 manifest hash / 전체 대상 범위 / 검토 역할·모델·모드 / 판정·finding·미검증:
- 로컬 검증 결과·실패 이력의 저장 위치 / 공개 package와의 분리 확인:
- 실제 관찰 / 로그 위치 / 미검증 범위:
- v1 verification: category / rationale / residual_uncertainty / exploit이면 real_components_insufficient_reason:
- v1 execution_boundary: status / authority_basis / scope / execution_authorization=`NOT_VERIFIED`(호스트 기록이며 실제 권한 인증·플랫폼 승인 아님):
- 방어 검증 연결: 정적 위험 / 관찰 가능한 방어 조건 / 수정 / `code_conditions` 또는 격리된 `real_components` 기능 시험 / 충분성 검토:
- 예외적 공격 재현(해당 시): 방어 검증 불충분 이유 / 구체 범위 / 사전 사용자 질문·동의 / 플랫폼 허용:
- 결과와 근거 유효성 / stale 이유:
- finding: ID / 위치 / 영향 / 근거·확실성 / 담당 / 해결·재검증:
- 시도 이력: 원인·행동·결과 / 이전 실패·차단 기록:
- 부정 이력 연결: 기존 검증 FAIL·BLOCKED, 검토 request_changes·blocked 또는 finding의 check ID / 보존한 category·scope / NOT_RUN 이력(PASS 위조 금지):
- 완료 수준: `PLAN_READY` / `TASK_DONE` / `RELEASE_READY` / 미달:
- 완료 판단 근거 / 남은 차단·미검증 / 다음 행동·담당:

상태값은 호스트가 실제 근거를 읽어 기록한다. 이 양식은 상태 자동 검사기나 설치·배포·릴리즈 권한을 제공하지 않는다. 정적 package 검사는 호스트 통합 동작의 증거가 아니다.
