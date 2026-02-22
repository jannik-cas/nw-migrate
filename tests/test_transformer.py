from __future__ import annotations

import textwrap


from nw_migrate.rules import Difficulty
from nw_migrate.transformer import (
    transform_source,
)


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

    def test_ascending_variable(self) -> None:
        """When ascending is a variable (not a literal), we wrap it in `not`."""
        source = _dedent("""\
            def process(df, flag):
                return df.sort_values('name', ascending=flag)
        """)
        result, _ = transform_source(source)
        assert "descending=not flag" in result

    def test_by_kwarg_unwrapped(self) -> None:
        """The by= kwarg doesn't exist in Narwhals, so it becomes positional."""
        source = _dedent("""\
            def process(df):
                return df.sort_values(by='name')
        """)
        result, _ = transform_source(source)
        assert "df.sort('name')" in result
        assert "by=" not in result

    def test_unknown_kwarg_preserved(self) -> None:
        """Kwargs we don't have a transform for (like key=) are kept as-is."""
        source = _dedent("""\
            def process(df):
                return df.sort_values('name', key=str.lower)
        """)
        result, _ = transform_source(source)
        assert "key=str.lower" in result


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

    def test_single_string_subscript_ignored(self) -> None:
        """df['col'] is single-column access, not multi-column select."""
        source = _dedent("""\
            def process(df):
                return df['col1']
        """)
        result, findings = transform_source(source)
        assert result == source
        assert len(findings) == 0

    def test_slice_subscript_ignored(self) -> None:
        """Row slicing like df[0:5] is not column selection."""
        source = _dedent("""\
            def process(df):
                return df[0:5]
        """)
        result, findings = transform_source(source)
        assert result == source
        assert len(findings) == 0


class TestDecorator:
    def test_added_to_converted_function(self) -> None:
        source = _dedent("""\
            def process(df):
                return df.sort_values('name')
        """)
        result, _ = transform_source(source)
        assert "@nw.narwhalify" in result

    def test_not_duplicated_attribute(self) -> None:
        """If @nw.narwhalify already exists, don't add another one."""
        source = _dedent("""\
            import narwhals as nw

            @nw.narwhalify
            def process(df):
                return df.sort_values('name')
        """)
        result, _ = transform_source(source)
        assert result.count("@nw.narwhalify") == 1

    def test_not_duplicated_bare_name(self) -> None:
        """Also recognize @narwhalify (from direct import) as existing decorator."""
        source = _dedent("""\
            from narwhals import narwhalify

            @narwhalify
            def process(df):
                return df.sort_values('name')
        """)
        result, _ = transform_source(source)
        assert "@nw.narwhalify" not in result
        assert result.count("narwhalify") >= 2  # import + decorator

    def test_not_duplicated_call_form(self) -> None:
        """Also recognize @nw.narwhalify() (with parens) as existing decorator."""
        source = _dedent("""\
            import narwhals as nw

            @nw.narwhalify()
            def process(df):
                return df.sort_values('name')
        """)
        result, _ = transform_source(source)
        assert result.count("@nw.narwhalify()") == 1
        assert result.count("import narwhals as nw") == 1

    def test_not_added_to_non_converted(self) -> None:
        """Only the function containing Pandas calls gets decorated, not siblings."""
        source = _dedent("""\
            def helper(x):
                return x + 1

            def process(df):
                return df.sort_values('name')
        """)
        result, _ = transform_source(source)
        lines = result.splitlines()
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
        """If 'import narwhals as nw' already exists, don't add it again."""
        source = _dedent("""\
            import narwhals as nw

            def process(df):
                return df.sort_values('name')
        """)
        result, _ = transform_source(source)
        assert result.count("import narwhals as nw") == 1

    def test_placed_after_existing_imports(self) -> None:
        """The narwhals import should appear after other imports, not before."""
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

    def test_placed_at_top_when_no_imports(self) -> None:
        """When there are no existing imports, narwhals goes before the code."""
        source = _dedent("""\
            def process(df):
                return df.sort_values('name')
        """)
        result, _ = transform_source(source)
        lines = result.splitlines()
        nw_idx = next(i for i, line in enumerate(lines) if "import narwhals" in line)
        func_idx = next(i for i, line in enumerate(lines) if "def " in line)
        assert nw_idx < func_idx


class TestMediumHardFlagging:
    def test_medium_gets_todo(self) -> None:
        """MEDIUM calls can't be auto-converted, so they get a TODO comment."""
        source = _dedent("""\
            def process(df):
                return df.fillna(0)
        """)
        result, findings = transform_source(source)
        assert "# TODO(nw-migrate):" in result
        assert "manual review" in result
        assert findings[0].rule.difficulty == Difficulty.MEDIUM

    def test_hard_gets_todo(self) -> None:
        """HARD calls have no Narwhals equivalent and get a TODO comment."""
        source = _dedent("""\
            def process(df):
                return df.apply(lambda x: x * 2)
        """)
        result, findings = transform_source(source)
        assert "# TODO(nw-migrate):" in result
        assert findings[0].rule.difficulty == Difficulty.HARD

    def test_medium_no_decorator(self) -> None:
        """Functions with only MEDIUM/HARD calls don't get @nw.narwhalify."""
        source = _dedent("""\
            def process(df):
                return df.fillna(0)
        """)
        result, _ = transform_source(source)
        assert "@nw.narwhalify" not in result


class TestNoOp:
    def test_no_pandas(self) -> None:
        """Files without any Pandas calls should pass through unchanged."""
        source = _dedent("""\
            def add(a, b):
                return a + b
        """)
        result, findings = transform_source(source)
        assert result == source
        assert len(findings) == 0


class TestChainedCalls:
    def test_chained(self) -> None:
        """Each call in a chain is converted independently."""
        source = _dedent("""\
            def process(df):
                return df.sort_values('a').drop_duplicates()
        """)
        result, findings = transform_source(source)
        assert "df.sort('a').unique()" in result
        assert len(findings) == 2


class TestNonAttributeCalls:
    def test_plain_function_call_ignored(self) -> None:
        """Built-in calls like len(df) should not be mistaken for Pandas methods."""
        source = _dedent("""\
            def process(df):
                result = len(df)
                return df.sort_values('name')
        """)
        result, findings = transform_source(source)
        assert "len(df)" in result
        assert len(findings) == 1

    def test_module_level_conversion(self) -> None:
        """Pandas calls outside any function are converted but don't get a decorator."""
        source = _dedent("""\
            result = df.sort_values('name')
        """)
        result, findings = transform_source(source)
        assert "df.sort('name')" in result
        assert "@nw.narwhalify" not in result
        assert len(findings) == 1


class TestSubscriptDuringTransform:
    """Verify that non-list subscripts survive the transformation pass unchanged.

    These tests combine a Pandas method call (to trigger the transformer) with
    various subscript patterns that should not be touched.
    """

    def test_non_list_subscript_preserved(self) -> None:
        """Single-key subscripts like df['col'] must not be rewritten to .select()."""
        source = _dedent("""\
            def process(df):
                x = df['col1']
                return df.sort_values('name')
        """)
        result, _ = transform_source(source)
        assert "df['col1']" in result
        assert "df.sort('name')" in result

    def test_multi_slice_subscript_preserved(self) -> None:
        """Multi-dimensional subscripts like arr[1:2, 3:4] should be left alone."""
        source = _dedent("""\
            def process(df, arr):
                x = arr[1:2, 3:4]
                return df.sort_values('name')
        """)
        result, _ = transform_source(source)
        assert "df.sort('name')" in result


class TestHelpers:
    """Direct tests for edge cases in internal helper functions."""

    def test_is_narwhalify_decorator_unknown_type(self) -> None:
        """A decorator that's not Name, Attribute, or Call should return False."""
        import libcst as cst

        from nw_migrate.transformer import _is_narwhalify_decorator

        dec = cst.Decorator(decorator=cst.Integer("1"))
        assert not _is_narwhalify_decorator(dec)

    def test_transform_args_simple_rename(self) -> None:
        """An ArgTransform with just a new_name (no invert) should rename the kwarg."""
        import libcst as cst

        from nw_migrate.rules import ArgTransform
        from nw_migrate.transformer import _transform_args

        arg = cst.Arg(
            keyword=cst.Name("old_name"),
            value=cst.Name("val"),
        )
        transforms = (ArgTransform(old_name="old_name", new_name="new_name"),)
        result = _transform_args([arg], transforms)
        assert result[0].keyword is not None
        assert result[0].keyword.value == "new_name"
