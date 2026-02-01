# sync

> Auto-generated from `/Users/mohameddiomande/Desktop/living-docs/living_docs/sync.py`
> Last updated: 2026-01-31 18:40

Sync engine for keeping docs in sync with code.

## Classes

### `SyncAction`

```python
class SyncAction
```

A pending documentation update.

### `SyncEngine`

```python
class SyncEngine
```

Engine for syncing code changes to documentation.

## Functions

### `get_diff`

```python
def get_diff(self) -> str
```

Generate a simple diff.

### `__init__`

```python
def __init__(self, project_root: Path, doc_root: Path)
```

*No documentation available.*

### `scan_code`

```python
def scan_code(self, patterns: list[str]) -> list[DocItem]
```

Scan code files and extract documentable items.

### `find_doc_for_code`

```python
def find_doc_for_code(self, code_path: Path) -> Optional[Path]
```

Find the documentation file for a code file.

### `generate_doc_content`

```python
def generate_doc_content(self, items: list[DocItem], code_path: Path) -> str
```

Generate markdown documentation from code items.

### `compute_sync_actions`

```python
def compute_sync_actions(self, code_patterns: list[str]) -> list[SyncAction]
```

Compute all pending sync actions.

### `_content_differs`

```python
def _content_differs(self, current: str, suggested: str) -> bool
```

Check if content meaningfully differs (ignoring timestamps).

### `apply_action`

```python
def apply_action(self, action: SyncAction, dry_run: bool) -> bool
```

Apply a sync action.
