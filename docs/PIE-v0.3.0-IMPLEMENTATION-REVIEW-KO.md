# PIE v0.3.0 구현·독립 리뷰 보고

## 1. 판정

**PASS — GitHub PR Integration Boundary 구현 완료**

- 기존 v0.2.0 기준선 유지
- GitHub read-only intake 구현
- PR URL/번호 직접 입력 구현
- 프로젝트 초기화 및 사용 설명서 구현
- 전체 회귀 테스트 79/79 PASS

## 2. 주요 변경 파일

### 생성

- `src/review_system/github_connector.py`
- `src/review_system/project_init.py`
- `tests/test_github_connector.py`
- `tests/test_project_init_and_pr_cli.py`
- `docs/PIE-GITHUB-CONNECTOR-DESIGN-KO.md`
- `docs/PIE-GITHUB-CONNECTOR-USAGE-KO.md`
- preset별 intelligence config 3개
- bootstrap intelligence README

### 수정

- `src/review_system/cli.py`
- `src/review_system/intelligence_report.py`
- `src/review_system/version.py`
- `scripts/sync_package_assets.py`
- `README.md`
- `CHANGELOG.md`
- `VERSION`
- `pyproject.toml`

## 3. 추가 CLI

```text
pie init-project
pie github-doctor
pie analyze-pr
pie validate-github-source
```

## 4. 독립 리뷰 발견·보완

### PIE-GH-R1 — 사용자 실행 경로 부재

- 문제: v0.2는 changed-files 파일을 사용자가 직접 만들어야 했음.
- 보완: PR URL/번호를 직접 받는 `analyze-pr` 구현.
- 상태: CLOSED.

### PIE-GH-R2 — 토큰 취급 위험

- 문제: 직접 GitHub API token 설정을 요구하면 저장·노출 위험이 생김.
- 보완: GitHub CLI 인증 세션만 재사용하고 토큰 출력·저장 기능 미구현.
- 상태: CLOSED.

### PIE-GH-R3 — command injection 위험

- 문제: PR URL을 shell 문자열에 결합하면 임의 명령 실행 가능.
- 보완: strict target parser, HTTPS URL 형식 제한, argument-vector subprocess, `shell=True` 금지.
- 검증: shell metacharacter literal 전달 테스트.
- 상태: CLOSED.

### PIE-GH-R4 — 다른 저장소 graph 오분석

- 문제: Bejewely PR을 BuildMap 폴더의 graph로 분석할 수 있음.
- 보완: local repository와 PR repository를 비교하고 기본 fail-closed.
- 상태: CLOSED.

### PIE-GH-R5 — diff 크기 제한으로 전체 분석 실패

- 문제: GitHub가 diff를 반환하지 못하면 metadata까지 버려질 수 있음.
- 보완: diff를 보조 증거로 분리하고 실패 시 warning 후 changed-file 분석 유지.
- 상태: CLOSED.

### PIE-GH-R6 — local checkout과 PR head 혼동

- 문제: 현재 graph가 PR head source를 반영한다고 오인할 수 있음.
- 보완: local HEAD와 PR head SHA 비교 및 명시적 warning.
- 상태: CLOSED.

### PIE-GH-R7 — bootstrap 덮어쓰기

- 문제: 기존 `.review` project rules를 초기화 과정에서 잃을 수 있음.
- 보완: 기본 skip, `--force`에서만 overwrite.
- 상태: CLOSED.

### PIE-GH-R8 — review 정보 불완전

- 문제: `gh pr view`의 review summary만으로 inline review comment가 누락될 수 있음.
- 보완: issue comments, reviews, inline review comments를 read-only paginated API로 별도 수집.
- 상태: CLOSED.

### PIE-GH-R9 — source 증거 변조 탐지 부재

- 문제: 수집 후 JSON이 수정되어도 impact와 source 관계를 확인할 방법이 없음.
- 보완: `source_sha256`, impact의 `source_evidence_sha256`, `validate-github-source` 구현.
- 상태: CLOSED.

### PIE-GH-R10 — GitHub 응답 target 혼선

- 문제: 예상하지 않은 PR 번호 또는 repository 응답을 수용할 수 있음.
- 보완: requested PR number와 response URL/repository 재검증.
- 상태: CLOSED.

## 5. 검증

```text
python -m compileall -q src tests
PYTHONPATH=src python -m unittest discover -s tests -v
```

결과:

```text
Ran 79 tests
OK
```

패키지 검증:

```text
wheel asset inspection: PASS
clean installed CLI version: 0.3.0
installed init-project: PASS
installed analyze-pr smoke: PASS
installed validate-github-source: PASS
```

검증 범위:

- 기존 URS/PIE 67개 회귀
- PR target parsing
- repository parsing
- authentication failure
- diff failure fallback
- inline review comment pagination normalization
- shell metacharacter literal handling
- source hash tamper detection
- non-destructive bootstrap
- local/remote repository mismatch block
- PR intake → graph → impact → report end-to-end

## 6. 남은 제한

- 실제 GitHub 인증이 필요한 live smoke는 패키지 사용자의 GitHub 환경에서 수행해야 한다.
- local graph는 자동으로 PR branch를 checkout하지 않는다. 이는 working tree를 임의 변경하지 않기 위한 의도적 제한이다.
- GitHub Actions 재실행, PR comment 작성, merge 등 write action은 범위 밖이다.
- review comment의 의미를 자동으로 project rule로 승인하지 않는다.

## 7. 다음 검증

Bejewely 저장소에서 최근 PR 하나를 실행하고 다음을 대조한다.

1. GitHub changed files와 `github-source.json`
2. 실제 리뷰 지적과 selected Review Packs
3. 누락된 영향 파일
4. 과도하게 추천된 영향 파일
5. BuildMap Decision Timeline에 연결할 source identifier 형태
