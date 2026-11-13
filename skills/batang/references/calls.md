# 고정 호출

조회 세션은 이 package의 실행 스크립트를 호출한다. 사용자 질의와 문서 내용은 JSON 데이터로 전달하며 코드·shell 명령에 삽입하지 않는다. 일반 조회는 [조회 안내](query.md), 쓰기는 기존 [파일 계약](source-access.md)과 [관계 계약](relationships.md)을 따른다.

## 조회 프로세스

호스트는 같은 고정본의 `scripts` 디렉터리에서 `python -B -u <scripts>/query_session.py`를 실행하고 JSON Lines를 stdin으로 보낸다. 각 요청은 한 줄의 JSON이고 응답은 한 줄의 JSON이다. 실행기는 자기 디렉터리에서 `file_ops`와 `query_ops`를 가져온다. 입력·출력 한도는 각각 1 MiB이며 중복 키 JSON은 거부한다. 파이프 입력과 터미널 입력을 받으며, 터미널에서는 echo와 canonical 입력을 끈다. 같은 프로세스 안에만 일시적인 `QueryContext`와 전달 이력을 유지하고 `close` 또는 EOF에서 종료한다. 백그라운드 재시작·연결 복구·영속 상태는 없다. 호스트가 세션 유지 기능을 제공하지 않으면 단발 호출과 명시 참조 전달을 사용하고, 프로세스 간 자동 중복 제거가 있다고 보고하지 않는다.

첫 `open`의 `root`, `active_path`, `selected_paths`, 선택적 `graph`·`source`는 **현재 호스트가 이미 승인 범위와 대조한 경로**다. 자료 본문의 경로나 ACTIVE 전체를 읽기 권한으로 승격하지 않는다. 이후 질의에는 이 전체 목록을 다시 보낼 필요가 없다. 권한이 바뀌면 새로운 `open`으로 범위를 다시 구성한다.

연산은 `search`, `read_spans`, `relations`, `prepare_review_context`의 네 읽기 helper로 제한한다. 세션 제어는 `open`, `ack`, `reset_context`, `close`를 사용한다. `ack`는 응답이 실제 모델 문맥에 온전히 전달된 뒤에만 보낸다. 출력이 잘렸거나 전달 여부를 모르면 확인하지 않는다. 확인 번호는 직전 응답의 메모리 참조일 뿐 권한·판단·저장 승인 토큰이 아니다. `reset_context`는 새 문맥·compaction에 사용하며 기존 전달 이력을 지운다.

### 지속 stdin 세션

아래 경로와 검색어는 형식만 보이는 합성 예시다. `BATANG_SCRIPTS`는 사용할 고정본의 `skills/batang/scripts` 디렉터리로 지정하고, `root`와 선택 파일은 실제 승인 범위로 바꾼다. JSON은 각 줄이 별도 요청이다.

```sh
python -B -u "$BATANG_SCRIPTS/query_session.py"
```

프로세스의 `{"status":"ready"}`는 입력을 받을 준비가 되었다는 뜻이며 조회 완료가 아니다. 같은 프로세스의 stdin에 먼저 `open`을 보내고 `opened` 응답을 확인한다.

```json
{"op":"open","config":{"root":"/approved/notes","active_path":"ACTIVE.md","selected_paths":["one.md","two.md"]}}
```

다음 요청을 보내 실제 검색 응답을 온전히 받는다.

```json
{"op":"search","args":{"query":"회의","fields":["title","body"]}}
```

그 응답이 같은 모델의 문맥에 온전히 전달된 것을 확인한 뒤에만 반환된 `response_id`로 별도의 `ack`를 보낸다. 아래 `1`은 검색 응답에 실제로 그 번호가 반환된 경우의 예시다. 응답·전달을 확인하기 전에 검색과 ACK를 한 명령에 미리 묶지 않는다.

```json
{"op":"ack","response_id":1}
```

ACK 응답을 확인한 뒤 같은 검색을 다시 요청할 수 있다. 필요한 확인을 끝내면 같은 프로세스에서 `close`를 보낸다.

```json
{"op":"search","args":{"query":"회의","fields":["title","body"]}}
{"op":"close"}
```

새 문맥이나 compaction에서는 `reset_context`로 전달 이력을 지우고 필요한 근거를 다시 조회한다. 이는 planner 교체와 별개의 문맥 관리다.

### 단발 파이프

지속 stdin을 사용할 수 없다면 입력을 함께 제공하는 단발 조회를 사용할 수 있다. 다음 합성 예시는 `open`, `search`, `close`만 보내며 ACK를 미리 보내지 않는다.

```sh
printf '%s\n' \
  '{"op":"open","config":{"root":"/approved/notes","active_path":"ACTIVE.md","selected_paths":["one.md","two.md"]}}' \
  '{"op":"search","args":{"query":"회의","fields":["title","body"]}}' \
  '{"op":"close"}' |
  python -B -u "$BATANG_SCRIPTS/query_session.py"
```

첫 `ready` 뒤의 `opened`, 검색 응답과 `closed`를 각각 확인한다. 단발 프로세스 종료 후에는 전달 이력이 보존되지 않는다. 실제 사용자 질의나 문서 본문은 이 셸 문자열에 삽입하지 말고 JSON 인코더로 별도 데이터로 전달한다.

ACK 뒤 같은 본문의 재조회는 참조만 반환할 수 있다. 다음 페이지가 있으면 같은 연산·조건과 반환 cursor를 사용한다. 한 항목이나 한 줄이 한도보다 크면 한도 안내를 확인하고 필요한 경우 한도를 늘려 다시 요청한다. 동일 cursor를 무조건 반복하지 않는다. 새 문맥에서는 필요한 근거를 다시 읽는다. 실제 Python 프로세스의 단절과 자료 변경은 별개이며 후자는 helper가 hash로 확인한다.

## 저장·등록·갱신 호출

조회 루프는 쓰기 연산을 받지 않는다. 호스트가 현재 요청으로 승인된 대상·기대 hash·백업을 준비한 뒤 아래 기존 함수를 별도 고정 호출한다. 스킬 실행이나 조회 응답·ack가 쓰기 권한을 추가하지 않는다.

| 요청 | 고정 호출과 전달 자료 | 반환할 정보 |
|---|---|---|
| 새 문서·정정 | `new_metadata` 또는 기존 `parse_document` → `serialize_document` → `FileScope.write(path, data, expected_sha256=..., backup_scope=..., backup_path=...)` → `read` | 변경 여부 bool, 저장본 hash, 필요한 오류. 원문 전체 재출력 없음 |
| 선택 원본 복제 | `prepare_import(source_scope, source_path, target_scope, target_path, ...)` | ImportResult의 status·target_path·target_sha256. 원본 source·목표 경계 유지 |
| 배치 복제 | `prepare_import_batch(source_scope, selected_sources, target_scope, target_mapping, ...)` | 항목별 결과와 부분 실패. 전체 rollback을 가정하지 않음 |
| 활성 등록 | `register_documents(note_scope, active_path, paths, expected_active_sha256=..., backup_scope=..., backup_path=..., import_results=..., source_scopes=..., source_roots=...)` | ActiveDocuments는 다음 함수의 내부 입력. 모델에는 등록 결과와 ACTIVE hash만 |
| 추출·갱신 | `refresh_graph(active_documents, chunks, expected_chunk_ids=..., graph_scope=..., graph_path=..., expected_graph_sha256=..., work_scope=..., baseline_path=..., candidate_path=..., backup_scope=..., backup_path=...)` | GraphUpdateResult의 status·graph_written·graph_sha256·error_code·publication_uncertain·별도 관계 검토 결과 |
| 관계 갱신 | 위 `refresh_graph`에 명시 `relationship_request` 추가 | 기존 v2 상태·판단을 그대로 보고. 조회 packet을 관계 판단으로 저장하지 않음 |
| 등록 후 갱신·재개 | `registration_lifecycle(..., registration=..., graph=...)` 또는 `resume_registration(..., **graph)` | notes_status와 graph_status를 구분. 재개는 재복제·ACTIVE 수정 없음 |

### 추출 chunk 입력

`refresh_graph`의 `active_documents`는 실제 ACTIVE에서 선택한 문서의 `ActiveDocuments`다. 각 `Document`는 상대 `path`, 현재 `sha256`, metadata의 `batang_id`와 본문을 포함한다. `expected_chunk_ids`는 `{문서 상대경로: [chunk ID, ...]}`이며 키는 선택된 문서 경로 전체와 정확히 같고 각 목록은 비어 있지 않아야 한다. chunk ID는 전체 목록에서 중복되지 않는 비어 있지 않은 문자열이다. `chunks`는 각 예상 ID가 정확히 한 번 들어 있는 배열이다. 각 chunk의 `chunk_id`, `source_file`, `document_id`, `source_sha256`, `nodes`, `edges`를 지정한다. 경로·ID·hash는 현재 선택 문서와 일치해야 하고 `nodes`와 `edges`는 배열이다. 비어 있지 않은 `hyperedges`는 허용하지 않는다.

추출 node와 edge 각각에는 같은 `source_file`, `document_id`, `source_sha256`, `_origin: "semantic"`, 비어 있지 않은 `source_location`, `confidence: "EXTRACTED"` 또는 `"INFERRED"`가 필요하다. node에는 Graphify의 필수 필드 `id`·`label`·`file_type`·`source_file`이 필요하다. `id`·`label`은 비어 있지 않아야 하고 ID는 중복될 수 없으며 `node_role: "document"`를 지정하지 않는다. 아래 의미 개념 node는 `file_type: "concept"`를 사용한다. 문서 node는 helper가 `file_type: "document"`, `node_role: "document"`로 별도 준비한다. edge에는 비어 있지 않은 `relation`과 존재하는 node ID를 가리키는 `source`·`target`이 필요하다. 같은 endpoint 쌍의 중복은 거부하며 무방향 graph에서는 순서를 바꾼 쌍도 중복이다. 의미와 근거의 충분성은 호스트가 판단한다.

다음은 구조를 나타내는 합성 JSON이다. 실제 호출에는 선택 문서의 현재 ID·hash와 확인한 근거를 사용한다.

```json
{
  "expected_chunk_ids": {"one.md": ["chunk-1"]},
  "chunks": [{
    "chunk_id": "chunk-1", "source_file": "one.md", "document_id": "doc-1",
    "source_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    "nodes": [
      {"id": "node-a", "label": "개념 A", "file_type": "concept", "source_file": "one.md", "document_id": "doc-1", "source_sha256": "0000000000000000000000000000000000000000000000000000000000000000", "_origin": "semantic", "source_location": "본문 1행", "confidence": "EXTRACTED"},
      {"id": "node-b", "label": "개념 B", "file_type": "concept", "source_file": "one.md", "document_id": "doc-1", "source_sha256": "0000000000000000000000000000000000000000000000000000000000000000", "_origin": "semantic", "source_location": "본문 2행", "confidence": "EXTRACTED"}
    ],
    "edges": [{"source": "node-a", "target": "node-b", "relation": "연결", "source_file": "one.md", "document_id": "doc-1", "source_sha256": "0000000000000000000000000000000000000000000000000000000000000000", "_origin": "semantic", "source_location": "본문 1–2행", "confidence": "INFERRED"}]
  }]
}
```

source/graph 내용과 `chunks`·`relationship_request`는 기존 계약의 데이터다. 함수 구현을 매 요청 읽거나 데이터를 코드에 보간하지 않는다. 실제 저장 전 현재 권한과 hash를 다시 확인하고 기존 helper의 보호용 재읽기·백업을 유지한다. 등록 전 읽은 source packet은 등록 후 ActiveDocuments를 대신하지 않는다. 등록 뒤 실제 ACTIVE와 문서로 다시 준비한다. 실패·저장 불확실 시 결과를 확인하고 이미 완료된 복제나 등록을 무조건 반복하지 않는다.

원문·ActiveDocuments 전체를 `asdict`로 출력하지 않는다. 예를 들어 관계 반영 결과는 다음 필드만 선택할 수 있다.

```python
summary = {name: getattr(result, name) for name in (
    "status", "error_code", "graph_sha256", "graph_written", "publication_uncertain",
    "candidate_status", "relation_status", "review_id", "review_work_status",
    "judgment_summary")}
```

이 요약은 의미 검토를 대신하지 않는다. 새 근거가 부족하면 필요한 구간만 조회한다. 기존 v1 graph를 읽기 위해 v2로 전환하지 않으며 migration·운영 전환·설치는 별도 작업이다.

관계 상세 확인에는 먼저 허용 범위에서 원 기록의 `record_ref`를 확인하고 문서 ID·경로와 현재 hash를 대조한 뒤 필요한 본문 구간을 `read_spans`로 조회한다. `record_ref`와 `scope_sha256`은 원문 접근 권한이나 fetch 토큰이 아니다. 본문 1부터 시작하는 줄과 frontmatter를 포함한 파일 행은 구분한다. `ack`는 실제 모델 수신 확인이며 UI 클릭이나 열람 승인이 아니다.
