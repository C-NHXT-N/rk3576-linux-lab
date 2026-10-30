# 02-2 处理文本，完成第一版巡检

> 建议时间：20—40 分钟（含独立练习） · 状态：已编写；验证范围见环境记录
>
> 执行位置：除特别标注外，均为 **RK3576 的 Bash 终端**。普通用户执行；带 `sudo` 的步骤才需要管理员权限。
>
> 环境：先按[环境说明](../environment.md)设置 `RKLAB_ROOT`。先修课见页尾“上一课”；首次阅读从课程总目录开始。

## 这课完成什么

- 能按行、字段处理命令输出。
- 能独立生成只包含系统身份的报告。

## 跟着做：解释、预测、操作、观察


### 1. 从原始数据到需要的字段

```bash
head -n 5 /etc/os-release
grep '^PRETTY_NAME=' /etc/os-release
grep '^PRETTY_NAME=' /etc/os-release | cut -d= -f2-
```

`^` 表示行首；`cut -d= -f2-` 按等号分隔，保留第二字段及以后内容。本课选择简单身份文件练习；不要随意 source 从网上获得的文件，因为 source 会执行内容。

接着观察一条短记录：

```bash
cat /proc/loadavg
cut -d' ' -f1-3 /proc/loadavg
awk '{print $1, $2, $3}' /proc/loadavg
```

这里先研究文本处理，load 含义在系统观察课讲解。awk 默认按空白划分字段，`$1` 是第一字段；awk 的单引号让这些符号交给 awk，而不是 Bash 展开。

### 2. 先做一个能解释的报告

创建 `~/rk3576-practice/my-report.sh`，写入：

```bash
#!/usr/bin/env bash
printf 'User: %s\n' "$(whoami)"
printf 'Host: %s\n' "$(hostname)"
printf 'Kernel: %s\n' "$(uname -r)"
printf 'Architecture: %s\n' "$(uname -m)"
grep '^PRETTY_NAME=' /etc/os-release
```

```bash
bash -n ~/rk3576-practice/my-report.sh
bash ~/rk3576-practice/my-report.sh
bash "$RKLAB_ROOT/01-system-inspector/system_report.sh" --section identity
```

**先预测：** 两份报告排版不同，哪些信息应该一致？比较关键字段，而不是要求所有空格和字面值一样。

### 3. 为什么有时解析结果为空

`grep` 无匹配时返回 1，不一定表示程序损坏。工具输出可能受语言环境或版本影响；项目脚本使用 `LC_ALL=C` 固定解析语言，监控项目用稳定的数值列并注明单位。遇到空结果时先直接查看原命令输出，再检查匹配条件。


## 自己完成一次

为自己的报告增加“生成时间”和“当前目录”，保存到 report.txt；随后从另一个目录运行，解释哪些字段会变化。

<details>
<summary>提示一：先想方向</summary>

区分设备身份与运行时上下文。

</details>

<details>
<summary>提示二：关键工具</summary>

`date`、`pwd`、`$()`、`>`。

</details>

<details>
<summary>参考思路与解释（先尝试再展开）</summary>

用 date 生成时间、pwd 获取调用时目录；用户名和内核通常不变，工作目录随启动位置变化。保存成功后同时检查文件内容和退出状态。

</details>

## 完成标准

- [ ] 能解释报告中的每条命令。
- [ ] 能自行增加两个字段。
- [ ] 明白第一版尚未包括全部系统知识，后续逐步扩展。

勾选属于自评，不能替代实际结果。请保留命令与关键现象，并用自己的话解释一次。

## 清理与回顾

保留 my-report.sh；report.txt 为自己的实验输出，确认后可以 rm -i 删除。后续系统观察课完成后，再使用完整巡检报告。

---

上一课：[02-1 输入输出、变量与退出状态](01-streams-variables.md) · 下一课：[02-3 判断、循环、函数与参数](03-control-flow.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
