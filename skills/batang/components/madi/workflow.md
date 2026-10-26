# 마디

설계 책임 이름에서 `마디`는 바탕의 상위 개발·문서·도면 책임이며, 이 문서는 해당 작업 절차를 적습니다. 바탕 스킬은 관련 개발·문서·도면 요청에서만 이 절차를 읽고, 일반 지식 흐름에는 적용하지 않습니다. [보기](../supul/bogi/workflow.md)는 `수풀` 아래에서 요청된 설명·시각화를 맡고 Archify는 요청 때만 사용합니다. 실제 실행과 권한은 현재 호스트와 프로젝트가 맡으며, 별도 실행 모듈·CLI·API·loader·provider·hook은 제공하지 않습니다.

## 시작 전 확인

1. 프로젝트의 `AGENTS.md`와 지정된 정책·진입 계약을 먼저 읽는다. 현재 요청의 승인 범위, 자료 접근 권한, 변경 금지 영역, 기존 run을 확인한다.
2. 프로젝트가 지정한 Obsidian vault와 활성 목록만 읽거나 쓴다. vault 전체를 자동 탐색·편입하지 않는다. vault 또는 활성 목록이 없거나 충돌하면 필요한 이름·위치·포함 파일을 제시하고 명시 승인 전에는 만들거나 덮어쓰지 않는다.
3. Obsidian vault 접근, Graphify, Archify는 준비 필수 전제다. 호스트는 Markdown을 직접 다루며 Obsidian 앱을 자동으로 열거나 등록하지 않는다. Graphify는 관계 작업과 승인된 갱신에 쓰고, Archify는 설명·도면을 요청받았을 때만 실행한다. 실제 위치와 접근을 확인하고 자동 설치·경로 탐색·provider 대체는 하지 않는다.
4. 새 run이면 등록된 [바탕 스킬](../../SKILL.md)과 이 내부 절차가 동일 checkout에 있는지 확인한다. Checkout root의 `SHA256SUMS`에 적힌 각 파일 hash를 대조하고, 그 파일 자체의 SHA-256을 bundle identity로 run에 기록한다. profile hash는 실제 저장한 profile bytes에서 계산해 run 기록에만 둔다. release의 `candidate-manifest.json`과 archive hash는 별도 후보 근거로 보존한다. 불일치하면 개발 절차의 결합만 중단하고 바탕 지식 기능까지 차단하지 않는다.

## 계획과 기록

목표·범위·제약·기존 결정을 정리하고, 사용자 결정·위임된 세부결정·가정·미정을 구분한다. 관련 형식은 다음 자료를 사용한다.

- 결정: [결정 기록](assets/decision-record.md)
- 프로젝트 조정값: [프로젝트 프로필](assets/project-profile.md)
- 계획: [상세 실행 계획](assets/execution-plan.md)
- 작업별 근거: [실행 기록](assets/run-record.md)

표현은 [공통 표현 지침](references/clear-language.md)을 따른다. 문서 작업이면 [문서 작업 지침](references/document-workflow.md), 도면 작업이면 [도면 작업 지침](references/diagram-workflow.md)을 추가로 읽는다. 사용자 검토·승인이 필요한 경우 [사용자 검토 표시 지침](references/user-review-presentation.md)을 따른다. 역할·상태·검증·기록 경계는 [실행 계약](references/workflow-contract.md)을 따른다.

## 중요한 경계

- `PLAN_READY`, `TASK_DONE`, `RELEASE_READY`는 호스트가 실제 Markdown 근거와 프로젝트 계약을 읽어 내리는 기록 상태다. 이 패키지는 이 값을 자동으로 검사·제출·전환하지 않는다.
- `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN`도 실제 관찰 범위의 기록이다. 파일 존재, 문구 일치, 설치 선택값, 합성 호출만으로 실제 호스트 동작이나 릴리즈 준비를 `PASS`로 바꾸지 않는다.
- 기존 API 기반 profile/run 또는 이전 snapshot은 보존한다. 공개판으로 자동 전환·이관·재작성하지 않으며, 기존 API가 필요한 run의 지침과 기록을 대체하지 않는다.
- 개발 원본에서 공개 package를 만들 때는 승인된 allowlist만 새 staging으로 추출하고 manifest·checksum hash를 고정한다. 공개 package와 로컬 실행 기록의 경계, 고정본 이후 검증 순서, 배포 직전 릴리즈 판단은 [공개 package와 릴리즈 계약](references/workflow-contract.md)을 따른다.
- 부모 역할만 서브에이전트를 생성한다. 위임 깊이는 1이며, 실제 호스트 슬롯 한도와 프로젝트 역할·모델 규약을 지킨다. 특정 모델·provider의 자동 호출 또는 전환을 추가하지 않는다.
- `quality_checker`는 검토 책임의 이름이며, 같은 이름의 Codex 프로필을 필수로 만들지 않는다. Codex의 `default`, `worker`, `explorer` 등 실제 사용 가능한 역할도 독립 호출과 필수 모델·모드를 충족하면 맡을 수 있다. 서브에이전트는 기본적으로 부모 모델·effort를 상속하므로 호출에서 실제 사용값을 확인한다. Madi 개발 작업의 필수 품질 검토는 일반 모드 `gpt-6.1-sol/high`에서 수행하며 실행·모드 확인이 불가능하면 `BLOCKED`다. 일반 문서·도면 작업은 프로젝트 계약이나 계획에서 별도 품질·보안 검토가 필요한지 이유와 함께 정한다. 보안 검토가 요구되거나 공개 코드 릴리즈를 준비할 때는 Daybreak 접근·호환·실제 모드가 확인되면 `gpt-6-sol/high`, 접근이 없으면 같은 고정 최종 후보 전체에 일반 모드 `gpt-6.1-sol/high`를 사용한다. 접근 거부는 보존하고, 일반 경로를 실제로 호출할 수 있을 때만 후속 검토한다. 공개 코드 릴리즈의 전체 후보 보안 검토는 면제하지 않는다.
- checker 권장 문구를 프로젝트 지침에 추가하는 일은 사용자의 선택이다. 이는 마디 작업에서 요구되는 독립 검토나 프로젝트 계획의 검토를 면제하지 않는다. [설치 안내](../../../../README.md)와 [프로젝트 설정 예시](../../../../examples/AGENTS.md)를 사용하되 사용자 선택·대상·충돌 확인 없이 설정을 수정하지 않는다. 새 run에서 선택 기록과 실제 정책 경로·hash를 다시 확인하고, 정적 문구만으로 실제 checker 가용성이나 검토 `PASS`를 추정하지 않는다.
- 바탕만 사용자 또는 프로젝트 skill로 등록한다. 이 내부 마디 절차는 같은 checkout에 보존하며 별도 skill로 등록하지 않는다.

## 설치·기존 run·새 run의 구분

설치된 link, 현재 세션이 읽은 파일, 새 run이 고정한 checkout은 서로 다를 수 있다. 기존 run은 시작 시 고정한 경로·지침·기록을 계속 사용하며, 진행 중 run의 실제 파일은 경로와 hash가 고정된 동안 수정하지 않는다. 새 후보는 별도 checkout 또는 고정 디렉터리에 준비해 이후 run에서 선택한다. 기존 설치·run·vault·Graphify 결과를 임의로 변경하거나 제거하지 않는다.

설치 또는 링크 전환의 실제 성공 여부는 격리된 실제 호스트 관찰로만 확인한다. 이 문서와 정적 검사는 package allowlist·참조·경계를 확인할 뿐, 단일 바탕 link 전환, 기존 마디 link 회수·복구 또는 vault 보존을 보증하지 않는다.
