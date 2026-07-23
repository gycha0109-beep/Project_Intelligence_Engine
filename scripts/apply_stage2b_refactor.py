from pathlib import Path


connector_path = Path("src/review_system/github_connector.py")
text = connector_path.read_text(encoding="utf-8")

for line in (
    "import os\n",
    "import shutil\n",
    "import subprocess\n",
    "import time\n",
    "from dataclasses import dataclass\n",
    "from urllib.parse import urlparse\n",
):
    text = text.replace(line, "", 1)
text = text.replace("from typing import Any, Iterable\n", "from typing import Any\n", 1)

runner_import = "from .github.runner import CommandResult, GitHubCLI, GitHubCLIError\n"
target_import = "from .github.target import (\n"
if runner_import not in text:
    if target_import not in text:
        raise SystemExit("GitHub target import anchor not found")
    text = text.replace(target_import, runner_import + target_import, 1)

start_marker = 'class GitHubCLIError(RuntimeError):\n'
end_marker = 'def _load_json_object(text: str, *, label: str) -> dict[str, Any]:\n'
if start_marker in text:
    start = text.index(start_marker)
    end = text.index(end_marker)
    text = text[:start] + text[end:]
elif runner_import not in text:
    raise SystemExit("GitHub runner block not found")

connector_path.write_text(text, encoding="utf-8")

test_path = Path("tests/test_github_connector.py")
test_text = test_path.read_text(encoding="utf-8")
test_text = test_text.replace(
    'patch("review_system.github_connector.subprocess.run",',
    'patch("review_system.github.runner.subprocess.run",',
)
test_text = test_text.replace(
    'patch("review_system.github_connector.time.sleep")',
    'patch("review_system.github.runner.time.sleep")',
)
test_path.write_text(test_text, encoding="utf-8")
