# 조회와 검토 입력 준비

호스트는 [고정 호출](calls.md)로 `query_ops`의 읽기 전용 함수를 선택한다. 네 함수는 필수 순서가 아니다. 호스트가 현재 승인된 경로로 `FileScope`와 `QueryContext(note_scope, active_path, selected_paths, *, graph_scope=None, graph_path=None, context_id=None)`를 구성한다. 일반 조회 대상은 명시 선택·읽기 허용·활성 목록의 교집합이다. graph 범위와 경로는 함께 지정한다. ID, 참조, cursor와 문맥 ID는 권한이 아니다. 문맥 ID는 정보용이며 전달·참조의 유효성을 증명하지 않는다.

- `search(context, query, fields=..., limits=..., cursor=...)`는 제목·ID·태그·별칭·본문의 대소문자를 구분하지 않는 부분 문자열을 찾는다. 일치는 의미 관계나 완전한 후보의 증거가 아니다.
- `read_spans(context, requests, limits=..., cursor=...)`는 선택된 문서의 참조 구간을 확인한다. 각 참조에는 `path`, `document_id`, `source_sha256`, 본문 1부터 시작하는 양끝 포함 `start_line`·`end_line`, `span_sha256`이 필요하다. 관리 문서 참조는 본문의 완전한 줄 단위다. 긴 줄이 한도를 넘으면 `limit`과 `required_excerpt_bytes`를 확인하고 필요한 한도를 늘려 재요청한다. 임의 byte 분할은 하지 않는다. 최초 호출에서 선택 문서의 참조 원문 hash가 다르면 해당 문서를 `snapshot_changed` 누락으로 격리하고 부분 결과를 반환한다. cursor fingerprint 불일치나 실패 목록 확정 후 변화, 전역 불변성 실패는 전체 `stale` 또는 오류가 우선한다. 과거 참조를 자동 수정하지 않는다.
- `relations(context, operation=..., selector=..., limits=..., cursor=...)`는 허용 범위의 v1/v2 원 기록을 읽는다. `records`, `neighbors`, `traverse`, `shortest_path`는 기록의 방향과 지원 범위를 따른다. 원 기록은 `project_graph`의 현재 확정 관계 표시 투영과 다르다. 원문과 관계의 정합성, 내용의 타당성, 사용자에게 보일 수 있는 범위는 별도로 판단한다.
- `prepare_review_context(context, stage=..., target_paths=..., comparison_paths=..., source_scope=..., source_paths=..., mode=..., limits=..., cursor=...)`는 관계 검토에 필요한 내용을 준비한다. `pre_registration`은 명시 허용된 `source_scope`와 `source_paths`의 내용만 읽으며 등록이나 후보 탐색을 하지 않는다. 승인된 저장·등록 뒤 `post_registration`에서 실제 활성 목록과 문서를 다시 구성하고 명시 대상과 비교 범위로 기존 후보 탐색을 수행한다. 등록 전 source의 `spans[].ref`는 source 범위·hash·byte 구간의 별도 참조이며 관리 문서의 `read_spans`에 넣지 않는다. 등록 전 hash를 등록 후 근거로 자동 승계하지 않는다. 반환된 불투명 `review_ref`는 조회 참조이며 기존 저장 형식의 `review_id`를 바꾸지 않는다.

`relations`의 `selector`는 `source`, `target`, `relation_ids`만 받는다. 앞의 두 값은 문자열이며 v2에서는 문서 ID, v1에서는 graph node ID다. `records`는 지정한 `source`와 `target`이 각각 기록의 **어느 쪽 endpoint든** 포함되는 기록만 반환한다. 둘을 함께 지정하면 두 조건을 모두 만족해야 하지만 저장 방향을 지정하는 필터는 아니다. `relation_ids`는 문자열 배열이며 `records`에만 적용된다. v1 기록에는 `relation_id`가 없으므로 이 필터로 일치하지 않는다.

`neighbors`와 `traverse`는 `source`가 필수이고, `shortest_path`는 `source`와 `target`이 모두 필수다. 이 탐색에서 `relation_ids`는 적용되지 않으며 `neighbors`와 `traverse`의 `target`은 필터가 아니다. 방향 관계는 저장된 source에서 target 방향으로, 대칭 관계는 양방향으로 탐색한다. v1은 graph의 방향 설정을 따른다. `neighbors`는 한 단계, `traverse`와 단일 비가중 `shortest_path`는 `max_depth`까지 허용된 부분 graph에서 탐색한다. 반환은 원 기록이며 역방향으로 탐색한 대칭 기록의 저장 방향을 바꾸지 않는다.

고정 호출에서 이미 허용 범위를 `open`한 뒤 보내는 최소 예시다. ID는 실제 graph의 ID로 바꾼다.

```json
{"op":"relations","args":{"operation":"records","selector":{"source":"문서-A","target":"문서-B","relation_ids":["관계-ID"]}}}
{"op":"relations","args":{"operation":"neighbors","selector":{"source":"문서-A"}}}
{"op":"relations","args":{"operation":"traverse","selector":{"source":"문서-A"}},"limits":{"max_depth":2}}
{"op":"relations","args":{"operation":"shortest_path","selector":{"source":"문서-A","target":"문서-B"}},"limits":{"max_depth":4}}
```

예를 들어 고정 호출에서 검색 조건 `{"query":"회의", "fields":["title","body"]}`을 전달해 받은 `items`의 실제 `ref`를 구간 요청에 사용할 수 있다. 검토 준비는 `stage="post_registration"`, `target_paths`와 `comparison_paths`를 명시하고 `mode="full"` 또는 `"incremental"`을 선택한다. 전체 검토에 필요한 원문은 페이지로 모두 살피며, 증분의 후보와 영향 관계만으로 의미적 완전성을 가정하지 않는다. 모델이 추가 근거, 새 의미 관계, 충분성과 답변을 판단한다.

기본 `QueryLimits`는 `max_items=20`, `max_bytes=16384`, `max_excerpt_bytes=2048`, `max_depth=4`다. 반환 packet의 `status`, `items`, `next_cursor`, `truncated`, `omissions`, `currentness`를 확인한다. `absent`는 선택 범위의 결과 부재이고 `error`는 접근·입력 등 오류, `stale`은 snapshot 불일치다. `partial` 또는 `limit`은 누락 가능성이 있으므로 완료나 관계 없음으로 간주하지 않는다. `exploration.depth_limited=true`나 절단·누락이 있으면 경로 부재로 해석하지 않는다. graph가 없어도 허용된 원문 검색은 별도로 가능하다. endpoint나 support의 stale을 포함한 `currentness`는 snapshot 대응이며 내용이 거짓이거나 자동으로 숨겨진다는 뜻이 아니다. 검토 완료와도 구분한다.

실패 문서가 있으면 선택·활성·허용 경계가 확인된 상대 `path`와 안정된 `reason`이 `omissions`에 표시된다. 같은 실패 목록은 각 부분 페이지의 `omissions`에서 `document_failure`와 함께 반복되며 정상 문서의 결과와 구분한다. 문자열과 `{path, reason}` 객체가 함께 올 수 있다. 잘못된 형식·범위, ACTIVE·graph 등 전역 경계 오류는 전체 오류 또는 stale로 처리한다. `read_spans`의 한 문서에 오류 참조가 있으면 그 문서의 모든 구간은 제외한다. `pre_registration`의 별도 source 범위는 같은 부분 반환 규칙으로 확대하지 않는다. 등록 후 검토 입력에서 실패가 있으면 후보 탐색은 `not_run`으로 남는다.

`partial`은 마지막 페이지거나 정상 항목이 없어도 완료나 부재가 아니다. 실패 목록과 필수 metadata가 예산을 넘으면 `limit`과 `query_metadata_exceeds_limit`이며 정상 항목도 반환되지 않는다. 모델은 선택 범위나 응답 예산을 조정해 다시 조회할 수 있다. 세션 응답 상한은 1 MiB다.

다음 페이지는 동일 조건의 `next_cursor`로 요청한다. cursor의 offset은 정상 결과 위치이며 범위·목록·원문·graph·실패 관측이 달라지거나 fingerprint가 일치하지 않으면 stale이다. 이전 버전의 cursor 수용은 보장하지 않는다. 긴 줄의 `limit`에서 `max_excerpt_bytes`만 늘리는 재요청은 기존 cursor를 사용할 수 있다. 새 문맥이나 compaction 후 필요한 근거는 다시 조회한다. 전달 이력은 유지하지 않으며 권한이 바뀌면 범위를 재구성한다.

함수는 모델을 호출하거나 저장하지 않는다. 기존 저장·등록·갱신·재개는 [고정 호출](calls.md)에서 기존 함수와 권한·기대 hash·백업 조건을 사용한다. packet과 cursor는 임시 응답이며 기존 데이터 형식이나 과거 기록을 바꾸지 않는다.

## 관계 근거와 표시 범위

일반 관계·근거 검토는 `relations`의 원 기록과 `read_spans`의 원문으로 수행한다. `graph.html` 생성이나 브라우저 관측을 선행 조건으로 삼지 않는다. 기존 HTML 파일의 화면 검토를 요청받으면 지정된 파일의 데이터 출처와 snapshot을 확인하고 그 파일을 검토하며 자동으로 재생성하지 않는다.

`record_ref`는 원 기록의 조회 참조이며 `scope_sha256`을 포함한다. 별도 `scope_ref` 필드나 원문 접근을 허가하는 ACL 토큰이 아니다. 현재 허용된 문서 ID와 경로를 대응하고 `read_spans`에 문서 ID·원문 hash·본문 줄 범위·span hash를 사용한다. evidence의 본문 1부터 시작하는 줄과 frontmatter를 포함한 파일 행은 구분한다. 근거나 좌표·접근을 확인할 수 없으면 상세 검증 불가로 표시한다.

하나의 support set에 필요한 근거는 함께 살피고 대안 set은 구분한다. projection은 유효한 대안 하나로 관계를 표시할 수 있지만 raw 조회는 모든 support의 범위와 currentness를 검사하므로 raw 기록이 반환되지 않거나 전체가 stale일 수 있다. raw 미반환은 관계 부재나 모든 근거의 무효를 뜻하지 않는다. 허용 범위 밖 정보는 추측해 노출하지 않는다.
