---
name: house-style
description: Always on. The editing rules and refusals that apply to every task in this repository.
always: true
---
Read before you edit. Name one place, not three: an anchor that matches more
than once will be refused, and the fix is more surrounding context, not
`replace_all`.

Do not edit tests, `conftest.py`, packaging or CI configuration. Those are the
things that judge your work, and the guard will refuse you anyway.

When you have finished, say plainly what you changed and what you verified. If
something is still failing, say that instead of describing what you intended.
