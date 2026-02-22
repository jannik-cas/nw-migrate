from __future__ import annotations

import difflib
import sys
from pathlib import Path

import click

from nw_migrate.rules import Difficulty
from nw_migrate.transformer import transform_source


@click.group()
@click.version_option(package_name="nw-migrate")
def main() -> None:
    """Convert Pandas code to Narwhals."""


@main.command()
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option("--quiet", "-q", is_flag=True, help="Only show summary counts")
def check(paths: tuple[Path, ...], quiet: bool) -> None:
    """Report Pandas usages that can be converted (no changes made)."""
    total = 0
    for path in _resolve_python_files(paths):
        source = path.read_text()
        _, findings = transform_source(source)
        total += len(findings)
        if not quiet:
            for f in findings:
                tag = f.rule.difficulty.value.upper()
                click.echo(f"{path}:{f.line}:{f.col} [{tag}] {f.rule.description}")

    if total > 0:
        click.echo(f"\nFound {total} convertible Pandas usage(s).")
        sys.exit(1)
    else:
        click.echo("No Pandas usages found.")


@main.command()
@click.argument("paths", nargs=-1, type=click.Path(exists=True, path_type=Path))
@click.option("--dry-run", is_flag=True, help="Print output instead of writing")
@click.option("--diff", is_flag=True, help="Show diff instead of writing")
def convert(paths: tuple[Path, ...], dry_run: bool, diff: bool) -> None:
    """Convert Pandas code to Narwhals."""
    for path in _resolve_python_files(paths):
        source = path.read_text()
        output, findings = transform_source(source)

        if source == output:
            continue

        if dry_run:
            click.echo(output)
        elif diff:
            d = difflib.unified_diff(
                source.splitlines(keepends=True),
                output.splitlines(keepends=True),
                fromfile=str(path),
                tofile=str(path),
            )
            click.echo("".join(d), nl=False)
        else:
            path.write_text(output)
            easy = sum(1 for f in findings if f.rule.difficulty == Difficulty.EASY)
            flagged = sum(1 for f in findings if f.rule.difficulty != Difficulty.EASY)
            click.echo(f"{path}: {easy} converted, {flagged} flagged for review")


def _resolve_python_files(paths: tuple[Path, ...]) -> list[Path]:
    result: list[Path] = []
    for p in paths:
        if p.is_dir():
            result.extend(sorted(p.rglob("*.py")))
        elif p.suffix == ".py":
            result.append(p)
    return result
