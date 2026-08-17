#!/usr/bin/env python3
"""Stage 1-2: parse a .pptx into template Markdown (IR).

Usage:
    python parse_ppt.py deck.pptx [-o deck.template.md]

Extracts every replaceable text block (title / subtitle / body paragraphs)
with its OfficeCLI path, role, list level, font size and character budget.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from occ_common import run_occ, occ_json  # noqa: E402

TEXTUAL_TYPES = {"title", "subtitle", "textbox", "body", "placeholder"}
TITLE_PHTYPES = {"title", "ctrTitle"}


def get_slide(path, slide_idx):
    # depth 4 so run nodes (text + size/bold/color) come inline; needed for
    # the per-paragraph `find` hint of multi-run ("label + body") paragraphs.
    proc = run_occ(["get", path, "/slide[%d]" % slide_idx, "--depth", "4", "--json"])
    data = occ_json(proc)
    if not data or not data.get("success"):
        return None
    results = data["data"].get("results") or []
    return results[0] if results else None


def get_shape(path, shape_path):
    """Shape-level get is authoritative for paragraph enumeration."""
    proc = run_occ(["get", path, shape_path, "--depth", "4", "--json"])
    data = occ_json(proc)
    if not data or not data.get("success"):
        return None
    results = data["data"].get("results") or []
    return results[0] if results else None


def run_find_hint(para):
    """For a multi-run paragraph shaped like `label-run + body-run`, return the
    trailing body-run text so the writer can rewrite ONLY the body (keeping the
    label run's bold/color/size). Return None for single-run paragraphs and for
    multi-run paragraphs whose first/last runs share the same style (full-text
    replacement is then acceptable — the collapsed run inherits that style).
    """
    runs = [c for c in para.get("children") or [] if c.get("type") == "run"]
    if len(runs) < 2:
        return None

    def sig(r):
        fmt = r.get("format") or {}
        return (fmt.get("bold"), fmt.get("size"), fmt.get("color"))

    if sig(runs[0]) != sig(runs[-1]):
        text = (runs[-1].get("text") or "").strip()
        return text or None
    return None


def shape_role(shape):
    fmt = shape.get("format") or {}
    stype = shape.get("type", "")
    ph = fmt.get("phType", "")
    if fmt.get("isTitle") or stype == "title" or ph in TITLE_PHTYPES:
        return "title"
    if stype == "subtitle" or ph == "subTitle":
        return "subtitle"
    return "body"


def _shape_blocks(shape, pptx_path):
    """Collect paragraph blocks from a textual shape. Returns block list."""
    fmt = shape.get("format") or {}
    role = shape_role(shape)
    size = fmt.get("size") or fmt.get("effective.size") or ""
    paras = shape.get("children") or []
    if len([p for p in paras if p.get("type") == "paragraph"]) > 1:
        # Multi-paragraph shapes: re-resolve at shape level to get
        # authoritative paragraph list (slide-level may split soft breaks).
        resolved = get_shape(pptx_path, shape["path"])
        if resolved and resolved.get("children"):
            paras = resolved.get("children")
    blocks = []
    for para in paras:
        if para.get("type") != "paragraph":
            continue
        text = (para.get("text") or "").strip()
        if not text:
            continue
        level = (para.get("format") or {}).get("level", 0) or 0
        budget = max(len(text), 1)
        blocks.append({
            "path": para["path"], "role": role, "level": level,
            "size": size, "budget": budget, "text": text,
            "find": run_find_hint(para),
        })
    return blocks


def _table_blocks(table):
    """Collect one block per non-empty table cell (table -> tr -> tc).
    Cell paths are leaves in officecli (childCount 0): find/replace on the
    tc path rewrites the cell text while keeping cell/run formatting."""
    blocks = []
    for tr in table.get("children") or []:
        if tr.get("type") != "tr":
            continue
        for tc in tr.get("children") or []:
            if tc.get("type") != "tc":
                continue
            text = (tc.get("text") or "").strip()
            if not text:
                continue
            size = (tc.get("format") or {}).get("size") or ""
            blocks.append({
                "path": tc["path"], "role": "cell", "level": 0,
                "size": size, "budget": max(len(text), 1), "text": text,
                "find": None,  # cells expose no run nodes
            })
    return blocks


def _walk_nodes(nodes, pptx_path, blocks, skipped):
    """Recursively collect blocks from slide-level children.
    Tables yield cell blocks; groups are re-resolved and recursed; any
    text-bearing node that yields nothing is recorded in `skipped` so the
    agent can tell the user exactly what was NOT replaced."""
    for node in nodes:
        ntype = node.get("type", "")
        text = (node.get("text") or "").strip()
        if ntype == "table":
            blocks.extend(_table_blocks(node))
        elif ntype == "group":
            # Re-resolve the group at its own path (depth from group node:
            # group -> shape -> paragraph -> run) and recurse into members.
            resolved = get_shape(pptx_path, node.get("path"))
            children = (resolved or node).get("children") or []
            inner, inner_skipped = [], []
            _walk_nodes(children, pptx_path, inner, inner_skipped)
            blocks.extend(inner)
            skipped.extend(inner_skipped)
            if not inner and not inner_skipped and text:
                skipped.append((node.get("path"), "group with text but no inner blocks"))
        elif ntype in TEXTUAL_TYPES or text:
            # Ordinary text shapes may come back as plain type "shape" -- the
            # presence of text is the real signal (matches the original filter).
            shape_blocks = _shape_blocks(node, pptx_path)
            blocks.extend(shape_blocks)
            if not shape_blocks and text:
                skipped.append((node.get("path"), "text shape yielded no paragraph blocks"))


def collect_blocks(slide, pptx_path):
    """Returns (blocks, skipped): replaceable text blocks plus a list of
    (path, reason) for text-bearing shapes the skill cannot process."""
    blocks, skipped = [], []
    _walk_nodes(slide.get("children") or [], pptx_path, blocks, skipped)
    return blocks, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    if not os.path.isfile(args.pptx):
        sys.exit("File not found: %s" % args.pptx)

    proc = run_occ(["view", args.pptx, "stats", "--json"])
    stats = occ_json(proc) or {}
    data = stats.get("data") or {}
    slide_count = data.get("slideCount") or data.get("slides") or 0
    if not slide_count:
        # fall back: probe slides until not_found
        slide_count = 0
        while True:
            if get_slide(args.pptx, slide_count + 1) is None:
                break
            slide_count += 1
    if not slide_count:
        sys.exit("No slides found in %s" % args.pptx)

    lines, total, all_skipped = [], 0, []
    for i in range(1, slide_count + 1):
        slide = get_slide(args.pptx, i)
        if slide is None:
            continue
        blocks, skipped = collect_blocks(slide, args.pptx)
        lines.append("<!-- slide:%d -->" % i)
        for path, reason in skipped:
            lines.append("<!-- skipped path=%s reason=%s -->" % (path, reason))
            all_skipped.append((i, path, reason))
        for b in blocks:
            size_part = " size=%s" % b["size"] if b["size"] else ""
            find_part = ' find="%s"' % b["find"] if b["find"] else ""
            lines.append(
                "<!-- block path=%s role=%s level=%d%s%s budget=%d -->"
                % (b["path"], b["role"], b["level"], size_part, find_part,
                   b["budget"])
            )
            lines.append(b["text"])
            total += 1

    header = ("<!-- OCC-TEMPLATE v1 file:%s slides:%d blocks:%d -->"
              % (os.path.basename(args.pptx), slide_count, total))
    out = args.output or os.path.splitext(args.pptx)[0] + ".template.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write(header + "\n" + "\n".join(lines) + "\n")
    print("Template written: %s (%d slides, %d blocks)" % (out, slide_count, total))
    if all_skipped:
        print("WARNING: %d text-bearing shape(s) NOT replaceable -- tell the user:"
              % len(all_skipped))
        for slide_no, path, reason in all_skipped:
            print("  - slide %d %s (%s)" % (slide_no, path, reason))


if __name__ == "__main__":
    main()
