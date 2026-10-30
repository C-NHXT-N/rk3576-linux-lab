# 04-1 综合项目：逐步完成系统巡检

> 建议时间：20—40 分钟（含独立练习） · 状态：已编写；验证范围见环境记录
>
> 执行位置：除特别标注外，均为 **RK3576 的 Bash 终端**。普通用户执行；带 `sudo` 的步骤才需要管理员权限。
>
> 环境：先按[环境说明](../environment.md)设置 `RKLAB_ROOT`。先修课见页尾“上一课”；首次阅读从课程总目录开始。

## 这课完成什么

- 能组合前面学过的知识形成可用报告。
- 能区分必要命令失败、可选设备缺失与结论不充分。

## 跟着做：解释、预测、操作、观察


### 1. 回顾已经能解释的模块

```bash
cd "$RKLAB_ROOT"
bash 01-system-inspector/system_report.sh --section identity
bash 01-system-inspector/system_report.sh --section memory
bash 01-system-inspector/system_report.sh --section storage
bash 01-system-inspector/system_report.sh --section process
```

前面自己写过第一版身份报告；现在给自己的版本增加内存、挂载与进程数量。先直接运行原命令，确认理解后再组合。这里的“进程数量”是当次观察，不是永远固定的硬件属性。

### 2. 阅读参考实现，而不是一次复制整份代码

[参考源码](../../01-system-inspector/system_report.sh) 是唯一完整版本。先看 selected 与 heading 如何选择模块、组织输出，再看 required 如何记录必需命令失败。

```bash
sed -n '1,90p' 01-system-inspector/system_report.sh
bash -n 01-system-inspector/system_report.sh
bash 01-system-inspector/system_report.sh --section devices
```

`sed -n '1,90p'` 打印指定行范围。没有匹配节点时输出 N/A，属于可接受的环境差异；缺少必需工具则应打印错误并返回非零。脚本不因为打印了几个标题就宣称成功。

### 3. 新的网络部分先保留观察问题

**先预测：** 同一块板卡能否有多个 IP？22 端口监听是否证明任意电脑都能登录？

```bash
bash 01-system-inspector/system_report.sh --section network
```

本节记录输出；[网络课](03-network.md) 集中解释接口、地址、路由、监听与连接。遇到 systemd 或网络字段时，不需要在这里再次展开全部知识。

### 4. 保存完整成果

```bash
mkdir -p run
bash 01-system-inspector/system_report.sh > run/system-report.txt
report_status=$?
printf 'report exit=%s\n' "$report_status"
python3 tools/check_lab.py inspector
```

检查器会重新生成一次只读报告并检查关键模块，不会安装或修改系统。它验证基本结构，不能替你证明每个字段的理解或内容准确性。

### 排错

运行失败先看 stderr，不要先加 sudo。设备节点缺失先判断是否确实需要该设备；`/dev/dri/renderD*` 也只是候选入口，不能仅凭节点名判断 NPU 可用。


## 自己完成一次

为自己的报告增加一个磁盘信息字段，故意写错一个命令再修复；保证失败时能在错误输出和退出状态上发现问题。

<details>
<summary>提示一：先想方向</summary>

先明确成功标准，再决定如何传播失败。

</details>

<details>
<summary>提示二：关键工具</summary>

`findmnt /`、`if ! command; then ...; fi`、脚本结尾 `exit`。

</details>

<details>
<summary>参考思路与解释（先尝试再展开）</summary>

把必需步骤失败保存为状态，最终非零退出。无需因为没有摄像头就把整份巡检标为失败；必需条件与可选资源要明确。

</details>

## 完成标准

- [ ] 自己的脚本至少含身份、内存、存储和进程信息。
- [ ] 完整参考报告检查通过。
- [ ] 能解释缺失设备与硬件不存在的区别。

勾选属于自评，不能替代实际结果。请保留命令与关键现象，并用自己的话解释一次。

## 清理与回顾

保留自己的实现；run/system-report.txt 可在比较后删除。网络细节在后两课补齐，下一课先建立受控监控程序。

---

上一课：[03-2 进程、作业与信号](../03-process/02-jobs-signals.md) · 下一课：[04-2 从一次报告到持续监控](02-monitor.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
