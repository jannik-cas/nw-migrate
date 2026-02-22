from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from nw_migrate.cli import main


def _write_file(tmp_path: Path, content: str) -> Path:
    f = tmp_path / "test.py"
    f.write_text(content)
    return f


class TestCheck:
    def test_reports_findings(self, tmp_path: Path) -> None:
        """Detected Pandas calls should be printed with difficulty tag and exit 1."""
        f = _write_file(tmp_path, "def p(df):\n    return df.sort_values('a')\n")
        runner = CliRunner()
        result = runner.invoke(main, ["check", str(f)])
        assert result.exit_code == 1
        assert "[EASY]" in result.output
        assert "sort_values" in result.output

    def test_clean_file(self, tmp_path: Path) -> None:
        """A file with no Pandas calls should exit 0 with a reassuring message."""
        f = _write_file(tmp_path, "def add(a, b):\n    return a + b\n")
        runner = CliRunner()
        result = runner.invoke(main, ["check", str(f)])
        assert result.exit_code == 0
        assert "No Pandas usages found" in result.output

    def test_quiet_mode(self, tmp_path: Path) -> None:
        """Quiet mode suppresses per-finding output, only showing the count."""
        f = _write_file(tmp_path, "def p(df):\n    return df.sort_values('a')\n")
        runner = CliRunner()
        result = runner.invoke(main, ["check", "--quiet", str(f)])
        assert result.exit_code == 1
        assert "[EASY]" not in result.output
        assert "Found 1" in result.output

    def test_directory(self, tmp_path: Path) -> None:
        """Passing a directory should scan all .py files recursively, skip others."""
        (tmp_path / "a.py").write_text("def p(df):\n    return df.groupby('x')\n")
        (tmp_path / "b.txt").write_text("not python")
        runner = CliRunner()
        result = runner.invoke(main, ["check", str(tmp_path)])
        assert result.exit_code == 1
        assert "groupby" in result.output


class TestConvert:
    def test_in_place(self, tmp_path: Path) -> None:
        """Default convert writes the transformed code back to the file."""
        f = _write_file(tmp_path, "def p(df):\n    return df.sort_values('a')\n")
        runner = CliRunner()
        result = runner.invoke(main, ["convert", str(f)])
        assert result.exit_code == 0
        assert "1 converted" in result.output
        converted = f.read_text()
        assert "df.sort('a')" in converted

    def test_dry_run(self, tmp_path: Path) -> None:
        """Dry-run prints the converted output but leaves the original file intact."""
        original = "def p(df):\n    return df.sort_values('a')\n"
        f = _write_file(tmp_path, original)
        runner = CliRunner()
        result = runner.invoke(main, ["convert", "--dry-run", str(f)])
        assert result.exit_code == 0
        assert "df.sort('a')" in result.output
        assert f.read_text() == original

    def test_diff(self, tmp_path: Path) -> None:
        """Diff mode shows a unified diff of what would change."""
        f = _write_file(tmp_path, "def p(df):\n    return df.sort_values('a')\n")
        runner = CliRunner()
        result = runner.invoke(main, ["convert", "--diff", str(f)])
        assert result.exit_code == 0
        assert "---" in result.output
        assert "+++" in result.output
        assert "-    return df.sort_values" in result.output
        assert "+    return df.sort" in result.output

    def test_no_changes_skipped(self, tmp_path: Path) -> None:
        """Files with nothing to convert should produce no output at all."""
        f = _write_file(tmp_path, "def add(a, b):\n    return a + b\n")
        runner = CliRunner()
        result = runner.invoke(main, ["convert", str(f)])
        assert result.exit_code == 0
        assert result.output == ""

    def test_flagged_count(self, tmp_path: Path) -> None:
        """When a file has both EASY and MEDIUM calls, report both counts."""
        f = _write_file(
            tmp_path,
            "def p(df):\n    df.sort_values('a')\n    return df.fillna(0)\n",
        )
        runner = CliRunner()
        result = runner.invoke(main, ["convert", str(f)])
        assert "1 converted" in result.output
        assert "1 flagged" in result.output


class TestVersion:
    def test_version(self) -> None:
        """--version should print the installed package version."""
        from importlib.metadata import version

        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert version("nw-migrate") in result.output
