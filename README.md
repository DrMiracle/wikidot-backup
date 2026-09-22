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
- revision authors, timestamps, comments, and historical source;
- content-addressed attachment storage with SHA-256 integrity hashes;
- resumable component-aware backup runs;
- retry/backoff for transient Wikidot failures;
- JSON and CSV page indexes for easier navigation;
- root archive metadata (`archive.json`) with site identity and backup timestamps;
- approximate backup size estimation from current source and remote metadata;
- archive inspection with page, revision, attachment, error, and disk usage statistics.

Forums, page discussions, external resources, and locally derived link data
are not yet archived.

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
└── .state/
    ├── resume.jsonl
    ├── errors.jsonl
    └── transactions/                # temporary interrupted-write recovery
```

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
