# 선택한 기존 자료 가져오기

설치 또는 첫 사용 때 기존 자료를 가져올지 확인하고 선택한 볼트·폴더·문서와 바탕 목적지 구조를 정한다. 가져올 자료가 없거나 가져오지 않으면 합의한 빈 구조만 만든다. 이미 답한 질문은 반복하지 않는다. 선택 범위 밖을 검색·읽기·복사하지 않는다.

원본은 읽기 전용이다. 수정·이동·삭제를 제안하거나 실행하지 않고 원본 metadata와 Obsidian 설정을 보존한다. 원본의 식별 정보와 읽은 전체 bytes의 hash를 기록하고 독립 bytes로 복제한다. 링크로 대체하지 않는다. 같은 볼트나 원본 root의 하위라는 이유로 복제를 일괄 차단하지 않는다. 선택한 원본 파일과 목적지의 실제 경로·정체성·심볼릭 링크·하드 링크를 대조해 충돌을 차단한다. 기존 파일을 덮어쓰지 않으며 이름 충돌은 별도 목적지 이름을 확인한다. 복제 중 원본 변경이나 무결성 불일치가 있으면 등록하지 않는다.

복제본만 변환하고 본문·기존 속성, ID 충돌과 출처를 확인한 다음 활성 목록에 등록한다. 최초 복제 자체에 원본 백업은 필요하지 않으며 기존 바탕 문서와 활성 목록 변경은 [안전 수정 계약](source-access.md)을 따른다. 문서별 성공·실패·미등록을 구분하며 실패 복제본을 임의로 삭제하거나 전체 성공·자동 rollback을 주장하지 않는다.

재가져오기 생략은 동일 원본 식별 정보와 관측 hash, 그 출처에 연결된 기존 등록 문서의 존재와 유효성이 모두 확인된 경우에만 허용한다. 경로나 같은 bytes만으로 다른 출처를 합치지 않는다. 변경된 원본은 별도 새 복제 대상으로 선택하며 자동 동기화하거나 사용자 문서를 덮어쓰지 않는다.

선택한 원본과 목적지의 경로·문서 ID·hash를 대응시켜 노트마다 복제·변환·등록·관계 반영 결과 또는 보류 사유를 남긴다. 첨부는 복제·링크 상태를 별도로 기록하고 노트 등록으로 취급하지 않는다. 위키링크의 폴더 경로는 Obsidian vault 기준으로, Markdown 상대 링크는 해당 노트 기준으로 구분한다. 원본 쪽 참조 확인과 복제 후 목적지 링크 대조는 별도다. 합의하지 않은 첨부·외부 자료를 자동 수집하지 않으며 선택 밖 자료를 읽지 않는다.

지원하는 단순 위키링크·Markdown 링크·이미지 참조는 원본과 복제본의 대응이 확인된 경우에만 복제본에서 조정하고 다시 대조한다. 링크의 표시 이름과 노트 안의 제목·블록 참조를 보존하며 원본은 수정하지 않는다. 확실한 코드 블록·인라인 코드·HTML 주석과 내용을 그대로 보존해야 하는 HTML 블록의 예시는 링크 대상에서 제외한다.

중첩된 표시 이름, 링크 안의 이미지, 복잡한 주소·제목·꺾쇠 주소, 참조형 링크와 목록·인용에 이어지는 모호한 부분은 미확인으로 남긴다. 인라인 HTML이나 해석이 불확실한 HTML도 마찬가지다. 지원하지 않는 바깥 구문 안의 일부만 따로 바꾸지 않고 해당 내용을 보존한다. 미확인·모호·깨진 참조가 남으면 참조 전체를 완료로 표시하지 않는다. 참조 목록이 비어 있어도 전체 CommonMark나 Obsidian 문법의 의미까지 완전히 확인했다고 주장하지 않는다.

## 가져오기 입력과 관리 문서

이 문서의 v1·v2는 제품 버전이 아닌 `batang_schema_version` 메타데이터 형식 버전이다.

관리 문서의 정규 형식은 [지식 계약](knowledge-contract.md)이다. `batang_schema_version` 또는 `batang_id`가 있는 문서는 기존 관리 문서로 판단하며 필수 일곱 key가 모두 유효해야 한다. 누락된 필수 key를 일반 YAML이나 무메타데이터 이관의 기본값으로 보충하지 않고 보류한다. `tags`, `aliases`, `subject`만 있는 일반 YAML은 신규 v2 변환 대상이다. 가져오기 입력은 Obsidian의 지원 속성 범위에 해당하는 평면 키와 문자열·유한 숫자·boolean·null·날짜 문자열, flow/block 목록을 보존한다. 관리 출처에 필요한 목록·객체도 읽는다. 범용 YAML 지원이 아니다. 중복 key·anchor·tag·merge key·복합 key와 지원하지 않는 중첩·복잡 구조는 보류하고 이유를 알린다. 확인하지 못한 출처를 추측하거나 미지원 속성을 버리지 않는다.

## 호스트와 도우미

`prepare_import(source_scope, source_path, target_scope, target_path, *, subject=None, content_kind="note", registered_documents=(), prior_imports=(), selected_sources=(), source_root_id=None, source_vault_root=None, target_mapping=None, target_vault_root=None)`는 `ImportResult`를 반환한다. 상태는 `prepared` 또는 `skipped`이며 대상 hash, metadata, 원본 식별 정보, 참조와 로컬 `source_root_binding`을 포함한다. 신규 source root ID를 지정하지 않으면 새 UUID를 만든다. 신규 URI를 기록한 경우 반환된 binding을 호스트가 로컬 설정에 기록·확인한다. 기존 관리 문서의 출처는 그대로 보존하며 새 binding이 없을 수 있다.

`inspect_import_links`는 허용된 선택 원본 표만 대조해 `selected`·`ambiguous`·`unverified`·`broken`·`same_document`를 구분한다. Obsidian vault 기준과 실제 읽기 범위는 `source_vault_root`와 `source_scope`로 구분한다. `target_mapping`은 확인된 선택 원본에서 허용된 목적지로의 대응이다. 복제본만 링크를 조정하고 `verify_import_destinations`로 실제 대상에 다시 연결되는지 확인한다. 그 결과의 `verified`와 `broken`, `broken_anchor`, `anchor_unverified`, `not_copied`, `unverified`는 서로 다르다. 제목과 블록 참조는 일반적인 ATX 제목 계층과 블록 ID를 코드·주석을 제외하고 대조한다. Setext 제목, 복잡한 인라인 서식이나 일반 HTML처럼 안전하게 확정할 수 없는 경우는 `anchor_unverified`로 남긴다. 범위 밖 파일은 읽지 않는다.

`prepare_import_batch`는 선택된 파일마다 결과 또는 오류를 반환하고 선택 수와 결과 수를 대조한다. `selected_count`·`prepared_count`·`selection_accounted`·`copies_complete`·`references_complete`와 참조 확인 오류를 구분한다. `prepared_count`는 마지막 대조에서 유효한 복제본의 수다. 준비 후 노트나 첨부가 사라지거나 바뀌면 해당 항목을 실패로 남기고 `copy_validation_status`와 최초 준비 상태를 함께 확인한다. `attachment_paths`에 별도로 명시한 첨부는 원본 bytes의 독립 복제와 링크 상태를 확인한다. 배치의 `registration_complete`와 `graph_complete`는 `False`로 시작하며 복제 성공은 ACTIVE 등록이나 그래프 반영의 성공이 아니다. 이 두 결과를 별도로 기록하고 [고리](../components/supul/gori/workflow.md)의 절차로 확인한다.

등록 직전 `verify_import_source(source_scope, result)`로 원본을 다시 확인한다. 일치하면 `True`를 반환하고 불일치하면 중단한다. 이어 `target_scope.read`로 복제본을 다시 읽어 `target_sha256`, metadata의 ID와 예상 본문을 대조한다. 원본 재확인만으로 복제본의 안전을 보장하지 않는다. 이후 기존 ACTIVE의 기대 hash와 백업을 적용해 등록하고, ACTIVE와 복제본을 다시 열어 확인한다. 도우미 결과는 활성 목록 등록 권한이 아니며 목록 등록과 재확인은 호스트 책임이다.

정규 v1·v2 문서의 복제는 기존 ID·schema·sources를 보존한다. v1의 `raw_path`를 허위로 채우거나 v2로 자동 승격하지 않는다. 가져오기 출처는 `ImportResult`와 호스트 등록 기록에 연결한다. 일반 자료를 신규 v2로 변환할 때는 source 식별자·인코딩된 상대 경로·전체 bytes hash와 `raw_path: null`을 사용한다. `source_roots`에 실제 루트와 반환된 binding을 기록하고 별도 허용 범위를 확인한 뒤 등록한다. 기존 절대 경로는 자동 변환하지 않는다.
