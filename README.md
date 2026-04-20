# journal-scripts

Custom command-line tools for journalism workflow: archiving Guardian stories into a PKM vault, downloading podcasts, transcribing recordings, and keeping an Obsidian/LogSeq vault up to date.

Designed around a specific personal setup (PKM vault at `~/notebook`, LogSeq + Obsidian interoperability, Claude Code for LLM-assisted tasks), but documented so others can adapt them.

## What's here

| Script | Purpose |
|---|---|
| [`story-closeout`](#story-closeout) | Archive a finished Guardian story folder into the PKM vault and a media archive |
| [`add-draft-frontmatter.sh`](#add-draft-frontmattersh) | Batch-add minimal YAML frontmatter to markdown drafts and move them into the vault |
| [`vault-digest`](#vault-digest) | Scan journal entries and propose append-only updates to existing entity pages (three-phase: scan → draft → apply) |
| [`vault-stubs`](#vault-stubs) | Find unresolved wikilinks and generate stub pages from vault-wide search context (two-phase: gather → draft) |
| [`yt-transcript`](#yt-transcript) | `yt-dlp` wrapper that auto-converts `.en.srt` files to clean `.transcript.txt` alongside the video |
| [`chromium-migrate`](#chromium-migrate) | Copy a Flatpak Chromium profile to a deb Chromium install (bookmarks, cookies, history, extensions, etc.) |

## Installation

Clone this repo and symlink the scripts you want into a directory on your `PATH`:

```bash
git clone https://github.com/J450n-4-W/journal-scripts.git ~/Software_Development_Projects/journal-scripts
for f in ~/Software_Development_Projects/journal-scripts/*; do
    [[ -x "$f" && ! -d "$f" ]] && ln -sf "$f" ~/.local/bin/"$(basename "$f")"
done
```

Updating later is just `git pull`.

## Prerequisites

- `bash`
- `jq`, `grep`, `find`, `sed`, `awk`, standard GNU core utilities
- `yt-dlp` (for `yt-transcript`)
- `claude` CLI from [Claude Code](https://claude.com/claude-code) (for `vault-digest`, `vault-stubs` — the draft phases call out to Claude)
- Python 3 (for `vault-digest`, `vault-stubs` scanning)

## Assumptions

The vault scripts (`story-closeout`, `add-draft-frontmatter.sh`, `vault-digest`, `vault-stubs`) assume:

- PKM vault at `~/notebook/` with `pages/`, `journals/`, `archive/`, `assets/` subdirectories
- LogSeq-style journal filenames: `YYYY_MM_DD.md` (or `YYYY-MM-DD.md`)
- `[[wikilinks]]` for entity references; YAML frontmatter for metadata
- Basenames must be unique across the whole vault (LogSeq treats same-basename files as the same page)

`story-closeout` additionally assumes a media archive directory at `/media/jason/4tb-external1/Reporting_Media_Archive/` — override via the hardcoded path in the script if yours is elsewhere.

---

## story-closeout

Archive a finished Guardian story folder into the PKM vault and media archive.

```bash
story-closeout <story-directory> [--slug NAME] [--date YYYY_MM]
```

Splits the story folder three ways:

- **Text** (published article, transcripts, background/coverage clips, RoR letters) → `~/notebook/archive/`
- **Small documents** (PDFs, EPUBs, DOCXs, CSVs, JSONs, DBs, ZIPs) → `~/notebook/assets/<slug>/`
- **Large media** (video/audio) → moved (not copied) to the media archive directory to free NVMe space

Working `.md` files (drafts, analysis) are listed for review rather than copied — they should be folded into entity pages as subheadings during an LLM-assisted follow-up phase.

## add-draft-frontmatter.sh

Batch-adds minimal YAML frontmatter to markdown drafts and moves them into `~/notebook/pages/`.

```bash
# Dry run (default — shows what would happen)
add-draft-frontmatter.sh ~/path/to/drafts

# Actually do it
DRY_RUN=0 add-draft-frontmatter.sh ~/path/to/drafts
```

Extracts the `created:` date from filenames starting with `YYYY-MM-DD` or `YYYY_MM_DD`; falls back to filesystem mtime. Skips files that already have frontmatter. Pre-flight collision check against the entire vault prevents overwriting anything elsewhere.

## vault-digest

Three-phase tool that scans recent journal entries for mentions of existing entity pages and drafts append-only updates via Claude.

```bash
vault-digest scan   [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--days N]
vault-digest draft  [--limit N] [--dry-run] [--force]
vault-digest apply  [--entity "Name"]
vault-digest status
```

The `scan` phase is pure Python — extracts wikilinks with outline context, cross-references against existing pages. The `draft` phase feeds context + current page content to Claude, which generates an append-only patch with deduplication. The `apply` helper shows a coloured diff and prints the `cp` command to install the patch.

Staging directory: `~/notebook-staging/digest/`.

## vault-stubs

Two-phase tool that finds wikilinks with no matching page, scans the vault for every mention of each candidate, and drafts stub pages via Claude.

```bash
vault-stubs gather [--min-mentions N] [--limit N]
vault-stubs draft  [--limit N] [--dry-run]
vault-stubs status
```

Opinionated about noise filtering — drops file-like links, URLs, dates, addresses, Wikipedia-style titles, and common false positives. Underscore variants are normalised and merged (`Jeremy_Carl` → `Jeremy Carl`). Stubs land in `~/notebook-staging/stubs/` for review.

## yt-transcript

`yt-dlp` wrapper that downloads a video along with its English subtitle file, then produces a clean `.transcript.txt` alongside each `.en.srt` file.

```bash
yt-transcript URL [URL...]
yt-transcript --cookies-from-browser firefox URL  # any yt-dlp flag works
```

Strips subtitle block numbers, deduplicates the scrolling-subtitle artifact that YouTube auto-captions produce (each content line appears in 3 consecutive subtitle blocks), but **keeps** timestamps and `>> ` speaker-change markers so you can jump to a point in the video to verify quotes.

## chromium-migrate

Copies a Flatpak Chromium profile to a deb Chromium installation — bookmarks, cookies, history, extensions, autofill, preferences, local storage, etc.

```bash
# Close Chromium first, then:
chromium-migrate
```

No arguments; paths are hardcoded. Refuses to run if Chromium is still running; prompts before overwriting an existing deb profile. Saved passwords won't decrypt across installs — export them to CSV first via `chrome://settings/passwords` and re-import after migration (script reminds you).

---

## License

No license specified — treat as "all rights reserved" unless you've asked.
