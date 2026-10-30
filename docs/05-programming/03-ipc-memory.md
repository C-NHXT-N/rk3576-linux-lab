# 05-3 管道通信与共享内存

> 建议时间：20—40 分钟（含独立练习） · 状态：已编写；验证范围见环境记录
>
> 执行位置：除特别标注外，均为 **RK3576 的 Bash 终端**。普通用户执行；带 `sudo` 的步骤才需要管理员权限。
>
> 环境：先按[环境说明](../environment.md)设置 `RKLAB_ROOT`。先修课见页尾“上一课”；首次阅读从课程总目录开始。

## 这课完成什么

- 能解释 pipe 的读写端、EOF 与关闭无用描述符。
- 能观察 fork 后共享映射与等待子进程的关系。

## 跟着做：解释、预测、操作、观察


### 1. 从 Shell 管道走到进程间通信

```bash
cd "$RKLAB_ROOT"
sed -n '1,160p' 03-linux-system-programming/03-pipe-lab.cpp
./build/pipe_lab
```

pipe 创建读写两端；fork 后父子进程继承描述符。示例子进程关闭读端并写消息，父进程关闭写端并读数据。只有所有写端都关闭，读端才会在数据读完后得到 EOF。忘记关闭写端可能让父进程一直等待。

waitpid 等待并回收子进程。进程结束与父进程回收是两个相关步骤，先前 procfs 观察里的僵尸状态由此得到更具体的解释。

### 2. 映射内存，不等于复制文件内容

```bash
sed -n '1,140p' 03-linux-system-programming/04-mmap-lab.cpp
./build/mmap_lab
```

预期输出 shared value after child exit: 42。示例在 fork 前建立 MAP_SHARED 匿名映射，子进程写入，父进程等子进程退出后读取。普通局部变量在 fork 后不能按同样方式当作共享通信区域。

这段程序用 waitpid 保证子进程已经结束，不存在同时读写；更一般的共享内存并发仍需要同步机制。mmap 是虚拟地址映射机制，不意味着所有映射都立即占据同样多的物理内存。

### 3. 观察创建、通信与映射调用

```bash
strace -f -o run/pipe.trace -e trace=process,read,write,close ./build/pipe_lab
strace -f -o run/mmap.trace -e trace=process,mmap,munmap ./build/mmap_lab
python3 tools/check_lab.py programming
```

不同架构和 libc 下 fork 可能表现为 clone 等系统调用，按语义理解，不要求某个固定调用名逐字出现。

### 排错

pipe 示例不退出先检查是否有未关闭写端；共享值未更新先看映射标志和等待顺序；不要通过加入随机 sleep 代替同步。返回值检查是实验的一部分。


## 自己完成一次

把 mmap 源码复制到 run 下，只在副本中将 MAP_SHARED 改为 MAP_PRIVATE，重新编译到 run，再预测父进程读到什么。保留原参考实现。

<details>
<summary>提示一：先想方向</summary>

fork 后私有映射的修改如何影响另一进程？

</details>

<details>
<summary>提示二：关键工具</summary>

`cp`、编辑器、`g++`，比较 MAP_PRIVATE 与 MAP_SHARED。

</details>

<details>
<summary>参考思路与解释（先尝试再展开）</summary>

父进程通常仍读到 0，示例的验证条件期待 42，因此副本返回非零是预期。这演示修改不会经私有映射传给父进程，并非编译错误。

</details>

## 完成标准

- [ ] pipe 和 mmap 参考程序成功运行。
- [ ] 能解释管道 EOF 的条件。
- [ ] 能解释共享映射为何需要同步。
- [ ] 系统编程检查通过。

勾选属于自评，不能替代实际结果。请保留命令与关键现象，并用自己的话解释一次。

## 清理与回顾

删除自己 run 中的实验副本、二进制和 trace，或保留带说明的记录；不要修改原示例来迎合副本的输出。

---

上一课：[05-2 文件描述符、write 与系统调用](02-fd-strace.md) · 下一课：[06-1 从启动链到设备树和驱动](../06-hardware/01-boot-devices.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
