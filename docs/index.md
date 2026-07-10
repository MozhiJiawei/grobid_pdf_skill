# GROBID + Docling PDF 解析

`grobid-docling-pdf` 用来把论文或技术 PDF 解析成一个下游 Agent 可消费的 XML 包：GROBID 负责学术文本结构，Docling 负责图表图片真值，最终合并成一个干净的 TEI/XML 交付目录。

## 逻辑视图

这个 skill 接收一份 PDF、GROBID 服务地址和解析选项，输出一份以 TEI/XML 为入口的材料包。它把“文本结构”和“视觉真值”分开处理：GROBID 提供标题、摘要、正文、引用和参考文献结构，Docling 提供图片与表格 PNG；合并阶段以 Docling 为唯一图表索引来源，并清理无法由 Docling 支撑的 GROBID 图表目标。

核心模块及其边界如下：

| 阶段 | 脚本 | 职责 |
| --- | --- | --- |
| 文本结构解析 | `scripts/grobid_parse_pdf.py` | 调用 GROBID，提取标题、摘要、正文、引用和参考文献结构。 |
| 视觉内容导出 | `scripts/docling_export.py` | 调用 Docling，导出 PDF 中的图片、表格和 Docling JSON。 |
| 结果合并 | `scripts/merge_docling_into_grobid_tei.py` | 将 Docling 图片索引写入 GROBID TEI，移除不可靠的 GROBID 图表记录。 |
| 包校验 | `scripts/validate_hybrid_outputs.py` | 检查 XML 中引用的图片是否存在、最终图片是否全部被索引。 |
| 编排与归档 | `scripts/run_hybrid_pipeline.py` | 串联以上阶段，归档中间结果，只保留最终 XML 包。 |

最终边界是 `final/<paper-name>.xml` 与相邻的 `final/images/`；GROBID 原始结果、Docling JSON、合并清单和校验 JSON 属于可追溯中间结果，不是默认最终目录中的独立交付件。

## 运行视图

从用户请求到交付物的执行路径是：

```text
用户 prompt + PDF 路径
  -> 主 Agent 确认 PDF 类型、输出目录和依赖
  -> run_hybrid_pipeline.py
     -> GROBID TEI
     -> Docling JSON + images
     -> merged TEI/XML + final/images
     -> 校验状态与 validation JSON
  -> intermediate_parse_results.zip
  -> 主 Agent 汇报 XML、图片、归档和校验摘要
```

默认流水线必须能访问 GROBID 服务；随后才会运行 Docling、合并与校验。任何阶段返回非零状态都会终止编排，校验失败也不能报告为成功交付。校验摘要会打印到命令输出，详细 JSON 会随 `work/` 进入中间归档。

## 开发视图

| 分层 | 位置 | 面向开发者的含义 |
| --- | --- | --- |
| Agent 使用约定 | `SKILL.md` | 定义默认工作流、最终输出契约和汇报要求，不是面向文档站的正文。 |
| 发布文档 | `docs/` | 提供能力展示、使用方式、依赖与架构说明。 |
| 依赖预检 | `verify_dependencies.py` | 检查 Python 包、可选 CUDA 状态及 GROBID HTTP 可达性。 |
| 流水线编排 | `scripts/run_hybrid_pipeline.py` | 负责阶段顺序、路径、归档和中间文件清理。 |
| 解析与合并 | `scripts/grobid_parse_pdf.py`、`scripts/docling_export.py`、`scripts/merge_docling_into_grobid_tei.py` | 分别处理学术文本、视觉导出及统一 XML。 |
| 交付校验 | `scripts/validate_hybrid_outputs.py` | 校验图片引用、索引和残留视觉记录，并以退出码决定流水线成败。 |

## 最终目录

```text
.tmp/pdf_xml/<paper-name>/
|-- final/
|   |-- <paper-name>.xml
|   `-- images/
|       |-- picture_*.png
|       `-- table_*.png
`-- <paper-name>.intermediate_parse_results.zip
```

## 设计边界

- born-digital 论文默认不开 OCR；扫描版 PDF 才启用 `--ocr`。
- 最终 XML 只以 Docling 导出的图表图片作为视觉真值。
- 中间 GROBID / Docling / merge / validation 文件默认打包进 zip 后移除。
- 校验失败意味着 XML 包不完整，不能作为成功交付。

## Agent 协作边界

当前 skill 的既定流程没有要求启动子 Agent、checker 或 reviewer，也没有定义跨 Agent 交接物。主 Agent 单独完成依赖确认、流水线执行、结果核验和最终汇报；因此使用本 skill 不需要额外申请子 Agent 权限。

如果上游任务自行采用多 Agent 编排，交接边界只应是已经生成并通过校验的最终 XML、`images/` 和中间归档路径；下游 Agent 不应绕过校验直接消费松散的 GROBID、Docling 或 `work/` 中间文件，也不应把“已建立图片索引”误报为“每张图片都存在准确正文位置引用”。

## 校验关注点

`validate_hybrid_outputs.py` 会检查最终 XML 包是否完整，重点包括：

- XML 中引用的图片是否都存在。
- 图片目录中的最终图片是否都被 XML 索引。
- 正文中的图表引用是否能连到 Docling 图片。
- 最终 XML 中是否残留不可靠的 GROBID 图表记录。

通过校验后，`final/<paper-name>.xml` 才应作为下游 Agent 的正式输入。
