# Crosstalk

[English](README.md) | [한국어](README.ko.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Version](https://img.shields.io/badge/version-0.10.0-blue)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-plugin-black)

Ghostty에서 Claude와 Codex를 나란히 띄워 토의하세요. 어느 CLI에서든 질문하면 Crosstalk이 상대 AI의 pane을 재사용하거나 Ghostty 화면을 분할해 실행하고, 질문과 답변을 주고받습니다. tmux는 필요 없습니다.

![Crosstalk hero](docs/hero.png)

## 소개

Crosstalk은 기존 대화형 AI CLI를 연결합니다. Codex에서는 `$crosstalk <topic>`, Claude Code에서는 `/crosstalk <topic>`으로 시작합니다. 각 AI가 독립적으로 분석한 뒤 호출자가 답변을 비교합니다. 합의에 이르거나 서로 다른 의견을 존중하며 마무리하고, 억지로 의견을 맞추지는 않습니다.

**Claude ↔ Codex 토의는 Ghostty로 시작하는 것을 권장합니다.** 고급 작업에는 기존 cmux 백엔드도 쓸 수 있습니다. 지원 범위는 다음과 같습니다.

| 기능 | macOS의 Ghostty | cmux |
| --- | --- | --- |
| Claude ↔ Codex 분석 및 콜백 | 지원, 로컬에서 양방향 전달 검증 | 지원, Codex 호출자는 실험 단계 |
| 빠른 의견 수집 (`ask`) | 지원 | 지원 |
| 상대 pane 준비 | 같은 탭에서 자체 분할 또는 재사용 | `:launch`로 워크스페이스 분할 |
| Antigravity 참여 | 미지원 | 지원 |
| 공동작업 및 PR 리뷰 | 아직 미이식 | 사용 가능, 심층 리뷰는 실험 단계 |
| 화면 캡처 / 화면 기반 전달 | Ghostty 1.3 AppleScript API에서 제공하지 않음 | 사용 가능 |

실제 점검 내용과 한계는 [Ghostty 검증 기록](docs/ghostty-verification.md)을 참고하세요. 이 소스에는 Ghostty 연동이 포함되어 있습니다. 마켓플레이스에서 예전 버전을 설치했다면 빠른 시작을 따라 하기 전에 업데이트해야 합니다.

## 주요 기능

- **눈으로 보는 토의**: 어느 CLI에서 시작하든 이웃한 Ghostty pane에서 Claude와 Codex의 작업을 볼 수 있습니다.
- **기존 CLI 계정 사용**: 별도의 모델 API 연동을 추가하지 않습니다.
- **상대 AI 자동 준비**: 같은 탭에 라벨이 지정된 상대 pane이 없으면 현재 디렉터리에서 다른 CLI를 실행합니다. 시작 확인을 받은 뒤 작업을 보냅니다.
- **독립적인 답변**: 각 AI에게 사용자의 원래 주제를 전달합니다.
- **영속 메시지함**: Ghostty의 요청과 답변을 SQLite에 저장합니다. `send`, `receive`, `reply`가 ID, 수신 상태, 답변 알림을 관리하므로 AI가 메시지별 MD 파일이나 ping 명령을 다룰 필요가 없습니다.
- **명시적인 판정**: 브리지가 `[AGREE]`, `[RESPECT_DISAGREE]` 표식을 읽어 다음 라운드 진행에 사용합니다.
- **빠른 의견 수집**: `ask`는 콜백이나 결과 취합 없이 각 AI의 pane에서 답변합니다.
- **cmux 고급 작업**: git worktree 공동작업, PR 리뷰, Antigravity 참여는 cmux에서 계속 사용할 수 있습니다.

## 요구 사항

| 도구 | 용도 | 참고 |
| --- | --- | --- |
| macOS | 두 터미널 백엔드 모두 | 터미널 앱이 지원하는 OS 버전 사용 |
| Ghostty 1.3+ | 자체 Claude ↔ Codex 토의 | macOS AppleScript 지원, cmux나 tmux 불필요 |
| Claude Code 및 Codex CLI | Ghostty 토의 | 두 CLI 모두 설치 및 인증 필요 |
| jq | 브리지 및 설정 | 필수 |
| sqlite3가 포함된 Python 3 | Ghostty 메시지함 | 표준 라이브러리만 사용, pip 패키지나 서버 불필요 |
| Node.js / npm | npm으로 배포되는 AI CLI 설치 | 별도의 Crosstalk 런타임은 아님 |
| cmux 1.3+ | 대체 백엔드 및 고급 작업 | Ghostty 토의에는 선택 사항 |
| GitHub CLI (`gh`) | PR 리뷰 | 선택 사항 |

Antigravity (`agy`)는 별도로 다운로드하며, 현재 cmux에서만 참여할 수 있습니다.

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
/plugin install crosstalk@dongsik93/crosstalk
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

```text
Ghostty tab
├── Codex  ← questions and responses →  Claude
```

독립적인 의견을 빠르게 받으려면 `$crosstalk ask <question>` 또는 `/crosstalk:ask <question>`을 사용하세요. 각 AI가 자기 pane에서 답하며, 결과를 하나로 취합하지 않습니다.

상대 AI를 실행하지 않고 상태만 보려면 주제 없이 `$crosstalk` 또는 `/crosstalk`을 호출하세요. 준비 상태 점검에서 백엔드, 호출자, 상대 pane을 보여 줍니다. 호출자를 식별하지 못하면 오류를 알리고 주제를 보존해 `$crosstalk resume` 또는 `/crosstalk:resume`으로 재개할 수 있게 합니다.

### 모델과 추론 effort

현재 Crosstalk은 모델이나 effort를 지정하지 않습니다. 재사용한 pane은 기존 세션 설정을 유지하고, 새 CLI는 자체 기본값을 사용합니다. Codex 설정을 Claude에 복사하거나 그 반대로 전달하지 않습니다. Crosstalk 전용 모델/effort 재정의 옵션은 아직 없습니다.

## Ghostty 설정 및 문제 해결

시작 대기 시간이 초과되면 기존 상대 pane에서 로그인이나 신뢰 확인을 마친 뒤 다시 시도하세요. Crosstalk은 시작 대기 상태를 기록하므로 재시도할 때 중복 pane을 만들지 않습니다.

브리지가 기존 CLI에 처음 연결할 때는 Ghostty 터미널 중 작업 디렉터리가 같은 터미널이 하나뿐이어야 합니다. 연결 후에는 호출자 프로세스의 식별 정보에 연결을 고정합니다. 디렉터리가 겹치면 포커스된 터미널을 추측하지 않고 실패합니다. 이 경우 브리지 호출에 `CROSSTALK_SURFACE_ID=ghostty:<UUID>`를 명시하세요. 새로 실행한 상대 CLI는 정확한 ID를 상속받습니다. ID와 디렉터리는 다음 명령으로 확인합니다.

```sh
osascript -e 'tell application "Ghostty" to get {id, name, working directory} of every terminal'
```

수동 브리지 명령:

```sh
~/.claude/scripts/crosstalk_bridge.sh self
~/.claude/scripts/crosstalk_bridge.sh ensure-peer codex claude
# From a Claude caller: ensure-peer claude codex
```

이번 Ghostty 연동은 Claude/Codex의 analyze, ask, 콜백을 지원합니다. 고급 cowork/review 작업은 아직 cmux 중심입니다. Ghostty 1.3은 AppleScript로 화면 내용을 제공하지 않으므로 캡처, 화면 기반 전달, 하단 표시를 통한 준비 상태 확인을 사용할 수 없습니다. 기존 pane의 AI 종류를 모르면 `bridge label <ID> claude|codex|shell`로 명시해야 합니다.

긴 메시지와 답변은 로컬 SQLite 메시지함에 두고, Ghostty에는 메시지 ID가 담긴 짧은 알림만 보냅니다. 수신 확인은 `receive`만 처리합니다. 데몬, 소켓 서버, 클립보드는 사용하지 않습니다. macOS가 Ghostty 제어를 위한 자동화 권한을 요청할 수 있습니다. 호환성을 위해 기존 파일/ping 방식의 실행도 계속 지원합니다.

격리된 터미널 및 메시지함 검사는 `python3 tests/test_bridge.py`와 `python3 tests/test_mailbox.py`로 실행합니다.

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
| `/crosstalk:review --deep [PR]` | cmux 작업: checkout/stash/restore를 사용하는 실험적 심층 PR 리뷰입니다. |

## 동작 방식: Ghostty 메시지함

AI가 사용하는 도구는 어느 CLI에서나 실행할 수 있는 일반 셸 명령입니다.

```sh
crosstalk send claude "What do you think of this design?"
crosstalk receive
crosstalk reply <MESSAGE_ID> "My analysis..."
```

Claude가 호출자라면 수신 대상을 `codex`로 지정합니다. 준비 상태 점검에서 먼저 `bridge ensure-peer`로 상대를 준비합니다. `send`를 실행하려면 현재 탭에 라벨이 지정된 상대 pane이 정확히 하나 있어야 합니다. `~/.local/bin`이 PATH에 없으면 `~/.claude/scripts/crosstalk`을 직접 사용하세요. 긴 본문은 명령 인자 대신 `--stdin`으로 파이프 입력할 수 있습니다.

1. **Send**: 본문을 `~/.claude/crosstalk/mailbox.sqlite3`에 커밋한 뒤 상대의 정확한 Ghostty 터미널 ID로 알립니다.
2. **Receive**: 대기 중인 메시지 하나를 원자적으로 수신 처리하고 본문을 JSON으로 반환합니다. 중복 알림에는 `actionable: false`를 반환하므로 AI에게 같은 요청을 두 번 처리하도록 지시하지 않습니다.
3. **Reply**: 답변을 저장해 요청에 연결하고, 요청을 답변 완료로 표시한 뒤 원래 호출자에게 알립니다. AI가 응답 파일을 쓰거나 ping을 호출할 필요는 없습니다.
4. **Compare**: 호출자는 답변을 읽고 자신의 의견과 비교해 요약하거나, `send <peer> --thread <ROOT_ID>`로 후속 질문을 보냅니다. 도구가 스레드당 요청/답변을 최대 10라운드로 제한합니다.

```text
request: pending → received → replied
                              └─ reply message: pending → received
```

도구는 답변에서 명시적인 판정 표식을 추출합니다. 표식은 상대의 입장을 나타냅니다. 호출자는 두 의견을 비교한 뒤에 합의 여부를 판단해야 합니다. `send --mode ask`에서는 답변을 저장하고 상대 pane에 출력하지만 호출자에게 답변 알림을 보내지 않습니다.

### 복구

| 명령 | 용도 |
| --- | --- |
| `status [ID]` | 메시지를 소비하지 않고 수신/답변 상태와 알림 오류 확인 |
| `history ID` | 스레드의 모든 메시지 읽기 |
| `retry ID` | 메시지를 새로 만들지 않고 대기 중인 알림 재전송 |
| `receive ID --replay` | 중단 전에 수신한 메시지를 명시적으로 재개 |
| `send ... --id <KEY>` | 동일한 요청에 ID 재사용, 내용이 다르면 거부 |

알림 전송에 실패하면 도구는 저장된 메시지 ID를 반환하고 0이 아닌 종료 코드로 끝납니다. 새 요청을 만들지 말고 해당 ID로 `retry`를 실행하세요. 같은 본문으로 `reply`를 반복하면 기존 답변을 반환하며, 다른 본문으로 덮어쓸 수 없습니다.

데이터베이스는 프로세스가 재시작되어도 남습니다. 로컬 사용자 전용이지만 그 사용자의 AI 프로세스를 샌드박스로 격리하지는 않습니다. 기본 설정 경로를 바꾼다면 양쪽이 같은 `CROSSTALK_CONFIG_DIR`를 사용해야 합니다. 터미널 ID가 전달 주소이므로 pane을 닫으면 수동으로 복구해야 합니다. 다른 pane으로 메시지를 임의로 돌려보내지 않습니다. CLI가 작업 중이거나 권한 확인창이 열려 있으면 알림 입력이 막힐 수 있습니다. 무인 재시도 데몬은 없습니다.

### 기존 파일 프로토콜

cmux 작업과 기존 `RUN_ID` 대화는 계속 `/tmp/crosstalk/run-*` 아래의 `preambles/`, `rounds/`, `assignments/`, `responses/` 및 완료 `ping`을 사용합니다. 기존 저수준 명령인 `crosstalk_bridge.sh send <surface> <text>`도 유지합니다. 새 메시지함 명령 `crosstalk send <peer> <body>`와는 별개입니다.

## 고급 작업: cmux

공동작업, PR 리뷰, Antigravity 참여에는 cmux를 사용하세요. 이 작업들은 아직 Ghostty로 이식되지 않았습니다.

PR 리뷰는 `/crosstalk:review <PR>`로 실행합니다. 실험 기능인 `--deep`은 PR 브랜치를 체크아웃하고 리뷰 후 이전 브랜치 복원을 시도합니다.

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
- **심층 PR 리뷰는 실험 단계**: checkout/stash/restore로 현재 git worktree를 변경합니다.
- **콜백은 CLI 입력 처리에 의존**: Ghostty 양방향 전달은 로컬에서 확인했지만, CLI가 작업 중이거나 권한 확인창이 열려 있으면 입력 처리가 지연되거나 막힐 수 있습니다. 상대가 작업을 시작했다고 판단하기 전에 메시지함 수신 상태를 확인하세요. 기존 ping은 앞서 보낸 각 트리거의 수신을 확인하지 않습니다.
- **Antigravity 호출자 미지원**: Antigravity (`agy`)는 참여자로만 사용할 수 있습니다. Claude나 Codex에서 시작해야 합니다.

## 향후 계획

- Ghostty에 고급 cowork/review 작업 지원
- 참여 AI별 모델과 effort 선택
- 무인 전달 복구 및 pane 종료 후 명시적 재연결
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
