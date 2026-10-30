# 02-3 判断、循环、函数与参数

> 建议时间：20—40 分钟（含独立练习） · 状态：已编写；验证范围见环境记录
>
> 执行位置：除特别标注外，均为 **RK3576 的 Bash 终端**。普通用户执行；带 `sudo` 的步骤才需要管理员权限。
>
> 环境：先按[环境说明](../environment.md)设置 `RKLAB_ROOT`。先修课见页尾“上一课”；首次阅读从课程总目录开始。

## 这课完成什么

- 能写有限循环、带参数函数和条件分支。
- 能解释参考脚本为何需要校验参数与处理缺失资源。

## 跟着做：解释、预测、操作、观察


### 1. 先从有限循环开始

```bash
for item in first second third; do
    printf 'item=%s\n' "$item"
done
```

for 依次赋值并执行循环体。先练有限次数，再运行长期程序，避免不知如何停止。

创建 `~/rk3576-practice/loop.sh`：

```bash
#!/usr/bin/env bash
count=0
while [ "$count" -lt 3 ]; do
    printf 'sample=%s\n' "$count"
    count=$((count + 1))
    sleep 1
done
```

`[ ... ]` 是条件命令，方括号与参数之间需要空格；`-lt` 比较整数。`$((...))` 执行整数算术，`while` 在条件退出状态为 0 时继续。`while true` 则需其他停止条件或信号。

### 2. 把可重复任务写成函数

```bash
show_file() {
    local target=$1
    if [ -r "$target" ]; then
        head -n 2 "$target"
    else
        printf 'Cannot read: %s\n' "$target" >&2
        return 1
    fi
}
show_file /etc/os-release
show_file /this-course-path-does-not-exist
```

函数中 `$1` 是第一个函数参数；脚本顶层的 `$1` 是脚本参数。`local` 限定函数变量，`return` 结束函数，`exit` 结束脚本。函数可通过 stdout 返回文本、通过退出状态表示是否成功，二者不要混淆。

### 3. 从小例子读懂项目的工程处理

```bash
case "$(uname -m)" in
    aarch64) echo 'ARM64' ;;
    *) echo 'another architecture' ;;
esac
```

`case` 选择匹配分支。Bash 参考脚本还使用 `[[ ... ]]` 判断、`=~` 正则验证、数组保存路径、`shift` 消费参数、`set -u` 检测未设置变量、pipefail 传播管道失败。它们是后续参考实现的阅读工具；不要求现在从零默写全部。

**先预测：** 温度读取函数找不到传感器时，如果直接做整数除法，会不会把缺失误写成 0？项目选择明确输出 N/A，让“读不到”和“确实为零”分开。


## 自己完成一次

把 loop.sh 改成接受一个正整数参数作为采样次数。没有参数时使用 3，输入非数字时打印错误并退出，不能进入无限循环。

<details>
<summary>提示一：先想方向</summary>

先处理输入，再执行循环。

</details>

<details>
<summary>提示二：关键工具</summary>

`${1:-3}` 提供默认值；`[[ $value =~ ^[0-9]+$ ]]` 检查数字，需额外拒绝 0。

</details>

<details>
<summary>参考思路与解释（先尝试再展开）</summary>

先校验再算术。本课程参考脚本还限制位数并按十进制处理，避免 08 被解释为八进制。输入 2 时恰好采样两次，输入 abc 时非零退出。

</details>

## 完成标准

- [ ] 有限循环可正常结束。
- [ ] 能区分函数参数、脚本参数、return 和 exit。
- [ ] 无效参数不会开始采样。

勾选属于自评，不能替代实际结果。请保留命令与关键现象，并用自己的话解释一次。

## 清理与回顾

保留自己编写的脚本用于回顾；程序应已自然退出。下一模块研究运行中的程序究竟是什么。

---

上一课：[02-2 处理文本，完成第一版巡检](02-text-report.md) · 下一课：[03-1 CPU、内存与系统负载](../03-process/01-system-observation.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
