# kojiPDFviewer Constitution

## Core Principles

### I. Preserve PDF reading behavior
Existing mail-bundle and general-document modes, bookmark navigation, search results, printing, and page-range export MUST remain usable unless a specification explicitly changes them. Changes to parser assumptions MUST include representative input cases and expected page ranges.

### II. Specify behavior before implementation
For a new feature or substantial behavior change, create `specs/NNN-short-name/spec.md`, then `plan.md` and `tasks.md` before changing application code. State user scenarios, observable acceptance criteria, affected files, and compatibility risks. Small isolated fixes MAY use a short spec in the same directory.

### III. Protect user documents and local state
The source PDF MUST NOT be modified by viewing, indexing, searching, or printing. Index databases are derived data beside the PDF. Changes to cache invalidation, read state, recent files, favorites, or page export MUST describe data and overwrite behavior before implementation. Test PDFs containing private mail MUST remain outside Git.

### IV. Verify the relevant behavior
Run the smallest checks that exercise the changed path. Parser and database changes SHOULD use synthetic PDFs and temporary directories. GUI changes SHOULD be checked with a representative PDF on Windows. Installer changes SHOULD be checked in GitHub Actions and by installing the generated MSI. Record checks and any unverified behavior in the feature artifacts.

### V. Keep Japanese text intact
Source, Markdown, and configuration text MUST be read and written as UTF-8 unless a format requires another encoding. Existing Japanese labels and documentation MUST NOT be corrupted or silently rewritten by encoding conversion.

### VI. Keep the reader document descriptive
`docs/日本語仕様書.md` explains current user-visible behavior for readers. It is not a source of new requirements or implementation tasks. A behavior change MUST first be specified and implemented through the feature artifacts; after verification, update the reader document to reflect the observed result.

## Project Constraints

- Target: Windows desktop, Python 3.12, PySide6, PyMuPDF, SQLite FTS5, optional Outlook desktop COM integration.
- Distribution: A push to `master` builds a Nuitka standalone app and packages it with WiX. A separate manually dispatched release workflow takes a release name, reuses the successful MSI artifact from the same commit, checks it with VirusTotal, and creates a tagged Release only after a clean result.
- Never commit real mail PDFs, generated indexes, API keys, signing keys, or machine-local Spec Kit state.
- Preserve the current user's changes when editing source or release files.

## Development Workflow

1. Describe the proposed behavior in a feature spec. Clarify ambiguous input formats and failure cases.
2. Write a plan with code paths, data effects, and a relevant verification method.
3. Break the plan into tasks, then implement and verify each affected behavior.
4. Compare the result with the spec and record remaining gaps. Update `docs/日本語仕様書.md` only for verified user-visible changes.

The installed Codex skills support `$speckit-specify`, `$speckit-clarify`, `$speckit-plan`, `$speckit-tasks`, `$speckit-analyze`, `$speckit-implement`, and `$speckit-converge`.

## Governance

This constitution guides future project work. Amend it in a dedicated change and explain the practical effect. Versioning: MAJOR changes or removes a principle; MINOR adds a principle; PATCH clarifies wording.

**Version**: 1.0.0 | **Ratified**: 2026-09-23 | **Last Amended**: 2026-09-23
