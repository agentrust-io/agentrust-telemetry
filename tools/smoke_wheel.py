"""Install a distribution into a fresh venv and verify bundled schemas load."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("distribution", type=Path)
    args = parser.parse_args()
    distribution = args.distribution.resolve()
    root = Path(__file__).resolve().parents[1]
    fixtures = {}
    for kind in ("valid", "invalid"):
        fixtures[kind] = [
            {"name": path.name, "event": json.loads(path.read_text(encoding="utf-8"))}
            for path in sorted((root / "conformance" / "fixtures" / kind).glob("*.json"))
        ]
    # Keep Python 3.10 support without introducing another TOML dependency.
    import re
    package_version = re.search(
        r'^version = "([^"]+)"', (root / "pyproject.toml").read_text(), re.MULTILINE
    ).group(1)
    controls = {"fixtures": fixtures, "version": package_version,
                "golden": json.loads((root / "compatibility/golden/event-factory.json").read_text())}
    with tempfile.TemporaryDirectory(prefix="agentrust-wheel-") as directory:
        env = Path(directory)
        venv.EnvBuilder(with_pip=True).create(env)
        python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run([python, "-m", "pip", "install", str(distribution)], check=True)
        (env / "controls.json").write_text(json.dumps(controls), encoding="utf-8")
        shutil.copyfile(Path(__file__).with_name("installed_python_controls.py"), env / "controls.py")
        clean_env = {key: value for key, value in os.environ.items()
                     if key not in {"PYTHONPATH", "PYTHONHOME"}}
        subprocess.run(
            [
                python,
                "-I", "controls.py", "controls.json",
            ],
            check=True, cwd=env, env=clean_env,
        )
    print(f"PASS installed distribution smoke test: {distribution.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
