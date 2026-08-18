"""Install a distribution into a fresh venv and verify bundled schemas load."""

from pathlib import Path
import argparse
import subprocess
import sys
import tempfile
import venv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("distribution", type=Path)
    args = parser.parse_args()
    distribution = args.distribution.resolve()
    with tempfile.TemporaryDirectory(prefix="agentrust-wheel-") as directory:
        env = Path(directory)
        venv.EnvBuilder(with_pip=True).create(env)
        python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run([python, "-m", "pip", "install", str(distribution)], check=True)
        subprocess.run(
            [
                python,
                "-c",
                "from agentrust_telemetry import SchemaValidator; "
                "v=SchemaValidator.bundled(); print(v.schema_directory)",
            ],
            check=True,
        )
    print(f"PASS installed distribution smoke test: {distribution.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
