# 마디 실행 계약

이 계약은 명시적으로 선택한 개발·문서·도면 작업의 기본값이다. 사용자 지시와 프로젝트 고유 계약이 우선한다. 이 패키지는 실행기나 진행 상태 API가 아니라 작업·근거 기록 방식이다.

## 경계와 시작

프로젝트 `AGENTS.md`, 승인 범위, 기존 profile/run과 실제 호스트 규약을 먼저 읽는다. 기존 API 기반 run, 현재 설치, 운영 vault와 기존 pin은 자동 변환하거나 수정하지 않는다. 새 run은 한 고정 checkout revision의 Batang skill과 `components/madi/workflow.md` 경로를 고정한다. 진행 중 run이 사용하는 실제 파일은 해당 경로와 hash가 고정된 동안 수정·갱신하지 않는다. 갱신은 기존 checkout을 당겨 바꾸는 대신 새 checkout 또는 새 고정 디렉터리를 준비하고 새 run에서 선택한다. Checkout root `SHA256SUMS`는 파일별 SHA-256 목록이다. 목록에 적힌 모든 파일을 확인한 뒤 `SHA256SUMS` 파일 자체의 SHA-256을 bundle identity로 run에 기록한다. 로컬 release의 `candidate-manifest.json` 및 archive hash는 별도 후보 근거로 유지하며 이 bundle identity로 대체하지 않는다. Profile hash는 profile을 실제 저장한 뒤 해당 bytes로 계산해 run 기록에만 쓴다.

Obsidian vault 접근과 Graphify·Archify의 지정 경로는 준비 필수 전제다. 호스트는 Markdown을 직접 다루며 Obsidian 앱을 자동으로 열거나 등록하지 않는다. Graphify는 관계 작업과 승인된 갱신에, Archify는 요청된 설명·도면에 사용한다. vault·활성 목록이 없거나 충돌하면 필요한 값을 묻고 승인 전 쓰기 0건으로 둔다. 준비된 Graphify의 실패는 Markdown 원본의 유효성과 분리하고 이전 graph를 보존한다. 누락·접근 불가·권한 부재는 해당 단계 `BLOCKED`이며 자동 설치·경로 탐색·provider 전환은 하지 않는다.

## 계획·검토·검증

요구마다 담당, 소유 파일 또는 모듈 경계, 의존성, 관찰 가능한 acceptance, 검증 방법·환경·예상 결과를 연결한다. 사용자 결정·위임·가정·미정을 구분하고 범위·권한·provider·검증 깊이를 넓힐 때만 사용자에게 질문한다.

작성자와 독립 검토자는 분리한다. 부모 역할만 서브에이전트를 만들고 깊이는 1이며 실제 슬롯 한도를 넘지 않는다. 역할의 책임과 실제 provider/model/invocation은 구분한다. 특정 모델 자동 호출, provider 추가, 자동 fallback은 제공하지 않는다.

### 품질·보안 검토의 실행 경계

바탕·마디는 설치만으로 Codex 전역의 역할·모델·Daybreak 상태를 설정하지 않고 호스트와 프로젝트의 기존 subagent 규약을 따른다. Codex는 `default`, `worker`, `explorer` 같은 기본 subagent 유형을 제공하며 `agents.enabled`는 기본적으로 `true`지만 호스트가 끌 수 있다. 사용자 정의 TOML은 선택 사항이고, subagent는 별도 설정이 없으면 부모의 model·effort를 상속한다([Codex subagents 문서](https://learn.chatgpt.com/docs/agent-configuration/subagents)). `quality_checker`는 책임 이름이지 그 이름의 profile이 필수라는 뜻이 아니다. 사용 가능한 역할이면 무엇이든 실제 독립 검토 호출의 model·mode가 기준을 충족할 때 이 책임을 맡을 수 있다. Madi 개발 작업에 필수인 품질 검토는 일반 모드 `gpt-6.1-sol/high`에서 정합성·상태 전이·운영 계약을 검토한다. Daybreak가 켜진 턴에서 표준 모드 실행이 확인되지 않으면 그 호출을 품질 검토 `PASS`로 승계하지 않으며, 필수 검토를 수행할 수 없으면 `BLOCKED`로 남긴다. 개인 전역 policy 파일은 이 package의 의존성이 아니다.

설치 호스트는 실제 대상 프로젝트의 규약과 [권장 예시](../../../../../examples/AGENTS.md)를 비교한다. 정확한 정책 파일·충돌·제안 변경안을 보여주면서 **기존 규약 유지**(기본) 또는 **대상 프로젝트 적용**을 선택하게 한다. 사용자가 적용을 선택한 경우에만 제시한 범위를 반영한다. 전역 정책·에이전트 TOML이나 다른 프로젝트를 자동 수정하지 않는다. 선택·대상·변경 전후 hash·충돌을 기록하며 미선택·충돌은 권장 규약을 설치한 것으로 취급하지 않는다. 새 run에서 선택 기록과 실제 정책 경로·hash를 다시 읽어 drift·충돌을 확인한다. 필요한 checker 호출을 실행할 수 없으면 해당 게이트를 `BLOCKED`로 기록하고, 일반 바탕 지식 조회는 계속 분리한다.

보안 검토가 프로젝트 계약상 필요하거나 공개 코드 릴리즈를 준비할 때는 고정 최종 후보 전체를 독립적으로 읽기 전용 검토한다. Daybreak 접근권한과 `gpt-6-sol/high`의 모델·제품 표면 호환성, 실제 호출 모드가 확인되면 해당 경로를 선택한다. Daybreak 접근이 없으면 일반 모드 `gpt-6.1-sol/high`로 같은 후보 전체를 검토한다. Daybreak 호출의 접근 거부도 원래 오류로 기록하고, 일반 모드를 실제로 선택할 수 있는 호스트에서만 후속 경로로 진행한다. 두 경로의 필수 범위·finding 처리·릴리즈 차단 기준은 같다. Daybreak 부재는 공개 코드 릴리즈의 보안 검토 면제나 범위 축소 근거가 아니다. 모드 전환이나 호출을 확인할 수 없으면 필수 게이트는 `BLOCKED`이며 조용한 재시도는 하지 않는다.

프로젝트 profile의 역할 표와 run 기록에 각 검토의 실제 provider·model·일반/Daybreak 모드, 접근 판단, 고정 후보 hash, 검토 범위·판정·finding·미검증을 남긴다. 특정 이름의 profile이 아니라 실제 실행 증거가 조건이다. 모델 접근 오류·미실행·차단은 원래 상태와 원인을 보존하고, 후속 검토가 통과하더라도 삭제하지 않는다. 프로젝트가 보안 검토에 더 엄격한 모델 게이트를 명시하면 그것을 따르되 `quality_checker`의 표준 모드 원칙은 유지한다. 일반 문서·도면 작업에 별도 품질·보안 검토를 적용할지는 프로젝트 계약이나 계획에서 필요성과 이유를 정한다. 이 공개 패키지는 전역 checker TOML이나 모델 선택 실행기를 설치하지 않는다.

`PLAN_READY`는 계획 착수 기준, `TASK_DONE`은 승인 범위의 산출물·필수 검토·검증이 충족한 기록, `RELEASE_READY`는 릴리즈 게이트 충족 기록이다. 모두 호스트가 실제 Markdown 근거와 관찰을 해석해 판단한다. 이 패키지는 자동 기계 검사·상태 전이·완료 제출을 제공하지 않는다.

| 축 | 값 |
|---|---|
| 단계 | `planning` / `implementation` / `review` / `verification` / `release` |
| 작업 상태 | `pending` / `active` / `paused` / `blocked` / `done` |
| 검토 판정 | `approve` / `request_changes` / `blocked` / 공란 |
| 검증 결과 | `PASS` / `FAIL` / `BLOCKED` / `NOT_RUN` |
| 근거 유효성 | `current` / `stale` |

`NOT_RUN`은 미실행, `BLOCKED`는 실행 불가, `FAIL`은 실행했으나 기준 미충족, `PASS`는 지정 범위의 실제 기준 충족이다. 정적 package 검사·문구·파일 존재만으로 호스트 통합 행동이나 공개 배포를 `PASS`로 만들지 않는다. 대상·환경·요구가 바뀌면 영향 근거는 `stale`로 보존하고 재검증한다.

프로필의 선택 필드 `verification_policy_version`이 정수 `1`이면 각 check에 다음 분류와 실행 경계를 기록한다. 필드가 없으면 기존 `check_scope`의 키·검사·상태 전이를 유지하며 새 필드를 요구하지 않는다.

```text
verification.category: code_conditions | real_components | exploit_reproduction
verification.rationale: 비어 있지 않은 근거
verification.residual_uncertainty: 비어 있지 않은 잔여 불확실성
execution_boundary.status: recorded | needs_confirmation | blocked
execution_boundary.authority_basis / scope: 비어 있지 않은 근거와 범위
```

`code_conditions`는 정적 조건, `real_components`는 격리된 실제 구성요소 기능 시험, `exploit_reproduction`은 실제 침입·악용 재현이 필수인 예외다. 예외에는 `real_components` 방어 검증만으로 부족한 이유, 구체 범위, 사전 사용자 질문·동의, 플랫폼 허용을 기록한다. 기본 계획에 재현 check를 자동 생성하지 않는다.

`recorded`와 `user_confirmed`는 호스트가 근거를 기록한 사실일 뿐 실제 권한 인증·플랫폼 승인·재현 허용이 아니다. `needs_confirmation` 또는 `blocked`인 check는 `PASS`를 제출할 수 없고 required check라면 `TASK_DONE`과 `RELEASE_READY`를 막는다. 이 실행 경계 상태만으로 `PLAN_READY`를 막지는 않는다. 기존 FAIL·BLOCKED·NOT_RUN, 검토 request_changes·blocked와 finding은 append-only로 보존하며, 실패를 감추기 위해 category·scope를 바꾸지 않는다.

## 릴리즈 기준

`TASK_DONE`은 승인 범위의 산출물·필수 검토·검증이 충족한 작업 완료 기록이다. `RELEASE_READY`는 별도 릴리즈 게이트 기록이며 배포 실행 또는 권한을 뜻하지 않는다. 공개 코드 release에는 고정 최종 후보 전체를 대상으로 한 독립된 읽기 전용 보안 검토가 필수다. Daybreak 가능 여부에 따라 위 두 보안 검토 경로 중 하나를 실제로 완료해야 하며, 결과가 없는 경우에는 모델 명칭이나 이전 후보의 검토 기록으로 게이트를 대체하지 않는다. 모델 정보는 프로젝트 프로필의 역할 표에 기록하고, CLI/API 제거를 이유로 검토 범위를 낮추거나 특정 모델·provider를 자동 호출하지 않는다.

중요한 미해결 finding, 필수 검토 미완료, required 검증의 미확인·FAIL·BLOCKED·NOT_RUN이 남으면 `RELEASE_READY`로 기록할 수 없다. 예외가 필요하면 사용자에게 근거·잔여 위험·담당·만료일을 제시해 별도 승인받으며, 예외 승인으로 결과를 `PASS`로 바꾸지 않는다.

## 설치와 복구의 기록 경계

Codex는 사용자 skill을 `~/.agents/skills`, 프로젝트 skill을 `<project>/.agents/skills`에서 읽는다. 바탕 skill 하나만 등록한다. 마디 절차는 `skills/batang/components/madi/workflow.md`에 내부 문서로 보존한다. 재현 가능한 설치는 전체 checkout을 고정 revision으로 유지하고 `skills/batang`에 대한 단일 skill 등록을 만든다. 전체 checkout을 보존해야 내부 문서와 프로젝트 예시의 상대 참조가 유효하다.

전환 전 현재 Batang 및 Madi 등록의 정확한 경로와 link target을 관찰한다. 기존 Madi link가 이 설치의 이전 snapshot을 가리키는 예상 대상이며 소유가 확인된 경우에만 전환 계획에 따라 회수한다. 대상이 다르거나 소유가 불명확하면 멈추고 보고한다. 의도한 새 Batang 등록이 이미 있으면 중복 추가하지 않으며, 다른 checkout을 가리키는 기존 Batang 등록은 구체적인 변경안 없이 덮어쓰거나 삭제하지 않는다. 이전 snapshot과 기존 run은 그대로 둔다.

아래는 기존 등록과 충돌이 없고 대상 경로가 비어 있을 때 사용하는 프로젝트 등록 예시다. 경로는 실제로 확인한 값으로 바꾼다.

```sh
mkdir -p /path/to/project/.agents/skills
ln -s /absolute/path/to/batang-checkout/skills/batang /path/to/project/.agents/skills/batang
```

등록 후 실제 link target과 checkout revision, root `SHA256SUMS`의 각 파일 hash 및 `SHA256SUMS` 자체의 hash를 확인한다. 기존 두 등록에서 새 단일 등록으로 이전하는 경우에는 새 Batang link를 먼저 검증한 뒤, 사전 관찰에서 이 설치의 소유로 확인된 예상 Madi link만 제거한다. 다른 link나 파일은 보존한다. 링크 대상의 변경·회수 순서가 실패하면 이번 작업에서 바꾼 link만 실제 target과 현재 상태를 재확인해 조건부 복구한다.

예시 명령은 대상 경로가 아직 없을 때만 실행한다. 기존 등록이 다른 대상을 가리키거나 변경 범위가 불명확하면 중단한다. 실제 link 전환·예상 Madi link 회수·복구 성공은 해당 호스트에서 관찰해야 한다. 이 패키지는 installer, link 조작 코드, rollback 실행기를 제공하지 않는다.

제거·복구는 해당 설치 link 선택만 다룬다. immutable snapshot, vault, AGENTS 설정, backup, Graphify 결과, 기존 run은 제거하지 않는다. 기존 API 필수 project/run은 공개판으로 자동 전환하지 않는다.

## 개발 원본과 공개 package

개발 원본에는 제품 자료와 로컬 개발·검증 기록이 함께 있을 수 있다. 공개 package는 승인된 allowlist에 속한 제품 파일에서 새 staging 디렉터리로 산출한다. 로컬 run 결과, 프로젝트별 상태·finding, 개인 경로, 개발 일정은 공개 staging으로 복사하지 않는다. 상태값의 의미와 빈 재사용 양식은 제품 계약으로 유지할 수 있다.

1. 작업 범위와 allowlist를 승인 근거에 고정하고, 새 staging 디렉터리에 허용 파일만 복제한다. 원본 개발 파일은 유지한다.
2. 고정 전에 공개 릴리즈 정보를 개발 원본과 승인 기록에 대조해 갱신한다. 공개 버전, 사용자에게 보이는 변경 요약, 지원 환경, 외부 의존성의 버전·revision을 확인한다. 정보가 없거나 확인되지 않은 값을 공개 사실처럼 쓰지 않는다. 로컬 실행 결과와 게시 전 상태는 공개 설명에 넣지 않고 run 기록에 남긴다. 개발 원본의 revision/hash와 갱신할 공개 버전을 연결해 기록한다.
3. staging에서 package 파일 목록, 내부 참조와 공개 문구를 확인한다. 허용 파일별 SHA-256을 계산하고 `SHA256SUMS`, manifest, 배포 archive를 만든다. manifest와 archive hash로 공개 대상을 고정한다. 공개 version·변경 요약·지원 범위·의존성 고지와 이 연결 정보가 함께 고정됐는지 확인한다.
4. 단위·합성 검사, 공식 validator, 지원 환경 확인, 설치·복구 검증, 독립 검토는 모두 고정한 같은 bytes와 manifest hash를 대상으로 한다. 각 결과와 근거 및 실패 이력은 로컬 run 기록에 남긴다.
5. A/B 비교는 같은 승인 기준과 검증 범위로 수행한다. 배포 대상으로 선택할 후보는 마지막 배포 직전에 결정하며, 더 최신 후보가 모든 필수 게이트를 통과했는지 확인한다. `RELEASE_READY`는 고정 후보의 대상·hash, 승인 범위, 필수 검토·검증, 미해결 finding을 대조한 뒤 호스트가 기록한다.
6. hash 고정 후 파일이 달라지면 그 결과를 해당 고정본의 검증으로 사용하지 않는다. 새 staging 후보를 만들고 새 hash를 고정한 뒤 변경 영향이 있는 검증과 독립 검토를 반복한다. 이전 후보와 그 결과는 기존 로컬 기록에 보존한다.

공개 package에는 실제 run 기록이나 후보별 검증 결과를 넣지 않는다. 릴리즈 판단과 외부 게시·배포 권한은 별도이며 이 절차는 자동 게시나 `RELEASE_READY` 판정을 제공하지 않는다.
