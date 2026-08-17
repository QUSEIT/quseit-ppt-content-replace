#!/usr/bin/env python3
"""Stage 3: normalize user input (docx / txt / md) into a plain markdown file.

Usage:
    python normalize_input.py input.docx|input.txt|input.md [-o user.md]
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from occ_common import run_occ  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        sys.exit("File not found: %s" % args.input)

    ext = os.path.splitext(args.input)[1].lower()
    out = args.output or os.path.splitext(args.input)[0] + ".user.md"

    if ext in (".txt", ".md", ".markdown"):
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    elif ext in (".docx", ".doc"):
        # annotated mode: every paragraph + its style (outline drops non-headings)
        proc = run_occ(["view", args.input, "annotated"])
        lines = []
        for l in proc.stdout.splitlines():
            l = l.strip()
            if not l or l.startswith("File:") or l.startswith("Note:"):
                continue
            # format: [/body/p[@paraId=00100000]] 「text」 ← Heading1 | 等线 11pt
            body = re.sub(r"^\[.*\]\s+", "", l, count=1)  # strip leading [path] (nested brackets)
            text = body.split("←", 1)[0].strip().strip("「」")
            style = body.split("←", 1)[1].strip() if "←" in body else ""
            if not text:
                continue
            if style.startswith("Heading1") or style.startswith("标题 1"):
                lines.append("# " + text)
            elif style.startswith("Heading2") or style.startswith("标题 2"):
                lines.append("## " + text)
            elif style.startswith("Heading") or style.startswith("标题"):
                lines.append("### " + text)
            else:
                lines.append(text)
        content = "\n".join(lines)
    else:
        sys.exit("Unsupported input type: %s (expected .docx/.txt/.md)" % ext)

    if not content.strip():
        sys.exit("EXTRACTED NOTHING from %s -- officecli 'view annotated' "
                 "returned no usable paragraphs (image-only doc, or output "
                 "format change). Do NOT continue with an empty user.md."
                 % args.input)

    with open(out, "w", encoding="utf-8") as f:
        f.write("# 用户素材\n\n" + content.strip() + "\n")
    print("User content written: %s (%d chars)" % (out, len(content)))


if __name__ == "__main__":
    main()
