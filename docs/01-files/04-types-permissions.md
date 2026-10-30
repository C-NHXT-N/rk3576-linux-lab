# 01-4 文件类型、权限与链接

> 建议时间：20—40 分钟（含独立练习） · 状态：已编写；验证范围见环境记录
>
> 执行位置：除特别标注外，均为 **RK3576 的 Bash 终端**。普通用户执行；带 `sudo` 的步骤才需要管理员权限。
>
> 环境：先按[环境说明](../environment.md)设置 `RKLAB_ROOT`。先修课见页尾“上一课”；首次阅读从课程总目录开始。

## 这课完成什么

- 能读懂 ls -l 的类型、所有者和权限。
- 能解释目录权限与文件权限的不同，建立并识别链接。

## 跟着做：解释、预测、操作、观察


### 1. 先读懂一行输出

```bash
cd ~/rk3576-practice/files
ls -ld notes notes/hello.txt /dev/null
id
```

权限串第一位是类型：`-` 普通文件、`d` 目录、`l` 符号链接、`c` 字符设备、`b` 块设备。后九位按所有者、所属组、其他用户分三组，`r/w/x` 分别表示读、写、执行/搜索。

对文件：读内容、改内容、作为程序执行。对目录：`r` 可列出名称，`w` 配合 `x` 可增删目录项，`x` 允许通过名称查找与进入。删除文件主要取决于父目录权限，还可能受 sticky bit、ACL 等约束，不是单看文件是否可写。

### 2. 给课程文件设定明确权限

**先预测：** 去掉文件对其他用户的权限，会不会导致所有者自己也读不了？

```bash
chmod 640 notes/hello.txt
ls -l notes/hello.txt
cat notes/hello.txt
```

数字 `4/2/1` 对应 `r/w/x`；`640` 为所有者读写、组只读、其他无权限。程序运行身份用 `id` 查看；遇到权限错误先确认身份、父目录和文件权限，不要直接把所有内容改成 777。

### 3. 符号链接的目标从哪里算起

```bash
ln -s notes/hello.txt hello-link
readlink hello-link
cat hello-link
ln notes/hello.txt hello-hard
ls -li notes/hello.txt hello-hard hello-link
```

符号链接保存目标路径；相对目标从**链接所在目录**解析。硬链接是同一文件 inode 的另一个名称，通常不能跨文件系统或用于普通用户的目录。inode 数字只在同一文件系统语境下比较。重复实验若提示 File exists，先查看已有链接是否正确。

### 4. 回到脚本执行权限

```bash
cd ~/rk3576-practice
chmod u+x hello.sh
./hello.sh
```

`./` 明确定位当前目录的脚本；直接执行需要执行权限及有效解释器声明。`bash hello.sh` 则由 Bash 读取文件执行，不要求该文件本身可执行。若所在文件系统挂载为 noexec，也会影响直接执行。


## 自己完成一次

解释“删除符号链接会不会删掉目标”和“硬链接与复制是否相同”。运行文件模块检查，再用 ls -li 自己论证。

<details>
<summary>提示一：先想方向</summary>

链接与目标、两个名字与两份内容要分开考虑。

</details>

<details>
<summary>提示二：关键工具</summary>

`readlink`、`ls -li`、`python3 "$RKLAB_ROOT/tools/check_lab.py" files`。

</details>

<details>
<summary>参考思路与解释（先尝试再展开）</summary>

删除符号链接只移除链接本身；硬链接共享 inode，复制通常创建新文件。对练习文件的 chmod 也会反映在另一个硬链接名称上。

</details>

## 完成标准

- [ ] notes/hello.txt 权限为 640。
- [ ] hello-link 正确指向原件。
- [ ] 能解释硬链接和副本。
- [ ] 文件模块检查通过。

勾选属于自评，不能替代实际结果。请保留命令与关键现象，并用自己的话解释一次。

## 清理与回顾

先保留验收材料，下一课结束后可按以下命令清理本组文件实验：

```bash
cd ~/rk3576-practice/files
rm -i -- hello-link hello-hard archive/hello-copy.txt notes/hello.txt
rmdir archive notes
cd ..
rmdir files
```

只移除本组列出的练习对象；若目录非空，先 ls 查看遗漏。保留 hello.sh 用于后续 Shell 课。

---

上一课：[01-3 Linux 目录各自负责什么](03-directory-map.md) · 下一课：[01-5 一棵目录树，多种文件系统](05-mounts-interfaces.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
