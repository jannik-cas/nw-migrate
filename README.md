# nw-migrate

[![CI](https://github.com/jannik-cas/nw-migrate/actions/workflows/ci.yml/badge.svg)](https://github.com/jannik-cas/nw-migrate/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jannik-cas/nw-migrate/graph/badge.svg)](https://codecov.io/gh/jannik-cas/nw-migrate)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

Convert Pandas code to [Narwhals](https://narwhals-dev.github.io/narwhals/) automatically.

nw-migrate parses your Python files, renames Pandas method calls to their Narwhals equivalents, adds `@nw.narwhalify` decorators, and flags operations that need manual review.

## Installation

```bash
pip install nw-migrate
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add nw-migrate
```

Or run without installing via [uvx](https://docs.astral.sh/uv/guides/tools/):

```bash
uvx nw-migrate check src/
```

## Usage

**Check** what can be converted (no changes made):

```bash
nw-migrate check src/
```

```
src/pipeline.py:12:4 [EASY] sort_values() -> sort()
src/pipeline.py:28:4 [EASY] merge() -> join()
src/pipeline.py:45:8 [MEDIUM] fillna() -> with_columns(nw.col(...).fill_null()) -- needs manual review
src/pipeline.py:52:8 [HARD] apply() has no direct Narwhals equivalent

Found 4 convertible Pandas usage(s).
```

**Convert** files in-place:

```bash
nw-migrate convert src/pipeline.py
```

**Preview** changes as a diff:

```bash
nw-migrate convert src/pipeline.py --diff
```

## Example

```python
# Before
import pandas as pd

def clean_data(df):
    result = df.sort_values('date')
    result = result.drop(columns=['temp', 'debug'])
    result = result.rename(columns={'old_name': 'new_name'})
    return result.drop_duplicates()
```

```python
# After
import narwhals as nw

@nw.narwhalify
def clean_data(df):
    result = df.sort('date')
    result = result.drop('temp', 'debug')
    result = result.rename({'old_name': 'new_name'})
    return result.unique()
```

The converted function now works with Pandas, Polars, PyArrow, cuDF, and Modin — no code changes needed.

## What Gets Converted

### Auto-converted (EASY)

| Pandas | Narwhals |
|--------|----------|
| `df.sort_values('col')` | `df.sort('col')` |
| `df.groupby('col')` | `df.group_by('col')` |
| `df.merge(other, on='id')` | `df.join(other, on='id')` |
| `df.drop_duplicates()` | `df.unique()` |
| `df.drop(columns=['a'])` | `df.drop('a')` |
| `df.rename(columns={...})` | `df.rename({...})` |
| `df[['col1', 'col2']]` | `df.select(['col1', 'col2'])` |

`ascending=False` is automatically converted to `descending=True`.

### Flagged for Review (MEDIUM)

These get a `# TODO(nw-migrate)` comment:

`fillna`, `isna`, `notna`, `astype`, `melt`, `value_counts`

These require switching to Narwhals' expression-based API and can't be mechanically renamed.

### Flagged Only (HARD)

These have no Narwhals equivalent:

`apply`, `iterrows`, `itertuples`, `query`, `select_dtypes`, `applymap`

## How It Works

1. Parses your code with [libcst](https://libcst.readthedocs.io/) (preserves formatting, comments, whitespace)
2. Collects all Pandas method calls matching conversion rules
3. Renames methods and transforms arguments for EASY cases
4. Adds `@nw.narwhalify` decorator to functions that received conversions
5. Adds `import narwhals as nw` at the top
6. Injects TODO comments for MEDIUM/HARD cases

## Pre-commit

```yaml
repos:
  - repo: https://github.com/jannik-cas/nw-migrate
    rev: v0.1.0
    hooks:
      - id: nw-migrate-check
```

## Limitations

- No type inference — converts any matching method call regardless of whether the receiver is actually a DataFrame. Review the output.
- Does not handle `pd.merge()` (free function), only `df.merge()` (method call).
- Does not convert `pd.concat()` to `nw.concat()`.
- Chained calls are converted independently — a chain mixing easy and hard operations will partially convert.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

[MIT](LICENSE)
