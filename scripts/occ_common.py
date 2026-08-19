"""Shared helpers for ppt-content-replace skill scripts."""
import os
import re
import shutil
import subprocess
import sys

BLOCK_RE = re.compile(
    r"^<!--\s*block\s+path=(\S+)\s+role=(\w+)\s+level=(\d+)"
    r"(?:\s+size=([\w.]+))?"
    r'(?:\s+find="([^"]*)")?'
    r"\s+budget=(\d+)\s*-->$"
)
SLIDE_RE = re.compile(r"^<!--\s*slide:(\d+)\s*(.*?)\s*-->$")
HEADER_RE = re.compile(r"^<!--\s*OCC-TEMPLATE\s+v1\s+(.*?)\s*-->$")


def get_skill_dir():
    """获取技能目录路径。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(script_dir)


def find_officecli():
    # 1. 技能目录内的 assets/officecli.exe（自包含优先）
    skill_dir = get_skill_dir()
    local_bin = os.path.join(skill_dir, "assets", "officecli.exe")
    if os.path.isfile(local_bin):
        return local_bin

    # 2. 系统安装
    candidates = [
        os.environ.get("OFFICECLI"),
        shutil.which("officecli"),
        os.path.expanduser("~/.office-form-filler/bin/officecli.exe"),
        os.path.expanduser("~/.workbuddy/binaries/officecli.exe"),
        os.path.expanduser("~/.officecli/bin/officecli.exe"),
    ]
    for c in candidates:
        if c and os.path.isfile(os.path.expanduser(c)):
            return os.path.expanduser(c)
    sys.exit(
        "officecli not found. Run: python scripts/check_officecli.py --install\n"
        "Or manually install: https://github.com/iOfficeAI/OfficeCLI/releases"
    )


def run_occ(args, check=True):
    proc = subprocess.run(
        [find_officecli()] + args,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if check and proc.returncode != 0:
        sys.exit(
            "officecli %s failed (exit %d)\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (" ".join(args[:4]), proc.returncode, proc.stdout, proc.stderr)
        )
    return proc


def occ_json(proc):
    """Parse the JSON envelope officecli prints (stdout may mix non-JSON lines)."""
    import json
    txt = proc.stdout.strip()
    start = txt.find("{")
    if start < 0:
        return None
    try:
        return json.loads(txt[start:])
    except json.JSONDecodeError:
        return None


class Block:
    """A replaceable paragraph block. `find` (optional) is the run-level text
    hint emitted by parse_ppt for multi-run paragraphs: the trailing body run
    that should be rewritten while the leading label run keeps its formatting.
    Its value must not contain a double quote (marker syntax limitation)."""

    def __init__(self, path, role, level, size, budget, text, find=None):
        self.path, self.role, self.level = path, role, int(level)
        self.size, self.budget = size, int(budget)
        self.text = text
        self.find = find

    def marker(self):
        size_part = " size=%s" % self.size if self.size else ""
        find_part = ' find="%s"' % self.find if self.find else ""
        return ("<!-- block path=%s role=%s level=%d%s%s budget=%d -->"
                % (self.path, self.role, self.level, size_part, find_part,
                   self.budget))


def parse_blocks(md_text):
    """Parse IR markdown into a list of Block. Content = lines until next marker."""
    blocks, cur = [], None
    for line in md_text.splitlines():
        m = BLOCK_RE.match(line.strip())
        if m:
            if cur:
                blocks.append(cur)
            cur = Block(m.group(1), m.group(2), m.group(3), m.group(4),
                        m.group(6), "", find=m.group(5))
        elif SLIDE_RE.match(line.strip()) or HEADER_RE.match(line.strip()):
            if cur:
                blocks.append(cur)
                cur = None
        elif cur is not None:
            if line.strip():
                cur.text = (cur.text + "\n" + line).strip("\n") if cur.text else line.strip()
    if cur:
        blocks.append(cur)
    return blocks


def budget_limit(budget):
    """Max allowed characters for a block with the given budget."""
    return int(budget * 1.25) + 2
