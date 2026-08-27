# 01 - RK3576 Linux System Inspector

## 章节简介

这是 **「RK3576 + Linux 从零到嵌入式 AI 工程师」** 项目制教程的第一章。

很多 Linux 初学教程从 `ls`、`cd`、`cp` 等命令开始，然后要求学习者记住大量命令。但如果不知道这些命令背后对应 Linux 的哪一部分，很容易出现：

> 命令会用，但不知道系统为什么这样工作。

因此，本章不以“背 Linux 命令”为目标，而是围绕一个具体问题展开：

> **一块正在运行 Ubuntu 的 RK3576 开发板，Linux 是怎样组织 CPU、内存、进程、存储、设备、网络和服务信息的？**

我们会从真实开发板出发逐层观察：

```text
Application / Shell
        │
        ▼
Ubuntu User Space
        │
        ▼
Linux Kernel
        │
        ▼
RK3576 Hardware
```

最后把本章学到的命令组合成第一个完整项目：

```text
01-system-inspector/
├── README.md
└── system_report.sh
```

运行：

```bash
./system_report.sh
```

即可一次性生成 RK3576 的系统状态报告。

---

## 学习目标

完成本章后，你应该能够解释：

* Linux Kernel 和 Ubuntu 是什么关系
* `aarch64` 表示什么
* 用户名、主机名、UID、GID 和 Group 的基本概念
* `/proc` 为什么不是普通磁盘目录
* `/proc/PID` 与 Linux 进程的关系
* PID 和 PPID 分别是什么
* `MemFree` 和 `MemAvailable` 有什么区别
* 块设备、分区、文件系统和挂载点分别是什么
* `mount` 到底做了什么
* `/proc` 与 `/dev` 的主要区别
* 字符设备与块设备的基本概念
* `ip addr`、`ip route` 和 `ss` 分别解决什么问题
* `systemd` 和 `systemctl` 的基本关系
* Shell 中 `$()`、`|`、`2>/dev/null`、`$?` 的作用

---

# 一、命令和原理

## 1. Linux 系统到底由什么组成？

首先需要纠正一个常见概念：

> **Ubuntu 不等于 Linux Kernel。**

Linux Kernel 是操作系统的核心，负责管理：

```text
CPU
Memory
Process
Filesystem
Network
Device Driver
...
```

Ubuntu 则是一个 Linux 发行版，它把 Linux Kernel 与大量用户空间组件组合起来，例如：

```text
Linux Kernel
+
glibc
+
bash
+
systemd
+
apt
+
coreutils
+
SSH
+
系统库
+
应用程序
```

在本教程使用的开发板上：

```text
Hardware:     RK3576
Kernel:       Linux 6.1.99-rk3576
Distribution: Ubuntu 22.04.5 LTS
Architecture: aarch64
```

可以画成：

```text
┌─────────────────────────────┐
│ Application                 │
│ bash / ssh / Python / C++   │
├─────────────────────────────┤
│ Ubuntu User Space           │
├─────────────────────────────┤
│ Linux Kernel 6.1.99-rk3576  │
├─────────────────────────────┤
│ RK3576 Hardware             │
└─────────────────────────────┘
```

---

## 2. 查看 Kernel 和 CPU 架构

### uname

```bash
uname
```

输出：

```text
Linux
```

表示当前运行的是 Linux Kernel。

查看 Kernel Release：

```bash
uname -r
```

本实验：

```text
6.1.99-rk3576
```

这里看到的是 **Linux Kernel 版本**，而不是 Ubuntu 版本。

查看机器架构：

```bash
uname -m
```

输出：

```text
aarch64
```

可以先把它理解为：

> 当前系统运行在 64 位 ARM 架构上。

综合查看：

```bash
uname -a
```

实验输出：

```text
Linux lubancat 6.1.99-rk3576 ... aarch64 GNU/Linux
```

---

## 3. 查看 Linux 发行版

```bash
cat /etc/os-release
```

实验中：

```text
PRETTY_NAME="Ubuntu 22.04.5 LTS"
VERSION="22.04.5 LTS (Jammy Jellyfish)"
```

因此要区分：

```text
uname -r
        ↓
Linux Kernel Version

/etc/os-release
        ↓
Linux Distribution
```

---

## 4. 用户、主机名和用户组

查看当前用户：

```bash
whoami
```

输出：

```text
cat
```

查看用户详细信息：

```bash
id
```

实验结果：

```text
uid=1000(cat)
gid=1000(cat)
groups=1000(cat),27(sudo),29(audio),44(video)
```

其中：

```text
UID    User ID
GID    Group ID
groups 用户所属的其他组
```

查看主机名：

```bash
hostname
```

输出：

```text
lubancat
```

因此终端：

```text
cat@lubancat:~$
```

可以理解成：

```text
cat       → 当前用户
lubancat  → 当前主机名
~         → 当前用户 Home 目录
```

---

## 5. `/proc`：Kernel 暴露运行状态的窗口

执行：

```bash
mount | grep "on /proc "
```

实验输出：

```text
proc on /proc type proc (rw,relatime)
```

注意：

```text
type proc
```

说明 `/proc` 使用的是：

> procfs 虚拟文件系统。

例如：

```bash
cat /proc/cpuinfo
cat /proc/meminfo
cat /proc/loadavg
```

这些看起来像普通文件，但其内容主要是 Linux Kernel 动态生成并暴露给用户空间的。

可以理解为：

```text
User Space
    │
    │ read()
    ▼
  /proc
    │
    ▼
Linux Kernel
    │
    ▼
当前系统状态
```

因此：

> `/proc/cpuinfo` 并不是一个普通文件长期存储在 eMMC 的某个位置。

---

## 6. 查看 CPU

### lscpu

```bash
lscpu
```

实验中：

```text
Architecture: aarch64
CPU(s):       8
```

并检测到两类 CPU：

```text
Cortex-A53
Cortex-A72
```

RK3576 当前系统呈现为：

```text
CPU0 ─ Cortex-A53
CPU1 ─ Cortex-A53
CPU2 ─ Cortex-A53
CPU3 ─ Cortex-A53

CPU4 ─ Cortex-A72
CPU5 ─ Cortex-A72
CPU6 ─ Cortex-A72
CPU7 ─ Cortex-A72
```

也就是：

```text
4 × Cortex-A53
4 × Cortex-A72
```

### nproc

```bash
nproc
```

输出：

```text
8
```

表示当前系统可使用 8 个逻辑处理器。

### `/proc/cpuinfo`

```bash
head -n 50 /proc/cpuinfo
```

它展示 Linux Kernel 当前维护的 CPU 信息。

---

## 7. 查看内存

```bash
free -h
```

实验：

```text
               total   used   free   buff/cache   available
Mem:           7.7Gi   1.2Gi  3.6Gi  2.9Gi        6.4Gi
Swap:             0B      0B     0B
```

需要重点区分：

### free

真正完全没有被使用的内存。

### available

Linux 估算的：

> 在不发生严重 swapping 的情况下，目前还能提供给新程序使用的内存。

Linux 会主动使用空闲 RAM 作为：

```text
page cache
buffer
filesystem cache
```

因此：

> `free` 很小不一定意味着系统马上没有内存。

还可以查看 Kernel 原始数据：

```bash
head -n 15 /proc/meminfo
```

---

## 8. Linux Process、PID 和 PPID

查看当前 Bash PID：

```bash
echo $$
```

例如：

```text
70709
```

查看：

```bash
ps -p $$ -o pid,ppid,user,state,comm
```

可能得到：

```text
PID     PPID   USER  S  COMMAND
70709   70658  cat   S  bash
```

其中：

```text
PID
Process ID
进程编号

PPID
Parent Process ID
父进程编号
```

---

## 9. `/proc/PID`

假设 Bash PID：

```text
70709
```

那么：

```bash
ls /proc/70709
```

可以看到：

```text
cmdline
cwd
environ
exe
fd/
maps
status
task/
...
```

这些是 Kernel 通过 procfs 暴露的进程信息。

实验：

```bash
sleep 1000 &
```

假设得到：

```text
74620
```

查看：

```bash
ls /proc/74620
```

目录存在。

然后：

```bash
kill 74620
```

再次：

```bash
ls /proc/74620
```

得到：

```text
No such file or directory
```

说明：

```text
Kernel 中存在进程
        ↓
procfs 呈现 /proc/PID

进程结束
        ↓
Kernel 不再维护该进程
        ↓
/proc/PID 消失
```

---

## 10. 块设备和分区

查看：

```bash
lsblk
```

本开发板：

```text
mmcblk0
├─mmcblk0p1
├─mmcblk0p2  → /boot
└─mmcblk0p3  → /
```

可以理解为：

```text
eMMC
/dev/mmcblk0
│
├── Partition 1
├── Partition 2 → /boot
└── Partition 3 → /
```

---

## 11. df 与文件系统空间

```bash
df -h
```

主要回答：

> 已经挂载的文件系统用了多少空间，还剩多少空间？

这与：

```bash
lsblk
```

不同。

可以先记成：

```text
lsblk
↓
有哪些块设备和分区？

df -h
↓
已挂载文件系统空间使用情况如何？
```

---

## 12. mount 是什么？

执行：

```bash
findmnt /
```

实验输出：

```text
TARGET SOURCE         FSTYPE
/      /dev/mmcblk0p3 ext4
```

这表示：

> `/dev/mmcblk0p3` 上的 ext4 文件系统被挂载到了 `/`。

### Linux 没有 C:、D: 这种独立目录树

Linux 使用一棵统一目录树：

```text
/
├── boot
├── dev
├── etc
├── home
├── proc
├── sys
├── usr
└── var
```

`mount` 可以理解为：

> **把一个文件系统接到 Linux 目录树中的某个位置。**

例如：

```text
/dev/mmcblk0p3
      │
      │ ext4
      │
    mount
      │
      ▼
      /
```

所以 mount 并不是“把文件复制进目录”。

---

## 13. `/dev`：设备节点

查看：

```bash
ls -l /dev/null
```

可能看到：

```text
crw-rw-rw-
```

第一位：

```text
c
```

表示：

> character device，字符设备。

Linux 常见文件类型：

```text
-    普通文件
d    目录
c    字符设备
b    块设备
```

### `/proc` 与 `/dev`

初学阶段可以这样区分：

```text
/proc
│
└── 查看系统、Kernel 和 Process 状态

/dev
│
└── 用户空间访问设备的入口
```

例如：

```text
/dev/i2c-3
/dev/video0
/dev/ttyS0
```

以后驱动开发中，用户程序通常会通过：

```text
open()
read()
write()
ioctl()
```

访问设备节点。

---

## 14. 网络接口和 IP

查看：

```bash
ip addr
```

更简洁：

```bash
ip -brief addr
```

实验中：

```text
wlan0       192.168.0.244/24
tailscale0  100.64.207.34/32
```

这里说明开发板同时存在多个网络接口。

---

## 15. 路由

```bash
ip route
```

实验：

```text
default via 192.168.0.1 dev wlan0
```

可以读成：

> 当没有更加具体的路由规则匹配时，通过 `wlan0` 把数据发给默认网关 `192.168.0.1`。

---

## 16. TCP 监听端口

```bash
ss -lntp
```

参数：

```text
-l  listening
-n  numeric
-t  TCP
-p  process
```

例如：

```text
0.0.0.0:22
```

表示 SSH 服务正在监听 TCP 22 端口。

可以建立：

```text
Network Interface
       ↓
IP Address
       ↓
Route
       ↓
TCP Port
       ↓
Application
```

的关系。

---

## 17. systemd 与 systemctl 初识

查看 SSH：

```bash
systemctl status ssh --no-pager
```

检查是否开机启动：

```bash
systemctl is-enabled ssh
```

检查当前是否运行：

```bash
systemctl is-active ssh
```

需要区分：

```text
enabled
↓
配置为开机自动启动

active
↓
此时此刻正在运行
```

`systemd` 是系统和服务管理器。

`systemctl` 是和 systemd 交互的命令行工具。

systemd 会在下一章重点学习。

---

## 18. Shell 命令替换 `$()`

```bash
kernel=$(uname -r)
```

执行顺序：

```text
uname -r
    ↓
6.1.99-rk3576
    ↓
保存到 kernel
```

然后：

```bash
echo "$kernel"
```

---

## 19. Shell 管道 `|`

例如：

```bash
lscpu | grep "Model name"
```

管道把：

> 前一个程序的 stdout 连接到后一个程序的 stdin。

```text
lscpu
  │
stdout
  │
  | 
  ▼
grep
stdin
```

Unix/Linux 很多工具都遵循这种“小工具组合”的思路。

---

## 20. 标准输入、标准输出和标准错误

Linux 程序默认拥有：

```text
0 → stdin
1 → stdout
2 → stderr
```

因此：

```bash
ls /dev/rknpu* 2>/dev/null
```

表示：

```text
stderr
  │
  │ 2>
  ▼
/dev/null
```

`/dev/null` 可以理解成一个数据黑洞。

---

## 21. `$?`：退出状态

执行：

```bash
uname -r
echo $?
```

成功通常得到：

```text
0
```

约定：

```text
0      成功
非 0   失败
```

退出状态和 stdout 是两个不同概念。

---

# 二、实操和讲解

## 实操 1：创建项目目录

```bash
mkdir -p ~/rk3576-linux-lab/01-system-inspector
cd ~/rk3576-linux-lab/01-system-inspector
pwd
```

预期：

```text
/home/cat/rk3576-linux-lab/01-system-inspector
```

---

## 实操 2：确认 RK3576 系统身份

执行：

```bash
whoami
id
hostname

uname
uname -r
uname -m
uname -a

cat /etc/os-release
```

实验得到：

```text
User:         cat
Hostname:     lubancat
Kernel:       6.1.99-rk3576
Architecture: aarch64
OS:           Ubuntu 22.04.5 LTS
```

通过这一组命令建立：

```text
RK3576 Hardware
       ↓
Linux Kernel
       ↓
Ubuntu
       ↓
User Space
```

的基本关系。

---

## 实操 3：检查 procfs

```bash
mount | grep "on /proc "
```

输出：

```text
proc on /proc type proc (rw,relatime)
```

说明 `/proc` 使用 procfs。

进一步：

```bash
lscpu
nproc
head -n 50 /proc/cpuinfo

free -h
head -n 15 /proc/meminfo
```

可以观察：

> Linux 用户空间工具可以通过 Kernel 提供的接口获得系统状态。

---

## 实操 4：观察进程生命周期

执行：

```bash
echo $$
ps -p $$ -o pid,ppid,user,state,comm
cat /proc/$$/status | head -n 15
```

再：

```bash
sleep 1000 &
```

查看：

```bash
ps | grep sleep
```

假设 PID 为 `74620`：

```bash
ls /proc/74620
```

存在。

然后：

```bash
kill 74620
ls /proc/74620
```

得到：

```text
No such file or directory
```

### 一个常见错误

错误：

```bash
ls proc/74620
```

这是相对路径。

正确：

```bash
ls /proc/74620
```

这是绝对路径。

Linux 中：

```text
/proc/...  → 绝对路径
proc/...   → 相对于当前目录
```

---

## 实操 5：观察内存

```bash
free -h
```

再：

```bash
head -n 15 /proc/meminfo
```

重点比较：

```text
MemFree
MemAvailable
Cached
```

不要把 `MemFree` 直接等同于“还能使用多少内存”。

---

## 实操 6：检查存储系统

```bash
lsblk
df -h
findmnt /
```

实验中：

```text
/dev/mmcblk0p3 → /
/dev/mmcblk0p2 → /boot
```

因此可以形成：

```text
eMMC
 ↓
Block Device
 ↓
Partition
 ↓
Filesystem
 ↓
Mount
 ↓
Linux Directory Tree
```

的认识。

---

## 实操 7：检查 `/dev`

```bash
ls -l /dev/null
ls -l /dev/zero
ls -l /dev/tty
```

再：

```bash
ls /dev | grep -E 'video|i2c|tty|rknpu' | head -n 30
```

实验可以看到：

```text
/dev/i2c-1
/dev/i2c-2
/dev/i2c-3
...
```

这些设备节点会在后面的驱动章节重新出现。

---

## 实操 8：检查网络

```bash
ip addr
ip route
ss -lntp
```

实验中：

```text
wlan0
192.168.0.244/24
```

以及：

```text
tailscale0
100.64.207.34/32
```

默认路由：

```text
default via 192.168.0.1 dev wlan0
```

同时 TCP 22 被 SSH 服务监听。

---

## 实操 9：查看 SSH Service

```bash
systemctl status ssh --no-pager
systemctl is-enabled ssh
systemctl is-active ssh
```

实验：

```text
enabled
active
```

表示：

> SSH 当前正在运行，并设置为开机自动启动。

---

## 实操 10：编写 `system_report.sh`

创建：

```bash
vim system_report.sh
```

完整实现：

```bash
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
```

赋予执行权限：

```bash
chmod +x system_report.sh
```

运行：

```bash
./system_report.sh
```

---

## 实操 11：检查脚本状态

查看退出状态：

```bash
echo $?
```

正常：

```text
0
```

检查 Bash 语法：

```bash
bash -n system_report.sh
```

没有输出通常表示 Bash 没有发现语法错误。

但是要记住：

> **语法正确不代表程序逻辑一定正确。**

---

## 实操 12：理解真实报错

### 错误一

```bash
head -nn 15 /proc/meminfo
```

报：

```text
invalid number of lines
```

因为参数写错。

正确：

```bash
head -n 15 /proc/meminfo
```

### 错误二

```bash
ls proc/74620
```

报：

```text
No such file or directory
```

原因不是 `/proc/74620` 不存在，而是少写了开头的 `/`。

学习 Linux 时应该养成：

> **先阅读错误信息，再尝试定位问题，而不是立刻复制新的命令。**

---

# 三、章节总结

本章最终建立了下面这套 Linux 基本结构：

```text
                         RK3576
                            │
                         Hardware
                            │
                ┌───────────┴───────────┐
                │                       │
             CPU/RAM                 Devices
                │                       │
                ▼                       ▼
          Linux Kernel              Drivers
                │                       │
       ┌────────┼─────────┐             │
       │        │         │             ▼
     /proc    Process   Network        /dev
       │        │         │             │
       └────────┴────┬────┴─────────────┘
                     │
                 User Space
                     │
          ┌──────────┼──────────┐
          │          │          │
        bash       systemd     sshd
          │
          ▼
   system_report.sh
```

完成这一章以后，看到：

```bash
free -h
```

不应该只想到：

> 这是查看内存的命令。

而应该进一步理解：

```text
free
 ↓
从 Linux 提供的系统接口获取内存状态
 ↓
格式化
 ↓
输出给用户
```

这套思维方式会一直延续到后面的：

```text
Linux System Programming
Driver
Device Tree
RKNN
RKLLM
ROS2
```

---

# 四、课后问题

## 基础题

1. `uname -r` 和 `/etc/os-release` 分别查看什么？
2. `aarch64` 表示什么？
3. `cat@lubancat` 中 `cat` 和 `lubancat` 分别是什么？
4. Ubuntu 和 Linux Kernel 是什么关系？
5. `/proc/cpuinfo` 是真正存储在 eMMC 上的普通文件吗？
6. `MemFree` 很小是否意味着 Linux 马上没有内存？
7. PID 和 PPID 分别是什么？
8. `/proc/1234` 和 PID 1234 的进程是什么关系？
9. 为什么进程结束后 `/proc/PID` 通常会消失？
10. `lsblk` 和 `df -h` 分别主要解决什么问题？

## 理解题

11. 什么是 mount？
12. Linux 中 `/` 表示什么？
13. `/proc` 和 `/dev` 最大的区别是什么？
14. `crw-rw-rw-` 最前面的 `c` 表示什么？
15. `ip addr` 和 `ip route` 分别查看什么？
16. `systemctl is-enabled` 和 `systemctl is-active` 有什么区别？
17. `$()` 在 Shell 中叫什么？有什么作用？
18. `|` 左右连接的分别是什么？
19. `2>/dev/null` 中 `2` 表示什么？
20. `$?` 表示什么？

## 思考题

21. 为什么 `echo "$(free -h)"` 通常不如直接执行 `free -h`？
22. 为什么没有发现 `/dev/rknpu*` 不能直接得出“RK3576 没有 NPU”的结论？
23. 为什么进行 Linux 排错时，要区分“观察到的事实”和“根据事实推导出的结论”？
24. 当你通过 SSH 登录 RK3576 并执行 `./system_report.sh` 时，请尝试用自己的话说明 Bash、用户空间、Linux Kernel 和硬件之间是如何联系起来的。

