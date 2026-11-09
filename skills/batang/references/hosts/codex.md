# Codex CLI와 ChatGPT 앱 안내

Codex CLI 또는 ChatGPT 앱에서 사용할 프로젝트 폴더를 선택하고, 실제 적용되는 사용자·프로젝트 지침과 권한을 확인한다. 각 디렉터리의 `AGENTS.override.md`와 `AGENTS.md` 적용은 [공식 지침](https://learn.chatgpt.com/docs/agent-configuration/agents-md)을 확인한다. 기존 정책을 덮어쓰거나 모델·에이전트 설정을 자동 변경하지 않는다.

Codex CLI에서는 `$batang`으로, ChatGPT 앱에서는 `@`로 바탕 스킬을 선택해 명시 호출한다. 제공된 `agents/openai.yaml`의 `allow_implicit_invocation: false`는 자동 선택을 끈다. 기존 정책이 매 요청마다 바탕을 읽도록 요구하면 설치 시 사용자와 합의해 바탕 진입 부분만 정리하고 일반 규칙과 역할 설정은 유지한다.

ChatGPT 앱에서는 선택한 작업 모드와 프로젝트가 해당 로컬 폴더를 사용하는지 확인한다. 작업 폴더와 스킬의 실제 대상, 적용 지침과 권한을 확인한다. 스킬 목록 표시와 실제 스킬 사용도 구분해 확인한다.

[스킬 안내](https://learn.chatgpt.com/docs/build-skills)의 개인 `~/.agents/skills` 또는 프로젝트 `.agents/skills` 중 선택한 위치에 전체 고정 checkout의 `skills/batang`을 단일 스킬로 연결한다. 등록 전에 기존 개인·프로젝트 등록의 실제 대상과 소유를 확인하고 동명 등록이 가리는지 확인한다. 다른 대상이나 소유가 불명확한 링크는 덮어쓰지 않는다. 기존 마디 링크는 이 설치의 이전 snapshot을 가리키는 예상 대상이고 소유가 확인된 경우에만 새 바탕 링크 검증 후 회수한다. 실패하면 이번 변경만 현재 상태를 확인해 조건부 복구하고 기존 run과 snapshot을 보존한다. 상세 안전 조건은 [설치와 복구 계약](../../components/madi/references/workflow-contract.md#설치와-복구의-기록-경계)을 따른다.

위임이 필요하면 [호스트의 native 서브에이전트](https://learn.chatgpt.com/docs/agent-configuration/subagents)와 적용 규약을 따른다. 필요한 custom 역할은 명시하고 의도한 모델과 실제 호출 모델을 구분해 차이를 기록한다. 필요한 도구와 권한을 확인하고 전달한 절차·정책과 관찰 가능한 역할·문서 참조·행동·결과를 확인한다. 내부 수신이나 바이트 확인을 강제하지 않으며 관찰 불가는 미확인으로 남긴다. 문서를 읽어 전달하는 것과 native 스킬 호출은 다르며 자동 상속을 가정하지 않는다. 역할 등록은 바탕 호출 밖에서도 발견될 수 있고 역할 숨김이나 권한 격리를 보장하지 않는다. 개인 역할·모델·추론 수준·등록과 도구 권한은 호스트 설정을 따른다.

공식 지침은 바뀔 수 있으므로 관련 작업 또는 호스트 갱신 때 필요한 부분을 다시 확인한다. 실제 등록·복구 성공은 해당 환경에서 관찰해야 한다.
