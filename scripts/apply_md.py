#!/usr/bin/env python3
"""Stage 5-6: apply final.md back into a copy of the pptx (atomic), then QA.

Usage:
    python apply_md.py deck.pptx template.md final.md [-o deck.filled.pptx] [--no-issues]

Write strategy (found in real-PPT testing):
  * officecli `set --find/--replace` edits ONLY the matched <a:t> text and
    keeps every run's formatting (size/bold/color), paragraph-level path
    confines the search to one paragraph. This is the zero-style-drift path.
  * Plain `set paragraph[N] text=...` is shape-level normalization: it
    rewrites the whole shape, collapsing multi-paragraph shapes (a later
    paragraph[N] then fails) and re-styling runs to the shape default.
  * Therefore: one find/replace op per CHANGED paragraph. find is normally
    the full template paragraph text; when the template block carries a
    `find="..."` hint (multi-run "label + body" paragraph), only the body
    run is rewritten so the label keeps its bold/color/size. Untouched
    paragraphs keep exact original XML.
  * A 0-match find "succeeds" silently, so after the batch we verify every
    changed block against final.md, failing loudly on any mismatch. Perf:
    one `get --depth 12` per CHANGED SLIDE builds a path->text map; a direct
    per-path `get` re-check runs only on mismatch (slide-tree paragraph
    enumeration can differ for soft breaks).

QA: `view issues` is compared against the template baseline — only newly
introduced or worsened overflows are reported (template's own layout issues
are not our responsibility and are ignored).

Exit codes: 0 ok | 1 batch/find failed | 2 overflow regressions.
"""
import argparse
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from occ_common import run_occ, occ_json, parse_blocks  # noqa: E402

PARA_RE = re.compile(r"/paragraph\[(\d+)\]$")
NEED_RE = re.compile(r"need\s+(\d+)pt")


def shape_key(path):
    """'/slide[2]/shape[@id=6]/paragraph[2]' -> '/slide[2]/shape[@id=6]'."""
    m = PARA_RE.search(path)
    return path[: m.start()] if m else path


def group_by_shape(blocks):
    """Return ({shape_key: [Block...]}, ordered keys) preserving template order."""
    out, order = {}, []
    for b in blocks:
        k = shape_key(b.path)
        if k not in out:
            out[k] = []
            order.append(k)
        out[k].append(b)
    return out, order


def split_replace(t, f):
    """Choose (find, replace) strings for one paragraph.

    Default: find = full template text, replace = full final text. For a
    multi-run paragraph the template carries a `find` hint (the trailing body
    run text). If the final text keeps the same label prefix, only the body
    run is rewritten — the label run keeps its bold/color/size. Otherwise the
    whole paragraph is replaced (runs collapse to the first run's style,
    which is acceptable when the old label/number is dropped entirely).
    """
    if t.find and t.text.endswith(t.find):
        label = t.text[: -len(t.find)]
        if label and f.text.startswith(label):
            return t.find, f.text[len(label):]
    return t.text, f.text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx")
    ap.add_argument("template_md")
    ap.add_argument("final_md")
    ap.add_argument("-o", "--output")
    ap.add_argument("--no-issues", action="store_true")
    args = ap.parse_args()

    for p in (args.pptx, args.template_md, args.final_md):
        if not os.path.isfile(p):
            sys.exit("File not found: %s" % p)

    out = args.output or os.path.splitext(args.pptx)[0] + ".filled.pptx"
    shutil.copy2(args.pptx, out)

    tpl_by_shape, _ = group_by_shape(
        parse_blocks(open(args.template_md, encoding="utf-8").read()))
    fin_by_shape, order = group_by_shape(
        parse_blocks(open(args.final_md, encoding="utf-8").read()))
    if not fin_by_shape:
        sys.exit("No blocks found in %s" % args.final_md)

    ops, changed_paras, group_shapes, group_verify = [], [], [], []
    unchanged = []  # blocks kept identical to the template (visible in report)
    for k in order:
        fin_paras = fin_by_shape.get(k) or []
        tpl_paras = tpl_by_shape.get(k) or []
        changed = [(f, t) for f, t in zip(fin_paras, tpl_paras) if f.text != t.text]
        unchanged.extend(f.path for f, t in zip(fin_paras, tpl_paras)
                         if f.text == t.text)
        if not changed:
            continue
        if "/group[" in k:
            # officecli find/replace scope rejects group-nested paths
            # ("Expected /slide[N]/<shape>[M]..."). Fallback: one shape-level
            # `set text` for the whole member shape, paragraphs joined by
            # newline. CAVEAT: run styles normalize to the shape default
            # (shape-level set semantics), unlike the zero-drift find/replace
            # path used for top-level shapes.
            final_text = "\n".join(f.text for f in fin_paras)
            ops.append({"command": "set", "path": k, "props": {"text": final_text}})
            group_shapes.append((k, len(fin_paras)))
            # NOTE: officecli `get` cannot address paragraph paths inside
            # groups (not_found) -- verify at the member-shape level instead.
            group_verify.append((k, final_text))
            for f, _t in changed:
                changed_paras.append((f.path, "(group shape-level set)",
                                      final_text, f.text))
            continue
        for f, t in changed:
            find_str, replace_str = split_replace(t, f)
            ops.append({"command": "set", "path": f.path,
                        "props": {"find": find_str, "replace": replace_str}})
            changed_paras.append((f.path, find_str, replace_str, f.text))

    if not ops:
        print("NO CONTENT CHANGES: final.md is identical to the template; "
              "%s is just a copy of the original. This almost always means "
              "the AI alignment step failed to map the user material. Do NOT "
              "deliver -- go back to step 3 (alignment), and check that "
              "user.md actually contains the material (step 2)." % out)
        sys.exit(3)

    proc = run_occ(["batch", out, "--commands", json.dumps(ops, ensure_ascii=False),
                    "--json"], check=False)
    result = occ_json(proc)
    summary = ((result or {}).get("data") or {}).get("summary") or {}
    if not (result or {}).get("success") or summary.get("succeeded") != len(ops):
        print("BATCH FAILED (rolled back, output file unchanged):")
        for r in ((result or {}).get("data") or {}).get("results") or []:
            if not r.get("success"):
                print("  - %s: %s (%s)" % (r.get("item", {}).get("path"),
                                           r.get("error"), r.get("code")))
        sys.exit(1)

    # A 0-match find "succeeds" silently (and large batches omit per-item
    # output), so success alone is not proof. Verify each changed paragraph's
    # actual text against the final.md text via `get`.
    #
    # Perf: one `get` subprocess per paragraph is slow on Windows (~100ms+
    # each). Instead fetch each CHANGED SLIDE once with --depth 12 and build a
    # path->text map from the tree (covers paragraphs, table cells and group
    # members alike). On any mismatch, re-check that single path with a direct
    # get before declaring failure -- the slide tree may enumerate soft-break
    # paragraphs differently than a paragraph-scoped get (see parse_ppt).
    checks = [(p, exp) for p, _fs, _rs, exp in changed_paras
              if "/group[" not in p]
    checks += [(sp, exp.replace("\x0b", "\n")) for sp, exp in group_verify]

    def direct_get_text(path):
        g = run_occ(["get", out, path, "--json"], check=False)
        gdata = (occ_json(g) or {}).get("data") or {}
        results = gdata.get("results") or []
        return results[0].get("text") if results else None

    slide_re = re.compile(r"^/slide\[(\d+)\]")
    slides_needed = sorted({int(slide_re.match(p).group(1))
                            for p, _ in checks if slide_re.match(p)})
    text_map = {}
    for n in slides_needed:
        g = run_occ(["get", out, "/slide[%d]" % n, "--depth", "12", "--json"],
                    check=False)
        gdata = (occ_json(g) or {}).get("data") or {}
        results = gdata.get("results") or []
        stack = list(results)
        while stack:
            node = stack.pop()
            if node.get("path") and node.get("text") is not None:
                prev = text_map.setdefault(node["path"], node["text"])
                if prev is None:
                    text_map[node["path"]] = node["text"]
            stack.extend(node.get("children") or [])

    not_applied = []
    for path, expected in checks:
        got = text_map.get(path)
        if got is not None:
            got = got.replace("\x0b", "\n")
        if got != expected:
            got = direct_get_text(path)  # authoritative re-check
            if got is not None:
                got = got.replace("\x0b", "\n")
            if got != expected:
                not_applied.append((path, expected, got))
    if not_applied:
        print("VERIFICATION FAILED (%d paragraph(s) did not reach final text):"
              % len(not_applied))
        for path, exp, got in not_applied:
            print("  - %s\n      expected: %r\n      actual:   %r"
                  % (path, exp, got))
        sys.exit(1)

    print("Applied %d paragraph(s) via find/replace (run styles preserved) -> %s"
          % (len(ops), out))
    for path, find_str, _rep, _exp in changed_paras:
        print("  %s  find=%r" % (path, find_str))
    total_blocks = len(changed_paras) + len(unchanged)
    if unchanged:
        print("UNCHANGED (kept original text): %d/%d block(s):"
              % (len(unchanged), total_blocks))
        for p in unchanged[:20]:
            print("  - %s" % p)
        if len(unchanged) > 20:
            print("  ... and %d more" % (len(unchanged) - 20))
        if len(unchanged) > total_blocks * 0.6:
            print("WARNING: most blocks unchanged -- the alignment probably "
                  "under-mapped the user material. Consider redoing step 3.")
    if group_shapes:
        print("NOTE: %d group member shape(s) rewritten via shape-level set text"
              " (officecli find/replace does not reach inside groups);"
              " their run styles normalize to the shape default:" % len(group_shapes))
        for k, n in group_shapes:
            print("  - %s (%d paragraphs)" % (k, n))

    if not args.no_issues:
        base = _issue_map(args.pptx)
        filled = _issue_map(out)
        regressions = []
        for path, need in filled.items():
            if path not in base or need > base[path]:
                regressions.append((path, need, base.get(path)))
        if regressions:
            print("REGRESSION OVERFLOWS (%d, not present in template baseline):"
                  % len(regressions))
            for path, need, bneed in regressions:
                print("  - %s need=%spt (baseline %s)" % (path, need, bneed or "none"))
            print("Fix: compress the listed blocks, re-run validate_md.py + apply_md.py")
            sys.exit(2)
        print("QA clean: %d baseline overflow(s) unchanged, no regressions." % len(base))
    print("Done. Visual check: officecli view %s screenshot" % out)


def _issue_map(pptx):
    """path -> overflow need(pt) from `view issues`. Absent path = no overflow."""
    proc = run_occ(["view", pptx, "issues", "--json"], check=False)
    data = (occ_json(proc) or {}).get("data") or {}
    out = {}
    for it in data.get("issues") or []:
        m = NEED_RE.search(it.get("message") or "")
        out[it.get("path")] = int(m.group(1)) if m else 0
    return out


if __name__ == "__main__":
    main()
