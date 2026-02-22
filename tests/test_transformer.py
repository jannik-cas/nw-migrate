from __future__ import annotations

import textwrap

from nw_migrate.rules import Difficulty
from nw_migrate.transformer import transform_source


def _dedent(s: str) -> str:
    return textwrap.dedent(s).lstrip("\n")


class TestSortValues:
    def test_simple(self) -> None:
        source = _dedent("""\
            def process(df):
                return df.sort_values('name')
        """)
        result, findings = transform_source(source)
        assert "df.sort('name')" in result
        assert "@nw.narwhalify" in result
        assert "import narwhals as nw" in result
        assert len(findings) == 1
        assert findings[0].rule.difficulty == Difficulty.EASY

    def test_ascending_false(self) -> None:
        source = _dedent("""\
            def process(df):
                return df.sort_values('name', ascending=False)
        """)
        result, _ = transform_source(source)
        assert "descending=True" in result
        assert "ascending" not in result

    def test_ascending_true(self) -> None:
        source = _dedent("""\
            def process(df):
                return df.sort_values('name', ascending=True)
        """)
        result, _ = transform_source(source)
        assert "descending=False" in result

    def test_by_kwarg_unwrapped(self) -> None:
        source = _dedent("""\
            def process(df):
                return df.sort_values(by='name')
        """)
        result, _ = transform_source(source)
        assert "df.sort('name')" in result
        assert "by=" not in result


class TestGroupby:
    def test_simple(self) -> None:
        source = _dedent("""\
            def process(df):
                return df.groupby('col').agg({'val': 'mean'})
        """)
        result, findings = transform_source(source)
        assert "df.group_by('col')" in result
        assert len(findings) == 1


class TestMerge:
    def test_simple(self) -> None:
        source = _dedent("""\
            def process(df, other):
                return df.merge(other, on='id')
        """)
        result, _ = transform_source(source)
        assert "df.join(other, on='id')" in result


class TestDropDuplicates:
    def test_simple(self) -> None:
        source = _dedent("""\
            def process(df):
                return df.drop_duplicates()
        """)
        result, _ = transform_source(source)
        assert "df.unique()" in result


class TestDrop:
    def test_columns_kwarg(self) -> None:
        source = _dedent("""\
            def process(df):
                return df.drop(columns=['a', 'b'])
        """)
        result, _ = transform_source(source)
        assert "df.drop(['a', 'b'])" in result
        assert "columns=" not in result


class TestRename:
    def test_columns_kwarg(self) -> None:
        source = _dedent("""\
            def process(df):
                return df.rename(columns={'old': 'new'})
        """)
        result, _ = transform_source(source)
        assert "df.rename({'old': 'new'})" in result
        assert "columns=" not in result


class TestSubscriptSelect:
    def test_list_subscript(self) -> None:
        source = _dedent("""\
            def process(df):
                return df[['col1', 'col2']]
        """)
        result, findings = transform_source(source)
        assert "df.select(['col1', 'col2'])" in result
        assert len(findings) == 1


class TestDecorator:
    def test_added_to_converted_function(self) -> None:
        source = _dedent("""\
            def process(df):
                return df.sort_values('name')
        """)
        result, _ = transform_source(source)
        assert "@nw.narwhalify" in result

    def test_not_duplicated(self) -> None:
        source = _dedent("""\
            import narwhals as nw

            @nw.narwhalify
            def process(df):
                return df.sort_values('name')
        """)
        result, _ = transform_source(source)
        assert result.count("@nw.narwhalify") == 1

    def test_not_added_to_non_converted(self) -> None:
        source = _dedent("""\
            def helper(x):
                return x + 1

            def process(df):
                return df.sort_values('name')
        """)
        result, _ = transform_source(source)
        lines = result.splitlines()
        # Find decorator and verify it's before process, not helper
        dec_idx = next(i for i, line in enumerate(lines) if "@nw.narwhalify" in line)
        func_idx = next(i for i in range(dec_idx, len(lines)) if "def " in lines[i])
        assert "process" in lines[func_idx]


class TestImport:
    def test_added_when_needed(self) -> None:
        source = _dedent("""\
            def process(df):
                return df.sort_values('name')
        """)
        result, _ = transform_source(source)
        assert "import narwhals as nw" in result

    def test_not_duplicated(self) -> None:
        source = _dedent("""\
            import narwhals as nw

            def process(df):
                return df.sort_values('name')
        """)
        result, _ = transform_source(source)
        assert result.count("import narwhals as nw") == 1

    def test_placed_after_existing_imports(self) -> None:
        source = _dedent("""\
            import os
            import sys

            def process(df):
                return df.sort_values('name')
        """)
        result, _ = transform_source(source)
        lines = result.splitlines()
        nw_idx = next(i for i, line in enumerate(lines) if "import narwhals" in line)
        sys_idx = next(i for i, line in enumerate(lines) if "import sys" in line)
        assert nw_idx > sys_idx


class TestMediumHardFlagging:
    def test_medium_gets_todo(self) -> None:
        source = _dedent("""\
            def process(df):
                return df.fillna(0)
        """)
        result, findings = transform_source(source)
        assert "# TODO(nw-migrate):" in result
        assert "manual review" in result
        assert findings[0].rule.difficulty == Difficulty.MEDIUM

    def test_hard_gets_todo(self) -> None:
        source = _dedent("""\
            def process(df):
                return df.apply(lambda x: x * 2)
        """)
        result, findings = transform_source(source)
        assert "# TODO(nw-migrate):" in result
        assert findings[0].rule.difficulty == Difficulty.HARD

    def test_medium_no_decorator(self) -> None:
        source = _dedent("""\
            def process(df):
                return df.fillna(0)
        """)
        result, _ = transform_source(source)
        assert "@nw.narwhalify" not in result


class TestNoOp:
    def test_no_pandas(self) -> None:
        source = _dedent("""\
            def add(a, b):
                return a + b
        """)
        result, findings = transform_source(source)
        assert result == source
        assert len(findings) == 0


class TestChainedCalls:
    def test_chained(self) -> None:
        source = _dedent("""\
            def process(df):
                return df.sort_values('a').drop_duplicates()
        """)
        result, findings = transform_source(source)
        assert "df.sort('a').unique()" in result
        assert len(findings) == 2
