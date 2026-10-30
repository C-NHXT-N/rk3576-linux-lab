# 02-1 输入输出、变量与退出状态

> 建议时间：20—40 分钟（含独立练习） · 状态：已编写；验证范围见环境记录
>
> 执行位置：除特别标注外，均为 **RK3576 的 Bash 终端**。普通用户执行；带 `sudo` 的步骤才需要管理员权限。
>
> 环境：先按[环境说明](../environment.md)设置 `RKLAB_ROOT`。先修课见页尾“上一课”；首次阅读从课程总目录开始。

## 这课完成什么

- 能区分 stdout、stderr 和退出状态。
- 能解释引号、变量与命令替换。

## 跟着做：解释、预测、操作、观察


### 1. 一个程序可以同时有结果和状态

```bash
cd ~/rk3576-practice
ls /this-course-path-does-not-exist > out.txt 2> error.txt
status=$?
printf 'status=%s\n' "$status"
cat out.txt
cat error.txt
```

默认 0/1/2 分别是标准输入、标准输出、标准错误的文件描述符。`>` 重定向 stdout，`2>` 重定向 stderr；失败信息进入 error.txt，退出状态通常非零。必须立即保存 `$?`，后续命令会更新它。

**先预测：** `cat error.txt` 成功后再 `echo $?`，看到的还是 ls 的状态吗？实际验证并解释。

### 2. 把一个命令的输出作为另一个命令的输入

```bash
head -n 8 /etc/os-release | grep '^NAME='
```

管道 `|` 把左侧 stdout 连接到右侧 stdin，不会默认传递 stderr。Shell 默认使用管道末条命令的退出状态；`set -o pipefail` 让前面失败也能影响整体状态。

```bash
false | cat
echo $?
set -o pipefail
false | cat
echo $?
set +o pipefail
```

`false` 返回失败，`cat` 正常处理空输入。本例用来区别“管道成功”和“每个步骤成功”。

### 3. 保存输出，不是保存退出状态

```bash
kernel_value=$(uname -r)
printf 'Kernel: %s\n' "$kernel_value"
printf '%s\n' '$kernel_value' "$kernel_value"
```

变量赋值的等号两侧不能有空格。`$()` 执行命令并捕获 stdout（去掉末尾换行）；双引号允许变量展开，单引号保留字面文本。使用 `"$variable"` 可避免内容被重新分词或进行通配符展开。

`>>` 追加而不是覆盖；`2>/dev/null` 丢弃错误输出，`2>&1` 让 stderr 连接到当时 stdout 的去向。排错时先保留错误，确认缺失确实可接受后再隐藏。

### 常见问题

`name = value` 会被当作执行名为 name 的命令；直接输入 `$!` 或 `$variable` 会尝试执行展开结果。`echo "$(free -h)"` 只是多做一次捕获与输出；无需保存时直接运行工具更清楚。


## 自己完成一次

让脚本把正常信息写到 stdout，把一条提示写到 stderr，并以状态 3 退出；分别保存两种输出与退出码。

<details>
<summary>提示一：先想方向</summary>

输出通道与进程状态是三件事。

</details>

<details>
<summary>提示二：关键工具</summary>

`echo ... >&2`、`exit 3`、`> result.txt 2> warning.txt`。

</details>

<details>
<summary>参考思路与解释（先尝试再展开）</summary>

脚本中依次写 echo、echo >&2、exit 3；调用后立即 status=$?。即使正常信息不为空，退出仍可失败。

</details>

## 完成标准

- [ ] 能保存并解释三个独立结果。
- [ ] 能预测单引号与双引号的区别。
- [ ] 能解释 pipefail 对示例的影响。

勾选属于自评，不能替代实际结果。请保留命令与关键现象，并用自己的话解释一次。

## 清理与回顾

删除自己本课创建的 out.txt、error.txt、result.txt、warning.txt 和实验脚本；先 ls 检查后使用 rm -i 指定名称。不要清理 hello.sh。

---

上一课：[01-5 一棵目录树，多种文件系统](../01-files/05-mounts-interfaces.md) · 下一课：[02-2 处理文本，完成第一版巡检](02-text-report.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
