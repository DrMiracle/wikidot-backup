# AGENTS.md

## Project

**SCP Wikidot Backup** is a Python CLI tool for creating portable, migration-friendly backups of Wikidot-based SCP sites.

Primary target during development:

- Site unix name: `scp-ukrainian`
- Domain: `scp-ukrainian.wikidot.com`
- Wikidot site ID: `1398197`

The archive must remain understandable and usable without this program and without Wikidot.

The project prioritizes:

1. source fidelity;
2. recoverability;
3. explicit, portable archive formats;
4. safe retry/resume behavior;
5. correctness over clever optimization;
6. clear separation between Wikidot integration objects and persistent archive models.

Do not silently normalize or discard remote data unless there is a documented reason.

---

## Environment

Development environment:

- Windows 11
- Python `3.12 <= version < 3.15`
- Current development interpreter is Python 3.14
- PyCharm
- PowerShell
- editable install

Typical setup:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Typical commands:

```powershell
pytest -v
wikidot-backup --help
wikidot-backup backup --help
wikidot-backup backup scp-ukrainian --limit 20
wikidot-backup backup scp-ukrainian --revisions --limit 20
wikidot-backup info ./backup
```

Do not assume Linux-only shell commands or tools.

---

## Important dependencies

The project currently uses approximately:

```text
wikidot==4.5.0
typer>=0.16,<1
rich>=15
pydantic>=2.11,<3
httpx>=0.28,<1
tenacity>=9,<10
beautifulsoup4>=4.13,<5
```

`wikidot.py` is an external integration dependency, not the archive data model.

Do not leak `wikidot.py` objects into persistent archive schemas.

---

## Current architecture

The intended data flow is:

```text
Wikidot / wikidot.py / AMC
        ↓
wikidot/ integration layer
        ↓
Wikidot*Data dataclasses
        ↓
collectors/
        ↓
Pydantic persistent archive models
        ↓
storage/
        ↓
filesystem archive
```

The important distinction is:

- `Wikidot*Data` classes are transient normalized integration models;
- Pydantic models under `models/` define the persistent archive schema.

Do not merge those layers merely because some fields currently match.

Example:

```text
wikidot.py User
    ↓
WikidotUserData
    ↓
user_to_ref()
    ↓
UserRef
```

This separation is intentional.

---

## Current project structure

Expected structure is roughly:

```text
src/
└── wikidot_backup/
    ├── cli.py
    ├── config.py
    │
    ├── wikidot/
    │   ├── amc.py
    │   ├── client.py
    │   ├── errors.py
    │   ├── models.py
    │   ├── retry.py
    │   └── source.py
    │
    ├── models/
    │   ├── common.py
    │   ├── file.py
    │   ├── manifest.py
    │   ├── page.py
    │   └── revision.py
    │
    ├── collectors/
    │   ├── common.py
    │   ├── files.py
    │   ├── pages.py
    │   └── revisions.py
    │
    ├── services/
    │   ├── backup.py
    │   ├── backup_types.py
    │   └── estimate.py
    │
    ├── storage/
    │   ├── archive.py
    │   ├── atomic.py
    │   ├── indexes.py
    │   ├── inspection.py
    │   ├── manifest.py
    │   └── state.py
    │
    ├── ui/
    │   └── progress.py
    │
    └── util/
        ├── formatting.py
        └── hashing.py
```

Temporary diagnostic scripts may exist under `src/temp/`, but they are not production architecture.

---

## Canonical archive layout

The canonical backup is an **open directory**, not a ZIP file.

Current layout:

```text
backup/
├── archive.json
│
├── pages/
│   └── <page_id>/
│       ├── page.json
│       ├── source.txt
│       ├── files.json
│       └── revisions/
│           ├── revisions.jsonl
│           └── sources/
│               └── <revision_id>.txt
│
├── blobs/
│   └── sha256/
│       └── <sha256>
│
├── indexes/
│   ├── pages.json
│   └── pages.csv
│
└── .state/
    ├── resume.jsonl
    ├── errors.jsonl
    └── transactions/                # temporary interrupted-write recovery
```

Keep numeric Wikidot page IDs as canonical page directory names.

Do **not** switch canonical storage to page fullname or title.

Reasons:

- numeric IDs are stable;
- IDs are unique;
- IDs are safe on Windows;
- page fullname/title may change;
- titles are not guaranteed unique;
- names can contain filesystem-hostile characters.

Human-readable views should be generated later by an export command, not used as canonical storage.

---

## Archive manifest

`archive.json` is root archive identity metadata.

It should contain stable metadata such as:

- archive schema version;
- archive format identifier;
- Wikidot site ID;
- site unix name;
- title;
- domain;
- URL;
- archive creation timestamp;
- last successful run timestamp;
- last successful full-backup timestamp;
- components requested by the last successful run.

Do not store dynamic page/revision/file counts in `archive.json`.

Those are derived by `wikidot-backup info` from actual files on disk.

The manifest should prevent accidentally writing a different Wikidot site into an existing archive directory.

---

## Page discovery

Wikidot `ListPagesModule` effectively returns at most 250 pages per request.

Use:

```text
limit = 250
offset = 0, 250, 500, ...
order = fullname
```

Do not rely on `perPage=10000`, page-number parameters, or a single request.

The target site has already been observed at roughly 1944–1946 archived/current pages depending on the date and archive state.

Discovery must be deterministic.

---

## Page source fidelity

This is one of the most important project invariants.

Current source and historical revision source come from different Wikidot modules:

```text
current:
viewsource/ViewSourceModule
    parameter: page_id

historical revision:
history/PageSourceModule
    parameter: revision_id
```

Wikidot returns HTML-wrapped source, not raw plain text.

The source decoder must handle:

- `<br>` as source line breaks;
- literal CR/LF formatting from the AMC HTML response as transport formatting;
- HTML entities;
- current-source `<a>` tags inserted inside otherwise plain source;
- current endpoint transport indentation;
- `&nbsp;` normalization consistent across current and revision sources.

The project currently uses endpoint-specific wrappers around common source decoding.

Critical invariant:

```text
current_source == latest_revision_source
```

This was verified on `scp-009-ua-arc`.

Known real example:

- page ID: `802215837`
- latest revision number: `14`
- total revision versions: `15`
- revisions are numbered from `0`

Do not casually add `.strip()`, `.lstrip()`, blanket whitespace collapsing, or `"\n\n" -> "\n"` normalization. Such changes can destroy valid Wikidot source.

---

## Revision numbering

`wikidot.py` exposes a field named `page.revisions_count`, but on real data it behaved as the **latest revision number**, not the number of revision versions.

Example:

```text
page.revisions_count = 14
len(page.revisions) = 15
revision numbers = 0..14
```

Our integration/archive naming should use:

```text
latest_revision_no
```

rather than `revision_count`.

When an approximate revision count is needed without fetching the revision list:

```text
revision_count = latest_revision_no + 1
```

assuming `latest_revision_no` is present.

---

## Current page title

Some Wikidot pages return `title=None`.

This is valid data.

Both integration and persistent models should allow:

```text
title: str | None
```

Do not substitute fullname or `""`.

Preserve `null`.

---

## Users

Transient integration user:

```text
@dataclass(slots=True)
class WikidotUserData:
    id: int | None
    name: str
    unix_name: str | None
```

Persistent archive user:

```text
class UserRef(BaseModel):
    ...
```

System users may have `id=None`.

Use explicit conversion such as:

```text
user_to_ref(...)
```

Do not use implicit `asdict()`-style schema coupling between integration and archive models.

---

## Page metadata

Persistent `PageRecord` includes or is expected to include:

- `schema_version`;
- `page_id`;
- `fullname`;
- `name`;
- `category`;
- nullable `title`;
- `parent_fullname`;
- visible and hidden tags;
- children count;
- comments count;
- size;
- rating;
- vote count;
- rating percent where present;
- `latest_revision_no`;
- created/updated/commented users and timestamps;
- discussion thread ID;
- metas;
- source reference.

Current raw source is stored separately in `source.txt`.

---

## Source references

Text source uses `SourceRef`, with fields conceptually like:

```text
format
encoding
path
sha256
characters
```

The source path should be explicit.

For the current page:

```text
source.txt
```

For historical revisions:

```text
revisions/sources/<revision_id>.txt
```

---

## Revisions

Revision archive layout:

```text
pages/<page_id>/
└── revisions/
    ├── revisions.jsonl
    └── sources/
        └── <revision_id>.txt
```

Each persistent revision record contains conceptually:

```text
schema_version
page_id
revision_id
revision_no
created_by
created_at
comment
source
```

Revision source and metadata should be complete before the page's `REVISIONS` component is marked complete.

A failed revision crawl may leave partial source files. That is acceptable because the component remains incomplete and will be retried.

---

## Attachments

Wikidot page attachments are a separate component from external resources.

Current attachment pipeline:

```text
page.files metadata
    ↓
WikidotFileData
    ↓
download original bytes
    ↓
SHA-256
    ↓
content-addressed blob
    ↓
files.json
```

Persistent archive layout:

```text
pages/<page_id>/files.json
blobs/sha256/<sha256>
```

The blob filename intentionally has no original extension.

This is **not conversion**.

JPEG/PNG/etc. files are already byte sequences. The archive stores the exact downloaded bytes unchanged.

Original filename, URL, MIME metadata, reported size, and blob reference are stored in `files.json`.

A future export command can simply copy the blob back under the original filename.

---

## Attachment size semantics

Wikidot-reported file size is not fully reliable.

Real example:

```text
wikidot_size         = 31950
HTTP Content-Length = 32716
downloaded bytes     = 32716
```

Therefore preserve both concepts:

```text
wikidot_size
    = metadata reported by Wikidot

content.size
    = actual number of bytes archived
```

Do not overwrite one with the other.

---

## Blob storage

Binary attachments are stored content-addressed:

```text
blobs/sha256/<sha256>
```

Benefits:

- integrity identity;
- duplicate content stored once;
- filename collisions avoided;
- original names remain metadata;
- easy later verification.

Blob writes should be atomic.

Do not add per-file resume state unless there is a demonstrated need.

Current decision:

- page/component-level resume: yes;
- content-addressed blob deduplication: yes;
- atomic blob writes: yes;
- per-file network resume journal: no.

If one file fails in the middle of a page, a later retry may download earlier files again. This is acceptable and also allows changed remote bytes to be detected by a new SHA-256.

---

## `files.json`

`files.json` represents a complete attachment metadata collection for a page.

Even a page with zero attachments should get:

```json
{
  "schema_version": 1,
  "page_id": 123,
  "files": []
}
```

This distinguishes:

```text
files.json exists, files=[]
    = attachment component was checked and is empty

files.json missing
    = attachment component was not completed
```

Prefer writing `files.json` atomically.

---

## Network errors and retries

Transient Wikidot failures have been observed in practice:

```text
500 Internal Server Error
RemoteProtocolError:
Server disconnected without sending a response.
```

The same resource may work on a later run.

Retry transient failures:

- `httpx.TransportError`;
- HTTP 408;
- HTTP 429;
- HTTP 5xx.

Do not retry ordinary permanent 4xx errors by default.

Current Tenacity behavior uses bounded exponential jitter.

Avoid nested retry decorators around calls that already go through a retrying AMC request layer.

---

## Resume state

Page-scoped component completion is stored in:

```text
.state/resume.jsonl
```

Components currently include:

```text
PAGE
FILES
REVISIONS
```

Example records:

```text
{"fullname":"scp-001","page_id":123,"component":"page","completed_at":"..."}
{"fullname":"scp-001","page_id":123,"component":"files","completed_at":"..."}
{"fullname":"scp-001","page_id":123,"component":"revisions","completed_at":"..."}
```

`load_page_states()` merges records by fullname.

A page ID conflict for the same fullname should raise an error.

Legacy records without a `component` may be interpreted as `PAGE`.

Do not silently ignore malformed resume state.

`resume.jsonl` is temporary operational state, not canonical archive data.

Recoverable page/revision writes additionally use `.state/transactions/`.
Canonical paths and schema version 1 are unchanged. A pending transaction
retains prior bytes until publication completes; backup rolls it back before
continuing, while read-only inspection rejects pending transactions.
Use only one writer per archive.

After a successful **full, unlimited** backup, resume state is cleared.

A successful limited run should update the archive manifest but must leave resume state intact.

Here, `limited_run` means `limit is not None`, even if all pending pages fit
within that limit. Only a successful invocation without `--limit` finalizes
the crawl.

Correct logic is conceptually:

```text
if failed == 0:
    manifest_store.record_success(
        components=[...],
        full_backup=not limited_run,
    )

    if not limited_run:
        state.clear_resume_state()
        resume_state_cleared = True
```

---

## Error state

Errors are recorded in:

```text
.state/errors.jsonl
```

A page is counted as failed if one of the components required by that invocation fails.

Progress semantics:

```text
20/20 • done • 19 saved • 1 failed
```

means 20 pages finished processing, 19 succeeded, 1 failed.

Advance progress only when a page succeeds or fails.

---

## Backup options

Current intended options:

```text
current page data
    always included

files
    included by default
    disable with --no-files

revisions
    disabled by default
    enable with --revisions
```

Examples:

```powershell
wikidot-backup backup scp-ukrainian
wikidot-backup backup scp-ukrainian --no-files
wikidot-backup backup scp-ukrainian --revisions
wikidot-backup backup scp-ukrainian --revisions --no-files
wikidot-backup backup scp-ukrainian --limit 20
```

---

## `info` command

Implemented command:

```powershell
wikidot-backup info ./backup
```

It inspects the actual archive filesystem and reports:

- archived page count;
- current source count;
- pages with `files.json`;
- attachment record count;
- unique blobs;
- pages with revisions;
- revision record count;
- page/blob/index/state disk usage;
- total archive size;
- archive creation time;
- last successful run;
- last full backup;
- incomplete resume state;
- pages represented in resume state;
- error record count.

The archive filesystem is the source of truth for these statistics.

Do not use resume state as the authoritative count of archived content.

---

## Human-readable indexes

Canonical page directories stay numeric.

Navigation is provided by:

```text
indexes/pages.json
indexes/pages.csv
```

Indexes are derived and rebuildable.

They should not become the source of truth.

---

## Human-readable export

Do **not** duplicate all files into human-readable directories inside the canonical archive.

A future export command should materialize a readable view, e.g.:

```text
export/
└── pages/
    └── scp-009-ua-arc/
        ├── source.txt
        ├── page.json
        └── files/
            └── Gold_credit_card009ua.jpg
```

Use page `fullname`, not title, as the default exported directory name.

Export should reconstruct original attachment filenames by copying blob bytes. No image conversion is required.

This feature is planned after forums/external-asset work.

---

## Backup packing/compression

Do not make a compressed archive the canonical working format.

Canonical format remains an open directory.

A later optional command may create a ZIP or other packed cold-storage snapshot:

```text
wikidot-backup pack ./backup
```

Do not implement automatic packing as part of the core write path unless explicitly requested.

---

## Backup size estimation

A separate command is implemented:

```powershell
wikidot-backup estimate scp-ukrainian
wikidot-backup estimate scp-ukrainian --revisions
wikidot-backup estimate scp-ukrainian --no-files
```

The estimate should be explicit and separate from `backup`.

Implemented semantics:

### Current source

Measure UTF-8 byte length:

```text
source_bytes = len(page.source.encode(TEXT_ENCODING))
```

### Attachments

Use `file.size` reported by Wikidot as an estimate.

Track unknown sizes separately.

Clearly state that reported sizes may differ from downloaded sizes.

### Revisions

Use the normalized field:

```text
page.latest_revision_no
```

not `page.revisions_count` in service code.

Approximate revision version count as:

```text
revision_count = page.latest_revision_no + 1
```

Historical source size is not known until fetched.

When `latest_revision_no` is absent, report the page in an unknown-revision-count
counter and exclude its historical size from the estimate.

For a simple v1 heuristic:

```text
estimated_revision_source_bytes += (
    current_source_bytes * revision_count
)
```

Mark this output clearly as approximate.

The estimate should process pages incrementally and only accumulate counters; it should not retain whole-site data in RAM.

---

## `info` vs `estimate`

Keep their responsibilities distinct:

```text
estimate
    = approximate future backup size from remote metadata/source

backup
    = perform the backup

info
    = statistics for data physically present in an archive
```

---

## External assets

Wikidot attachments are **not** the same as arbitrary external resources referenced by a page.

Current `FILES` component handles only Wikidot page attachments.

Examples:

```text
[[image https://example.com/foo.jpg]]
<img src="https://example.com/foo.jpg">
```

These are not returned by `page.files`.

External assets are a planned separate component.

Do not blindly crawl normal hyperlinks.

Initial future scope should focus on directly embedded media resources.

---

## Forums and discussions

This is the next major feature area after size estimation.

There are two related sources:

```text
Site forum
└── groups/categories
    └── threads
        └── posts
            └── post revisions

Page discussion
└── thread
    └── posts
        └── post revisions
```

A page discussion is forum-backed, so avoid writing two independent storage/parsing pipelines if the underlying Wikidot object structure is shared.

Proposed archive direction:

```text
forums/
├── groups.json
├── categories.json
└── threads/
    └── <thread_id>/
        ├── thread.json
        ├── posts.jsonl
        └── post-revisions.jsonl
```

Before implementing persistence, inspect the real `wikidot.py` object graph and pagination behavior.

Do not add a `FORUM` member to the current page-scoped `BackupComponent` merely for convenience.

---

## `wdotcrawl` reference

The old `wdotcrawl` project is a useful reference but not a replacement.

It focuses primarily on:

- pages;
- revision history;
- source;
- Mercurial-backed history.

Its code left files and forums/comments as TODO.

Useful ideas learned from it:

- historical source endpoint behavior;
- HTMLified revision source handling;
- request pacing/throttling;
- historical page-name/title investigation.

Do not copy its implementation directly unless licensing permits it.

---

## Coding style

Prefer explicit, boring code over clever abstractions.

Use:

- type annotations;
- `dataclass(slots=True)` for transient normalized integration data;
- Pydantic `BaseModel` for persistent archive schemas;
- docstrings for modules, classes, and meaningful helpers;
- comments for non-obvious **why**, not obvious line-by-line behavior;
- keyword-only arguments where they improve call clarity;
- explicit model conversion functions between layers.

Avoid:

- `asdict()`/`**dict` coupling between integration and archive schemas;
- broad exception swallowing;
- silent data normalization;
- unnecessary abstractions;
- speculative optimization;
- premature concurrency.

---

## Error handling

Fail loudly for:

- malformed persistent archive metadata;
- corrupted resume state;
- site identity mismatch;
- invalid source response structure;
- programming/schema errors.

Retry only transient network failures.

Do not silently turn unknown errors into successful archive state.

Mark a component complete only after all required data for that component has been safely persisted.

---

## Tests

Important areas:

### Source parser

- current endpoint transport wrapper removal;
- revision HTML entity decoding;
- blank-line preservation;
- trailing-newline preservation;
- real leading indentation preservation;
- `&nbsp;` normalization;
- current/revision equivalent source canonicalization;
- missing `.page-source` failure.

### Retry

- retry transport errors;
- retry 408/429/5xx;
- do not retry normal 4xx;
- stop after configured attempts.

### Page models

- nullable title.

### Files

- original bytes preserved;
- actual content size distinct from Wikidot-reported size;
- empty attachment collection writes `files.json`;
- blob path based on SHA-256;
- identical content reuses one canonical blob.

### Manifest

- manifest creation;
- reuse keeps original `created_at`;
- different site rejected;
- limited run updates last successful run but not last full backup;
- full run sets last full backup;
- later limited run does not erase previous full-backup timestamp.

### Inspection

- count pages/sources/files/revisions/blobs;
- count unique resume pages rather than raw component lines;
- missing optional data reports zero;
- invalid metadata raises rather than silently skipping.

Do not over-test Rich table spacing.

---

## Known real-world observations

### Page title can be null

Preserve it.

### Current source and revision source use different HTML wrappers

Parser was adjusted until:

```text
current source == latest revision source
```

### Wikidot attachment metadata size can be stale

Preserve reported size and actual downloaded byte size separately.

### Wikidot can transiently fail

Observed:

```text
500 Internal Server Error
RemoteProtocolError
```

The same resource may later work.

Do not immediately classify transient failures as permanently unavailable content.

---

## Archive philosophy

The archive should remain useful if:

- this Python package no longer exists;
- `wikidot.py` no longer exists;
- Wikidot is unavailable;
- the site must be migrated to another engine.

Prefer:

- UTF-8 text;
- JSON;
- JSONL;
- CSV derived indexes;
- original binary bytes;
- SHA-256;
- explicit schema versions.

Avoid opaque databases as the only source of truth.

---

## Planned roadmap

```text
Core page discovery                 done
Current source + metadata           done
Revision history                    done
Wikidot attachments                 done
SHA-256 blobs                       done
Retry / component resume            done
Archive manifest                    done
Archive info command                done

Approximate size estimate           done
Forums + page discussions           next major feature
External embedded assets            later
Link/backlink index                 later
Human-readable export               later
Archive verification                later
Optional packed/cold-storage copy   later
```

Prefer small, testable milestones.

---

## README expectations

When new user-facing functionality is added, update README sections as appropriate:

- `Current features`;
- `Usage`;
- `Archive layout`;
- relevant archive-file explanation;
- `Project structure`.

README should explain what users need to know, not duplicate all internal architecture documentation from this file.

---

## Working with Codex

When making changes:

1. inspect existing code before proposing a replacement;
2. preserve existing names and architecture unless a change has a concrete benefit;
3. do not reintroduce already rejected ideas such as per-file resume state;
4. keep canonical archive compatibility in mind;
5. add or update tests for behavior changes;
6. avoid broad refactors while implementing one feature;
7. explain any schema or archive-layout change before making it;
8. treat current filesystem formats as persistent data contracts;
9. prefer backwards-compatible readers when a stored-state format changes;
10. do not remove old archive data merely because it is absent from a later Wikidot snapshot unless deletion semantics are explicitly designed.

When unsure whether a Wikidot field means what its name suggests, verify against real data before encoding that assumption into the archive schema.
