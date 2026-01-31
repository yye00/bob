"""Critical Path Analysis for BOB orchestrator.

This module implements the Critical Path Method (CPM) for analyzing task dependencies
and identifying the longest chain of dependent tasks (critical path) that determines
the minimum project completion time.
"""

import json
import os
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from bob.database.manager import DatabaseManager
from bob.models.base import Task, TaskStatus


@dataclass
class TaskEstimate:
    """Task duration estimate with confidence level."""
    task_spec_id: str
    estimated_duration_hours: float
    confidence: str = "medium"  # "high", "medium", "low"
    source: str = "heuristic"  # "historical", "heuristic", "default"
    historical_samples: int = 0
    
    
@dataclass
class CriticalPathNode:
    """Node in the critical path analysis graph."""
    task: Task
    earliest_start: float = 0.0
    earliest_finish: float = 0.0
    latest_start: float = 0.0
    latest_finish: float = 0.0
    duration: float = 0.0
    float_time: float = 0.0  # Slack time
    is_critical: bool = False
    
    @property
    def slack(self) -> float:
        """Alias for float_time."""
        return self.float_time


@dataclass
class ParallelismGroup:
    """Group of tasks that can run in parallel."""
    depth_level: int
    tasks: List[Task] = field(default_factory=list)
    estimated_duration: float = 0.0  # Duration of longest task in group
    
    
@dataclass
class CriticalPathAnalysis:
    """Complete critical path analysis results."""
    critical_path: List[Task] = field(default_factory=list)
    critical_path_duration: float = 0.0
    total_estimated_duration: float = 0.0
    task_estimates: Dict[str, TaskEstimate] = field(default_factory=dict)
    task_nodes: Dict[str, CriticalPathNode] = field(default_factory=dict)
    parallelism_groups: List[ParallelismGroup] = field(default_factory=list)
    bottleneck_scores: Dict[str, float] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class CriticalPathAnalyzer:
    """Critical Path Method (CPM) analyzer for BOB tasks."""
    
    def __init__(self, db_manager: DatabaseManager, project_id: str):
        """Initialize the analyzer.
        
        Args:
            db_manager: Database manager instance
            project_id: Project ID to analyze
        """
        self.db_manager = db_manager
        self.project_id = project_id
        
        # Default duration estimates in hours
        self.default_durations = {
            "critical": 8.0,
            "high": 4.0, 
            "medium": 2.0,
            "low": 1.0
        }
        
    def analyze(self) -> CriticalPathAnalysis:
        """Perform complete critical path analysis.
        
        Returns:
            CriticalPathAnalysis with complete results
        """
        result = CriticalPathAnalysis()
        
        # Get all tasks for the project
        tasks = self.db_manager.list_tasks(project_id=self.project_id, limit=10000)
        if not tasks:
            result.errors.append("No tasks found for project")
            return result
            
        # Build task lookup map
        task_map = {task.spec_id: task for task in tasks}
        
        # Estimate task durations
        result.task_estimates = self._estimate_task_durations(tasks)
        
        # Check for circular dependencies
        cycles = self._detect_cycles(tasks)
        if cycles:
            result.errors.extend([f"Circular dependency detected: {' -> '.join(cycle)}" for cycle in cycles])
            return result
            
        # Build dependency graph
        graph, reverse_graph = self._build_dependency_graph(tasks)
        
        # Create task nodes with estimates
        result.task_nodes = {}
        for task in tasks:
            estimate = result.task_estimates.get(task.spec_id)
            duration = estimate.estimated_duration_hours if estimate else self.default_durations.get(task.priority, 2.0)
            
            result.task_nodes[task.spec_id] = CriticalPathNode(
                task=task,
                duration=duration
            )
        
        # Forward pass - calculate earliest start/finish times
        self._forward_pass(result.task_nodes, graph)
        
        # Find project end time (max finish time of leaf nodes)
        # Leaf nodes are tasks that have no dependents (no outgoing edges in the graph)
        leaf_nodes = [spec_id for spec_id in task_map.keys() 
                     if spec_id not in graph or len(graph[spec_id]) == 0]
        
        if not leaf_nodes:
            # Fallback: use all tasks (shouldn't happen in a proper DAG)
            leaf_nodes = list(task_map.keys())
            
        project_end_time = max(result.task_nodes[spec_id].earliest_finish for spec_id in leaf_nodes)
        result.total_estimated_duration = project_end_time
        
        # Backward pass - calculate latest start/finish times
        self._backward_pass(result.task_nodes, reverse_graph, project_end_time)
        
        # Calculate float/slack and identify critical path
        critical_task_specs = []
        for spec_id, node in result.task_nodes.items():
            node.float_time = node.latest_start - node.earliest_start
            node.is_critical = abs(node.float_time) < 0.001  # Account for float precision
            
            if node.is_critical:
                critical_task_specs.append(spec_id)
        
        # Build critical path in order
        result.critical_path = self._build_critical_path(critical_task_specs, task_map, graph)
        result.critical_path_duration = project_end_time
        
        # Calculate parallelism groups
        result.parallelism_groups = self._calculate_parallelism_groups(result.task_nodes, graph)
        
        # Calculate bottleneck scores
        result.bottleneck_scores = self._calculate_bottleneck_scores(result.task_nodes, graph)
        
        return result
    
    def _estimate_task_durations(self, tasks: List[Task]) -> Dict[str, TaskEstimate]:
        """Estimate duration for each task using multiple sources.
        
        Priority order:
        1. Historical telemetry data
        2. Task complexity heuristics 
        3. Default based on priority
        
        Args:
            tasks: List of tasks to estimate
            
        Returns:
            Dictionary mapping spec_id to TaskEstimate
        """
        estimates = {}
        
        # Try to load historical data
        historical_data = self._load_historical_telemetry()
        
        for task in tasks:
            estimate = None
            
            # 1. Try historical data first
            if task.spec_id in historical_data:
                hist_data = historical_data[task.spec_id]
                estimate = TaskEstimate(
                    task_spec_id=task.spec_id,
                    estimated_duration_hours=hist_data["avg_duration_hours"],
                    confidence="high" if hist_data["sample_count"] >= 3 else "medium",
                    source="historical",
                    historical_samples=hist_data["sample_count"]
                )
            
            # 2. Use complexity heuristics
            elif not estimate:
                duration = self._estimate_from_complexity(task)
                if duration:
                    estimate = TaskEstimate(
                        task_spec_id=task.spec_id,
                        estimated_duration_hours=duration,
                        confidence="medium",
                        source="heuristic"
                    )
            
            # 3. Fall back to defaults
            if not estimate:
                duration = self.default_durations.get(task.priority.lower(), 2.0)
                estimate = TaskEstimate(
                    task_spec_id=task.spec_id,
                    estimated_duration_hours=duration,
                    confidence="low",
                    source="default"
                )
            
            estimates[task.spec_id] = estimate
            
        return estimates
    
    def _load_historical_telemetry(self) -> Dict[str, Dict]:
        """Load historical execution times from telemetry data.
        
        Returns:
            Dictionary mapping spec_id to aggregated historical data
        """
        telemetry_dir = os.path.join(self.db_manager.db_path.parent, "telemetry")
        if not os.path.exists(telemetry_dir):
            return {}
        
        historical_data = defaultdict(list)
        
        # Load all telemetry files
        for filename in os.listdir(telemetry_dir):
            if not filename.endswith('.json'):
                continue
                
            try:
                filepath = os.path.join(telemetry_dir, filename)
                with open(filepath, 'r') as f:
                    data = json.load(f)
                
                # Extract task-level timing data
                if 'tasks' in data:
                    for spec_id, task_data in data['tasks'].items():
                        if 'wall_clock_seconds' in task_data:
                            duration_hours = task_data['wall_clock_seconds'] / 3600.0
                            historical_data[spec_id].append(duration_hours)
                            
            except (json.JSONDecodeError, IOError, KeyError):
                continue
        
        # Aggregate the data
        result = {}
        for spec_id, durations in historical_data.items():
            if durations:
                avg_duration = sum(durations) / len(durations)
                result[spec_id] = {
                    "avg_duration_hours": avg_duration,
                    "min_duration_hours": min(durations),
                    "max_duration_hours": max(durations),
                    "sample_count": len(durations)
                }
        
        return result
    
    def _estimate_from_complexity(self, task: Task) -> Optional[float]:
        """Estimate duration based on task complexity indicators.
        
        Args:
            task: Task to estimate
            
        Returns:
            Estimated duration in hours, or None if no heuristics apply
        """
        base_duration = self.default_durations.get(task.priority.lower(), 2.0)
        
        # Complexity multipliers based on task characteristics
        multiplier = 1.0
        
        # Check description for complexity indicators
        description_lower = task.description.lower()
        
        # Database/storage operations
        if any(word in description_lower for word in ['database', 'migration', 'schema', 'sql']):
            multiplier *= 1.5
        
        # API/integration work
        if any(word in description_lower for word in ['api', 'integration', 'external', 'service']):
            multiplier *= 1.3
        
        # UI/frontend work
        if any(word in description_lower for word in ['ui', 'frontend', 'interface', 'component']):
            multiplier *= 1.2
        
        # Testing work
        if any(word in description_lower for word in ['test', 'testing', 'coverage']):
            multiplier *= 0.8
        
        # Refactoring work
        if any(word in description_lower for word in ['refactor', 'cleanup', 'optimize']):
            multiplier *= 0.7
        
        # Multiple acceptance criteria suggest complexity
        if len(task.acceptance_criteria) > 3:
            multiplier *= 1.2
        elif len(task.acceptance_criteria) > 5:
            multiplier *= 1.5
        
        # Multiple steps suggest complexity
        if len(task.steps) > 5:
            multiplier *= 1.3
        elif len(task.steps) > 8:
            multiplier *= 1.6
        
        # Multiple dependencies suggest complexity
        if len(task.depends_on) > 2:
            multiplier *= 1.1
        
        return base_duration * multiplier
    
    def _detect_cycles(self, tasks: List[Task]) -> List[List[str]]:
        """Detect circular dependencies in task graph.
        
        Args:
            tasks: List of tasks to check
            
        Returns:
            List of cycles found, each as list of spec_ids
        """
        # Build adjacency list
        graph = defaultdict(list)
        all_specs = set()
        
        for task in tasks:
            all_specs.add(task.spec_id)
            for dep_id in task.depends_on:
                graph[dep_id].append(task.spec_id)
        
        # DFS cycle detection
        color = {}  # 0=white, 1=gray, 2=black
        cycles = []
        
        def dfs(node, path):
            if node not in all_specs:
                return  # Skip invalid dependencies
                
            if color.get(node, 0) == 1:  # Gray - cycle detected
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                return
            
            if color.get(node, 0) == 2:  # Black - already processed
                return
            
            color[node] = 1  # Gray
            for neighbor in graph[node]:
                dfs(neighbor, path + [node])
            color[node] = 2  # Black
        
        for spec_id in all_specs:
            if color.get(spec_id, 0) == 0:
                dfs(spec_id, [])
        
        return cycles
    
    def _build_dependency_graph(self, tasks: List[Task]) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
        """Build forward and reverse dependency graphs.
        
        Args:
            tasks: List of tasks
            
        Returns:
            Tuple of (forward_graph, reverse_graph)
            forward_graph: spec_id -> [dependent_spec_ids]
            reverse_graph: spec_id -> [dependency_spec_ids]
        """
        forward_graph = defaultdict(list)
        reverse_graph = defaultdict(list)
        
        all_specs = {task.spec_id for task in tasks}
        
        for task in tasks:
            for dep_spec_id in task.depends_on:
                if dep_spec_id in all_specs:  # Only valid dependencies
                    forward_graph[dep_spec_id].append(task.spec_id)
                    reverse_graph[task.spec_id].append(dep_spec_id)
        
        return dict(forward_graph), dict(reverse_graph)
    
    def _forward_pass(self, nodes: Dict[str, CriticalPathNode], graph: Dict[str, List[str]]) -> None:
        """Calculate earliest start and finish times (forward pass).
        
        Args:
            nodes: Dictionary of task nodes
            graph: Forward dependency graph (dependencies -> dependents)
        """
        # Initialize all start times to 0
        for node in nodes.values():
            node.earliest_start = 0.0
            node.earliest_finish = node.duration
        
        # Topological sort for processing order
        in_degree = defaultdict(int)
        for spec_id in nodes:
            in_degree[spec_id] = 0
        
        for dependents in graph.values():
            for dependent_id in dependents:
                if dependent_id in nodes:
                    in_degree[dependent_id] += 1
        
        # Process nodes in topological order
        queue = deque([spec_id for spec_id in nodes if in_degree[spec_id] == 0])
        
        while queue:
            current_id = queue.popleft()
            current_node = nodes[current_id]
            
            # Update all dependents
            for dependent_id in graph.get(current_id, []):
                if dependent_id in nodes:
                    dependent_node = nodes[dependent_id]
                    
                    # Update earliest start time
                    new_start = current_node.earliest_finish
                    if new_start > dependent_node.earliest_start:
                        dependent_node.earliest_start = new_start
                        dependent_node.earliest_finish = new_start + dependent_node.duration
                    
                    # Reduce in-degree and add to queue if ready
                    in_degree[dependent_id] -= 1
                    if in_degree[dependent_id] == 0:
                        queue.append(dependent_id)
    
    def _backward_pass(self, nodes: Dict[str, CriticalPathNode], reverse_graph: Dict[str, List[str]], 
                      project_end_time: float) -> None:
        """Calculate latest start and finish times (backward pass).
        
        Args:
            nodes: Dictionary of task nodes
            reverse_graph: Reverse dependency graph (dependents -> dependencies)
            project_end_time: Total project duration
        """
        # Find leaf nodes (tasks with no dependents)
        all_dependencies = set()
        for deps in reverse_graph.values():
            all_dependencies.update(deps)
        
        leaf_nodes = [spec_id for spec_id in nodes.keys() if spec_id not in all_dependencies]
        
        # Initialize latest finish times
        for spec_id, node in nodes.items():
            if spec_id in leaf_nodes:
                # Leaf nodes: latest finish = earliest finish (since they determine project end)
                node.latest_finish = node.earliest_finish
            else:
                node.latest_finish = float('inf')
            
            node.latest_start = node.latest_finish - node.duration
        
        # Count how many dependents each task has
        dependent_count = defaultdict(int)
        for spec_id, deps in reverse_graph.items():
            for dep_id in deps:
                if dep_id in nodes:
                    dependent_count[dep_id] += 1
        
        # Start with leaf nodes (no dependents in reverse_graph)
        queue = deque(leaf_nodes)
        processed = set()
        
        while queue:
            current_id = queue.popleft()
            if current_id in processed:
                continue
            processed.add(current_id)
            
            current_node = nodes[current_id]
            
            # Update all dependencies (predecessors)
            for dep_id in reverse_graph.get(current_id, []):
                if dep_id in nodes:
                    dep_node = nodes[dep_id]
                    
                    # Update latest finish time (min of all dependent's latest start times)
                    new_latest_finish = current_node.latest_start
                    if new_latest_finish < dep_node.latest_finish:
                        dep_node.latest_finish = new_latest_finish
                        dep_node.latest_start = new_latest_finish - dep_node.duration
                    
                    # Reduce dependent count and add to queue if ready
                    dependent_count[dep_id] -= 1
                    if dependent_count[dep_id] == 0:
                        queue.append(dep_id)
    
    def _build_critical_path(self, critical_specs: List[str], task_map: Dict[str, Task], 
                           graph: Dict[str, List[str]]) -> List[Task]:
        """Build ordered critical path from critical task specs.
        
        Args:
            critical_specs: List of spec_ids on critical path
            task_map: Mapping of spec_id to Task
            graph: Forward dependency graph
            
        Returns:
            Ordered list of tasks on critical path
        """
        if not critical_specs:
            return []
        
        # Build subgraph of only critical tasks
        critical_graph = {}
        for spec_id in critical_specs:
            critical_graph[spec_id] = [dep for dep in graph.get(spec_id, []) if dep in critical_specs]
        
        # Find critical path order using topological sort
        in_degree = defaultdict(int)
        for spec_id in critical_specs:
            in_degree[spec_id] = 0
        
        for dependents in critical_graph.values():
            for dependent_id in dependents:
                in_degree[dependent_id] += 1
        
        # Topological sort
        queue = deque([spec_id for spec_id in critical_specs if in_degree[spec_id] == 0])
        ordered_path = []
        
        while queue:
            current_id = queue.popleft()
            ordered_path.append(task_map[current_id])
            
            for dependent_id in critical_graph.get(current_id, []):
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)
        
        return ordered_path
    
    def _calculate_parallelism_groups(self, nodes: Dict[str, CriticalPathNode], 
                                    graph: Dict[str, List[str]]) -> List[ParallelismGroup]:
        """Calculate groups of tasks that can run in parallel.
        
        Args:
            nodes: Task nodes with timing information
            graph: Forward dependency graph
            
        Returns:
            List of parallelism groups ordered by depth level
        """
        # Calculate depth level for each task (distance from start)
        depth_levels = {}
        
        # Find tasks with no dependencies (depth 0)
        has_dependencies = set()
        for dependents in graph.values():
            has_dependencies.update(dependents)
        
        queue = deque()
        for spec_id in nodes:
            if spec_id not in has_dependencies:
                depth_levels[spec_id] = 0
                queue.append((spec_id, 0))
        
        # BFS to assign depth levels
        while queue:
            spec_id, depth = queue.popleft()
            
            for dependent_id in graph.get(spec_id, []):
                if dependent_id in nodes:
                    new_depth = depth + 1
                    if dependent_id not in depth_levels or depth_levels[dependent_id] < new_depth:
                        depth_levels[dependent_id] = new_depth
                        queue.append((dependent_id, new_depth))
        
        # Group tasks by depth level
        groups_by_level = defaultdict(list)
        for spec_id, depth in depth_levels.items():
            groups_by_level[depth].append(nodes[spec_id].task)
        
        # Create parallelism groups
        groups = []
        for depth in sorted(groups_by_level.keys()):
            tasks = groups_by_level[depth]
            if len(tasks) > 1:  # Only include levels with multiple tasks
                # Duration is the longest task in the group
                max_duration = max(nodes[task.spec_id].duration for task in tasks)
                
                groups.append(ParallelismGroup(
                    depth_level=depth,
                    tasks=tasks,
                    estimated_duration=max_duration
                ))
        
        return groups
    
    def _calculate_bottleneck_scores(self, nodes: Dict[str, CriticalPathNode], 
                                   graph: Dict[str, List[str]]) -> Dict[str, float]:
        """Calculate bottleneck score for each task.
        
        Bottleneck score = (number of dependent tasks) * (1 / slack_time)
        Higher score = more critical bottleneck
        
        Args:
            nodes: Task nodes with timing information
            graph: Forward dependency graph
            
        Returns:
            Dictionary mapping spec_id to bottleneck score
        """
        scores = {}
        
        for spec_id, node in nodes.items():
            # Count all transitively dependent tasks
            dependent_count = len(self._get_all_dependents(spec_id, graph, nodes))
            
            # Calculate inverse slack (critical tasks get high score)
            if node.float_time <= 0.001:
                slack_factor = 1000.0  # Critical path tasks get very high score
            else:
                slack_factor = 1.0 / node.float_time
            
            scores[spec_id] = dependent_count * slack_factor
        
        return scores
    
    def _get_all_dependents(self, spec_id: str, graph: Dict[str, List[str]], 
                          nodes: Dict[str, CriticalPathNode]) -> Set[str]:
        """Get all transitively dependent tasks.
        
        Args:
            spec_id: Starting task spec_id
            graph: Forward dependency graph
            nodes: Task nodes
            
        Returns:
            Set of all transitively dependent spec_ids
        """
        visited = set()
        
        def dfs(current_id):
            if current_id in visited or current_id not in nodes:
                return
            visited.add(current_id)
            for dependent_id in graph.get(current_id, []):
                dfs(dependent_id)
        
        # Start DFS from immediate dependents
        for dependent_id in graph.get(spec_id, []):
            dfs(dependent_id)
        
        return visited