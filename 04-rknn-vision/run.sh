#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export LIBRKNNRT_PATH="$project_dir/runtime/librknnrt.so"
exec "$project_dir/.venv/bin/python" "$project_dir/vision.py" "$@"
