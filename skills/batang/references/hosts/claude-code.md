# Claude Code CLI와 Claude 앱 안내

이 안내는 macOS ARM64의 Claude Code CLI와 Claude 앱의 로컬 Code 세션에 적용한다. 앱에서는 Code 사용이 가능한 계정으로 로그인하고 작업 폴더를 선택한다. CLI의 API 인증만으로 앱의 Code 이용 권한이 확인되는 것은 아니다.

사용자는 요청 앞에 `/batang`을 명시해 호출한다. `SKILL.md`의 `disable-model-invocation: true`는 Claude의 자동 호출을 끈다. 기존 정책이 매 요청마다 바탕을 읽도록 요구하면 설치 시 사용자와 합의해 바탕 진입 부분만 정리하고 일반 규칙과 역할 설정은 유지한다.

[스킬 안내](https://code.claude.com/docs/en/skills)의 개인 `~/.claude/skills` 또는 프로젝트 `.claude/skills` 중 선택한 위치에 전체 고정 checkout의 `skills/batang`을 단일 스킬로 연결한다. 기존 개인·프로젝트 등록의 실제 대상·소유와 동명 등록의 가림을 확인한다. 다른 대상이나 소유 불명 링크는 덮어쓰지 않는다. 기존 마디 링크는 이 설치의 이전 snapshot을 가리키는 예상 대상이고 소유가 확인된 경우에만 새 바탕 링크 검증 후 회수한다. 전환 실패 시 이번 변경만 실제 상태를 확인해 조건부 복구하고 이전 snapshot·run은 보존한다. [설치와 복구 계약](../../components/madi/references/workflow-contract.md#설치와-복구의-기록-경계)을 따른다.

[프로젝트 지침](https://code.claude.com/docs/en/memory)에 따르면 AGENTS 직접 읽기는 v2.1.277 이후에도 CLAUDE 파일·설정·세션 조건에 좌우된다. 이 숫자는 바탕의 최소 지원 버전 확정이 아니다. 실제 적용되는 필수 정책과 전달을 확인하며 `AGENTS.override.md` 자동 로딩은 가정하지 않는다. 필요하면 기존 `CLAUDE.md`에 `@AGENTS.md` 참조를 충돌 없이 병합하되 기존 내용을 보존한다. 새 CLAUDE 파일이나 전역 설정을 자동 생성·변경하지 않는다. 필수 정책을 확인하지 못하면 그 정책에 의존하는 행동을 중단한다.

[설정 예시](../../../../examples/AGENTS.md#using-the-example-with-claude-code)는 공유 지침을 기존 `CLAUDE.md`에 연결하는 방법을 보여 준다. 지침 참조와 스킬 등록은 각각 확인한다.

메인은 [서브에이전트](https://code.claude.com/docs/en/sub-agents)에 필요한 정책·바탕 절차·자료와 범위를 전달하고 적용 규약과 관찰 가능한 역할·문서 참조·행동·결과를 확인한다. 내부 수신이 관찰되지 않으면 미확인으로 남기며 실제 계약 실패와 구분한다. Explore·Plan에 초기 지침이 자동 전달된다고 가정하지 않는다.

위임할 때 필요한 custom 역할을 명시하고 의도한 모델과 실제 호출 모델을 구분해 차이를 기록한다. 필요한 도구·권한과 관찰 가능한 실행 결과를 확인하며 문서의 Read 전달과 native Skill 호출을 구분한다. 역할 등록은 바탕 호출 밖에서도 발견될 수 있으며 역할 숨김이나 권한 격리가 아니다. 개인 역할·모델·추론 수준·등록과 도구 권한은 호스트 설정을 따른다.

앱 조작 담당 역할은 선택 사항이다. 실제 computer-use 도구가 제공된 부모 또는 허용된 역할이 사용할 수 있으며 동명 역할이나 새 MCP가 필수는 아니다. 도구가 없으면 해당 UI 단계만 `BLOCKED` 또는 미확인으로 남기고 바탕의 지식 기능 전체를 막지 않는다.

Claude 앱에서는 폴더를 선택하고 로컬 Code 세션에서 바탕 발견을 확인한 뒤 요청한다. 선택한 프로젝트·worktree, 파일 권한과 도구 PATH를 확인한다. 앱에 내장된 Code 버전은 CLI와 다를 수 있고 공유 설정만으로 한쪽의 관측을 다른 쪽에 승계하지 않는다. [앱의 Code 안내](https://code.claude.com/docs/en/desktop)를 따른다. CLI 별도 설치 없이 Code를 쓸 수 있지만 Obsidian·Graphify·Archify와 필요한 Python·Node 준비는 별개다.

공식 지침 변경은 관련 작업이나 호스트 갱신 때 필요한 부분을 확인한다.
