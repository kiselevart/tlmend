"""tlmend CLI entrypoint."""

from __future__ import annotations

import asyncio
import tomllib
from pathlib import Path
from typing import Annotated, Optional

import typer

app = typer.Typer(name="tlmend", add_completion=False)


def _load_config(project_dir: Path) -> dict:
    config_path = project_dir / "config.toml"
    if not config_path.exists():
        typer.echo(f"No config.toml found in {project_dir}", err=True)
        raise typer.Exit(1)
    return tomllib.loads(config_path.read_text(encoding="utf-8"))


def _find_source_files(project_dir: Path, fmt: str) -> list[Path]:
    source_dir = project_dir / "source"
    if not source_dir.is_dir():
        return []
    ext_map = {"txt": "*.txt", "epub": "*.epub", "markdown": "*.md", "html-dir": "*.html"}
    return sorted(source_dir.glob(ext_map.get(fmt, f"*.{fmt}")))


@app.command()
def run(
    project: Annotated[Path, typer.Argument(help="Path to project directory")],
    mode: Annotated[str, typer.Option(help="Pipeline mode: edit or review")] = "",
    policy: Annotated[str, typer.Option(help="Edit policy: trust, report, conservative")] = "",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    chapter_range: Annotated[Optional[str], typer.Option("--range", help="e.g. 1-50")] = None,
) -> None:
    """Run the correction pipeline on a project."""
    config = _load_config(project)
    pipeline_cfg = config.get("pipeline", {})
    project_cfg = config.get("project", {})

    effective_mode = mode or pipeline_cfg.get("mode", "edit")
    effective_policy = policy or pipeline_cfg.get("policy", "report")
    source_fmt = project_cfg.get("source_format", "txt")
    output_fmt = project_cfg.get("output_format", "txt")

    source_files = _find_source_files(project, source_fmt)
    if not source_files:
        typer.echo(
            f"No source files found in {project / 'source'}. "
            f"Place your .{source_fmt} files there (that directory is gitignored).",
            err=True,
        )
        raise typer.Exit(1)

    if dry_run:
        typer.echo(f"Dry-run: {len(source_files)} source file(s) found, no LLM calls.")
        raise typer.Exit(0)

    asyncio.run(_run_async(
        project=project,
        config=config,
        effective_mode=effective_mode,
        effective_policy=effective_policy,
        source_fmt=source_fmt,
        output_fmt=output_fmt,
        source_files=source_files,
        chapter_range=chapter_range,
    ))


async def _run_async(
    project: Path,
    config: dict,
    effective_mode: str,
    effective_policy: str,
    source_fmt: str,
    output_fmt: str,
    source_files: list[Path],
    chapter_range: str | None,
) -> None:
    from rich.console import Console
    from rich.table import Table
    from rich import box

    from tlmend.adapters.input.epub import EpubAdapter
    from tlmend.adapters.input.txt import TxtAdapter
    from tlmend.adapters.output.epub import EpubOutputAdapter
    from tlmend.adapters.output.txt import TxtOutputAdapter
    from tlmend.glossary.loader import load_glossary
    from tlmend.models import ChapterResult, ChapterStatus, RunConfig
    from tlmend.pipeline.orchestrator import CostCapExceeded, run_pipeline
    from tlmend.providers.factory import build_provider
    from tlmend.store.db import Store

    console = Console()

    in_adapters = {"txt": TxtAdapter(), "epub": EpubAdapter()}
    in_adapter = in_adapters.get(source_fmt)
    if in_adapter is None:
        raise typer.BadParameter(f"Unsupported source_format: {source_fmt!r}")

    if output_fmt == "epub":
        if not source_files:
            raise typer.BadParameter("EPUB output requires a source EPUB template.")
        out_adapter = EpubOutputAdapter(source_files[0])
    elif output_fmt == "txt":
        out_adapter = TxtOutputAdapter()
    else:
        raise typer.BadParameter(f"Unsupported output_format: {output_fmt!r}")

    pipeline_cfg = config.get("pipeline", {})

    run_cfg = RunConfig(
        project_dir=str(project),
        mode=effective_mode,  # type: ignore[arg-type]
        policy=effective_policy,  # type: ignore[arg-type]
        concurrency=int(pipeline_cfg.get("concurrency", 4)),
        cost_cap_usd=pipeline_cfg.get("cost_cap_usd"),
        prompt_version=str(pipeline_cfg.get("prompt_version", "v1")),
    )

    editor = build_provider(config.get("editor", {}))
    reviewer = build_provider(config.get("reviewer", {})) if effective_mode == "review" else None

    glossary_path = project / config.get("glossary", {}).get("path", "glossary.json")
    glossary_terms = load_glossary(glossary_path) if glossary_path.exists() else []

    chapters = []
    for src in source_files:
        chapters.extend(in_adapter.load(src))

    if chapter_range:
        lo, _, hi = chapter_range.partition("-")
        start, end = int(lo) - 1, int(hi) if hi else len(chapters)
        chapters = chapters[start:end]

    console.print(f"[bold]{project.name}[/bold]  mode=[cyan]{effective_mode}[/cyan]  policy=[cyan]{effective_policy}[/cyan]  chapters=[cyan]{len(chapters)}[/cyan]")
    console.print()

    chapter_results: list[ChapterResult] = []

    def on_done(result: ChapterResult) -> None:
        chapter_results.append(result)
        ok = result.status == ChapterStatus.ASSEMBLED
        icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
        title = result.title[:40]
        tokens = f"{result.prompt_tokens}↑ {result.completion_tokens}↓"
        cost = f"${result.cost_usd:.6f}"
        hunks = f"{result.hunks_mechanical}mech {result.hunks_substantive}sub"
        retries = f"  [yellow](attempt {result.attempts})[/yellow]" if result.attempts > 1 else ""
        if ok:
            console.print(f"  {icon}  [bold]{title}[/bold]  {tokens}  {cost}  {hunks}{retries}")
        else:
            errors = "; ".join(result.validation_errors)
            console.print(f"  {icon}  [bold]{title}[/bold]  {tokens}  {cost}  [red]flagged[/red]: {errors}{retries}")

    store_path = project / "run.sqlite"
    async with Store(store_path) as store:
        try:
            assembled = await run_pipeline(
                chapters, editor, reviewer, run_cfg, store, glossary_terms,
                on_chapter_done=on_done,
            )
        except CostCapExceeded as exc:
            console.print(f"\n[red]Aborted:[/red] {exc}")
            raise typer.Exit(2)

    # summary
    console.print()
    total_tokens_in  = sum(r.prompt_tokens for r in chapter_results)
    total_tokens_out = sum(r.completion_tokens for r in chapter_results)
    total_cost = sum(r.cost_usd for r in chapter_results)
    n_assembled = sum(1 for r in chapter_results if r.status == ChapterStatus.ASSEMBLED)
    n_flagged   = sum(1 for r in chapter_results if r.status == ChapterStatus.FLAGGED)

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("assembled", f"[green]{n_assembled}[/green]")
    table.add_row("flagged",   f"[red]{n_flagged}[/red]" if n_flagged else "0")
    table.add_row("tokens",    f"{total_tokens_in}↑  {total_tokens_out}↓")
    table.add_row("cost",      f"${total_cost:.6f}")
    console.print(table)

    if assembled:
        output_dir = project / "output"
        output_dir.mkdir(exist_ok=True)
        ext = {"epub": ".epub", "txt": ".txt"}.get(output_fmt, ".txt")
        out_path = output_dir / f"output{ext}"
        out_adapter.write(assembled, out_path)
        console.print(f"[dim]output → {out_path}[/dim]")


@app.command()
def estimate(
    project: Annotated[Path, typer.Argument(help="Path to project directory")],
    chapter_range: Annotated[Optional[str], typer.Option("--range")] = None,
) -> None:
    """Estimate token cost without running the pipeline."""
    _load_config(project)
    typer.echo(f"Cost estimate for {project} (range={chapter_range or 'all'})")
    typer.echo("Estimator not yet implemented.")


if __name__ == "__main__":
    app()
