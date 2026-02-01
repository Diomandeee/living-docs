# Living Documentation 📚✨

**Docs that evolve with your code.**

Living Documentation automatically keeps your documentation in sync with your codebase by:

- 🔄 **Auto-updating** when code changes
- 👀 **Tracking usage** to prioritize what matters
- ⚠️ **Detecting staleness** before users do
- 🔗 **Cross-referencing** code ↔ docs bidirectionally
- 💡 **Suggesting improvements** based on patterns

## Quick Start

```bash
# Initialize in a project
living-docs init

# Start the watcher daemon
living-docs watch

# Check doc health
living-docs health

# Generate missing docs
living-docs generate
```

## How It Works

### 1. Code → Docs Sync
When you modify code, Living Docs:
- Parses docstrings, comments, type hints
- Updates related markdown files
- Flags sections that may be stale
- Creates PR-ready diffs

### 2. Usage Tracking
Embedded analytics (optional) track:
- Which docs are read most
- Search queries that lead nowhere
- Time spent on each section
- Sections users scroll past

### 3. Staleness Detection
Computes a "freshness score" based on:
- Last code change vs last doc update
- Function signature changes
- Import/dependency changes
- Git blame patterns

### 4. AI-Powered Generation
Uses LLMs to:
- Generate initial docs from code
- Suggest improvements
- Answer "how would I document this?"
- Create examples from tests

## Installation

```bash
pip install living-docs
# or
pipx install living-docs
```

## Configuration

Create `.living-docs.yaml` in your project root:

```yaml
# What to watch
sources:
  - src/**/*.py
  - lib/**/*.ts

# Where docs live
docs:
  - docs/
  - README.md

# Sync rules
rules:
  - pattern: "src/api/*.py"
    docs: "docs/api/"
    template: "api-endpoint"
  
  - pattern: "src/models/*.py"
    docs: "docs/models/"
    template: "data-model"

# Staleness thresholds (days)
staleness:
  warning: 30
  critical: 90

# AI provider (optional)
ai:
  provider: anthropic  # or openai, local
  model: claude-sonnet-4-20250514
```

## Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize Living Docs in current project |
| `watch` | Start file watcher daemon |
| `health` | Show documentation health report |
| `stale` | List stale documentation |
| `generate` | Generate docs for undocumented code |
| `sync` | One-shot sync (no daemon) |
| `improve` | AI-powered doc analysis & improvement |
| `ci` | CI/CD integration check |
| `related` | Find semantically related docs/code |
| `setup-ci` | Generate GitHub/GitLab CI config |
| **`diff`** | 🆕 Analyze git diff for doc impact |
| **`pr-check`** | 🆕 Check PR for documentation impact |

## Gen 6 Features 🚀

### AI-Powered Improvement

Use Claude or GPT to analyze and improve your documentation:

```bash
# Analyze a doc file
living-docs improve docs/api.md --analyze-only

# Generate improved version
living-docs improve docs/api.md --with-context

# Preview changes
living-docs improve docs/api.md --dry-run

# Update in place
living-docs improve docs/api.md --inplace
```

Output includes quality scores, specific issues, and actionable suggestions.

### CI/CD Integration

Fail builds when documentation is stale:

```bash
# Run CI check
living-docs ci

# Generate GitHub Actions workflow
living-docs setup-ci --provider github

# Output formats: human, github, gitlab, markdown, json
living-docs ci --format markdown

# Strict mode (fail on any warning)
living-docs ci --strict
```

The generated GitHub Action:
- Runs on every PR
- Comments a health report
- Fails if critical docs are stale
- Tracks coverage trends

### Semantic Similarity

Find related documentation when code changes:

```bash
# Build semantic index
living-docs related

# Find docs related to a code file
living-docs related src/api/users.py

# Adjust sensitivity
living-docs related --threshold 0.5 --top 10
```

Uses embeddings to understand conceptual relationships, not just file paths.

### Configuration (Gen 6)

```yaml
# AI provider
ai:
  provider: anthropic  # anthropic, openai, local
  model: claude-sonnet-4-20250514
  temperature: 0.3

# Embeddings for semantic search
embeddings:
  provider: local  # local, openai, voyage
  model: all-MiniLM-L6-v2  # sentence-transformers model
  # use_ollama: true  # for local Ollama

# CI thresholds
ci:
  fail_on_stale: true
  min_coverage: 0.5
  min_score: 0.6
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   Code Files    │────▶│   AST Parser    │
└─────────────────┘     └────────┬────────┘
                                 │
┌─────────────────┐     ┌────────▼────────┐
│   Doc Files     │◀───▶│  Sync Engine    │
└─────────────────┘     └────────┬────────┘
                                 │
┌─────────────────┐     ┌────────▼────────┐
│   Git History   │────▶│ Staleness Calc  │
└─────────────────┘     └────────┬────────┘
                                 │
┌─────────────────┐     ┌────────▼────────┐
│   Usage Data    │────▶│  Health Score   │
└─────────────────┘     └─────────────────┘
```

## HEF Evolution

**Instance:** inst_20260131082143_322  
**Generation:** 7  
**Origin:** Dream Weaver idea incubation

### Evolution History

| Gen | Features Added |
|-----|----------------|
| 5 | Core engine: parser, staleness, sync, watcher, usage tracking |
| 6 | AI improvement, CI/CD integration, semantic similarity |
| 7 | Diff analysis, PR checks, code→doc impact mapping |

## Gen 7 Features 🆕

### Diff Analysis

Analyze any git diff to see which documentation needs updating:

```bash
# Analyze staged changes
living-docs diff --staged

# Compare branches
living-docs diff --base main --target feature/api-v2

# Output formats: human, markdown, json, github
living-docs diff --format markdown
```

### PR Documentation Check

Before merging, check if your PR needs doc updates:

```bash
# Check current branch against main
living-docs pr-check --base main

# Generate PR comment (markdown)
living-docs pr-check --format markdown

# Fail CI if critical docs missing
living-docs pr-check --fail-on-critical
```

Output in GitHub Actions format:
```bash
living-docs pr-check --format github
# ::warning file=docs/api.md,line=1,title=Documentation Impact (update)::Doc update needed: Function `create_user` signature changed
```

### How It Works

The diff analyzer:
1. Parses git diffs to extract semantic changes (function signatures, class definitions, etc.)
2. Maps code files to documentation using configurable patterns
3. Calculates impact severity (critical/high/medium/low)
4. Suggests actions (update/review/regenerate)
5. Generates reports in multiple formats

### Configuration

Add mappings to `.living-docs.yaml`:

```yaml
mappings:
  patterns:
    - code: "src/api/**"
      docs: ["docs/api/", "README.md"]
    - code: "src/models/**"
      docs: ["docs/models/"]
  special:
    pyproject.toml: ["README.md", "docs/installation.md"]
    package.json: ["README.md"]
```

## Gen 8 Features 🆕🆕

### Documentation Knowledge Graph

Build a graph of relationships between docs, code, and concepts:

```bash
# Build the graph
living-docs graph build

# Find orphaned documentation (no connections)
living-docs graph orphans

# Find hub documents (most connected)
living-docs graph hubs --top 10

# Find path between two nodes
living-docs graph path --node doc:README.md --target class:UserService

# Query navigation suggestions
living-docs graph query --node doc:api.md

# Export as Mermaid diagram
living-docs graph mermaid > graph.mmd
```

The graph captures:
- **Cross-references** between documentation files
- **Code references** (`function_name` mentions in docs)
- **Hierarchical relationships** (sections, examples)
- **Implementation links** (which docs describe which code)

### Documentation Coverage

Visual reports showing what's documented vs undocumented:

```bash
# ASCII treemap visualization
living-docs coverage

# Get coverage trend over time
living-docs coverage --trend

# Generate markdown report
living-docs coverage --format markdown

# HTML treemap (D3.js)
living-docs coverage --format html --output coverage.html

# Shields.io badge URL
living-docs coverage --format badge

# Fail CI if below threshold
living-docs coverage --min 80
```

Example ASCII output:
```
┌──────────────────────────────────────────────────────────┐
│        Documentation Coverage: 73.4%                     │
├──────────────────────────────────────────────────────────┤
│ src/api.py           ███████████████████░░░░░░░░░  65.0% 🟡│
│ src/models.py        ████████████████████████████  92.0% 🟢│
│ src/utils.py         ██████░░░░░░░░░░░░░░░░░░░░░░  23.0% 🔴│
└──────────────────────────────────────────────────────────┘
```

### Runnable Examples Validator

Extract and validate code examples from your documentation:

```bash
# Validate all examples
living-docs examples

# Validate specific file
living-docs examples --file docs/quickstart.md

# JSON output
living-docs examples --format json

# Fail CI on invalid examples
living-docs examples --fail-on-invalid
```

The validator:
- Extracts code blocks from Markdown/RST
- Validates Python syntax via AST parsing
- Checks imports exist in the codebase
- Runs safe examples in a sandbox
- Validates JSON/YAML syntax
- Checks bash scripts with `bash -n`
- Detects outdated API patterns

Example output:
```
=== Documentation Examples Validation ===
Total examples: 24
Valid: 21 ✓
Invalid: 2 ✗
Skipped: 1 -
Pass rate: 91.3%

=== Invalid Examples ===

📍 docs/api.md:45
   syntax_error: Syntax error at line 3: unexpected indent
   💡 Suggested: Check indentation - mixing tabs and spaces?

📍 docs/quickstart.md:89
   import_error: Cannot import 'old_module'
```

### Gen 8 Configuration

```yaml
# Graph settings
graph:
  max_depth: 3
  include_examples: true

# Coverage settings  
coverage:
  ignore:
    - "**/test_*.py"
    - "**/__pycache__/**"
  min_threshold: 75

# Example validation
examples:
  languages:
    - python
    - javascript
    - bash
  execute_safe: true  # Run safe examples
  timeout: 10  # seconds
```

## Commands Reference

| Command | Gen | Description |
|---------|-----|-------------|
| `init` | 5 | Initialize Living Docs |
| `watch` | 5 | Start file watcher daemon |
| `health` | 5 | Show documentation health |
| `stale` | 5 | List stale documentation |
| `generate` | 5 | Generate missing docs |
| `sync` | 5 | One-shot sync |
| `improve` | 6 | AI-powered improvement |
| `ci` | 6 | CI/CD integration check |
| `related` | 6 | Semantic similarity search |
| `setup-ci` | 6 | Generate CI config |
| `diff` | 7 | Analyze git diff impact |
| `pr-check` | 7 | Check PR for doc impact |
| **`graph`** | 8 | 🆕 Knowledge graph |
| **`coverage`** | 8 | 🆕 Coverage visualization |
| **`examples`** | 8 | 🆕 Validate code examples |

## Gen 9 Features 🆕🆕🆕

### Auto-PR Creation

Automatically create pull requests for documentation fixes:

```bash
# Preview what PRs would be created
living-docs auto-pr --dry-run

# Create PRs interactively
living-docs auto-pr --interactive

# Create PRs from specific sources
living-docs auto-pr --source stale        # Only stale docs
living-docs auto-pr --source coverage     # Only missing docs
living-docs auto-pr --source all          # Everything

# Group fixes differently
living-docs auto-pr --group-by severity   # One PR per severity level
living-docs auto-pr --group-by type       # One PR per fix type
living-docs auto-pr --group-by single     # One PR per fix

# Add reviewers
living-docs auto-pr --reviewers alice bob
```

The auto-PR system:
- Creates branches with meaningful names (`docs/stale-api-20260201-0845`)
- Generates conventional commit messages
- Creates detailed PR descriptions with severity indicators
- Supports GitHub (via `gh` CLI) and GitLab (via `glab` CLI)

### Test-to-Example Generation

Transform your test files into documentation examples:

```bash
# Generate examples from all tests
living-docs from-tests

# Specific test files
living-docs from-tests tests/test_api.py tests/test_models.py

# Use AI to improve examples (requires API key)
living-docs from-tests --use-ai

# Filter by quality threshold
living-docs from-tests --min-quality good

# Filter by complexity (1-10)
living-docs from-tests --max-complexity 5

# Filter by tags
living-docs from-tests --tags api edge_case

# Output formats
living-docs from-tests --format markdown --output EXAMPLES.md
living-docs from-tests --format json
living-docs from-tests --format rst
```

Example transformation:

**Before (test):**
```python
def test_user_creation_with_email():
    """Users can be created with email."""
    user = User.create(email="test@example.com")
    assert user.id is not None
    assert user.email == "test@example.com"
```

**After (example):**
```markdown
### User Creation With Email

Users can be created with email.

​```python
user = User.create(email="test@example.com")
print(user.id)  # => 1
print(user.email)  # => "test@example.com"
​```
```

### Interactive Documentation Explorer

Browse your documentation in the terminal:

```bash
# Launch full interactive explorer
living-docs explore

# Simple mode (no TUI dependencies)
living-docs explore --simple

# Just print the tree
living-docs explore --tree-only

# Non-interactive search
living-docs explore --search "authentication"

# JSON tree output
living-docs explore --tree-only --format json
```

**Interactive controls:**
- `↑↓` / `jk` - Navigate
- `Enter` - Open/expand
- `b` - Back
- `/` - Search
- `h` - Show health
- `p` - Toggle preview
- `q` - Quit

The explorer shows:
- 📁 Documentation tree structure
- 🔴🟡🟢 Health indicators (stale/warning/healthy)
- Full-text search with highlighting
- Content preview with sections

### Gen 9 Configuration

```yaml
# Auto-PR settings
auto_pr:
  provider: github  # github, gitlab
  base_branch: main
  branch_prefix: "docs/"
  draft: true
  labels:
    - documentation
    - auto-generated
  reviewers: []
  max_files_per_pr: 10
  group_by: severity

# Test-to-example settings
test_to_example:
  use_ai: false
  min_quality: fair
  max_complexity: 7
  include_tags:
    - api
    - example
  exclude_tags:
    - regression

# Explorer settings
explorer:
  include_sections: true
  show_health: true
```

## Commands Reference

| Command | Gen | Description |
|---------|-----|-------------|
| `init` | 5 | Initialize Living Docs |
| `watch` | 5 | Start file watcher daemon |
| `health` | 5 | Show documentation health |
| `stale` | 5 | List stale documentation |
| `generate` | 5 | Generate missing docs |
| `sync` | 5 | One-shot sync |
| `improve` | 6 | AI-powered improvement |
| `ci` | 6 | CI/CD integration check |
| `related` | 6 | Semantic similarity search |
| `setup-ci` | 6 | Generate CI config |
| `diff` | 7 | Analyze git diff impact |
| `pr-check` | 7 | Check PR for doc impact |
| `graph` | 8 | Knowledge graph |
| `coverage` | 8 | Coverage visualization |
| `examples` | 8 | Validate code examples |
| **`auto-pr`** | 9 | 🆕 Create PRs for doc fixes |
| **`from-tests`** | 9 | 🆕 Generate examples from tests |
| **`explore`** | 9 | 🆕 Interactive explorer |

## HEF Evolution

**Instance:** inst_20260131082143_322  
**Generation:** 9  
**Origin:** Dream Weaver idea incubation

### Evolution History

| Gen | Features Added |
|-----|----------------|
| 5 | Core engine: parser, staleness, sync, watcher, usage tracking |
| 6 | AI improvement, CI/CD integration, semantic similarity |
| 7 | Diff analysis, PR checks, code→doc impact mapping |
| 8 | Knowledge graph, coverage visualization, example validation |
| 9 | Auto-PR creation, test-to-example generation, interactive explorer |

### Future Directions (Gen 10+)
- VSCode extension for inline staleness warnings
- Multi-language support (Go, Rust, Java)
- Watch mode with real-time PR annotations
- Voice-guided documentation navigation
- Collaborative documentation editing

---

*Documentation should be a living thing, not a graveyard of good intentions.*
