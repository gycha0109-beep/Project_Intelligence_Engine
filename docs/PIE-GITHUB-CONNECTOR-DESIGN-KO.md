# PIE v0.3 GitHub PR Integration Boundary 설계

## 1. 목적

PIE v0.2의 `analyze-change`는 변경 파일 목록을 외부에서 준비해야 했다. v0.3의 목적은 사용자가 PR 번호 또는 URL 하나를 제공하면 GitHub 증거 수집부터 영향 분석까지 연결하는 것이다.

이번 경계는 GitHub의 production 상태를 변경하지 않는다. PR checkout, merge, comment, review submission, workflow rerun, 배포는 수행하지 않는다.

## 2. 사용자 흐름

```text
대상 저장소 폴더
  ↓
pie init-project --preset <project>
  ↓
pie github-doctor
  ↓
pie analyze-pr <PR 번호 또는 URL>
  ↓
GitHub source evidence + diff + impact report
```

PIE 소스 ZIP과 분석 대상 저장소는 분리한다. PIE는 설치되는 도구이며 `.review/`와 `.pie/`는 대상 저장소에 생성된다.

## 3. 구성요소

```text
PR Target Parser
  ├─ positive PR number
  └─ https://HOST/OWNER/REPO/pull/NUMBER
        ↓
GitHub CLI Preflight
  ├─ executable detection
  ├─ host authentication
  └─ current repository resolution
        ↓
Read-only Collector
  ├─ gh pr view --json
  ├─ gh pr diff --patch
  └─ gh api --paginate --slurp
        ↓
Source Normalizer
  ├─ stable field names
  ├─ compact actors/comments/reviews
  ├─ warnings
  └─ source_sha256
        ↓
Repository Binding
  ├─ local repository match
  ├─ local HEAD capture
  └─ PR head mismatch warning
        ↓
Project Graph + Approved Rules
        ↓
Impact Analysis
        ↓
REPORT.md / impact.json / github-source.json / pull-request.diff
```

## 4. 인증 설계

PIE는 PAT 입력 필드나 토큰 파일을 만들지 않는다. GitHub CLI가 관리하는 기존 인증 세션을 사용한다.

- 인증 점검: `gh auth status --active --hostname HOST`
- 토큰 출력 옵션 사용 금지
- 환경 변수와 표준 출력에 토큰 기록 금지
- 모든 명령은 argument vector로 실행하며 `shell=True`를 사용하지 않음

## 5. 수집 범위

### 필수

- PR 번호, 제목, 본문, URL, 상태
- base/head branch 및 SHA
- 변경 파일, additions/deletions
- commit 목록
- label, review decision, merge state
- CI status rollup

### 토론·리뷰

- PR issue comments
- review records
- inline review comments

세 종류는 REST endpoint를 paginated read-only 방식으로 수집한다. 일부 endpoint가 실패하면 기존 `gh pr view` 결과를 유지하고 경고를 기록한다.

### diff

`gh pr diff --patch`가 실패해도 PR metadata와 changed-file 분석은 유지한다. diff 부재는 명시적인 warning이며 runtime correctness를 증명하지 않는다.

## 6. 신뢰 경계

### 확인된 증거

- GitHub CLI가 반환한 PR metadata
- collected diff의 SHA-256
- source evidence 전체의 SHA-256
- 로컬 graph hash

### 제한된 추론

- changed files와 local graph를 연결한 구조 영향
- configured Review Pack 추천
- approved project rule 영향

### 보장하지 않는 것

- PR head의 전체 source tree가 현재 local checkout과 동일함
- CI 성공이 제품 요구사항을 만족함
- GitHub review discussion이 의사결정의 전부임
- merge conflict 또는 runtime defect 부재

## 7. 실패 정책

| 상황 | 처리 |
|---|---|
| `gh` 미설치 | 중단, 설치 필요 오류 |
| 인증 실패 | 중단, `gh auth login` 안내 |
| PR 번호인데 repository 미확정 | 중단, `--repo` 또는 올바른 repo 폴더 요구 |
| PR URL과 `--repo` 불일치 | 중단 |
| local repository와 PR repository 불일치 | 기본 중단 |
| PR response 번호/repository 불일치 | 중단 |
| diff 실패 | warning 후 metadata 분석 계속 |
| discussion pagination 실패 | warning 후 가능한 metadata 유지 |
| local HEAD와 PR head 불일치 | warning 후 분석 계속 |
| existing `.review` files | 기본 skip, `--force`에서만 overwrite |

## 8. 산출물

`pie analyze-pr` 기본 출력:

```text
.pie/pr-N/
├─ github-source.json
├─ pull-request.diff
├─ impact.json
└─ REPORT.md
```

`github-source.json`의 `source_sha256`은 해당 필드를 제외한 전체 canonical JSON을 해시한다. `validate-github-source`가 구조와 해시를 다시 검증한다.
