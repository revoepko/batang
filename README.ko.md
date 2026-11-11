> AI 에이전트는 먼저 [AGENTS.md](AGENTS.md)를 읽어야 합니다. [English](README.md)

# 바탕

바탕을 사용하면 선택한 노트를 출처와 함께 정리하고, 필요한 내용을 찾아 개발·문서·도면 작업에 활용할 수 있습니다.

[변경 기록](RELEASE.ko.md)

## 시작하기

macOS ARM64에서 Codex CLI와 ChatGPT 앱으로 바탕을 사용할 수 있습니다.

필요한 소프트웨어는 다음과 같습니다.

| 소프트웨어 | 사용 시점 |
|---|---|
| [Obsidian](https://obsidian.md/download) | 노트를 보관하고 관리합니다. |
| [Graphify](https://github.com/Graphify-Labs/graphify) | 노트와 개념 사이의 관계를 정리합니다. |
| [Archify](https://github.com/tt-a1i/archify) | 요청하신 설명이나 도면을 만들 때 사용합니다. |

Markdown 직접 조회에는 Graphify와 Archify가 필요하지 않습니다. Graphify는 관계 작업과 승인된 갱신에, Archify는 요청된 시각화에 필요합니다.

Graphify는 Python을, Archify는 Node.js를 실행 환경으로 사용합니다. 필요한 도구가 없다면 사용하는 AI에게 함께 설치해 달라고 요청할 수 있습니다.

확인한 버전과 자세한 내용은 [Third-party notices](THIRD_PARTY.md)에 있습니다.

저장소를 클론하고 폴더로 이동하세요.

```sh
git clone https://github.com/revoepko/batang.git
cd batang
```

이 폴더에서 사용할 AI 도구를 열고 다음과 같이 요청하세요.

```text
이 폴더의 AGENTS.md에 따라 바탕을 설치해 주세요.
```

AI는 바탕을 사용할 프로젝트 폴더와 노트를 보관할 볼트를 확인합니다. 프로젝트는 AI와 작업하는 폴더이며 볼트와 같은 위치일 필요는 없습니다.

확인한 설정은 승인 범위에서 프로젝트의 실제 정책과 기록 방식에 반영합니다. 기존 설정과 스킬 등록은 보존합니다.

기존 노트를 가져올지, 어떤 노트를 사용할지 사용하는 AI에게 알려 주세요. 새로 시작한다면 빈 볼트를 준비할 수도 있습니다. 다른 곳에서 가져온 노트는 사본을 사용하고 원본을 보존합니다.

모두 같은 바탕 스킬을 사용합니다.

Codex CLI와 ChatGPT 앱은 [Codex 안내](skills/batang/references/hosts/codex.md)를 참고하세요.

## 자연어로 요청하기

먼저 사용하는 AI에서 바탕을 호출하세요.

- Codex CLI: 요청 앞에 `$batang`을 입력합니다.
- ChatGPT 앱: `@`를 입력하고 바탕 스킬을 선택합니다.

바탕은 호출한 작업과 이어지는 후속 요청에 적용됩니다.
다른 작업에는 자동으로 적용하지 않습니다.

기존 AI 규칙과 에이전트 역할은 그대로 유지됩니다.

| 요청 예시 | 예상 결과 |
|---|---|
| “이 폴더의 노트를 바탕으로 가져와 주세요.” | 선택한 노트를 사본으로 가져오고 연결 상태를 확인합니다. |
| “가져온 노트의 관련 내용을 찾아 주세요.” | 노트와 관계를 살펴보고 출처를 알려 줍니다. |
| “이 내용을 항목별로 선택해 볼 수 있는 설명 페이지로 만들어 주세요.” | 선택 버튼 아래 같은 영역에서 내용을 바꾸어 볼 수 있는 페이지를 만듭니다. |
| “이 노트들을 참고해서 결정 내용을 decision.md에 정리해 주세요. 출처도 함께 남겨 주세요.” | 요청한 대상만 수정하고 참고한 출처를 연결합니다. |
| “이 노트들에서 이 주제에 관해 어떤 결정을 했는지 찾아서 비교해 주세요.” | 관련 노트를 비교해 결정 내용과 근거를 알려 줍니다. |
| “이 노트들을 바탕으로 짧은 안내문과 작업 흐름 그림을 만들어 주세요.” | 선택한 노트에 근거한 안내문과 요청한 도면을 만듭니다. |

## 바탕의 구성

| 구성 요소 | 하는 일 |
|---|---|
| [`가닥`](skills/batang/components/gadak/workflow.md) | 어떤 노트와 도구를 사용할지, 프로젝트 설정이 준비됐는지 확인합니다. |
| [`나루`](skills/batang/components/naru/workflow.md) | 요청을 보고 지식 조회, 개발, 문서 또는 도면 중 필요한 작업을 고릅니다. |
| [`두레`](skills/batang/components/dure/workflow.md) | 변경할 수 있는 대상을 확인하고 수정 전 백업과 복구 조건을 살핍니다. |
| [`마디`](skills/batang/components/madi/workflow.md) | 개발·문서·도면 작업을 계획하고 결과를 만든 뒤 다른 검토자가 확인하도록 합니다. |
| [`수풀`](skills/batang/components/supul/workflow.md) | 요청에 따라 선택한 자료를 노트에 저장하고, 필요한 내용을 찾거나 정정합니다. |

`갈피`, `고리`, `보기`는 수풀에 속합니다.

| 구성 요소 | 하는 일 |
|---|---|
| [`갈피`](skills/batang/components/supul/galpi/workflow.md) | 선택한 노트를 읽고 출처를 분명히 합니다. |
| [`고리`](skills/batang/components/supul/gori/workflow.md) | 노트와 개념 사이의 관계를 보여 줍니다. |
| [`보기`](skills/batang/components/supul/bogi/workflow.md) | 요청에 따라 설명과 도면을 만듭니다. |

이 구성 요소들은 하나의 바탕 스킬에 들어 있습니다. 호스트 AI가 요청에 필요한 절차와 사용자가 준비한 도구를 연결하고 실제 실행을 맡습니다.

필요한 작업을 여러 AI에게 나누어 맡기고, 작성 결과를 다른 AI가 검토할 수 있습니다.

바탕은 선택한 노트를 근거로 답합니다. 관계도와 그림은 이해를 돕는 보조 자료입니다.

답변에 사용할 원문의 적용 시점과 조건을 확인합니다. 자료가 서로 충돌하거나 현재 효력을 확인하지 못하면 그 상태를 알려 드립니다.

## 노트 읽기와 변경

- 지정한 노트와 허용된 출처만 읽습니다.
- 대화 내용을 자동으로 저장하지 않습니다.
- 저장을 요청하시면 지정한 대상에만 반영하고, 기존 노트를 수정하기 전에 백업합니다.

새 관리 노트는 짧고 명확한 주제의 파일명을 사용하며 파일명에 ID를 붙이지 않습니다. 내부 ID는 유지하고, 이름이 겹치면 대상이나 주제를 보충합니다. 기존 노트의 이름은 명시적으로 요청한 경우에만 바꿉니다. [명명 규칙](skills/batang/references/knowledge-contract.md#관리-문서-이름)

자세한 내용은 [노트 읽기·저장 안내](skills/batang/references/source-access.md)와 [노트 작성 안내](skills/batang/references/knowledge-contract.md)를 확인해 주세요.

다른 곳에서 작성한 노트도 가져올 수 있습니다. 선택한 노트의 사본과 출처를 등록하고, 사본의 연결까지 확인합니다. 원본은 그대로 둡니다. 지원하지 않는 속성이나 연결이 있으면 보존하고 확인이 필요한 이유를 알려 드립니다. [가져오기 안내](skills/batang/references/import.md)를 확인하세요.

가져온 노트의 본문과 속성은 Obsidian에서 편집할 수 있습니다. 저장한 노트와 관계 자료를 연결하지 못했다면 노트는 계속 읽을 수 있으며, 관계 반영이 대기 중이라고 알려 드립니다.

노트에 별칭(`aliases`)을 붙일 수 있습니다. AI는 선택한 노트의 별칭을 단서로 관련 내용을 찾습니다. [관계 안내](skills/batang/components/supul/gori/workflow.md)를 확인하세요.

## 라이선스

[MIT](LICENSE) © 2026 EPKO · [Third-party notices](THIRD_PARTY.md)
