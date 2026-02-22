# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-02-22

### Added

- Initial release
- `check` command to scan for convertible Pandas usages
- `convert` command with `--dry-run` and `--diff` modes
- Auto-conversion of 6 EASY methods: `sort_values`, `groupby`, `merge`,
  `drop_duplicates`, `drop`, `rename`
- Auto-conversion of `df[['col1', 'col2']]` to `df.select(...)`
- Argument transforms: `ascending` to `descending`, `by=` unwrap, `columns=` unwrap
- `@nw.narwhalify` decorator injection (with duplicate detection)
- `import narwhals as nw` injection (placed after existing imports)
- TODO comment injection for MEDIUM and HARD cases
- Pre-commit hook support (`nw-migrate-check`)
- 100% test coverage enforced in CI
