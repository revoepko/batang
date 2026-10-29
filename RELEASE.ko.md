# 변경 기록

[English](RELEASE.md)

## 0.1.0

### 추가

- 선택한 노트를 독립 복제본으로 가져오며 원본을 보존하고 출처를 기록합니다. 메타데이터가 없거나 지원 범위의 YAML을 사용하는 노트는 변환할 수 있습니다. 미지원 속성이나 구조는 검토를 위해 보류합니다. [가져오기 안내](skills/batang/references/import.md)
- 노트에 별칭(`aliases`)을 지정할 수 있습니다.
- 조건에 맞는 빈 임시 파일과 폴더를 정리할 수 있습니다. 기본적으로는 자동 정리를 보류합니다. AI가 같은 잠금 규칙을 따르는 다른 작업과 동시에 접근하지 않도록 확인하고 잠금을 유지할 때만 정리합니다. 이 잠금은 규칙을 따르지 않는 앱의 접근을 막는다고 보장하지 않습니다. 파일 반영에 실패하거나 결과가 불확실하면 내용을 보존합니다. [파일 접근 안내](skills/batang/references/source-access.md)

### 변경

- 보기의 [재사용 HTML 설명 패널 예제](skills/batang/components/supul/bogi/assets/explanation-panel.html)는 항목을 선택하면 같은 자리의 내용을 바꿔 보여 줍니다. 허용된 내용과 출처로 바꾸어 사용할 수 있습니다. PC와 모바일에서 스크롤을 강제하지 않고 조건을 바로 확인할 수 있으며 JavaScript가 없어도 내용을 읽을 수 있습니다.
- 권장 모델을 사용할 수 없을 때 작업을 총괄하는 AI가 프로젝트의 필수 기준을 지키며 허용된 대안 모델을 선택할 수 있도록 안내합니다. [실행 계약](skills/batang/components/madi/references/workflow-contract.md)
- 선택한 활성 노트의 별칭으로 관련 노트를 살펴볼 수 있습니다. AI가 별칭과 노트를 대조하며 Graphify 자체의 자동 별칭 검색은 보장하지 않습니다. [관계 안내](skills/batang/components/supul/gori/workflow.md)

### 호환성

- 별칭 항목이 있는 노트는 바탕 0.1.0에서 읽을 수 있습니다. 이전 버전에서는 읽을 수 없습니다.
