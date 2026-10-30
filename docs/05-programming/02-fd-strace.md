# 05-2 文件描述符、write 与系统调用

> 建议时间：20—40 分钟（含独立练习） · 状态：已编写；验证范围见环境记录
>
> 执行位置：除特别标注外，均为 **RK3576 的 Bash 终端**。普通用户执行；带 `sudo` 的步骤才需要管理员权限。
>
> 环境：先按[环境说明](../environment.md)设置 `RKLAB_ROOT`。先修课见页尾“上一课”；首次阅读从课程总目录开始。

## 这课完成什么

- 能把 Shell 重定向与文件描述符联系起来。
- 能通过 strace 验证实际系统调用，而非只看程序输出。

## 跟着做：解释、预测、操作、观察


### 1. 回顾 0、1、2，但换一个观察层次

```bash
cd "$RKLAB_ROOT"
ls -l "/proc/$$/fd"
sed -n '1,120p' 03-linux-system-programming/02-write-lab.cpp
./build/write_lab
```

文件描述符是进程中的整数引用，不是文件名。0/1/2 是惯例上的标准输入、输出和错误；1 可以指向终端、普通文件或管道。`STDOUT_FILENO` 是表示 1 的符号常量。

系统调用把用户空间请求交给内核；库函数可能封装系统调用，也可能先缓冲数据。不能认为每个 C++ 输出语句都恰好对应一次 write。

### 2. 亲眼验证重定向改变了什么

```bash
mkdir -p run
strace -o run/write.trace -e trace=write ./build/write_lab > run/write-output.txt
cat run/write-output.txt
cat run/write.trace
```

**先预测：** 代码没改，trace 中的 fd 是否仍然为 1？为什么输出却在文件里？

Shell 在程序启动前安排了描述符映射；write 仍对 1 写，内核根据该进程的描述符表找到实际对象。此次只追踪 write，便于聚焦；完整追踪还会看到程序加载器等调用。

### 3. 返回值为什么不能忽略

`write` 返回实际写入字节数，失败返回 -1 并设置 errno；一次请求可能只写入部分数据，被信号中断也需考虑。本例循环推进已写字节数，处理 EINTR 并把其他错误作为失败。更完整的非阻塞 I/O 还需处理 EAGAIN 等情况，留作专题。

```bash
python3 tools/check_lab.py programming
```

该检查还运行下一课的 pipe/mmap 基础示例；本课先确认 write 输出和状态，下一课解释其余两项。

### 排错

strace 无权限或受 ptrace 策略限制时，先确认追踪的是自己启动的程序。不要为了观察别人的进程修改系统安全设置。日志为空时确认 -o 文件路径，以及命令是否真正运行。


## 自己完成一次

将 write_lab 的 stdout 接到 wc -c，预测并验证字节数；解释本次 fd 1 连接的对象与上一步有何不同。

<details>
<summary>提示一：先想方向</summary>

注意字符串末尾的换行也是一个字节。

</details>

<details>
<summary>提示二：关键工具</summary>

`./build/write_lab | wc -c`；查看源码中的 sizeof(message) - 1。

</details>

<details>
<summary>参考思路与解释（先尝试再展开）</summary>

Hello via write() 加换行共 18 字节；-1 排除 C 字符串结束符。fd 1 这次连接管道，终端显示的是 wc 的输出。

</details>

## 完成标准

- [ ] 能找到 fd 1 的 write 调用。
- [ ] 能解释输出文件中的内容与 Shell 重定向。
- [ ] 能说明短写和错误返回值为何需要处理。

勾选属于自评，不能替代实际结果。请保留命令与关键现象，并用自己的话解释一次。

## 清理与回顾

run/write.trace 与 run/write-output.txt 是自己的输出，可保留对照或指定名称删除。不要覆盖仓库中历史 trace 来冒充新的结果。

---

上一课：[05-1 从 C++ 源码到 Linux 进程](01-build-process.md) · 下一课：[05-3 管道通信与共享内存](03-ipc-memory.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
