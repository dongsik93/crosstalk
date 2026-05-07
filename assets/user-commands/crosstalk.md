---
description: Crosstalk 단독 명령 — 인자가 있으면 토론 주제로 사용해 debate 시작, 없으면 사용 가능 명령 안내. /crosstalk:install 으로 활성화됨.
allowed-tools: Bash, AskUserQuestion
argument-hint: <토론 주제>
---

# /crosstalk (단독)

`/crosstalk:install` 이 사용자 홈에 설치한 단독 명령. `/crosstalk 주제` 형태로 콜론 없이 호출 가능.

## 동작

### 인자 비어있을 때
다음과 같이 사용법 안내:

```
🗣️ Crosstalk — 다중 AI 토론

기본 사용:
  /crosstalk <주제>                 이 단축 명령 (debate 자동)
  /crosstalk:debate <주제>          명시적 일반 토론
  /crosstalk:debate --rules brainstorm <주제>      룰 일회성
  /crosstalk:debate --persona senior-junior <주제> 페르소나 일회성

PR 리뷰:
  /crosstalk:review [PR번호]        PR 리뷰 토론 (빠른 모드)
  /crosstalk:review --deep [PR번호] PR 리뷰 토론 (깊은 모드)

토론 룰/페르소나:
  /crosstalk:status                 현재 active 셋업 + 사용 가능 목록
  /crosstalk:rules                  룰 전환/생성/편집
  /crosstalk:persona                페르소나 전환/생성/편집

환경:
  /crosstalk:setup                  cmux 라벨링
  /crosstalk:launch                 cmux 자동 실행 + 셋업
  /crosstalk:install                최초 컴포넌트 설치
  /crosstalk:uninstall              컴포넌트 제거

자세한 안내는 https://github.com/dongsik93/crosstalk 참고.
```

### 인자가 있을 때
`$ARGUMENTS` 를 토론 주제로 사용해 `/crosstalk:debate` 와 동일하게 동작한다.

`/crosstalk:debate` 본문(플러그인의 `commands/debate.md`)을 그대로 따라 실행하되, 주제는 `$ARGUMENTS`.

## 주의사항

- 이 파일은 `/crosstalk:install` 이 사용자 홈(`~/.claude/commands/`)에 복사한 사용자 레벨 슬래시 커맨드.
- 플러그인 본체와는 별개로 동작 — `/crosstalk:uninstall` 또는 수동 삭제 시 `/crosstalk` 단독 호출은 비활성화.
- 플러그인 자체 명령(`/crosstalk:debate` 등)은 그대로 동작.
