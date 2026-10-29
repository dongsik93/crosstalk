# v0.12 verification record

Status: implementation under verification. The engine remains explicit opt-in; no completed release or actual-user-flow claim is made from test-file existence. Baseline is pinned v0.11 commit `0d8a24e692bfde2ee3ee61fe84731050b85b0c0f`, not an invented tag or the plan author's older v0.10 remote observation.

## Current handoff

The user requested stopping further verification loops and finishing implementation. No additional live sessions or final review cohort were started after that instruction. The engine, protocol/schema-3 upgrade, adapter boundary and shared workflow are implemented; `engine_default=false` remains in place. These changes are not a certified release or a claim that every scenario below passed.

Work already executed before that instruction includes a complete CLI one-round vertical slice; initial-disclosure/paused-disclosure checks; local rebind fencing; transaction and ask tests; schema-3 migration with the real v0.11 runtime; installation/repair; adapter parity; and workflow command contracts. The first integration transcript is `.dsgoal/artifacts/v012-integration-initial.txt`. Its only failing script was the old lease fixture using positional inserts after binding columns were added; those two fixture inserts were made explicit and all twelve lease tests then passed (`v012-leases.txt`). Subsequent pending-peer association and finalization guidance edits have not had a final integrated rerun.

Detailed scenario mapping, actual v0.12 user-entrypoint flows, final code review and release acceptance remain deferred. No production database was migrated by this implementation work.

## Baseline and evidence rules

The parent implementation run executed the pinned v0.11 source in a separate temporary checkout: 12 test scripts exited zero, including 123 unittest cases plus the original bridge and mailbox integration scripts. This is baseline evidence only; it does not certify the changed v0.12 runtime.

For each current result record the source snapshot, command, environment, expected/actual state and sanitized transcript. Native tests must name real CLI/terminal versions, start entrypoint, permission mode and stored run/action/message links. Never commit user DBs, token values or credentials. A mock adapter or configured CI workflow is not proof of a live test or a remote CI run.

The required scenario inventory below is transcribed from the approved plan so omissions remain visible. Its pending status must be replaced only by an actual execution record; no automated scenario is inferred from implementation names. Full live checks and support/default activation remain gated separately.

## Automated scenario inventory

| ID | Scenario | Expected contract | Current evidence |
| --- | --- | --- | --- |
| BASE-01 | v0.11 최종 태그와 계획서의 명령을 대조합니다. | 이름 차이와 선행 변경을 기록하고 존재하지 않는 함수를 가정하지 않습니다. | Pending v0.12 execution record. |
| BASE-02 | 기존 v0.11 전체 테스트를 새 runtime에서 실행합니다. | 기존 성공·실패 의미가 유지됩니다. 변경된 계약은 별도 표시합니다. | Pending v0.12 execution record. |
| BASE-03 | engine module만 import합니다. | DB 생성·터미널 호출·환경 변경이 없습니다. | Pending v0.12 execution record. |
| BASE-04 | engine core의 의존성을 검사합니다. | CLI별 분기·subprocess·terminal 직접 호출이 없습니다. | Pending v0.12 execution record. |
| BASE-05 | 지원하지 않는 조합으로 engine run을 시작합니다. | 메시지나 pane을 만들기 전에 명시적으로 거부합니다. | Pending v0.12 execution record. |
| ENG-01 | 새 analyze run을 준비합니다. | 원문·설정·참가자·버전·첫 action이 정확히 저장됩니다. | Pending v0.12 execution record. |
| ENG-02 | 같은 start operation을 재호출합니다. | run·첫 request·pending launch가 중복 생성되지 않습니다. | Pending v0.12 execution record. |
| ENG-03 | 같은 caller가 다른 operation으로 두 번째 활성 analyze를 시작합니다. | 기존 run을 알려주며 중복 시작을 거부합니다. | Pending v0.12 execution record. |
| ENG-04 | peer가 caller 초기 분석보다 먼저 답합니다. | 결과는 저장되지만 caller에 본문·결론 summary를 공개하지 않습니다. | Pending v0.12 execution record. |
| ENG-05 | caller 초기 답변을 저장하기 전에 history/report/export로 접근합니다. | 결과 존재·상태만 보이고 본문은 공개하지 않습니다. | Pending v0.12 execution record. |
| ENG-06 | peer 완료로 run_revision이 바뀐 뒤 caller 초기 분석을 제출합니다. | 같은 input/action epoch라면 정상 수락합니다. | Pending v0.12 execution record. |
| ENG-07 | 초기 분석을 확정한 뒤 다른 본문으로 다시 제출합니다. | RESULT_CONFLICT이며 원래 결과가 남습니다. | Pending v0.12 execution record. |
| ENG-08 | 두 결과가 갖춰집니다. | 현재 round의 compare action이 하나만 만들어집니다. | Pending v0.12 execution record. |
| ENG-09 | 존재하지 않거나 이전 round의 답변을 비교 근거로 제출합니다. | 현재 입력 참조 불일치를 거부합니다. | Pending v0.12 execution record. |
| ENG-10 | continue 결정을 제출합니다. | caller 입장·질문·ack·다음 request가 한 번만 연결됩니다. | Pending v0.12 execution record. |
| ENG-11 | 두 번째 round의 peer 답변이 먼저 들어옵니다. | 이전 결정의 고정된 caller_position을 비교 기준으로 사용합니다. | Pending v0.12 execution record. |
| ENG-12 | concluded/diverged/unresolved 종료를 각각 제출합니다. | 저장 결과와 화면 라벨이 서로 구분됩니다. | Pending v0.12 execution record. |
| ENG-13 | 마지막 허용 round에서 continue를 제출합니다. | 추가 request 없이 round_limit으로 종료하며 requested/applied 결정을 남깁니다. | Pending v0.12 execution record. |
| ENG-14 | completed run에 신규 submit/decide를 보냅니다. | 동일 확정 결과 조회를 제외한 새 변경은 거부합니다. | Pending v0.12 execution record. |
| ENG-15 | 진행 중 preset 파일을 수정합니다. | 기존 run의 snapshot과 input_digest는 바뀌지 않습니다. | Pending v0.12 execution record. |
| TX-01 | 첫 request 저장 트랜잭션의 각 단계에서 실패시킵니다. | run/round/action/request가 함께 남거나 함께 rollback합니다. | Pending v0.12 execution record. |
| TX-02 | peer reply 저장과 engine result 연결 사이에 오류를 발생시킵니다. | reply만 저장되거나 engine result만 존재하지 않습니다. | Pending v0.12 execution record. |
| TX-03 | continue의 ack와 후속 request 사이에 오류를 발생시킵니다. | 현재 reply 완료와 다음 round가 함께 rollback합니다. | Pending v0.12 execution record. |
| TX-04 | 같은 compare에 두 프로세스가 서로 다른 결정을 제출합니다. | 유효한 하나만 확정되고 다른 결과는 충돌입니다. | Pending v0.12 execution record. |
| TX-05 | commit 직후 stdout 전에 프로세스를 종료합니다. | 같은 operation_id의 재호출로 기존 결과와 연결된 ID를 확인합니다. | Pending v0.12 execution record. |
| TX-06 | 같은 operation_id에 다른 의미 payload를 보냅니다. | 새 요청 생성 없이 IDEMPOTENCY_CONFLICT입니다. | Pending v0.12 execution record. |
| TX-07 | request commit 직후 알림 전에 종료합니다. | 같은 message의 not_attempted 상태가 남고 retry로 처리합니다. | Pending v0.12 execution record. |
| TX-08 | UI 입력 후 attempt 기록 전에 종료합니다. | unknown이며 같은 request를 다시 만들지 않습니다. | Pending v0.12 execution record. |
| TX-09 | finish 판단 저장 후 final report 저장 전 종료합니다. | finalizing에서 advance만으로 복구되며 모델을 부르지 않습니다. | Pending v0.12 execution record. |
| TX-10 | SQLite write lock을 다른 연결이 점유합니다. | 제한된 대기 후 DB_BUSY로 끝나고 외부 UI를 잘못 호출하지 않습니다. | Pending v0.12 execution record. |
| TX-11 | peer 완료와 pause/cancel을 동시에 실행합니다. | DB에서 허용된 순서 하나로 확정되고 terminal 이후 후속 요청이 없습니다. | Pending v0.12 execution record. |
| TX-12 | advance를 두 프로세스가 동시에 호출합니다. | 동일 action/report가 중복되지 않고 무한 전이 루프가 없습니다. | Pending v0.12 execution record. |
| ROUTE-01 | 같은 cwd에 Codex 2개·Claude 2개를 둡니다. | 검증된 논리 참가자만 사용하고 포커스로 대상을 바꾸지 않습니다. | Pending v0.12 execution record. |
| ROUTE-02 | peer가 claim 후 종료합니다. | 기존 recover로 같은 메시지를 재점유하며 round가 늘지 않습니다. | Pending v0.12 execution record. |
| ROUTE-03 | caller가 compare claim 후 종료합니다. | 같은 peer reply를 recover하고 peer 분석을 다시 요청하지 않습니다. | Pending v0.12 execution record. |
| ROUTE-04 | recover 후 과거 token으로 답변을 제출합니다. | stale 결과를 새 engine result로 확정하지 못합니다. | Pending v0.12 execution record. |
| ROUTE-05 | caller local_initial을 수행하던 pane을 재바인딩합니다. | 기존 local action handle은 거부되고 명시적 인계만 epoch를 갱신합니다. | Pending v0.12 execution record. |
| ROUTE-06 | peer rebind와 결과 제출을 경합시킵니다. | binding generation을 검사해 허용된 한 경로만 확정합니다. | Pending v0.12 execution record. |
| ROUTE-07 | take 후 token 출력 전에 종료합니다. | 로그에서 token을 복원하거나 검사를 건너뛰지 않고 기존 recover를 안내합니다. | Pending v0.12 execution record. |
| ROUTE-08 | managed request/reply에 raw reply/ack/send를 실행합니다. | RUN_MANAGED_BY_ENGINE이며 run 상태를 우회 변경하지 않습니다. | Pending v0.12 execution record. |
| ROUTE-09 | 초기 barrier로 막힌 reply 앞뒤에 다른 준비된 메시지가 있습니다. | 다른 처리 가능한 메시지를 부당하게 막지 않습니다. | Pending v0.12 execution record. |
| ROUTE-10 | 새 task 알림을 CLI가 읽습니다. | 기존 run action으로 dispatch하고 새로운 run start를 만들지 않습니다. | Pending v0.12 execution record. |
| ADAPT-01 | 기존 default Claude/Codex/agy launcher와 새 LaunchSpec을 비교합니다. | 기존 CLI 인자 의미를 유지하고 새로운 권한 우회 옵션이 없습니다. | Pending v0.12 execution record. |
| ADAPT-02 | 명시적인 실행별 auto-approve를 선택합니다. | 선택한 새 peer에만 적용하고 기존 peer나 전역 설정을 바꾸지 않습니다. | Pending v0.12 execution record. |
| ADAPT-03 | PATH·config root·공백·한글·따옴표 경로를 사용합니다. | 실행 파일·DB·지시문·대상 경로가 정확히 전달됩니다. | Pending v0.12 execution record. |
| ADAPT-04 | terminal submit helper를 timeout시킵니다. | submitted/failed/unknown을 구분하고 사용자 AI 프로세스를 종료하지 않습니다. | Pending v0.12 execution record. |
| ADAPT-05 | screen capture 미지원 backend를 사용합니다. | 엔진이 screen 없이 동작하고 optional capture는 명시적으로 거부합니다. | Pending v0.12 execution record. |
| ADAPT-06 | capability가 unknown인 환경을 사용합니다. | 지원이 필요한 작업을 추측해서 실행하지 않습니다. | Pending v0.12 execution record. |
| ADAPT-07 | cmux send/key/capture와 콜백을 golden fixture로 비교합니다. | 추출 전후 legacy 의미가 유지됩니다. | Pending v0.12 execution record. |
| ADAPT-08 | Ghostty pending peer의 ready를 지연시킵니다. | 새 pane을 추가 생성하지 않고 같은 pending launch를 유지합니다. | Pending v0.12 execution record. |
| ADAPT-09 | adapter와 legacy wrapper의 호출 경로를 추적합니다. | engine→adapter→bridge→engine 같은 순환 호출이 없습니다. | Pending v0.12 execution record. |
| ADAPT-10 | create/input 사이에서 대상 pane을 닫습니다. | 새 대상에 자동 재지정하지 않고 기존 delivery 정책을 따릅니다. | Pending v0.12 execution record. |
| ASK-01 | ask를 시작하고 양쪽 분석을 저장합니다. | compare·follow-up 없이 sampled로 끝납니다. | Pending v0.12 execution record. |
| ASK-02 | ask peer가 답변을 저장합니다. | caller reply wake-up을 보내지 않습니다. | Pending v0.12 execution record. |
| ASK-03 | 완료 ask를 report로 조회합니다. | 개별 답변만 표시하고 새로운 AI 요약을 만들지 않습니다. | Pending v0.12 execution record. |
| ASK-04 | 완료 ask의 informational reply가 inbox에 남습니다. | stuck work로 오판하거나 다음 일반 메시지를 막지 않습니다. | Pending v0.12 execution record. |
| ASK-05 | 기존 일반 v0.11 ask와 새 managed ask를 함께 둡니다. | owner별 처리 계약이 섞이지 않습니다. | Pending v0.12 execution record. |
| UPG-01 | v0.11 DB를 schema 3으로 이관합니다. | ID·본문·seq·reply·lease·binding 관계를 보존합니다. | Pending v0.12 execution record. |
| UPG-02 | migration을 중간에 종료하거나 반복합니다. | 구DB 또는 완성된 새DB로 판별되고 중복 run을 만들지 않습니다. | Pending v0.12 execution record. |
| UPG-03 | 실제 v0.11 실행 파일이 schema 3 DB에 접근합니다. | 새 데이터를 쓰거나 managed UI 알림을 보내기 전에 거부합니다. | Pending v0.12 execution record. |
| UPG-04 | 새 runtime으로 기존 mailbox-v2 thread를 처리합니다. | 과거 대화를 자동 run 변환하지 않고 기존 의미를 유지합니다. | Pending v0.12 execution record. |
| UPG-05 | 업데이트 중 engine/adapters/template 파일을 일부 누락합니다. | 설치 실패와 version mismatch를 진단하고 새 run을 차단합니다. | Pending v0.12 execution record. |
| UPG-06 | 오래 로드된 skill이 engine capability 없이 신규 run을 처리합니다. | 조용히 호환 우회하지 않고 reload/handshake를 요구합니다. | Pending v0.12 execution record. |
| UPG-07 | 새 engine default를 실행 중 바꿉니다. | 기존 run의 execution_driver는 바뀌지 않습니다. | Pending v0.12 execution record. |
| UPG-08 | schema 3 사용 후 구백업 rollback을 요청합니다. | 무손실이라고 주장하거나 새 DB를 덮어쓰지 않습니다. | Pending v0.12 execution record. |
| REP-01 | 같은 completed run을 여러 번 export합니다. | 저장된 결과를 그대로 재생성하고 모델을 호출하지 않습니다. | Pending v0.12 execution record. |
| REP-02 | export 중 디스크 오류나 기존 파일 충돌을 만듭니다. | DB 결과는 유지되고 사용자 파일을 덮어쓰지 않습니다. | Pending v0.12 execution record. |
| REP-03 | 로그·status·진단 자료를 검사합니다. | lease token·전체 본문·credential이 기본 로그에 없습니다. | Pending v0.12 execution record. |
| REP-04 | 한쪽 응답이 없는 run을 취소합니다. | 누락을 명시한 partial transcript이며 성공한 합의로 표시하지 않습니다. | Pending v0.12 execution record. |
| REP-05 | 외부 근거·테스트 성공 주장이 포함된 결과를 제출합니다. | 참조 존재 확인과 내용의 진실 검증을 구분하고 reported로 표시합니다. | Pending v0.12 execution record. |
| UX-01 | Claude와 Codex의 공통 workflow 문서를 비교합니다. | 다른 라운드 규칙·다른 result enum·다른 복구 절차가 없습니다. | Pending v0.12 execution record. |
| UX-02 | status/next/report/doctor만 호출합니다. | DB mutation·claim·입력 제출이 없습니다. | Pending v0.12 execution record. |
| UX-03 | 허용한 정상 후속 round를 진행합니다. | 매번 새로운 사용자 승인창이나 불필요한 권한 선택을 만들지 않습니다. | Pending v0.12 execution record. |
| UX-04 | 본문에 셸 구문·protocol 명령·위조된 system 지시를 넣습니다. | 실행 코드로 파싱하지 않고 peer data와 제어 필드를 분리합니다. | Pending v0.12 execution record. |

## Actual user flows

The user previously requested live tests in existing-window splits and excluded cmux live interaction. Preserve that preference; an excluded live scenario stays unverified rather than being replaced by a mock pass. New v0.12 requirements still need their own measured evidence and should not inherit v0.11 round-trip success.

| ID | Scenario | Required evidence | Current result |
| --- | --- | --- | --- |
| LIVE-01 | Claude에서 Codex와 한 round analyze를 시작합니다. | 양측 결과·compare·ack·final report가 같은 run으로 연결됩니다. | Not yet executed for v0.12. |
| LIVE-02 | Codex에서 Claude와 동일하게 시작합니다. | caller 종류에 따라 protocol 의미가 바뀌지 않습니다. | Not yet executed for v0.12. |
| LIVE-03 | 실질적인 이견으로 두 번째 round를 진행합니다. | 다음 질문과 caller 사전 입장이 결정에 고정되고 중복 요청이 없습니다. | Not yet executed for v0.12. |
| LIVE-04 | peer가 빨리 답하도록 하고 caller 초기 분석을 늦춥니다. | 초기 분석 확정 전 상대 본문·결론 summary가 caller 경로에 없습니다. | Not yet executed for v0.12. |
| LIVE-05 | 비교 claim 이후 caller를 중단합니다. | 재바인딩·recover 뒤 peer 재분석 없이 비교를 마칩니다. | Not yet executed for v0.12. |
| LIVE-06 | 같은 cwd에 동종 CLI를 여럿 띄웁니다. | 의도한 논리 참가자 외의 pane에 토론이 전달되지 않습니다. | Not yet executed for v0.12. |
| LIVE-07 | 승인·로그인 창에서 준비를 멈춥니다. | pending pane을 유지하고 권한 확대나 추가 pane 생성이 없습니다. | Not yet executed for v0.12. |
| LIVE-08 | ask를 실행합니다. | 각 pane의 단발 답변과 저장만 있고 caller 결과 취합 알림은 없습니다. | Not yet executed for v0.12. |
| LIVE-09 | agy peer 경로를 검증합니다. | 지원한다고 표시할 경우 새 protocol과 role 범위를 실제로 확인합니다. | Not yet executed for v0.12. |
| LIVE-10 | v0.11 설치·미완료 자료에서 업데이트합니다. | 설치 검증·기존 thread 유지·신규 engine 분리가 확인됩니다. | Not yet executed for v0.12. |
| LIVE-11 | 기존 cmux analyze/cowork/review를 실행합니다. | adapter 추출이 전송·콜백·원본 작업 보호를 퇴행시키지 않습니다. | Not executed; prior user preference excludes cmux live interaction. |
| LIVE-12 | 사용자 pause/cancel과 결과 도착을 경합시킵니다. | 저장된 사실, 진행 중 입력의 한계, 이후 신규 작업 차단이 일치합니다. | Not yet executed for v0.12. |

## Release boundary

Do not activate the engine as the default or claim all gates passed while data-loss, wrong-peer delivery, managed-message bypass, initial-result leakage, duplicate continuation, stale-result acceptance, old-writer access, partial-installation defects, or required live evidence remain unresolved. Keep concluded, diverged, unresolved, round_limit and partial outcomes distinct.

The benchmark may measure control overhead and retained-result recovery only with recorded commands and environment. No unmeasured latency, model accuracy, token-cost or consensus-quality claim belongs in the release notes.
