# Development workflow

- Use the Codex Spec Kit skills installed in `.agents/skills` for feature work: specify → clarify when needed → plan → tasks → analyze when useful → implement → converge.
- Keep feature artifacts in `specs/NNN-short-name/`. Consult `.specify/memory/constitution.md` before planning.
- `docs/日本語仕様書.md` is a reader-facing description of verified current behavior. Do not treat it as a request to implement features. Update it after a behavior change is verified.
- Preserve UTF-8 Japanese text. Keep real PDF and SQLite data out of Git.
- On Windows hosts where `pwsh` is unavailable or `.ps1` execution is restricted, run Spec Kit scripts with `powershell.exe -NoProfile -ExecutionPolicy Bypass -File <script>`. Do not change the machine-wide execution policy.
- When changing the installer, check the Nuitka build, WiX package, VirusTotal gate, and tag/version relationship.
