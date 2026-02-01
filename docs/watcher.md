# watcher

> Auto-generated from `/Users/mohameddiomande/Desktop/living-docs/living_docs/watcher.py`
> Last updated: 2026-01-31 18:40

File watcher daemon for real-time doc sync.

## Classes

### `DocSyncHandler`

```python
class DocSyncHandler(FileSystemEventHandler)
```

Handle file changes and trigger doc syncs.

### `Daemon`

```python
class Daemon
```

File watcher daemon.

## Functions

### `__init__`

```python
def __init__(self, project_root: Path, on_change: Callable[..., None], patterns: list[str], debounce_ms: int)
```

*No documentation available.*

### `_matches_patterns`

```python
def _matches_patterns(self, path: Path) -> bool
```

Check if path matches any watched pattern.

### `_should_process`

```python
def _should_process(self, path: Path) -> bool
```

Check if we should process this event (debouncing + hash check).

### `on_modified`

```python
def on_modified(self, event)
```

*No documentation available.*

### `on_created`

```python
def on_created(self, event)
```

*No documentation available.*

### `__init__`

```python
def __init__(self, project_root: Path, config: dict)
```

*No documentation available.*

### `_log`

```python
def _log(self, message: str)
```

Log a message with timestamp.

### `_on_file_change`

```python
def _on_file_change(self, path: Path)
```

Handle a file change.

### `start`

```python
def start(self, foreground: bool)
```

Start the daemon.

### `stop`

```python
def stop(self)
```

Stop the daemon.

### `_handle_signal`

```python
def _handle_signal(self, signum, frame)
```

Handle termination signals.

### `status`

```python
def status(cls, project_root: Path) -> dict
```

Check daemon status.

### `kill`

```python
def kill(cls, project_root: Path) -> bool
```

Kill running daemon.
