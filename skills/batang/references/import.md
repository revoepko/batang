# 선택한 기존 자료 가져오기

설치 또는 첫 사용 때 기존 자료를 가져올지 확인하고 선택한 볼트·폴더·문서와 바탕 목적지 구조를 정한다. 가져올 자료가 없거나 가져오지 않으면 합의한 빈 구조만 만든다. 이미 답한 질문은 반복하지 않는다. 선택 범위 밖을 검색·읽기·복사하지 않는다.

원본은 읽기 전용이다. 수정·이동·삭제를 제안하거나 실행하지 않고 원본 metadata와 Obsidian 설정을 보존한다. 원본 경로와 읽은 전체 bytes의 hash를 기록하고 독립 bytes로 복제한다. 링크로 대체하지 않는다. 목적지가 원본과 같거나 원본 하위에 겹치거나 링크 별칭으로 동일하면 중단한다. 기존 파일을 덮어쓰지 않으며 이름 충돌은 별도 목적지 이름을 확인한다. 복제 중 원본 변경이나 무결성 불일치가 있으면 등록하지 않는다.

복제본만 변환하고 본문·기존 속성, ID 충돌과 출처를 확인한 다음 활성 목록에 등록한다. 최초 복제 자체에 원본 백업은 필요하지 않으며 기존 바탕 문서와 활성 목록 변경은 [안전 수정 계약](source-access.md)을 따른다. 문서별 성공·실패·미등록을 구분하며 실패 복제본을 임의로 삭제하거나 전체 성공·자동 rollback을 주장하지 않는다.

재가져오기 생략은 동일 원본 식별 정보와 관측 hash, 그 출처에 연결된 기존 등록 문서의 존재와 유효성이 모두 확인된 경우에만 허용한다. 경로나 같은 bytes만으로 다른 출처를 합치지 않는다. 변경된 원본은 별도 새 복제 대상으로 선택하며 자동 동기화하거나 사용자 문서를 덮어쓰지 않는다.

상대 링크와 첨부 참조는 선택 범위 안에서 대조한다. 반환된 참조 상태 `selected`는 원본 선택 범위 내에서 존재를 확인했다는 뜻이며 복제 후 목적지 링크의 유효성을 뜻하지 않는다. 폴더나 파일명이 바뀌면 호스트가 허용된 목적지 경로에서 본문의 상대 링크와 첨부 참조를 다시 대조한다. 합의하지 않은 첨부·외부 자료를 자동 수집하거나 본문을 자동 수정하지 않으며 링크 검사를 이유로 선택 밖 자료를 읽지 않는다. 목적지에서 깨졌거나 확인하지 못한 참조를 명시하고 완전 이관으로 보고하지 않는다.

## 가져오기 입력과 관리 문서

이 문서의 v1·v2는 제품 버전이 아닌 `batang_schema_version` 메타데이터 형식 버전이다.

관리 문서의 정규 형식은 [지식 계약](knowledge-contract.md)이다. `batang_schema_version` 또는 `batang_id`가 있는 문서는 기존 관리 문서로 판단하며 필수 일곱 key가 모두 유효해야 한다. 누락된 필수 key를 일반 YAML이나 무메타데이터 이관의 기본값으로 보충하지 않고 보류한다. `tags`, `aliases`, `subject`만 있는 일반 YAML은 신규 v2 변환 대상이다. 가져오기 입력에 한해 평면의 허용된 key와 문자열 scalar, `tags`·`aliases`의 문자열 목록(JSON 배열 또는 엄격한 block 목록)을 변환한다. 범용 YAML 지원이 아니다. 미지원 key, 중복 key, anchor, 중첩, multiline 또는 모호한 값은 보류하고 등록하지 않는다. 확인하지 못한 출처를 추측하거나 미지원 속성을 버리지 않는다.

## 호스트와 도우미

`prepare_import(source_scope, source_path, target_scope, target_path, *, subject=None, content_kind="note", registered_documents=(), prior_imports=(), selected_sources=())`는 `ImportResult(status, target_root, target_path, target_sha256, metadata, provenance, references, source_identity)`를 반환한다. status는 `prepared` 또는 `skipped`다. `registered_documents`는 명시된 `(FileScope, 상대경로)` 목록이다. 등록 직전 `verify_import_source(source_scope, result)`로 원본을 다시 확인한다. 일치하면 `True`를 반환하고 불일치하면 중단한다. 이어 `target_scope.read`로 복제본을 다시 읽어 `target_sha256`, metadata의 ID와 예상 본문을 대조한다. 원본 재확인만으로 복제본의 안전을 보장하지 않는다. 이후 기존 ACTIVE의 기대 hash와 백업을 적용해 `FileScope.write`로 등록하고, ACTIVE와 복제본을 다시 열어 확인한다. 도우미 결과는 활성 목록 등록 권한이 아니며 목록 등록과 재확인은 호스트 책임이다.

정규 v1·v2 문서의 복제는 기존 ID·schema·sources를 보존한다. v1의 `raw_path`를 허위로 채우거나 v2로 자동 승격하지 않는다. 가져오기 출처는 `ImportResult`와 호스트 등록 기록에 연결한다. 비정규 자료를 신규 v2로 변환할 때만 실제 source 경로·전체 bytes hash와 `raw_path: null`을 사용한다.
