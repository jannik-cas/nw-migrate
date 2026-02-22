from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

from nw_migrate.rules import RULES, ArgTransform, Difficulty, Rule


@dataclass
class Finding:
    """Represents a single detected Pandas API call in the source code.

    Each finding maps to one method call (or subscript pattern) that matched
    a known conversion rule. The enclosing_function field tracks which function
    the call lives in, so we know where to attach the @nw.narwhalify decorator.
    Findings at module level (outside any function) have enclosing_function=None.
    """

    line: int
    col: int
    pandas_method: str
    rule: Rule
    enclosing_function: str | None


class PandasCallCollector(cst.CSTVisitor):
    """First pass over the CST: walks the tree and records every Pandas call
    that matches one of our conversion rules.

    This visitor does not modify anything. It collects two things:
      - findings: the full list of detected Pandas usages (with positions)
      - functions_needing_decorator: names of functions that contain at least
        one EASY-level conversion, meaning they should get @nw.narwhalify
    """

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self) -> None:
        self.findings: list[Finding] = []
        self.functions_needing_decorator: set[str] = set()
        # We maintain a stack of function names so we can handle nested
        # function definitions and always know which function we're inside.
        self._function_stack: list[str] = []

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        self._function_stack.append(node.name.value)
        return True

    def leave_FunctionDef(self, original_node: cst.FunctionDef) -> None:
        self._function_stack.pop()

    def visit_Call(self, node: cst.Call) -> bool:
        """Check if a method call matches a known Pandas API we want to convert.

        We only look at attribute calls (obj.method()), not plain function calls
        like len(df) or print(). This avoids false positives on built-ins that
        happen to share a name with a Pandas method.
        """
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

        # Only functions with auto-convertible (EASY) calls get the decorator.
        # MEDIUM/HARD calls just get TODO comments and don't change signatures.
        if rule.difficulty == Difficulty.EASY and enclosing is not None:
            self.functions_needing_decorator.add(enclosing)

        return True

    def visit_Subscript(self, node: cst.Subscript) -> bool:
        """Detect column selection via df[['col1', 'col2']] syntax.

        In Pandas, passing a list of column names to __getitem__ selects those
        columns. The Narwhals equivalent is df.select(['col1', 'col2']).
        We only match subscripts where the index is a literal list — single
        string keys like df['col'] or slices like df[0:5] are left alone.
        """
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


class NarwhalsTransformer(cst.CSTTransformer):
    """Second pass over the CST: applies the actual code transformations.

    This transformer rewrites EASY-level Pandas calls to their Narwhals
    equivalents (renaming methods, transforming arguments) and attaches the
    @nw.narwhalify decorator to functions that were modified. MEDIUM and HARD
    calls are intentionally left untouched here — they only get TODO comments
    injected as a text post-processing step later.
    """

    def __init__(self, functions_needing_decorator: set[str]) -> None:
        self.functions_needing_decorator = functions_needing_decorator
        self.conversions_made: int = 0
        self.needs_import: bool = False

    def leave_FunctionDef(
        self,
        original_node: cst.FunctionDef,
        updated_node: cst.FunctionDef,
    ) -> cst.FunctionDef:
        """Add @nw.narwhalify to functions that received EASY conversions.

        Before adding, we check if the function already has a narwhalify
        decorator in any of its recognized forms (@nw.narwhalify, @narwhalify,
        or @nw.narwhalify()) to avoid duplicating it.
        """
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
        """Rewrite EASY Pandas method calls to their Narwhals equivalents.

        For example, df.sort_values('name', ascending=False) becomes
        df.sort('name', descending=True). MEDIUM/HARD calls pass through
        unchanged — they'll get TODO comments in the post-processing step.
        """
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
        """Rewrite df[['col1', 'col2']] to df.select(['col1', 'col2']).

        Non-list subscripts (single key access, slices, multi-dimensional
        indexing) pass through without modification.
        """
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


def _is_narwhalify_decorator(dec: cst.Decorator) -> bool:
    """Check whether a decorator is any form of narwhalify.

    Recognizes three patterns that users might already have in their code:
      - @nw.narwhalify        (Attribute form)
      - @narwhalify           (bare Name, from direct import)
      - @nw.narwhalify()      (Call form, with or without arguments)
    """
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
    """Return True if the subscript is df[['a', 'b']] style (list of columns).

    We require exactly one slice element whose value is a literal List node.
    This excludes single-key access (df['col']), slices (df[0:5]), and
    multi-dimensional indexing (arr[1:2, 3:4]).
    """
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
    """Apply argument transformations defined by a conversion rule.

    Handles three kinds of argument changes:
      - Invert a boolean kwarg (ascending=True -> descending=False). For
        literal True/False we swap the value; for variables we wrap in `not`.
      - Unwrap a kwarg to positional (by='name' -> just 'name'), used when
        Narwhals takes the same value as a positional arg instead of a kwarg.
      - Rename a kwarg (old_name='x' -> new_name='x'), for cases where only
        the parameter name changed between Pandas and Narwhals.

    Arguments not mentioned in the transforms pass through unchanged.
    """
    if not transforms:
        return tuple(args)

    transform_map = {t.old_name: t for t in transforms}
    new_args: list[cst.Arg] = []

    for arg in args:
        # Positional args are never subject to kwarg transforms
        if arg.keyword is None:
            new_args.append(arg)
            continue

        kwarg_name = arg.keyword.value
        transform = transform_map.get(kwarg_name)

        # Unknown kwargs (e.g. key=str.lower on sort_values) are kept as-is
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
            # Unwrap to positional: drop the keyword entirely
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
    """Flip a boolean expression: True->False, False->True, var->`not var`.

    Used for the ascending->descending conversion. For literal booleans we
    can produce clean output (descending=True). For arbitrary expressions
    like variables we fall back to wrapping with `not`.
    """
    if isinstance(node, cst.Name):
        if node.value == "True":
            return node.with_changes(value="False")
        if node.value == "False":
            return node.with_changes(value="True")
    return cst.UnaryOperation(
        operator=cst.Not(whitespace_after=cst.SimpleWhitespace(" ")),
        expression=node,
    )


def _has_narwhals_import(tree: cst.Module) -> bool:
    """Check if the module already contains 'import narwhals (as ...)'.

    Walks top-level statements looking for an import of the narwhals package.
    This prevents adding a duplicate import when the user already has one.
    """
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
    """Find the position of the last import statement in the module body.

    Returns the index of the last import/from-import line, or -1 if there
    are no imports. We insert the narwhals import right after this position
    so it groups naturally with the existing imports.
    """
    last_idx = -1
    for i, stmt in enumerate(body):
        if isinstance(stmt, cst.SimpleStatementLine):
            for item in stmt.body:
                if isinstance(item, (cst.Import, cst.ImportFrom)):
                    last_idx = i
                    break
    return last_idx


def add_narwhals_import(tree: cst.Module) -> cst.Module:
    """Insert 'import narwhals as nw' into the module if not already present.

    Places the import after the last existing import statement, or at the
    very top of the file if there are no other imports.
    """
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


def inject_todo_comments(source: str, todos: list[tuple[int, str]]) -> str:
    """Append TODO comments to specific lines in the source text.

    This is a text-level post-processing step (not CST-based) because libcst
    doesn't have a clean way to attach trailing comments to arbitrary nodes.
    We process lines in reverse order so that inserting characters on one line
    doesn't shift the line numbers of subsequent insertions.
    """
    if not todos:
        return source
    lines = source.splitlines(keepends=True)
    for line_no, comment in sorted(todos, reverse=True):
        idx = line_no - 1
        if idx < len(lines):
            stripped = lines[idx].rstrip("\n").rstrip("\r")
            lines[idx] = f"{stripped}  {comment}\n"
    return "".join(lines)


def transform_source(source: str) -> tuple[str, list[Finding]]:
    """Main entry point: transform a Python source string from Pandas to Narwhals.

    Runs a two-pass architecture over the concrete syntax tree:
      1. Collection pass — walks the tree read-only to find all Pandas method
         calls matching our rules, and identifies which functions need the
         @nw.narwhalify decorator.
      2. Transformation pass — rewrites EASY calls (rename methods, transform
         args), adds decorators, and injects the narwhals import.

    After transformation, we run the collector again on the output to find
    correct line numbers for MEDIUM/HARD calls (they shifted because we added
    imports and decorators), then inject TODO comments at those positions.

    Returns the transformed source code and the list of all findings from
    the original source.
    """
    tree = cst.parse_module(source)
    wrapper = MetadataWrapper(tree)

    collector = PandasCallCollector()
    wrapper.visit(collector)

    if not collector.findings:
        return source, []

    transformer = NarwhalsTransformer(
        functions_needing_decorator=collector.functions_needing_decorator,
    )
    new_tree = tree.visit(transformer)

    if transformer.needs_import:
        new_tree = add_narwhals_import(new_tree)

    output = new_tree.code

    # The transformation may have shifted line numbers (added imports,
    # decorators, etc.), so we re-collect on the transformed code to get
    # accurate positions for the TODO comments on MEDIUM/HARD calls.
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
