# Spec Formats

BOB supports multiple specification formats for defining project tasks. Choose the format that best fits your workflow.

## Supported Formats

- **YAML** - Most popular, readable, supports comments
- **JSON** - Strict, machine-friendly, good for generation
- **Markdown** - Human-friendly, good for documentation-first
- **GitHub Issues** - Use GitHub as spec source with auto-sync
- **Custom** - Extend via plugins (Jira, Linear, etc.)

## YAML Format (Recommended)

### Basic Structure

```yaml
name: Project Name
description: Project description

defaults:
  priority: medium
  category: functional

tasks:
  - id: task-1
    title: Task Title
    description: Detailed description
    priority: high  # critical, high, medium, low
    category: functional  # functional, test, infra, docs
    depends_on: []  # Task IDs this depends on
    research_required: false
    research_queries: []
    acceptance_criteria:
      - Criterion 1
      - Criterion 2
    steps:
      - Step 1
      - Step 2
```

### Complete Example

```yaml
name: E-Commerce API
description: RESTful API for e-commerce platform

defaults:
  priority: medium
  category: functional

tasks:
  # Setup tasks
  - id: setup-project
    title: Initialize Project Structure
    description: |
      Set up the basic project structure with dependencies,
      configuration files, and directory layout.
    priority: critical
    category: infra
    acceptance_criteria:
      - Project directory structure created
      - package.json with required dependencies
      - TypeScript configured
      - ESLint and Prettier set up
    steps:
      - Create project directory
      - Initialize npm project
      - Install TypeScript, Express, and dev dependencies
      - Create tsconfig.json
      - Set up linting and formatting
      - Create basic directory structure (src/, tests/, etc.)

  - id: setup-database
    title: Database Setup
    description: Configure PostgreSQL with migrations and seed data
    priority: critical
    category: infra
    depends_on: [setup-project]
    acceptance_criteria:
      - PostgreSQL connection working
      - Migration system in place
      - Seed data script created
    steps:
      - Install database libraries (pg, knex)
      - Create database connection module
      - Set up migration system
      - Create initial schema migration
      - Add seed data script

  # Feature tasks
  - id: user-auth
    title: User Authentication
    description: |
      Implement JWT-based authentication with secure token storage.
      This task requires research on current best practices.
    priority: high
    category: functional
    depends_on: [setup-project, setup-database]
    research_required: true
    research_queries:
      - "JWT token storage best practices 2026"
      - "Secure session management Node.js Express"
      - "Password hashing algorithms comparison bcrypt argon2"
    acceptance_criteria:
      - User registration endpoint works
      - Login endpoint returns JWT token
      - Password hashing implemented securely
      - Token validation middleware working
      - Refresh token mechanism in place
    steps:
      - Research best practices for JWT storage
      - Implement password hashing
      - Create user registration endpoint
      - Create login endpoint
      - Implement JWT generation and validation
      - Add authentication middleware
      - Add refresh token logic
      - Write unit tests

  - id: product-catalog
    title: Product Catalog API
    description: CRUD operations for product management
    priority: high
    category: functional
    depends_on: [setup-database, user-auth]
    acceptance_criteria:
      - GET /products returns paginated list
      - GET /products/:id returns single product
      - POST /products creates new product (auth required)
      - PUT /products/:id updates product (auth required)
      - DELETE /products/:id deletes product (auth required)
      - Input validation working
    steps:
      - Create product model and migration
      - Implement GET /products with pagination
      - Implement GET /products/:id
      - Implement POST /products with auth middleware
      - Implement PUT /products/:id
      - Implement DELETE /products/:id
      - Add input validation
      - Write integration tests

  # Testing tasks
  - id: integration-tests
    title: Integration Test Suite
    description: Comprehensive integration tests for all endpoints
    priority: medium
    category: test
    depends_on: [user-auth, product-catalog]
    acceptance_criteria:
      - All endpoints have integration tests
      - Tests cover success and error cases
      - Test coverage above 80%
    steps:
      - Set up test database
      - Write auth endpoint tests
      - Write product endpoint tests
      - Add error case tests
      - Generate coverage report
```

### Task Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique task identifier |
| `title` | string | Yes | Short title |
| `description` | string | Yes | Detailed description |
| `priority` | enum | No | critical, high, medium, low (default: medium) |
| `category` | enum | No | functional, test, infra, docs (default: functional) |
| `depends_on` | list | No | List of task IDs that must complete first |
| `research_required` | boolean | No | If true, run research before implementing |
| `research_queries` | list | No | Suggested research queries |
| `acceptance_criteria` | list | No | How to verify task is complete |
| `steps` | list | No | Implementation steps |

## JSON Format

Same structure as YAML, but in JSON:

```json
{
  "name": "E-Commerce API",
  "description": "RESTful API for e-commerce platform",
  "defaults": {
    "priority": "medium",
    "category": "functional"
  },
  "tasks": [
    {
      "id": "setup-project",
      "title": "Initialize Project Structure",
      "description": "Set up basic project structure",
      "priority": "critical",
      "category": "infra",
      "depends_on": [],
      "acceptance_criteria": [
        "Project directory structure created",
        "package.json with required dependencies"
      ],
      "steps": [
        "Create project directory",
        "Initialize npm project"
      ]
    }
  ]
}
```

## Markdown Format

Uses markdown with YAML frontmatter:

```markdown
---
name: E-Commerce API
description: RESTful API for e-commerce platform
---

# E-Commerce API Project

## Task: setup-project
**Priority**: critical
**Category**: infra
**ID**: setup-project

Initialize the project structure with all dependencies.

**Acceptance Criteria:**
- Project directory structure created
- package.json with required dependencies
- TypeScript configured

**Steps:**
1. Create project directory
2. Initialize npm project
3. Install dependencies

---

## Task: user-auth
**Priority**: high
**Category**: functional
**Depends on**: setup-project, setup-database
**Research Required**: Yes

Implement JWT-based authentication.

**Research Queries:**
- JWT token storage best practices 2026
- Secure session management Node.js

**Acceptance Criteria:**
- User registration works
- Login returns JWT token

**Steps:**
1. Research best practices
2. Implement password hashing
3. Create endpoints
```

## GitHub Issues Format

Use GitHub issues with labels as spec source:

### Setup

```bash
bob project create my-project ./workspace \
  github://owner/repo/issues \
  --description "Project from GitHub"
```

### Issue Format

Title: Task title (becomes task `title`)
Body:
```markdown
Implement user authentication feature.

## Priority
high

## Category
functional

## Depends On
- #12 (setup-project)
- #15 (setup-database)

## Research Required
Yes

## Research Queries
- JWT best practices 2026
- Secure password hashing

## Acceptance Criteria
- User registration endpoint works
- Login endpoint returns JWT

## Steps
1. Research JWT storage
2. Implement password hashing
3. Create endpoints
4. Write tests
```

Labels:
- `ai-implement` - Required label to include in spec
- `priority:high` - Sets priority
- `category:functional` - Sets category

### Auto-sync

BOB automatically syncs with GitHub:

```bash
# Enable auto-sync
bob sync enable --source github

# Manual sync
bob sync run

# View sync status
bob sync status
```

When syncing:
- New issues → New tasks
- Updated issues → Updated tasks
- Closed issues → Completed tasks
- New comments → Task notes

## Custom Spec Sources (Plugins)

Create custom spec source plugins for Jira, Linear, etc.

See [Plugins Guide](plugins.md) for details.

## Best Practices

### 1. Use Clear IDs

```yaml
# Good
id: setup-database
id: user-auth-jwt
id: product-catalog-api

# Bad
id: task1
id: db
id: auth
```

### 2. Explicit Dependencies

```yaml
# Good - Clear dependencies
- id: product-api
  depends_on: [setup-database, user-auth]

# Bad - Implicit dependencies
- id: product-api
  depends_on: []  # Will fail without auth!
```

### 3. Detailed Acceptance Criteria

```yaml
# Good - Specific, testable
acceptance_criteria:
  - GET /users returns 200 with user list
  - POST /users with valid data creates user
  - POST /users with invalid data returns 400

# Bad - Vague
acceptance_criteria:
  - Endpoint works
```

### 4. Mark Research Tasks

```yaml
# Good - Explicit research requirement
- id: ml-model
  research_required: true
  research_queries:
    - "transformer model training best practices"
    - "PyTorch vs TensorFlow 2026"

# Bad - Agent will waste attempts
- id: ml-model
  description: Implement ML model  # How? Agent doesn't know
```

### 5. Break Down Complex Tasks

```yaml
# Good - Decomposed
- id: user-system-setup
- id: user-registration
- id: user-login
- id: user-profile

# Bad - Too large
- id: user-system  # Too much for one task
```

### 6. Use Defaults

```yaml
defaults:
  priority: medium
  category: functional

tasks:
  - id: task-1
    # Inherits defaults
  - id: task-2
    priority: high  # Override default
```

## Validation

BOB validates specs on load:

```bash
# Validate spec file
bob spec validate ./spec.yaml

# Validate and show structure
bob spec show ./spec.yaml

# Validate for issues
bob spec validate ./spec.yaml --strict
```

Common validation errors:
- Missing required fields (id, title, description)
- Invalid priority/category values
- Circular dependencies
- Duplicate task IDs
- Invalid dependency references

---

For more information:
- [Getting Started](getting-started.md) - Creating your first spec
- [Configuration](configuration.md) - Spec source configuration
- [Research-First](research-first.md) - Using research_required
- [Architecture](architecture.md) - How specs are parsed
