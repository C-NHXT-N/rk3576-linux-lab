# 00-2 读懂命令、查帮助与编辑文件

> 建议时间：20—40 分钟（含独立练习） · 状态：已编写；验证范围见环境记录
>
> 执行位置：除特别标注外，均为 **RK3576 的 Bash 终端**。普通用户执行；带 `sudo` 的步骤才需要管理员权限。
>
> 环境：先按[环境说明](../environment.md)设置 `RKLAB_ROOT`。先修课见页尾“上一课”；首次阅读从课程总目录开始。

## 这课完成什么

- 能区分命令名、选项、参数。
- 能查工具位置和帮助，编辑并运行一个小脚本。

## 跟着做：解释、预测、操作、观察


### 1. 命令不是不可拆分的一串字符

```bash
command -v bash
ls --help
man ls
```

在 `man` 中按 `q` 退出、输入 `/pattern` 搜索。若没有 `man`，先用 `--help`，不要因此中断学习。`command -v` 帮助判断命令是否存在。

以 `head -n 3 /etc/os-release` 为例：`head` 是命令，`-n 3` 指定行数，最后的路径是读取对象。选项大小写可能有不同含义。

**先预测：** 把 `-n` 写成 `-nn`，报错更可能来自文件还是参数解析？执行对照：

```bash
head -n 3 /etc/os-release
head -nn 3 /etc/os-release
```

后一个命令用来观察错误，出现失败是本课预期，不必复制更多未知命令。

### 2. 先学会编辑自己的文件

```bash
mkdir -p ~/rk3576-practice
cd ~/rk3576-practice
command -v nano
nano hello.sh
```

若 `nano` 不存在，可按环境说明安装；使用 `vim` 时，按 `i` 输入，按 Esc 后输入 `:wq` 保存退出，`:q!` 放弃本次修改退出。

在编辑器写入以下内容（不要把 Markdown 的反引号写入文件）：

```bash
#!/usr/bin/env bash
echo 'hello from my board'
```

保存后在终端执行：

```bash
cat hello.sh
bash -n hello.sh
bash hello.sh
```

`cat` 查看内容，`bash -n` 仅检查语法，`bash hello.sh` 让 Bash 读取并执行脚本；这种方式暂时不要求脚本具有执行权限。

### 3. 常见问题

`command not found`：检查拼写和命令是否安装。`No such file or directory`：先 `pwd`、`ls`，确认所在目录和文件名。出现 `>` 提示符：可能引号未闭合，可按 Ctrl+C 取消本次输入后重写。不要把 `$` 提示符一并复制。


## 自己完成一次

把脚本改成输出两行，第二行说明这是开发板上的 Bash 在执行。故意漏写一个单引号，用语法检查定位，再修复。

<details>
<summary>提示一：先想方向</summary>

先检查源文件，再运行，避免混淆编辑和执行。

</details>

<details>
<summary>提示二：关键工具</summary>

`cat`、`bash -n`、`bash`。

</details>

<details>
<summary>参考思路与解释（先尝试再展开）</summary>

两条 `echo` 可输出两行；单引号必须配对。`bash -n` 通过仅说明解析成功，不证明输出符合需求。

</details>

## 完成标准

- [ ] 能独立保存并运行脚本。
- [ ] 能退出编辑器和帮助页。
- [ ] 能解释语法检查与逻辑验证的区别。

勾选属于自评，不能替代实际结果。请保留命令与关键现象，并用自己的话解释一次。

## 清理与回顾

保留 `~/rk3576-practice/hello.sh`，权限课会再次使用。按 Ctrl+C 只结束当前前台操作；不要用它替代保存文件。

---

上一课：[00-1 从电脑连接到开发板](01-connect.md) · 下一课：[01-1 你在哪里：目录与路径](../01-files/01-paths.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
