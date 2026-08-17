# OfficeCLI 命令速查（本技能用到的子集）

完整文档见 https://github.com/iOfficeAI/OfficeCLI 。本技能只用以下命令。
所有命令加 `--json` 可得结构化输出。Windows 下本机可用二进制：
`~/.office-form-filler/bin/officecli.exe`（脚本会自动探测）。

## 会话管理

```bash
officecli open deck.pptx      # 常驻模式打开（后续命令近零延迟）
officecli close deck.pptx     # 保存并释放
```

## 解析

```bash
# 全部段落（快速）
officecli query deck.pptx "paragraph" --json

# 逐页取结构：slide → shape → paragraph → run（parse_ppt.py 使用）
officecli get deck.pptx '/slide[1]' --depth 4 --json
```

get 返回的 JSON 形状：

```json
{"success": true, "data": {"results": [{
  "path": "/slide[1]", "type": "slide",
  "children": [{
    "path": "/slide[1]/shape[@id=2]", "type": "title",
    "text": "标题", "format": {"isTitle": true, "phType": "title", "size": "44pt"},
    "children": [
      {"path": ".../paragraph[1]", "type": "paragraph", "text": "标题",
       "format": {"level": 0}, "children": [...]}
    ]
  }]
}]}}
```

角色判定：`format.isTitle == true` 或 `phType in (title, ctrTitle)` → title；
`phType == subTitle` → subtitle；其余有文本的形状 → body。

## Word 输入解析

```bash
officecli view report.docx outline      # 大纲（标题层级）
officecli view report.docx annotated    # 带样式注释，信息更全
```

## 回写

> 本技能主策略是 `set --find/--replace`：只编辑匹配的 `<a:t>` 文本节点，
> 单 run 段落实现零样式漂移；多 run 段落的整段 find 会合并 run（继承首 run 样式）。
> 对含 `find` 提示的混排段落，仅替换正文 run，标签 run 样式完全保留。
> 不推荐直接用 `set --prop text=...` 设置段落，因为那是 shape 级归一化，
> 会重写整个 shape、坍缩多段结构并统一 run 样式。

```bash
# find/replace 单段（零样式漂移）
officecli set deck.pptx '/slide[1]/shape[@id=2]/paragraph[1]' \
  --prop find="旧标题" --prop replace="新标题"

# 批量原子替换（apply_md.py 使用；逐段 find/replace）
officecli batch deck.pptx --commands '[
  {"command":"set","path":"/slide[1]/shape[@id=2]/paragraph[1]","props":{"find":"旧标题","replace":"新标题"}}
]' --json
```

**注意事项**：
- `find` 支持段落级 path，结果只影响匹配到的 run(s)
- 跨多个 run 的 find 匹配会合并为单个 run（取首 run 样式）
- 0 匹配时 batch 仍返回 success（静默成功），必须在回写后通过 `get` 逐段校验实际文本
- `raw` 命令不支持 shape 级 path，取整页需 `raw '/slide[1]'`

## 质检

```bash
officecli view deck.pptx issues --json     # 文本溢出等文档问题检测
officecli view deck.pptx outline           # 快速核对结构
officecli view deck.pptx screenshot --grid auto -o preview.png          # 全页缩略图
officecli view deck.pptx screenshot --page 1 -o slide1.png               # 单页截图
officecli view deck.pptx screenshot --page 1,3,5 -o sel.png             # 多页截图
officecli watch deck.pptx                                                # 浏览器实时预览 localhost:26315
```

## 常见错误码

`not_found`（路径错，检查 @id）、`invalid_value`（属性值格式错）、
`file_locked`（文件被占用，先 close）。错误对象自带 `suggestion` 字段。
