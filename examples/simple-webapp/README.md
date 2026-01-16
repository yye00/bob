# Simple Todo Web App - BOB Example

This is an example project specification for BOB (Build Orchestration Bot) that demonstrates how to define a complete web application as a series of tasks.

## What This Example Shows

- **Task dependencies**: How to define what must be built before other components
- **Different priorities**: Critical (1) to nice-to-have (4)
- **Multiple categories**: functional, style, test, docs
- **Acceptance criteria**: Clear success conditions for each task
- **Implementation steps**: Guidance for the AI agent

## Project Structure

This spec defines a simple full-stack todo application:

```
Backend (Node.js + Express + TypeScript + SQLite)
    ↓
Frontend (React + Vite + TypeScript)
    ↓
Styling + Error Handling
    ↓
Testing + Documentation + Docker
```

## Running This Example with BOB

Once BOB is implemented, you'll be able to run:

```bash
# Create the project
bob project create todo-app \
  --spec examples/simple-webapp/spec.yaml \
  --workspace ./workspace/todo-app

# Run the agent
bob run --project todo-app

# Monitor progress
bob status --project todo-app
bob logs --follow
```

BOB will:
1. Execute tasks in dependency order (backend → database → API → frontend → UI)
2. Run independent tasks in parallel (frontend-init can run alongside database-setup)
3. Escalate to more powerful models if tasks fail
4. Track costs and progress

## Expected Outcome

After BOB completes all tasks, you'll have:
- A working todo application
- Backend API with 4 endpoints
- React frontend with CRUD operations
- Basic styling
- Error handling
- Tests
- Documentation
- Docker setup for deployment

## Learning from This Example

Study this spec to learn:
- How to break down a project into tasks
- How to define dependencies (depends_on)
- How to write clear acceptance criteria
- How to provide implementation guidance
- How to structure a multi-tier application
