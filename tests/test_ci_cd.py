"""
Tests for F074: CI/CD setup - GitHub Actions workflows

These tests verify that CI/CD workflows are properly configured:
- test.yml for automated testing on push and PR
- publish.yml for PyPI publication on tag/release
- Workflows run on multiple Python versions
- Workflows include all necessary steps
"""

import os
from pathlib import Path

import pytest
import yaml


class TestTestWorkflow:
    """Test the test.yml GitHub Actions workflow"""

    def test_test_workflow_exists(self):
        """test.yml workflow file should exist"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "test.yml"
        assert workflow_path.exists(), "test.yml workflow should exist"

    def test_test_workflow_is_valid_yaml(self):
        """test.yml should be valid YAML"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "test.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)
        assert workflow is not None, "test.yml should be valid YAML"

    def test_test_workflow_has_name(self):
        """test.yml should have a workflow name"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "test.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)
        assert 'name' in workflow, "Workflow should have a name"

    def test_test_workflow_triggers_on_push(self):
        """test.yml should trigger on push"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "test.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)
        # YAML treats 'on' as True, so check for True key
        triggers = workflow.get('on') or workflow.get(True)
        assert triggers is not None, "Workflow should have triggers"
        assert 'push' in triggers, "Workflow should trigger on push"

    def test_test_workflow_triggers_on_pr(self):
        """test.yml should trigger on pull requests"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "test.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)
        # YAML treats 'on' as True, so check for True key
        triggers = workflow.get('on') or workflow.get(True)
        assert 'pull_request' in triggers, "Workflow should trigger on pull requests"

    def test_test_workflow_has_test_job(self):
        """test.yml should have a test job"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "test.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)
        assert 'jobs' in workflow, "Workflow should have jobs"
        assert 'test' in workflow['jobs'], "Workflow should have test job"

    def test_test_workflow_uses_matrix(self):
        """test.yml should use matrix for multiple Python versions"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "test.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        test_job = workflow['jobs']['test']
        assert 'strategy' in test_job, "Test job should use strategy"
        assert 'matrix' in test_job['strategy'], "Test job should use matrix"

    def test_test_workflow_tests_python_310(self):
        """test.yml should test Python 3.10"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "test.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        matrix = workflow['jobs']['test']['strategy']['matrix']
        python_versions = matrix.get('python-version', [])
        assert '3.10' in python_versions, "Should test Python 3.10"

    def test_test_workflow_tests_python_311(self):
        """test.yml should test Python 3.11"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "test.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        matrix = workflow['jobs']['test']['strategy']['matrix']
        python_versions = matrix.get('python-version', [])
        assert '3.11' in python_versions, "Should test Python 3.11"

    def test_test_workflow_tests_python_312(self):
        """test.yml should test Python 3.12"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "test.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        matrix = workflow['jobs']['test']['strategy']['matrix']
        python_versions = matrix.get('python-version', [])
        assert '3.12' in python_versions, "Should test Python 3.12"

    def test_test_workflow_checks_out_code(self):
        """test.yml should check out code"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "test.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        steps = workflow['jobs']['test']['steps']
        checkout_steps = [s for s in steps if 'actions/checkout' in str(s.get('uses', ''))]
        assert len(checkout_steps) > 0, "Should check out code"

    def test_test_workflow_sets_up_python(self):
        """test.yml should set up Python"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "test.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        steps = workflow['jobs']['test']['steps']
        python_steps = [s for s in steps if 'actions/setup-python' in str(s.get('uses', ''))]
        assert len(python_steps) > 0, "Should set up Python"

    def test_test_workflow_installs_dependencies(self):
        """test.yml should install dependencies"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "test.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        steps = workflow['jobs']['test']['steps']
        # Look for steps that install dependencies
        install_steps = [s for s in steps if 'install' in s.get('name', '').lower()]
        assert len(install_steps) > 0, "Should install dependencies"

    def test_test_workflow_runs_pytest(self):
        """test.yml should run pytest"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "test.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        steps = workflow['jobs']['test']['steps']
        # Look for pytest in any step
        pytest_steps = [s for s in steps if 'pytest' in str(s.get('run', '')).lower()]
        assert len(pytest_steps) > 0, "Should run pytest"

    def test_test_workflow_has_package_build_job(self):
        """test.yml should have a package build test job"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "test.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        # Should have a job that tests package building
        jobs = workflow['jobs']
        build_jobs = [name for name in jobs if 'build' in name.lower() or 'package' in name.lower()]
        assert len(build_jobs) > 0, "Should have a package build test job"


class TestPublishWorkflow:
    """Test the publish.yml GitHub Actions workflow"""

    def test_publish_workflow_exists(self):
        """publish.yml workflow file should exist"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "publish.yml"
        assert workflow_path.exists(), "publish.yml workflow should exist"

    def test_publish_workflow_is_valid_yaml(self):
        """publish.yml should be valid YAML"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "publish.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)
        assert workflow is not None, "publish.yml should be valid YAML"

    def test_publish_workflow_has_name(self):
        """publish.yml should have a workflow name"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "publish.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)
        assert 'name' in workflow, "Workflow should have a name"

    def test_publish_workflow_triggers_on_tag(self):
        """publish.yml should trigger on tag creation"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "publish.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        # YAML treats 'on' as True, so check for True key
        triggers = workflow.get('on') or workflow.get(True)
        assert triggers is not None, "Workflow should have triggers"
        # Should trigger on tags or release
        has_tag_trigger = (
            'push' in triggers and isinstance(triggers.get('push'), dict) and 'tags' in triggers['push']
        ) or 'release' in triggers
        assert has_tag_trigger, "Workflow should trigger on tags or release"

    def test_publish_workflow_has_build_job(self):
        """publish.yml should have a build job"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "publish.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        assert 'jobs' in workflow, "Workflow should have jobs"
        jobs = workflow['jobs']
        build_jobs = [name for name in jobs if 'build' in name.lower()]
        assert len(build_jobs) > 0, "Workflow should have a build job"

    def test_publish_workflow_has_publish_job(self):
        """publish.yml should have a publish job"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "publish.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        jobs = workflow['jobs']
        publish_jobs = [name for name in jobs if 'publish' in name.lower() or 'pypi' in name.lower()]
        assert len(publish_jobs) > 0, "Workflow should have a publish job"

    def test_publish_workflow_builds_package(self):
        """publish.yml should build the package"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "publish.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        # Find build job
        jobs = workflow['jobs']
        build_job_name = [name for name in jobs if 'build' in name.lower()][0]
        build_job = jobs[build_job_name]

        steps = build_job['steps']
        # Should have a step that builds the package
        build_steps = [s for s in steps if 'build' in str(s.get('run', '')).lower() or 'build' in s.get('name', '').lower()]
        assert len(build_steps) > 0, "Should build the package"

    def test_publish_workflow_uses_artifacts(self):
        """publish.yml should use artifacts to pass distributions between jobs"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "publish.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        all_steps = []
        for job in workflow['jobs'].values():
            all_steps.extend(job.get('steps', []))

        # Should have upload-artifact and download-artifact steps
        upload_steps = [s for s in all_steps if 'upload-artifact' in str(s.get('uses', ''))]
        download_steps = [s for s in all_steps if 'download-artifact' in str(s.get('uses', ''))]

        assert len(upload_steps) > 0, "Should upload artifacts"
        assert len(download_steps) > 0, "Should download artifacts"

    def test_publish_workflow_checks_distributions(self):
        """publish.yml should check distributions with twine"""
        workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "publish.yml"
        with open(workflow_path) as f:
            workflow = yaml.safe_load(f)

        all_steps = []
        for job in workflow['jobs'].values():
            all_steps.extend(job.get('steps', []))

        # Should check distributions with twine
        check_steps = [s for s in all_steps if 'twine check' in str(s.get('run', ''))]
        assert len(check_steps) > 0, "Should check distributions with twine"


class TestWorkflowsDirectory:
    """Test GitHub workflows directory structure"""

    def test_workflows_directory_exists(self):
        """GitHub workflows directory should exist"""
        workflows_dir = Path(__file__).parent.parent / ".github" / "workflows"
        assert workflows_dir.exists(), ".github/workflows directory should exist"
        assert workflows_dir.is_dir(), ".github/workflows should be a directory"

    def test_workflows_are_yaml_files(self):
        """All workflow files should be YAML"""
        workflows_dir = Path(__file__).parent.parent / ".github" / "workflows"
        yaml_files = list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml"))
        assert len(yaml_files) > 0, "Should have YAML workflow files"

    def test_all_workflows_parse_successfully(self):
        """All workflow files should parse as valid YAML"""
        workflows_dir = Path(__file__).parent.parent / ".github" / "workflows"
        yaml_files = list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml"))

        for yaml_file in yaml_files:
            with open(yaml_file) as f:
                try:
                    workflow = yaml.safe_load(f)
                    assert workflow is not None, f"{yaml_file.name} should parse as valid YAML"
                except yaml.YAMLError as e:
                    pytest.fail(f"{yaml_file.name} is not valid YAML: {e}")


class TestCICDIntegration:
    """Test CI/CD integration points"""

    def test_requirements_txt_exists_for_ci(self):
        """requirements.txt should exist for CI installation"""
        req_path = Path(__file__).parent.parent / "requirements.txt"
        assert req_path.exists(), "requirements.txt should exist for CI"

    def test_setup_py_exists_for_ci(self):
        """setup.py should exist for CI package building"""
        setup_path = Path(__file__).parent.parent / "setup.py"
        assert setup_path.exists(), "setup.py should exist for CI"

    def test_pytest_ini_or_config(self):
        """Should have pytest configuration (pytest.ini, pyproject.toml, or setup.cfg)"""
        project_root = Path(__file__).parent.parent

        has_pytest_config = (
            (project_root / "pytest.ini").exists() or
            (project_root / "pyproject.toml").exists() or
            (project_root / "setup.cfg").exists()
        )

        assert has_pytest_config, "Should have pytest configuration"

    def test_tests_directory_exists(self):
        """tests/ directory should exist for CI testing"""
        tests_dir = Path(__file__).parent
        assert tests_dir.exists(), "tests/ directory should exist"
        assert tests_dir.is_dir(), "tests/ should be a directory"

    def test_has_test_files(self):
        """Should have test files for CI to run"""
        tests_dir = Path(__file__).parent
        test_files = list(tests_dir.glob("test_*.py"))
        assert len(test_files) > 0, "Should have test files"
