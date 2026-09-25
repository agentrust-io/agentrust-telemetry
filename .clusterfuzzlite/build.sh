#!/bin/bash -eu
# Build the fuzz targets for ClusterFuzzLite.
#
# Third-party packages come from the same hash-pinned lock CI installs, then
# the package itself goes in with --no-deps, so the targets exercise the
# dependency set the test matrix runs against. The lock carries the
# opentelemetry and agentrust-trace extras the targets import (agentrust-trace
# behind a python_version >= 3.11 marker, which the base image satisfies).

cd "$SRC/agentrust-telemetry"
pip3 install --no-cache-dir --require-hashes -r requirements/test.txt
pip3 install --no-cache-dir --no-deps .

# compile_python_fuzzer bundles each target with PyInstaller, which follows
# static imports only. What has to be named explicitly:
#   email                   cryptography and pydantic reach email.mime lazily.
#   agentrust_telemetry     the event schemas are package data, not imports.
#   agentrust_trace         likewise its TRACE v0.2 schema, read at signing
#                           time. Without it the TRACE target dies with
#                           FileNotFoundError on schema/trace-v0.2.json.
#   jsonschema_specifications, opentelemetry
#                           metaschemas are data; OTel propagators and runtime
#                           context load through entry points. Current
#                           pyinstaller-hooks-contrib covers both; they are
#                           named so the build does not depend on the hooks
#                           version the base image happens to ship.
PYI_ARGS=(
  --collect-submodules=email
  --collect-data=agentrust_telemetry
  --collect-data=agentrust_trace
  --collect-data=jsonschema_specifications
  --collect-submodules=opentelemetry
  --copy-metadata=opentelemetry-api
)

for target in "$SRC"/agentrust-telemetry/.clusterfuzzlite/fuzz_*.py; do
  compile_python_fuzzer "$target" "${PYI_ARGS[@]}"
done
