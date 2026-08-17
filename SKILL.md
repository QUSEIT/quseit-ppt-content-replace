---
name: ppt-content-replace
description: 基于已有 PPT 模板的内容替换技能。当用户上传一份 PPT 作为版式模板，并提供新内容（Word 文档或大段文本），要求"只换内容不动版式"、"套用这个 PPT 的格式改内容"、"生成同样式的新 PPT"时使用。通过 OfficeCLI 解析 PPT 结构生成带定位标记的模板 Markdown（IR），将用户内容 AI 对齐到模板结构（不足扩写、过多压缩），校验后原子回写为一份仅内容变化的新 PPT，全程保留原版式与样式。触发词：换内容、内容替换、套模板、改文案保持格式。
---

# ppt-content-replace：PPT 内容替换（版式不变）

把一份 PPT 当作"版式模板"，用用户提供的新素材（Word / 长文本）重写其中所有文字，
输出一份**只改内容、版式样式完全不变**的新 PPT。

核心思想：PPT 结构 → 模板 Markdown（IR）→ AI 对齐 → 校验 → 原子回写。
解析与回写全部依赖 OfficeCLI（单一二进制，本机已安装），AI 只负责中间的对齐。

> 已知限制：OfficeCLI `set --find/--replace` 仅编辑匹配的 `<a:t>` 文本节点，因此单 run 段落
> 实现零样式漂移；多 run 段落的整段替换会合并 run（继承首 run 样式）。
> 对"粗体标签+普通正文"这类混排，模板会携带 `find="..."` 提示，apply_md 只替换正文 run，
> 从而保留标签样式。若需保留段内更复杂的混排（如中间出现高亮词），仍可能丢失，此时需手动
> 用 L3 `raw` 编辑 XML。

## 前置条件

- OfficeCLI 已安装（`officecli --version` 可执行）。脚本自动探测：
  `OFFICECLI` 环境变量 → PATH → `~/.office-form-filler/bin/officecli.exe` 等已知位置。
- Python 3（仅标准库）。
- 若 officecli 缺失：Windows 执行 `irm https://d.officecli.ai/install.ps1 | iex`。

## 工作流（严格按序执行）

设技能目录为 `SKILL_DIR`，用户模板 PPT 为 `deck.pptx`，素材为 `input.docx` 或长文本。

### 1. 解析模板

```bash
python SKILL_DIR/scripts/parse_ppt.py deck.pptx -o work/deck.template.md
```

产出模板 IR（含每个文本块的 path/role/level/size/budget）。格式规范见
`references/ir-format.md`。若 block 数为 0，提示用户该 PPT 无可替换文本。

### 2. 规范化用户素材

```bash
python SKILL_DIR/scripts/normalize_input.py input.docx -o work/user.md
# 纯文本素材：直接把用户消息里的文字存为 work/user.md，无需跑脚本
```

### 3. AI 对齐（由助手本人完成，不是脚本）

读取 `deck.template.md` 与 `user.md`，产出 `work/final.md`。硬规则：

1. **所有标记行（`<!-- ... -->`）逐字符原样保留**，一个都不能增删改
2. 只编辑标记行之间的内容行；内容是纯文本，不加 `#`、`-`、`**` 等 Markdown 装饰
3. 每个 block 遵守字符预算：新文本长度 ≤ `budget * 1.25 + 2`；素材不足就基于素材
   合理扩写（但别超预算），素材过多就压缩提炼
4. 严格贴合模板的角色与层级：title 块写标题式短语，body 块按原层级写正文/列表内容
5. 素材确实覆盖不到的 block 才允许保留原文，且保留是例外不是默认——宁可基于
   素材主题合理改写，也不要原样照抄模板旧内容；小标题、正文都要贴合新素材重写
6. 专业术语、数字、产品名等事实性内容以素材为准，不得编造
7. 对齐后自查改动覆盖率：final.md 与模板逐块对比，大部分 block 未变化即映射
   失败，必须重新对齐（validate_md.py 与 apply_md.py 的 WARNING 都会提示）

### 4. 校验（强制门禁，不过不回写）

```bash
python SKILL_DIR/scripts/validate_md.py work/deck.template.md work/final.md
```

失败则把报错逐条修正到 final.md 后重跑，最多 3 轮；仍失败则向用户报告冲突点。
若输出 WARNING 提示大量 block 未改动（>60% 或全同），必须回第 3 步重新对齐，
不得带着 WARNING 直接回写。

### 5. 原子回写 + 质检

```bash
python SKILL_DIR/scripts/apply_md.py deck.pptx work/deck.template.md work/final.md -o deck.filled.pptx
```

- **逐段落 find/replace**：每个变化段落生成一条 `set --find <模板原文> --replace <新文本>`，
  OfficeCLI 只编辑匹配的 `<a:t>` 节点，从而**零样式漂移**（字号、颜色、粗体均保持）
- 若模板 block 携带 `find="..."` 提示（parse_ppt 为"标签+正文"混排自动生成），
  apply_md 只替换正文 run，标签 run 的样式完全保留
- 只改动文本发生变化的段落，未改动的段落保持原 XML 零漂移；输出末尾列出
  UNCHANGED 清单——exit code = 3（final 与模板全同）时**禁止交付**，回第 3 步
- 所有替换以一条 `officecli batch` 原子提交，任一失败自动回滚；
  回写成功后按页 `get` 校验实际文本，确保无静默失败
- 自动跑 `view issues` 做溢出检测，并与模板基线对比：只报告**本次引入的溢出**
  （新增或恶化）；若 exit code = 2，把溢出 block 压缩后重走第 4、5 步
- 需要视觉复核时：`officecli view deck.filled.pptx screenshot --page N --out pN.png`

### 6. 交付

用 present_files 向用户交付新 PPT（和/或截图预览）。交付说明中如实报告：
改动块数、保留原文的 block（UNCHANGED 清单）及其原因、skipped 清单中未替换的形状。

## 硬规则

- 永远不修改用户的原始 deck.pptx；所有回写只作用于副本
- 回写前 validate_md.py 必须通过，无例外
- 不改字体、颜色、位置、形状、图片——只 set 段落 text
- OfficeCLI 命令报错时读错误对象的 `suggestion` 字段修复，不要盲试
- apply_md.py 使用 `set --find/--replace` 按段落级路径操作，不是 shape 级归一化；
  对含 `find` 提示的混排段落，仅替换正文 run，标签 run 的样式保持不变

## 降级路径

- `batch` 报 `unsupported_property` / 路径异常：用 `officecli get deck.pptx '<path>'`
  核对实际路径；个别顽固形状可用 L3 层 `raw-set`（XPath）兜底
- 表格已完整支持：parse_ppt 递归解析 table→tr→tc（每格一个 role=cell 的
  block），apply_md 对 cell 路径同样走 find/replace，零样式漂移
- 组合形状（group）：解析可深入成员段落，但 officecli 的 find/replace 与 get
  均不支持 group 内路径；apply_md 自动降级为成员 shape 级 `set text`（段落以
  \n 连接），**run 样式会归一为 shape 默认**，输出会列出受影响形状——交付时告知用户
- 解析输出末尾如出现 `skipped` 清单（SmartArt 等无法处理的带文字形状），
  **必须在交付时明确告知用户哪些内容未被替换**——不允许静默跳过

## 参考资料

- `references/ir-format.md` — IR 格式规范与 AI 对齐约束（对齐前必读）
- `references/officecli-recipes.md` — 本技能用到的 OfficeCLI 命令速查
