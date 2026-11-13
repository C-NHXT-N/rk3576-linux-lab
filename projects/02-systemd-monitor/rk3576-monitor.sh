#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 C-NHXT-N and contributors
set -u
set -o pipefail
export LC_ALL=C
interval=5
samples=0
while (($#)); do
    case "$1" in
        --once) samples=1; shift ;;
        --samples|--interval)
            if (($# < 2)); then echo "Missing value for $1" >&2; exit 2; fi
            case "$1" in --samples) samples=$2 ;; --interval) interval=$2 ;; esac
            shift 2 ;;
        *) echo 'Usage: rk3576-monitor.sh [--once | --samples N] [--interval SECONDS]' >&2; exit 2 ;;
    esac
done
if [[ ! $samples =~ ^[0-9]{1,6}$ || ! $interval =~ ^[0-9]{1,6}$ ]]; then
    echo 'Samples and interval must be non-negative integers (at most six digits).' >&2
    exit 2
fi
samples=$((10#$samples))
interval=$((10#$interval))
if ((interval < 1)); then echo 'Interval must be at least one second.' >&2; exit 2; fi
# Override only for repeatable fixtures; production uses the normal sysfs mount.
thermal_root=${RK3576_THERMAL_ROOT:-/sys/class/thermal}
get_temperature() {
    local target_type=$1 zone zone_type raw
    for zone in "$thermal_root"/thermal_zone*; do
        [[ -r $zone/type ]] || continue
        IFS= read -r zone_type < "$zone/type" || continue
        [[ $zone_type == "$target_type" ]] || continue
        if [[ ! -r $zone/temp ]]; then
            printf 'N/A (unreadable)'
        elif ! IFS= read -r raw < "$zone/temp" || [[ ! $raw =~ ^-?[0-9]+$ ]]; then
            printf 'N/A (invalid reading)'
        else
            awk -v raw="$raw" 'BEGIN {printf "%.1f C", raw / 1000}'
        fi
        return
    done
    printf 'N/A (not found)'
}
sleep_pid=
cleanup() {
    if [[ -n $sleep_pid ]]; then
        kill "$sleep_pid" 2>/dev/null || :
        wait "$sleep_pid" 2>/dev/null || :
    fi
    echo 'Monitor stopping...'
    exit 0
}
trap cleanup INT TERM
count=0
while :; do
    printf '[%s]\n' "$(date '+%Y-%m-%d %H:%M:%S')"
    if [[ -r /proc/loadavg ]]; then
        printf 'Load: %s\n' "$(cut -d' ' -f1-3 /proc/loadavg)"
    else
        echo 'ERROR: /proc/loadavg unavailable' >&2; exit 1
    fi
    if ! free -m | awk '/^Mem:/ {printf "Memory: used=%s MiB total=%s MiB available=%s MiB\n", $3, $2, $7}'; then
        echo 'ERROR: could not read memory' >&2; exit 1
    fi
    printf 'Temperature: SoC=%s NPU=%s\n' "$(get_temperature soc-thermal)" "$(get_temperature npu-thermal)"
    count=$((count + 1))
    if ((samples > 0 && count >= samples)); then break; fi
    sleep "$interval" &
    sleep_pid=$!
    wait "$sleep_pid" || :
    sleep_pid=
done
