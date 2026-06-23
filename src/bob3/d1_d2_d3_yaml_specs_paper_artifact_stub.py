"""D1, D2, D3 benchmark specification YAML files (paper artifacts).

Three self-contained spec YAML files for the Bob3 sweep orchestrator:
  D1 (ml):  nanoGPT GPT-2-small training on OpenWebText — target ≤25 perplexity
  D2 (pl):  WASM bytecode interpreter — 500-opcode subset
  D3 (hpc): Navier-Stokes lid-driven cavity solver — Re=100, steady state

Each spec uses only machine-verifiable acceptance criteria
(File exists:, pytest:, Function defined:, CLI command:) and is
parseable by the sweep orchestrator's load_sweep_plan / yaml.safe_load.
"""

from __future__ import annotations

import yaml

# ---------------------------------------------------------------------------
# D1 — nanoGPT GPT-2-small on OpenWebText (ML domain)
# ---------------------------------------------------------------------------

SPEC_D1_YAML: str = """\
name: d1-nanogpt-gpt2-openwebtext
version: "1.0.0"
domain: ml
description: |
  Train a GPT-2 small model (124M parameters) on the OpenWebText corpus
  using the nanoGPT implementation. Target validation perplexity ≤25
  after 10 000 training steps with the default nanoGPT hyperparameters.

workspace: /tmp/d1-nanogpt

features:
  F001:
    title: "Project scaffold"
    description: |
      Create the Python package skeleton with pyproject.toml and
      src/nanogpt_d1/ directory.
    priority: critical
    depends_on: []
    acceptance_criteria:
      - "File exists: src/nanogpt_d1/__init__.py"
      - "File exists: pyproject.toml"

  F002:
    title: "Data preparation — tokenize OpenWebText"
    description: |
      Download and tokenize the OpenWebText dataset using the GPT-2
      tiktoken encoder. Write train.bin and val.bin to data/openwebtext/.
    priority: critical
    depends_on: ["F001"]
    acceptance_criteria:
      - "File exists: src/nanogpt_d1/data_prep.py"
      - "Function defined: nanogpt_d1.data_prep.prepare_openwebtext"
      - "pytest: tests/test_data_prep.py::test_prepare_openwebtext_returns_paths"

  F003:
    title: "GPT-2 model definition"
    description: |
      Implement the GPT-2 small architecture: 12 layers, 12 heads,
      768 embedding dimensions, 1024 context window, tied weight embeddings.
    priority: critical
    depends_on: ["F001"]
    acceptance_criteria:
      - "File exists: src/nanogpt_d1/model.py"
      - "Function defined: nanogpt_d1.model.GPT"
      - "pytest: tests/test_model.py::test_gpt2_small_param_count"
      - "pytest: tests/test_model.py::test_forward_pass_shape"

  F004:
    title: "Training loop"
    description: |
      Implement the main training loop with AdamW optimiser, gradient
      clipping at 1.0, cosine LR schedule, and periodic validation-loss
      evaluation. Log perplexity every 500 steps.
    priority: critical
    depends_on: ["F002", "F003"]
    acceptance_criteria:
      - "File exists: src/nanogpt_d1/train.py"
      - "Function defined: nanogpt_d1.train.train"
      - "pytest: tests/test_train.py::test_train_step_decreases_loss"

  F005:
    title: "Perplexity evaluation script"
    description: |
      CLI command `nanogpt-eval --checkpoint <path> --data val.bin`
      that loads a checkpoint and reports validation perplexity.
      Target: ≤25 after full training run.
    priority: high
    depends_on: ["F003", "F004"]
    acceptance_criteria:
      - "File exists: src/nanogpt_d1/eval.py"
      - "CLI command: nanogpt-eval"
      - "pytest: tests/test_eval.py::test_eval_returns_finite_perplexity"
"""

# ---------------------------------------------------------------------------
# D2 — WASM bytecode interpreter, 500-opcode subset (PL domain)
# ---------------------------------------------------------------------------

SPEC_D2_YAML: str = """\
name: d2-wasm-interpreter
version: "1.0.0"
domain: pl
description: |
  A pure-Python WebAssembly (WASM) bytecode interpreter covering a
  500-opcode subset of the MVP instruction set.  Supports the numeric
  types (i32, i64, f32, f64), control flow (block, loop, if, br, br_if,
  return), function calls (call, call_indirect), memory operations
  (i32.load, i32.store, …), and the table/element sections needed for
  indirect calls.

workspace: /tmp/d2-wasm-interp

features:
  F001:
    title: "Project scaffold"
    description: |
      Create src/wasm_interp/ package with pyproject.toml.
    priority: critical
    depends_on: []
    acceptance_criteria:
      - "File exists: src/wasm_interp/__init__.py"
      - "File exists: pyproject.toml"

  F002:
    title: "Binary decoder — parse .wasm module"
    description: |
      Decode the WASM binary format: magic number, version, and all
      standard sections (type, import, function, table, memory, global,
      export, element, code, data).
    priority: critical
    depends_on: ["F001"]
    acceptance_criteria:
      - "File exists: src/wasm_interp/decoder.py"
      - "Function defined: wasm_interp.decoder.decode_module"
      - "pytest: tests/test_decoder.py::test_decode_magic_version"
      - "pytest: tests/test_decoder.py::test_decode_type_section"

  F003:
    title: "Execution engine — value stack and frame stack"
    description: |
      Implement the operand value stack and call-frame stack.
      Each frame holds locals, a label stack, and a program counter.
    priority: critical
    depends_on: ["F002"]
    acceptance_criteria:
      - "File exists: src/wasm_interp/engine.py"
      - "Function defined: wasm_interp.engine.Interpreter"
      - "pytest: tests/test_engine.py::test_push_pop_i32"
      - "pytest: tests/test_engine.py::test_call_frame_locals"

  F004:
    title: "Numeric instructions (i32/i64/f32/f64)"
    description: |
      Implement all arithmetic, comparison, conversion, and bitwise
      instructions for i32, i64, f32, f64 — covering ≥300 opcodes.
    priority: critical
    depends_on: ["F003"]
    acceptance_criteria:
      - "File exists: src/wasm_interp/numeric_ops.py"
      - "pytest: tests/test_numeric_ops.py::test_i32_add"
      - "pytest: tests/test_numeric_ops.py::test_i64_mul"
      - "pytest: tests/test_numeric_ops.py::test_f64_div"
      - "pytest: tests/test_numeric_ops.py::test_trunc_i32_f32"

  F005:
    title: "Control-flow instructions"
    description: |
      Implement block, loop, if/else, br, br_if, br_table, return, and
      unreachable. Label stack correctly tracks block arity.
    priority: critical
    depends_on: ["F003"]
    acceptance_criteria:
      - "File exists: src/wasm_interp/control_flow.py"
      - "pytest: tests/test_control_flow.py::test_block_break"
      - "pytest: tests/test_control_flow.py::test_loop_counter"
      - "pytest: tests/test_control_flow.py::test_if_else_branch"

  F006:
    title: "Memory instructions and linear memory"
    description: |
      Implement linear memory (grow/size), i32/i64/f32/f64 load & store
      with alignment and offset.  Memory bounds trap correctly.
    priority: high
    depends_on: ["F003"]
    acceptance_criteria:
      - "File exists: src/wasm_interp/memory.py"
      - "pytest: tests/test_memory.py::test_i32_store_load_roundtrip"
      - "pytest: tests/test_memory.py::test_memory_bounds_trap"

  F007:
    title: "Integration — run wasm-testsuite subset"
    description: |
      Execute ≥50 spec-testsuite .wast files and assert all assertions
      pass.  CLI: `wasm-run <file.wasm> [--func <name>]`.
    priority: high
    depends_on: ["F004", "F005", "F006"]
    acceptance_criteria:
      - "CLI command: wasm-run"
      - "pytest: tests/test_integration.py::test_run_hello_world_wasm"
      - "pytest: tests/test_integration.py::test_testsuite_i32_spec"
"""

# ---------------------------------------------------------------------------
# D3 — Navier-Stokes lid-driven cavity, Re=100 (HPC domain)
# ---------------------------------------------------------------------------

SPEC_D3_YAML: str = """\
name: d3-navier-stokes-cavity
version: "1.0.0"
domain: hpc
description: |
  Solve the steady-state incompressible Navier-Stokes equations for the
  classic lid-driven square cavity benchmark at Reynolds number Re=100.
  Uses a staggered-grid finite-difference scheme (MAC) with a
  pressure-Poisson solver (Gauss-Seidel or SOR) on a uniform N×N mesh.
  Converge until the L∞ residual of both velocity components is < 1e-6.
  Validate u-velocity profile along the vertical centreline against the
  Ghia et al. (1982) reference data.

workspace: /tmp/d3-cavity-solver

features:
  F001:
    title: "Project scaffold"
    description: |
      Create src/cavity_solver/ Python package with pyproject.toml.
      Dependencies: numpy, scipy, matplotlib.
    priority: critical
    depends_on: []
    acceptance_criteria:
      - "File exists: src/cavity_solver/__init__.py"
      - "File exists: pyproject.toml"

  F002:
    title: "Staggered MAC grid"
    description: |
      Implement the MAC (Marker-and-Cell) staggered-grid layout:
      u-velocity at horizontal cell faces, v-velocity at vertical
      faces, pressure at cell centres.  Provide helper index functions.
    priority: critical
    depends_on: ["F001"]
    acceptance_criteria:
      - "File exists: src/cavity_solver/grid.py"
      - "Function defined: cavity_solver.grid.MACGrid"
      - "pytest: tests/test_grid.py::test_mac_grid_shape"
      - "pytest: tests/test_grid.py::test_mac_grid_index_helpers"

  F003:
    title: "Momentum equations — convection + diffusion"
    description: |
      Discretise the u and v momentum equations with central-difference
      convection and diffusion.  Apply no-slip BCs on three walls and
      the moving lid (u=1) at the top.
    priority: critical
    depends_on: ["F002"]
    acceptance_criteria:
      - "File exists: src/cavity_solver/momentum.py"
      - "Function defined: cavity_solver.momentum.apply_momentum"
      - "pytest: tests/test_momentum.py::test_no_slip_bc"
      - "pytest: tests/test_momentum.py::test_lid_bc"

  F004:
    title: "Pressure-Poisson solver (SOR)"
    description: |
      Solve the pressure-Poisson equation with SOR (ω≈1.5) to enforce
      incompressibility.  Neumann BCs on all walls.
    priority: critical
    depends_on: ["F002"]
    acceptance_criteria:
      - "File exists: src/cavity_solver/pressure.py"
      - "Function defined: cavity_solver.pressure.solve_pressure"
      - "pytest: tests/test_pressure.py::test_pressure_solver_converges"

  F005:
    title: "Time-stepping loop to steady state"
    description: |
      Implement the fractional-step (projection) method:
      (1) advect/diffuse momentum, (2) solve pressure Poisson,
      (3) project velocity.  Iterate until L∞ residual < 1e-6.
    priority: critical
    depends_on: ["F003", "F004"]
    acceptance_criteria:
      - "File exists: src/cavity_solver/solver.py"
      - "Function defined: cavity_solver.solver.solve_cavity"
      - "pytest: tests/test_solver.py::test_solver_reaches_steady_state"

  F006:
    title: "Validation against Ghia et al. (1982)"
    description: |
      Compare computed u-velocity along the vertical centreline at Re=100
      to the Ghia et al. reference tabulation.  Max deviation ≤ 0.01.
    priority: high
    depends_on: ["F005"]
    acceptance_criteria:
      - "File exists: src/cavity_solver/validation.py"
      - "Function defined: cavity_solver.validation.ghia_reference_re100"
      - "pytest: tests/test_validation.py::test_centreline_u_matches_ghia"

  F007:
    title: "CLI — run and plot"
    description: |
      CLI command `cavity-solve --re 100 --n 64 --output result.png`
      that runs the solver and saves a streamline / contour plot.
    priority: high
    depends_on: ["F005"]
    acceptance_criteria:
      - "CLI command: cavity-solve"
      - "pytest: tests/test_cli.py::test_cli_runs_and_produces_output"
"""

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_d1_spec() -> dict:
    """Return the D1 nanoGPT spec as a parsed Python dict."""
    return yaml.safe_load(SPEC_D1_YAML)


def get_d2_spec() -> dict:
    """Return the D2 WASM interpreter spec as a parsed Python dict."""
    return yaml.safe_load(SPEC_D2_YAML)


def get_d3_spec() -> dict:
    """Return the D3 Navier-Stokes cavity spec as a parsed Python dict."""
    return yaml.safe_load(SPEC_D3_YAML)


def get_all_specs() -> list[dict]:
    """Return all three D1/D2/D3 specs as a list of dicts."""
    return [get_d1_spec(), get_d2_spec(), get_d3_spec()]
