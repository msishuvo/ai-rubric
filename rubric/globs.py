"""Glob matching for path patterns.

Written by hand rather than reached for: `fnmatch` is not path-aware, so
its `*` happily crosses a directory separator, and `pathlib.PurePath.match`
does not treat a leading `**/` as optional. Both would silently widen or
narrow what counts as "the work", which is a rule nobody would notice
breaking.
"""

import re

_CACHE = {}


def _translate(pattern, anchored=False):
    if anchored or pattern.startswith("**"):
        out = [""]
    else:
        out = ["(?:.*/)?"]
    index = 0
    length = len(pattern)
    while index < length:
        char = pattern[index]
        if pattern.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif char == "*":
            out.append("[^/]*")
            index += 1
        elif char == "?":
            out.append("[^/]")
            index += 1
        else:
            out.append(re.escape(char))
            index += 1
    return re.compile("^" + "".join(out) + "$")


def _compiled(pattern, anchored=False):
    key = (pattern, anchored)
    if key not in _CACHE:
        try:
            _CACHE[key] = _translate(pattern, anchored=anchored)
        except re.error:
            _CACHE[key] = None
    return _CACHE[key]


def matches(path, pattern, anchored=False):
    """True when `path` matches `pattern`.

    By default the leading `(?:.*/)?` means a relative pattern also matches
    an absolute path by its suffix, which is what makes `src/**/*.ts` work
    against the absolute file_path an edit tool reports. Pass
    `anchored=True` to require the pattern to match from the very start of
    `path` instead, which is what a root-relative path (as `invariants.py`
    computes with `os.path.relpath`) needs: unanchored, `src/**/*.ts` would
    also match `vendor/src/a.ts` by suffix, which is wrong for a rule scoped
    to one directory.

    A non-string `pattern` (a list, most likely, from a config mistake such
    as `"files": ["src/**/*.ts"]`) is treated as no match rather than
    raised, since a pattern that came from config is not guaranteed to be
    the right shape.
    """
    if not path or not pattern or not isinstance(pattern, str):
        return False
    compiled = _compiled(pattern, anchored=anchored)
    if compiled is None:
        return False
    return bool(compiled.match(str(path).replace("\\", "/")))


def matches_any(path, patterns, anchored=False):
    return any(matches(path, p, anchored=anchored) for p in (patterns or []))
