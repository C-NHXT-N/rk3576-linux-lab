# 03-2 进程、作业与信号

> 建议时间：20—40 分钟（含独立练习） · 状态：已编写；验证范围见环境记录
>
> 执行位置：除特别标注外，均为 **RK3576 的 Bash 终端**。普通用户执行；带 `sudo` 的步骤才需要管理员权限。
>
> 环境：先按[环境说明](../environment.md)设置 `RKLAB_ROOT`。先修课见页尾“上一课”；首次阅读从课程总目录开始。

## 这课完成什么

- 能保存并观察自己创建的后台进程。
- 能解释 PID/PPID、jobs/ps、SIGINT/SIGTERM/SIGKILL。

## 跟着做：解释、预测、操作、观察


### 1. 用当前 Shell 启动一个可控对象

```bash
echo $$
sleep 120 &
lab_pid=$!
printf 'child=%s\n' "$lab_pid"
jobs
ps -p "$$,$lab_pid" -o pid,ppid,user,state,comm
ls "/proc/$lab_pid"
```

`$$` 是当前 Shell PID，`$!` 是最近一次后台任务的 PID，应立即保存，避免被后续后台任务覆盖。`jobs` 属于当前 Shell 的作业表，`ps` 观察系统中的进程；不同终端的 jobs 可能不同。

PID 标识进程，PPID 标识父进程。本例 sleep 的父进程通常是当前 Bash。不要照抄示例数字，更不要把未知 PID 传给 kill。

### 2. 让进程正常结束，再观察 procfs

**先预测：** sleep 结束后，它的 /proc 目录还会一直存在吗？

```bash
kill -TERM "$lab_pid"
wait "$lab_pid"
ps -p "$lab_pid" -o pid,ppid,comm
ls "/proc/$lab_pid"
```

wait 负责等待并回收自己的子进程；被信号终止通常有非零状态。之后 /proc 路径消失是预期。进程刚退出但未回收时可能暂为僵尸，因此“进程结束即瞬时消失”不是所有时刻都成立的保证。

### 3. 信号请求与处理机会

SIGINT 常由 Ctrl+C 发送给前台进程组；SIGTERM 请求结束，可被程序处理；SIGKILL 无法被捕获和清理，只用于本课专门安排的异常恢复实验。后台运行不等于可靠服务，进程仍涉及会话、终端与父进程关系。

创建 `~/rk3576-practice/signal.sh`：

```bash
#!/usr/bin/env bash
trap 'echo "cleanup done"; exit 0' INT TERM
while true; do
    echo 'running'
    sleep 1
done
```

```bash
bash ~/rk3576-practice/signal.sh
```

按 Ctrl+C，观察 cleanup done。trap 注册处理函数；外部命令正在前台运行时，Bash 的处理时机可能延后。正式监控脚本单独管理 sleep 子进程，使 TERM 时可以及时清理。

### 常见问题

运行 `$!` 是尝试执行数字；只看到 ps 的一部分结果不代表其余进程不存在；重新登录后 jobs 为空不代表所有后台进程都停止了。先确定观察对象和会话，再下结论。


## 自己完成一次

新开一个 SSH 终端，比较两个终端的 jobs 和 ps。解释为什么“当前终端看不到某个作业”和“系统不存在该进程”不是同一件事。

<details>
<summary>提示一：先想方向</summary>

Shell 的作业表和内核进程列表不在同一层。

</details>

<details>
<summary>提示二：关键工具</summary>

`jobs`、`ps -e`、保存的 lab_pid。

</details>

<details>
<summary>参考思路与解释（先尝试再展开）</summary>

终端 A 启动并保存自己的 sleep PID；终端 B 的 jobs 不包含它，但可以用 ps -p PID 查询。清理由 A 执行 kill 和 wait，避免操作其他人的进程。

</details>

## 完成标准

- [ ] 没有使用抄写的固定 PID。
- [ ] 自己的 sleep 已终止并回收。
- [ ] 能解释三种信号和后台任务与服务的区别。

勾选属于自评，不能替代实际结果。请保留命令与关键现象，并用自己的话解释一次。

## 清理与回顾

确认所有本课创建的 sleep 和 signal.sh 已结束，退出第二个 SSH 会话。只有仍在运行且已确认属于自己的 PID 才需要清理。

---

上一课：[03-1 CPU、内存与系统负载](01-system-observation.md) · 下一课：[04-1 综合项目：逐步完成系统巡检](../04-services/01-inspector.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
