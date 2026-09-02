"""Derive the npm dist-tag for the declared contract version.

npm refuses to publish a prerelease without an explicit `--tag`, because an
untagged publish moves `latest`. Hardcoding a tag in the workflow or in
`publishConfig` would then need editing at every phase change, and the phase is
already declared once in `spec/VERSION`. This derives the tag from that single
source so the release workflow never has to be told which phase it is in.

    python tools/npm_dist_tag.py        # prints the tag for spec/VERSION

Mapping, using the same phase grammar `check_versions.ecosystem_versions` parses:

    1.0.0           -> latest
    0.1.0-alpha.1   -> alpha
    0.1.0-beta.2    -> beta
    0.1.0-rc.1      -> rc
    0.1.0-dev       -> dev
"""

import sys
from pathlib import Path

try:
    from check_versions import ROOT, CONTRACT_PATTERN
except ModuleNotFoundError:  # Imported as a repository test module.
    from tools.check_versions import ROOT, CONTRACT_PATTERN

STABLE_TAG = "latest"


def dist_tag(contract: str) -> str:
    """Return the npm dist-tag for a contract version, or raise on a bad one."""
    match = CONTRACT_PATTERN.fullmatch(contract)
    if not match:
        raise ValueError(f"unsupported contract version: {contract}")
    phase = match.group(4)
    return phase if phase else STABLE_TAG


def main() -> int:
    contract = (ROOT / "spec" / "VERSION").read_text(encoding="utf-8").strip()
    try:
        print(dist_tag(contract))
    except ValueError as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
