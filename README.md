# SCP Wikidot Backup

Simple CLI-based backup and archival tool for Wikidot-based SCP sites.

The project is designed to preserve Wikidot content in a simple, portable format that can later be used for disaster recovery or migration to another wiki engine.

## Goals

The backup should eventually preserve:

* all wiki pages;
* raw Wikidot source;
* page metadata;
* tags;
* parent-page relationships;
* complete page revision history;
* revision authors, timestamps, and comments;
* page attachments and their metadata;
* forum groups and categories;
* forum threads and posts;
* forum post revisions where available;
* page discussions/comments;
* locally derived link and backlink information.

The archive format should remain usable independently of this program and independently of Wikidot.

## Archive philosophy

The backup is filesystem-based rather than database-based.

Human-readable data is stored using open formats:

* Wikidot source: UTF-8 `.txt` files;
* metadata: JSON;
* append-style collections such as revisions/posts: JSONL;
* attachments: original binary data;
* integrity information: SHA-256 hashes.

## Requirements

* Python 3.12+
* Internet access to the target Wikidot site

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

The intended CLI interface is:

```bash
wikidot-backup backup <site-name>
```

Example:

```bash
wikidot-backup backup scp-ukrainian --output ./backup
```


## Project structure

```text
src/
└── wikidot_backup/
    ├── cli.py
    ├── config.py
    ├── models/
    ├── wikidot/
    ├── collectors/
    ├── storage/
    └── util/
```

## Reliability requirements

Backup operations should be safe to retry.

A failed request must not invalidate data that has already been successfully archived.

Existing archived revisions and attachments should not be removed merely because they disappear from a later Wikidot snapshot.

Network operations should use conservative retry and rate-limiting behaviour.

`wikidot.py` is treated as an external integration dependency, not as the archive's data model.

The Wikidot dependency is pinned to a tested version. Upgrades should be performed deliberately and tested against the target site before use.

## Status

Early development.

The current priority is a complete and verifiable page/source backup pipeline.
