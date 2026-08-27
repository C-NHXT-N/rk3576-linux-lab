#!/usr/bin/env bash

echo "================================"
echo "      RK3576 SYSTEM REPORT"
echo "================================"

hostname_value=$(hostname)
user_value=$(whoami)
kernel_value=$(uname -r)
arch_value=$(uname -m)
os_value=$(grep '^PRETTY_NAME=' /etc/os-release | cut -d= -f2 | tr -d '"')
echo
echo "========== SYSTEM =========="

echo "Hostname: $hostname_value"
echo "User: $user_value"
echo "Kernel: $kernel_value"
echo "Architecture: $arch_value"
echo "OS: $os_value"
echo
echo "========== CPU =========="

echo "Logical CPUs: $(nproc)"
lscpu | grep "Model name"
echo
echo "========== MEMORY =========="
free -h
echo
echo "========== STORAGE =========="
lsblk
df -h
echo
echo "========== NETWORK =========="
echo "ip address:"
ip -brief addr
echo "ip route:"
ip route
echo
echo "========== SERVICES =========="

echo "SSH enabled: $(systemctl is-enabled ssh)"
echo "SSH active: $(systemctl is-active ssh)"
echo
echo "========== PROCESS =========="
echo "Process count: $(ps -e --no-headers | wc -l)"
echo
echo "========== DEVICES =========="
echo
echo "========== DEVICES =========="

echo
echo "I2C devices:"
if ls /dev/i2c-* >/dev/null 2>&1; then
    ls /dev/i2c-*
else
    echo "No I2C devices found"
fi

echo
echo "Video devices:"
if ls /dev/video* >/dev/null 2>&1; then
    ls /dev/video*
else
    echo "No video devices found"
fi

echo
echo "NPU devices:"
if ls /dev/rknpu* >/dev/null 2>&1; then
    ls /dev/rknpu*
else
    echo "No matching NPU device node found"
fi