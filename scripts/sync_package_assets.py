from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
target = root / "src/review_system/assets"
if target.exists():
    shutil.rmtree(target)
target.mkdir(parents=True)
for name in ("core", "packs", "templates", "schemas", "intelligence"):
    shutil.copytree(root / name, target / name)
(target / "profiles").mkdir()
shutil.copytree(root / "profiles" / "stacks", target / "profiles" / "stacks")
shutil.copytree(root / "profiles" / "examples", target / "profiles" / "examples")

(target / "bootstrap" / "intelligence").mkdir(parents=True)
for source in (root / "bootstrap" / ".review" / "intelligence").iterdir():
    if source.is_file():
        shutil.copy2(source, target / "bootstrap" / "intelligence" / source.name)
shutil.copy2(root / "VERSION", target / "VERSION")
print(target)
