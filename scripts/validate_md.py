#!/usr/bin/env python3
"""Stage 4 gate: validate that final.md structurally matches template.md.

Checks:
  1. same number of blocks, identical paths in identical order
  2. every block non-empty
  3. every block within character budget (budget * 1.25 + 2)

Usage:
    python validate_md.py template.md final.md [--json]
Exit code 0 = pass, 1 = fail (errors printed for AI retry).
"""
import argparse
import json
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from occ_common import parse_blocks, budget_limit  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("template")
    ap.add_argument("final")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    tpl = parse_blocks(open(args.template, encoding="utf-8").read())
    fin = parse_blocks(open(args.final, encoding="utf-8").read())

    errors = []
    if len(tpl) != len(fin):
        errors.append("block count mismatch: template=%d final=%d" % (len(tpl), len(fin)))
    for i in range(min(len(tpl), len(fin))):
        t, f = tpl[i], fin[i]
        if t.path != f.path:
            errors.append("block %d: path changed: %s -> %s" % (i + 1, t.path, f.path))
            continue
        if not f.text.strip():
            errors.append("block %d (%s): empty content" % (i + 1, t.path))
        limit = budget_limit(t.budget)
        over = len(f.text) - limit
        if over > 0:
            errors.append(
                "block %d (%s): %d chars over budget (budget=%d, limit=%d, got=%d)"
                % (i + 1, t.path, over, t.budget, limit, len(f.text))
            )

    result = {"ok": not errors, "blocks": len(tpl), "errors": errors}
    # Advisory: high unchanged ratio usually means the AI alignment step
    # barely mapped the user material (or not at all) -- catch it here,
    # before the write-back delivers a near-copy as "success".
    n_same = sum(1 for t, f in zip(tpl, fin) if t.text == f.text)
    result["unchanged"] = n_same
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif errors:
        print("VALIDATION FAILED (%d error(s)):" % len(errors))
        for e in errors:
            print("  - " + e)
    else:
        print("OK: %d blocks, all within structure and budget." % len(tpl))
    if tpl and n_same == len(tpl):
        print("WARNING: final.md is IDENTICAL to the template -- the alignment "
              "step changed nothing. Do NOT proceed; re-run content alignment "
              "against the user material.")
    elif tpl and n_same > len(tpl) * 0.6:
        print("WARNING: %d/%d blocks unchanged (kept original text). If the "
              "user material should cover them, go back and fix the alignment."
              % (n_same, len(tpl)))
    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()
