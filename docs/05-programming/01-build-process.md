# 05-1 从 C++ 源码到 Linux 进程

> 建议时间：20—40 分钟（含独立练习） · 状态：已编写；验证范围见环境记录
>
> 执行位置：除特别标注外，均为 **RK3576 的 Bash 终端**。普通用户执行；带 `sudo` 的步骤才需要管理员权限。
>
> 环境：先按[环境说明](../environment.md)设置 `RKLAB_ROOT`。先修课见页尾“上一课”；首次阅读从课程总目录开始。

## 这课完成什么

- 能区分源文件、编译器、可执行文件和进程。
- 能观察自己程序的 PID、PPID 与生命周期。

## 跟着做：解释、预测、操作、观察


### 1. 源码不是已经运行的程序

```bash
cd "$RKLAB_ROOT"
g++ --version
sed -n '1,100p' 03-linux-system-programming/01-process-lab.cpp
bash tools/build_labs.sh
file build/process_lab
```

构建脚本把四个 C++ 示例编译到 build，使用 C++17、警告和调试符号；`-O0` 便于学习观察。`file` 应识别本板可执行格式与架构。不能把另一台 x86 电脑生成的程序直接当作 ARM64 程序运行。

### 2. 把磁盘上的文件变为一个运行实例

**先预测：** 同一份可执行文件启动两次，是一个 PID 还是两个？先启动一次：

```bash
./build/process_lab &
cpp_pid=$!
ps -p "$cpp_pid" -o pid,ppid,state,comm,args
readlink "/proc/$cpp_pid/exe"
readlink "/proc/$cpp_pid/cwd"
wait "$cpp_pid"
echo $?
```

程序打印自己的 PID/PPID，休眠约 30 秒再正常退出；观察要在休眠期间完成。Bash 启动程序时涉及创建进程和加载可执行文件，`exec` 的要点是替换进程映像，不是“每次调用都新增 PID”。

`exe` 指向正在执行的文件，`cwd` 指向当前工作目录；它们不是同一个位置。父子关系与磁盘目录关系也不是同一棵树。

### 3. 看到失败时先分阶段

编译错误先看第一条诊断和源代码行；No such file 先确认构建结果路径；Exec format error 先检查架构；Permission denied 检查执行位、目录访问和挂载设置。

仓库第三章目录中保留的旧二进制与旧 trace 是历史产物，本轮实验只运行自己构建的 build 版本，避免把旧输出当成新验证。


## 自己完成一次

启动同一个 process_lab 两次，保存两个 PID，比较 exe 与 PID，等待它们退出。说明程序文件与进程实例的关系。

<details>
<summary>提示一：先想方向</summary>

同一份文件可以对应多个运行实例。

</details>

<details>
<summary>提示二：关键工具</summary>

两次 `$!` 分别存入不同变量，`ps -p`、`readlink /proc/PID/exe`、`wait`。

</details>

<details>
<summary>参考思路与解释（先尝试再展开）</summary>

两个进程通常有不同 PID，exe 可相同。等待结束后 /proc 下对应目录消失，文件仍在 build 中。

</details>

## 完成标准

- [ ] 四个示例成功构建。
- [ ] 能区分源码、可执行文件与进程。
- [ ] 能在程序仍运行时观察并解释 PID/PPID。

勾选属于自评，不能替代实际结果。请保留命令与关键现象，并用自己的话解释一次。

## 清理与回顾

等待自己启动的实例自然退出；若提前停止，只操作自己保存的 PID 并 wait。build 中产物被 Git 忽略，可留作后续实验。

---

上一课：[04-4 用 systemd 管理监控服务](../04-services/04-systemd.md) · 下一课：[05-2 文件描述符、write 与系统调用](02-fd-strace.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)

早期二进制已停止由 Git 跟踪（原设备本地文件可保留）；新克隆只提供源码，请用 build 目录重新构建。
