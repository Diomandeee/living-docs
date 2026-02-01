"""Code parsing and docstring extraction."""

import ast
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DocItem:
    """Represents a documentable code element."""
    name: str
    kind: str  # function, class, method, module
    docstring: Optional[str]
    signature: Optional[str]
    file_path: str
    line_number: int
    dependencies: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    
    @property
    def is_documented(self) -> bool:
        return bool(self.docstring and len(self.docstring.strip()) > 10)
    
    @property
    def doc_quality_score(self) -> float:
        """Score 0-1 based on documentation quality."""
        if not self.docstring:
            return 0.0
        
        score = 0.2  # Base for having any docstring
        doc = self.docstring.lower()
        
        # Has description (not just params)
        if len(doc) > 50:
            score += 0.2
        
        # Documents parameters
        if 'param' in doc or 'args' in doc or ':param' in doc:
            score += 0.2
        
        # Documents return value
        if 'return' in doc or ':return' in doc:
            score += 0.2
        
        # Has examples
        if '>>>' in doc or 'example' in doc:
            score += 0.2
        
        return min(score, 1.0)


class PythonParser:
    """Parse Python files for documentation elements."""
    
    def parse_file(self, file_path: Path) -> list[DocItem]:
        """Extract all documentable items from a Python file."""
        items = []
        
        try:
            content = file_path.read_text()
            tree = ast.parse(content)
        except (SyntaxError, UnicodeDecodeError) as e:
            return []
        
        # Module docstring
        if ast.get_docstring(tree):
            items.append(DocItem(
                name=file_path.stem,
                kind="module",
                docstring=ast.get_docstring(tree),
                signature=None,
                file_path=str(file_path),
                line_number=1,
                dependencies=self._extract_imports(tree)
            ))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                items.append(self._parse_function(node, file_path))
            elif isinstance(node, ast.AsyncFunctionDef):
                items.append(self._parse_function(node, file_path, is_async=True))
            elif isinstance(node, ast.ClassDef):
                items.append(self._parse_class(node, file_path))
        
        return items
    
    def _parse_function(self, node: ast.FunctionDef, file_path: Path, is_async: bool = False) -> DocItem:
        """Parse a function/method definition."""
        sig = self._build_signature(node, is_async)
        
        return DocItem(
            name=node.name,
            kind="async_function" if is_async else "function",
            docstring=ast.get_docstring(node),
            signature=sig,
            file_path=str(file_path),
            line_number=node.lineno,
            examples=self._extract_examples(ast.get_docstring(node) or "")
        )
    
    def _parse_class(self, node: ast.ClassDef, file_path: Path) -> DocItem:
        """Parse a class definition."""
        bases = [self._get_name(b) for b in node.bases]
        sig = f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"
        
        return DocItem(
            name=node.name,
            kind="class",
            docstring=ast.get_docstring(node),
            signature=sig,
            file_path=str(file_path),
            line_number=node.lineno
        )
    
    def _build_signature(self, node: ast.FunctionDef, is_async: bool) -> str:
        """Build function signature string."""
        args = []
        
        # Regular args
        for arg in node.args.args:
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {self._get_annotation(arg.annotation)}"
            args.append(arg_str)
        
        # *args
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        
        # **kwargs
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")
        
        prefix = "async def" if is_async else "def"
        return_hint = ""
        if node.returns:
            return_hint = f" -> {self._get_annotation(node.returns)}"
        
        return f"{prefix} {node.name}({', '.join(args)}){return_hint}"
    
    def _get_annotation(self, node) -> str:
        """Get string representation of type annotation."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Subscript):
            return f"{self._get_annotation(node.value)}[{self._get_annotation(node.slice)}]"
        elif isinstance(node, ast.Attribute):
            return f"{self._get_annotation(node.value)}.{node.attr}"
        elif isinstance(node, ast.Tuple):
            return ", ".join(self._get_annotation(e) for e in node.elts)
        return "..."
    
    def _get_name(self, node) -> str:
        """Get name from various node types."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        return "..."
    
    def _extract_imports(self, tree: ast.Module) -> list[str]:
        """Extract import names from module."""
        imports = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        return imports
    
    def _extract_examples(self, docstring: str) -> list[str]:
        """Extract code examples from docstring."""
        examples = []
        in_example = False
        current = []
        
        for line in docstring.split('\n'):
            if '>>>' in line:
                in_example = True
                current.append(line.strip())
            elif in_example:
                if line.strip() and not line.strip().startswith('>>>'):
                    current.append(line.strip())
                else:
                    if current:
                        examples.append('\n'.join(current))
                    current = []
                    in_example = '>>>' in line
                    if in_example:
                        current.append(line.strip())
        
        if current:
            examples.append('\n'.join(current))
        
        return examples


class TypeScriptParser:
    """Parse TypeScript/JavaScript files for documentation."""
    
    def parse_file(self, file_path: Path) -> list[DocItem]:
        """Extract documentable items using regex (simplified)."""
        items = []
        content = file_path.read_text()
        
        # Match JSDoc comments followed by exports
        jsdoc_pattern = r'/\*\*\s*([\s\S]*?)\*/\s*(export\s+(?:async\s+)?(?:function|class|const|interface)\s+(\w+))'
        
        for match in re.finditer(jsdoc_pattern, content):
            docstring = match.group(1).strip()
            declaration = match.group(2)
            name = match.group(3)
            
            # Determine kind
            if 'class ' in declaration:
                kind = 'class'
            elif 'interface ' in declaration:
                kind = 'interface'
            elif 'function ' in declaration:
                kind = 'function'
            else:
                kind = 'const'
            
            items.append(DocItem(
                name=name,
                kind=kind,
                docstring=docstring,
                signature=declaration.split('\n')[0],
                file_path=str(file_path),
                line_number=content[:match.start()].count('\n') + 1
            ))
        
        return items


def get_parser(file_path: Path):
    """Get appropriate parser for file type."""
    suffix = file_path.suffix.lower()
    
    if suffix == '.py':
        return PythonParser()
    elif suffix in ('.ts', '.tsx', '.js', '.jsx'):
        return TypeScriptParser()
    
    return None
