"""Build the text injected on every prompt.

The core block is the only string in the kit that is hardcoded rather than
configured, because it is the only thing that is genuinely universal. It is
kept deliberately short: a hook that costs a paragraph a turn becomes
wallpaper, which is exactly how the prose it replaces stopped working.

The cost table is NOT injected here. It belongs to the gate, which quotes
the one relevant row at the moment a check was skipped.
"""

import re

CORE_TEMPLATE = (
    "Before any factual claim this turn:\n"
    "  1. Checked, or recalled? If recalled and checkable in under two minutes, check it.\n"
    "  2. What did I observe, versus what am I inferring?\n"
    "  3. If I am wrong here, could {who} tell?{cannot} If no, slow down.\n"
    'Anything unchecked ships with the words "I have not checked this".'
)


def core_block(config):
    who = (config or {}).get("who") or "the user"
    domains = [d for d in ((config or {}).get("cannot_check") or []) if d]
    cannot = " They cannot check %s." % ", ".join(domains) if domains else ""
    return CORE_TEMPLATE.format(who=who, cannot=cannot)


def situation_blocks(config, prompt):
    """The `say` of every configured situation whose `when` matches `prompt`."""
    if not isinstance(prompt, str):
        prompt = "" if prompt is None else str(prompt)
    out = []
    for block in ((config or {}).get("situations") or []):
        say = (block or {}).get("say")
        if not say:
            continue
        for pattern in (block.get("when") or []):
            try:
                if re.search(pattern, prompt, re.IGNORECASE):
                    out.append(say)
                    break
            except (re.error, TypeError):
                continue
    return out


def build(config, prompt):
    return "\n\n".join([core_block(config)] + situation_blocks(config, prompt))
