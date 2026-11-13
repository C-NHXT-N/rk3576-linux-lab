# 本地检查工具

从仓库根目录运行，所有工具仅依赖基础 Linux 工具或 Python 标准库；RKNN 应用另需 SDK。

`tools/` 提供学习和维护时直接调用的命令：检查课文、构建示例、验证实验成果、生成服务配置。自动回归用例单独位于 [tests/](../tests/README.md)，用于检查代码修改后的行为。

| 命令 | 检查/执行内容 | 副作用 |
|---|---|---|
| [`python3 tools/check_docs.py`](check_docs.py) | Markdown 本地链接、锚点、围栏、根目录课程结构 | 只读，不请求外部 URL |
| [`python3 tools/check_lab.py environment`](check_lab.py) | 基础工具与平台 | 只读，不安装软件 |
| [`python3 tools/check_lab.py files`](check_lab.py) | 练习原件、副本、链接、权限 | 只读；需在清理练习前执行 |
| [`python3 tools/check_lab.py inspector`](check_lab.py) | 运行只读报告并核对模块 | 读取系统状态 |
| [`python3 tools/check_lab.py monitor`](check_lab.py) | 课程服务状态和主 PID | 只读，不启动/停止/enable |
| [`python3 tools/check_lab.py programming`](check_lab.py) | 运行 build 中 write/pipe/mmap | 创建短暂子进程与匿名内存 |
| [`python3 tools/check_lab.py vision`](check_lab.py) | 真实推理程序的近期健康文件 | 只读，不等同精度验收 |
| [`bash tools/build_labs.sh`](build_labs.sh) | 编译 projects 中的四个 C++ 示例 | 写入 build |
| [`python3 tools/render_service.py --project monitor`](render_service.py) | 渲染当前用户和监控项目新路径的 unit | 只输出 stdout；安装是单独步骤 |
| [`python3 tools/render_service.py --project vision`](render_service.py) | 渲染当前用户、视觉项目和 Runtime 路径的 unit | 只输出 stdout；安装是单独步骤 |

check_lab 成功返回 0，检查失败返回 1，命令行用法错误由 argparse 返回 2。每个失败项提供下一步；没有对应成果时应失败，不能把检查脚本当作自动完成实验的工具。

files 默认检查 `~/rk3576-practice/files`，可用 --workspace 指定其他自己的练习目录。monitor 默认检查 rk3576-monitor-lab.service，可用 --unit 指定受支持的课程名称。vision 可用 --health 指定心跳文件，默认要求 30 秒内实际成功推理且状态为 running。

默认视觉心跳位于 `projects/04-rknn-vision/run/health.json`。文档检查覆盖课程、项目说明和配套资料，跳过虚拟环境、构建与运行产物；只有根目录编号章节内的课文要求包含固定课程结构。

service 源文件为模板，必须先渲染到 run 下，审阅后再由读者安装。渲染器拒绝包含特殊字符的仓库路径，便于保持本课程的 systemd 路径规则可解释。

[课程目录](../README.md)

板端视频复验见[视觉项目说明](../projects/04-rknn-vision/README.md)。
