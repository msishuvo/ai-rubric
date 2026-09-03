"""Glob matching for path patterns.

Written by hand rather than reached for: `fnmatch` is not path-aware, so
its `*` happily crosses a directory separator, and `pathlib.PurePath.match`
does not treat a leading `**/` as optional. Both would silently widen or
narrow what counts as "the work", which is a rule nobody would notice
breaking.
"""

import re

_CACHE = {}


def _translate(pattern):
    out = ["(?:.*/)?"] if not pattern.startswith("**") else [""]
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


def _compiled(pattern):
    if pattern not in _CACHE:
        try:
            _CACHE[pattern] = _translate(pattern)
        except re.error:
            _CACHE[pattern] = None
    return _CACHE[pattern]


def matches(path, pattern):
    """True when `path` matches `pattern`.

    The leading `(?:.*/)?` means a relative pattern also matches an
    absolute path by its suffix, which is what makes `src/**/*.ts` work
    against the absolute file_path an edit tool reports.
    """
    if not path or not pattern:
        return False
    compiled = _compiled(pattern)
    if compiled is None:
        return False
    return bool(compiled.match(str(path).replace("\\", "/")))


def matches_any(path, patterns):
    return any(matches(path, p) for p in (patterns or []))
