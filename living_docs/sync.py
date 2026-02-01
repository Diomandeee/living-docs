"""Sync engine for keeping docs in sync with code."""

import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from .parser import get_parser, DocItem


@dataclass
class SyncAction:
    """A pending documentation update."""
    action: str  # create, update, delete, flag
    doc_path: str
    code_path: str
    current_content: Optional[str]
    suggested_content: Optional[str]
    reason: str
    confidence: float  # 0-1 how confident we are this is right
    
    def get_diff(self) -> str:
        """Generate a simple diff."""
        if not self.current_content or not self.suggested_content:
            return self.suggested_content or ""
        
        # Simple line-by-line diff
        current_lines = self.current_content.split('\n')
        suggested_lines = self.suggested_content.split('\n')
        
        diff_lines = []
        for i, (cur, sug) in enumerate(zip(current_lines, suggested_lines)):
            if cur != sug:
                diff_lines.append(f"- {cur}")
                diff_lines.append(f"+ {sug}")
            else:
                diff_lines.append(f"  {cur}")
        
        # Handle length differences
        if len(suggested_lines) > len(current_lines):
            for line in suggested_lines[len(current_lines):]:
                diff_lines.append(f"+ {line}")
        elif len(current_lines) > len(suggested_lines):
            for line in current_lines[len(suggested_lines):]:
                diff_lines.append(f"- {line}")
        
        return '\n'.join(diff_lines)


class SyncEngine:
    """Engine for syncing code changes to documentation."""
    
    def __init__(self, project_root: Path, doc_root: Path):
        self.project_root = project_root
        self.doc_root = doc_root
        self.doc_root.mkdir(parents=True, exist_ok=True)
    
    def scan_code(self, patterns: list[str]) -> list[DocItem]:
        """Scan code files and extract documentable items."""
        items = []
        
        for pattern in patterns:
            for file_path in self.project_root.glob(pattern):
                parser = get_parser(file_path)
                if parser:
                    items.extend(parser.parse_file(file_path))
        
        return items
    
    def find_doc_for_code(self, code_path: Path) -> Optional[Path]:
        """Find the documentation file for a code file."""
        # Convert code path to potential doc paths
        rel_path = code_path.relative_to(self.project_root)
        
        # Try: docs/module_name.md
        doc_name = rel_path.stem + '.md'
        
        # Check common doc locations
        candidates = [
            self.doc_root / doc_name,
            self.doc_root / rel_path.parent / doc_name,
            self.doc_root / 'api' / doc_name,
            self.doc_root / 'reference' / doc_name,
        ]
        
        for candidate in candidates:
            if candidate.exists():
                return candidate
        
        return None
    
    def generate_doc_content(self, items: list[DocItem], code_path: Path) -> str:
        """Generate markdown documentation from code items."""
        lines = [
            f"# {code_path.stem}",
            "",
            f"> Auto-generated from `{code_path}`",
            f"> Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]
        
        # Group by kind
        modules = [i for i in items if i.kind == 'module']
        classes = [i for i in items if i.kind == 'class']
        functions = [i for i in items if i.kind in ('function', 'async_function')]
        
        # Module docstring first
        for mod in modules:
            if mod.docstring:
                lines.append(mod.docstring)
                lines.append("")
        
        # Classes
        if classes:
            lines.append("## Classes")
            lines.append("")
            
            for cls in classes:
                lines.append(f"### `{cls.name}`")
                lines.append("")
                if cls.signature:
                    lines.append(f"```python")
                    lines.append(cls.signature)
                    lines.append("```")
                    lines.append("")
                if cls.docstring:
                    lines.append(cls.docstring)
                    lines.append("")
        
        # Functions
        if functions:
            lines.append("## Functions")
            lines.append("")
            
            for func in functions:
                lines.append(f"### `{func.name}`")
                lines.append("")
                if func.signature:
                    lines.append("```python")
                    lines.append(func.signature)
                    lines.append("```")
                    lines.append("")
                if func.docstring:
                    lines.append(func.docstring)
                else:
                    lines.append("*No documentation available.*")
                lines.append("")
                
                if func.examples:
                    lines.append("**Examples:**")
                    lines.append("```python")
                    for ex in func.examples:
                        lines.append(ex)
                    lines.append("```")
                    lines.append("")
        
        return '\n'.join(lines)
    
    def compute_sync_actions(self, code_patterns: list[str]) -> list[SyncAction]:
        """Compute all pending sync actions."""
        actions = []
        
        for pattern in code_patterns:
            for code_path in self.project_root.glob(pattern):
                parser = get_parser(code_path)
                if not parser:
                    continue
                
                items = parser.parse_file(code_path)
                if not items:
                    continue
                
                doc_path = self.find_doc_for_code(code_path)
                suggested = self.generate_doc_content(items, code_path)
                
                if doc_path and doc_path.exists():
                    current = doc_path.read_text()
                    
                    # Check if update needed
                    if self._content_differs(current, suggested):
                        actions.append(SyncAction(
                            action="update",
                            doc_path=str(doc_path),
                            code_path=str(code_path),
                            current_content=current,
                            suggested_content=suggested,
                            reason="Code has changed since doc was written",
                            confidence=0.7
                        ))
                else:
                    # No doc exists - suggest creation
                    default_doc_path = self.doc_root / (code_path.stem + '.md')
                    actions.append(SyncAction(
                        action="create",
                        doc_path=str(default_doc_path),
                        code_path=str(code_path),
                        current_content=None,
                        suggested_content=suggested,
                        reason="No documentation exists for this code",
                        confidence=0.9
                    ))
        
        return actions
    
    def _content_differs(self, current: str, suggested: str) -> bool:
        """Check if content meaningfully differs (ignoring timestamps)."""
        # Remove timestamp lines
        date_pattern = r'> Last updated:.*\n'
        current_clean = re.sub(date_pattern, '', current)
        suggested_clean = re.sub(date_pattern, '', suggested)
        
        # Remove extra whitespace
        current_clean = re.sub(r'\n\s*\n', '\n\n', current_clean.strip())
        suggested_clean = re.sub(r'\n\s*\n', '\n\n', suggested_clean.strip())
        
        return current_clean != suggested_clean
    
    def apply_action(self, action: SyncAction, dry_run: bool = True) -> bool:
        """Apply a sync action."""
        if dry_run:
            print(f"[DRY RUN] Would {action.action}: {action.doc_path}")
            return True
        
        if action.action == "create":
            Path(action.doc_path).parent.mkdir(parents=True, exist_ok=True)
            Path(action.doc_path).write_text(action.suggested_content)
            return True
        
        elif action.action == "update":
            Path(action.doc_path).write_text(action.suggested_content)
            return True
        
        elif action.action == "delete":
            Path(action.doc_path).unlink()
            return True
        
        return False
