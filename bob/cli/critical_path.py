"""Critical path analysis CLI command implementation."""

import json as json_lib
from typing import Optional

import click

from bob.database.manager import DatabaseManager
from bob.orchestrator.critical_path import CriticalPathAnalyzer


def format_duration(hours: float) -> str:
    """Format duration in a human-readable way."""
    if hours < 1:
        minutes = int(hours * 60)
        return f"{minutes}m"
    elif hours < 24:
        return f"{hours:.1f}h"
    else:
        days = hours / 24
        return f"{days:.1f}d"


def format_confidence(confidence: str) -> str:
    """Format confidence level with color coding."""
    color_map = {
        "high": "green",
        "medium": "yellow", 
        "low": "red"
    }
    color = color_map.get(confidence, "white")
    return click.style(confidence, fg=color)


def display_text_analysis(analysis, verbose: bool = False) -> None:
    """Display critical path analysis in text format."""
    click.echo()
    click.echo(click.style("═" * 80, fg="cyan"))
    click.echo(click.style("  CRITICAL PATH ANALYSIS", fg="cyan", bold=True))
    click.echo(click.style("═" * 80, fg="cyan"))
    click.echo()
    
    if analysis.errors:
        click.echo(click.style("  ERRORS", fg="red", bold=True))
        for error in analysis.errors:
            click.echo(f"    ✗ {error}")
        click.echo()
        return
    
    # Overview
    click.echo(click.style("  OVERVIEW", fg="cyan", bold=True))
    click.echo(f"    Total Estimated Duration:    {format_duration(analysis.total_estimated_duration)}")
    click.echo(f"    Critical Path Length:        {len(analysis.critical_path)} tasks")
    click.echo(f"    Critical Path Duration:      {format_duration(analysis.critical_path_duration)}")
    
    if analysis.parallelism_groups:
        max_parallel = max(len(group.tasks) for group in analysis.parallelism_groups)
        click.echo(f"    Max Parallel Tasks:          {max_parallel} tasks")
    
    click.echo()
    
    # Critical Path
    click.echo(click.style("  CRITICAL PATH", fg="red", bold=True))
    if not analysis.critical_path:
        click.echo("    No critical path found.")
    else:
        for i, task in enumerate(analysis.critical_path, 1):
            estimate = analysis.task_estimates.get(task.spec_id)
            duration_str = format_duration(estimate.estimated_duration_hours) if estimate else "N/A"
            confidence_str = format_confidence(estimate.confidence) if estimate else "N/A"
            
            click.echo(f"    {i:2d}. {click.style(task.spec_id, fg='red', bold=True)} - {task.title}")
            click.echo(f"        Duration: {duration_str} ({confidence_str})")
            if verbose and task.description:
                desc = task.description[:100] + "..." if len(task.description) > 100 else task.description
                click.echo(f"        {desc}")
    click.echo()
    
    # Bottlenecks
    if analysis.bottleneck_scores:
        click.echo(click.style("  TOP BOTTLENECKS", fg="yellow", bold=True))
        sorted_bottlenecks = sorted(analysis.bottleneck_scores.items(), 
                                  key=lambda x: x[1], reverse=True)[:5]
        
        for i, (spec_id, score) in enumerate(sorted_bottlenecks, 1):
            node = analysis.task_nodes.get(spec_id)
            if node:
                task = node.task
                slack_str = format_duration(node.slack) if node.slack > 0.001 else "0h"
                critical_indicator = "🔴 " if node.is_critical else ""
                
                click.echo(f"    {i}. {critical_indicator}{click.style(spec_id, fg='yellow', bold=True)} - {task.title}")
                click.echo(f"       Score: {score:.1f}, Slack: {slack_str}")
        click.echo()
    
    # Tasks with most slack (good for deprioritization)
    click.echo(click.style("  TASKS WITH MOST SLACK", fg="green", bold=True))
    non_critical_tasks = [(spec_id, node) for spec_id, node in analysis.task_nodes.items() 
                         if not node.is_critical and node.slack > 0.001]
    
    if not non_critical_tasks:
        click.echo("    All tasks are on the critical path.")
    else:
        sorted_slack = sorted(non_critical_tasks, key=lambda x: x[1].slack, reverse=True)[:5]
        
        for i, (spec_id, node) in enumerate(sorted_slack, 1):
            task = node.task
            slack_str = format_duration(node.slack)
            estimate = analysis.task_estimates.get(spec_id)
            duration_str = format_duration(estimate.estimated_duration_hours) if estimate else "N/A"
            
            click.echo(f"    {i}. {click.style(spec_id, fg='green')} - {task.title}")
            click.echo(f"       Slack: {slack_str}, Duration: {duration_str}")
    click.echo()
    
    # Parallelism opportunities
    if analysis.parallelism_groups:
        click.echo(click.style("  PARALLELISM OPPORTUNITIES", fg="blue", bold=True))
        for group in analysis.parallelism_groups:
            click.echo(f"    Level {group.depth_level}: {len(group.tasks)} tasks can run in parallel")
            click.echo(f"    Duration: {format_duration(group.estimated_duration)}")
            
            if verbose:
                for task in group.tasks[:5]:  # Show first 5 tasks
                    click.echo(f"      • {task.spec_id} - {task.title}")
                if len(group.tasks) > 5:
                    click.echo(f"      ... and {len(group.tasks) - 5} more")
            else:
                task_ids = [task.spec_id for task in group.tasks[:3]]
                if len(group.tasks) > 3:
                    task_ids_str = ", ".join(task_ids) + f", +{len(group.tasks) - 3} more"
                else:
                    task_ids_str = ", ".join(task_ids)
                click.echo(f"      Tasks: {task_ids_str}")
            click.echo()
    
    # Task estimates breakdown (verbose mode)
    if verbose and analysis.task_estimates:
        click.echo(click.style("  TASK ESTIMATES", fg="cyan", bold=True))
        
        # Group by source
        by_source = {}
        for estimate in analysis.task_estimates.values():
            source = estimate.source
            if source not in by_source:
                by_source[source] = []
            by_source[source].append(estimate)
        
        for source, estimates in by_source.items():
            source_name = {
                "historical": "Historical Data",
                "heuristic": "Complexity Heuristics", 
                "default": "Default Estimates"
            }.get(source, source.title())
            
            click.echo(f"    {source_name}: {len(estimates)} tasks")
            
            if source == "historical":
                total_samples = sum(est.historical_samples for est in estimates)
                click.echo(f"      Total historical samples: {total_samples}")
        click.echo()
    
    click.echo(click.style("═" * 80, fg="cyan"))


def display_json_analysis(analysis) -> None:
    """Display critical path analysis in JSON format."""
    # Convert analysis to serializable format
    result = {
        "critical_path": [
            {
                "spec_id": task.spec_id,
                "title": task.title,
                "description": task.description,
                "priority": task.priority,
                "status": task.status.value,
                "depends_on": task.depends_on
            }
            for task in analysis.critical_path
        ],
        "critical_path_duration_hours": analysis.critical_path_duration,
        "total_estimated_duration_hours": analysis.total_estimated_duration,
        "task_estimates": {
            spec_id: {
                "estimated_duration_hours": est.estimated_duration_hours,
                "confidence": est.confidence,
                "source": est.source,
                "historical_samples": est.historical_samples
            }
            for spec_id, est in analysis.task_estimates.items()
        },
        "task_analysis": {
            spec_id: {
                "earliest_start": node.earliest_start,
                "earliest_finish": node.earliest_finish,
                "latest_start": node.latest_start,
                "latest_finish": node.latest_finish,
                "duration": node.duration,
                "slack": node.slack,
                "is_critical": node.is_critical,
                "task": {
                    "spec_id": node.task.spec_id,
                    "title": node.task.title,
                    "priority": node.task.priority,
                    "status": node.task.status.value
                }
            }
            for spec_id, node in analysis.task_nodes.items()
        },
        "parallelism_groups": [
            {
                "depth_level": group.depth_level,
                "task_count": len(group.tasks),
                "estimated_duration_hours": group.estimated_duration,
                "tasks": [
                    {
                        "spec_id": task.spec_id,
                        "title": task.title,
                        "priority": task.priority
                    }
                    for task in group.tasks
                ]
            }
            for group in analysis.parallelism_groups
        ],
        "bottleneck_scores": analysis.bottleneck_scores,
        "errors": analysis.errors,
        "summary": {
            "total_tasks": len(analysis.task_nodes),
            "critical_tasks": sum(1 for node in analysis.task_nodes.values() if node.is_critical),
            "parallelism_groups": len(analysis.parallelism_groups),
            "max_parallel_tasks": max(len(group.tasks) for group in analysis.parallelism_groups) if analysis.parallelism_groups else 0
        }
    }
    
    click.echo(json_lib.dumps(result, indent=2))


@click.command()
@click.option('--json', 'json_output', is_flag=True, help='Output in JSON format')
@click.option('--verbose', '-v', is_flag=True, help='Show detailed analysis')
@click.pass_context
def critical_path(ctx: click.Context, json_output: bool, verbose: bool) -> None:
    """Analyze critical path and task dependencies.

    \b
    Performs Critical Path Method (CPM) analysis to identify:
    • The critical path - longest chain of dependent tasks
    • Bottleneck tasks that would delay the entire project if delayed
    • Parallelism opportunities - tasks that can run simultaneously  
    • Task slack - how much tasks can be delayed without affecting the project
    • Estimated completion time based on task complexity and historical data

    \b
    Examples:
        bob critical-path                # Show critical path analysis
        bob critical-path --verbose      # Detailed analysis with estimates
        bob critical-path --json         # JSON output for scripts
    """
    # Get database path from context
    db_path = ctx.obj.db_path
    
    # Get project ID from context
    project_id = ctx.obj.project_id
    if not project_id:
        click.echo("✗ No project specified. Use --project or set an active project.", err=True)
        ctx.exit(1)
    
    # Initialize database manager
    db = DatabaseManager(db_path)
    
    # Verify project exists
    project = db.get_project(project_id)
    if not project:
        click.echo(f"✗ Project not found: {project_id}", err=True)
        ctx.exit(1)
    
    # Run critical path analysis
    analyzer = CriticalPathAnalyzer(db, project_id)
    analysis = analyzer.analyze()
    
    # Display results
    if json_output:
        display_json_analysis(analysis)
    else:
        display_text_analysis(analysis, verbose=verbose)