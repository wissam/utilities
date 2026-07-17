# Raw Scripts

This directory is the tracked intake queue for scripts first created under
`/tmp` during agent work.

Scripts here may be one-off, narrowly scoped, hardcoded to Wissam's current
environment, or insufficiently tested. They are preserved because later review
may reveal reusable utilities, Velskills, runbook steps, or agent-editor/Neovim
features.

## Intake Rules

- Use a dated, descriptive filename.
- Record origin, purpose, assumptions, and limitations in the script header.
- Preserve useful one-time scripts rather than deleting them with `/tmp`.
- Never store credentials, tokens, private payloads, or secret-bearing output.
- Prefer a sanitized skeleton when the executed script contained sensitive
  values.
- Put scripts directly into a product repo instead when ownership is already
  clear.

## Trust Boundary

Files in this directory are **not production-ready by default**. Do not install
or automate them merely because they are tracked. Promotion requires review,
generalization where useful, tests appropriate to risk, documentation, and a
move into `scripts/` or the owning repository.

Possible review outcomes:

- promote unchanged after verification
- generalize and add tests
- merge with an existing helper
- extract a reusable snippet or Velskill
- preserve as historical evidence
- delete after an explicit review concludes it has no durable value

