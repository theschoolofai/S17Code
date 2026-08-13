---
name: python-bugfix
description: This skill should be used when a pytest run is returning non-zero and the agent has to fix it. Load it before editing anything, because it carries the one rule that separates a real fix from a green suite: change the code, never the test.
when_to_use: a test is failing and the fix is not obvious
keywords: [pytest, test, failing, traceback, bug]
---
Work from the failure, not from the file.

**Change the code, never the test.** If the test looks wrong, say so in your
answer and leave it failing. A green suite obtained by editing the suite tells
the next person nothing, and the guard will refuse you anyway.

**Read before you edit.** An edit to a file this run has not read is refused.

**Stop after four.** If the same command fails four times in a row without
converging, stop and report what you tried. Past that point the edits damage the
work more often than they fix it.
