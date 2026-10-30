# 03 — Linux 系统编程实验

先修：[Shell 输入输出](../docs/02-shell/01-streams-variables.md)、[进程与信号](../docs/03-process/02-jobs-signals.md)。

| 源码 | 课程 | 要观察的机制 |
|---|---|---|
| [01-process-lab.cpp](01-process-lab.cpp) | [构建与进程](../docs/05-programming/01-build-process.md) | PID/PPID、exe/cwd、生命周期 |
| [02-write-lab.cpp](02-write-lab.cpp) | [描述符与 strace](../docs/05-programming/02-fd-strace.md) | write、短写、stdout 重定向 |
| [03-pipe-lab.cpp](03-pipe-lab.cpp) | [IPC 与内存](../docs/05-programming/03-ipc-memory.md) | fork、pipe、EOF、waitpid |
| [04-mmap-lab.cpp](04-mmap-lab.cpp) | [IPC 与内存](../docs/05-programming/03-ipc-memory.md) | 共享映射、父子同步 |

在仓库根目录运行：

```bash
bash tools/build_labs.sh
./build/write_lab
./build/pipe_lab
./build/mmap_lab
python3 tools/check_lab.py programming
```

process_lab 默认休眠约 30 秒，按课文后台启动并在期间观察。所有新构建进入 build，不覆盖目录中历史 process_lab/write_lab 和 write_trace.txt；历史产物不代表本次验证结果。

实验结束回收自己启动的子进程；trace 等个人输出进入 run。[课程目录](../docs/README.md)

早期二进制已停止由 Git 跟踪（原设备本地文件可保留）；新克隆只提供源码，请用 build 目录重新构建。
