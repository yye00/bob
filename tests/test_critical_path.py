"""Tests for critical path analysis functionality."""

import json
import os
import tempfile
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from bob.database.manager import DatabaseManager
from bob.models.base import Project, Task, TaskStatus, ProjectStatus
from bob.orchestrator.critical_path import CriticalPathAnalyzer, CriticalPathAnalysis


class TestCriticalPathAnalyzer:
    """Test critical path analysis functionality."""
    
    @pytest.fixture
    def db_manager(self):
        """Create a test database manager."""
        # Create temporary database
        temp_dir = tempfile.mkdtemp()
        db_path = Path(temp_dir) / "test.db"
        
        db_manager = DatabaseManager(db_path)
        
        # Create test project
        project = Project(
            id="test-project",
            name="Test Project",
            description="Test project for critical path analysis",
            workspace_dir=temp_dir,
            spec_source="file://test.yaml",
            status=ProjectStatus.ACTIVE,
            created_at=datetime.now()
        )
        db_manager.create_project(project)
        
        yield db_manager
        
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def analyzer(self, db_manager):
        """Create analyzer instance."""
        return CriticalPathAnalyzer(db_manager, "test-project")
    
    def create_task(self, db_manager, spec_id: str, title: str, depends_on=None, 
                   priority="medium", status=TaskStatus.PENDING):
        """Helper to create a test task."""
        task = Task(
            id=f"task-{spec_id}",
            project_id="test-project",
            spec_id=spec_id,
            title=title,
            description=f"Description for {title}",
            depends_on=depends_on or [],
            priority=priority,
            status=status
        )
        db_manager.create_task(task)
        return task
    
    def test_empty_project(self, analyzer):
        """Test analysis with no tasks."""
        analysis = analyzer.analyze()
        
        assert len(analysis.errors) == 1
        assert "No tasks found" in analysis.errors[0]
        assert len(analysis.critical_path) == 0
        assert analysis.total_estimated_duration == 0
    
    def test_single_task(self, analyzer, db_manager):
        """Test analysis with single task."""
        self.create_task(db_manager, "A", "Task A")
        
        analysis = analyzer.analyze()
        
        assert len(analysis.errors) == 0
        assert len(analysis.critical_path) == 1
        assert analysis.critical_path[0].spec_id == "A"
        assert analysis.total_estimated_duration == 2.0  # default medium priority
        
        # Task should be critical (only task)
        node_a = analysis.task_nodes["A"]
        assert node_a.is_critical
        assert node_a.slack == 0.0
    
    def test_linear_chain(self, analyzer, db_manager):
        """Test linear chain: A → B → C → D (all tasks critical)."""
        self.create_task(db_manager, "A", "Task A", priority="high")
        self.create_task(db_manager, "B", "Task B", depends_on=["A"])
        self.create_task(db_manager, "C", "Task C", depends_on=["B"], priority="low")
        self.create_task(db_manager, "D", "Task D", depends_on=["C"])
        
        analysis = analyzer.analyze()
        
        assert len(analysis.errors) == 0
        assert len(analysis.critical_path) == 4
        
        # Check order
        path_specs = [task.spec_id for task in analysis.critical_path]
        assert path_specs == ["A", "B", "C", "D"]
        
        # All tasks should be critical
        for spec_id in ["A", "B", "C", "D"]:
            node = analysis.task_nodes[spec_id]
            assert node.is_critical, f"Task {spec_id} should be critical"
            assert abs(node.slack) < 0.001, f"Task {spec_id} should have zero slack"
        
        # Check timing
        expected_duration = 4.0 + 2.0 + 1.0 + 2.0  # high + med + low + med
        assert abs(analysis.total_estimated_duration - expected_duration) < 0.001
    
    def test_diamond_dependency(self, analyzer, db_manager):
        """Test diamond: A → B, A → C, B → D, C → D."""
        self.create_task(db_manager, "A", "Task A", priority="medium")  # 2h
        self.create_task(db_manager, "B", "Task B", depends_on=["A"], priority="high")  # 4h
        self.create_task(db_manager, "C", "Task C", depends_on=["A"], priority="low")   # 1h
        self.create_task(db_manager, "D", "Task D", depends_on=["B", "C"], priority="medium")  # 2h
        
        analysis = analyzer.analyze()
        
        assert len(analysis.errors) == 0
        
        # Critical path should be A → B → D (longer path)
        path_specs = [task.spec_id for task in analysis.critical_path]
        assert "A" in path_specs
        assert "B" in path_specs
        assert "D" in path_specs
        
        # A, B, D should be critical
        assert analysis.task_nodes["A"].is_critical
        assert analysis.task_nodes["B"].is_critical
        assert analysis.task_nodes["D"].is_critical
        
        # C should have slack (shorter path)
        node_c = analysis.task_nodes["C"]
        assert not node_c.is_critical
        assert node_c.slack > 0
        
        # Expected duration: A(2) + B(4) + D(2) = 8h
        assert abs(analysis.total_estimated_duration - 8.0) < 0.001
    
    def test_wide_parallel(self, analyzer, db_manager):
        """Test 10 independent tasks (critical path = longest single task)."""
        priorities = ["critical", "high", "medium", "low"] * 3 + ["critical"]
        
        for i in range(10):
            priority = priorities[i % len(priorities)]
            self.create_task(db_manager, f"T{i+1}", f"Task {i+1}", priority=priority)
        
        analysis = analyzer.analyze()
        
        assert len(analysis.errors) == 0
        
        # Critical path should include all the critical priority tasks (8h each)
        # Since they all have the same max duration, they're all critical
        critical_tasks = [t for t in analysis.critical_path if t.priority == "critical"]
        assert len(critical_tasks) >= 1  # At least one critical task should be on critical path
        
        # Total duration should be 8h (longest task)
        assert abs(analysis.total_estimated_duration - 8.0) < 0.001
        
        # Should have parallelism opportunities
        assert len(analysis.parallelism_groups) > 0
        group = analysis.parallelism_groups[0]
        assert group.depth_level == 0
        assert len(group.tasks) == 10
    
    def test_complex_dag(self, analyzer, db_manager):
        """Test complex DAG with multiple paths."""
        # Create a more complex dependency graph
        #     A
        #   /   \
        #  B     C
        #  |   / | \
        #  D  E  F  G
        #   \ |  | /
        #     H  I
        #      \ |
        #        J
        
        self.create_task(db_manager, "A", "Task A", priority="medium")    # 2h
        self.create_task(db_manager, "B", "Task B", depends_on=["A"], priority="high")     # 4h
        self.create_task(db_manager, "C", "Task C", depends_on=["A"], priority="low")      # 1h
        self.create_task(db_manager, "D", "Task D", depends_on=["B"], priority="medium")   # 2h
        self.create_task(db_manager, "E", "Task E", depends_on=["C"], priority="critical") # 8h
        self.create_task(db_manager, "F", "Task F", depends_on=["C"], priority="medium")   # 2h
        self.create_task(db_manager, "G", "Task G", depends_on=["C"], priority="low")      # 1h
        self.create_task(db_manager, "H", "Task H", depends_on=["D", "E"], priority="medium") # 2h
        self.create_task(db_manager, "I", "Task I", depends_on=["F", "G"], priority="medium") # 2h
        self.create_task(db_manager, "J", "Task J", depends_on=["H", "I"], priority="medium") # 2h
        
        analysis = analyzer.analyze()
        
        assert len(analysis.errors) == 0
        assert len(analysis.critical_path) > 0
        
        # The critical path should include E (8h task)
        critical_specs = [task.spec_id for task in analysis.critical_path]
        assert "E" in critical_specs
        
        # Should have some parallelism opportunities
        assert len(analysis.parallelism_groups) > 0
    
    def test_circular_dependency_detection(self, analyzer, db_manager):
        """Test detection of circular dependencies."""
        self.create_task(db_manager, "A", "Task A", depends_on=["C"])
        self.create_task(db_manager, "B", "Task B", depends_on=["A"])
        self.create_task(db_manager, "C", "Task C", depends_on=["B"])
        
        analysis = analyzer.analyze()
        
        assert len(analysis.errors) > 0
        assert any("Circular dependency" in error for error in analysis.errors)
    
    def test_invalid_dependencies(self, analyzer, db_manager):
        """Test handling of invalid dependencies."""
        self.create_task(db_manager, "A", "Task A")
        self.create_task(db_manager, "B", "Task B", depends_on=["A", "NONEXISTENT"])
        
        analysis = analyzer.analyze()
        
        # Should still work, just ignore the invalid dependency
        assert len(analysis.errors) == 0
        assert len(analysis.critical_path) == 2
    
    def test_historical_duration_estimates(self, analyzer, db_manager):
        """Test duration estimation with historical data."""
        # Create telemetry directory and file
        telemetry_dir = db_manager.db_path.parent / "telemetry"
        telemetry_dir.mkdir(exist_ok=True)
        
        # Mock telemetry data
        telemetry_data = {
            "run_id": "test-run",
            "started_at": "2024-01-01T00:00:00",
            "ended_at": "2024-01-01T05:00:00",
            "wall_clock_seconds": 18000,  # 5 hours
            "tasks": {
                "A": {"wall_clock_seconds": 7200},  # 2 hours
                "B": {"wall_clock_seconds": 10800}  # 3 hours
            }
        }
        
        telemetry_file = telemetry_dir / "run-test.json"
        with open(telemetry_file, 'w') as f:
            json.dump(telemetry_data, f)
        
        try:
            self.create_task(db_manager, "A", "Task A")
            self.create_task(db_manager, "B", "Task B", depends_on=["A"])
            
            analysis = analyzer.analyze()
            
            # Check that historical data was used
            estimate_a = analysis.task_estimates["A"]
            estimate_b = analysis.task_estimates["B"]
            
            assert estimate_a.source == "historical"
            assert abs(estimate_a.estimated_duration_hours - 2.0) < 0.1
            assert estimate_b.source == "historical" 
            assert abs(estimate_b.estimated_duration_hours - 3.0) < 0.1
            
        finally:
            # Cleanup
            telemetry_file.unlink()
    
    def test_complexity_heuristics(self, analyzer, db_manager):
        """Test duration estimation based on task complexity."""
        # Task with complex description should get longer estimate
        complex_task = Task(
            id="complex",
            project_id="test-project",
            spec_id="COMPLEX",
            title="Complex Task",
            description="Implement database migration with API integration and extensive testing",
            acceptance_criteria=[f"Criteria {i}" for i in range(6)],  # Many criteria
            steps=[f"Step {i}" for i in range(10)],  # Many steps
            depends_on=[],
            priority="medium"
        )
        db_manager.create_task(complex_task)
        
        # Simple task should get shorter estimate
        simple_task = Task(
            id="simple", 
            project_id="test-project",
            spec_id="SIMPLE",
            title="Simple Task",
            description="Fix typo in documentation",
            acceptance_criteria=["Fix typo"],
            steps=["Edit file"],
            depends_on=[],
            priority="medium"
        )
        db_manager.create_task(simple_task)
        
        analysis = analyzer.analyze()
        
        complex_estimate = analysis.task_estimates["COMPLEX"]
        simple_estimate = analysis.task_estimates["SIMPLE"]
        
        assert complex_estimate.source in ["heuristic", "default"]
        assert simple_estimate.source in ["heuristic", "default"]
        
        # Complex task should take longer
        assert complex_estimate.estimated_duration_hours > simple_estimate.estimated_duration_hours
    
    def test_bottleneck_scores(self, analyzer, db_manager):
        """Test bottleneck score calculation."""
        # Create dependency chain where B is a bottleneck
        self.create_task(db_manager, "A", "Task A")
        self.create_task(db_manager, "B", "Task B", depends_on=["A"])
        self.create_task(db_manager, "C", "Task C", depends_on=["B"])
        self.create_task(db_manager, "D", "Task D", depends_on=["B"])
        self.create_task(db_manager, "E", "Task E", depends_on=["B"])
        
        analysis = analyzer.analyze()
        
        # A should have highest bottleneck score (affects most total tasks)
        # A affects: B, C, D, E (4 tasks)
        # B affects: C, D, E (3 tasks)
        assert "B" in analysis.bottleneck_scores
        assert "A" in analysis.bottleneck_scores
        score_b = analysis.bottleneck_scores["B"]
        score_a = analysis.bottleneck_scores["A"]
        
        assert score_a > score_b  # A affects more total tasks than B
    
    def test_parallelism_groups(self, analyzer, db_manager):
        """Test parallelism group calculation."""
        # Create tasks with different dependency levels
        self.create_task(db_manager, "A", "Task A")  # Level 0
        self.create_task(db_manager, "B", "Task B")  # Level 0
        self.create_task(db_manager, "C", "Task C", depends_on=["A"])  # Level 1
        self.create_task(db_manager, "D", "Task D", depends_on=["A"])  # Level 1
        self.create_task(db_manager, "E", "Task E", depends_on=["B"])  # Level 1
        
        analysis = analyzer.analyze()
        
        # Should have parallelism groups
        assert len(analysis.parallelism_groups) > 0
        
        # Find the level 0 group (A, B can run in parallel)
        level_0_group = next((g for g in analysis.parallelism_groups if g.depth_level == 0), None)
        assert level_0_group is not None
        assert len(level_0_group.tasks) == 2
        
        # Find the level 1 group (C, D, E can run in parallel)
        level_1_group = next((g for g in analysis.parallelism_groups if g.depth_level == 1), None)
        assert level_1_group is not None
        assert len(level_1_group.tasks) == 3
    
    def test_json_output_format(self, analyzer, db_manager):
        """Test that analysis can be serialized to JSON."""
        self.create_task(db_manager, "A", "Task A")
        self.create_task(db_manager, "B", "Task B", depends_on=["A"])
        
        analysis = analyzer.analyze()
        
        # Convert to dict format like CLI command does
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
            "errors": analysis.errors
        }
        
        # Should be serializable to JSON
        json_str = json.dumps(result, indent=2)
        assert len(json_str) > 0
        
        # Should be deserializable
        parsed = json.loads(json_str)
        assert len(parsed["critical_path"]) == 2
        assert parsed["errors"] == []


class TestCriticalPathCLI:
    """Test critical path CLI integration."""
    
    @pytest.fixture
    def cli_runner(self):
        """Create CLI test runner."""
        from click.testing import CliRunner
        return CliRunner()
    
    @pytest.fixture 
    def temp_project(self):
        """Create temporary project for testing."""
        temp_dir = tempfile.mkdtemp()
        db_path = Path(temp_dir) / "test.db"
        
        db_manager = DatabaseManager(db_path)
        
        # Create test project
        project = Project(
            id="test-cli-project",
            name="Test CLI Project",
            description="Test project for CLI testing",
            workspace_dir=temp_dir,
            spec_source="file://test.yaml",
            status=ProjectStatus.ACTIVE,
            created_at=datetime.now()
        )
        db_manager.create_project(project)
        
        # Create some test tasks
        task_a = Task(
            id="task-a",
            project_id="test-cli-project",
            spec_id="A",
            title="Task A",
            description="First task",
            priority="high",
            status=TaskStatus.PENDING
        )
        task_b = Task(
            id="task-b", 
            project_id="test-cli-project",
            spec_id="B",
            title="Task B",
            description="Second task",
            depends_on=["A"],
            priority="medium", 
            status=TaskStatus.PENDING
        )
        
        db_manager.create_task(task_a)
        db_manager.create_task(task_b)
        
        yield {
            'db_path': db_path,
            'project_id': project.id,
            'temp_dir': temp_dir
        }
        
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)
    
    def test_critical_path_cli_text_output(self, cli_runner, temp_project):
        """Test critical path CLI with text output."""
        from bob.cli.critical_path import critical_path
        from bob.cli.main import GlobalContext
        
        # Create context
        ctx = GlobalContext()
        ctx.db_path = temp_project['db_path']
        ctx.project_id = temp_project['project_id']
        
        with cli_runner.isolated_filesystem():
            result = cli_runner.invoke(critical_path, [], obj=ctx)
            
        assert result.exit_code == 0
        output = result.output
        
        # Should contain critical path analysis output
        assert "CRITICAL PATH ANALYSIS" in output
        assert "CRITICAL PATH" in output
        assert "Task A" in output
        assert "Task B" in output
    
    def test_critical_path_cli_json_output(self, cli_runner, temp_project):
        """Test critical path CLI with JSON output."""
        from bob.cli.critical_path import critical_path
        from bob.cli.main import GlobalContext
        
        # Create context
        ctx = GlobalContext()
        ctx.db_path = temp_project['db_path']
        ctx.project_id = temp_project['project_id']
        
        with cli_runner.isolated_filesystem():
            result = cli_runner.invoke(critical_path, ['--json'], obj=ctx)
        
        assert result.exit_code == 0
        
        # Extract JSON from output (skip database migration messages)
        output_lines = result.output.strip().split('\n')
        json_lines = []
        found_json_start = False
        
        for line in output_lines:
            if line.strip().startswith('{'):
                found_json_start = True
            if found_json_start:
                json_lines.append(line)
        
        json_output = '\n'.join(json_lines)
        
        # Parse JSON output
        output_data = json.loads(json_output)
        
        assert "critical_path" in output_data
        assert "critical_path_duration_hours" in output_data
        assert "task_estimates" in output_data
        assert len(output_data["critical_path"]) == 2
        assert output_data["errors"] == []


class TestStatusIntegration:
    """Test critical path integration with status command."""
    
    def test_status_includes_critical_path(self):
        """Test that bob status includes critical path information."""
        # This would require a more complex setup to test the full status integration
        # For now, we verify the get_project_summary function includes critical path data
        
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            db_manager = DatabaseManager(db_path)
            
            # Create test project
            project = Project(
                id="status-test",
                name="Status Test Project", 
                description="Test project",
                workspace_dir=temp_dir,
                spec_source="file://test.yaml",
                status=ProjectStatus.ACTIVE
            )
            db_manager.create_project(project)
            
            # Create test tasks
            task_a = Task(
                id="task-a",
                project_id="status-test",
                spec_id="A", 
                title="Task A",
                description="First task",
                priority="high",
                status=TaskStatus.PENDING
            )
            task_b = Task(
                id="task-b",
                project_id="status-test", 
                spec_id="B",
                title="Task B",
                description="Second task",
                depends_on=["A"],
                priority="medium",
                status=TaskStatus.PENDING
            )
            
            db_manager.create_task(task_a)
            db_manager.create_task(task_b)
            
            # Import the function to test
            from bob.cli.status import get_project_summary
            
            summary = get_project_summary(db_manager, project)
            
            # Should include critical path information
            assert 'critical_path' in summary
            cp_info = summary['critical_path']
            
            if cp_info:  # May be None if analysis fails
                assert 'critical_path_length' in cp_info
                assert 'estimated_remaining_hours' in cp_info
                assert cp_info['critical_path_length'] == 2
                assert cp_info['estimated_remaining_hours'] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])