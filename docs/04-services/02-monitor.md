# 04-2 从一次报告到持续监控

> 建议时间：20—40 分钟（含独立练习） · 状态：已编写；验证范围见环境记录
>
> 执行位置：除特别标注外，均为 **RK3576 的 Bash 终端**。普通用户执行；带 `sudo` 的步骤才需要管理员权限。
>
> 环境：先按[环境说明](../environment.md)设置 `RKLAB_ROOT`。先修课见页尾“上一课”；首次阅读从课程总目录开始。

## 这课完成什么

- 能按设备属性查温度，并明确表示缺失读数。
- 能有限采样、持续运行并处理停止信号。

## 跟着做：解释、预测、操作、观察


### 1. 先理解数据源

```bash
for zone in /sys/class/thermal/thermal_zone*; do
    [ -r "$zone/type" ] || continue
    printf '%s: ' "$zone"
    cat "$zone/type"
    cat "$zone/temp"
done
```

`|| continue` 表示前面的判断失败时跳过当前项。type 描述 thermal zone 类型；temp 通常以毫摄氏度表示。不要固定“zone4 一定是 NPU”，编号可能随镜像、内核或设备树变化。type 名称本身也需按实际 BSP 确认。

### 2. 先有限采样，再持续运行

```bash
cd "$RKLAB_ROOT"
bash 02-systemd-monitor/rk3576-monitor.sh --once
bash 02-systemd-monitor/rk3576-monitor.sh --samples 2 --interval 1
```

**先预测：** `--samples 2` 结束时，应有几条时间戳？温度数据缺失时应显示多少度？

参考实现把 SoC/NPU 温度按 type 查找，读不到显示 N/A，非法读数也不会转换为 0。正常 0 是有效温度，与缺失不同。内存以 MiB 输出，load 不加百分号。

### 3. 跟踪一次正常停止

```bash
bash 02-systemd-monitor/rk3576-monitor.sh --interval 1 &
monitor_pid=$!
sleep 2
kill -TERM "$monitor_pid"
wait "$monitor_pid"
echo $?
```

应输出 Monitor stopping...，退出状态为 0。脚本的 trap 调用 cleanup，清理等待中的 sleep 子进程。完整代码见[监控源码](../../02-systemd-monitor/rk3576-monitor.sh)。

### 4. 构造缺失传感器，而不修改系统

```bash
mkdir -p "$RKLAB_ROOT/run/empty-thermal"
RK3576_THERMAL_ROOT="$RKLAB_ROOT/run/empty-thermal" bash 02-systemd-monitor/rk3576-monitor.sh --once
```

该环境变量仅为可重复测试替换读取目录；默认仍读真实 sysfs。它没有创建或伪造真实传感器。本次应明确显示 not found，验证的是错误处理。

### 排错

没有 npu-thermal 不代表没有 NPU；先看本板的 type。读取失败先检查路径、权限和原始内容。不要向 sysfs 写入测试温度；使用自己的测试目录。


## 自己完成一次

在自己的 run 目录构造一个 type 为 npu-thermal、temp 为 42000 的测试 zone。验证 42.0 C 后，把 temp 改为非数字，确认出现 invalid reading。

<details>
<summary>提示一：先想方向</summary>

只替换输入目录，不触碰 /sys。

</details>

<details>
<summary>提示二：关键工具</summary>

mkdir、printf、RK3576_THERMAL_ROOT，以及 --once。

</details>

<details>
<summary>参考思路与解释（先尝试再展开）</summary>

测试目录含 thermal_zone任意编号/type 与 temp；写入时带换行。先测试 42000、再测试 broken，检查正常与错误分支。这个模拟只证明脚本逻辑，不证明硬件温度。

</details>

## 完成标准

- [ ] 单次、有限次数和正常停止均符合预期。
- [ ] 缺失、无效和真实零读数可区分。
- [ ] 说明为何不能固定 thermal zone 编号。

勾选属于自评，不能替代实际结果。请保留命令与关键现象，并用自己的话解释一次。

## 清理与回顾

确认后台进程已 wait 回收；删除自己 run 目录的测试 type/temp 文件，再用 rmdir 删除空测试目录。真实 /sys 保持只读。

---

上一课：[04-1 综合项目：逐步完成系统巡检](01-inspector.md) · 下一课：[04-3 接口、地址、路由和监听端口](03-network.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
