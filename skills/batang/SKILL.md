---
name: batang
description: 사용자가 바탕을 명시 호출할 때 지정된 Obsidian Markdown과 출처를 조회하고 선택한 자료를 반영하며, 승인된 개발·문서·도면 작업을 계획·작성하고 적용 규약에 따라 검토한다.
---

# 바탕

사용자는 바탕을 명시 호출해 원하는 일을 요청한다. 현재 호스트 모델이 의도·자료·범위·권한을 판단하며 스킬 호출 자체는 파일 쓰기 권한이 아니다. 별도 분류기 API, 모델 호출기, 고정 모델 파이프라인을 만들지 않는다. 호스트의 상위 지침과 필수 역할·모델·검토 조건은 유지하며, 위임이 필요한 작업에서는 [바탕 업무배정](references/delegation.md)을 따른다. 개발·문서·도면의 검토 기준은 [마디 실행 계약](components/madi/references/workflow-contract.md)에서 확인한다.

실제 호스트를 확인해 [Codex 안내](references/hosts/codex.md)의 해당 작업에 필요한 부분과 적용 정책을 확인한다. 유효한 원문은 재사용한다. 호스트를 알 수 없으면 해당 진입 단계에서 중단한다. 메인은 요청·권한을 판단하고 직접 처리 또는 위임하며 결과를 확인한다. 위임 시 필요한 정책·절차·자료와 범위를 전달하고, 자식은 전달받은 범위와 실제 위임 규약을 따른다. 지침 읽기 자체는 권한이 아니다.

사용자가 바탕을 명시 호출한 요청과 같은 작업의 후속 요청에 필요한 내부 절차를 적용한다. 같은 대화라도 무관한 새 작업에는 바탕 고유 절차를 자동 연장하지 않는다. 일반 개인·프로젝트 규칙과 기존 역할·권한은 유지한다. 적용 범위는 대화에 전달된 지침의 자동 제거 또는 보안 격리를 뜻하지 않는다. 스킬 등록은 추가 권한이 아니다.

합성 예: “선택한 노트에서 근거를 찾아줘”는 허용 자료를 조회하고 답·근거·미확인을 보고한다. “이 대화만 요약해줘”는 저장 요청이 아니므로 저장하지 않는다. 반영 요청은 범위·권한·백업을 확인하고 저장과 관계 상태를 보고한다. 개발·문서 요청은 산출물과 적용된 검토·미확인을 보고한다. [합성 계획 예시](components/madi/references/synthetic-example.md)를 참고한다.

바탕을 호출한 요청에 적용할 [공통 표현 지침](components/madi/references/clear-language.md)은 유효한 원문을 재사용하고 필요한 부분을 확인한다. 이 지침은 마디 실행이나 별도 도구·검토를 강제하지 않는다.

## 필요한 절차 선택

지식 조회와 관계 검토에는 [조회 안내](references/query.md)와 [조회 프로세스](references/calls.md#조회-프로세스)를 필요할 때 사용한다. 구현 전체를 매번 탐색하지 않는다.

[나루](components/naru/workflow.md)로 요청을 분기하고 필요한 조항만 확인한다. 해당 대상의 유효한 준비 근거가 없거나 조건이 달라지면 [가닥](components/gadak/workflow.md)의 해당 부분을 확인한다. 자료를 읽거나 변경할 때는 [두레](components/dure/workflow.md)의 범위를 확인한다. 조회에는 [조회와 허용 범위](references/source-access.md#조회와-허용-범위)와 [출처와 근거 판단](references/knowledge-contract.md#출처와-근거-판단)을, 변경에는 [쓰기와 백업 복구](references/source-access.md#쓰기와-백업-복구), [변경·복구](references/knowledge-contract.md#변경복구)와 필요한 [문서 형식](references/knowledge-contract.md#v1v2-정규-frontmatter)을 확인한다.

대상·설정·버전·권한·고정본이 같은 유효한 준비 근거는 재사용하며, 변경·오류·불명이 있으면 영향 부분을 재확인한다. 같은 고정본의 유효한 등록·manifest 근거는 실행 간 재사용한다. 새 등록 선택·설치·전송이나 관련 변경·오류·불명 시 실제 경로와 manifest를 다시 검증한다.

그 밖의 절차는 요청에 필요한 것만 읽는다.

- [가닥](components/gadak/workflow.md): 프로젝트 설정, 필수 의존성과 설치 준비를 확인한다.
- [나루](components/naru/workflow.md): 요청에 맞는 지식·개발·문서·도면 경로를 선택한다.
- [두레](components/dure/workflow.md): 권한 범위, 기대 hash, 백업·복구와 실행 상태를 확인한다.
- [수풀](components/supul/workflow.md): 선택한 지식의 조회·반영·정정을 다룬다. 필요한 경우 [갈피](components/supul/galpi/workflow.md)의 원문·출처, [고리](components/supul/gori/workflow.md)의 관계 자료, [보기](components/supul/bogi/workflow.md)의 설명·시각화 절차를 읽는다.
- [마디](components/madi/workflow.md): 개발·문서·도면 요청에만 읽고 계획·작성하고 적용되는 검토를 수행한다. 일반 지식 조회에 강제하지 않는다.

각 이름은 단일 바탕 스킬 안의 책임이며 독립 프로그램이 아니다. 실제 도구 실행과 권한 판단은 호스트가 맡는다. 요청에 필요한 절차만 읽고, 활성 목록과 허용된 개별 자료를 넘어서 접근하지 않는다. Graphify 갱신과 시각화는 각각 승인된 관련 변경과 요청이 있을 때만 수행한다.
