# 갈피: 원문과 출처

여기서 v1·v2는 제품 버전이 아닌 `batang_schema_version` 메타데이터 형식 버전이다.

호스트는 활성 목록과 현재 허용된 개별 원문·출처만 읽고 날짜·부정·조건·인용을 대조한다. 출처 연결과 v1/v2 metadata의 단일 기준은 [지식 계약](../../../references/knowledge-contract.md)이다. 일반 원문은 허용 범위에서 읽고, 관리 문서의 필수 정보와 지원 속성, 최초 가져오기 입력을 구분한다. 손상된 관리 ID·출처는 임의로 새로 만들지 않는다. 신규 문서는 v2, 기존 v1 수정은 v1과 ID·변경하지 않은 값을 유지한다. 읽기나 no-op 때문에 재저장·승격하지 않으며 미지원 frontmatter를 손실 변환하지 않는다.

호스트는 명시 범위로 [내부 파일 도우미](../../../scripts/file_ops.py)의 `FileScope(root, explicit_relative_paths)`를 구성하고 `read(path)`의 bytes와 hash를 확보한다. 필요한 경우 `parse_document`, `new_metadata`, `serialize_document`와 `verify_quote(source_bytes, start_byte, end_byte, quote)`를 호출한다. 인용은 지정 byte 구간과 대조하고 의미·맥락도 별도로 확인한다. 승인된 저장은 기대 hash·백업을 갖춘 `write`를 사용하고 저장 결과를 다시 읽어 확인한다. 구체적 함수 제약과 실패·복구는 [파일·출처 접근](../../../references/source-access.md), schema와 인용 조건은 지식 계약을 따른다. 공개 CLI는 없다.
