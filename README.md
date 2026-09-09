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
- JSON and CSV page indexes for easier navigation.

Forums, page discussions, external resources, and locally derived link data
are not yet archived.

## Requirements

- Python 3.12+
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

Options can be combined:

```bash
wikidot-backup backup scp-ukrainian \
    --revisions \
    --limit 20 \
    --output ./backup
```

Run the built-in help for the complete CLI reference:

```bash
wikidot-backup --help
wikidot-backup backup --help
```

## Archive layout

Pages are stored by their stable numeric Wikidot page ID. Human-readable
page names and titles are preserved in metadata and navigation indexes.

```text
backup/
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
    └── errors.jsonl
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

It is not required to interpret the portable archive itself.

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
    │   ├── models.py
    │   ├── retry.py
    │   └── source.py
    │
    ├── models/
    │   ├── common.py
    │   ├── file.py
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
    │   └── backup_types.py
    │
    ├── storage/
    │   ├── archive.py
    │   ├── indexes.py
    │   └── state.py
    │
    ├── ui/
    │   └── progress.py
    │
    └── util/
        └── hashing.py
```

The main responsibilities are:

- `wikidot/` — communication with Wikidot and normalization of remote data;
- `collectors/` — conversion of Wikidot data into persistent archive records;
- `models/` — schemas of data stored in the archive;
- `services/` — backup workflow orchestration;
- `storage/` — archive writing, indexes, and resume state;
- `ui/` — terminal progress reporting;
- `util/` — small shared utilities such as hashing.

## Reliability

A component is marked complete only after its data has been successfully
persisted. Interrupted runs can therefore retry unfinished work without
invalidating components that were already archived.

Transient network failures use bounded retry/backoff.

The archive stores original source text and attachment bytes separately from
Wikidot-specific runtime objects so that the resulting data remains usable
without this program or Wikidot.