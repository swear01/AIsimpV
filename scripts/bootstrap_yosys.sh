#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
uv venv .tools/yosys-venv
uv pip install --python .tools/yosys-venv/bin/python \
  yowasp-yosys==0.69.0.0.post1233 yowasp-runtime==1.96 \
  wasmtime==47.0.1 click==8.5.0 platformdirs==4.11.11
.tools/yosys-venv/bin/yowasp-yosys -V
