"""CLI handler for `bob spec-trace` — prints an AC with its provenance spans."""

from __future__ import annotations

import click

from bob.spec.provenance import trace_ac_provenance


def spec_trace(target: str, db_path: str | None) -> None:
    """Print an AC alongside its source-intent provenance spans.

    TARGET is <feature_id>:<ac_index> (e.g. abc123:2 for the third AC).
    """
    if ":" not in target:
        click.echo(
            "Error: TARGET must be <feature_id>:<ac_index> (e.g. abc123:2)",
            err=True,
        )
        raise SystemExit(1)

    feature_id, _, raw_index = target.partition(":")
    try:
        ac_index = int(raw_index)
    except ValueError:
        click.echo(f"Error: ac_index must be an integer, got {raw_index!r}", err=True)
        raise SystemExit(1)

    try:
        result = trace_ac_provenance(feature_id, ac_index, db_path=db_path)
    except KeyError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
    except IndexError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)

    click.echo(f"Feature : {result['feature_id']}")
    click.echo(f"AC [{result['ac_index']}]: {result['ac']}")
    click.echo("")
    if result["spans"]:
        click.echo("Provenance spans:")
        for span in result["spans"]:
            click.echo(f"  span={span['start']}:{span['end']}")
    else:
        click.echo("Provenance spans: (none — AC could not be traced to a source span)")
