#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$repo_dir/build"
sources=(01-process-lab:process_lab 02-write-lab:write_lab 03-pipe-lab:pipe_lab 04-mmap-lab:mmap_lab)
for pair in "${sources[@]}"; do
    source_name=${pair%%:*}
    output_name=${pair##*:}
    g++ -std=c++17 -Wall -Wextra -Werror -O0 -g \
        "$repo_dir/03-linux-system-programming/$source_name.cpp" -o "$repo_dir/build/$output_name"
done
printf 'Built four labs in %s/build\n' "$repo_dir"
