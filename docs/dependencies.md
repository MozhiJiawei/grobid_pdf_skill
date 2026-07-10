# 依赖说明

使用这个 skill 前，请先让 Agent 跑依赖检查。依赖状态以子仓根目录的 `verify_dependencies.py` 输出为准；文档只说明它会检查什么。

## 让 Agent 先做什么

你可以直接这样说：

```text
我要使用 grobid-docling-pdf，请先检查 PDF 解析依赖；如果 GROBID 服务或 Python 包没有就绪，请帮我处理到可用。
```

## 检查命令

只检查本地 Python 依赖：

```powershell
python skills/grobid_pdf_skill/verify_dependencies.py --skip-services
```

连同 GROBID 服务一起检查：

```powershell
python skills/grobid_pdf_skill/verify_dependencies.py --grobid-url http://localhost:8070
```

## 它会检查什么

| 类型 | 必需性 | 脚本实际检查 |
| --- | --- | --- |
| Python 包 | 必需 | 分别导入 `docling`、`lxml`、`torch`，导入失败即检查失败；若模块暴露版本号则打印版本。 |
| GROBID 服务 | 完整流水线必需 | 默认请求 `<grobid-url>/api/isalive`，连接或响应读取失败即检查失败。默认地址为 `http://localhost:8070`。 |
| CUDA | 可选 | 通过 `torch.cuda.is_available()` 检查；不可用只给出警告，可继续使用 `--docling-device auto` 或 `cpu`。 |

`--skip-services` 只用于安装或环境准备阶段的本地 Python 包预检。默认流水线会无条件调用 GROBID 来生成学术文本结构，因此即使 `--skip-services` 返回成功，也不能据此判断完整 PDF 解析可运行。

## 不会检查什么

`verify_dependencies.py` 不会：

- 扫描或验证仓库脚本、`SKILL.md`、示例 PDF 等代码资产；
- 下载模型、执行真实 PDF 解析，或验证 GROBID 对某份 PDF 的解析质量；
- 检查 Python 包版本兼容矩阵、模型缓存、磁盘空间、网络代理或远端下载权限；
- 验证 CUDA 驱动、CUDA toolkit 与 PyTorch 构建版本是否互相兼容；
- 运行合并器、最终图片索引校验或解析器自测试。

## 缺失时的修复方向

- `docling`、`lxml` 或 `torch` 导入失败：在运行该工作区的同一 Python 环境中安装或修复对应包，再重新运行依赖检查。安装 `torch` 时按目标机器的 CPU/CUDA 平台选择官方匹配构建。
- GROBID 检查失败：启动可访问的 GROBID 服务，确认 `/api/isalive` 可从当前环境访问；若服务不在默认地址，通过 `--grobid-url` 同时传给依赖检查和流水线。
- CUDA 只出现警告：不必阻塞 CPU 流程，使用 `--docling-device auto` 或 `cpu`；如果确实需要 GPU，再核对 NVIDIA 驱动、PyTorch CUDA 构建和 `torch.cuda.is_available()`。

## 判断标准

只有必需 Python 包和 GROBID 服务检查均通过，才满足默认流水线的依赖前提。依赖检查通过只表示前置环境可用，不代表任意 PDF 的最终包必然通过内容与图片索引校验。
