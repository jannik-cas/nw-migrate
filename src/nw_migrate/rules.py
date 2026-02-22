from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Difficulty(Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass(frozen=True)
class ArgTransform:
    """Describes how to transform a single keyword argument."""

    old_name: str
    new_name: str | None = None  # None = unwrap to positional
    invert_bool: bool = False  # ascending=True -> descending=False


@dataclass(frozen=True)
class Rule:
    """A single Pandas -> Narwhals method conversion rule."""

    pandas_method: str
    narwhals_method: str
    difficulty: Difficulty
    arg_transforms: tuple[ArgTransform, ...] = ()
    description: str = ""


RULES: dict[str, Rule] = {}


def _register(*rules: Rule) -> None:
    for rule in rules:
        RULES[rule.pandas_method] = rule


# --- EASY: auto-convert ---

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

# --- MEDIUM: flag with TODO ---

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

# --- HARD: flag only, no conversion ---

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
