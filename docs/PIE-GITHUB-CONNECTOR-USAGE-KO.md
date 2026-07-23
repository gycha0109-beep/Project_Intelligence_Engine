# PIE v0.3 GitHub PR 분석 사용 설명서

## 결론부터

**PIE ZIP을 풀고 그 안에 PR 주소를 붙여 넣는 방식이 아니다.**

1. PIE를 설치한다.
2. 분석할 GitHub 저장소의 로컬 폴더로 이동한다.
3. 그 폴더에서 `pie analyze-pr <PR URL>`을 실행한다.

## Windows 기준 정확한 절차

### 1. PIE 설치

Wheel 파일과 같은 폴더에서:

```powershell
py -m pip install .\project_intelligence_engine-0.3.0-py3-none-any.whl
pie version
```

소스 ZIP만 있는 경우 압축을 푼 뒤:

```powershell
cd D:\Tools\project-intelligence-engine-v0.3.0
py -m pip install .
pie version
```

### 2. GitHub CLI 확인 및 로그인

```powershell
gh --version
gh auth login
```

로그인은 최초 1회이며, PIE 설정 파일에 토큰을 넣지 않는다.

### 3. 분석 대상 저장소로 이동

Bejewely 예시:

```powershell
cd D:\Ji_hwan\K_beauty
```

이 폴더는 실제 `package.json`, `src`, `supabase`, `.git` 등이 있는 프로젝트 폴더다.

### 4. PIE 프로젝트 설정 생성

```powershell
pie init-project --preset bejewely
```

기존 파일은 덮어쓰지 않는다. 다시 생성하면서 덮어써야 할 때만:

```powershell
pie init-project --preset bejewely --force
```

### 5. 연결 상태 확인

```powershell
pie github-doctor
```

`"ready": true`여야 한다. 현재 저장소가 `gycha0109-beep/K_beauty`로 확인되는지도 본다.

### 6. PR 분석

```powershell
pie analyze-pr https://github.com/gycha0109-beep/K_beauty/pull/71
```

또는 해당 저장소 폴더 안에서는:

```powershell
pie analyze-pr 71
```

### 7. 결과 확인

```powershell
notepad .pie\pr-71\REPORT.md
```

원본 증거 무결성 확인:

```powershell
pie validate-github-source .pie\pr-71\github-source.json
```

## BuildMap에서 사용할 때

```powershell
cd D:\Ji_hwan\BuildMap
pie init-project --preset buildmap
pie github-doctor
pie analyze-pr https://github.com/OWNER/BuildMap/pull/NUMBER
```

BuildMap과 연결할 때 `github-source.json`은 PR/리뷰/CI 사실 기록, `impact.json`은 구조 영향 기록으로 사용할 수 있다. 이후 Change Card 또는 Decision Timeline과 연결할 식별자는 repository, PR number, base/head SHA다.

## 자주 생기는 오류

### `gh is not installed`

GitHub CLI 설치 후 새 터미널에서 다시 실행한다.

### `not authenticated`

```powershell
gh auth login
```

### `cannot determine repository for a PR number`

PR URL 전체를 사용하거나 `--repo`를 붙인다.

```powershell
pie analyze-pr 71 --repo gycha0109-beep/K_beauty
```

### `local repository does not match`

다른 프로젝트 폴더에서 실행한 것이다. 올바른 로컬 저장소로 이동한다. `--allow-repository-mismatch`는 의도적인 오프라인 비교에만 사용한다.

### local HEAD mismatch

현재 로컬 checkout이 PR 최신 commit과 다르다는 뜻이며 기본적으로 분석을 중단한다. 해당 PR head를 안전하게 checkout한 뒤 `--refresh-graph`로 재실행한다. 의도적으로 현재 checkout과 비교할 때만 정확도 저하를 감수하고 `--allow-head-mismatch`를 사용한다.

```powershell
pie analyze-pr <URL> --refresh-graph
```

### 증거 파일 보안

`.pie/`에는 PR 본문, 댓글, 리뷰, CI metadata와 patch가 저장될 수 있다. `pie init-project`는 `.gitignore`에 `.pie/`를 비파괴 방식으로 추가하지만, 공유·업로드 전에 민감정보 포함 여부를 직접 확인한다. 대형 PR에서 GitHub가 diff를 거부하면 보고서의 `Diff evidence`가 `unavailable`로 표시되며 changed-file metadata 기반 결과만 사용해야 한다.

### Rate limit

PIE는 rate limit 또는 일시적인 502/503/504 오류를 제한적으로 재시도한다. 계속 실패하면 `gh api rate_limit`으로 reset 시각을 확인한 뒤 재실행한다.

### graph와 working tree

PR 분석은 다른 checkout에서 만든 stale graph를 재사용하지 않고 확인된 PR head에서 graph를 다시 생성한다. 분석 scope 안에 미커밋 변경이 있으면 기본적으로 중단하며, 의도적인 로컬 비교에만 `--allow-dirty-worktree`를 사용한다.
