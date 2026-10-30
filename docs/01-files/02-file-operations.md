# 01-2 创建、查看、复制、移动和删除

> 建议时间：20—40 分钟（含独立练习） · 状态：已编写；验证范围见环境记录
>
> 执行位置：除特别标注外，均为 **RK3576 的 Bash 终端**。普通用户执行；带 `sudo` 的步骤才需要管理员权限。
>
> 环境：先按[环境说明](../environment.md)设置 `RKLAB_ROOT`。先修课见页尾“上一课”；首次阅读从课程总目录开始。

## 这课完成什么

- 能区分复制与移动。
- 能处理带空格的文件名，并只清理指定的练习副本。

## 跟着做：解释、预测、操作、观察


### 1. 先检查再操作

```bash
cd ~/rk3576-practice/files
ls -la
cat notes/hello.txt
cp notes/hello.txt archive/hello-copy.txt
cmp notes/hello.txt archive/hello-copy.txt
```

`cp` 创建另一份文件。`cmp` 无输出且退出成功，表示本次比较内容相同；它们仍是两个不同文件。原件和副本的后续修改不会自动同步。

### 2. 用临时副本研究移动和引号

**先预测：** 重命名后，旧名字还在吗？

```bash
cp notes/hello.txt archive/move-me.txt
mv archive/move-me.txt 'archive/moved note.txt'
ls -l archive
cat 'archive/moved note.txt'
```

Shell 默认以空白分隔参数，引号让带空格的路径保持为一个参数。`mv` 可以重命名；跨文件系统移动时实现方式与同一文件系统内重命名不同，这里先观察可见结果。

### 3. 删除一个指定副本

```bash
rm -i -- 'archive/moved note.txt'
ls -l archive
```

确认提示中的完整目标后输入 `y`。`--` 表示后面按操作数处理，适用于防止以连字符开头的文件名被解释为选项。`rm` 通常没有回收站，不用通配符扩大本次删除范围。

### 4. 目录和文件要分清

```bash
mkdir archive/empty-dir
rmdir archive/empty-dir
ls -lh notes/hello.txt archive/hello-copy.txt
```

`rmdir` 只删除空目录，非空时报错有助于发现遗漏内容。`head -n 5` 查看开头，`less` 分页阅读、按 `q` 退出，大文件不必全部输出到终端。

### 常见问题

`cannot stat`：先确认源路径。`Is a directory`：确认自己想看目录还是文件。复制到已有文件可能覆盖；本课固定使用课程文件名，重做前先查看内容。带空格的路径忘记引号时，命令可能收到两个参数。


## 自己完成一次

用一个新的临时副本演示“复制后两个名字存在，移动后旧名字消失”，然后只删除临时副本，保留 hello-copy.txt 供验收。

<details>
<summary>提示一：先想方向</summary>

每一步都用 ls 验证，避免仅凭命令没有报错判断。

</details>

<details>
<summary>提示二：关键工具</summary>

`cp`、`mv`、`ls -l`、`rm -i --`。

</details>

<details>
<summary>参考思路与解释（先尝试再展开）</summary>

复制增加一份；重命名替换可访问名称。删除练习副本后，再次 cmp 原件与 hello-copy.txt，确认课程验收材料还在。

</details>

## 完成标准

- [ ] 原件和 archive/hello-copy.txt 内容一致。
- [ ] 能操作带空格的文件名。
- [ ] 临时移动实验已清理。

勾选属于自评，不能替代实际结果。请保留命令与关键现象，并用自己的话解释一次。

## 清理与回顾

保留 notes/hello.txt 和 archive/hello-copy.txt。只对自己刚创建的副本使用 rm；下一课先观察系统目录的职责。

---

上一课：[01-1 你在哪里：目录与路径](01-paths.md) · 下一课：[01-3 Linux 目录各自负责什么](03-directory-map.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
