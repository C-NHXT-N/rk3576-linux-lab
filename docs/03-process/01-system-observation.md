# 03-1 CPU、内存与系统负载

> 建议时间：20—40 分钟（含独立练习） · 状态：已编写；验证范围见环境记录
>
> 执行位置：除特别标注外，均为 **RK3576 的 Bash 终端**。普通用户执行；带 `sudo` 的步骤才需要管理员权限。
>
> 环境：先按[环境说明](../environment.md)设置 `RKLAB_ROOT`。先修课见页尾“上一课”；首次阅读从课程总目录开始。

## 这课完成什么

- 能解释系统工具与 procfs 的关系。
- 能区分空闲内存、可用内存、负载与 CPU 使用率。

## 跟着做：解释、预测、操作、观察


### 1. 同一个系统，多个观察入口

```bash
uname -m
lscpu
nproc
head -n 30 /proc/cpuinfo
```

`lscpu` 汇总架构与 CPU 信息；`nproc` 反映当前进程可用的处理器数量，可能受亲和性或资源限制影响，不总等于芯片物理核心数。不要因为一条工具输出缺少型号，就直接断言硬件不同。

### 2. Linux 会把空闲内存用于缓存

```bash
free -h
grep -E '^(MemTotal|MemFree|MemAvailable|Cached):' /proc/meminfo
```

**先预测：** free 很小、available 仍较大，能直接判定内存耗尽吗？

`MemFree` 是未使用内存，`MemAvailable` 是内核对无需交换即可供新应用使用内存的估计。缓存中的部分内存可回收，因此“已使用”与“完全不可再分配”不相同。不同版本 free 的 used 计算方式可能变化，先确认字段与单位。

### 3. 负载不是百分比

```bash
uptime
cat /proc/loadavg
```

前三项为约 1、5、15 分钟负载平均值；Linux 负载包含可运行任务以及部分不可中断等待任务。高负载可能与 CPU 或 I/O 等待有关，不能单独推出 CPU 使用率。八核设备也不能把某个负载值直接乘固定系数当作占用率。

可用 `top` 继续查看实际进程与 CPU 情况，按 `q` 退出。先看趋势和进程证据，再推导原因。

### 4. 逐步扩展巡检项目

```bash
bash "$RKLAB_ROOT/01-system-inspector/system_report.sh" --section memory
bash "$RKLAB_ROOT/01-system-inspector/system_report.sh" --section storage
```

memory 模块包含 CPU 与内存；storage 回顾前面学过的块设备、挂载与空间。现在应能解释这些部分，不必提前解释尚未学习的网络服务。

### 常见错误

混淆 GiB 与 GB、把负载写成百分比、把全部缓存当成浪费、认为 nproc 必须在所有环境返回固定数值。记录工具版本与原始输出，比记住作者截图里的数字更有价值。


## 自己完成一次

在间隔几秒的两次观察中记录 available 与负载，写出一个“观察事实”和一个“尚不能确认的原因”。

<details>
<summary>提示一：先想方向</summary>

把测量结果与原因判断分开。

</details>

<details>
<summary>提示二：关键工具</summary>

`free -h`、`uptime`、`top`。

</details>

<details>
<summary>参考思路与解释（先尝试再展开）</summary>

可以说“available 两次不同”；不能仅此断言内存泄漏。负载上升也需要结合进程、CPU 与 I/O 信息。

</details>

## 完成标准

- [ ] 能解释 free 与 available。
- [ ] 不把 load average 当作百分比。
- [ ] 能解释巡检的 CPU、内存和存储输出。

勾选属于自评，不能替代实际结果。请保留命令与关键现象，并用自己的话解释一次。

## 清理与回顾

只读观察，无需清理。退出 top，保留两次观察记录。

---

上一课：[02-3 判断、循环、函数与参数](../02-shell/03-control-flow.md) · 下一课：[03-2 进程、作业与信号](02-jobs-signals.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
