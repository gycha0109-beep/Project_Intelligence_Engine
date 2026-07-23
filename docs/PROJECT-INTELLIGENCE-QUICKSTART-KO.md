# Project Intelligence Engine v0.2 빠른 시작

## 설치

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install .
pie version
```

## 프로젝트 온보딩

```powershell
Copy-Item -Recurse bootstrap\.review <프로젝트>\.review
```

수정 대상:

- `.review/project.yml`: 저장소 범위, 기술 Stack, Review Pack
- `.review/intelligence/config.yml`: 프로젝트 component와 path pattern
- `.review/intelligence/approved-rules.yml`: 실제 승인된 규칙만 기록

## 그래프 생성

```powershell
pie validate-profile .review\project.yml
pie validate-intelligence-config .review\intelligence\config.yml
pie index-project .review\project.yml `
  --config .review\intelligence\config.yml `
  --output .review\intelligence\project-graph.json
pie validate-graph .review\intelligence\project-graph.json
```

## PR 변경 분석

```powershell
git diff --name-only origin/main...HEAD | Out-File -Encoding utf8 changed-files.txt
pie analyze-change .review\project.yml `
  --graph .review\intelligence\project-graph.json `
  --approved-rules .review\intelligence\approved-rules.yml `
  --files changed-files.txt `
  --change-id PR-123 `
  --output impact.json `
  --markdown-output impact.md
```

결과의 핵심 구역:

- `direct.files_in_graph`
- `direct.files_missing_from_graph`
- `impact.dependent_files`
- `impact.direct_dependencies`
- `impact.matched_rules`
- `review.selected_packs`
- `review.unconfigured_rule_packs`
- `review.required_tests`
- `evidence[].classification`

## 병렬 PR 비교

각 PR의 직접 변경, 영향 파일, component를 `active-changes.yml`에 모은 뒤 실행합니다.

```powershell
pie compare-changes --input active-changes.yml --output comparison.json --markdown-output comparison.md
```

`none`은 독립성의 증명이 아닙니다. 제공된 증거에서 겹침을 찾지 못했다는 뜻입니다.

## 규칙 후보 발견

```powershell
pie discover-rule-candidates `
  --history change-history.yml `
  --config .review\intelligence\config.yml `
  --min-samples 3 `
  --min-confidence 0.75 `
  --output .review\intelligence\candidate-rules.yml
```

후보는 자동 적용되지 않습니다. 승인 시에만 `approved-rules.yml`로 이동합니다.

```powershell
pie approve-rule `
  --candidates .review\intelligence\candidate-rules.yml `
  --approved .review\intelligence\approved-rules.yml `
  --rule-id LC_0123456789 `
  --approved-by maintainer
```

## 운영 원칙

- CI 결과와 영향 추론을 분리합니다.
- 구조 그래프가 있다고 런타임 영향이 증명되는 것은 아닙니다.
- 규칙 후보의 confidence는 공동 변경 빈도이지 인과 확률이 아닙니다.
- 자동 차단은 기존 Universal Review System의 승인된 Finding·Gate 계약을 통해서만 수행합니다.
