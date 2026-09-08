# SCP Wikidot Backup

CLI tool for creating portable backups of Wikidot-based SCP sites.

The archive preserves Wikidot content in simple filesystem-based formats so
that it can be inspected without this program and later used for disaster
recovery or migration to another wiki engine.

## Current features

- complete page discovery across all Wikidot categories;
- current page metadata and Wikidot source;
- optional complete page revision history;
- revision authors, timestamps, comments, and historical source;
- resumable component-aware backup runs;
- retry/backoff for transient Wikidot failures;
- SHA-256 source integrity hashes;
- JSON and CSV page indexes for easier navigation.

Attachments, forums/discussions, and locally derived link information are
planned but not yet implemented.

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

Back up the current version of every page:

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

Pages are stored by their stable numeric Wikidot page ID. The human-readable
fullname and title remain available in page metadata and indexes.

```text
backup/
├── pages/
│   └── <page_id>/
│       ├── page.json
│       ├── source.txt
│       └── revisions/                 # only with --revisions
│           ├── revisions.jsonl
│           └── sources/
│               └── <revision_id>.txt
├── indexes/
│   ├── pages.json
│   └── pages.csv
└── .state/
    ├── completed_pages.jsonl
    └── errors.jsonl
```

### `pages/<page_id>/page.json`

Contains normalized page metadata such as:

- page fullname, name, category, and title;
- visible and hidden tags;
- parent relationship;
- creation/update metadata;
- comments and rating metadata;
- source path, character count, and SHA-256 hash.

### `pages/<page_id>/source.txt`

Contains the current Wikidot wiki source as UTF-8 text.

This is source markup rather than rendered HTML, so Wikidot constructs such
as `[[include]]`, collapsibles, modules, and formatting syntax remain
preserved.

### `revisions/`

Created when `--revisions` is enabled.

`revisions.jsonl` contains one metadata record per revision, while
`sources/<revision_id>.txt` contains the corresponding historical Wikidot
source.

### `indexes/`

Derived navigation data.

`pages.csv` is intended for convenient manual lookup by page name/title.
`pages.json` provides the same general mapping in a machine-readable format.

The page directories remain the authoritative archive data; indexes can be
rebuilt from them.

### `.state/`

Temporary operational state used to resume interrupted or partial backup
runs and record errors.

It is not part of the portable archive format itself.

## Archive format

The backup intentionally uses ordinary open formats:

| Data | Format |
| --- | --- |
| Wikidot source | UTF-8 text |
| Entity metadata | JSON |
| Revision collections | JSONL |
| Navigation indexes | JSON / CSV |
| Integrity hashes | SHA-256 |
| Attachments | Original binary files (planned) |

Archived source and metadata are kept separate from the `wikidot.py` data
model. Wikidot-specific integration code is normalized before data enters
the persistent archive format.

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
    │   ├── page.py
    │   └── revision.py
    │
    ├── collectors/
    │   ├── common.py
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
- `collectors/` — conversion of Wikidot data into archive models;
- `models/` — persistent archive schemas;
- `services/` — backup workflow orchestration;
- `storage/` — filesystem archive, indexes, and resume state;
- `ui/` — terminal progress reporting.

## Reliability

Backup writes are resumable. A page component is marked complete only after
its data has been successfully persisted, so interrupted runs can retry
unfinished work without invalidating already archived content.

Transient network failures use bounded retry/backoff. Archive data is stored
independently of the third-party `wikidot.py` object model.