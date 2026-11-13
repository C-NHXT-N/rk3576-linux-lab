# 自动测试

[课程总目录](../README.md) · [检查与构建工具](../tools/README.md)

`tests/` 保存可重复运行的回归测试，帮助检查修改是否破坏已有行为。`fixtures/` 保存测试用的替代实现，例如模拟 RKNN Runtime 的 C++ 库，供资源释放和错误路径测试使用。

## 检查什么

| 范围 | 测试入口 | 内容 |
|---|---|---|
| 巡检、监控与视觉配置 | [test_labs.py](test_labs.py) | 报告分段、参数处理、有限采样、信号清理、配置路径和健康状态 |
| 文档与服务工具 | [test_repository_tools.py](test_repository_tools.py) | 根目录课程结构、失效链接、模板与项目说明的识别、服务路径生成 |
| 图片检测与输入输出 | [test_detection.py](test_detection.py) · [test_io.py](test_io.py) | 检测后处理、输入校验、异常与资源生命周期 |
| 视频处理与输出 | [test_video.py](test_video.py) · [test_batch_pipeline.py](test_batch_pipeline.py) · [test_output_pipeline.py](test_output_pipeline.py) | 视频读取、批处理、队列和输出完整性 |
| 原生库与媒体后端 | [test_native_rknn.py](test_native_rknn.py) · [test_native_mpp.py](test_native_mpp.py) · [test_media_backends.py](test_media_backends.py) | 原生接口、缓冲生命周期、编解码和后端选择 |
| 性能统计与显示 | [test_bench_support.py](test_bench_support.py) · [test_pipeline_metrics.py](test_pipeline_metrics.py) · [test_display_output.py](test_display_output.py) · [test_native_render.py](test_native_render.py) | 计时统计、线程与显示输出、原生绘制 |

## 如何运行

推荐使用 Ubuntu 22.04。下面的命令均在仓库根目录执行，测试依赖版本与自动检查保持一致：

```bash
python3 -m venv build/test-venv
build/test-venv/bin/python -m pip install numpy==1.26.4 opencv-python-headless==4.10.0.84
bash tools/build_labs.sh
build/test-venv/bin/python -m unittest discover -s tests -v
build/test-venv/bin/python tools/check_lab.py programming
```

基础环境需要 Bash、Python 3、venv、g++ 和 Linux 常用工具，安装方式见[环境说明](../docs/reference/environment.md)。文档与服务工具可以单独检查：

```bash
python3 tools/check_docs.py
python3 -m unittest discover -s tests -p test_repository_tools.py -v
```

## 环境条件与结果

- 监控和进程清理测试依赖 Linux、Bash 和 `/proc`，其他系统会跳过相应测试。
- 部分图像、视频及原生库测试依赖 NumPy、OpenCV、g++；缺少依赖时按各测试的条件跳过。
- 原生 RKNN Runtime 测试还需要固定版本的官方头文件。按[视觉项目说明](../projects/04-rknn-vision/README.md#最终视频版)获取后运行；头文件仍由忽略规则排除。
- `fixtures/fake_rknn.cpp` 模拟 Runtime 接口，相关测试通过只表示接口和生命周期行为通过，不代表真实 NPU 推理成功。
- `unittest` 输出中的失败、错误和跳过需要分别记录。摄像头、真实 NPU、systemd 服务和板端视频性能仍按对应课程验收，已有证据见[验证记录](../docs/README.md)。
