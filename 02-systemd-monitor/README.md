# 02 - RK3576 Systemd Monitor

## 章节简介

这是 **「RK3576 + Linux 从零到嵌入式 AI 工程师」** 项目制教程的第二章。

上一章实现的：

```text
system_report.sh
```

属于一次性程序：

```text
启动
 ↓
采集状态
 ↓
打印结果
 ↓
退出
```

但实际嵌入式设备中存在大量需要长期运行的程序，例如：

```text
设备监控服务
传感器采集服务
网络服务器
机器人节点
摄像头服务
AI 推理服务
```

这些程序不能依赖用户每次 SSH 登录后手工启动。

因此本章解决的问题是：

> **怎样把一个普通 Shell 程序变成可以长期运行、响应 Signal、记录日志、异常自动恢复并且能够开机自动启动的 Linux Service？**

最终项目：

```text
02-systemd-monitor/
├── README.md
├── rk3576-monitor.sh
└── rk3576-monitor.service
```

最终实现：

```text
Load Average
Memory
SoC Temperature
NPU Temperature
       │
       ▼
rk3576-monitor.sh
       │
       ▼
systemd
       │
       ├── start / stop / restart
       ├── journal
       ├── failure recovery
       └── boot auto-start
```

---

## 学习目标

完成本章后，你应该能够解释：

* 前台进程和后台进程的区别
* Shell Job 和 Linux Process 的区别
* PID 与 PPID
* `&`、`jobs`、`$!` 的作用
* SIGINT、SIGTERM 和 SIGKILL 的区别
* `while true` 为什么会持续运行
* `/proc/loadavg` 是什么
* `/sys/class/thermal` 的基本作用
* Shell 函数、`for`、`if`、`trap` 的作用
* systemd 和 systemctl 的关系
* 为什么 systemd 通常是 PID 1
* `.service` 文件的基本结构
* `ExecStart`、`User`、`Restart=on-failure`
* `start`、`stop`、`restart`、`enable`
* `daemon-reload`
* journald 与 journalctl
* systemd 如何判断程序异常退出并自动重启

---

# 一、代码和原理

## 1. 前台进程

运行：

```bash
sleep 20
```

此时 Shell 不再立即出现命令提示符。

关系：

```text
bash
 │
 │ fork/exec 等机制
 ▼
sleep 20
 │
 │ Bash 等待
 ▼
程序结束
 │
 ▼
bash 继续接受命令
```

---

## 2. 后台进程

运行：

```bash
sleep 1000 &
```

最后的：

```text
&
```

表示：

> Bash 启动程序之后不等待它结束，而是立即继续接收用户输入。

```text
          ┌── sleep 1000
bash ─────┤
          └── 继续接受命令
```

但要注意：

> **后台进程不等于 Linux Service。**

它仍然可能与：

```text
Shell
Terminal
Session
```

存在关系。

---

## 3. jobs 与 ps

查看：

```bash
jobs
```

例如：

```text
[1]+ Running sleep 1000 &
```

`jobs` 观察的是：

> 当前 Shell 管理的 Job。

而：

```bash
ps
```

观察的是 Linux Process。

因此：

```text
jobs
↓
Shell 层

ps
↓
Process / Kernel 层
```

直接执行 `ps` 默认只显示当前终端相关的一部分进程。

查看所有进程可以使用：

```bash
ps -e
```

---

## 4. `$!`

执行：

```bash
sleep 1000 &
```

然后：

```bash
echo $!
```

`$!` 表示：

> 当前 Shell 最近一次启动的后台任务的 PID。

例如：

```text
112066
```

### 为什么不能直接执行 `$!`？

如果输入：

```bash
$!
```

Bash 会先展开：

```text
$!
 ↓
112066
```

然后相当于执行：

```bash
112066
```

于是：

```text
command not found
```

正确使用：

```bash
echo $!
kill $!
ps -p $!
```

---

## 5. PID 与 PPID

查看 Bash：

```bash
echo $$
```

其中：

```text
$$
```

表示当前 Shell PID。

然后：

```bash
sleep 1000 &
```

执行：

```bash
ps -o pid,ppid,stat,comm -p $$,$!
```

实验中可以看到：

```text
bash
PID = 111537
      │
      └── sleep
          PID  = 112066
          PPID = 111537
```

其中：

```text
PID
Process ID

PPID
Parent Process ID
```

---

## 6. Linux Signal

Linux 可以通过 Signal 向进程发送事件。

本章重点学习三个 Signal。

### SIGINT

手工运行：

```bash
./rk3576-monitor.sh
```

按：

```text
Ctrl+C
```

终端通常会向前台程序发送：

```text
SIGINT
```

---

### SIGTERM

当执行：

```bash
sudo systemctl stop rk3576-monitor
```

systemd 正常停止 Service 时通常会使用：

```text
SIGTERM
```

它的意义更接近：

> 请结束运行。

程序可以捕获这个 Signal，并在退出之前执行清理工作。

---

### SIGKILL

```bash
kill -9 PID
```

其中：

```text
-9
```

对应：

```text
SIGKILL
```

SIGKILL 非常特殊：

> 它不能被程序捕获、忽略或处理。

```text
SIGTERM
 ↓
程序收到通知
 ↓
有机会 cleanup
 ↓
退出

SIGKILL
 ↓
Kernel
 ↓
立即结束进程
```

因此不要把 `kill -9` 当成正常停止程序的首选方式。

---

## 7. `while true`

监控程序需要不断采集数据。

基础结构：

```bash
while true
do
    echo "monitor running"
    sleep 5
done
```

其中：

```bash
true
```

本身是一个命令。

执行：

```bash
true
echo $?
```

得到：

```text
0
```

说明 `true` 总是成功。

而 `while` 会在条件成功时继续执行，因此：

```bash
while true
```

形成无限循环。

---

## 8. date 时间格式

```bash
date '+%Y-%m-%d %H:%M:%S'
```

例如：

```text
2026-08-26 03:32:21
```

格式：

```text
%Y  四位年份
%m  月
%d  日
%H  小时
%M  分钟
%S  秒
```

注意大小写非常重要。

例如：

```text
%m → month
%M → minute
```

`+` 表示：

> 后面的内容是输出 FORMAT。

---

## 9. Load Average

查看：

```bash
uptime
```

例如：

```text
load average: 0.00, 0.02, 0.00
```

也可以直接：

```bash
cat /proc/loadavg
```

例如：

```text
0.07 0.04 0.00 1/639 114211
```

前三个值对应大约：

```text
1 分钟
5 分钟
15 分钟
```

的系统 Load Average。

必须注意：

> **Load Average 不是 CPU 使用率百分比。**

提取前三列：

```bash
cut -d' ' -f1-3 /proc/loadavg
```

然后：

```bash
load=$(cut -d' ' -f1-3 /proc/loadavg)
```

---

## 10. 使用 awk 提取内存

原始命令：

```bash
free -h
```

输出是一个表格。

我们只希望日志出现：

```text
Memory: 1.0Gi / 7.7Gi
```

可以使用：

```bash
free -h | awk '/^Mem:/ {print $2}'
```

总内存：

```bash
memory_total=$(free -h | awk '/^Mem:/ {print $2}')
```

已使用内存：

```bash
memory_used=$(free -h | awk '/^Mem:/ {print $3}')
```

其中 awk：

```text
/^Mem:/
```

表示寻找以：

```text
Mem:
```

开头的行。

而：

```text
$2
$3
```

表示 awk 当前记录的第二列、第三列。

---

## 11. `/sys` 和 sysfs

上一章已经认识：

```text
/proc
/dev
```

本章第一次使用：

```text
/sys
```

`/sys` 通常挂载 sysfs。

它主要向用户空间呈现：

```text
Device
Driver
Bus
Kernel Object
Hardware Attribute
```

等信息。

本章使用：

```text
/sys/class/thermal/
```

读取温度传感器。

---

## 12. RK3576 Thermal Zone

执行：

```bash
ls /sys/class/thermal/
```

再：

```bash
for zone in /sys/class/thermal/thermal_zone*; do
    echo "=== $zone ==="
    cat "$zone/type"
    cat "$zone/temp"
done
```

实际开发板检测到：

```text
thermal_zone0
soc-thermal

thermal_zone1
bigcore-thermal

thermal_zone2
little-core-thermal

thermal_zone3
ddr-thermal

thermal_zone4
npu-thermal

thermal_zone5
gpu-thermal
```

温度例如：

```text
37922
```

通常表示：

```text
37922 毫摄氏度
≈
37.922°C
```

---

## 13. 为什么不能硬编码 thermal_zone4？

虽然当前实验环境：

```text
thermal_zone4 = npu-thermal
```

但是不应该写死：

```bash
cat /sys/class/thermal/thermal_zone4/temp
```

然后假设它永远表示 NPU。

因为 thermal zone 编号可能随着：

```text
Kernel
Device Tree
Driver
初始化顺序
BSP
```

发生变化。

更好的逻辑是：

> 查找 `type=npu-thermal` 的 thermal zone。

---

## 14. Shell 函数

定义：

```bash
get_temperature() {
    ...
}
```

调用：

```bash
get_temperature "npu-thermal"
```

函数内部：

```bash
target_type="$1"
```

其中：

```text
$1
```

表示函数获得的第一个参数。

---

## 15. for 循环

```bash
for zone in /sys/class/thermal/thermal_zone*; do
    ...
done
```

会依次处理：

```text
thermal_zone0
thermal_zone1
thermal_zone2
...
```

---

## 16. if 判断

```bash
if [ "$zone_type" = "$target_type" ]; then
    ...
fi
```

可以读成：

> 如果当前 thermal zone 的类型等于目标类型，则执行里面的代码。

---

## 17. get_temperature()

完整函数：

```bash
get_temperature() {
    target_type="$1"

    for zone in /sys/class/thermal/thermal_zone*; do
        zone_type=$(cat "$zone/type")

        if [ "$zone_type" = "$target_type" ]; then
            cat "$zone/temp"
            return
        fi
    done
}
```

执行流程：

```text
get_temperature "npu-thermal"
            │
            ▼
target_type=npu-thermal
            │
            ▼
遍历 thermal_zone
            │
            ▼
读取 type
            │
        ┌───┴───┐
        │       │
      不同     相同
        │       │
     下一个     ▼
              temp
               │
             return
```

---

## 18. 算术展开 `$(( ))`

假设：

```text
npu_temp_raw=37922
```

执行：

```bash
npu_temp=$((npu_temp_raw / 1000))
```

得到：

```text
37
```

`$(( ... ))` 是 Bash 的算术展开。

---

## 19. trap

定义清理函数：

```bash
cleanup() {
    echo "Monitor stopping..."
    exit 0
}
```

注册：

```bash
trap cleanup SIGINT SIGTERM
```

意思是：

> Bash 收到 SIGINT 或 SIGTERM 时，不直接按默认行为退出，而是执行 `cleanup()`。

因此：

```text
Ctrl+C
 ↓
SIGINT
 ↓
trap
 ↓
cleanup()
```

以及：

```text
systemctl stop
 ↓
SIGTERM
 ↓
trap
 ↓
cleanup()
```

---

## 20. exit 0

```bash
exit 0
```

表示：

> 程序以成功状态退出。

需要区分：

```text
stdout
↓
程序打印的内容

exit status
↓
程序成功还是失败
```

例如：

```bash
echo $?
```

才能查看上一条程序的退出状态。

---

## 21. systemd

执行：

```bash
ps -p 1 -o pid,ppid,user,comm,args
```

本实验：

```text
PID PPID USER COMMAND
1   0    root systemd
```

说明当前系统中：

```text
systemd
PID = 1
```

可以先理解为：

> Linux Kernel 启动用户空间之后，由 systemd 负责组织大量系统服务。

```text
Linux Kernel
     │
     ▼
 systemd
 PID 1
     │
     ├── ssh.service
     ├── ...
     └── rk3576-monitor.service
```

---

## 22. systemctl

`systemctl` 不是 systemd 本身。

关系：

```text
User
 │
 ▼
systemctl
 │
 ▼
systemd
 │
 ▼
Service
```

例如：

```bash
systemctl stop ssh
```

本质上是使用 `systemctl` 向 systemd 发出服务控制请求。

---

## 23. Service Unit 基本结构

本项目：

```ini
[Unit]
Description=RK3576 System Monitor

[Service]
Type=simple
User=cat
WorkingDirectory=/home/cat/rk3576-linux-lab/02-systemd-monitor
ExecStart=/home/cat/rk3576-linux-lab/02-systemd-monitor/rk3576-monitor.sh
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

---

## 24. `[Unit]`

主要描述：

> 这个 Unit 是什么，以及它与其他 Unit 的关系。

例如：

```ini
Description=RK3576 System Monitor
```

---

## 25. `[Service]`

描述：

> Service 真正如何运行。

例如：

```ini
ExecStart=...
User=...
Restart=...
```

---

## 26. `[Install]`

主要涉及：

```bash
systemctl enable
```

时：

> 这个 Service 应该加入哪个系统启动目标。

---

## 27. Type=simple

```ini
Type=simple
```

可以先理解成：

> `ExecStart` 启动出来的进程就是这个 Service 的主要进程。

我们的脚本本身拥有：

```bash
while true
```

会长期运行，非常适合这种方式。

---

## 28. User=cat

```ini
User=cat
```

表示：

> 使用普通用户 `cat` 运行服务。

本项目只需要读取：

```text
/proc
/sys
```

没有必要以 root 运行。

工程原则：

> **不需要 root，就不要给 root。**

这属于最小权限原则。

---

## 29. WorkingDirectory

```ini
WorkingDirectory=/home/cat/rk3576-linux-lab/02-systemd-monitor
```

可以理解为 systemd 启动程序前，为这个 Service 指定工作目录。

相对路径会基于这里解析。

---

## 30. ExecStart

```ini
ExecStart=/home/cat/rk3576-linux-lab/02-systemd-monitor/rk3576-monitor.sh
```

表示：

> Service 启动时 systemd 实际执行的命令。

最好使用绝对路径。

---

## 31. Restart=on-failure

```ini
Restart=on-failure
RestartSec=3
```

表示：

```text
程序异常退出
     ↓
systemd 检测 failure
     ↓
等待 3 秒
     ↓
重新启动
```

这里的：

```text
RestartSec=3
```

可以避免程序崩溃后立即进入高频启动—崩溃循环。

---

## 32. WantedBy=multi-user.target

```ini
[Install]
WantedBy=multi-user.target
```

执行：

```bash
sudo systemctl enable rk3576-monitor
```

后，会建立类似：

```text
/etc/systemd/system/multi-user.target.wants/
    rk3576-monitor.service
        ↓
        symlink
        ↓
/etc/systemd/system/rk3576-monitor.service
```

这样系统进入：

```text
multi-user.target
```

时，该 Service 可以被自动启动。

不要简单把 `multi-user.target` 直接称作“用户等级 3”。

传统 SysV 的 runlevel 3 与它存在一定功能对应，但 systemd 使用的是 target 概念。

---

## 33. daemon-reload

修改：

```text
/etc/systemd/system/*.service
```

后执行：

```bash
sudo systemctl daemon-reload
```

意思是：

> 通知 systemd 重新扫描和解析 Unit 配置。

它本身不会：

```text
start
stop
restart
```

Service。

---

## 34. journald 与 journalctl

手动执行脚本时：

```text
monitor
 │
stdout
 │
 ▼
SSH Terminal
```

由 systemd 启动后：

```text
monitor
 │
 ├── stdout
 └── stderr
       │
       ▼
    journald
       │
       ▼
   journalctl
```

因此可以：

```bash
journalctl -u rk3576-monitor
```

查看服务日志。

---

# 二、实操和讲解

## 实操 1：创建项目

```bash
cd ~/rk3576-linux-lab
mkdir -p 02-systemd-monitor
cd 02-systemd-monitor
```

---

## 实操 2：观察前台和后台进程

前台：

```bash
sleep 20
```

此时 Shell 等待。

后台：

```bash
sleep 1000 &
```

Shell 立即返回：

```text
[1] 112066
```

查看：

```bash
jobs
```

得到：

```text
[1]+ Running sleep 1000 &
```

再：

```bash
ps
```

可以看到 `bash` 与 `sleep` 是不同进程。

---

## 实操 3：观察父子进程

```bash
echo "bash PID = $$"
```

然后：

```bash
ps -o pid,ppid,stat,comm -p $$,$!
```

实验观察到：

```text
sleep PPID
=
bash PID
```

说明当前 `sleep` 是 Bash 启动出来的子进程。

---

## 实操 4：研究 systemd

```bash
ps -p 1 -o pid,ppid,user,comm,args
```

实验：

```text
1  0  root  systemd
```

说明 systemd 是 PID 1。

---

## 实操 5：研究 SSH Unit

```bash
systemctl status ssh --no-pager
systemctl cat ssh
```

可以看到：

```text
[Unit]
[Service]
[Install]
```

以及：

```ini
ExecStart=/usr/sbin/sshd ...
Restart=on-failure
WantedBy=multi-user.target
```

先研究系统已有的 Service，再创建自己的 Service。

---

## 实操 6：第一个长期运行脚本

创建：

```bash
vim rk3576-monitor.sh
```

最初版本：

```bash
#!/usr/bin/env bash

while true
do
    echo "monitor running"
    sleep 5
done
```

然后：

```bash
chmod +x rk3576-monitor.sh
./rk3576-monitor.sh
```

观察程序每隔 5 秒输出。

按：

```text
Ctrl+C
```

停止。

---

## 实操 7：加入时间

测试：

```bash
date '+%Y-%m-%d %H:%M:%S'
```

脚本：

```bash
echo "[$(date '+%Y-%m-%d %H:%M:%S')]"
```

一个实际调试错误是：

```bash
date '+%Y-%M-%D %H:%M:%S'
```

由于 `%M` 是分钟、`%D` 是另一种日期格式，会得到错误的输出格式。

这个实验说明：

> Linux 命令选项和格式符的大小写具有语义区别。

---

## 实操 8：采集 Load

```bash
uptime
cat /proc/loadavg
```

提取：

```bash
cut -d' ' -f1-3 /proc/loadavg
```

加入：

```bash
load=$(cut -d' ' -f1-3 /proc/loadavg)
echo "Load: $load"
```

---

## 实操 9：采集内存

测试：

```bash
free -h | awk '/^Mem:/ {print $2, $3}'
```

加入：

```bash
memory_total=$(free -h | awk '/^Mem:/ {print $2}')
memory_used=$(free -h | awk '/^Mem:/ {print $3}')

echo "Memory: $memory_used / $memory_total"
```

得到：

```text
Memory: 1.0Gi / 7.7Gi
```

---

## 实操 10：调查 Thermal Zone

```bash
ls /sys/class/thermal/
```

然后：

```bash
for zone in /sys/class/thermal/thermal_zone*; do
    echo "=== $zone ==="
    cat "$zone/type"
    cat "$zone/temp"
done
```

实验结果：

```text
soc-thermal
bigcore-thermal
little-core-thermal
ddr-thermal
npu-thermal
gpu-thermal
```

因此我们决定监控：

```text
SoC
NPU
```

两组温度。

---

## 实操 11：编写 get_temperature()

```bash
get_temperature() {
    target_type="$1"

    for zone in /sys/class/thermal/thermal_zone*; do
        zone_type=$(cat "$zone/type")

        if [ "$zone_type" = "$target_type" ]; then
            cat "$zone/temp"
            return
        fi
    done
}
```

这样代码依赖的是：

```text
npu-thermal
```

这个设备属性，而不是偶然的：

```text
thermal_zone4
```

编号。

---

## 实操 12：加入温度

```bash
soc_temp_raw=$(get_temperature "soc-thermal")
npu_temp_raw=$(get_temperature "npu-thermal")

soc_temp=$((soc_temp_raw / 1000))
npu_temp=$((npu_temp_raw / 1000))

echo "Temperature: SoC=${soc_temp}°C NPU=${npu_temp}°C"
```

实验：

```text
Temperature: SoC=36°C NPU=37°C
```

---

## 实操 13：处理 SIGINT 和 SIGTERM

加入：

```bash
cleanup() {
    echo "Monitor stopping..."
    exit 0
}

trap cleanup SIGINT SIGTERM
```

运行：

```bash
./rk3576-monitor.sh
```

然后：

```text
Ctrl+C
```

输出：

```text
Monitor stopping...
```

查看：

```bash
echo $?
```

得到：

```text
0
```

说明程序正常退出。

---

## 实操 14：完整 Monitor

```bash
#!/usr/bin/env bash

get_temperature() {
    target_type="$1"

    for zone in /sys/class/thermal/thermal_zone*; do
        zone_type=$(cat "$zone/type")

        if [ "$zone_type" = "$target_type" ]; then
            cat "$zone/temp"
            return
        fi
    done
}

cleanup() {
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
```

示例：

```text
[2026-08-26 03:32:21]
Load: 0.12 0.08 0.02
Memory: 1.0Gi / 7.7Gi
Temperature: SoC=36°C NPU=37°C
```

---

## 实操 15：创建 systemd Service

创建：

```bash
vim rk3576-monitor.service
```

内容：

```ini
[Unit]
Description=RK3576 System Monitor

[Service]
Type=simple
User=cat
WorkingDirectory=/home/cat/rk3576-linux-lab/02-systemd-monitor
ExecStart=/home/cat/rk3576-linux-lab/02-systemd-monitor/rk3576-monitor.sh
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

---

## 实操 16：部署 Service

复制：

```bash
sudo cp rk3576-monitor.service /etc/systemd/system/
```

重新读取 Unit：

```bash
sudo systemctl daemon-reload
```

启动：

```bash
sudo systemctl start rk3576-monitor
```

查看：

```bash
systemctl status rk3576-monitor --no-pager
```

---

## 实操 17：确认 systemd 正在管理进程

获取 Main PID：

```bash
pid=$(systemctl show rk3576-monitor -p MainPID --value)
```

查看：

```bash
echo "Main PID: $pid"
```

再：

```bash
ps -o pid,ppid,user,stat,comm,args -p "$pid"
```

实验实际观察到：

```text
PID      PPID USER
128315   1    cat
```

意味着：

```text
systemd PID 1
     │
     └── rk3576-monitor.sh
```

此时监控程序已经不再由当前 SSH Bash 直接管理。

---

## 实操 18：查看 journal

```bash
sudo journalctl -u rk3576-monitor -n 20 --no-pager
```

可以看到：

```text
Load
Memory
Temperature
```

等脚本输出。

实时查看：

```bash
sudo journalctl -u rk3576-monitor -f
```

按：

```text
Ctrl+C
```

退出。

然后：

```bash
systemctl is-active rk3576-monitor
```

仍然得到：

```text
active
```

原因：

> Ctrl+C 结束的是前台运行的 `journalctl`，不是由 systemd 管理的 Monitor。

---

## 实操 19：正常停止

```bash
sudo systemctl stop rk3576-monitor
```

然后：

```bash
systemctl status rk3576-monitor --no-pager
```

看到：

```text
inactive (dead)
```

日志：

```bash
sudo journalctl -u rk3576-monitor -n 20 --no-pager
```

出现：

```text
Terminated
Monitor stopping...
```

整个过程：

```text
systemctl stop
       ↓
systemd
       ↓
SIGTERM
       ↓
trap
       ↓
cleanup()
       ↓
exit 0
```

---

## 实操 20：验证 Restart=on-failure

启动：

```bash
sudo systemctl start rk3576-monitor
```

保存旧 PID：

```bash
old_pid=$(systemctl show rk3576-monitor -p MainPID --value)
echo "Old PID: $old_pid"
```

故意异常终止：

```bash
sudo kill -9 "$old_pid"
```

这里发送：

```text
SIGKILL
```

查看：

```bash
systemctl status rk3576-monitor --no-pager
```

实验观察到：

```text
Active: activating (auto-restart)
Result: signal
code=killed
signal=KILL
```

日志：

```text
Main process exited, code=killed, status=9/KILL
Failed with result 'signal'
```

几秒后重新启动。

实验中：

```text
Old PID: 129145
New PID: 129322
```

证明：

```text
129145
  │
SIGKILL
  ▼
异常退出
  │
  ▼
systemd
  │
Restart=on-failure
  ▼
等待 RestartSec
  │
  ▼
129322
```

自动恢复成功。

---

## 实操 21：为什么 SIGKILL 没有 cleanup？

`cleanup()` 通过：

```bash
trap cleanup SIGINT SIGTERM
```

处理：

```text
SIGINT
SIGTERM
```

但是 SIGKILL：

> 不能被用户程序捕获。

因此：

```text
SIGKILL
 ↓
Kernel
 ↓
立即结束进程
```

不会出现：

```text
Monitor stopping...
```

这也是正常 stop 与异常 kill 的重要区别。

---

## 实操 22：enable 开机启动

执行：

```bash
sudo systemctl enable rk3576-monitor
```

实验输出：

```text
Created symlink
/etc/systemd/system/multi-user.target.wants/rk3576-monitor.service
→
/etc/systemd/system/rk3576-monitor.service
```

检查：

```bash
systemctl is-enabled rk3576-monitor
```

输出：

```text
enabled
```

检查当前状态：

```bash
systemctl is-active rk3576-monitor
```

输出：

```text
active
```

因此：

```text
enabled + active
```

表示：

> 当前运行，并且配置为开机自动启动。

---

## 实操 23：start 与 enable

一定要区分：

```bash
systemctl start
```

表示：

> **现在启动。**

而：

```bash
systemctl enable
```

表示：

> **建立启动关系，以后系统启动时自动启动。**

因此四种组合都可能存在：

```text
enabled  + active
enabled  + inactive
disabled + active
disabled + inactive
```

---

## 实操 24：修改程序与修改 Service 的区别

### 修改 `rk3576-monitor.sh`

程序代码变化后：

```bash
sudo systemctl restart rk3576-monitor
```

即可重新运行新版本。

### 修改 `rk3576-monitor.service`

需要：

```bash
sudo cp rk3576-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart rk3576-monitor
```

原因：

> systemd 需要重新读取新的 Unit 配置。

可以记成：

```text
改程序
 ↓
restart

改 systemd Unit
 ↓
deploy
 ↓
daemon-reload
 ↓
restart
```

---

# 三、章节总结

这一章最大的变化，是从：

```text
./program
```

进入了：

```text
systemd Service
```

完整结构：

```text
                     Linux Kernel
                          │
                          ▼
                    systemd PID 1
                          │
                          ▼
              rk3576-monitor.service
                          │
                          ▼
                rk3576-monitor.sh
               ┌──────────┼──────────┐
               │          │          │
               ▼          ▼          ▼
          /proc/loadavg   free     sysfs thermal
                                      │
                             ┌────────┴────────┐
                             ▼                 ▼
                         SoC Temp           NPU Temp
```

正常生命周期：

```text
systemctl start
       ↓
systemd
       ↓
ExecStart
       ↓
monitor
       ↓
stdout / stderr
       ↓
journald
       ↓
journalctl
```

正常停止：

```text
systemctl stop
       ↓
SIGTERM
       ↓
trap
       ↓
cleanup()
       ↓
exit 0
```

异常退出：

```text
Crash / SIGKILL
       ↓
failure
       ↓
Restart=on-failure
       ↓
systemd 启动新进程
```

完成本章以后，对：

```bash
systemctl start xxx
```

的理解不应该只是：

> “这是启动服务的命令。”

而应该能够进一步想到：

```text
systemctl
 ↓
systemd PID 1
 ↓
读取 Unit
 ↓
执行 ExecStart
 ↓
创建和管理进程
 ↓
监听退出状态
 ↓
根据 Restart Policy 决定下一步
```

这套服务管理机制以后会直接用于：

```text
机器人后台节点
传感器程序
网络服务
摄像头服务
RKNN 推理程序
RKLLM 服务
```

---

# 四、课后问题

## 基础题

1. `sleep 1000` 和 `sleep 1000 &` 最大区别是什么？
2. 后台进程是否就等于 Linux Service？
3. `jobs` 和 `ps` 的观察对象有什么区别？
4. PID 和 PPID 分别是什么？
5. `$!` 表示什么？
6. 为什么直接输入 `$!` 会出现 `command not found`？
7. `while true` 为什么会形成无限循环？
8. Load Average 是 CPU 使用率百分比吗？
9. `/proc/loadavg` 与 Linux Kernel 是什么关系？
10. `/sys/class/thermal` 在本项目中用于做什么？

## Shell 编程题

11. 函数中的 `$1` 表示什么？
12. `for zone in ...` 在做什么？
13. `if [ "$a" = "$b" ]` 在做什么？
14. 为什么不能认为 `thermal_zone4` 永远是 NPU？
15. `$((npu_temp_raw / 1000))` 使用了什么 Shell 机制？
16. `free -h | awk ...` 中管道左右分别在做什么？
17. `trap cleanup SIGINT SIGTERM` 的作用是什么？
18. `exit 0` 中的 `0` 表示什么？

## Signal 题

19. Ctrl+C 通常会发送什么 Signal？
20. `systemctl stop` 正常停止 Service 时通常使用什么 Signal？
21. SIGTERM 和 SIGKILL 最大的区别是什么？
22. 为什么 `kill -9` 后不会执行 `cleanup()`？
23. 为什么不建议一遇到程序停止不了就直接使用 `kill -9`？

## systemd 题

24. systemd 和 systemctl 是什么关系？
25. PID 1 在本实验系统中是什么程序？
26. `[Unit]`、`[Service]`、`[Install]` 分别负责什么？
27. `ExecStart` 是做什么的？
28. 为什么本项目使用 `User=cat` 而不是 root？
29. 什么是最小权限原则？
30. `Restart=on-failure` 有什么作用？
31. `RestartSec=3` 为什么有意义？
32. 修改 `.service` 文件后为什么需要 `daemon-reload`？
33. `daemon-reload` 会自动 restart Service 吗？
34. `start` 和 `enable` 的本质区别是什么？
35. `WantedBy=multi-user.target` 与 `systemctl enable` 是怎样联系起来的？
36. 为什么 Service 的 `echo` 可以通过 journalctl 查看？
37. 为什么退出 `journalctl -f` 不会停止 Service？

## 综合题

38. 请解释下面这条完整链路：

```text
systemctl stop
→ systemd
→ SIGTERM
→ trap
→ cleanup()
→ exit 0
```

39. 请解释：

```text
kill -9
→ SIGKILL
→ Service failure
→ Restart=on-failure
→ 新 PID
```

40. 如果修改了 `rk3576-monitor.sh`，应该怎样部署？
41. 如果修改了 `rk3576-monitor.service`，部署流程有什么不同？
42. 为什么“能够在后台运行”仍然不足以称为一个可靠的 Linux Service？
43. 为什么 systemd 管理的是“服务生命周期”，而不仅仅是“执行一次命令”？

