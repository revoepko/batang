---
name: batang
description: 지정된 Obsidian Markdown과 출처를 조회하고 선택한 자료를 반영하며, 승인된 개발·문서·도면 작업을 계획·작성·독립 검토한다. 요청에 맞는 작업 절차만 적용하고 대화를 자동 저장하지 않는다.
---

# 바탕

사용자는 원하는 일을 자연어로 요청한다. 현재 호스트 모델이 의도·자료·범위·권한을 판단한다. 자동 스킬 선택은 허용하지만 선택 자체가 파일 쓰기 권한은 아니다. 별도 분류기 API, 모델 호출기, 고정 모델 파이프라인을 만들지 않는다. 위임은 현재 호스트의 기존 subagent 규약을 따르며 개발·문서·도면의 모델·검토 기준은 [마디 실행 계약](components/madi/references/workflow-contract.md)에서 확인한다.

요청을 분기하기 전에 모든 결과물의 작성과 검수에 적용할 [공통 표현 지침](components/madi/references/clear-language.md)을 읽는다. 이 지침은 마디 실행이나 별도 도구·검토를 강제하지 않는다.

## 필요한 절차 선택

요청을 분기하기 전에 [나루](components/naru/workflow.md)를 따른다. 현재 실행에서 해당 대상의 준비 확인 근거가 없거나 대상·설정·접근 조건이 달라지면 [가닥](components/gadak/workflow.md)을 확인한다. 자료를 읽거나 변경할 때는 [두레](components/dure/workflow.md)의 범위를 적용한다. 같은 실행에서 유효한 준비 확인만 재사용하며, 그 밖의 절차는 요청에 필요한 것만 읽는다.

- [가닥](components/gadak/workflow.md): 프로젝트 설정, 필수 의존성과 설치 준비를 확인한다.
- [나루](components/naru/workflow.md): 요청에 맞는 지식·개발·문서·도면 경로를 선택한다.
- [두레](components/dure/workflow.md): 권한 범위, 기대 hash, 백업·복구와 실행 상태를 확인한다.
- [수풀](components/supul/workflow.md): 선택한 지식의 조회·반영·정정을 다룬다. 필요한 경우 [갈피](components/supul/galpi/workflow.md)의 원문·출처, [고리](components/supul/gori/workflow.md)의 관계 자료, [보기](components/supul/bogi/workflow.md)의 설명·시각화 절차를 읽는다.
- [마디](components/madi/workflow.md): 개발·문서·도면 요청에만 읽고 계획·작성·독립 검토를 수행한다. 일반 지식 조회에 강제하지 않는다.

각 이름은 단일 바탕 스킬 안의 책임이며 독립 프로그램이 아니다. 실제 도구 실행과 권한 판단은 호스트가 맡는다. 요청에 필요한 절차만 읽고, 활성 목록과 허용된 개별 자료를 넘어서 접근하지 않는다. Graphify 갱신과 시각화는 각각 승인된 관련 변경과 요청이 있을 때만 수행한다.
