# 使用方式

这个 skill 适合在“论文阅读、技术 PDF 解析、后续 PPT 或报告生成”之前调用。你可以直接把 PDF 路径交给 Agent，让它生成结构化 XML 包，而不是让 Agent 直接从 PDF 页面里硬读内容。

## 典型 Prompt

- `请解析这篇论文 PDF，输出结构化 XML 和图表图片索引，用于后续分析。`
- `请把这篇论文 PDF 的正文、引用、参考文献、图和表整理成 agent 可消费的结构化结果。`
- `请先把这个技术 PDF 转成 XML 包，保留最终 XML 路径、图片目录和校验结果。`

## 推荐流程

1. 确认 PDF 是 born-digital 还是扫描版。
2. 确认唯一的共享 GROBID 运行时符合规范；默认流水线会自动检查、创建或启动它。
3. 将输出目录放在主工作区 `.tmp/pdf_xml/<paper-name>/` 下。
4. 运行混合解析流水线。
5. 检查最终 XML、图片目录、归档 zip 和校验状态。

## 脚本入口

以下命令从工作区根目录（即包含 `skills/` 和 `.tmp/` 的目录）运行：

```powershell
python skills/grobid_pdf_skill/scripts/run_hybrid_pipeline.py `
  --pdf path/to/paper.pdf `
  --out .tmp/pdf_xml/<paper-name> `
  --grobid-url http://127.0.0.1:8070 `
  --docling-device auto
```

本地默认模式固定复用 `grobid-docling-pdf` 容器，不要为论文、任务或 Agent 创建独立容器。容器不存在时流水线会创建并启动，已停止时会重新启动，解析完成后保持运行以支持并发任务。也可以单独检查或确保运行时：

```powershell
python skills/grobid_pdf_skill/scripts/manage_grobid_runtime.py status
python skills/grobid_pdf_skill/scripts/manage_grobid_runtime.py ensure
```

只有显式传入非默认 `--grobid-url` 时，流水线才会跳过本地 Docker 管理。

扫描版 PDF 才加：

```powershell
--ocr
```

确认 CUDA PyTorch 可用后才指定：

```powershell
--docling-device cuda
```

## 交付汇报

Agent 完成后应汇报：

- 最终 XML 路径。
- 最终图片目录和图片数量。
- 中间结果归档路径。
- 校验状态，包括缺失图片引用、未索引图片、body-linked 图片数量。

## 依赖检查

以下命令同样从工作区根目录运行。它检查 Python 包、Docker Desktop、唯一标准 GROBID 镜像以及本地容器唯一性；不会启动容器或请求 GROBID API：

```powershell
python skills/grobid_pdf_skill/verify_dependencies.py
```

依赖检查允许标准容器尚未创建；默认流水线会调用运行时管理脚本，将唯一标准容器处理到可用状态。
