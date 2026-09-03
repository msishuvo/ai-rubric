"""Check the conventions a grep can settle.

This exists because of a specific finding: in the audit that motivated the
whole kit, every convention violation in the tree broke a rule the project
had already written down in prose, several of them in files whose own
comments quoted the rule. Prose did not hold.

`rule_source` is mandatory for the same reason in reverse. A check that
cannot cite the rule it enforces is policing something nobody agreed to,
and the first person to hit it will be right to delete it.

Output is a triage list, not a verdict. Some flagged lines will be correct
on reading.

A future version may glob `.claude/rubric.d/*.py` for checks a regex cannot
express, such as one that has to parse a file rather than scan it. That seam
is named here and deliberately not wired: it stays closed until a project
actually has such a check, because opening it later is a change to this
module and opening it now is a contract other projects would depend on.
"""

import os
import re

from rubric import globs

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
             ".build", "build", "dist", ".worktrees", "DerivedData"}


class Finding(object):
    def __init__(self, rule, path, line, text, message, rule_source):
        self.rule = rule
        self.path = path
        self.line = line
        self.text = text
        self.message = message
        self.rule_source = rule_source

    def __eq__(self, other):
        return isinstance(other, Finding) and vars(self) == vars(other)

    def __repr__(self):
        return "Finding(%r, %r, %r)" % (self.rule, self.path, self.line)


def validate(rules):
    """Human-readable problems with the rules themselves."""
    problems = []
    for index, raw in enumerate(rules or []):
        rule = raw or {}
        name = rule.get("name") or "rule %d" % (index + 1)
        if not rule.get("rule_source"):
            problems.append(
                "%s has no rule_source. Name the written rule it enforces, or "
                "delete it." % name)
        if not rule.get("files"):
            problems.append("%s has no files glob." % name)
        has_forbid = bool(rule.get("forbid"))
        has_require = bool(rule.get("require"))
        if has_forbid and has_require:
            problems.append("%s sets both forbid and require. Pick one." % name)
        elif not has_forbid and not has_require:
            problems.append("%s sets neither forbid nor require." % name)
        for key in ("forbid", "require", "allow"):
            pattern = rule.get(key)
            if not pattern:
                continue
            try:
                re.compile(pattern)
            except re.error as error:
                problems.append("%s has an invalid regex in %s: %s" % (name, key, error))
    return problems


def _files_under(root):
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in names:
            full = os.path.join(base, name)
            yield full, os.path.relpath(full, root).replace(os.sep, "/")


def _lines(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read().splitlines()
    except OSError:
        return []


def run(root, rules):
    """Every finding under `root`. Rules with problems are skipped."""
    usable = [r for r in (rules or []) if not validate([r])]
    if not usable:
        return []

    findings = []
    for full, relative in _files_under(root):
        for rule in usable:
            if not globs.matches(relative, rule.get("files")):
                continue
            findings.extend(_check(full, relative, rule))
    findings.sort(key=lambda f: (f.path, f.line or 0, f.rule))
    return findings


def _check(full, relative, rule):
    name = rule.get("name") or "unnamed"
    message = rule.get("message") or ""
    source = rule.get("rule_source") or ""
    comments = tuple(rule.get("skip_line_comments") or ())
    lines = _lines(full)

    if rule.get("require"):
        pattern = re.compile(rule["require"], re.MULTILINE)
        if not any(pattern.search(line) for line in lines):
            return [Finding(name, relative, None, "", message, source)]
        return []

    forbid = re.compile(rule["forbid"])
    allow = re.compile(rule["allow"]) if rule.get("allow") else None
    out = []
    for number, line in enumerate(lines, 1):
        if comments and line.strip().startswith(comments):
            continue
        if not forbid.search(line):
            continue
        if allow and allow.search(line):
            continue
        out.append(Finding(name, relative, number, line.strip()[:100], message, source))
    return out


def report(findings, problems):
    """The triage list, as text."""
    out = []
    if problems:
        out.append("Problems with the rules themselves:")
        out.extend("  %s" % p for p in problems)
        out.append("")
    if not findings:
        out.append("No findings.")
        return "\n".join(out)

    out.append("%d finding%s. These are for triage, not a verdict: read each "
               "line before changing it." % (len(findings), "" if len(findings) == 1 else "s"))
    out.append("")
    for finding in findings:
        where = "%s:%d" % (finding.path, finding.line) if finding.line else finding.path
        out.append("  %s  [%s]" % (where, finding.rule))
        if finding.text:
            out.append("      %s" % finding.text)
        out.append("      %s  (%s)" % (finding.message, finding.rule_source))
    return "\n".join(out)
