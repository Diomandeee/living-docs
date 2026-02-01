# staleness

> Auto-generated from `/Users/mohameddiomande/Desktop/living-docs/living_docs/staleness.py`
> Last updated: 2026-01-31 18:40

Staleness detection for documentation.

## Classes

### `StalenessReport`

```python
class StalenessReport
```

Report on documentation freshness.

### `StalenessCalculator`

```python
class StalenessCalculator
```

Calculate documentation staleness based on git history.

## Functions

### `find_doc_code_mappings`

```python
def find_doc_code_mappings(project_root: Path) -> dict[Path, list[Path]]
```

Auto-detect documentation to code mappings.

### `is_stale`

```python
def is_stale(self) -> bool
```

*No documentation available.*

### `__init__`

```python
def __init__(self, repo_root: Path, warning_days: int, critical_days: int)
```

*No documentation available.*

### `check_doc`

```python
def check_doc(self, doc_path: Path, related_code: list[Path]) -> StalenessReport
```

Check staleness of a doc file against its related code.

### `_get_last_modified`

```python
def _get_last_modified(self, path: Path) -> Optional[datetime]
```

Get last modification date from git.

### `_get_signature_changes`

```python
def _get_signature_changes(self, code_path: Path, since: datetime) -> list[str]
```

Detect significant changes since a date.

### `_suggest_action`

```python
def _suggest_action(self, severity: str, code_path: Optional[Path]) -> Optional[str]
```

Suggest action based on staleness.

### `scan_project`

```python
def scan_project(self, doc_map: dict[Path, list[Path]]) -> list[StalenessReport]
```

Scan all doc-code mappings and return reports.
