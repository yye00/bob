# Contributing to BOB

Thank you for your interest in contributing to BOB (Build Orchestration Bot)! This document provides guidelines for contributing to the project.

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/bob.git
cd bob
```

2. Run the setup script:
```bash
./init.sh
source venv/bin/activate
```

3. Install development dependencies:
```bash
pip install -r requirements-dev.txt
```

## Code Style

- Follow PEP 8 style guidelines
- Use type hints for all function signatures
- Write docstrings for all public functions and classes
- Use `black` for code formatting: `black bob/`
- Use `isort` for import sorting: `isort bob/`
- Use `mypy` for type checking: `mypy bob/`

## Testing

- Write tests for all new features
- Maintain test coverage above 80%
- Run tests before submitting PR: `pytest`
- Run with coverage: `pytest --cov=bob --cov-report=html`

## Feature Development Workflow

1. Check the `feature_list.json` for planned features
2. Create a new branch: `git checkout -b feature/F042-my-feature`
3. Implement the feature following the steps in the feature definition
4. Write tests for the feature
5. Update feature status to "passes": true when complete
6. Commit with reference to feature ID: `git commit -m "F042: Implement feature XYZ"`
7. Create a pull request

## Pull Request Process

1. Update the README.md with details of changes if needed
2. Update the feature_list.json to mark features as passing
3. Ensure all tests pass
4. Ensure code coverage is maintained
5. Update documentation if you're changing functionality
6. The PR will be merged once you have approval from maintainers

## Feature List Guidelines

- **NEVER** remove features from feature_list.json
- **NEVER** change feature IDs
- Only change "passes": false to "passes": true
- Mark features as deprecated if no longer needed (set "deprecated": true)
- Add "passed_at" timestamp when marking as passing
- Expand steps if needed, but set "needs_reverification": true if already passing

## Architecture Guidelines

### Adding New Spec Sources

1. Inherit from `SpecSource` base class
2. Implement all abstract methods: `fetch_tasks()`, `sync()`, `mark_completed()`
3. Register in spec source registry
4. Add tests for the new source
5. Document in `docs/spec-formats.md`

### Adding New Agents

1. Define agent type in `AgentType` enum
2. Create agent configuration in project.yaml
3. Add prompt template in `prompts/`
4. Register agent in agent registry
5. Add tests for agent behavior

### Adding New Plugins

1. Inherit from appropriate plugin base class
2. Implement required methods
3. Add plugin metadata (name, version)
4. Document in `docs/plugins.md`
5. Add example plugin in `examples/plugins/`

## Database Migrations

When modifying the database schema:

1. Create migration script in `database/migrations/`
2. Update schema version
3. Test migration on existing database
4. Document changes in migration file

## Documentation

- Update relevant documentation in `docs/`
- Add examples for new features in `examples/`
- Update CLI help text for new commands
- Keep README.md up to date

## Questions?

If you have questions, please:
- Open an issue for discussion
- Join our Discord community
- Email the maintainers

## Code of Conduct

Be respectful, inclusive, and professional in all interactions.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
