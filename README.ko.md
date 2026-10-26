> AI 에이전트는 먼저 [AGENTS.md](AGENTS.md)를 읽어야 합니다. [English](README.md)

# 바탕

바탕은 선택한 자료를 출처와 함께 지식으로 정리하고, 쌓인 지식을 개발·문서·도면 작업에 활용하는 워크플로우입니다.

지식을 모으는 일부터 원하는 것을 만드는 일까지 한 흐름으로 잇고 싶었습니다. 원본 지식과 도구, 작업 절차를 나누어 필요에 따라 확장할 수 있도록 설계했습니다.

코드와 문서는 직접 작성하지 않았습니다. AI와 대화하며 기능과 작업 범위를 정하고, 구현과 검증을 반복했습니다.

## 시작하기

0.0.9의 지원 환경은 **Codex / macOS ARM64**입니다. 필요한 소프트웨어는 다음과 같습니다.

| 필수 설치 소프트웨어 | 용도 |
|---|---|
| Obsidian | 노트를 보관하고 관리합니다. |
| Graphify | 노트와 개념 사이의 관계를 정리합니다. |
| Archify | 요청하신 설명이나 도면을 만들 때 사용합니다. |

Graphify는 Python을, Archify는 Node.js를 실행 환경으로 사용합니다. 버전과 자세한 내용은 [Third-party notices](THIRD_PARTY.md)에 있습니다.

저장소를 클론하고 폴더로 이동하세요.

```sh
git clone https://github.com/revoepko/batang.git
cd batang
```

이 폴더에서 Codex를 열고 다음과 같이 요청하세요.

```text
이 폴더의 AGENTS.md에 따라 바탕을 설치해 주세요.
```

Codex는 확인한 경로를 대상 프로젝트의 `AGENTS.md`에 기록하고 바탕 스킬 하나의 등록 상태를 확인합니다.

## 자연어로 요청하기

| 요청 예시 | 예상 결과 |
|---|---|
| “선택한 노트로 출처 문단 링크를 달아 결정 노트를 갱신해 주세요.” | 요청한 대상만 수정하고 참고한 출처를 연결합니다. |
| “이 주제에 대해 무엇을 결정했나요? 선택한 노트를 비교하고 관계를 설명해 주세요.” | 관련 노트를 비교해 결정 내용과 근거를 알려 줍니다. |
| “선택한 노트로 짧은 안내문을 작성하고 작업 흐름 도면도 만들어 주세요.” | 선택한 노트에 근거한 안내문과 요청한 도면을 만듭니다. |

## 바탕의 구성

| 구성 요소 | 하는 일 |
|---|---|
| [`가닥`](skills/batang/components/gadak/workflow.md) | 작업에 필요한 원본, 도구 경로와 프로젝트 정책을 정합니다. |
| [`나루`](skills/batang/components/naru/workflow.md) | Codex의 요청 처리를 바탕의 작업 절차와 준비된 도구에 연결합니다. |
| [`두레`](skills/batang/components/dure/workflow.md) | 변경 전에 허용할 대상과 확인·백업·복구 조건을 정합니다. |
| [`마디`](skills/batang/components/madi/workflow.md) | 개발·문서·도면 작업을 계획하고 만든 뒤 작성자와 분리된 검토를 연결합니다. |
| [`수풀`](skills/batang/components/supul/workflow.md) | 선택한 지식을 반영·조회·정정합니다. |

`갈피`, `고리`, `보기`는 수풀에 속합니다.

| 구성 요소 | 하는 일 |
|---|---|
| [`갈피`](skills/batang/components/supul/galpi/workflow.md) | 선택한 노트를 읽고 출처를 분명히 합니다. |
| [`고리`](skills/batang/components/supul/gori/workflow.md) | 노트와 개념 사이의 관계를 보여 줍니다. |
| [`보기`](skills/batang/components/supul/bogi/workflow.md) | 요청에 따라 설명과 도면을 만듭니다. |

이 구성 요소들은 하나의 바탕 스킬 안에 있는 책임입니다. 호스트 AI가 요청에 필요한 절차와 기존 도구를 연결합니다.

바탕은 선택한 노트를 근거로 답합니다. 관계도와 그림은 이해를 돕는 보조 자료입니다.

## 노트 읽기와 변경

- 지정한 노트와 허용된 출처만 읽습니다.
- 대화 내용을 자동으로 저장하지 않습니다.
- 저장을 요청하시면 지정한 대상에만 반영하고, 기존 노트를 수정하기 전에 백업합니다.

자세한 내용은 [노트 읽기·저장 안내](skills/batang/references/source-access.md)와 [노트 작성 안내](skills/batang/references/knowledge-contract.md)를 확인해 주세요.

## 라이선스

[MIT](LICENSE) © 2026 EPKO · [Third-party notices](THIRD_PARTY.md)
