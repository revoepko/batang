# 공통 표현 지침

문서는 주체·조건·행동·결과·예외·근거를 함께 드러낸다. 알 수 없는 내용은 미정·가정·미검증으로 남기고 사실처럼 채우지 않는다. 코드·필드·식별자와 상태값은 바꾸지 않는다.

- 검토(review), 검증(verification), 승인, `PLAN_READY`, `TASK_DONE`, `RELEASE_READY`, `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN`을 서로 대체해 쓰지 않는다.
- 파일 존재, 정적 문서 검사, 설치 선택값, 합성 호출은 실제 호스트 동작·권한·배포·릴리즈의 증거가 아니다.
- snapshot은 이번 run에 고정한 파일 묶음이고, manifest는 파일별 해시 목록이며, pin은 다음 선택값이다. Checkout bundle은 root `SHA256SUMS`에 적힌 각 파일을 먼저 대조한 뒤 그 `SHA256SUMS` 파일 자체의 SHA-256으로 식별한다. 로컬 release 후보의 `candidate-manifest.json`과 archive hash는 별도 근거이며 기존 값을 대체하지 않는다. 설치 link·세션 전달 경로·run snapshot은 구분한다. profile hash는 실제 저장한 profile bytes에서 계산해 run 기록에만 둔다.
- Graphify는 파생 관계이고 Markdown 원본을 대체하지 않는다. Archify는 요청된 설명 산출물이며 요청이 없으면 실행하지 않는다.
- 예시는 형식을 보이기 위한 합성 자료다. 실제 사용자 승인·데이터·검증 결과로 가져오지 않는다.

사용자에게는 결론·영향·다음 행동을 먼저 알리고, 중요한 위험·미정·미검증과 근거 위치를 연결한다. 읽기 쉽게 줄이더라도 권한·부정·수치·조건·예외는 빼지 않는다.
