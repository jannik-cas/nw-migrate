from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

from nw_migrate.rules import RULES, ArgTransform, Difficulty, Rule


@dataclass
class Finding:
    """A detected Pandas usage that can/should be converted."""

    line: int
    col: int
    pandas_method: str
    rule: Rule
    enclosing_function: str | None


# ---------------------------------------------------------------------------
# Pass 1: Collector — find all Pandas calls matching rules
# ---------------------------------------------------------------------------


class PandasCallCollector(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self) -> None:
        self.findings: list[Finding] = []
        self.functions_needing_decorator: set[str] = set()
        self._function_stack: list[str] = []

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        self._function_stack.append(node.name.value)
        return True

    def leave_FunctionDef(self, original_node: cst.FunctionDef) -> None:
        self._function_stack.pop()

    def visit_Call(self, node: cst.Call) -> bool:
        if not isinstance(node.func, cst.Attribute):
            return True

        method_name = node.func.attr.value
        rule = RULES.get(method_name)
        if rule is None:
            return True

        pos = self.get_metadata(PositionProvider, node)
        enclosing = self._function_stack[-1] if self._function_stack else None

        self.findings.append(
            Finding(
                line=pos.start.line,
                col=pos.start.column,
                pandas_method=method_name,
                rule=rule,
                enclosing_function=enclosing,
            )
        )

        if rule.difficulty == Difficulty.EASY and enclosing is not None:
            self.functions_needing_decorator.add(enclosing)

        return True

    def visit_Subscript(self, node: cst.Subscript) -> bool:
        """Match df[['col1', 'col2']] — subscript with a List value."""
        if not _is_list_subscript(node):
            return True

        pos = self.get_metadata(PositionProvider, node)
        enclosing = self._function_stack[-1] if self._function_stack else None

        self.findings.append(
            Finding(
                line=pos.start.line,
                col=pos.start.column,
                pandas_method="__getitem__",
                rule=Rule(
                    pandas_method="__getitem__",
                    narwhals_method="select",
                    difficulty=Difficulty.EASY,
                    description="df[['a','b']] -> df.select(['a','b'])",
                ),
                enclosing_function=enclosing,
            )
        )

        if enclosing is not None:
            self.functions_needing_decorator.add(enclosing)

        return True


# ---------------------------------------------------------------------------
# Pass 2: Transformer — apply conversions
# ---------------------------------------------------------------------------


class NarwhalsTransformer(cst.CSTTransformer):
    def __init__(self, functions_needing_decorator: set[str]) -> None:
        self.functions_needing_decorator = functions_needing_decorator
        self.conversions_made: int = 0
        self.needs_import: bool = False
        self.todos: list[tuple[int, str]] = []
        self._pos_map: dict[int, int] = {}

    def leave_FunctionDef(
        self,
        original_node: cst.FunctionDef,
        updated_node: cst.FunctionDef,
    ) -> cst.FunctionDef:
        name = updated_node.name.value
        if name not in self.functions_needing_decorator:
            return updated_node

        for dec in updated_node.decorators:
            if _is_narwhalify_decorator(dec):
                return updated_node

        new_decorator = cst.Decorator(
            decorator=cst.Attribute(
                value=cst.Name("nw"),
                attr=cst.Name("narwhalify"),
            ),
            leading_lines=[cst.EmptyLine()],
        )

        self.needs_import = True
        return updated_node.with_changes(
            decorators=[new_decorator, *updated_node.decorators],
        )

    def leave_Call(
        self,
        original_node: cst.Call,
        updated_node: cst.Call,
    ) -> cst.BaseExpression:
        if not isinstance(updated_node.func, cst.Attribute):
            return updated_node

        method_name = updated_node.func.attr.value
        rule = RULES.get(method_name)
        if rule is None:
            return updated_node

        if rule.difficulty in (Difficulty.MEDIUM, Difficulty.HARD):
            return updated_node

        new_func = updated_node.func.with_changes(
            attr=cst.Name(rule.narwhals_method),
        )
        new_args = _transform_args(updated_node.args, rule.arg_transforms)
        self.conversions_made += 1
        self.needs_import = True

        return updated_node.with_changes(func=new_func, args=new_args)

    def leave_Subscript(
        self,
        original_node: cst.Subscript,
        updated_node: cst.Subscript,
    ) -> cst.BaseExpression:
        if not _is_list_subscript(updated_node):
            return updated_node

        index_slice = updated_node.slice[0].slice
        assert isinstance(index_slice, cst.Index)
        list_node = index_slice.value

        self.conversions_made += 1
        self.needs_import = True

        return cst.Call(
            func=cst.Attribute(
                value=updated_node.value,
                attr=cst.Name("select"),
            ),
            args=[cst.Arg(value=list_node)],
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_narwhalify_decorator(dec: cst.Decorator) -> bool:
    expr = dec.decorator
    if isinstance(expr, cst.Attribute):
        return (
            isinstance(expr.value, cst.Name)
            and expr.value.value == "nw"
            and expr.attr.value == "narwhalify"
        )
    if isinstance(expr, cst.Name):
        return expr.value == "narwhalify"
    if isinstance(expr, cst.Call):
        return _is_narwhalify_decorator(cst.Decorator(decorator=expr.func))
    return False


def _is_list_subscript(node: cst.Subscript) -> bool:
    if not isinstance(node.slice, (list, tuple)) or len(node.slice) != 1:
        return False
    slice_el = node.slice[0]
    if not isinstance(slice_el.slice, cst.Index):
        return False
    return isinstance(slice_el.slice.value, cst.List)


def _transform_args(
    args: Sequence[cst.Arg],
    transforms: tuple[ArgTransform, ...],
) -> tuple[cst.Arg, ...]:
    if not transforms:
        return tuple(args)

    transform_map = {t.old_name: t for t in transforms}
    new_args: list[cst.Arg] = []

    for arg in args:
        if arg.keyword is None:
            new_args.append(arg)
            continue

        kwarg_name = arg.keyword.value
        transform = transform_map.get(kwarg_name)

        if transform is None:
            new_args.append(arg)
            continue

        if transform.invert_bool:
            inverted = _invert_bool_expr(arg.value)
            new_kw = cst.Name(transform.new_name) if transform.new_name else None
            new_args.append(
                arg.with_changes(
                    keyword=new_kw,
                    value=inverted,
                    equal=cst.MaybeSentinel.DEFAULT if new_kw is None else arg.equal,
                )
            )
        elif transform.new_name is None:
            new_args.append(
                arg.with_changes(
                    keyword=None,
                    equal=cst.MaybeSentinel.DEFAULT,
                )
            )
        else:
            new_args.append(arg.with_changes(keyword=cst.Name(transform.new_name)))

    return tuple(new_args)


def _invert_bool_expr(node: cst.BaseExpression) -> cst.BaseExpression:
    if isinstance(node, cst.Name):
        if node.value == "True":
            return node.with_changes(value="False")
        if node.value == "False":
            return node.with_changes(value="True")
    return cst.UnaryOperation(
        operator=cst.Not(whitespace_after=cst.SimpleWhitespace(" ")),
        expression=node,
    )


# ---------------------------------------------------------------------------
# Import injection
# ---------------------------------------------------------------------------


def _has_narwhals_import(tree: cst.Module) -> bool:
    for stmt in tree.body:
        if isinstance(stmt, cst.SimpleStatementLine):
            for item in stmt.body:
                if isinstance(item, cst.Import) and isinstance(
                    item.names, (list, tuple)
                ):
                    for alias in item.names:
                        if (
                            isinstance(alias.name, cst.Name)
                            and alias.name.value == "narwhals"
                        ):
                            return True
    return False


def _find_last_import_index(
    body: Sequence[cst.SimpleStatementLine | cst.BaseCompoundStatement],
) -> int:
    last_idx = -1
    for i, stmt in enumerate(body):
        if isinstance(stmt, cst.SimpleStatementLine):
            for item in stmt.body:
                if isinstance(item, (cst.Import, cst.ImportFrom)):
                    last_idx = i
                    break
    return last_idx


def add_narwhals_import(tree: cst.Module) -> cst.Module:
    if _has_narwhals_import(tree):
        return tree

    import_stmt = cst.SimpleStatementLine(
        body=[
            cst.Import(
                names=[
                    cst.ImportAlias(
                        name=cst.Name("narwhals"),
                        asname=cst.AsName(
                            whitespace_before_as=cst.SimpleWhitespace(" "),
                            whitespace_after_as=cst.SimpleWhitespace(" "),
                            name=cst.Name("nw"),
                        ),
                    ),
                ],
            ),
        ],
        leading_lines=[cst.EmptyLine()],
    )

    insert_idx = _find_last_import_index(tree.body) + 1
    new_body = list(tree.body)
    new_body.insert(insert_idx, import_stmt)
    return tree.with_changes(body=new_body)


# ---------------------------------------------------------------------------
# TODO comment injection (text-level post-processing)
# ---------------------------------------------------------------------------


def inject_todo_comments(source: str, todos: list[tuple[int, str]]) -> str:
    if not todos:
        return source
    lines = source.splitlines(keepends=True)
    for line_no, comment in sorted(todos, reverse=True):
        idx = line_no - 1
        if idx < len(lines):
            stripped = lines[idx].rstrip("\n").rstrip("\r")
            lines[idx] = f"{stripped}  {comment}\n"
    return "".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def transform_source(source: str) -> tuple[str, list[Finding]]:
    """Transform a source string. Returns (output, findings)."""
    tree = cst.parse_module(source)
    wrapper = MetadataWrapper(tree)

    # Pass 1: collect findings
    collector = PandasCallCollector()
    wrapper.visit(collector)

    if not collector.findings:
        return source, []

    # Pass 2: transform
    transformer = NarwhalsTransformer(
        functions_needing_decorator=collector.functions_needing_decorator,
    )
    new_tree = tree.visit(transformer)

    # Add import if needed
    if transformer.needs_import:
        new_tree = add_narwhals_import(new_tree)

    output = new_tree.code

    # Re-collect on transformed code to get correct line numbers for TODOs
    new_wrapper = MetadataWrapper(cst.parse_module(output))
    post_collector = PandasCallCollector()
    new_wrapper.visit(post_collector)

    todos = [
        (f.line, f"# TODO(nw-migrate): {f.rule.description}")
        for f in post_collector.findings
        if f.rule.difficulty in (Difficulty.MEDIUM, Difficulty.HARD)
    ]
    output = inject_todo_comments(output, todos)

    return output, collector.findings
