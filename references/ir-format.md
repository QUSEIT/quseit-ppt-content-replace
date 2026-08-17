# IR 格式规范（模板 Markdown / final Markdown 中间表示）

本技能的中间格式是一份带 HTML 注释定位标记的 Markdown。标记行由脚本生成和读取，
**AI 对齐时必须原样保留，一个字符都不能改**；AI 只能编辑标记行之间的内容行。

## 文件结构

```
<!-- OCC-TEMPLATE v1 file:deck.pptx slides:2 blocks:4 -->
<!-- slide:1 -->
<!-- block path=/slide[1]/shape[@id=2]/paragraph[1] role=title level=0 size=44pt budget=6 -->
上半年业务总结
<!-- block path=/slide[1]/shape[@id=100000]/paragraph[1] role=body level=0 size=24pt budget=7 -->
营收增长要点
<!-- slide:2 -->
<!-- block path=/slide[2]/shape[@id=2]/paragraph[1] role=title level=0 size=44pt budget=4 -->
未来规划
...
```

## 标记语法

| 标记 | 说明 |
|---|---|
| `OCC-TEMPLATE v1` | 文件头：源文件名、slide 数、block 数 |
| `slide:N` | 幻灯片分隔符，仅用于可读性，不参与校验 |
| `block path=... role=... level=... size=... budget=...` | 一个可替换文本块，对应 PPT 中的一个段落 |
| `skipped path=... reason=...` | 仅有文字但**无法替换**的形状（如 SmartArt）。解析脚本自动列出，位于 slide 标记之后；不参与校验，但交付时必须告知用户这些内容未替换 |

### block 字段

- **path**：OfficeCLI 元素路径（如 `/slide[1]/shape[@id=2]/paragraph[1]`）
- **find**（可选）：parse_ppt 为多 run "标签+正文" 混排段落生成的正文子串提示。
  出现时表示该段落的首尾 run 样式不同；apply_md 会只替换正文 run，保留标签 run 的样式
- **role**：`title`（页面主标题，含 phType=title/ctrTitle）、`subtitle`（副标题）、
  `body`（正文/小标题/列表项等其余文本）、`cell`（表格单元格，path 以
  `/tc[N]` 结尾；一格一个 block，内容应简洁贴合原格用途，无 run 信息故无 find 提示）
- **level**：段落列表层级（0=普通段，1/2=列表项层级），来自 PowerPoint 段落属性
- **size**：该形状生效字号（如 `44pt`），用于判断文本块重要性，仅供 AI 参考
- **budget**：字符预算 = 原文本长度。新文本长度不得超过 `budget * 1.25 + 2`，
  否则极可能溢出文本框（validate_md.py 会强制校验）

## 内容行规则

- 每个 block 的内容是紧跟标记之后、直到下一个标记之前的所有非空行
- 内容 = 段落的纯文本，**不要**加 Markdown 装饰（`#`、`-`、`**` 等）——
  列表符号、加粗等格式保存在 PPT 段落属性里，写回文本时会被自动继承，
  如果内容里再带装饰符号会出现双重格式
- 一个 block 一律只写一行（一个段落）
- 多段 shape 的各段内容在回写时由 apply_md.py 为每段独立生成 find/replace，
  段落之间互不干扰，不会因 shape 级 set 导致段落被覆盖

## 对齐（AI）操作约束

1. 输出文件必须包含与模板**完全相同、顺序一致**的全部标记行
2. 只修改内容行；空白或无对应素材的 block 允许保留原文或合理引申
3. 每个 block 遵守字符预算：内容不足则扩写（不超过预算），过多则压缩
4. 不得增删 block、不得合并/拆分 block、不得调换 block 顺序
5. 完成后必须运行 validate_md.py 校验，失败则按报错修正后重试（最多 3 轮）
