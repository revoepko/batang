# 지식 문서 계약

현재 활성 원본은 설정된 `knowledge_root` 안에서 `active_index`가 명시하는 Markdown 파일이다. 목록은 지식 본문이 아니라 선택 목록이며, 하위 폴더 이름은 자유다. 예를 들어 `- [주제](notes/topic.md)`처럼 root 기준 경로를 명시한다. 기존 목록의 형식·경로·포함 파일을 확인하고 승인 범위를 대조한다. 새 목록의 위치·포함 파일은 생성 전 명시 승인이 필요하다.

여기서 v1·v2는 제품 버전이 아닌 `batang_schema_version` 메타데이터 형식 버전이다.

## v1·v2 정규 frontmatter

필수 최상위 key는 아래 일곱 개이며 선택 key `aliases`를 허용한다. 각 줄은 `key: JSON값`이며 `---` 줄로 감싼다. 범용 YAML은 지원하지 않는다. `parse_document`·`serialize_document`는 누락·중복·미지원 key와 잘못된 타입을 거부한다. 기존 비정규 YAML을 부분 해석해 덮어쓰지 않는다.

| key | 계약 |
|---|---|
| `batang_schema_version` | 정수 `1` 또는 `2` |
| `batang_id` | 기존의 빈 문자열 아닌 ID를 보존. 신규 v2 생성 때만 UUID 발급 |
| `subject` | 문자열 |
| `tags` | 문자열 배열 |
| `content_kind` | 선택 자료의 유형을 나타내는 문자열 |
| `sources` | `{id, path, origin, sha256, raw_path}` 객체 배열 |
| `legacy_refs` | `{path, sha256}` 객체 배열. 과거 참조가 없으면 빈 배열 |

`aliases`는 v1·v2에서 누락 또는 문자열 배열(빈 배열 포함)이다. 누락과 빈 배열을 자동 치환하지 않는다. null·단일 문자열·숫자·혼합 배열·빈 문자열·공백뿐인 항목은 거부한다. 별칭의 표기·순서·중복을 임의 정규화하지 않는다. 정규 예: `aliases: ["별칭"]`. 기존 reader는 이 key를 거부하므로 확장 reader가 필요하며 필드를 삭제하거나 숨겨 우회하지 않는다.

v1은 기존 엄격 타입을 유지한다. source의 다섯 값은 모두 빈 문자열 아닌 문자열이고 hash는 소문자 64자리 hex다. v1 문서는 읽기 때문에 다시 저장하지 않으며, 명시 수정 때도 v1·ID·변경하지 않은 값을 보존한다. 자동 key 보충·v2 승격·migration은 하지 않는다.

v2의 source `id`·`origin`은 빈 문자열 아닌 문자열이다. `path`·`sha256`·`raw_path`는 빈 문자열 아닌 문자열 또는 `null`이다. hash 문자열은 소문자 64자리 hex다. path를 모르면 `null`, 정확한 전체 원문 bytes를 관측하지 못하면 `sha256: null`, raw 사본이 없으면 `raw_path: null`로 둔다. 경로나 날짜를 추정하거나 raw 사본을 새로 만들지 않는다. 부분 자료 hash를 전체 원문 hash로 표시하지 않는다. `legacy_refs`는 두 버전 모두 기존의 문자열 path·hash 구조를 유지한다.

호스트가 **신규** metadata를 만들 때 내부 `new_metadata(subject, content_kind, sources, *, tags=..., legacy_refs=..., aliases=...)`를 사용할 수 있다. v2와 새 UUID를 만들고, `tags`·`legacy_refs` 인자를 미제공한 경우에만 빈 배열을 채운다. 명시 `null`은 거부한다. `aliases` 인자가 누락되면 key를 만들지 않고 명시 인자는 검증해 보존한다. 이 함수는 저장·승인·기존 문서 변환을 수행하지 않는다. 저장된 v1·v2는 일곱 key가 모두 있어야 하며 읽기 시 기본값을 보충하지 않는다.

`sources[].sha256`는 원문을 관측한 당시 hash이며 현재 raw 파일 hash나 현재 지식 문서 hash가 아니다. `legacy_refs[].sha256`는 참조한 과거 파일의 확인한 hash다. stage/status/call·모델 이력은 지식의 확신 등급이 아니며 별도 신뢰도 필드를 만들지 않는다. 파일 hash·형식 검사가 의미 검토 완료를 뜻하지 않는다.

## 본문·인용·no-op

본문은 frontmatter 종료 줄 다음 byte부터다. 본문 bytes를 그대로 전달하고 디코딩·재인코딩·줄바꿈 정규화하지 않는다. `split_frontmatter`는 경계만 분리하며 YAML 의미를 해석하지 않는다.

기존 파일을 명시 수정할 때 `serialize_document(metadata, body, original=읽은bytes)`를 사용하면 metadata와 본문이 같을 때 원래 bytes를 반환한다. CRLF frontmatter도 no-op에서 보존된다. 변경이 있을 때만 정규 JSON 값 frontmatter를 생성한다. aliases 변경 시에도 ID·schema·본문과 변경하지 않은 metadata를 보존한다. 미지원 기존 형식은 이 인자로도 우회 변환하지 않는다.

직접 인용은 `verify_quote(source_bytes, start_byte, end_byte, quote)`로 선택한 byte 구간을 대조할 수 있다. 시작 포함·끝 제외다. 반복 문구도 명시 구간을 사용하며 Unicode 정규화·공백 보정·유사 매칭은 하지 않는다. byte 일치와 날짜·부정·조건·의미 대조는 별개다.

## 변경·복구

같은 ID의 이동은 경로 변경이다. 활성 목록에서 ID 중복을 확인하고 새 경로 충돌을 덮어쓰지 않는다. 명시 삭제 대상과 공유 근거를 분리하며 과거 자료·DB를 자동 정리하거나 fallback으로 읽지 않는다.

변경 전 기대 hash 대조와 승인된 `backup_root`의 최소 백업을 하고 쓴 뒤 실제 파일·본문·metadata를 다시 대조한다. 백업 디렉터리는 `0700`, 파일은 `0600`으로 준비하고 검색 대상에서 제외한다. 원문·비밀값을 일반 로그나 시험 artifact에 복제하지 않는다.

원본 검증 후 활성 목록을 갱신하고, 목록도 개별 파일로 기대 hash·백업을 적용한다. 복구는 작업 때 기록한 변경 후 hash와 현재 파일을 대조하며 이후 사용자 수정이 있으면 중단한다. 새 파일과 기존 파일의 복구 경계도 구분한다. 여러 파일·목록·그래프는 단일 트랜잭션이 아니며 중간 실패를 전체 완료로 보고하지 않는다.
