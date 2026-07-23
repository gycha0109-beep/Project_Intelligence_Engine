# Universal Review System v0.1.1 빠른 시작

## 1. 역할

이 자산은 결함을 자동으로 모두 찾는 분석기가 아닙니다. 다음 검토 통제 기능을 프로젝트마다 동일하게 적용합니다.

- Stack Profile과 프로젝트 설정 병합
- Review Pack 선택 및 버전 잠금
- Finding·Evidence 계약 검증
- Explorer → Challenger → Verifier 역할 분리
- 보호 경로 SHA-256 기준선 검증
- Finding 기반 Gate metric 자동 집계
- 실행 산출물 동기화·검증·보존

## 2. 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install .
```

## 3. 프로젝트 온보딩

```bash
cp -R bootstrap/.review <target-project>/.review
```

`.review/project.yml`에서 다음을 수정합니다.

1. 프로젝트 ID와 기준 브랜치
2. `inherits` 기술 Stack
3. 포함·제외 범위
4. 보호 경로
5. baseline/integration/migration replay 명령
6. 적용 Review Pack
7. Gate blocker 심각도
8. production·hosted DB·외부 네트워크 제약

Stack 기본 Pack을 제외하려면 다음처럼 지정합니다.

```yaml
review:
  packs:
    - domain.recommendation
  exclude_packs:
    - application.authentication
```

프로젝트 전용 Stack은 `.review/stacks/<stack-id>.yml`에 둘 수 있습니다.

## 4. 프로파일 해석 및 검증

```bash
urs validate-profile <target-project>/.review/project.yml
urs resolve-profile <target-project>/.review/project.yml \
  --output <target-project>/.review/project.resolved.yml
```

검증은 원본이 아니라 Stack 상속이 적용된 **effective profile**을 대상으로 수행됩니다.

## 5. 실행 디렉터리 생성

```bash
urs init-run <target-project>/.review/project.yml \
  --mode full \
  --snapshot-protected \
  --output <target-project>/docs/reviews/runs/2026-07-19-full-review
```

주요 생성 파일:

```text
run.json
project-profile.source.yml
project-profile.resolved.yml
packs.lock.json
protected-baseline.json          # 보호 경로가 있고 옵션을 사용한 경우
candidate-findings.json
findings.json
rejected-findings.json
challenge-log.md
verification-log.md
initial-manifest.sha256
```

## 6. 변경 기반 Pack 선택

```bash
git diff --name-only <baseline>...HEAD > changed-files.txt
urs select-packs <target-project>/.review/project.yml \
  --files changed-files.txt \
  --json
```

이 결과는 검토 범위를 줄이기 위한 라우팅 보조 자료입니다. 호출 그래프 기반 영향 분석을 대신하지 않습니다.

## 7. Finding 상태 계약

```text
HYPOTHESIS → SUPPORTED → CONFIRMED → FIXED → RESOLVED/CLOSED
                         └────────── E5 검증 필요 ──────────┘
```

- `SUPPORTED`: E2 이상
- `CONFIRMED`: E3 이상 + reproduction
- `FIXED`: 수정됐지만 E5 재검증 전인 중간 상태
- `RESOLVED`: E5 증거 필요
- `ACCEPTED`: P1 이하에서 owner·reason·review_by 필요
- P0는 residual risk로 수용할 수 없음

```bash
urs validate-findings <run-directory>/findings.json
```

## 8. Finding 병합

```bash
urs merge-findings explorer.json verifier.json \
  --output findings.json \
  --conflicts-output merge-conflicts.json
```

`findings.json`에는 배열만 저장되므로 후속 `validate-findings`와 `sync-run`에 바로 사용할 수 있습니다.

## 9. Run 동기화와 Gate

```bash
urs sync-run <run-directory>
urs calculate-gate-dir <run-directory>
```

`sync-run`은 `findings.json`을 `run.json`에 반영하고 blocker·accepted risk metric을 다시 계산합니다.

`calculate-gate-dir`은 다음을 함께 수행합니다.

- Finding 동기화
- 보호 기준선 재검증
- Gate 계산
- `gate-result.json` 생성
- `final-gate.md` 갱신

## 10. 검증 및 보존

```bash
urs validate-run-dir <run-directory> --require-gate
urs archive-run <run-directory> --output <archive-path>.zip
```

아카이브 전에 Finding 동기화, resolved profile, Pack lock, Gate 결과, Gate policy hash, 보호 기준선 검증이 모두 최신인지 확인합니다. 하나라도 어긋나면 실패합니다. ZIP에는 최종 `manifest.sha256`가 포함됩니다.

```bash
urs verify-manifest <run-directory>
```

## 11. 현재 자동화 경계

v0.1.1은 다음을 아직 자동 수행하지 않습니다.

- LLM에게 저장소 파일 자동 분배
- 검토 명령의 격리 실행과 로그 캡처
- 호출 그래프 기반 영향 분석
- GitHub PR 코멘트 및 merge gate 게시
- Review Benchmark 탐지율·오탐률 측정

현재 버전은 이러한 기능을 올릴 수 있는 **검토 통제 기반선**입니다.
