# 문서 간 관계 처리

조회와 검토 입력 준비는 [조회 안내](query.md)와 [고정 호출](calls.md)을 따른다. 원 관계 기록의 조회 결과는 현재 확정 관계의 표시 투영이 아니다. 자료 정합성, 내용 판단과 노출 가능성은 각각 확인한다.

이 문서는 바탕의 내부 관계 처리 계약을 설명한다. 호출과 파일 범위는 호스트가 현재 요청·프로젝트 설정·사용자 권한에 따라 결정하며, 아래 필드나 함수가 새로운 CLI·provider·권한을 제공하지는 않는다. 지식 원본은 Markdown이고 graph는 재생성 가능한 파생 자료다. 전체 절차는 [고리](../components/supul/gori/workflow.md)를 따른다.

## 대상과 비교 범위

`targets`는 이번에 등록하거나 의미 추출을 갱신할 활성 문서다. `comparisons`는 기존 관계 후보를 찾기 위해 읽도록 허용된 활성 문서다. 비교 문서의 본문과 metadata, 기존 문서 노드의 의미 내용을 다시 쓰지 않는다. 기존 endpoint는 선택된 활성 목록에서 실제 문서 ID·graph node ID·현재 해시의 대응을 확인한다. 이 확인에 실패하면 해당 참조와 관계를 대기로 두고 임의로 다른 노드를 선택하지 않는다.

`ACTIVE.md`나 graph에 항목이 있다는 사실은 읽기 권한이 아니다. 명시 허용된 원문에 대해서만 `read_active_documents`로 대상과 비교 자료를 준비한다. 두 선택은 같은 root·활성 목록·목록 hash를 사용하며 공통 문서 ID가 있으면 동일한 원문이어야 한다. 관계 ID나 파일 경로는 별도의 권한을 부여하지 않는다.

## 호스트의 의미 추출 순서

1. `targets`의 허용된 원문에서 문서 내부 개념과 근거를 추출하고 예상 chunk와 출처를 확인한다. 반환 누락·오류·stale 또는 부분 추출은 게시 전에 중단한다.
2. 허용된 `comparisons`와 기존 관계를 이용해 문서 간 후보를 찾는다. 명시 참조, 기존 관계, 제목·별칭·태그·본문 표현은 후보 신호다. 호스트는 같은 허용 범위 안에서 의미가 관련된 후보를 추가할 수 있다.
3. 각 후보의 현재 원문과 조건을 비교해 `accepted`, `no_relation`, `deferred`를 판단한다. 공통 주제, 의존, 지지, 충돌, 대체의 뜻과 방향을 혼동하지 않는다. 태그나 별칭이 같다는 사실만으로 관계를 확정하지 않는다. 문서 쌍의 판단과 별도로 각 관계 종류·방향·조건의 판단도 구분한다.
4. 채택한 assertion과 지원 근거를 준비한다. 채택 전 관계 종류·방향·의미 조건에 필요한 전제를 원문과 대조하고 저장할 근거 묶음이 주장을 지지하는지 확인한다. 원문에 없는 재사용·변환·동일 적용 상황을 가정해 서로 다른 범위의 주장을 충돌로 만들지 않는다. 전체 원문에서 확인한 필수 전제가 근거 구간에서 빠졌다면 해당 근거를 포함하고, 확인하지 못한 전제는 주장에 보충하지 않는다. 기존 관계의 끝점과 근거 중 `targets`가 포함된 것과 명시적으로 검토가 승인된 관계를 영향 대상으로 살핀다. 새 추출에 관계가 없다는 이유만으로 기존 근거를 철회하지 않는다.
5. 입력의 출처·권한과 저장 조건을 확인하고 관계 갱신을 수행한다. 문서 노드 coverage, 후보 탐색, 관계 검토와 graph 게시 상태를 별개로 확인해 보고한다.

후보 탐색의 `complete`는 실제로 살핀 허용 범위·방법에 한정되며 의미 완전성 보장이 아니다. 해당 범위의 접근 불가, 후보 누락, 미재검토 영향 관계 또는 판단 충돌은 검토 작업의 완료로 표현하지 않는다. 현재 근거를 검토한 뒤 타당하게 명시한 `deferred`는 관계의 확정을 보류한 판단이며 검토 작업 자체는 완료일 수 있다. 이때 기존 `relation_status`는 `partial`로 남을 수 있고 보류 관계는 확정 투영에서 제외한다. 정당하게 관련 관계가 0개인 경우와 탐색·검토를 하지 않은 경우도 구분한다. 구조와 해시 검사는 근거가 실제로 존재하는지 확인하지만 주장 간 의미적 적절성은 호스트의 판단과 별도 평가가 필요하다.

원문의 각 절에서 실제로 주장한 범위와 의미 강도를 확인한다. 어떤 내용을 적용하라는 지시가 그 내용 전체에 대한 의존을 항상 뜻하지는 않는다. 유지하라는 말이 언제나 검사를 뜻하지 않으며, 일부 항목에 대한 조건을 문서 전체의 계약으로 확대하지 않는다. 두 근거의 적용 대상·버전·조건이 같은지 살피고 필요한 의미나 범위가 확인되지 않으면 해당 주장만 보류한다.

`references`는 문서에 대한 명시 참조를, `depends_on`은 내용에 대한 의존을 나타낸다. `depends_on` 후보는 A의 과제·필요, B가 정의·제공하거나 제한하는 내용, 두 내용의 대상·범위·기능이 연결된다는 근거를 대조한다. 이것은 내용 수준의 의존 추론이며 특정 정책이 실제로 채택·구현됐거나 작업이 완료·성공했다는 주장은 별도의 근거가 필요하다. 좁은 내용 의존에 실제 완료·성공, 하이퍼링크 또는 A가 B의 모든 정의를 되풀이한 사실을 필수로 요구하지 않는다. 핵심 연결이나 판단에 필요한 대상·시점이 확인되지 않으면 해당 의존은 `deferred`로 둔다.

링크나 조건 공유, 단어 일치 또는 가능성만으로 의존을 확정하지 않는다. A와 B가 같은 대상·범위에 적용되는지와 각 문서가 자기완결적인 병행 규칙일 가능성도 살핀다. 대안이 실제 원문 근거로 지지되는지와 단순히 가능하다는 추측을 구분하며, 다른 해석이 가능하다는 이유만으로 모든 추론을 보류하지 않는다. 시점이 모호한 현재 정책은 연결할 근거가 없으면 보류한다. A가 조건을 다시 설명했다는 이유만으로 의존을 자동 부정하지 않는다. `INFERRED` 표기는 추론임을 나타낼 뿐 채택 권한이나 근거를 대신하지 않는다. 어떤 종류의 관계든 각 절이 양쪽 문서에 똑같이 쓰여 있어야 한다고 요구하지 않고 해당 종류의 정의·방향·조건에 따라 근거 묶음 전체가 연결을 지지하는지 판단한다.

넓은 주장에 불확실한 부분이 있으면 그 판단은 보류하고, 원문으로 독립적으로 성립하는 더 좁은 주장이 있는지 별도로 검토한다. 좁은 후보도 해당 관계 종류의 정의·방향·조건과 원문 근거를 대조하고 뒷받침되지 않으면 보류한다. 필요한 조건을 삭제하거나 상식으로 목적·효과·순서를 보충해 주장을 성립시키지 않는다. 의미가 바뀐 좁은 주장은 새 qualifier와 관계 ID로 구분하고 기존 관계·근거·보류 이력을 보존한다. 의미 없이 qualifier만 바꾸어 보류를 우회하지 않는다. 기존 qualifier의 의미가 같은 관계를 재채택할 때는 기존 ID와 현재 근거 proposal을 사용한다.

실제로 고려한 종류·방향·조건은 채택뿐 아니라 보류와 무관계 판단도 기존 `assertion_decisions`에 남긴다. 검토한 후보의 판단 요약은 근거를 확인할 수 있게 쓰되 숨겨진 추론 과정의 제출을 요구하지 않는다. 모든 쌍에 모든 관계 종류를 전수 생성하거나 검토하지 않은 종류를 완료로 표시하지 않는다.

## 내부 함수와 갱신 입력

바탕의 내부 scripts 경로에서 `graph_ops`와 `relationship_ops`를 사용한다. `graph_ops.refresh_graph`는 선택 keyword `relationship_request`를 받는다. 이를 생략하거나 `None`이면 기존 v1 경로를 사용한다. 요청을 명시하면 v2 관계 처리 경로를 사용하며, 기존 graph가 v1이면 명시 전환 전에는 거부한다. graph가 없는 경우 승인된 범위의 새 v2 graph를 만들 수 있다. `registration_lifecycle`와 `resume_registration`은 `graph` 인자에 관계 요청을 전달할 수 있다.

호스트가 준비할 `relationship_request`의 모양은 다음과 같다. `comparisons`는 직렬화된 경로 목록이 아닌 허용된 실제 `ActiveDocuments` 객체다. 아래의 `...`는 설명용 자리표시자다. 사전에 `FileScope`·대상·chunk·백업·기대 hash를 실제 승인 범위에서 준비해야 하므로 이 예시는 그대로 실행하는 명령이 아니다.

```python
relationship_request = {
    "comparisons": comparisons,  # 생략 또는 None이면 targets만 비교
    "candidate_plan": {
        "method": "후보 탐색 방법",
        "status": "complete",  # complete / partial / not_run
        "considered_document_ids": ["문서 A ID", "문서 B ID"],
        "candidates": [{"source_document_id": "문서 A ID",
                        "target_document_id": "문서 B ID", "signals": ["후보 단서"]}],
        "omissions": [],
    },
    "decisions": [{"source_document_id": "문서 A ID", "target_document_id": "문서 B ID",
                   "decision": "accepted", "relation_ids": ["계산된 관계 ID"],
                   "reason": "원문 비교 판단 이유"}],
    "assertion_decisions": [],
    "relations": [relation],
    "retract_supports": [],
    "unavailable_document_ids": [],
    "removed_document_ids": [],
    "affected_relation_ids": [],
    "renamed_documents": [],
}
```

`candidate_plan`은 필수이며 위의 다섯 필드를 포함한다. `decisions`·`relations`와 나머지 목록은 생략하면 빈 목록이다. 각 후보 문서 쌍은 한 번만 나열한다. `accepted`에는 채택한 `relation_ids`를 넣고 `no_relation`·`deferred`에는 빈 배열을 사용한다. 새 assertion은 같은 문서 쌍의 `accepted` 결정에 연결해야 한다. 명시 철회 항목은 `relation_id`, `support_ids`, `reason`을 담는다. `unavailable_document_ids`는 접근할 수 없다고 확인한 문서만, `removed_document_ids`는 명시적으로 삭제·등록 해제된 문서만 지정한다. 관계 ID를 목록에 넣는 것 자체는 변경 권한이 아니다.

도구가 찾은 후보는 검토 단서이며 그대로 의미 검토 목록이 확정되는 것은 아니다. 허용된 현재 원문에서 대상·기능·조건을 확인해 실제 검토할 문서 쌍을 선별하고, `candidate_plan`의 `candidates`, `method`, `considered_document_ids`와 상태·누락은 실제 검토 범위에 맞춘다. 신호가 있었던 쌍을 제외한다면 쌍별 또는 공통 근거군별 이유와 근거를 확인해 기록하며, 제외는 모든 관계 종류에 대한 `no_relation`을 뜻하지 않는다. 근거를 아직 읽지 못했거나 시간·예산 때문에 검토하지 못한 쌍을 범위 밖으로 바꾸어 완료로 만들지 않고, 부분 탐색과 누락을 그대로 구분한다. 실제 검토가 필요한 쌍이 남으면 기존 결과를 보존하면서 원래 허용 범위 안에서 후속 보완한다. 이는 모든 문서 쌍이나 모든 종류의 전수 검토를 강제하거나 도구가 자동 선별·완료를 판정한다는 뜻이 아니다.

### 개별 관계 판단과 보류

문서 쌍에 대한 `decisions`와 별도로 선택 필드 `assertion_decisions`에 특정 종류·방향·조건의 판단을 기록할 수 있다. 각 항목은 다음 두 형태 중 하나를 사용하며 `decision`은 `accepted`, `no_relation`, `deferred` 중 하나다.

```python
# 기존 관계 또는 이번에 제안한 관계의 ID로 지정
{"relation_id": "관계 ID", "decision": "deferred", "reason": "판단 보류 이유"}

# 문서 쌍과 개별 관계의 종류·조건으로 지정
{"source_document_id": "문서 A ID", "target_document_id": "문서 B ID",
 "kind": "depends_on", "qualifier": "검토할 조건",
 "decision": "deferred", "reason": "판단 보류 이유"}
```

같은 문서 쌍에서 한 관계를 채택하면서 다른 종류나 조건의 관계를 보류할 수 있다. 다만 같은 관계 ID를 `accepted` 목록에 넣으면서 동시에 `deferred`로 지정하지 않는다. 저장되는 검토 기록은 관계 ID·문서 쌍·종류·조건·판단·이유·`context_document_ids`를 정규화해 남긴다. 실제 읽은 원문의 hash는 해당 `review.documents`에서 확인한다. 보류 맥락에는 양 끝점과 기존·제안 support의 모든 근거 문서 ID를 유지하지만 현재 읽지 못한 문서의 hash가 기록됐다고 추정하지 않는다.

기존 `active` assertion을 명시 보류하면 관계 상태는 `unknown`이 되고 기존 support 이력은 그대로 보존된다. 아직 만들지 않은 관계의 보류는 검토 기록에만 남는다. `unknown` 관계를 다시 채택하려면 현재 endpoint와 완전하고 유효한 active support 하나의 모든 근거를 검증한 proposal을 명시적으로 제공한다. 각 support 내부 근거는 모두 필요하지만 서로 다른 support는 대체 근거이므로 과거의 모든 support 문서에 현재 접근할 필요까지 강제하지 않는다. 단순히 다음 입력에서 보류를 생략하거나 같은 쌍의 다른 종류·조건을 채택하는 것으로 이전 보류가 해제되지 않는다.

기존 관계에 대해 종류·조건별 `no_relation`을 확정하려면 해당 관계의 근거를 명시적으로 철회한 뒤 `retracted` 상태가 되어야 한다. 기존 assertion이 없는 경우에는 그 관계를 만들지 않고 `no_relation` 검토를 마칠 수 있다. 관련 범위에 해결되지 않은 보류가 있으면 기존 호환 상태인 `relation_status`는 `partial`이다. 현재 근거를 검토해 타당하게 보류했다면 별도의 `review_work_status`는 `complete`일 수 있다. 원문 hash가 바뀌어 보류 판단이 stale이 된 경우에도 자동 해제하지 않는다. 이번 검토와 무관한 다른 범위의 보류까지 현재 범위의 `relation_status`를 일률적으로 `partial`로 만들지는 않는다.

아직 생성되지 않은 보류를 채택하거나 `no_relation`으로 해결할 때는 해당 endpoint를 `targets`에 선택한 관계 갱신으로 수행한다. `affected_relation_ids`는 이미 존재하는 `relations`의 ID만 지정하며, `comparisons`만 읽는 권한을 변경 권한으로 취급하지 않는다.

검토 기록에는 필요할 때 직전 기록의 `previous_review_id`가 연결된다. 직전과 실질 내용이 같은 재시도는 기존 ID를 재사용하며, 보류 뒤 이전과 같은 채택 내용으로 돌아오는 것은 새로운 판단 사건으로 보존한다. 이 연결은 호스트가 입력할 필드가 아니다.

새 `accepted` 검토 사건에는 당시 endpoint와 원문·근거 구간이 모두 검증된 완전한 OR support의 ID를 담은 `accepted_support_ids`가 기록된다. 이 목록은 정렬되고 중복이 없으며 비어 있지 않다. helper가 기록하며 호스트 입력 필드가 아니다. 이후 더 좁은 허용 범위에서 다른 OR support를 사용하려면 당시 목록의 같은 support였는지와 당시 snapshot, 현재 원문 및 구간 hash를 대조한다. 당시 대표 근거로 사용한 다른 support 문서의 현재 접근을 강제하지 않으며, 당시 목록에 없고 나중에 추가된 support만으로 과거 보류를 해제하지 않는다. 과거 typed 사건에 이 목록이 없으면 원래 `context_document_ids`와 snapshot의 일치만 보수적으로 확인한다. 과거 legacy 사건도 snapshot 검증의 한계를 유지한다. 이 일치는 해당 support ID가 당시 목록에 있었다는 증거가 아니며 다른 OR support까지 당시 승인됐다고 소급 추정하지 않는다. 필요한 경우 현재 근거를 제공해 명시적으로 재채택하면 새로운 사건에 검증된 support 목록이 기록된다. 기존 사건을 자동 보강하거나 원형을 바꾸지 않는다.

승인된 경로 변경은 `renamed_documents`에 `{"document_id": "기존 ID", "old_path": "이전 상대 경로", "new_path": "현재 상대 경로"}`로 명시한다. 같은 root 안의 다른 정상 상대 경로만 허용한다. 현재 대상·활성 목록의 새 경로와 ID·hash, 기존 graph에서 같은 ID의 유일한 문서 노드와 이전 경로를 대조하며 node ID를 보존한다. 이전 경로가 여전히 활성화돼 있거나 새 경로를 다른 ID가 점유하는 등 충돌이 있으면 거부한다. 해당 문서의 이전·새 경로 semantic만 교체하고 AST·비교 문서·다른 출처·legacy 자료는 보존한다. 같은 ID의 경로만 바뀌고 hash가 같으면 관계 ID와 근거를 유지하며, hash가 바뀌면 근거를 stale로 두고 명시 재검토한다. 이 입력은 원문 파일 이름 변경·삭제나 활성 목록 편집을 수행하지 않는다. 문서 ID 변경은 자동 대응하지 않는다.

`relationship_ops.discover_candidates(targets, comparisons=None, envelope=None)`은 전달된 범위의 명시 참조·metadata·본문 표현·기존 관계와 보류된 후보를 바탕으로 후보 계획을 준비한다. 허용 범위 밖에 있어 검토할 수 없는 경우는 누락으로 구분한다. 호스트가 실제 원문을 비교해 결론을 채우며, 후보에 없는 허용 범위의 관련 문서를 추가할 수 있다. 이 함수가 뜻을 판단하거나 모든 관계를 찾아낸다고 가정하지 않는다.

`relationship_ops.relation_id(source_document_id, target_document_id, kind, qualifier)`로 관계 ID를 계산한다. `evidence_span(document, start_line, end_line)`은 `parse_document`로 분리된 본문에서 개행을 포함한 1부터 시작하는 양끝 포함 줄 범위의 hash와 원문 hash를 만든다. `support_set_id(evidence, confidence="EXTRACTED")`로 근거 묶음 ID를 계산한다. `support_sets` 내부 evidence는 AND, 다른 support set은 OR이며 의미상 충분성은 호스트가 확인한다.

아래는 호스트가 이미 읽기와 비교를 허용받고, 두 문서의 첫 줄이 같은 주제를 실제로 뒷받침한다고 확인한 **합성 예시**다. 실제 작업에서는 적절한 문서와 근거 줄을 사용하고 이를 후보·판단과 연결한다.

```python
from relationship_ops import evidence_span, relation_id, support_set_id

source_id, target_id = sorted((doc_a.document_id, doc_b.document_id))
evidence = [evidence_span(doc_a, 1, 1), evidence_span(doc_b, 1, 1)]
relation = {
    "relation_id": relation_id(source_id, target_id, "shares_topic", "공통 주제"),
    "source_document_id": source_id,
    "target_document_id": target_id,
    "kind": "shares_topic",
    "qualifier": "공통 주제",
    "support_sets": [{
        "support_id": support_set_id(evidence, "INFERRED"),
        "confidence": "INFERRED", "evidence": evidence,
        "rationale": "두 문서의 근거가 같은 주제를 다룸", "status": "active",
    }],
    "status": "active",
}
```

관계의 `qualifier`와 support의 `rationale`은 비어 있지 않은 문자열이어야 한다. `shares_topic`처럼 대칭인 종류는 정렬된 문서 ID를 사용하며, 방향성 관계의 양 끝 순서를 임의로 정렬하지 않는다. 지원 묶음의 hash가 일치해도 실제 의미 판단이 맞는지는 별도로 살핀다.

`refresh_graph(..., relationship_request=relationship_request)`의 반환값에서 기존 `status`, `coverage`, `candidate_status`, `relation_status`, `review_id`를 유지하고 새 `review_work_status`와 `judgment_summary`를 별도로 확인한다. `status="current"` 또는 문서 coverage는 문서 대응·게시 상태이며 관계 검토의 완료를 뜻하지 않는다. 기존 `relation_status`는 호환을 위해 의미를 유지한다. 적절한 보류가 있으면 `partial`이 남을 수 있으므로 새 작업 완료 여부의 대용으로 사용하지 않는다. 예상 chunk가 누락되면 `pending`으로 기존 graph를 유지한다.

`review_work_status`는 명시된 `candidate_plan` 범위와 `targets`의 후보·영향 관계에 대한 실제 판단과 근거의 현재성을 나타내며 `complete`, `partial`, `not_run`, `unknown`을 사용한다. 기존 전체 coverage를 나타내는 `candidate_status`가 `partial`이어도 이번 검토 작업은 완료일 수 있다. 현재 근거를 확인하고 적절히 `deferred`로 결론을 내린 경우도 `complete`일 수 있다. 후보나 영향 관계를 검토하지 않았거나 필요한 현재 snapshot이 일치하지 않거나 판단 충돌이 있으면 `partial`이다. 보존된 과거 support가 stale이거나 관계가 `unknown`이라는 사실만으로 현재 작업을 `partial`로 만들지는 않는다. 완료는 의미 확정·정확도·게시 성공·권한을 대신하지 않는다.

`judgment_summary`는 다음 형태다. 각 값은 helper가 산출하는 것으로 호스트가 임의로 입력하는 결과가 아니다. `pair_decisions`와 `assertion_decisions`는 각각 해당 단위의 판단 수이며, ID 배열은 해당 관계의 목록이다.

```json
{
  "pair_decisions": {"accepted": 0, "no_relation": 0, "deferred": 0},
  "assertion_decisions": {"accepted": 0, "no_relation": 0, "deferred": 0},
  "pending_assertion_ids": [],
  "unreviewed_pair_count": 0,
  "unreviewed_assertion_count": 0,
  "stale_assertion_ids": [],
  "unavailable_assertion_ids": [],
  "decision_conflict_count": 0
}
```

helper는 새 review에 두 필드와 실제 영향받은 기존 관계 ID의 `affected_relation_ids`를 산출해 저장한다. 이 review 결과는 호스트가 직접 선언하지 않는다. 앞서 설명한 요청의 `affected_relation_ids`는 검토를 요청하는 추가 범위로서 별도이며 권한을 부여하지 않는다. 저장된 과거 graph의 판정값은 원형대로 읽어들이며 수정하지 않는다. 읽기 전용 `relationship_ops.summarize_review(envelope, active_documents)`는 최신 범위와 현재 hash를 다시 대조해 `review_id`, `review_work_status`, `judgment_summary`, `basis`를 반환한다. `basis`의 `stored`는 저장된 근거, `derived`는 과거 기록에서 충분한 근거를 확인해 읽기 시 도출한 결과, `insufficient`는 근거 부족을 뜻한다. 근거가 부족하면 완료를 추정하지 않는다. 구체적으로 충돌이 확인되면 `partial`, 후보 탐색이 실행되지 않았으면 `not_run`, 그 외 충분한 근거가 없으면 `unknown`으로 구분하며 과거 review를 수정하지 않는다.

이 함수는 이미 읽기가 승인된 envelope의 최신 review 전체를 요약한다. `active_documents`는 현재 원문 검증 근거이며 출력 권한 필터가 아니다. 호스트는 사용자에게 표시할 범위를 기존 읽기 권한에 따라 별도로 확인한다. 허용된 노트만의 관계도나 경로를 만들 때는 권한 범위로 걸러진 `project_graph`를 사용한다.

`no_relation` 판단을 내렸지만 같은 문서 쌍에 활성 관계가 남았거나, `accepted`의 관계 ID가 최종 활성 관계 집합과 일치하지 않으면 `relation_review`의 `decision_conflicts`에 남는다. 안전한 게시가 가능하더라도 이 불일치를 자동으로 관계 삭제나 판단 수정으로 해결하지 않으며, 관계 검토 작업을 완료로 보고하지 않는다. 해당 기록의 충돌 내용과 `review_work_status`·판단 요약을 함께 확인해 남은 판단·근거를 재검토한다.

## 관계 형식

새 graph는 `batang_graph_format: 2`, `content_graph`, `relations`, `relation_review`로 구성된 단일 JSON이다. `content_graph`는 기존 node-link graph와 문서 내부 개념을 담고, `relations`는 문서 간 assertion과 근거의 기준이다. `relation_review`는 선택된 범위와 원문 hash에 한정된 후보·판단 근거를 보존한다. 최상위 `nodes`와 `links`는 사용하지 않는다. 아래는 모양을 설명하는 예시이며 저장·승인 명령이 아니다.

```json
{
  "batang_graph_format": 2,
  "content_graph": {"directed": false, "multigraph": false, "graph": {}, "nodes": [], "links": []},
  "relations": [],
  "relation_review": []
}
```

문서 간 assertion은 `relation_id`, `source_document_id`, `target_document_id`, `kind`, `qualifier`, `support_sets`, `status`를 담는다. 종류는 `references`, `depends_on`, `supports`, `contradicts`, `supersedes`, `shares_topic`이며 `contradicts`, `shares_topic`만 대칭이다. 관계 ID는 종류·양 끝 문서 ID·의미 조건의 정규화된 값으로 계산한다. 대칭 관계에만 양 끝 순서를 정규화하며 조건은 NFC·공백 정규화를 적용하고 대소문자를 보존한다. 파일 경로·원문 hash·표시명은 ID에 넣지 않는다. 같은 문서 쌍이라도 관계 종류·방향·의미 조건이 다르면 다른 assertion이다.

| `kind` | 의미와 방향 |
|---|---|
| `references` | 원문이 다른 문서를 명시적으로 참조한다. 참조하는 문서 → 참조받는 문서. |
| `depends_on` | 한 내용이 다른 내용에 의존한다는 명시적 또는 검토된 근거가 있다. 의존하는 문서 → 근거 문서. |
| `supports` | 같은 주장과 적용 조건을 대조해 한 문서가 다른 문서의 주장을 지지한다. 지지 문서 → 대상 문서. |
| `contradicts` | 같은 주장·조건·적용 범위를 비교해 충돌이 확인된다. 대칭 관계이며 비교 조건을 남긴다. |
| `supersedes` | 승인·폐기 등 실제 근거로 후속 문서가 이전 내용을 대체한다. 후속 문서 → 이전 문서. 최신 날짜만으로 결정하지 않는다. |
| `shares_topic` | 두 문서가 같은 개념 또는 적용 주제를 다룬다. 대칭 관계이며 주제와 적용 범위를 남긴다. |

호스트는 명시적인 문서 간 링크가 없더라도 허용된 원문을 비교해 한 문서의 내용이 다른 문서의 조건이나 전제에 의존하는지 검토한다. 공통 주제만으로 의존을 확정하지 않으며 방향과 실제 근거를 확인한다. `shares_topic`은 근거 있는 다른 종류의 관계를 대신하지 않는다. 같은 쌍에서 여러 종류나 방향이 각각 근거로 뒷받침되면 각 assertion을 구분해 기록한다. 판단할 근거가 부족하면 보류한다.

하나의 `support_sets` 항목은 `support_id`, `confidence`, `evidence`, `rationale`, `status`를 담는다. `confidence`는 `EXTRACTED` 또는 `INFERRED`다. 각 evidence는 `document_id`, `source_sha256`, `start_line`, `end_line`, `span_sha256`으로 원문 본문의 UTF-8 줄 범위와 실제 근거를 지정한다. 줄 번호는 1부터 시작한다. 하나의 support set에 든 evidence는 모두 필요하고, 서로 다른 support set은 각각 독립적인 대체 근거다. 두 endpoint와 evidence 문서가 모두 해당 관계의 의존 대상이다. 전체 본문이나 대화를 복사하지 않는다.

본문이 바뀌면 영향받은 근거는 이전 hash를 새 값으로 자동 승계하지 않는다. 근거 철회가 명시된 경우에는 해당 support만 철회하고 다른 독립 근거가 충분한지 살핀다. 자료 부재나 권한 상실은 삭제로 추정하지 않는다. 문서 경로 변경과 ID 변경을 구분하며 의미 조건의 변경은 이전 관계의 종료와 새로운 assertion으로 구분한다.

## 자료 갱신과 호환

기존 v1 graph는 자동 전환하지 않는다. 승인된 명시 전환에서는 원본 snapshot과 hash를 확보하고 별도의 후보와 백업을 준비하며 v1 노드·속성·관계의 보존을 대조한다. 기존 문서 간 edge가 있거나 양 끝 문서를 식별할 수 없어도 임의로 버리지 않는다. 검토되지 않은 legacy 관계는 기본 확정 관계 투영과 경로 검색에 넣지 않고 원형을 보존하며, 의미와 근거를 검토한 뒤에만 새 assertion으로 승계한다.

명시 migration 직후에는 원형 edge가 `content_graph`에 남을 수 있다. 이후 승인된 v2 갱신은 노드를 교체하기 전에 문서 간 edge와 소유자를 식별할 수 없거나 출처가 일치하지 않는 semantic edge를 현재 edge 목록에서 분리해 `content_graph.graph.batang_legacy_relations`에 보존한다. 이 archive는 `archive_version: 1`과 `records`를 포함하며 각 기록은 원래 edge, 양 endpoint의 전체 node 속성, 방향과 hash 기반 `record_id`를 담는다. 같은 기록은 중복하지 않고 기존 기록을 누적 보존한다. 키 충돌이나 지원하지 않는 archive 형식은 거부한다. archive는 현재 개념 노드의 수명과 독립적이며 기본 투영·후보 탐색이나 활성 관계의 근거로 사용하지 않는다. 조회나 형식 검사만으로 이를 쓰지 않는다.

v2 JSON 전체에 기대 hash, 백업, 후보 재읽기와 게시 직전 원문·목록·graph 재확인을 적용한다. 부분 후보 탐색이나 판단 보류는 미검토 관계의 삭제나 부정을 뜻하지 않는다. 관계 갱신의 게시 전 오류는 기존 graph를 유지하고 대기로 보고한다. 관계 갱신 중 게시 후 확인 실패는 `publication_uncertain`으로 구분하고 현재 graph와 백업을 먼저 대조한다. graph 게시와 원문·활성 목록 저장을 하나의 트랜잭션으로 주장하지 않는다.

`relationship_ops.migrate_graph(v1_bytes)`는 파일을 쓰지 않고 v2 후보 bytes만 반환한다. 실제 게시가 승인된 때의 `publish_migration(active_documents, *, graph_scope, graph_path, expected_graph_sha256, work_scope, baseline_path, candidate_path, backup_scope=None, backup_path=None)`은 별도 작업 위치와 기존 백업·기대 hash 조건을 사용한다. `restore_graph(*, graph_scope, graph_path, expected_graph_sha256, restore_bytes, backup_scope, backup_path)`는 현재 v2의 기대 hash와 백업 범위를 요구한다. 전환·복구 helper는 `status`, `graph_written`, `publication_uncertain`, `graph_sha256`을 포함한 딕셔너리를 반환하고 실패 시 `error_code`를 포함한다. 입력과 기대 hash의 일부 오류는 게시 전 예외로 거부한다. 예외 또는 `pending`을 받으면 게시 여부를 추정하지 말고 현재 파일과 백업을 확인한다. 각 함수의 호출 자체는 전환이나 복구 권한이 아니다. 작업 후 반환값과 저장본을 대조한다.

Graphify 분석·시각화에는 허용된 현재 원문을 확인한 메모리 투영을 사용한다. 같은 노드 쌍의 여러 관계와 근거는 canonical assertion에 보존하고 표시용 물리 edge의 수를 관계의 수로 취급하지 않는다. 기본 투영은 접근 불가·stale·철회·미확인 관계를 확정 관계로 표시하지 않으며, 비허용 endpoint나 근거를 노드 이름·연결 수·경로로 간접 노출하지 않는다. v2 envelope를 기존 `graphify export`에 직접 넘기지 않는다. 투영 결과를 canonical 관계에 재입력해 덮어쓰지 않는다. 조회 자체는 읽기 전용이다.

기본 투영은 과거 문서 쌍 단위의 `deferred` 기록도 읽기 전용으로 반영해, 해당 보류 관계를 명시적으로 재채택하기 전까지 확정 표시에서 제외한다. 이는 관계의 노출을 제한하는 처리이며 전체 검토 상태가 `partial`인지와 별개다. 원문이 바뀌었다는 이유만으로 보류를 자동 해제하지 않는다.

`relationship_ops.project_graph(envelope, active_documents)`는 현재 읽기가 허용된 `ActiveDocuments`를 받아 필터링한 node-link 데이터를 메모리에서 반환한다. Graphify의 Python 내보내기 함수를 사용할 때는 반환값을 NetworkX graph로 변환해 전달하고, 허용된 산출 경로와 출력을 실제로 확인한다. 원문 접근·시각화 권한이나 외부 공개 권한이 함수 호출로 생기지는 않는다. `parse_envelope`로 v2 형식을 검사할 수 있으며 문서 coverage는 해당 envelope의 `content_graph`에 대해 계산한다.

다음은 `envelope`, 허용된 현재 `active_documents`, 사용자가 허용한 `output_path`를 호스트가 이미 준비한 경우의 내부 예시다. graph와 원문을 읽거나 output 경로를 쓰는 권한을 부여하는 예시는 아니다.

```python
import networkx as nx
from graphify.export import to_html
from relationship_ops import project_graph

visible = project_graph(envelope, active_documents)
graph = nx.node_link_graph(visible, edges="links")
written = to_html(graph, {}, str(output_path))
# written과 생성된 결과를 확인한다. False는 결과가 작성됐다는 뜻이 아니다.
```

Graphify HTML의 브라우저 라이브러리와 네트워크 요구 사항은 사용 중인 Graphify 버전의 출력을 확인한다. 화면에 표시할 문서와 근거의 현재 권한도 다시 확인하고, 산출물을 자동으로 외부에 게시하지 않는다.

구형 바탕 helper는 v2 envelope를 인식하지 못하고 입력을 거부한다. 이는 해당 helper의 검사 범위에 관한 설명이며 다른 프로그램이나 임의의 파일 쓰기를 막는 OS 보안 경계가 아니다. 복구 시에는 현재 graph의 기대 hash와 복구 허용 범위를 확인하고 이후 변경을 보존하며 이전 snapshot을 자동 병합하지 않는다.

### 좁은 주장과 후보의 범위

선택 targets와 기존 영향 관계·단서에서 시작해 필요한 관련 구간을 조회한다. 도구는 허용 범위·후보·hash·span과 증분 영향 범위를 확인하고, 모델은 실제 주장과 근거·관계 종류·방향·조건을 판단한다. 양쪽의 실제 근거를 찾되 source 링크만 있는 `references`에 target 절이나 내용 의존을 만들어 넣지 않는다. 판단할 수 없는 근거는 없거나 미확인임을 구분한다.

일반 링크의 상대 경로, 확장자, anchor, percent 인코딩 및 Unicode 표기는 허용된 문서 부분집합에서 대조한다. 동명 대상이 모호하면 관계를 확정하지 않고 태그로 우회하지 않는다. `no_relation`의 범위는 실제 검토한 종류에 한정하며 범위 밖 미검토를 자동으로 `deferred`로 만들지 않는다. 실제 누락이나 모호함은 숨기지 않는다.

기존 문서 ID·관계 ID·원문 hash와 원형을 보존한다. `qualifier`는 주장에 적용되는 의미 조건이며 endpoint를 감추는 수단이 아니다. 실질적으로 새로운 좁은 주장은 기존 ID 규칙으로 별도 식별하고 기존 assertion을 덮어쓰지 않는다. `shares_topic`은 기존 대칭 관계다. 공통 주제 관계는 실제 근거를 바탕으로 판단하고 동명 다의를 구분하며 관계의 추이성이나 자동 태그 생성을 가정하지 않는다.
