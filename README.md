# SCP Wikidot Backup

CLI tool for creating portable backups of Wikidot-based SCP sites.

The archive preserves Wikidot content in simple filesystem-based formats so
that it can be inspected independently of this program and later used for
disaster recovery or migration to another wiki engine.

## Current features

- complete page discovery across all Wikidot categories;
- current page metadata and raw Wikidot source;
- page attachments and attachment metadata;
- optional complete page revision history;
- public forum threads and page discussions, with optional rendered post revisions;
- revision authors, timestamps, comments, and historical source;
- content-addressed attachment storage with SHA-256 integrity hashes;
- resumable component-aware backup runs;
- retry/backoff for transient Wikidot failures;
- JSON and CSV page indexes for easier navigation;
- root archive metadata (`archive.json`) with site identity and backup timestamps;
- approximate backup size estimation from current source and remote metadata;
- archive inspection with page, revision, attachment, error, and disk usage statistics.

External resources and locally derived link data are not yet archived.
Forum content is rendered HTML; raw forum wiki source is unavailable through
the public endpoints used here.

## Requirements

- Python 3.12 through 3.14 (`>=3.12,<3.15`)
- Internet access to the target Wikidot site

## Installation

Create a virtual environment:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install the project in editable mode with development dependencies:

```bash
python -m pip install -e ".[dev]"
```

## Usage

Back up the current version of every page, including its Wikidot attachments:

```bash
wikidot-backup backup scp-ukrainian
```

Choose another output directory:

```bash
wikidot-backup backup scp-ukrainian --output ./backup
```

Include complete page revision history:

```bash
wikidot-backup backup scp-ukrainian --revisions
```

Revision history is disabled by default because retrieving every historical
source version requires substantially more requests and storage.

Skip attachment downloads:

```bash
wikidot-backup backup scp-ukrainian --no-files
```

Limit the number of pages processed, for example during testing:

```bash
wikidot-backup backup scp-ukrainian --limit 20
```

Any invocation using `--limit` retains resume state and does not update the
last full-backup timestamp, even if it processes all remaining pages. Run
without `--limit` to finalize the crawl. Failed page collections return exit
code 1; an interrupted backup returns 130.

Options can be combined:

```bash
wikidot-backup backup scp-ukrainian \
    --revisions \
    --limit 20 \
    --output ./backup
```
wikidot-backup backup scp-wiki --limit 20 --output ./temp-backup
Run the built-in help for the complete CLI reference:

```bash
wikidot-backup --help
wikidot-backup backup --help
```

### Backing up forums and discussions

Normal output shows progress for pages, forum category discovery, and threads.
Use `--verbose` (or `-v`) on `backup` or `backup-forums` to print individual
saved pages/threads and discovered categories. Coverage warnings and the final
failure summary remain visible without verbose mode.

```powershell
wikidot-backup backup scp-ukrainian --forums --limit 20
wikidot-backup backup scp-ukrainian --forums --revisions
```

Add `--forums` to include forums in a site backup. Pages are collected first,
then forum discovery follows public category listings and discussion thread IDs
in archived `page.json` files. Each thread is stored once. This does not discover inaccessible
threads or discussions absent from both the forum listing and archived pages.

With `--forums`, `--limit N` restricts pages and threads independently to N each;
category discovery still runs in full. `--revisions` includes both page history
and every publicly listed post version, including the initial
version of unedited posts. Both current and historical content are labelled
as HTML, never as original wiki markup. Embedded images are not downloaded.

Completed threads are skipped while resuming. Adding `--revisions` causes
threads without history to be fetched again. An unlimited run without failures
or coverage warnings clears forum state; subsequent runs fetch fresh content.

Reported counts are checked against retrieved records. Count discrepancies
are recorded as coverage warnings and return exit code **2**, with resume state
retained. Remote failures return **1**; interruption returns **130**. A limited
batch without problems returns **0**, but does not mean the whole forum is saved.
For example, the target site's discussion category reported 2017 threads while
all 101 listing pages exposed only 1953 during reconnaissance; its cause is
unknown. The archive records this gap rather than claiming complete coverage.

Combined backups update the manifest and clear both resume files only when
pages and forums succeed without coverage warnings. Limited runs retain both
resume files and do not set the full-backup timestamp.

For forum-only retries, the separate command remains available:

```powershell
wikidot-backup backup-forums scp-ukrainian --revisions
wikidot-backup backup-forums scp-ukrainian --refresh --limit 20
```

`--refresh` discards only forum completion state and fetches fresh snapshots.
Forum-only runs never set the full site-backup timestamp. `info` reports stored
forum threads, posts, revisions and disk usage.

### Estimating an archive's size

Estimate approximate size of the archive (can take a while, since we're doing full crawl through every page):

```bash
wikidot-backup estimate scp-ukrainian
```

Has options:

- `--revisions` - estimate historical source size from current source size and revision numbering;
- `--no-files` - exclude files.
- `--limit N` - inspect at most N pages (the result covers only those pages).

Unknown attachment sizes and unknown revision counts are reported separately
and excluded from the total. The estimate excludes metadata and filesystem
overhead and does not account for attachment deduplication.
Forum content is excluded from the estimate.

### Inspecting an archive

Show information about an existing backup:

```bash
wikidot-backup info ./backup
```

The command reports:

- archived pages and current page sources;
- pages with attachment metadata and total attachment records;
- unique stored attachment blobs;
- pages with revision history and total revision records;
- archive disk usage by data category;
- backup creation and completion timestamps;
- resumable/incomplete run state;
- recorded backup errors.

Archive content is inspected directly from the filesystem, so these counts
describe what is actually stored in the backup rather than the current state
of the Wikidot site.

## Archive layout

Pages are stored by their stable numeric Wikidot page ID. Human-readable
page names and titles are preserved in metadata and navigation indexes.

```text
backup/
├── archive.json
│
├── pages/
│   └── <page_id>/
│       ├── page.json
│       ├── source.txt
│       ├── files.json
│       └── revisions/                 # only with --revisions
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
├── forums/
│   ├── catalog.json               # latest discovery, with its run_id
│   ├── runs/<UTC-timestamp>-<unique-suffix>/
│   │   ├── catalog.json           # immutable discovery snapshot for this run
│   │   └── report.json            # results and warnings, written when run finishes
│   └── threads/<thread_id>/
│       ├── thread.json
│       ├── posts.jsonl
│       └── post-revisions.jsonl    # only with forum --revisions
│
└── .state/
    ├── resume.jsonl
    ├── errors.jsonl
    ├── forum-resume.jsonl
    ├── forum-errors.jsonl
    └── transactions/                # temporary interrupted-write recovery
```

### Forum records

A **thread** is one discussion topic, such as all comments on a page. A **post**
is one comment or reply within that thread. `thread.json` holds the topic's title,
category and page links; `posts.jsonl` holds the comments, their authors and reply
relationships. Both are needed to reconstruct the discussion. Post revisions
are earlier versions of individual comments, not additional discussions.

These are canonical archive records, not the final browsing interface. An export
can follow `page.json.discussion_thread_id` to the matching forum directory and
render its posts as nested comments. The intended readable layout is:

```text
export/
├── pages/
│   └── scp-009-ua-arc/
│       ├── page.json
│       ├── source.txt
│       ├── files/<original-filename>
│       ├── comments.html
│       └── comments.json
└── forums/
    └── <category>/<thread-name>/discussion.html
```

This export is planned, not implemented. General forum topics belong under
`export/forums/`; page discussions appear beside their pages. An exporter should
use `observed_post_ids` and `parent_id` to reconstruct the latest discussion,
and label retained older posts separately. It should render the structured post
records, not replay the raw AMC interface HTML from `thread.json.responses`.
Raw responses preserve evidence and metadata; catalogs and run reports support
recovery and coverage auditing. None requires changing the numeric canonical
paths or duplicating comments in the working archive.

`forums/catalog.json` is the latest completed discovery, even when the subsequent
thread crawl is incomplete. Its `run_id` names a timestamped directory under
`forums/runs/`, containing the same catalog and the run's report. If interrupted
before reporting, the directory has a catalog but no report. Historical snapshots
preserve categories and groups that disappear from later listings. Existing
`catalogs/<uuid>.json` and `runs/<uuid>.json` files are retained; older catalogs
remain readable when no current `catalog.json` exists.

Public group IDs are not exposed: category
`group_position` refers to that catalog's `groups_html` list, not a remote ID.
Each catalog includes the original forum index HTML and discovery warnings.

`thread.json` records thread metadata, references from archived pages, the
latest observed post IDs in display order, and original thread/posts endpoint
bodies. `posts.jsonl` stores authors, UTC timestamps, reply parent IDs, titles
and rendered HTML. Extracted titles trim transport padding; original bodies
retain it. New post HTML contains only the content element's inner HTML; the
outer Wikidot `div.content` wrapper is excluded. Formatting, nested elements and
whitespace are preserved through DOM serialization, without text cleanup. The
original response remains in `thread.json.responses`. Older wrapped post records
remain valid HTML and are not automatically rewritten; refetching a post writes
the cleaner form.
Revision HTML is saved unchanged from the endpoint's `content` field.
`history_position` is a derived, zero-based ordering, not a Wikidot revision number.

Later snapshots update observed posts and retain previously saved posts and
revisions that are now absent. Use `observed_post_ids` to distinguish the latest
snapshot from retained records. `revisions_included` describes the latest
snapshot; historical revision records may remain after a run without revisions.
Thread files publish as a recoverable transaction before completion is recorded.

Run reports retain errors and warnings. `.state/forum-errors.jsonl` contains
the most recent invocation that encountered thread failures, including interrupted
runs; it is diagnostic history, not an indicator of current completion.

### `pages/<page_id>/page.json`

Contains normalized page metadata such as:

- fullname, name, category, and title;
- visible and hidden tags;
- parent relationship;
- creation and update metadata;
- comments and rating metadata;
- source path, character count, and SHA-256 hash.

### `pages/<page_id>/source.txt`

Contains the current Wikidot wiki source as UTF-8 text.

This is the original wiki markup rather than rendered HTML, so constructs
such as `[[include]]`, collapsibles, modules, and Wikidot formatting syntax
remain preserved.

### `pages/<page_id>/files.json`

Contains metadata for attachments associated with the page, including their
original Wikidot filename and URL.

Attachment contents are not renamed or converted. Their original bytes are
stored unchanged in the global content-addressed blob store and referenced
from `files.json`.

For example:

```text
pages/802215837/files.json
        │
        │ name = Gold_credit_card009ua.jpg
        │ sha256 = abc...
        ▼
blobs/sha256/abc...
```

The blob is still the original JPEG data even though its stored filename has
no `.jpg` extension.

Content-addressed storage avoids keeping duplicate copies when identical
binary content is referenced more than once.

A future export/restore command can reconstruct a human-readable directory
tree using the original filenames without modifying the archived data.

### `revisions/`

Created when `--revisions` is enabled.

`revisions.jsonl` contains one metadata record for each page revision.
Newly written histories are ordered by `revision_no`, oldest first (`0, 1, 2, ...`).
Older archives may use newest-first order and remain valid; readers should use
`revision_no` rather than line position. Existing files are not automatically reordered.
`sources/<revision_id>.txt` contains the corresponding historical Wikidot
source.

### `blobs/sha256/`

Contains immutable binary data addressed by SHA-256 digest.

The filename identifies the exact file contents rather than the original
Wikidot filename. Original names, MIME metadata, source URLs, and page
relationships remain stored in `files.json`.

### `indexes/`

Contains derived navigation data.

`pages.csv` is intended for convenient manual lookup by page fullname/title.
`pages.json` provides similar information in a machine-readable format.

The page directories remain the authoritative archive data; indexes can be
rebuilt from them.

### `.state/`

Contains temporary operational state used to resume interrupted or partial
backup runs and record failures.

After a completed write it is not required to interpret the portable archive.
If a process stops while publishing page or revision files, keep the transaction
directory: it contains the prior bytes needed for rollback. The next backup
recovers interrupted writes before processing pages. `info` refuses to inspect
a pending transaction. Do not run concurrent writers against the same archive.

## Archive formats

The backup intentionally uses ordinary open formats:

| Data | Format |
| --- | --- |
| Wikidot source | UTF-8 text |
| Page metadata | JSON |
| Revision metadata | JSONL |
| Attachment metadata | JSON |
| Binary attachments | Original bytes |
| Navigation indexes | JSON / CSV |
| Integrity | SHA-256 |

Archived source and metadata are independent of the third-party `wikidot.py`
object model. Wikidot-specific data is normalized before it enters the
persistent archive format.

## Project structure

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
    │   ├── forum_client.py
    │   ├── models.py
    │   ├── retry.py
    │   └── source.py
    │
    ├── models/
    │   ├── common.py
    │   ├── file.py
    │   ├── forum_records.py
    │   ├── manifest.py
    │   ├── page.py
    │   └── revision.py
    │
    ├── collectors/
    │   ├── common.py
    │   ├── files.py
    │   ├── forum_threads.py
    │   ├── pages.py
    │   └── revisions.py
    │
    ├── services/
    │   ├── backup.py
    │   ├── backup_types.py
    │   ├── forum_backup.py
    │   └── estimate.py
    │
    ├── storage/
    │   ├── archive.py
    │   ├── atomic.py
    │   ├── forum_archive.py
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

The main responsibilities are:

- `wikidot/` — communication with Wikidot and normalization of remote data;
- `collectors/` — conversion of Wikidot data into persistent archive records;
- `models/` — schemas for data stored in the archive;
- `services/` — backup workflow orchestration;
- `storage/` — archive writing, manifest handling, indexes, inspection, and resume state;
- `ui/` — terminal progress reporting;
- `util/` — small shared utilities such as hashing and output formatting.

## Reliability

A component is marked complete only after its data has been successfully
persisted. Interrupted runs can therefore retry unfinished work without
invalidating components that were already archived.

Transient network failures use bounded retry/backoff.

Malformed metadata, unsupported schema versions, programming errors and disk
failures abort the run. Expected remote resource/network failures are recorded
per page. Resumed page identities are checked before skipping their content.
Existing blobs are verified before reuse; corrupt blobs cause an error.

Page/source pairs and revision collections are staged before publication and
retain rollback copies until the group commits. Each file replacement is
atomic; the recovery journal handles interruption between replacements.

The archive stores original source text and attachment bytes separately from
Wikidot-specific runtime objects so that the resulting data remains usable
without this program or Wikidot.
