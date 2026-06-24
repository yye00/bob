"""Tests for F117: Graceful Interruption Handling.

Tests that Bob3 handles SIGINT/SIGTERM gracefully by:
1. Registering signal handlers
2. Setting a graceful_shutdown flag
3. Waiting for current sub-agent to reach safe point (or timeout 30s)
4. Creating checkpoint with current state
5. Updating feature status to 'interrupted'
6. Stopping MCP server gracefully
7. Logging: 'Interrupted. Run bob3 run to resume.'
8. Verifying checkpoint is created on SIGINT
9. Verifying resume after SIGINT continues from checkpoint
"""

import asyncio
import json
import signal
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob3.db import (
    create_feature,
    create_project,
    get_feature,
    init_database,
    list_checkpoints,
    update_feature,
)
from bob3.orchestrator.claude_executor import ExecutionResult, SpawnResult
from bob3.orchestrator.run_loop import (
    LoopTermination,
    OrchestrationLoop,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database with schema initialized."""
    db_path = tmp_path / "test.db"
    init_database(db_path=db_path)
    with patch("bob3.db.get_database_path", return_value=db_path):
        yield db_path


@pytest.fixture
def project(tmp_db):
    """Create a test project."""
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        return create_project(
            name="shutdown-test-project",
            workspace_path="/tmp/shutdown-test",
            max_cost_usd=100.0,
        )


@pytest.fixture
def ready_features(tmp_db, project):
    """Create multiple ready features for testing."""
    with patch("bob3.db.get_database_path", return_value=tmp_db):
        features = []
        for i in range(3):
            f = create_feature(
                project_id=project.id,
                name=f"Feature {i + 1}",
                description=f"Test feature {i + 1}",
                status="ready",
                priority=10 * (i + 1),
                risk_category="medium",
            )
            update_feature(
                f.id,
                conf_spec_understanding=0.9,
                conf_impl_correctness=0.9,
                conf_test_adequacy=0.9,
                readiness_score=0.9,
            )
            features.append(get_feature(f.id))
        return features


# ============================================================
# Step 1: Register signal handlers for SIGINT, SIGTERM
# ============================================================


class TestSignalHandlerRegistration:
    """Step 1: Signal handlers are registered for SIGINT and SIGTERM."""

    def test_install_signal_handlers_registers_sigint(self, tmp_db, project):
        """Signal handler is installed for SIGINT."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            original_handler = signal.getsignal(signal.SIGINT)
            try:
                loop._install_signal_handlers()
                handler = signal.getsignal(signal.SIGINT)
                # Handler should be a function (not default or ignore)
                assert callable(handler)
                assert handler is not signal.SIG_DFL
                assert handler is not signal.SIG_IGN
            finally:
                signal.signal(signal.SIGINT, original_handler)

    def test_install_signal_handlers_registers_sigterm(self, tmp_db, project):
        """Signal handler is installed for SIGTERM."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            original_handler = signal.getsignal(signal.SIGTERM)
            try:
                loop._install_signal_handlers()
                handler = signal.getsignal(signal.SIGTERM)
                assert callable(handler)
                assert handler is not signal.SIG_DFL
                assert handler is not signal.SIG_IGN
            finally:
                signal.signal(signal.SIGTERM, original_handler)


# ============================================================
# Step 2: On signal, set graceful_shutdown flag
# ============================================================


class TestGracefulShutdownFlag:
    """Step 2: Signal handler sets the graceful_shutdown flag."""

    def test_signal_handler_sets_shutdown_flag(self, tmp_db, project):
        """Receiving a signal sets shutdown_requested to True."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            assert loop.shutdown_requested is False
            loop.request_shutdown()
            assert loop.shutdown_requested is True

    def test_signal_handler_via_installed_handler(self, tmp_db, project):
        """The installed signal handler calls request_shutdown."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            original_handler = signal.getsignal(signal.SIGUSR1)
            try:
                # Install handlers (uses SIGINT/SIGTERM, but we test the mechanism)
                loop._install_signal_handlers()
                # Directly invoke the handler that was installed
                handler = signal.getsignal(signal.SIGINT)
                handler(signal.SIGINT, None)
                assert loop.shutdown_requested is True
            finally:
                signal.signal(signal.SIGINT, original_handler if original_handler != signal.SIG_DFL else signal.SIG_DFL)


# ============================================================
# Step 3: Wait for current sub-agent to reach safe point (or timeout 30s)
# ============================================================


class TestWaitForSafePoint:
    """Step 3: On shutdown, wait for current sub-agent to finish or timeout."""

    @pytest.mark.asyncio
    async def test_shutdown_waits_for_current_feature(self, tmp_db, project, ready_features):
        """Loop finishes the current feature before shutting down."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            call_count = 0

            async def mock_spawn(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                # Request shutdown during first feature execution
                if call_count == 1:
                    loop.request_shutdown()
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text=f"Done {call_count}",
                        is_error=False,
                        duration_ms=1000,
                        num_turns=5,
                        total_cost_usd=0.50,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                termination = await loop.run()

            # First feature was completed, then loop stopped
            assert call_count == 1
            assert termination == LoopTermination.SHUTDOWN_REQUESTED
            # First feature should be completed (not interrupted) because it finished
            updated = get_feature(ready_features[0].id)
            assert updated.status == "completed"


# ============================================================
# Step 4: Create checkpoint with current state
# ============================================================


class TestCheckpointCreation:
    """Step 4: Checkpoint is created when shutdown is requested during execution."""

    @pytest.mark.asyncio
    async def test_checkpoint_created_on_shutdown(self, tmp_db, project, ready_features):
        """A checkpoint is created when shutdown is triggered during execution."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            async def mock_spawn_interrupted(*args, **kwargs):
                # Simulate the sub-agent being interrupted mid-execution
                loop.request_shutdown()
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="Partial work",
                        is_error=True,
                        error_message="Interrupted",
                        duration_ms=5000,
                        num_turns=3,
                        total_cost_usd=0.30,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_interrupted,
            ):
                termination = await loop.run()

            assert termination == LoopTermination.SHUTDOWN_REQUESTED

            # A checkpoint should have been created for the feature
            feature = ready_features[0]
            checkpoints = list_checkpoints(feature_id=feature.id)
            assert len(checkpoints) >= 1
            cp = checkpoints[-1]
            assert cp.checkpoint_type == "interruption"
            state = json.loads(cp.state_snapshot)
            assert state["reason"] == "graceful_shutdown"

    @pytest.mark.asyncio
    async def test_checkpoint_stores_cost_and_duration(self, tmp_db, project, ready_features):
        """Checkpoint stores cost accumulated so far."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            async def mock_spawn_interrupted(*args, **kwargs):
                loop.request_shutdown()
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="Partial",
                        is_error=True,
                        error_message="Interrupted",
                        duration_ms=15000,
                        num_turns=5,
                        total_cost_usd=1.75,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_interrupted,
            ):
                await loop.run()

            feature = ready_features[0]
            checkpoints = list_checkpoints(feature_id=feature.id)
            assert len(checkpoints) >= 1
            cp = checkpoints[-1]
            assert cp.cost_at_checkpoint is not None
            assert cp.cost_at_checkpoint > 0


# ============================================================
# Step 5: Update feature status to 'interrupted'
# ============================================================


class TestFeatureInterruptedStatus:
    """Step 5: Feature status is set to 'interrupted' (not 'failed') on shutdown."""

    @pytest.mark.asyncio
    async def test_feature_set_to_interrupted_on_shutdown(self, tmp_db, project, ready_features):
        """Feature that was executing when shutdown was requested is marked 'interrupted'."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            async def mock_spawn_interrupted(*args, **kwargs):
                loop.request_shutdown()
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="Partial",
                        is_error=True,
                        error_message="Interrupted",
                        duration_ms=3000,
                        num_turns=2,
                        total_cost_usd=0.20,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_interrupted,
            ):
                await loop.run()

            feature = ready_features[0]
            updated = get_feature(feature.id)
            assert updated.status == "interrupted"

    @pytest.mark.asyncio
    async def test_successful_feature_stays_completed_even_with_shutdown(
        self, tmp_db, project, ready_features
    ):
        """Feature that completed successfully before shutdown stays 'completed'."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            async def mock_spawn_then_shutdown(*args, **kwargs):
                loop.request_shutdown()
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="Completed successfully",
                        is_error=False,
                        duration_ms=5000,
                        num_turns=10,
                        total_cost_usd=0.50,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_then_shutdown,
            ):
                await loop.run()

            feature = ready_features[0]
            updated = get_feature(feature.id)
            # Completed successfully, so stays completed even though shutdown was requested
            assert updated.status == "completed"


# ============================================================
# Step 6: Stop MCP server gracefully
# ============================================================


class TestMCPServerGracefulStop:
    """Step 6: MCP server is stopped gracefully on interruption."""

    @pytest.mark.asyncio
    async def test_mcp_stop_called_on_shutdown(self, tmp_db, project, ready_features):
        """stop_mcp_server is called when loop terminates via shutdown."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            async def mock_spawn(*args, **kwargs):
                loop.request_shutdown()
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="Done",
                        is_error=False,
                        duration_ms=1000,
                        num_turns=5,
                        total_cost_usd=0.50,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                with patch(
                    "bob3.orchestrator.run_loop.stop_mcp_server"
                ) as mock_stop:
                    termination = await loop.run()

            assert termination == LoopTermination.SHUTDOWN_REQUESTED
            mock_stop.assert_called_once()


# ============================================================
# Step 7: Log: 'Interrupted. Run bob3 run to resume.'
# ============================================================


class TestInterruptionLogMessage:
    """Step 7: Log message about resuming is emitted on interruption."""

    @pytest.mark.asyncio
    async def test_log_message_on_shutdown(self, tmp_db, project, ready_features):
        """'Interrupted. Run bob3 run to resume.' is logged on shutdown."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)

            async def mock_spawn(*args, **kwargs):
                loop.request_shutdown()
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="Done",
                        is_error=False,
                        duration_ms=1000,
                        num_turns=5,
                        total_cost_usd=0.50,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ):
                with patch("bob3.orchestrator.run_loop.stop_mcp_server"):
                    with patch("bob3.orchestrator.run_loop.logger") as mock_logger:
                        await loop.run()

            # Check that the resume message was logged
            log_messages = [
                str(call) for call in mock_logger.info.call_args_list
            ]
            found = any("Interrupted" in msg and "resume" in msg for msg in log_messages)
            assert found, f"Expected log about 'Interrupted...resume' but got: {log_messages}"


# ============================================================
# Step 8: Test: Start bob3, send SIGINT, verify checkpoint created
# ============================================================


class TestSIGINTCreatesCheckpoint:
    """Step 8: Sending SIGINT to a running loop creates a checkpoint."""

    @pytest.mark.asyncio
    async def test_sigint_triggers_checkpoint(self, tmp_db, project, ready_features):
        """Simulating SIGINT during execution creates checkpoint and returns SHUTDOWN_REQUESTED."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            feature = ready_features[0]

            async def mock_spawn_slow(*args, **kwargs):
                # Simulate the signal handler being called during execution
                loop.request_shutdown()
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="Partial implementation",
                        is_error=True,
                        error_message="Agent was interrupted",
                        duration_ms=8000,
                        num_turns=4,
                        total_cost_usd=0.80,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_slow,
            ):
                with patch("bob3.orchestrator.run_loop.stop_mcp_server"):
                    termination = await loop.run()

            assert termination == LoopTermination.SHUTDOWN_REQUESTED

            # Verify checkpoint was created
            checkpoints = list_checkpoints(feature_id=feature.id)
            assert len(checkpoints) >= 1
            cp = checkpoints[-1]
            assert cp.checkpoint_type == "interruption"
            assert cp.feature_id == feature.id
            assert cp.project_id == project.id


# ============================================================
# Step 9: Test: Resume after SIGINT, verify continues from checkpoint
# ============================================================


class TestResumeAfterInterruption:
    """Step 9: After SIGINT, resuming picks up interrupted features."""

    @pytest.mark.asyncio
    async def test_interrupted_feature_is_resumable(self, tmp_db, project, ready_features):
        """An interrupted feature can be resumed by a new loop run."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop1 = OrchestrationLoop(project_id=project.id)
            feature = ready_features[0]

            # First run: gets interrupted
            async def mock_spawn_interrupt(*args, **kwargs):
                loop1.request_shutdown()
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="Partial",
                        is_error=True,
                        error_message="Interrupted",
                        duration_ms=5000,
                        num_turns=3,
                        total_cost_usd=0.30,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_interrupt,
            ):
                with patch("bob3.orchestrator.run_loop.stop_mcp_server"):
                    await loop1.run()

            # The feature should be 'interrupted'
            updated = get_feature(feature.id)
            assert updated.status == "interrupted"

            # Set the interrupted feature back to 'ready' (simulating resume logic)
            update_feature(feature.id, status="ready")

            # Second run: completes successfully
            loop2 = OrchestrationLoop(project_id=project.id)
            call_count = 0

            async def mock_spawn_success(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text=f"Completed feature {call_count}",
                        is_error=False,
                        duration_ms=2000,
                        num_turns=5,
                        total_cost_usd=0.50,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_success,
            ):
                termination = await loop2.run()

            assert termination == LoopTermination.ALL_COMPLETED
            # All 3 features should now be completed
            for f in ready_features:
                assert get_feature(f.id).status == "completed"

    @pytest.mark.asyncio
    async def test_checkpoint_contains_feature_state(self, tmp_db, project, ready_features):
        """Checkpoint state_snapshot contains useful feature state for resume."""
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop = OrchestrationLoop(project_id=project.id)
            feature = ready_features[0]

            async def mock_spawn_interrupt(*args, **kwargs):
                loop.request_shutdown()
                return SpawnResult(
                    execution_result=ExecutionResult(
                        text="Partial work done",
                        is_error=True,
                        error_message="Interrupted",
                        duration_ms=5000,
                        num_turns=3,
                        total_cost_usd=0.30,
                    ),
                    agent_run=MagicMock(id=str(uuid.uuid4())),
                )

            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn_interrupt,
            ):
                with patch("bob3.orchestrator.run_loop.stop_mcp_server"):
                    await loop.run()

            checkpoints = list_checkpoints(feature_id=feature.id)
            assert len(checkpoints) >= 1
            cp = checkpoints[-1]
            state = json.loads(cp.state_snapshot)
            assert "feature_id" in state
            assert "feature_name" in state
            assert "feature_status" in state
            assert state["feature_id"] == feature.id
            assert state["reason"] == "graceful_shutdown"


# ============================================================
# Step 10: Signal handler is async-signal-safe (no DB/subprocess I/O)
# ============================================================


class TestSignalHandlerIsAsyncSignalSafe:
    """The signal handler itself must NOT do DB or subprocess I/O.

    Per POSIX, signal handlers should be async-signal-safe. Performing
    arbitrary I/O — especially database commits and subprocess control
    — can deadlock when the signal interrupts code that already holds
    a non-reentrant lock (e.g., ``conn.commit()`` on the main thread).

    The contract is:
      * ``_handle_signal`` only sets ``shutdown_requested`` and logs.
      * The actual shutdown work happens in ``_perform_shutdown``,
        which is called from regular (non-handler) code paths.
    """

    def test_handler_does_not_call_db_create_checkpoint(self):
        """``_handle_signal`` must not invoke ``db.create_checkpoint``."""
        from bob3.signal_handler import GracefulShutdownHandler

        handler = GracefulShutdownHandler(
            conn=MagicMock(name="sqlite_conn"),
            project_id="proj-1",
        )
        handler.set_active_feature(
            feature_id="feat-1",
            feature_data={"name": "f1", "status": "executing"},
            execution_start_ms=0,
            cost_so_far=0.1,
        )

        # The handler must not perform any DB or subprocess I/O from
        # signal context. We patch the I/O surfaces and verify the
        # handler doesn't reach for them.
        with patch(
            "bob3.db.create_checkpoint"
        ) as create_cp, patch(
            "bob3.db.update_feature"
        ) as upd, patch(
            "bob3.mcp_lifecycle.stop_mcp_server"
        ) as stop_mcp:
            handler._handle_signal(signal.SIGINT, None)

            # The flag must be set...
            assert handler.shutdown_requested is True
            # ...but no I/O must have happened from the handler.
            create_cp.assert_not_called()
            upd.assert_not_called()
            stop_mcp.assert_not_called()

    def test_handler_does_not_commit_connection(self):
        """``_handle_signal`` must not call ``conn.commit()``.

        The main deadlock scenario the spec calls out: SIGINT firing
        while the main loop is inside ``conn.commit()`` would re-enter
        the SQLite connection lock and deadlock the process. The
        handler must not touch ``self._conn`` at all.
        """
        from bob3.signal_handler import GracefulShutdownHandler

        mock_conn = MagicMock(name="sqlite_conn")
        handler = GracefulShutdownHandler(conn=mock_conn, project_id="proj-1")
        handler.set_active_feature(
            feature_id="feat-1",
            feature_data={"name": "f1", "status": "executing"},
        )

        handler._handle_signal(signal.SIGTERM, None)

        assert handler.shutdown_requested is True
        # No call whatsoever to the connection from handler context.
        mock_conn.commit.assert_not_called()
        mock_conn.execute.assert_not_called()
        mock_conn.cursor.assert_not_called()

    def test_double_signal_raises_systemexit(self):
        """A second signal during shutdown raises :class:`SystemExit`.

        Once ``shutdown_requested`` is already set, the next signal
        forces immediate exit. ``SystemExit`` from a handler is allowed
        (it unwinds via the regular exception path).
        """
        from bob3.signal_handler import GracefulShutdownHandler

        handler = GracefulShutdownHandler(
            conn=MagicMock(name="sqlite_conn"),
            project_id="proj-1",
        )

        # First signal: set the flag, no SystemExit.
        handler._handle_signal(signal.SIGINT, None)
        assert handler.shutdown_requested is True

        # Second signal: SystemExit with code 128 + signum.
        with pytest.raises(SystemExit) as exc:
            handler._handle_signal(signal.SIGINT, None)
        assert exc.value.code == 128 + signal.SIGINT

    def test_flag_visible_to_polling_caller(self):
        """After the handler runs, a polling caller sees the flag.

        This mirrors what the orchestration loop does: poll
        ``shutdown_requested`` at a safe point between feature
        executions, then perform its own shutdown sequence.
        """
        from bob3.signal_handler import GracefulShutdownHandler

        handler = GracefulShutdownHandler(
            conn=MagicMock(name="sqlite_conn"),
            project_id="proj-1",
        )

        # Before the signal, the flag is False.
        assert handler.shutdown_requested is False

        # Simulate signal arrival.
        handler._handle_signal(signal.SIGINT, None)

        # The polling caller (main loop) sees the new value at the next
        # safe point.
        assert handler.shutdown_requested is True


# ============================================================
# Step 10b: The ACTUAL signal handler installed by the production
# orchestration loop is async-signal-safe.
# ============================================================


class TestOrchestrationLoopSignalHandlerIsAsyncSignalSafe:
    """``OrchestrationLoop._install_signal_handlers`` installs an inline
    closure as the SIGINT/SIGTERM handler — NOT the
    ``GracefulShutdownHandler`` class exercised by
    :class:`TestSignalHandlerIsAsyncSignalSafe`.

    The ``GracefulShutdownHandler`` tests above gave false confidence
    that the production signal path is async-signal-safe, because
    nothing in production actually installs that class. This test
    class instead inspects the handler that ``_install_signal_handlers``
    *actually* puts into ``signal.getsignal``, calls it directly with
    a synthetic signum/frame, and verifies that:

      1. it does NOT touch any DB function or DB-touching helper;
      2. it does NOT touch the MCP subprocess machinery;
      3. it sets ``loop.shutdown_requested = True`` afterwards (the
         flag the polling main-loop reads at safe points).

    This is the "test what production calls, not the handler API
    surface" invariant called out in the signal-safety recurring
    pattern.
    """

    def _install_and_get_real_handler(self, project):
        """Create a loop, install handlers, and return (loop, handler).

        Restoring SIGINT/SIGTERM is handled by the autouse fixture in
        ``conftest.py`` (it captures and restores them around every
        test), so we don't need to do it ourselves.
        """
        loop = OrchestrationLoop(project_id=project.id)
        loop._install_signal_handlers()

        installed_sigint = signal.getsignal(signal.SIGINT)
        installed_sigterm = signal.getsignal(signal.SIGTERM)

        # Sanity: the loop installed something (not the default int
        # handler, not SIG_DFL/SIG_IGN, not None).
        assert installed_sigint is not None
        assert callable(installed_sigint), (
            "_install_signal_handlers should install a callable for SIGINT"
        )
        assert callable(installed_sigterm), (
            "_install_signal_handlers should install a callable for SIGTERM"
        )
        # And what it installed is the same callable for both signals
        # (the inline closure inside ``_install_signal_handlers``).
        assert installed_sigint is installed_sigterm, (
            "Both SIGINT and SIGTERM should map to the same closure"
        )
        return loop, installed_sigint

    def test_installed_handler_does_not_touch_db_or_mcp(self, tmp_db, project):
        """The actual installed SIGINT closure must be async-signal-safe.

        We patch every DB and subprocess surface the handler could
        plausibly reach for and verify zero calls land on any of them
        when the handler is invoked. This pins the contract that the
        handler ONLY sets a flag.
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop, handler = self._install_and_get_real_handler(project)

            # Pre-state: the loop has not been told to shut down.
            assert loop.shutdown_requested is False

            with patch(
                "bob3.db.create_checkpoint"
            ) as create_cp, patch(
                "bob3.db.update_feature"
            ) as upd_feat, patch(
                "bob3.db.update_project_cost"
            ) as upd_cost, patch(
                "bob3.mcp_lifecycle.stop_mcp_server"
            ) as stop_mcp:
                # Call the actual production handler with a synthetic
                # signum/frame. SIGINT (vs SIGTERM) doesn't matter for
                # the contract; either signal must satisfy it.
                handler(signal.SIGINT, None)

            # The flag must flip — that is the entire job of the
            # handler, and the only piece of "real work" it is allowed
            # to do.
            assert loop.shutdown_requested is True

            # And NO I/O must have happened from the handler.
            create_cp.assert_not_called()
            upd_feat.assert_not_called()
            upd_cost.assert_not_called()
            stop_mcp.assert_not_called()

    def test_installed_handler_handles_sigterm_same_way(self, tmp_db, project):
        """SIGTERM must behave identically to SIGINT.

        The closure conditions on ``signum`` only for the log message;
        the contract (set flag, no I/O) must hold for both signals.
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop, handler = self._install_and_get_real_handler(project)

            with patch(
                "bob3.db.create_checkpoint"
            ) as create_cp, patch(
                "bob3.db.update_feature"
            ) as upd_feat, patch(
                "bob3.mcp_lifecycle.stop_mcp_server"
            ) as stop_mcp:
                handler(signal.SIGTERM, None)

            assert loop.shutdown_requested is True
            create_cp.assert_not_called()
            upd_feat.assert_not_called()
            stop_mcp.assert_not_called()

    def test_installed_handler_second_signal_forces_systemexit(
        self, tmp_db, project
    ):
        """A second signal during shutdown must force-exit.

        Production behaviour: first Ctrl-C requests graceful shutdown,
        second Ctrl-C raises SystemExit so the user can escape a stuck
        sub-agent. We verify on the *installed* handler.
        """
        with patch("bob3.db.get_database_path", return_value=tmp_db):
            loop, handler = self._install_and_get_real_handler(project)

            # First signal: sets the flag, returns normally.
            handler(signal.SIGINT, None)
            assert loop.shutdown_requested is True

            # Second signal: must raise SystemExit. We don't pin the
            # exact code because that's a documented detail of the
            # closure, but it must propagate as SystemExit (not
            # SystemError, not RuntimeError).
            with pytest.raises(SystemExit):
                handler(signal.SIGINT, None)
