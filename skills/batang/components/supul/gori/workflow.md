# 고리: 관계 자료

호스트는 Graphify 결과를 재생성 가능한 관계 단서로 사용하며 `EXTRACTED`와 `INFERRED`를 구분하고 현재 원문을 확인한다. 준비된 실행 실패는 Markdown 답변과 분리한다. 승인 없는 갱신은 하지 않는다.

aliases가 붙은 노드는 원문 ID·hash·tags를 보존하고 같은 별칭만으로 서로 다른 문서를 병합하지 않는다. 별칭 검색은 허용된 활성 문서의 별칭과 대조해 후보를 고르고 해당 `batang_id`와 실제 graph node ID의 대응을 확인한 뒤 해당 노드를 seed로 관계를 탐색한다. 두 ID는 다를 수 있다. upstream의 자동 별칭 추출은 보장하지 않으며 실제 검색·연결 효과는 실행 결과로 확인한다.

Graphify의 최초 생성과 갱신은 허용된 활성 원문과 기존 라이브러리로 수행한다. 그래프가 없으면 첫 생성의 범위와 권한을 확인하고, 문서 ID·hash에 대응하는 노드를 포함한다. 관계가 없는 노드에 근거 없는 연결을 만들지 않는다. 새 batch 서비스·provider나 기존 도구 source 복사·수정은 하지 않는다.

1. 원본 변경 성공과 관련 갱신 승인 여부를 확인한다. `active_index` 중 허용 파일만 명시 목록으로 전달한다. 과거 자료·볼트 전체 detection으로 확대하지 않는다. 원문 ID와 읽은 현재 hash를 연결한다.
2. 현재 호스트 또는 기존 subagent 규약으로 허용 자료만 추출한다. `source_file`·`source_location`, 원문 ID/hash, `_origin: semantic`, `EXTRACTED`·`INFERRED`를 추적한다. 새 모델 호출기나 provider를 만들지 않으며 키가 존재해도 Gemini로 자동 전환하지 않는다.
3. 모든 예상 chunk의 반환·JSON 배열·source 범위·hash·참조 endpoint를 확인한다. 누락·오류·stale·부분 추출은 중단한다. 공통 도구의 chunk skip 지침보다 불완전 결과 미교체 계약을 우선한다.
4. 내부 `scripts/graph_ops.py`의 `refresh_graph`에 허용된 활성 원문과 검증할 chunk·예상 ID를 전달한다. 검증한 기존 그래프 snapshot과 선택 자료를 메모리에서 합쳐 기존 Graphify `build`를 `dedup=False`로 사용한다. 선택한 source의 semantic 추출분은 새 결과로 교체하되 같은 source의 AST 층과 대상 밖 node·edge·hyperedge를 보존한다. 입력에 없다는 이유로 미허용 자료를 삭제하거나 upstream의 고립 노드 정리를 자동 실행하지 않는다. 승인된 작업 위치에서 기준 그래프와 후보를 안전하게 만들고 serialize·reload해 node ID와 원문 ID, 원문 hash·aliases·tags 및 변경 대상 밖 자료를 대조한 뒤 기대 hash와 백업 조건을 적용해 게시한다. 원본 Markdown 복제·새 DB·새 설치는 하지 않는다.
5. 게시 전 실패는 기존 그래프와 저장된 노트를 유지하고 관계 반영 대기를 알리며 현재 Markdown으로 답한다. 게시 후 재확인 실패는 `publication_uncertain=True`, `graph_written=None`으로 구분한다. 현재 그래프와 백업을 대조해 결과를 판단하며 무조건 교체 전 상태라고 주장하거나 자동 복구하지 않는다. 다음 관련 요청에서 동일한 승인 범위와 현재 요청을 확인하고 원문 ID·hash를 다시 대조해 대기 항목을 재개한다. 읽기 전용 요청이면 쓰지 않는다. 원본 저장 성공·Markdown 답변과 Graphify 준비·갱신 결과를 각각 기록한다. 조회의 `save-result`·`reflect`·어휘 파일 생성·재생성은 제외한다. watch·자동 재시도는 없다. 미허용 파일의 부재를 삭제 근거로 삼거나 `prune_sources`로 넘기지 않는다.

내부 함수는 `read_active_documents(note_scope, active_path, selected_paths=None)`로 선택된 활성 노트와 목록의 현재 hash를 읽고, `graph_coverage(documents, graph_bytes)`로 노트별 `current`·`missing`·`stale`·`invalid`를 대조한다. 목록 자체는 읽기 권한이 아니다. `document_nodes`는 관계가 없는 노트도 식별할 수 있는 문서 노드를 준비한다. 호스트는 허용된 자료에서 의미 chunk를 만들고 예상 chunk ID와 원문 ID·hash·출처·endpoint를 검증해 `refresh_graph`에 전달한다. Graphify가 자동으로 별칭을 추출하거나 의미를 검증한다고 가정하지 않는다.

`refresh_graph(active_documents, chunks, *, expected_chunk_ids, graph_scope, graph_path, expected_graph_sha256, work_scope, baseline_path, candidate_path, backup_scope=None, backup_path=None, read_only=False)`의 `work_scope`는 이미 허용된 임시 대상이다. 기존 결과에는 기대 hash·백업을 적용한다. `read_only=True`는 갱신하지 않으며 권한 인증을 대신하지 않는다. 등록에는 `register_documents`와 `registration_lifecycle`, 다음 관련 요청의 재개에는 복제하지 않는 `resume_registration`을 사용한다. 각각의 실제 결과를 확인하며 source binding과 원본 재확인도 등록 전에 수행한다.
