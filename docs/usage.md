# usage

> Auto-generated from `/Users/mohameddiomande/Desktop/living-docs/living_docs/usage.py`
> Last updated: 2026-01-31 18:40

Usage tracking for documentation analytics.

## Classes

### `PageView`

```python
class PageView
```

Single page view event.

### `UsageStats`

```python
class UsageStats
```

Aggregated usage statistics for a doc.

### `UsageTracker`

```python
class UsageTracker
```

Track and analyze documentation usage patterns.

## Functions

### `generate_tracking_script`

```python
def generate_tracking_script() -> str
```

Generate JavaScript tracking snippet for docs.

### `__init__`

```python
def __init__(self, data_dir: Path)
```

*No documentation available.*

### `record_view`

```python
def record_view(self, view: PageView)
```

Record a page view event.

### `get_events`

```python
def get_events(self, since: Optional[datetime]) -> list[PageView]
```

Load events, optionally filtered by date.

### `compute_stats`

```python
def compute_stats(self, days: int) -> dict[str, UsageStats]
```

Compute usage statistics for each doc.

### `save_stats`

```python
def save_stats(self, stats: dict[str, UsageStats])
```

Save computed stats to file.

### `load_stats`

```python
def load_stats(self) -> dict[str, UsageStats]
```

Load saved stats from file.

### `get_insights`

```python
def get_insights(self, stats: dict[str, UsageStats]) -> list[str]
```

Generate actionable insights from usage data.
