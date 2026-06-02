# Lab Worktrees

`lab-worktrees/` is a local working area used by the agentic tool loop and by
the OpenTerminal-controlled lab environment.

The worktrees under this directory are external repositories or local working
copies used for controlled tests, code inspection, compile checks, and
report-only code-product generation. They are not part of this repository's
source package.

Only this descriptor is intended to be committed from `lab-worktrees/`.
The actual worktree contents, generated artifacts, caches, virtual
environments, outputs, renders, and temporary files remain local.
