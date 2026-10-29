# Crosstalk

[English](README.md) | [한국어](README.ko.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Version](https://img.shields.io/badge/version-0.12.2--dev-blue)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-plugin-black)

Ghostty에서 Claude와 Codex를 나란히 띄워 토의하거나, Antigravity(`agy`)를 참여자로 초대하세요. 어느 CLI에서든 질문하면 Crosstalk이 상대 AI의 pane을 재사용하거나 Ghostty 화면을 분할해 실행하고, 질문과 답변을 주고받습니다. tmux는 필요 없습니다.

![Crosstalk hero](docs/hero.png)

> v0.12.2은 Claude 호출자와 새 Codex 대화 사이의 독립 검토를 추가합니다. 자연어로 독립 검토를 요청하면 엔진 옵션 없이 보호 경로를 선택합니다. 일반 엔진 토론은 opt-in을 유지하며, 기존 mailbox-v2 thread의 의미는 바꾸지 않습니다. [독립 검토의 범위](docs/independent-review.md), [업그레이드](docs/upgrade-v0.12.md), [v0.12 검증 기록](docs/verification-v0.12.md)을 확인하세요. 전체 릴리스·실기 검증 완료를 뜻하지 않습니다.

## 소개

Crosstalk은 기존 대화형 AI CLI를 연결합니다. Codex에서는 `$crosstalk <topic>`, Claude Code에서는 `/crosstalk <topic>`으로 시작합니다. 호출자가 각 AI의 답변을 비교하고 억지로 의견을 맞추지는 않습니다. 첫 전달문을 보호하려면 아래 독립 검토 흐름을 사용합니다. 기존 일반 메시지함 대화가 소급해서 이 보호를 받는 것은 아닙니다.

**Claude ↔ Codex 토의는 Ghostty로 시작하는 것을 권장합니다.** 고급 작업에는 기존 cmux 백엔드도 쓸 수 있습니다. 지원 범위는 다음과 같습니다.

| 기능 | macOS의 Ghostty | cmux |
| --- | --- | --- |
| Claude ↔ Codex 일반 메시지함 | mailbox-v2 호환 경로 유지 | 레거시 지원, Codex 호출자는 실험 단계 |
| Discussion engine 1 (`--engine`) | caller 1명·peer 1명, 명시적 opt-in; v0.12 실기 검증 대기 | 미지원; 기존 RUN_ID 흐름 유지 |
| 자연어 독립 검토 | Claude 호출자 → 새 Codex peer; 사용자 발언을 수집하며 `--engine` 불필요 | 미지원 |
| 빠른 의견 수집 (`ask`) | 지원 | 지원 |
| 상대 pane 준비 | 같은 탭에서 자체 분할 또는 재사용 | `:launch`로 워크스페이스 분할 |
| Antigravity (`agy`) 참여 | 일반 호환 경로 유지; engine peer는 protocol 3/engine 1 준비와 실기 검증 필요 | 레거시 지원 |
| 공동작업 및 PR 리뷰 | 아직 미이식 | 사용 가능, 심층 리뷰는 실험 단계 |
| 화면 캡처 / 화면 기반 전달 | 현재 어댑터 미지원; 엔진 필수 조건 아님 | 레거시 지원 |

실제 점검 내용과 한계는 [Ghostty 검증 기록](docs/ghostty-verification.md)을 참고하세요. 이 소스에는 Ghostty 연동이 포함되어 있습니다. 마켓플레이스에서 예전 버전을 설치했다면 빠른 시작을 따라 하기 전에 업데이트해야 합니다.

## 평소 대화에서 독립 검토하기 (v0.12.2)

Claude와 평소처럼 이야기하다가 이렇게 말하면 됩니다.

> 야, 이거 옆에 Codex랑 독립적으로 좀 검토해.

Crosstalk이 기록된 사용자 질문과 이후 사용자 제약을 묶습니다. Claude가 자기 결론을 섞어 첫 전달문을 다시 쓰지 않습니다. 주제가 분명하면 바로 진행하고, 범위나 출처가 불명확할 때만 한 번 짧게 확인합니다. 사용자가 엔진 옵션을 알거나 매 라운드 승인할 필요는 없습니다.

Claude는 기존 문맥을 유지하고, Codex는 해당 입력용 새 대화로 옆 pane에 실행합니다. 기존 Codex 대화를 지우거나 닫지는 않습니다. 두 첫 답변을 저장한 뒤 공개하고, 이후에는 같은 대화에서 의견과 근거를 교환합니다.

업데이트된 Claude 플러그인의 입력 capture hook과 런타임이 필요하므로 설치 후 플러그인/세션 지침을 다시 읽어야 합니다. 첫 독립 요청에는 임의 body·rules·persona를 덧붙이지 못합니다. “Claude가 만든 설계안을 검토해”는 별도 제안서 검토로 표시하며, 기존 문맥의 추가 의견을 독립 검토로 부르지 않습니다. 새 대화도 프로젝트 지침과 공유 파일을 읽을 수 있어 완전한 무문맥·무편향 보장은 아닙니다. [상세 동작과 한계](docs/independent-review.md)를 참고하세요.

## 일반 토론 엔진 opt-in (v0.12)

엔진은 현재 run·round·action·고정 입력과 종료 이유를 저장합니다. 분석과 비교 판단은 AI가, 진행 절차와 원자적 상태 변경은 코드가 담당합니다. 실기 게이트를 통과하기 전에는 명시적으로 선택합니다.

```text
# Claude
/crosstalk:analyze --engine <주제>
/crosstalk:ask --engine <질문>
# Codex
$crosstalk analyze --engine <주제>
$crosstalk ask --engine <질문>
```

양쪽에 protocol-3/engine-1 준비가 필요합니다. `capabilities --json`의 `discussion_instructions`가 알려주는 [공통 workflow](assets/codex-skills/crosstalk/discussion.md)를 따릅니다. `run start` 자체가 저수준 opt-in이며, `engine_default=false`인 동안 그 외의 옵션 없는 새 요청은 일반 메시지함 경로를 유지합니다. 자연어 독립 검토 요청은 별도의 보호 경로를 자동 선택합니다. 기존 thread/run의 실행 소유자를 조용히 바꾸지 않습니다.

caller가 첫 분석을 저장하기 전에는 Crosstalk API가 peer의 첫 답변을 공개하지 않습니다. 이는 공개 순서에 대한 보장이며 옆 pane이나 기존 문맥의 영향을 격리하는 보장은 아닙니다. 비교 결정은 해당 round의 고정 결과를 참조하며, peer의 agree만으로 합의나 정답을 인증하지 않습니다. 결과는 호출자의 비교 결론·이견 유지·정보 부족·라운드 상한 종료를 구분합니다.

Ask는 각 답변을 저장하고 sampled로 끝납니다. compare·추가 round·caller reply wake-up·읽었다는 가짜 ack가 없습니다. 요청받았을 때 `run report`로 저장 결과를 봅니다. `run continue`는 workflow/local action 인계, `recover`는 승인된 message lease 재점유, `retry`는 같은 알림 재전송입니다.

상주 데몬·직접 모델 API·모델/effort 변경·agy caller·혼합 터미널 run·다중 peer quorum·Ghostty cowork/review 이식은 추가하지 않습니다. [엔진 계약](docs/discussion-engine-v1.md), [어댑터](docs/adapter-contracts.md), [업그레이드](docs/upgrade-v0.12.md), [검증](docs/verification-v0.12.md)을 참고하세요. 시작 문구는 짧게 유지하며 상세 handshake는 비공개 임시 파일에 둡니다.

## 주요 기능

- **눈으로 보는 토의**: 어느 CLI에서 시작하든 이웃한 Ghostty pane에서 Claude와 Codex의 작업을 볼 수 있습니다.
- **기존 CLI 계정 사용**: 별도의 모델 API 연동을 추가하지 않습니다.
- **상대 AI 자동 준비**: 같은 탭에 라벨이 지정된 상대 pane이 없으면 현재 디렉터리에서 다른 CLI를 실행합니다. 시작 확인을 받은 뒤 작업을 보냅니다.
- **첫 독립 입력 보호**: Claude capture 흐름에서는 호출자가 재작성한 결론 대신 기록된 사용자 발언과 중립 지침을 전달합니다.
- **영속 메시지함**: Ghostty의 요청과 답변을 SQLite에 저장합니다. `send`, `receive`, `reply`가 ID, 수신 상태, 답변 알림을 관리하므로 AI가 메시지별 MD 파일이나 ping 명령을 다룰 필요가 없습니다.
- **명시적인 결과**: 일반 답변은 verdict/confidence를 유지하며, opt-in 엔진은 고정 입력 참조와 구조화된 비교 결정을 추가합니다. 기존 cmux 표식은 JSON으로 안전하게 파싱합니다.
- **빠른 의견 수집**: `ask`는 콜백이나 결과 취합 없이 각 AI의 pane에서 답변합니다.
- **cmux 고급 작업**: git worktree 공동작업, PR 리뷰, Antigravity 참여는 cmux에서 계속 사용할 수 있습니다.

## 요구 사항

| 도구 | 용도 | 참고 |
| --- | --- | --- |
| macOS | 두 터미널 백엔드 모두 | 터미널 앱이 지원하는 OS 버전 사용 |
| 필요한 AppleScript 동작을 제공하는 Ghostty | 자체 Claude ↔ Codex 토의 | 정확한 주소·입력 capability 확인; 실제 버전은 검증 기록 참고 |
| Claude Code 또는 Codex CLI | 토의 호출자 | 토의를 시작하려면 둘 중 하나 이상 필요 |
| Claude, Codex 또는 Antigravity (`agy`) | 참여자 | 선택한 호출자와 참여자 CLI를 설치하고 인증 |
| jq | 브리지 및 설정 | 필수 |
| sqlite3가 포함된 Python 3.11+ | Ghostty 메시지함 | 표준 라이브러리만 사용, pip 패키지나 서버 불필요 |
| Node.js / npm | npm으로 배포되는 AI CLI 설치 | 별도의 Crosstalk 런타임은 아님 |
| cmux 1.3+ | 대체 백엔드 및 고급 작업 | Ghostty 토의에는 선택 사항 |
| GitHub CLI (`gh`) | PR 리뷰 | 선택 사항 |

Antigravity (`agy`)는 별도로 다운로드합니다. Ghostty 메시지함과 기존 cmux 대화에서 참여자로 사용할 수 있습니다. 사용할 CLI를 설치하고 인증해 두세요.

## 언어

Crosstalk 명령 UI는 영어와 한국어를 지원합니다. `/crosstalk:install` 실행 중 인터페이스 언어를 고릅니다.

- English
- Korean

설정은 다음 파일에 저장됩니다.

```text
~/.claude/crosstalk/config.json
```

```json
{
  "active_rules": "default",
  "active_persona": "default",
  "language": "en"
}
```

한국어는 `"language": "ko"`로 설정합니다. 기본 규칙과 페르소나는 두 언어로 설치됩니다.

```text
~/.claude/crosstalk/rules/{en,ko}/
~/.claude/crosstalk/personas/{en,ko}/
```

## 설치

Claude Code에서 실행합니다.

```text
/plugin marketplace add dongsik93/crosstalk
/plugin install crosstalk@crosstalk
```

최초 설정은 한 번만 실행하면 됩니다.

```text
/crosstalk:install
```

설치 항목:

- `~/.claude/scripts/crosstalk` 및 `~/.local/bin/crosstalk` 심볼릭 링크(해당 이름이 비어 있을 때)
- `~/.claude/crosstalk/mailbox.md`
- `~/.claude/scripts/crosstalk_bridge.sh`
- `~/.claude/scripts/crosstalk_ghostty.sh`
- `~/.claude/commands/crosstalk.md`
- `~/.codex/skills/crosstalk/`
- `~/.claude/crosstalk/` 아래의 기본 규칙과 페르소나

## 빠른 시작: Ghostty

Ghostty를 지원하는 Crosstalk 버전을 설치한 뒤, Ghostty에서 프로젝트를 열고 평소처럼 CLI를 실행하세요. 기존 세션은 그대로 두어도 됩니다.

**Codex에서 시작:**

```text
$crosstalk Should this project use Compose or XML? Discuss it with Claude.
```

**Claude Code에서 시작:**

```text
/crosstalk Should this project use Compose or XML?
```

Crosstalk은 같은 탭에서 라벨이 지정된 상대 pane을 재사용하거나 오른쪽으로 분할해 현재 디렉터리에서 다른 CLI를 시작합니다. 처음 실행할 때 로그인이나 신뢰 확인이 나오면 해당 pane에서 완료하세요. 시작 확인을 받으면 질문을 전달하고, 완료 콜백은 호출자에게 돌아옵니다.

기본 조합은 Claude와 Codex입니다. Antigravity와 토의하려면 agy를 명시하세요.

```text
$crosstalk Review this design with agy.
/crosstalk Review this design with agy.
```

```text
Ghostty tab
├── Codex  ← questions and responses →  Claude
```

독립적인 의견을 빠르게 받으려면 `$crosstalk ask <question>` 또는 `/crosstalk:ask <question>`을 사용하세요. 각 AI가 자기 pane에서 답하며, 결과를 하나로 취합하지 않습니다.

상대 AI를 실행하지 않고 상태만 보려면 주제 없이 `$crosstalk` 또는 `/crosstalk`을 호출하세요. 준비 상태 점검에서 백엔드, 호출자, 상대 pane을 보여 줍니다. 호출자를 식별하지 못하면 오류를 알리고 주제를 보존해 `$crosstalk resume` 또는 `/crosstalk:resume`으로 재개할 수 있게 합니다.

### 모델과 추론 effort

현재 Crosstalk은 모델이나 effort를 지정하지 않습니다. 재사용한 pane은 기존 세션 설정을 유지하고, 새 CLI는 자체 기본값을 사용합니다. Codex 설정을 Claude에 복사하거나 그 반대로 전달하지 않습니다. Crosstalk 전용 모델/effort 재정의 옵션은 아직 없습니다.

### 새 pane의 권한 선택

Crosstalk 스킬이나 슬래시 명령이 새 Ghostty 참여자를 실행할 때 다음 두 가지 중에서 고릅니다.

| 선택 | 동작 |
| --- | --- |
| CLI 설정 유지 (기본값) | 권한 우회 옵션을 추가하지 않고 해당 CLI의 설정 유지 |
| 이번 실행만 자동승인 | 새 참여자에 한해 아래 옵션 추가 |

| 참여자 | `--auto-approve`가 추가하는 옵션 |
| --- | --- |
| Codex | `--yolo` — 승인 **및 샌드박스** 우회 |
| Claude | `--dangerously-skip-permissions` |
| Antigravity (`agy`) | `--dangerously-skip-permissions`; 대화형 실행에는 `--prompt-interactive` 사용 |

자동승인은 메시지함 명령뿐 아니라 해당 세션의 모든 도구에 적용됩니다. 선택을 전역 설정에 저장하지 않습니다. 이미 열린 참여자는 권한을 유지한 채 다시 묻지 않고 재사용합니다. 기존 참여자의 권한을 바꾸려면 사용자가 재시작을 명시적으로 결정해야 하며, 브리지가 자동으로 재시작하지는 않습니다.

브리지를 직접 실행하면 선택 질문은 나오지 않습니다. 옵션이 없으면 CLI 기본 설정을 유지합니다.

```sh
~/.claude/scripts/crosstalk_bridge.sh ensure-peer codex agy
```

**새 참여자**의 자동승인을 명시적으로 선택했을 때만 다음과 같이 실행합니다.

```sh
~/.claude/scripts/crosstalk_bridge.sh ensure-peer claude codex --auto-approve
~/.claude/scripts/crosstalk_bridge.sh ensure-peer codex claude --auto-approve
~/.claude/scripts/crosstalk_bridge.sh ensure-peer codex agy --auto-approve
```

일치하는 참여자가 이미 있으면 `--auto-approve`는 거부됩니다. 기존 참여자를 재사용하려면 옵션을 빼세요. 시간 초과나 권한 확인창이 나타났다는 이유로 권한을 넓혀 다시 실행하지 않습니다.

## Ghostty 설정 및 문제 해결

### Antigravity (`agy`) 참여

Codex나 Claude에게 agy와 토의해 달라고 요청하거나 다음 명령으로 준비할 수 있습니다.

```sh
~/.claude/scripts/crosstalk_bridge.sh ensure-peer codex agy
crosstalk send agy "Review this approach" --summary "Reviewing the proposed approach"
```

Claude에서는 `ensure-peer claude agy`를 사용합니다. `agy`와 `antigravity`는 같은 참여자를 가리킵니다. 런처는 `agy --prompt-interactive`로 실행하고 호출자의 PATH를 전달합니다. agy에도 앞서 설명한 공통 권한 선택을 적용합니다. 로그인·프로젝트 선택·도구 승인 창이 뜨면 해당 pane에서 완료하세요. 시간이 초과돼도 새 pane을 만들지 말고 기존 pane을 사용하세요.

새 agy pane은 protocol-3/engine-1 준비 절차를 수행합니다. 기존 pane은 지시문 reload와 명시적 handshake가 필요합니다. `receive`의 managed dispatch는 공통 `discussion_instructions`, 일반 mailbox-v2는 `mailbox_instructions`를 따릅니다. `/crosstalk-peer ... RUN_ID=...`는 레거시 처리기로 유지합니다. 새 엔진에서 agy는 peer만 지원하고 caller는 Claude/Codex입니다. v0.12 실기 검증은 아직 대기 중입니다.

### 식별 및 복구

세션 바인딩은 논리 소유권과 물리 pane을 분리합니다. 새 engine에는 protocol 3/engine 1 준비가 필요하며, 기존 protocol-2 바인딩만으로 이를 인정하지 않습니다. Claude/agy는 정확한 TTY probe를 사용할 수 있지만 Codex CLI 세션 ID만으로 pane 주소가 증명되지는 않습니다. `bridge strict-self`는 라벨/cwd fallback을 거부합니다. 사용자가 선택한 대상은 `/crosstalk:setup --surface ghostty:<UUID>`로 준비하고 각 CLI가 자신의 일회용 challenge/bind를 실행해야 합니다. 준비 완료는 `session status`로 확인하며 라벨만으로 판단하지 않습니다.

다른 pane에서 CLI를 resume했다면 의도한 논리 세션에 명시적으로 rebind하고 새 binding generation을 받아야 합니다. 이전 pane이 닫혔다고 작업이 자동 이전되지는 않습니다. 이전 pane이 살아 있거나 repository 문맥이 바뀌었다면 인계를 확인합니다. History를 읽고 중단 claim은 승인된 recover로 재개합니다. 포커스·제목·종류·cwd로 추측하지 않습니다.

Codex는 매 Ghostty protocol 호출에 정확한 현재 `CROSSTALK_SURFACE_ID`와 공유 `CROSSTALK_CONFIG_DIR`를 명시해야 합니다. 이전 pane이 살아 있어도 thread cache만으로 resume 후 주소를 증명할 수 없습니다. restart/resume 후 현재 target을 다시 선택하고 handshake하세요. 이전 대화에서 기억한 주소를 복사하지 마세요. 현재 호출과 handshake 형식은 [readiness](assets/codex-skills/crosstalk/readiness.md)를 참고하세요.

시작 timeout이면 기존 pending pane을 재사용하고 실제 관찰한 로그인/신뢰 확인을 처리합니다. 중복 pane을 열거나 권한을 우회하지 않습니다. unknown pane의 라벨은 후보 정보이며 검증된 protocol/engine handshake가 여전히 필요합니다. Ghostty의 화면 캡처/푸터 기반 준비 확인은 제공하지 않습니다. Cowork와 review는 cmux 전용입니다.

정확한 후보 주소는 다음 명령으로 확인합니다.

```sh
osascript -e 'tell application "Ghostty" to get {id, name, working directory} of every terminal'
crosstalk capabilities --json
crosstalk doctor --offline
crosstalk session status
```

긴 본문은 SQLite에 남고 알림 제출·수신·처리 완료를 구분합니다. 자동 테스트는 격리된 가짜 터미널을 사용하며, v0.12 engine의 실제 검증은 [검증 기록](docs/verification-v0.12.md)에 따로 남깁니다.

## 데모

기존 데모와 대표 이미지는 cmux 작업 화면입니다. 새 Ghostty 연동을 녹화한 자료는 아닙니다.

![Crosstalk cmux demo](docs/demo.gif)

## 명령어

### 기본 명령

| 명령 | 설명 |
| --- | --- |
| `/crosstalk <topic>` | **기본 진입점.** analyze 실행, 누락된 설정 처리, Ghostty에서 Codex 준비를 담당합니다. |
| `/crosstalk` | 주제 없이 호출하면 설치 / 백엔드 / 상대 pane과 다음에 할 한 가지 작업을 점검합니다. |
| `/crosstalk:analyze <topic>` | analyze를 명시적으로 실행합니다. 각 AI가 독립적으로 분석하고 조건에 따라 의견을 주고받은 뒤, 합의하거나 서로 다른 의견을 존중하며 끝냅니다. |
| `/crosstalk:ask <question>` | **가벼운 의견 수집 (v0.7.0+).** 각 AI가 자기 pane에서 한 번 답합니다. 토론, 왕복 대화, 결과 취합은 없습니다. |
| `/crosstalk:resume` | `/crosstalk`이 호출자 터미널을 식별하지 못해 보존한 주제를 재개합니다. |
| `/crosstalk:cowork "claude=A, codex=B, goal=Y"` | **cmux 작업.** 각 AI가 자기 CLI에서 `/goal`을 실행하고 맡은 부분을 병렬로 수행합니다. 기본적으로 worktree로 격리합니다. |
| `/crosstalk:cowork-stop [RUN_ID]` | **cmux 작업.** 진행 중인 공동작업을 중단합니다. 모든 참여자에게 `/goal clear`와 종료 알림을 보냅니다. |
| `/crosstalk:status` | 활성 규칙, 페르소나, pane 상태를 보여 줍니다. |
| `/crosstalk:install` / `/crosstalk:uninstall` | Crosstalk 구성 요소를 설치하거나 제거합니다. |

### Codex 호출자 (실험 단계)

`/crosstalk:install`로 `~/.codex/skills/crosstalk/`를 설치한 뒤 Codex pane에서 실행합니다.

| 명령 | 설명 |
| --- | --- |
| `$crosstalk <topic>` | Codex 호출자의 진입점입니다. Codex가 진행자를 맡아 analyze를 실행합니다. |
| `$crosstalk analyze [--rules <name>] [--persona <name>] <topic>` | Codex에서 analyze를 명시적으로 실행합니다. |
| `$crosstalk ask <question>` | Codex에서 가볍게 의견을 수집합니다 (v0.7.0+). |
| `$crosstalk cowork "claude=A, antigravity=B, goal=Y"` | Codex에서 공동작업을 시작합니다 (cmux 작업). |
| `$crosstalk cowork-stop [RUN_ID]` | Codex에서 진행 중인 공동작업을 중단합니다 (cmux 작업). |
| `$crosstalk resume` | Codex에서 보존된 주제를 재개합니다. |
| `$crosstalk status` | Codex에서 설정과 pane 상태를 확인합니다. |

### 고급 명령

수동 제어나 복구용 명령입니다. 보통은 직접 실행할 필요가 없습니다.

| 명령 | 설명 |
| --- | --- |
| `/crosstalk:analyze --rules <name> <topic>` | 한 번의 분석에 규칙 프리셋을 적용합니다. |
| `/crosstalk:analyze --persona <name> <topic>` | 한 번의 분석에 페르소나 프리셋을 적용합니다. |
| `/crosstalk:launch` | Ghostty에서 다른 CLI를 준비하거나 cmux에서 워크스페이스 참여자를 실행합니다. |
| `/crosstalk:setup` | 이미 열린 터미널 pane에 라벨을 지정합니다 (`--language en\|ko`로 UI 언어도 변경). |
| `/crosstalk:rules` / `/crosstalk:persona` | 프리셋을 전환, 생성, 편집, 삭제합니다. |
| `/crosstalk:review [PR]` | cmux 작업: 진행자가 `gh pr diff`로 PR 리뷰를 이끕니다. |
| `/crosstalk:review --deep [PR]` | cmux 작업: commit을 고정한 detached worktree와 안전한 정리를 사용합니다. |

## 동작 방식: 일반 mailbox-v2 호환 경로

이 절은 일반 thread용이며 discussion-v1 managed 메시지에는 적용하지 않습니다. setup으로 호출자와 참여자의 handshake를 완료합니다. `crosstalk capabilities --json`이 protocol/schema와 실제 메시지함 지시문 경로를 알려줍니다. 라벨만으로 소유권을 정하지 않습니다. `send`는 검증된 논리 세션을 선택하며 종류가 같은 후보가 여러 개라면 `--peer-session`을 명시합니다. 실행 파일이 PATH에 없으면 `~/.claude/scripts/crosstalk`을 사용하세요.

```sh
crosstalk capabilities --json
crosstalk send claude "What do you think of this design?" --summary "Reviewing the design"
crosstalk receive
crosstalk reply <REQUEST_ID> "My analysis..." --lease-token <TOKEN> --verdict none --confidence unknown
```

Claude 호출자는 `codex`를 대상으로 지정합니다. 긴 본문은 `--stdin`을 씁니다. Send는 저장 후 알리고, receive는 queued 메시지 하나를 삽입 순서로 점유해 비공개 token을 반환합니다. Reply는 답변 저장과 요청 완료를 원자적으로 처리합니다. 호출자는 reply를 수신한 뒤 `ack <REPLY_ID> --lease-token <TOKEN> --outcome concluded --result-stdin`으로 비교 결과를 저장하거나, `send <peer> --thread <THREAD_ID> --after-reply <REPLY_ID> --lease-token <TOKEN> --stdin`으로 다음 요청 생성과 reply 완료를 함께 처리합니다.

```text
request: queued -> processing -> completed (reply 저장)
reply:   queued -> processing -> completed (ack 또는 다음 request 저장)
만료 processing -> effective recovery_required -> 명시적으로 승인한 재점유
```

본문 표식은 v2 verdict를 설정하지 않습니다. `--verdict`, `--confidence`로 명시합니다. 상대의 동의는 객관적 정답 증명이 아닙니다. 요청은 10라운드까지입니다. Ask는 답변을 저장하되 콜백·자동 토론을 만들지 않고, 요청된 사후 조회는 observed로 완료합니다. 요약은 미리보기이며 라우팅 식별자가 아닙니다. 가져온 본문과 claim을 하나씩 처리합니다.

### 복구

| 명령 | 용도 |
| --- | --- |
| `doctor --offline` | 터미널 입력이나 수정 없이 설치/DB/복구 상태 조회. |
| `status [ID]`, `history ID` | 메시지를 점유하지 않고 조회. 더 많은 행은 `--limit`/`--offset` 사용. |
| `retry ID` | 저장된 같은 알림만 재전송. 작업을 다시 실행하지 않음. |
| `recover ID` | 중단된 claim을 변경 없이 진단. |
| `recover ID --reclaim --expected-claim-version N --confirm-external-effects` | 사용자 승인 후 같은 메시지를 새 lease로 재점유. |
| `renew ID --lease-token TOKEN` | 유효 claim 연장. 만료 claim을 되살리지 않음. |

`receive ID --replay`는 deprecated입니다. 알림이 failed/unknown이어도 저장된 메시지는 남습니다. 새 요청을 만들지 말고 status로 확인한 같은 ID를 retry하세요. 입력 제출은 AI 수신 확인이 아닙니다. 복구 전 history와 외부 변경을 확인하세요. 기존 프로세스가 계속 실행 중일 수 있습니다. Rebind는 이전 token을 무효화합니다. 완전히 동일한 reply 재제출은 기존 결과를 확인하며 덮어쓰지 않습니다.

데몬·자동 재점유·파일/네트워크 부작용의 exactly-once 보장은 없습니다. DB와 백업은 사용자 전용 권한의 로컬 평문이며 암호화 저장소나 보안 샌드박스가 아닙니다. 양쪽이 같은 `CROSSTALK_CONFIG_DIR`를 사용해야 합니다. [프로토콜](docs/protocol-v2.md), [업그레이드](docs/upgrade-v0.11.md), [복구](docs/recovery.md), [검증](docs/verification-v0.11.md)을 참고하세요.

### 기존 파일 프로토콜

cmux 작업과 기존 `RUN_ID` 대화는 계속 `/tmp/crosstalk/run-*` 아래의 `preambles/`, `rounds/`, `assignments/`, `responses/` 및 완료 `ping`을 사용합니다. 기존 저수준 명령인 `crosstalk_bridge.sh send <surface> <text>`도 유지합니다. 새 메시지함 명령 `crosstalk send <peer> <body>`와는 별개입니다.

## 고급 작업: cmux

공동작업과 PR 리뷰에는 cmux를 사용하세요. 이 작업들은 아직 Ghostty로 이식되지 않았습니다. Antigravity 메시지함 토의는 Ghostty에서도 지원합니다.

PR 리뷰는 `/crosstalk:review <PR>`로 실행합니다. Deep review는 base/head commit이 고정된 소유 detached worktree를 사용하며 원본 checkout/index/stash를 보존합니다. dirty 또는 불확실한 review worktree는 남깁니다. [리뷰 안전성](docs/review-safety.md)을 참고하세요.

### 공동작업

`analyze`는 *의견*을, `cowork`는 *결과물*을 위한 기능입니다. 역할과 목표를 나누면 각 AI가 자기 CLI에서 `/goal` 슬래시 명령을 실행하고 목표를 달성했다고 판단할 때까지 작업합니다.

```text
/crosstalk:cowork "claude=Repository layer, codex=ViewModel layer, goal=mail search feature shipping with passing tests"
```

진행 순서:

1. **역할 해석**: Crosstalk이 역할을 읽고 git worktree로 작업을 격리할지 한 번 묻습니다(권장). 공유 작업 트리를 쓰려면 `--no-worktree`를 사용합니다.
2. **작업 전달**: 각 AI의 담당 범위, `/goal "<goal>"`, 최종 보고 지침을 `assignments/<agent>.md`에 씁니다. cmux에는 `[crosstalk] cowork-task <agent> RUN_ID=...`만 전달합니다.
3. **각 AI가 자체 `/goal` 실행**: 상대 CLI는 목표가 달성됐다고 판단할 때까지 종료를 막습니다. Crosstalk이 그 판단을 다시 심사하지는 않습니다.
4. **시간 제한**: 기본 1시간입니다. 시간이 초과되거나 `/crosstalk:cowork-stop`을 실행하면 브리지가 cmux로 모든 참여자에게 `/goal clear`와 종료 알림을 보냅니다.
5. **결과 취합**: 진행자가 각 AI의 보고서와 worktree 내 git log를 읽고 `cowork-summary.md`를 작성합니다. worktree 처리는 사용자가 `keep`(기본값), `merge`, `drop` 중에서 정합니다.

```text
/tmp/crosstalk/run-<RUN_ID>/
  manifest.json
  responses/
    claude-r01.md          # each peer's work report
    codex-r01.md
  assignments/
    claude.md              # each peer's work prompt
    codex.md
  cowork-summary.md        # moderator's rolled-up summary

/tmp/crosstalk/worktrees/run-<RUN_ID>/
  claude/                  # git worktree on branch cowork/<RUN_ID>-claude
  codex/                   # git worktree on branch cowork/<RUN_ID>-codex
```

> 목표 달성 판단을 각 AI의 `/goal`에 맡기는 이유는 Crosstalk의 역할을 작게 유지하기 위해서입니다. 각 AI가 자기 모델의 신호를 가장 잘 알고, Crosstalk이 별도 검증기를 만들 필요도 없습니다. 시간 제한과 `cowork-stop`만 안전장치로 두며, 완료된 것처럼 보이는지 LLM이 다시 판정하지 않습니다.
>
> MVP 범위: 각 AI는 서로의 진행 상황을 볼 수 없습니다(실시간 교차 확인 없음). 병렬로 작업한 뒤 진행자가 마지막에 결과를 합칩니다. 참여자 간 교차 확인은 향후 계획에 있습니다.

## 규칙과 페르소나 (고급)

선택 기능입니다. 기본 analyze는 페르소나를 지정하지 않고 최소 규칙으로 실행합니다. 토의 방식을 조정하고 싶을 때만 프리셋을 지정하세요.

기본 규칙 프리셋:

| 규칙 | 스타일 |
| --- | --- |
| `default` | 제약과 어조만 지정, 길이와 형식은 각 AI가 선택 |
| `brainstorm` | 짧고 탐색적이며 아이디어를 받아 발전시키는 방식 |
| `debate` | 더 깊이 비판하고 신중하게 합의 |

기본 페르소나 프리셋:

| 페르소나 | 역할 |
| --- | --- |
| `default` | 페르소나 미지정 |
| `senior-junior` | 보수적인 시니어와 진보적인 주니어 |
| `critic-builder` | 비평가와 구현자 |
| `triple-perspective` | 보수주의자, 혁신가, 실용주의자 |

예시:

```text
/crosstalk:analyze --rules debate --persona critic-builder Should we merge this PR?
```

사용자 프리셋 경로입니다. 각 규칙/페르소나 파일은 압축 없이 원문 그대로 preamble에 들어갑니다.

```text
~/.claude/crosstalk/rules/{en,ko}/
~/.claude/crosstalk/personas/{en,ko}/
```

## 제약 사항

- **macOS 전용**: 현재 터미널 백엔드는 macOS가 필요합니다.
- **cmux CLI UI 감지는 바뀔 수 있음**: cmux의 시작 준비 상태와 자동 감지는 CLI 하단 표시 패턴을 사용합니다. 감지에 실패하면 `/crosstalk:setup`으로 pane 라벨을 직접 지정하세요.
- **완전한 샌드박스 없음**: Crosstalk은 로컬 CLI 프로세스를 연결해 작업을 조율하며, 이 프로세스들을 샌드박스로 격리하지 않습니다.
- **기존 파일 방식에는 `bridge ping` 필요**: 완료는 이벤트 기반입니다. 상대가 ping하지 않으면 진행자는 대기합니다. 어느 pane에서든 `bridge ping <RUN_ID> <agent> <round>`를 직접 실행해 대기를 풀 수 있습니다.
- **AI가 전달 지침을 무시할 수 있음**: cmux에서 선택하는 `--transport file/screen` 모드는 이를 프로토콜 오류로 처리하고 재시도/건너뛰기/중단 선택지를 제공합니다.
- **심층 PR 리뷰는 실기 검증 필요**: detached worktree는 Git 메타데이터를 공유하며 보안 샌드박스가 아닙니다. 위험한 정리는 거부합니다.
- **콜백은 CLI 입력 처리에 의존**: v0.12 engine 실기 검증은 아직 완료되지 않았으며, CLI가 작업 중이거나 권한 확인창이 열려 있으면 입력 처리가 지연되거나 막힐 수 있습니다. 상대가 작업을 시작했다고 판단하기 전에 메시지함 수신 상태를 확인하세요. 기존 ping은 앞서 보낸 각 트리거의 수신을 확인하지 않습니다.
- **Antigravity 호출자 미지원**: Antigravity (`agy`)는 참여자로만 사용할 수 있습니다. Claude나 Codex에서 시작해야 합니다.

## 향후 계획

- Ghostty에 고급 cowork/review 작업 지원
- 참여 AI별 모델과 effort 선택
- 전달 진단 개선; 자동 작업 재실행은 보장 범위가 아님
- Antigravity 진행자 모드
- 추가 CLI 어댑터
- tmux 및 zellij 지원
- 문제 해결 문서 보강
- 시작 감지 안정성 개선
- 실제 PR 리뷰 공개 예시

## 기여

이슈와 PR을 환영합니다. 다음 작업부터 기여할 수 있습니다.

- CLI 하단 감지 패턴 갱신
- 규칙 또는 페르소나 프리셋 추가
- 설치 및 문제 해결 문서 개선
- 여러 Codex/Antigravity/Claude CLI 버전에서 테스트
- tmux 또는 zellij 어댑터 탐색

## 라이선스

Crosstalk은 [MIT 라이선스](LICENSE)로 배포합니다.
