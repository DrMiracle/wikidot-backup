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
- offline human-readable export with named attachments, revision history, and discussions;
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

### Windows: first-time setup

You do not need PyCharm or programming experience to run the tool. The commands
below go into **PowerShell**. Copy only
the commands inside each code block, run them in order, and wait for each to finish.

#### 1. Install Python

Install the **Python install manager** from [python.org](https://www.python.org/downloads/windows/).
Open PowerShell from the Start menu (reopen it if it was already open), then run:

```powershell
py install 3.14
py -3.14 --version
```

The second command should print `Python 3.14.x`. If you already have Python 3.14,
you can skip the installation command. Python 3.12 and 3.13 also work: use your
installed version in place of `3.14` in the environment-creation command below.
Python 3.15 and later are not currently supported by this project.

If `py` is not recognized, reopen PowerShell and check that installation finished.
If `py install` tries to open a file named `install`, an older Python launcher is
handling the command; see the [official Windows setup guide](https://docs.python.org/3/using/windows.html).

#### 2. Download and open the project folder

Open the [project repository](https://github.com/DrMiracle/wikidot-backup), choose
**Code → Download ZIP**, and extract the ZIP. Open the extracted folder containing
`pyproject.toml`, `README.md`, and `src`—not the ZIP itself or its parent folder.

In File Explorer's address bar, type `powershell` and press Enter. This opens
PowerShell in that folder. Check your location:

```powershell
Get-Item .\pyproject.toml
```

If it says the file cannot be found, open the correct folder before continuing.

#### 3. Create a private Python environment

A virtual environment is a folder containing this project's Python environment
and libraries. It keeps them separate from those used by other programs.

```powershell
py -3.14 -m venv .venv
```

This creates a `.venv` folder inside the project. No output usually means success.
You only need to create it once for this copy of the project.

#### 4. Install the backup tool

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

This downloads the required libraries and installs the command.
Keep the project folder in place after installation. Internet access is needed.

#### 5. Check the installation and try a small backup

```powershell
.\.venv\Scripts\wikidot-backup.exe --help
.\.venv\Scripts\wikidot-backup.exe backup scp-ukrainian --limit 1
```

Help should list the commands and options. The second command downloads one
page and its attachments into `backup` inside the current folder. Page discovery
still checks the site first, so this may take a little time. You can use
`--output ./my-backup` to choose another archive directory.

#### 6. Use the shorter commands shown below

To type `wikidot-backup` instead of its full path, activate the environment:

```powershell
.\.venv\Scripts\Activate.ps1
wikidot-backup --help
```

You will normally see `(.venv)` at the start of your prompt. Activate it again
whenever you open a new PowerShell window, after opening the project folder.
You do not need to repeat environment creation or installation each time.

If PowerShell says script execution is disabled, activation is optional: continue
using `.\.venv\Scripts\wikidot-backup.exe` in place of `wikidot-backup` in every
example. No execution-policy change is needed. Python's
[virtual environment documentation](https://docs.python.org/3/library/venv.html)
explains how direct executable paths work without activation.

### Optional: development tools

Only install these extras if you want to run tests or work on the code:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
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

Resuming first discovers the current page list, reads the local resume file,
and checks each completed page's ID against Wikidot before skipping it. These
identity checks protect against a deleted page's name being reused by a different
page. They make network requests, so resuming thousands of pages can take time;
they do not re-download completed sources, attachments or revision histories.
Progress shows these as separate phases, including `Checking saved page IDs`.
`--verbose` also prints the page name before each check. If a request is slow or
retrying, the counter stays on that page until it succeeds or raises an error.

Options can be combined:

```powershell
wikidot-backup backup scp-ukrainian --revisions --limit 20 --output ./backup
```

You can also back up another site into a separate directory:

```bash
wikidot-backup backup scp-ukrainian --output ./backup-ukrainian
wikidot-backup backup scp-wiki --output ./backup-english
```

Each archive directory belongs to one site; the manifest prevents mixing sites.

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

### Exporting a readable copy

```powershell
wikidot-backup export ./backup --output ./export
```

Open `export/index.html` to browse pages and discussions. Export runs offline and
leaves the backup unchanged. Choose a new output directory outside the backup;
existing output directories are never overwritten. Add `--verbose` to list each
page and standalone thread as it is exported.

Open that file directly from Windows File Explorer in your browser. No localhost
server is required; a temporary editor preview URL may stop working later.
Source links open UTF-8 HTML viewers so Ukrainian text displays correctly;
the original `source.txt` and revision text files remain unchanged.

Export does not currently resume or update an existing export. After updating
your backup, generate another snapshot with a new output directory, for example
`wikidot-backup export ./backup --output ./export-updated`. This reads local
files only and does not download the site again.

Each page directory contains original wiki source, metadata, named attachments,
revision history if archived, and its discussion if available. Source remains
wiki markup; this is not a complete Wikidot page renderer. Discussion HTML keeps
basic formatting and reply links, disables scripts, and shows remote images as
links. Original post HTML remains available in the JSON records.

Attachments are copied byte-for-byte, with their original extensions. Names that
are invalid on Windows or collide are adjusted; exported `files.json` maps each
original name to its exported path and retains the original archive metadata.
Revision source paths in exported records are relative to the page directory.

Missing content produces warnings in `export.json` and each page's
`export-status.json`, and exit code 2. If `files.json` was never archived, the
attachment list is unknown; export cannot recover filenames from orphaned blobs.
Malformed metadata or failed integrity checks stop export with exit code 1.
Interrupted or failed output remains marked incomplete; retry into a new directory.
Do not export while another process is writing the backup.

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

The export command follows `page.json.discussion_thread_id` to place discussions
beside their pages. Its readable layout is:

```text
export/
├── index.html
├── export.json
├── pages/
│   └── scp-182-ua/
│       ├── index.html
│       ├── page.json
│       ├── source.txt
│       ├── export-status.json
│       ├── files.json
│       ├── files/<original-filename>
│       ├── revisions/
│       │   ├── index.html
│       │   ├── revisions.jsonl
│       │   └── sources/<revision-number>-<revision-id>.txt
│       └── discussion/
│           ├── index.html
│           ├── thread.json
│           ├── posts.jsonl
│           └── post-revisions.jsonl
└── forums/
    └── <thread-name>/              # same files as discussion/
```

Threads without an exported page belong under `export/forums/`, including
discussions of deleted pages. Export uses `observed_post_ids` and `parent_id`
to show the latest discussion and reply links, and labels retained older posts
separately. It renders structured post records rather than replaying the raw
AMC interface HTML from `thread.json.responses`.
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
pages/123456789/files.json
        │
        │ name = photo.jpg
        │ sha256 = abc...
        ▼
blobs/sha256/abc...
```

The blob is still the original JPEG data even though its stored filename has
no `.jpg` extension.

Content-addressed storage avoids keeping duplicate copies when identical
binary content is referenced more than once.

The export command reconstructs a human-readable directory
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
    │   ├── export.py
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
    │   ├── export_html.py
    │   ├── help.py
    │   └── progress.py
    │
    └── util/
        ├── export_names.py
        ├── formatting.py
        └── hashing.py
```

The main responsibilities are:

- `wikidot/` — communication with Wikidot and normalization of remote data;
- `collectors/` — conversion of Wikidot data into persistent archive records;
- `models/` — schemas for data stored in the archive;
- `services/` — backup workflow orchestration;
- `storage/` — archive writing, manifest handling, indexes, inspection, and resume state;
- `ui/` — terminal reporting and offline export HTML;
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
