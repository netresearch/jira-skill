# Changelog fragments

Each pull request writes its changelog entry into its own file here instead of
editing `## [Unreleased]` in `CHANGELOG.md`. Two pull requests that both edit
that section conflict as soon as one of them merges; two fragment files do not.

## Format

- File name: `<branch-slug>.<section>.md`, lowercase, for example
  `fix-sync-lock.fixed.md`. The branch slug keeps names unique.
- `<section>` selects the heading the entry lands under:

  | Section      | Heading in `CHANGELOG.md`                         |
  |--------------|---------------------------------------------------|
  | `upgrading`  | `### Upgrading from X.Y` (the last minor release) |
  | `added`      | `### Added`                                       |
  | `changed`    | `### Changed`                                     |
  | `deprecated` | `### Deprecated`                                  |
  | `removed`    | `### Removed`                                     |
  | `fixed`      | `### Fixed`                                       |
  | `security`   | `### Security`                                    |

- Content: one or more top-level bullets (`-` and a space), written as they
  will appear in `CHANGELOG.md`. No heading; the file name selects it. A
  change that belongs under two headings gets two files.

Apart from this `README.md`, any other file in this directory, or a fragment
that breaks these rules (including a code fence left open), stops the release
roll before it writes anything.

## Release

The version bump runs `roll-changelog.py` from the skill-repo skill. Before it
moves `[Unreleased]` under the new version, it appends every fragment, in
file-name order, at the end of its heading, creates a missing heading in Keep a
Changelog order, and deletes the fragment. The bump commit carries those
deletions. With no fragments the roll works as it does without this directory:
it still moves the existing `[Unreleased]` entries under the new version. Preview with
`roll-changelog.py CHANGELOG.md X.Y.Z --dry-run`.
