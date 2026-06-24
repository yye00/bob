# Spec Constitution v1.0
# Constitutional-AI style quality principles for acceptance criteria

version: "1.0"

## Principles

### P1: No Ambiguity
Every acceptance criterion MUST have a measurable, verifiable outcome.
Criteria containing vague phrases ("works correctly", "handles properly", "supports",
"is good") without a concrete observable predicate are defective.
defect_type: ambiguity

### P2: Edge Cases Required
A feature specification MUST contain at least one criterion that covers a failure path,
boundary condition, or error case when the feature interacts with external data or state.
A spec consisting entirely of happy-path criteria is defective.
defect_type: missing_edge_case

### P3: Testability
Every criterion MUST be machine-verifiable. Criteria that require human judgment,
aesthetics, or subjective evaluation ("looks good", "user-friendly", "intuitive")
cannot be tested and are defective.
defect_type: untestable

### P4: No Implementation Leaks
Criteria MUST specify WHAT, not HOW. References to specific algorithms, data structures,
or implementation details ("uses a hashmap", "calls subprocess", "inherits from X")
are implementation leaks that constrain the implementer unnecessarily.
defect_type: implementation_leak

### P5: Concrete Quantifiers
Any quantifier (count, threshold, rate, duration) MUST be specific.
Vague quantifiers ("fast", "large", "many", "few", "reasonable", "acceptable") are defective.
defect_type: vague_quantifier

### P6: Actor Must Be Named
Every behavioral criterion MUST identify who or what performs the action.
Criteria with missing actor ("shall persist findings", "must reject invalid") are defective.
defect_type: missing_actor

### P7: Integration Targets Must Be Reachable
Any criterion declaring `integration: <module>` MUST reference a module that either
already exists in the workspace OR is declared as a feature in the current spec.
Unreachable integration targets are defective.
defect_type: unreachable_integration
