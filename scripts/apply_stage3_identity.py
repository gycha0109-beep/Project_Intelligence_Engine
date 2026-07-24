from pathlib import Path

implementation = Path(__file__).with_name("stage3_identity_impl.py")
exec(compile(implementation.read_text(encoding="utf-8"), str(implementation), "exec"))
