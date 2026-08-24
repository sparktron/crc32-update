# AGENTS.md

## Long-running commands

Do not start commands in Codex when their expected runtime can exceed the
command-execution time limit. Instead, provide the user with the exact,
resumable command to run manually and explain where it records progress.

Only run a long command here when the user explicitly asks Codex to run it
despite that limit.
