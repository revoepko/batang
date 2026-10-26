# 결정 기록

결정마다 확인된 사실, 사용자 승인, 위임된 세부결정, 가정과 열린 질문을 구분한다. `confirmed`는 근거가 확인됐다는 뜻이며 사용자 승인을 뜻하지 않는다.

- decision_id / recorded_at:
- 상태: `confirmed` / `candidate` / `superseded`
- 종류: `user_confirmed` / `delegated_ai` / `assumption` / `open_question`
- 내용 / 적용 범위:
- 결정 주체 / 권한 또는 위임 근거:
- 고려한 선택 / 선택 이유 / 영향:
- Markdown 근거 경로·구절 또는 요청 ID:
- 대체하는 결정 / 변경 조건:
- 미정이라면 차단 여부·이유 / 담당 / 해결 시점:
- vault·활성 목록·Graphify·Archify에 미치는 영향과 실제 접근 권한:
- 기존 run·기존 API 요구와의 관계: 보존 / 별도 전환 승인 필요 / 해당 없음:
- 사용자 검토 표시 연결: 관련 E·D·T·R·V ID / 상세 위치:

| 관계 | 대상 | 이유 | 근거 | 관계 상태 |
|---|---|---|---|---|
| `depends_on` / `supports` / `refines` / `conflicts_with` / `supersedes` |  |  |  | `confirmed` / `candidate` |

관계는 원본에서 대상으로 기록한다. 대체된 결정과 이전 `FAIL`·`BLOCKED`·`NOT_RUN` 이력은 지우지 않는다. 기존 API 기반 run을 공개판 구조로 자동 변환하지 않는다.
