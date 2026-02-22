from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Difficulty(Enum):
    """How hard it is to mechanically convert a Pandas call to Narwhals.

    EASY methods have a direct 1:1 mapping and can be auto-converted with
    confidence. MEDIUM methods exist in Narwhals but require switching to
    the expression API, so they need manual review. HARD methods have no
    Narwhals equivalent at all and require a fundamentally different approach.
    """

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass(frozen=True)
class ArgTransform:
    """Describes how to transform a single keyword argument during conversion.

    For example, Pandas sort_values() takes ascending=True, but Narwhals
    sort() uses descending=False. This is represented as an ArgTransform
    with old_name="ascending", new_name="descending", and invert_bool=True.

    When new_name is None, the kwarg is unwrapped to a positional argument.
    This handles cases like drop(columns=['a']) becoming drop('a'), where
    the Narwhals API takes the same value but as a positional arg.
    """

    old_name: str
    new_name: str | None = None
    invert_bool: bool = False


@dataclass(frozen=True)
class Rule:
    """Maps a single Pandas method to its Narwhals equivalent.

    Each rule captures the method name on both sides, the conversion
    difficulty, any argument transformations needed, and a human-readable
    description used in CLI output and TODO comments.
    """

    pandas_method: str
    narwhals_method: str
    difficulty: Difficulty
    arg_transforms: tuple[ArgTransform, ...] = ()
    description: str = ""


# Global registry of all conversion rules, keyed by Pandas method name.
# Populated at module load time by _register() calls below.
RULES: dict[str, Rule] = {}


def _register(*rules: Rule) -> None:
    """Add one or more conversion rules to the global RULES registry."""
    for rule in rules:
        RULES[rule.pandas_method] = rule


# These Pandas methods have direct Narwhals equivalents and can be safely
# auto-converted. The transformer renames the method and adjusts arguments
# according to each rule's arg_transforms.

_register(
    Rule(
        pandas_method="sort_values",
        narwhals_method="sort",
        difficulty=Difficulty.EASY,
        arg_transforms=(
            ArgTransform(old_name="by", new_name=None),
            ArgTransform(old_name="ascending", new_name="descending", invert_bool=True),
        ),
        description="sort_values() -> sort()",
    ),
    Rule(
        pandas_method="groupby",
        narwhals_method="group_by",
        difficulty=Difficulty.EASY,
        description="groupby() -> group_by()",
    ),
    Rule(
        pandas_method="merge",
        narwhals_method="join",
        difficulty=Difficulty.EASY,
        description="merge() -> join()",
    ),
    Rule(
        pandas_method="drop_duplicates",
        narwhals_method="unique",
        difficulty=Difficulty.EASY,
        description="drop_duplicates() -> unique()",
    ),
    Rule(
        pandas_method="drop",
        narwhals_method="drop",
        difficulty=Difficulty.EASY,
        arg_transforms=(ArgTransform(old_name="columns", new_name=None),),
        description="drop(columns=...) -> drop(...)",
    ),
    Rule(
        pandas_method="rename",
        narwhals_method="rename",
        difficulty=Difficulty.EASY,
        arg_transforms=(ArgTransform(old_name="columns", new_name=None),),
        description="rename(columns=...) -> rename(...)",
    ),
)

# These methods exist in Narwhals but require switching from Pandas' method-call
# style to Narwhals' expression-based API. For example, df.fillna(0) becomes
# df.with_columns(nw.col('x').fill_null(0)). Because the transformation isn't
# mechanical (you need to know which columns to target), we flag them with a
# TODO comment instead of auto-converting.

_register(
    Rule(
        pandas_method="fillna",
        narwhals_method="fill_null",
        difficulty=Difficulty.MEDIUM,
        description="fillna() -> with_columns(nw.col(...).fill_null()) -- needs manual review",
    ),
    Rule(
        pandas_method="isna",
        narwhals_method="is_null",
        difficulty=Difficulty.MEDIUM,
        description="isna() -> expression-based is_null() -- needs manual review",
    ),
    Rule(
        pandas_method="notna",
        narwhals_method="is_not_null",
        difficulty=Difficulty.MEDIUM,
        description="notna() -> expression-based is_not_null() -- needs manual review",
    ),
    Rule(
        pandas_method="astype",
        narwhals_method="cast",
        difficulty=Difficulty.MEDIUM,
        description="astype() -> .cast() expression -- needs manual review",
    ),
    Rule(
        pandas_method="melt",
        narwhals_method="unpivot",
        difficulty=Difficulty.MEDIUM,
        description="melt() -> unpivot() -- needs manual review",
    ),
    Rule(
        pandas_method="value_counts",
        narwhals_method="value_counts",
        difficulty=Difficulty.MEDIUM,
        description="value_counts() -> expression-based -- needs manual review",
    ),
)

# These Pandas methods have no Narwhals equivalent. They rely on row-level
# iteration or string-based queries that don't translate to Narwhals' lazy,
# expression-oriented model. They get flagged in the output so the developer
# knows they need a fundamentally different approach.

_register(
    Rule(
        pandas_method="apply",
        narwhals_method="",
        difficulty=Difficulty.HARD,
        description="apply() has no direct Narwhals equivalent",
    ),
    Rule(
        pandas_method="iterrows",
        narwhals_method="",
        difficulty=Difficulty.HARD,
        description="iterrows() has no Narwhals equivalent",
    ),
    Rule(
        pandas_method="itertuples",
        narwhals_method="",
        difficulty=Difficulty.HARD,
        description="itertuples() has no Narwhals equivalent",
    ),
    Rule(
        pandas_method="query",
        narwhals_method="",
        difficulty=Difficulty.HARD,
        description="query() has no Narwhals equivalent -- use filter()",
    ),
    Rule(
        pandas_method="select_dtypes",
        narwhals_method="",
        difficulty=Difficulty.HARD,
        description="select_dtypes() has no Narwhals equivalent",
    ),
    Rule(
        pandas_method="applymap",
        narwhals_method="",
        difficulty=Difficulty.HARD,
        description="applymap() has no Narwhals equivalent",
    ),
)
