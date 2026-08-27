# 依赖说明

使用这个 skill 前，请先让 Agent 跑依赖检查。依赖状态以子仓根目录的 `verify_dependencies.py` 输出为准；文档只说明它会检查什么。

## 让 Agent 先做什么

你可以直接这样说：

```text
我要使用 grobid-docling-pdf，请先检查 PDF 解析依赖；如果 Docker、GROBID 镜像或 Python 包没有就绪，请帮我处理到可用。
```

## 检查命令

检查完整本地依赖：

```powershell
python skills/grobid_pdf_skill/verify_dependencies.py
```

## 它会检查什么

| 类型 | 必需性 | 脚本实际检查 |
| --- | --- | --- |
| Python 包 | 必需 | 分别导入 `docling`、`lxml`、`torch`，导入失败即检查失败；若模块暴露版本号则打印版本。 |
| Docker | 必需 | 检查 `docker` 命令是否存在，并通过 Docker Server 版本确认 Docker Desktop 引擎可用。Windows 缺失时提示安装 WSL2 和 Docker Desktop；macOS 缺失时提示安装 Docker Desktop for Mac。引擎不可用时返回对应平台的启动提示。 |
| GROBID 镜像 | 必需 | 本地必须恰好只有一个 GROBID 镜像 ID，并且唯一标签为 `grobid/grobid:0.8.2`。 |
| GROBID 容器 | 必需 | 容器可以尚未创建；如果存在，则包括停止实例在内最多只能有一个，并且必须是固定名称 `grobid-docling-pdf`、固定端口 `127.0.0.1:8070` 和 `unless-stopped` 重启策略。 |
| CUDA | 可选 | 通过 `torch.cuda.is_available()` 检查；不可用只给出警告，可继续使用 `--docling-device auto` 或 `cpu`。 |

## 不会检查什么

`verify_dependencies.py` 不会：

- 扫描或验证仓库脚本、`SKILL.md`、示例 PDF 等代码资产；
- 下载模型、执行真实 PDF 解析，或验证 GROBID 对某份 PDF 的解析质量；
- 启动、停止、创建或删除 GROBID 容器，也不会请求 GROBID HTTP API；
- 检查 Python 包版本兼容矩阵、模型缓存、磁盘空间、网络代理或远端下载权限；
- 验证 CUDA 驱动、CUDA toolkit 与 PyTorch 构建版本是否互相兼容；
- 运行合并器、最终图片索引校验或解析器自测试。

## 缺失时的修复方向

- `docling`、`lxml` 或 `torch` 导入失败：在运行该工作区的同一 Python 环境中安装或修复对应包，再重新运行依赖检查。安装 `torch` 时按目标机器的 CPU/CUDA 平台选择官方匹配构建。
- Windows 上 Docker 检查失败：安装 WSL2 和 Docker Desktop；若已经安装，则启动 Docker Desktop 并确认 WSL2 backend 可用。
- macOS 上 Docker 检查失败：安装并启动 Docker Desktop for Mac，等待 Docker engine ready 后重新检查。
- GROBID 镜像缺失：拉取 `docker pull grobid/grobid:0.8.2`；检测到额外镜像时先报告并获得授权，再精确清理。
- GROBID 容器重复或配置漂移：不要新建任务专属容器，也不要静默清理；先报告异常资源并获得授权。状态符合规范后，运行 `python skills/grobid_pdf_skill/scripts/manage_grobid_runtime.py ensure` 创建、启动并复用标准容器。
- CUDA 只出现警告：不必阻塞 CPU 流程，使用 `--docling-device auto` 或 `cpu`；如果确实需要 GPU，再核对 NVIDIA 驱动、PyTorch CUDA 构建和 `torch.cuda.is_available()`。

## 判断标准

只有必需 Python 包、Docker、唯一标准 GROBID 镜像和容器唯一性检查均通过，才满足默认流水线的安装前提。零容器是合法的初始状态；默认流水线会创建或启动唯一标准容器并等待健康检查。依赖检查通过仍不代表任意 PDF 的最终包必然通过内容与图片索引校验。
