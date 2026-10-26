# 고리: 관계 자료

호스트는 Graphify 결과를 재생성 가능한 관계 단서로 사용하며 `EXTRACTED`와 `INFERRED`를 구분하고 현재 원문을 확인한다. 준비된 실행 실패는 Markdown 답변과 분리한다. 승인 없는 갱신은 하지 않는다.

Graphify의 실제 갱신은 다음처럼 기존 라이브러리와 호스트 절차를 사용한다. 새 배치 실행기를 만들거나 기존 도구 source를 복사·수정하지 않는다.

1. 원본 변경 성공과 관련 갱신 승인 여부를 확인한다. `active_index` 중 허용 파일만 명시 목록으로 전달한다. 과거 자료·볼트 전체 detection으로 확대하지 않는다. 원문 ID와 읽은 현재 hash를 연결한다.
2. 현재 호스트 또는 기존 subagent 규약으로 허용 자료만 추출한다. `source_file`·`source_location`, 원문 ID/hash, `_origin: semantic`, `EXTRACTED`·`INFERRED`를 추적한다. 새 모델 호출기나 provider를 만들지 않으며 키가 존재해도 Gemini로 자동 전환하지 않는다.
3. 모든 예상 chunk의 반환·JSON 배열·source 범위·hash·참조 endpoint를 확인한다. 누락·오류·stale·부분 추출은 중단한다. 공통 도구의 chunk skip 지침보다 불완전 결과 미교체 계약을 우선한다.
4. 유효 chunk만 기존 `graphify.build.build_merge(new_chunks, graph_path=..., root=...)`에 전달한다. 이 함수는 기존 그래프를 읽어 새 그래프를 반환하며 직접 쓰지 않는다. `graph_output`의 승인된 후보 위치에서 새 결과를 검증하고 기존 결과의 기대 hash도 대조한 뒤 교체한다. 원본 Markdown 복제·새 DB·새 설치는 하지 않는다.
5. 실행 실패는 기존 그래프를 유지하고 stale로 보고하며 현재 Markdown으로 답한다. 원본 저장 성공·Markdown 답변과 Graphify 준비·갱신 결과를 각각 기록한다. 조회의 `save-result`·`reflect`·어휘 파일 생성·재생성은 제외한다. watch·자동 재시도는 없다. 미허용 파일의 부재를 삭제 근거로 삼거나 `prune_sources`로 넘기지 않는다.
