#!/usr/bin/env bash
 get_temperature(){
                target_type="$1"

                for zone in /sys/class/thermal/thermal_zone*; do
                        zone_type=$(cat "$zone/type")

                        if [ "$zone_type" = "$target_type" ] ; then
                                cat "$zone/temp"
                                return
                        fi
                done
        }

  cleanup(){
	echo "Monitor stopping..."
	exit 0
	}
trap cleanup SIGINT SIGTERM
while true
do
	echo "[$(date '+%Y-%m-%d %H:%M:%S')]"
	load=$(cut -d' ' -f1-3 /proc/loadavg)
	echo "Load: $load"
	memory_total=$(free -h | awk '/^Mem:/ {print $2}')
	memory_used=$(free -h | awk '/^Mem:/ {print $3}')
	echo "Memory: $memory_used / $memory_total"

	soc_temp_raw=$(get_temperature "soc-thermal")
	npu_temp_raw=$(get_temperature "npu-thermal")

	soc_temp=$((soc_temp_raw / 1000))
	npu_temp=$((npu_temp_raw / 1000))

	echo "Temperature: SoC=${soc_temp}°C NPU=${npu_temp}°C"
	sleep 5
done
