# 01-1 你在哪里：目录与路径

> 建议时间：20—40 分钟（含独立练习） · 状态：已编写；验证范围见环境记录
>
> 执行位置：除特别标注外，均为 **RK3576 的 Bash 终端**。普通用户执行；带 `sudo` 的步骤才需要管理员权限。
>
> 环境：先按[环境说明](../environment.md)设置 `RKLAB_ROOT`。先修课见页尾“上一课”；首次阅读从课程总目录开始。

## 这课完成什么

- 能区分根目录、用户家目录和当前目录。
- 能在改变当前目录后，判断路径指向哪里。

## 跟着做：解释、预测、操作、观察


### 1. 先建立三个位置

`/` 是整棵目录树的根；`~` 由 Shell 展开为当前用户的家目录；当前目录是本次 Shell 查找相对路径的起点。家目录与根目录不是同一个概念。

```bash
cd ~
pwd
printf '%s\n' ~
ls -ld / . ..
```

`pwd` 显示当前位置，`.` 表示当前目录，`..` 表示父目录。`ls -ld` 查看目录本身；如果省略 `-d`，通常会列出目录里的内容。

### 2. 建一个能反复观察的小场景

```bash
mkdir -p ~/rk3576-practice/files/notes
mkdir -p ~/rk3576-practice/files/archive
cd ~/rk3576-practice/files
printf 'hello linux\n' > notes/hello.txt
cat notes/hello.txt
```

`mkdir -p` 创建缺失的父目录，已有目录不报错。`>` 将本次输出写入指定文件，若文件已存在会覆盖；这里只写课程练习文件。

**先预测：** 进入 `archive` 后，再用 `notes/hello.txt` 会怎样？

```bash
cd archive
pwd
cat notes/hello.txt
cat ../notes/hello.txt
cat ~/rk3576-practice/files/notes/hello.txt
```

第一条 `cat` 会尝试寻找 `archive/notes/hello.txt`，预期失败。`../notes/hello.txt` 先返回上级，再进入 notes；最后一条通过家目录定位，不依赖当前目录。

以 `/` 开头的是绝对路径。`notes/...` 和 `../notes/...` 都是相对路径。单引号中的 `'~/...'` 不会展开家目录，不能把它当成上面的路径。

### 3. 用同一个文件验证，而不是记结论

```bash
cd /
cat ~/rk3576-practice/files/notes/hello.txt
cd ~/rk3576-practice/files
```

改变当前目录没有移动文件；它改变的是相对路径的解析起点。`cd` 作用于当前 Shell，所以终端 A 的 `cd` 不会替终端 B 切目录。

### 排错顺序

看到找不到文件时：先 `pwd`，再查看目标父目录，再检查拼写、大小写和开头的 `/`。只有这些事实确认后，再判断文件是否被删除。不要把预期的相对路径失败误判成磁盘故障。


## 自己完成一次

进入 `notes`，分别用相对路径与绝对路径读取同一个 hello.txt。再进入 `/tmp`，解释哪一种路径可以保持不变。

<details>
<summary>提示一：先想方向</summary>

画出当前位置和目标文件之间的目录关系。

</details>

<details>
<summary>提示二：关键工具</summary>

`pwd`、`cat ./hello.txt`、`cat ~/rk3576-practice/files/notes/hello.txt`。

</details>

<details>
<summary>参考思路与解释（先尝试再展开）</summary>

在 notes 中可用 `./hello.txt`；进入 /tmp 后它变成 /tmp/hello.txt。展开后的家目录绝对路径仍指向原文件。

</details>

## 完成标准

- [ ] 能解释 `/`、`~`、`.`、`..`。
- [ ] 能先预测再解释一次相对路径失败。
- [ ] 能从任意目录读取练习文件。

勾选属于自评，不能替代实际结果。请保留命令与关键现象，并用自己的话解释一次。

## 清理与回顾

保留 files 目录供后四课使用。当前只创建了自己的练习文件，没有修改系统目录。回顾：路径是定位方法，文件与当前目录是不同的对象。

---

上一课：[00-2 读懂命令、查帮助与编辑文件](../00-start/02-help-editor.md) · 下一课：[01-2 创建、查看、复制、移动和删除](02-file-operations.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
