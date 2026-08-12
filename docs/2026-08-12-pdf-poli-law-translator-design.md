# 设计文档：政治法律 PDF 专业翻译 Skill（v2 长文本并行版）

日期：2026-08-12
状态：已批准（方案 A + 并行多 agent 扩展）

## 1. 目标

将 `pdf-legal-zh-translator` skill 改造为面向**政治与法律文献长文本 PDF**（含数百页文档）的英→中专业翻译工具：
- 输入：英文 PDF（.pdf），任意长度
- 输出：中文 PDF + 合并 Markdown + 术语表
- 全文术语一致性（共享 glossary 并行翻译）
- 自动去除页眉/页脚/页码

## 2. 目录结构

```
pdf-legal-zh-translator/
├── SKILL.md                  # 并行多 agent 翻译工作流
├── scripts/
│   ├── extract_pdf.py        # PyMuPDF: PDF → 按页文本（自动去页眉页脚页码 + 表格识别）
│   ├── split_chunks.py       # 按标题边界分块 + manifest.json + 跨块上下文提示
│   ├── merge_chunks.py       # 按序合并各块译文（剥页标记/上下文块）
│   ├── merge_glossary.py     # 合并各 chunk_XXX_terms.json → 共享 glossary（去竞态）
│   ├── apply_glossary.py     # 用 glossary 确定性回填正文中的英文残留术语
│   ├── check_completeness.py # 自动校验页覆盖/长度比/标题缺失
│   └── build_pdf.py          # reportlab: 译文(md) → 中文 PDF（标题/列表/表格/页码）
├── glossary.json             # 运行时生成：中英术语表（唯一真源，仅主流程写）
└── docs/
    └── 2026-08-12-pdf-poli-law-translator-design.md
```

## 3. 流水线

1. **提取**：`extract_pdf.py` 按页输出，自动去除重复页眉/页脚/裸页码（`--keep-header-footer` 可关）；表格以 Markdown 表格 + `【表格 / Table】` 标记输出（新版 PyMuPDF 用 `find_tables`，旧版走网格启发式回退）；扫描版/加密检测
2. **预建术语表**：先读开头页/目录，预登记关键机构/法律/案例/学理词条到 `glossary.json`
3. **分块**：`split_chunks.py` 按标题边界切成约 20 页/块（`--pages` 可调，`--max-chunks` 限并发），每块开头附带上一块末尾 ~300 字符作为上下文，产出 `chunk_XXX.txt` + `manifest.json`
4. **并行翻译**：每块派一个子 agent 并行翻译；agent 只读共享 glossary，新术语只写入自己的 `chunk_XXX_terms.json`（避免并行写竞态）；输出 `chunk_XXX_zh.md`，保留页标记，忽略上下文块，翻译表格单元格并保留 `|` 结构
4b. **合并术语表**：`merge_glossary.py` 将 base glossary + 所有 chunk terms 确定性合并（先到先得，冲突告警）写回 `glossary.json`
5. **完整性校验**：`check_completeness.py` 自动比对每块译文页标记覆盖、译文/源长度比、标题缺失；硬错误时退出码 1
6. **合并**：`merge_chunks.py` 按 manifest 顺序拼接并剥离页标记与上下文块
7. **多 agent 审查**：并行派 术语/引用/完整性/语言 四类审查 agent，收集问题修复后跑 `apply_glossary.py` 确定性回填英文残留术语
8. **生成 PDF**：`build_pdf.py` 合并 md → 中文 PDF（自动选系统中文字体、标题/列表/表格渲染、页码）

## 4. 翻译规则（政治法律专项）

- 术语表为共享唯一真源；并行 agent 只读共享 glossary，新术语写入各自 chunk terms 文件，由 `merge_glossary.py` 合并（避免写竞态）
- 机构/法律/案例名首现附英文原名：`联邦最高法院 (Supreme Court of the United States)`
- 法条引用原样保留：`§ 1983`、`5 U.S.C. § 552`、`Miranda v. Arizona`
- 拉丁法律术语：`habeas corpus (人身保护令)`、`stare decisis (遵循先例)`
- 表格：翻译单元格内容，保留 `| ... |` 列结构与表头行
- 政治语言中性客观，不掺立场；正式、专业、自然中文

## 5. 脚本要点

- `extract_pdf.py`：块级读取按顺序输出；0.08/0.92 高度带判定页眉页脚；≥2 次出现且 ≥40% 页数判为重复而剔除；纯数字判为页码剔除；表格先于块合并排序，块与表格 bbox 重叠 >50% 则剔除该块避免重复
- `split_chunks.py`：章节标题正则（全大写行、Article/Section/Chapter/Part/Title/Annex/Appendix/§、中文"第X章"等）作为断点；优先在标题边界分块；每块头部写入上一块末尾 ~300 字符作上下文（`<!-- CONTEXT -->` / `【上下文】`）
- `merge_glossary.py`：base glossary 优先，chunk terms 按序合并，同词不同译报冲突，首登记生效
- `apply_glossary.py`：整词匹配（字母边界），跳过括号内（首现注释）与已有 `中文 (English)` 形式；长词优先，按长度降序处理
- `check_completeness.py`：复用 split_chunks 的 PAGE_RE/HEADING_RE；页标记集合相等为硬校验，译文/源长度比 <0.25 或 >1.6 及标题缺失为告警
- `merge_chunks.py`：缺块即报错列出缺失文件；剥页标记/分隔线/上下文块
- `build_pdf.py`：微软雅黑/黑体/宋体自动检测，标题/段落/列表/代码块/Markdown 表格（reportlab Table）支持，页脚页码

## 6. 边界与错误处理

- 扫描版 PDF：脚本警告，提示需 OCR（超出范围）
- 加密/损坏 PDF：报错提示
- 并行冲突：agent 只写自己的 chunk 文件与 terms 文件；glossary 由主流程合并（首登记生效）
- 缺失块：merge 报错，重跑对应块；check_completeness 硬错误退出码 1

## 7. 测试

用数十页英文政治法律文档生成 PDF，跑通 提取 → 分块 → 模拟并行译文 → 合并 → 生成中文 PDF 全链路，验证页眉页脚剔除与分块正确性。
