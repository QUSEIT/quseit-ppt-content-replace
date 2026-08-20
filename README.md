# ppt-content-replace

> 基于已有 PPT 模板的内容替换技能 —— 把一份 PPT 当作「版式模板」，用新素材（Word / 长文本）重写其中所有文字，输出一份**只改内容、版式样式完全不变**的新 PPT。

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![platforms](https://img.shields.io/badge/platforms-windows%20%7C%20linux%20%7C%20macos-lightgrey.svg)](#安装)
[![language](https://img.shields.io/badge/language-python%203-yellow.svg)](scripts)

## 它是什么

一个 **Hermes skill**：用户上传一份 PPT 作为版式模板，并提供新内容（Word 文档或大段文本），技能完成「只换内容不动版式」的整份 PPT 重写。

核心思想：**PPT 结构 → 模板 Markdown（IR）→ AI 对齐 → 校验 → 原子回写**。

- 解析与回写全部依赖 [OfficeCLI](https://d.officecli.ai/)（单一二进制），AI 只负责中间的内容对齐
- 逐段落 `set --find/--replace` 编辑匹配的 `<a:t>` 文本节点 → 单 run 段落**零样式漂移**
- 所有替换以一条 `officecli batch` 原子提交，任一失败自动回滚
- 回写前强制校验门禁（`validate_md.py`），回写后按页 `get` 复核 + `view issues` 溢出对比基线
- 表格完整支持；组合形状自动降级并在交付时如实告知受影响形状

## 何时用

触发词：**换内容、内容替换、套模板、改文案保持格式**。

典型场景：上传旧 PPT + 新文案（Word 或长文本），要求「套用这个 PPT 的格式改内容」「生成同样式的新 PPT」。

## 工作流

1. **解析模板**：`parse_ppt.py deck.pptx` → 模板 IR（每个文本块的 path/role/level/size/budget）
2. **规范化素材**：`normalize_input.py input.docx` → 纯文本素材
3. **AI 对齐**（助手完成）：按模板结构重写内容，遵守字符预算，标记行逐字符保留
4. **校验**：`validate_md.py` 强制门禁，不过不回写
5. **原子回写 + 质检**：`apply_md.py` → 逐段 find/replace 零样式漂移，失败自动回滚
6. **交付**：新 PPT + 如实报告改动块 / 保留原文 / 未替换形状

## 安装

作为 Hermes skill 部署（推荐）：

```bash
# 把整个仓库复制到你的 Hermes skills 目录（如 productivity/ppt-content-replace/）
cp -r quseit-ppt-content-replace $HERMES_HOME/skills/productivity/ppt-content-replace
```

**前置条件**：

- **OfficeCLI**（必装）。本技能所有 PPT 解析与回写均依赖 OfficeCLI，AI 仅负责中间的内容对齐。
  - 源码仓库：https://github.com/iOfficeAI/OfficeCLI
  - Windows 安装：`irm https://d.officecli.ai/install.ps1 | iex`
  - 安装后验证：`officecli --version`
- Python 3（仅标准库，无第三方依赖）

## 仓库结构

```
quseit-ppt-content-replace/
├── SKILL.md                    # 技能主文档（工作流 + 硬规则 + 降级路径）
├── references/
│   ├── ir-format.md            # IR 格式规范与 AI 对齐约束
│   └── officecli-recipes.md    # 本技能用到的 OfficeCLI 命令速查
├── scripts/
│   ├── parse_ppt.py            # PPT → 模板 IR
│   ├── normalize_input.py      # Word/文本 → 纯文本素材
│   ├── validate_md.py         # 对齐结果校验门禁
│   ├── apply_md.py            # 原子回写（batch find/replace + 质检）
│   ├── occ_common.py          # 公共：OfficeCLI 探测与调用
│   └── check_officecli.py     # 检测/自动安装 OfficeCLI
├── assets/                     # 可选：自包含 OfficeCLI 二进制（放入后技能完全独立运行）
│   └── officecli.exe           # 放入后优先使用，缺则回退系统安装
└── work/                      # 运行产物目录（模板 IR / 素材 / final.md）
```

### 自包含 OfficeCLI（可选）

技能支持 **自包含 OfficeCLI**，放入后其他用户克隆即可直接使用，无需单独安装：

1. 从本机复制：`cp ~/to/path/OfficeCLI/bin/officecli.exe assets/`
2. 或运行自动下载：`python scripts/check_officecli.py --install`

技能会按以下优先级查找 OfficeCLI：
1. `assets/officecli.exe`（技能自包含）
2. 系统 PATH / 环境变量 / 常见安装路径

## 已知限制

- OfficeCLI `set --find/--replace` 仅编辑匹配的 `<a:t>` 文本节点：单 run 段落零样式漂移；多 run 段落的整段替换会合并 run（继承首 run 样式）
- 「粗体标签 + 普通正文」混排：模板携带 `find="..."` 提示，只替换正文 run，标签样式保留；段内更复杂的混排（如中间高亮词）可能丢失，需 L3 `raw` 编辑 XML
- 组合形状（group）：解析可深入，但 find/replace 不支持 group 内路径，自动降级为成员 shape 级 `set text`（run 样式归一为 shape 默认），输出会列出受影响形状

## 使用注意

> ⚠️ **上传的 PPT 模板和 Word 文档在内容上要尽量相近，越相近内容编排效果越好。**

本技能基于模板已有的**版式结构**（标题层级、段落数、表格列数、图说位置等）反向编排新素材内容：

- **模板与素材主题契合**（例如："C公司 AI 报告" ↔ "C公司 AI 新报告"）：AI 对齐只需做内容替换，编排效果最佳
- **结构差异大**（例如："E企业 AI 9 页模板" ↔ "通用企业 Agent 8 章论文" 或 "2026年第三季度工作总结与规划 20 页模板" ↔ "业务发展复盘与战略思考 3 大主题"）：AI 需把素材拆散重排，可能出现标题被压缩、段落需要合并或扩写的情况，最终内容与原素材叙述顺序差异较大
- **完全无关领域**（例如：旅游模板 ↔ 财务报告）：编排效果通常较差，建议先换一个与素材主题更接近的 PPT 模板

**建议**：准备 PPT 时，先选好与目标素材主题相近的模板，再让技能做内容替换。

## License

[Apache-2.0](LICENSE) © 2026 Tricro968
