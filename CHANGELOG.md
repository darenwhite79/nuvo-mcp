# Changelog

The format is [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
the numbering is [semantic](https://semver.org/).

## [0.1.0] — 2026-09-03

The first release: the server has been pulled out of the app's repository into a
package of its own, and installs in a single line.

### Added

- Twenty-one tools: the lists and Today, search, a task in full, creating and
  editing, the note that stands in for comments, moving, state (do it, bring it
  back, park it, file it, trash it and back again), checklists, tags, projects
  and areas.
- Readable refusals instead of tracebacks: no key set, a key with non-ASCII
  characters in it, the app not answering, the key missing a right.
- Instructions for the client (`INSTRUCTIONS`) about how tasks are handled here:
  Today is a commitment, not a priority flag; a deadline and the day of doing
  are different things.
- Setup for Claude Code, Claude Desktop, Cursor, VS Code, Windsurf and Zed —
  [docs/clients.md](docs/clients.md).

### Deliberately missing

- Permanent deletion. Emptying the trash is the person's own job.
