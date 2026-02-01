# parser

> Auto-generated from `/Users/mohameddiomande/Desktop/living-docs/living_docs/parser.py`
> Last updated: 2026-01-31 18:40

Code parsing and docstring extraction.

## Classes

### `DocItem`

```python
class DocItem
```

Represents a documentable code element.

### `PythonParser`

```python
class PythonParser
```

Parse Python files for documentation elements.

### `TypeScriptParser`

```python
class TypeScriptParser
```

Parse TypeScript/JavaScript files for documentation.

## Functions

### `get_parser`

```python
def get_parser(file_path: Path)
```

Get appropriate parser for file type.

### `is_documented`

```python
def is_documented(self) -> bool
```

*No documentation available.*

### `doc_quality_score`

```python
def doc_quality_score(self) -> float
```

Score 0-1 based on documentation quality.

### `parse_file`

```python
def parse_file(self, file_path: Path) -> list[DocItem]
```

Extract all documentable items from a Python file.

### `_parse_function`

```python
def _parse_function(self, node: ast.FunctionDef, file_path: Path, is_async: bool) -> DocItem
```

Parse a function/method definition.

### `_parse_class`

```python
def _parse_class(self, node: ast.ClassDef, file_path: Path) -> DocItem
```

Parse a class definition.

### `_build_signature`

```python
def _build_signature(self, node: ast.FunctionDef, is_async: bool) -> str
```

Build function signature string.

### `_get_annotation`

```python
def _get_annotation(self, node) -> str
```

Get string representation of type annotation.

### `_get_name`

```python
def _get_name(self, node) -> str
```

Get name from various node types.

### `_extract_imports`

```python
def _extract_imports(self, tree: ast.Module) -> list[str]
```

Extract import names from module.

### `_extract_examples`

```python
def _extract_examples(self, docstring: str) -> list[str]
```

Extract code examples from docstring.

### `parse_file`

```python
def parse_file(self, file_path: Path) -> list[DocItem]
```

Extract documentable items using regex (simplified).
