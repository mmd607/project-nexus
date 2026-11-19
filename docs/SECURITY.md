# Security & privacy model

Project Nexus reads folders you choose and shows what it finds on a local web page. This document lists what it does and does not do, and how that is enforced. Tests referenced as `tests/...` exercise the behaviour.

## Trust boundaries

```
your projects (read-only)  →  scanner  →  SQLite in Nexus' data dir  →  local HTTP API (127.0.0.1)  →  browser UI
                                                                    ↘ optional, opt-in →  local model server
```

## Filesystem

| Guarantee | How | Test |
|---|---|---|
| Nothing inside a workspace is written, created, renamed or executed. | The scanner only uses `scandir`/`lstat`/`open(rb)` on manifests & README; no project script is ever run. Git is the only subprocess, with fixed arguments. | `test_scanner.py` (counts unchanged after scans), code review |
| Only the folders you registered (and their children) are read. | Every listed directory must `realpath` inside the workspace root (`fsutil.is_within`). | `test_links_are_never_followed` |
| Symlinks, Windows junctions and other reparse points are never followed. | `fsutil.is_reparse_or_link` checks `is_symlink()` and `FILE_ATTRIBUTE_REPARSE_POINT`. Circular links cannot loop; links pointing outside are ignored. | same |
| Unreadable folders don't abort a scan. | Permission errors are collected into the scan run's issue list. | `test_scan_completes_without_crash` |
| Bounded work. | Depth, project-count, per-project file-count, manifest/README byte caps and Git timeouts are all settings with validated ranges. | `test_limits_are_respected`, `test_settings_db.py` |
| Secrets are never read. | Files matching the sensitive patterns (`.env*`, keys, tokens, credentials, `.ssh/`…) are only ever *listed* (name, size, mtime) and flagged; they are never opened and never sent to a model. | `test_sensitive_files_flagged_never_read`, `test_payload_excludes_secrets_and_caps` |

## Git

Only `git` itself is executed: `rev-parse`, `status --porcelain=v2`, `log`, `rev-list`, always with `--no-optional-locks`, a timeout, `stdin=DEVNULL`, and an environment that disables hooks (`core.hooksPath=/dev/null`), fsmonitor, terminal prompts and askpass helpers. Repository configuration in the scanned repo cannot make Nexus run anything else.

## Local HTTP API

| Threat | Mitigation | Test |
|---|---|---|
| Other machines reaching the UI | Binds to `127.0.0.1` by default; any other host requires `--host` **and** `--allow-remote`, and the UI shows a warning. | manual |
| DNS rebinding (a web page resolving `evil.example` → 127.0.0.1) | The `Host` header must be one of `127.0.0.1:<port>`, `localhost:<port>`, `[::1]:<port>`; otherwise `421`. | `test_dns_rebinding_host_check` |
| Cross-site requests from a malicious page in your browser | A per-launch random token is embedded only in the served HTML and required (`X-Nexus-Token`) for every `POST/PATCH/DELETE`; other origins cannot read the HTML, so they cannot obtain it. `Origin` (if present) must match, `Sec-Fetch-Site` must be `same-origin`/`none`, no CORS headers are ever emitted, `OPTIONS` pre-flights are refused. | `test_mutations_require_token`, `test_cross_origin_requests_are_rejected` |
| XSS / injected content from project names, READMEs, file names | The frontend never uses `innerHTML` with data — everything goes through `textContent`/`setAttribute`. The page ships a strict CSP (`default-src 'self'`, no inline scripts/styles, `frame-ancestors 'none'`). | `test_index_has_csp_and_token_not_exposed_by_api` |
| Path traversal | Static files are served only from the bundled `static/` directory after `realpath` containment; dot-files are refused. API routes identify projects by opaque 16-hex ids, never by path. | `test_static_traversal_blocked`, `test_ids_are_validated` |
| Registering dangerous roots | Paths are resolved and must exist; drive roots are refused unless explicitly confirmed; overlapping workspaces are refused. | `test_workspace_validation`, `test_scan_progress_cancel_and_runs` |
| Oversized / malformed bodies | 1 MB body limit, JSON-only, unknown settings keys and out-of-range values rejected. | `test_settings_validation` |
| "Open folder" | Only opens the directory of a *registered project id* in the OS file manager; never an arbitrary path. | `test_project_open_and_rescan_only_by_id` |

## Optional local AI

- Off by default; every request additionally needs a per-request `consent: true` flag from the UI dialog.
- Endpoint must be local unless `allow_non_local_endpoint` is explicitly enabled.
- Only the selected metadata fields are sent; the exact payload is previewed. Secrets and file contents are excluded (see AI_SETUP.md).
- Model output is schema-validated and inert: it can only become a *pending suggestion* that you accept or reject. It cannot alter settings, paths or files. Prompt-injection text in project files is passed as data with an explicit "untrusted" system prompt.
- Tests: `test_ai.py` (disabled-by-default, consent, payload filtering, schema validation, timeout/garbage handling, injected instructions inert, non-local endpoint refused).

## Data at rest

- Everything Nexus stores lives in its data directory: `nexus.db` (SQLite), `settings.json`, `logs/`, `session.json` (current token + port, mode 600 semantics not enforced on Windows).
- Stored per file: relative path, extension, size, mtime, kind, sensitive flag. Never contents.
- Logs do not contain request paths unless `privacy.log_full_paths` is enabled. JSON export anonymises workspace roots by default.

## Reporting

If you find a way to make Nexus read outside a workspace, write into one, or accept a cross-origin mutation, please open an issue with a reproduction.
