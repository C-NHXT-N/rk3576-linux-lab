#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
# Read-only report. Optional devices/services may legitimately be absent.
set -u
set -o pipefail
export LC_ALL=C
section=all
if [[ $# -eq 2 && $1 == --section ]]; then
    section=$2
elif [[ $# -ne 0 ]]; then
    echo 'Usage: bash system_report.sh [--section identity|memory|storage|process|network|devices|all]' >&2
    exit 2
fi
case "$section" in
    identity|memory|storage|process|network|devices|all) ;;
    *) echo "Unknown section: $section" >&2; exit 2 ;;
esac
failed=0
required() {
    if ! "$@"; then
        echo "ERROR: could not run $1" >&2
        failed=1
    fi
}
heading() { printf '\n========== %s ==========\n' "$1"; }
selected() { [[ $section == all || $section == "$1" ]]; }
if selected identity; then
    heading SYSTEM
    printf 'Hostname: '; required hostname
    printf 'User: '; required whoami
    printf 'Kernel: '; required uname -r
    printf 'Architecture: '; required uname -m
    if [[ -r /etc/os-release ]]; then
        grep '^PRETTY_NAME=' /etc/os-release
    else
        echo 'OS: N/A (/etc/os-release unreadable)'
    fi
fi
if selected memory; then
    heading CPU
    printf 'Logical CPUs available to this process: '; required nproc
    required lscpu
    heading MEMORY
    required free -h
fi
if selected storage; then
    heading STORAGE
    required lsblk
    required df -h
    required findmnt /
fi
if selected process; then
    heading PROCESS
    if count=$(ps -e --no-headers | wc -l); then
        printf 'Process count: %s\n' "$count"
    else
        failed=1
    fi
    required ps -p "$$" -o pid,ppid,user,state,comm
fi
if selected network; then
    heading NETWORK
    required ip -brief addr
    required ip route
    required ss -lnt
    heading SERVICES
    if command -v systemctl >/dev/null && [[ -d /run/systemd/system ]]; then
        printf 'SSH enabled: '; systemctl is-enabled ssh 2>/dev/null || :
        printf 'SSH active: '; systemctl is-active ssh 2>/dev/null || :
    else
        echo 'SSH state: N/A (systemd is not running)'
    fi
fi
if selected devices; then
    heading DEVICES
    shopt -s nullglob
    for pattern in i2c video rknpu; do
        case "$pattern" in
            i2c) nodes=(/dev/i2c-*) ;;
            video) nodes=(/dev/video*) ;;
            rknpu) nodes=(/dev/rknpu* /dev/dri/renderD*) ;;
        esac
        printf '%s candidate nodes:\n' "$pattern"
        if ((${#nodes[@]})); then
            printf '  %s\n' "${nodes[@]}"
        else
            echo '  N/A (no matching nodes)'
        fi
    done
    echo 'Node names alone do not prove that a camera or NPU inference is usable.'
fi
exit "$failed"
