"""
Diff Analyzer — Gen 7 Feature
Analyzes git diffs to identify which documentation needs updating.

Features:
- Parse git diffs (staged, unstaged, PR branches)
- Map code changes to affected documentation
- Generate impact reports
- Auto-suggest doc updates
- PR annotation format output
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
import json


class ChangeType(Enum):
    """Type of code change detected."""
    FUNCTION_SIGNATURE = "function_signature"
    FUNCTION_BODY = "function_body"
    CLASS_ADDED = "class_added"
    CLASS_REMOVED = "class_removed"
    CLASS_MODIFIED = "class_modified"
    IMPORT_CHANGED = "import_changed"
    CONSTANT_CHANGED = "constant_changed"
    TYPE_CHANGED = "type_changed"
    DOCSTRING_CHANGED = "docstring_changed"
    CONFIG_CHANGED = "config_changed"
    API_ENDPOINT = "api_endpoint"
    FILE_ADDED = "file_added"
    FILE_DELETED = "file_deleted"


@dataclass
class CodeChange:
    """Represents a single code change."""
    file: str
    change_type: ChangeType
    name: str  # Function/class/variable name
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    line_start: int = 0
    line_end: int = 0
    severity: str = "medium"  # low, medium, high, critical
    
    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "change_type": self.change_type.value,
            "name": self.name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "severity": self.severity,
        }


@dataclass
class DocImpact:
    """Documentation impact from a code change."""
    doc_file: str
    section: Optional[str] = None
    reason: str = ""
    code_change: Optional[CodeChange] = None
    confidence: float = 0.8
    suggested_action: str = "review"  # review, update, regenerate
    
    def to_dict(self) -> dict:
        return {
            "doc_file": self.doc_file,
            "section": self.section,
            "reason": self.reason,
            "code_change": self.code_change.to_dict() if self.code_change else None,
            "confidence": self.confidence,
            "suggested_action": self.suggested_action,
        }


@dataclass
class DiffReport:
    """Complete diff analysis report."""
    changes: list[CodeChange] = field(default_factory=list)
    impacts: list[DocImpact] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "changes": [c.to_dict() for c in self.changes],
            "impacts": [i.to_dict() for i in self.impacts],
            "summary": self.summary,
        }
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
    
    def to_markdown(self) -> str:
        """Generate markdown report for PR comments."""
        lines = ["## 📚 Documentation Impact Report\n"]
        
        if not self.impacts:
            lines.append("✅ No documentation updates needed for these changes.\n")
            return "\n".join(lines)
        
        # Summary
        by_action = {}
        for impact in self.impacts:
            by_action.setdefault(impact.suggested_action, []).append(impact)
        
        lines.append("### Summary\n")
        lines.append(f"- **{len(self.changes)}** code changes analyzed")
        lines.append(f"- **{len(self.impacts)}** documentation files affected\n")
        
        # Impacts by severity
        critical = [i for i in self.impacts if i.code_change and i.code_change.severity == "critical"]
        high = [i for i in self.impacts if i.code_change and i.code_change.severity == "high"]
        
        if critical:
            lines.append("### 🚨 Critical Updates Required\n")
            for impact in critical:
                lines.append(f"- `{impact.doc_file}` — {impact.reason}")
            lines.append("")
        
        if high:
            lines.append("### ⚠️ High Priority Updates\n")
            for impact in high:
                lines.append(f"- `{impact.doc_file}` — {impact.reason}")
            lines.append("")
        
        # All impacts table
        lines.append("### Affected Documentation\n")
        lines.append("| File | Section | Action | Reason |")
        lines.append("|------|---------|--------|--------|")
        for impact in self.impacts:
            section = impact.section or "—"
            lines.append(f"| `{impact.doc_file}` | {section} | {impact.suggested_action} | {impact.reason} |")
        
        return "\n".join(lines)
    
    def to_github_annotations(self) -> list[dict]:
        """Generate GitHub Actions annotations."""
        annotations = []
        for impact in self.impacts:
            level = "warning"
            if impact.code_change and impact.code_change.severity in ("critical", "high"):
                level = "error"
            
            annotations.append({
                "file": impact.doc_file,
                "line": 1,
                "level": level,
                "message": f"Doc update needed: {impact.reason}",
                "title": f"Documentation Impact ({impact.suggested_action})",
            })
        return annotations


class DiffAnalyzer:
    """Analyzes git diffs to find documentation impact."""
    
    # Patterns for detecting significant changes
    PYTHON_PATTERNS = {
        "function_def": re.compile(r"^[+-]\s*def\s+(\w+)\s*\((.*?)\)"),
        "class_def": re.compile(r"^[+-]\s*class\s+(\w+)"),
        "import": re.compile(r"^[+-]\s*(?:from\s+\S+\s+)?import\s+"),
        "constant": re.compile(r"^[+-]\s*([A-Z_][A-Z0-9_]*)\s*="),
        "type_hint": re.compile(r"^[+-]\s*(\w+)\s*:\s*(\w+)"),
        "docstring": re.compile(r'^[+-]\s*"""'),
        "decorator": re.compile(r"^[+-]\s*@(\w+)"),
    }
    
    TS_PATTERNS = {
        "function_def": re.compile(r"^[+-]\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)"),
        "arrow_fn": re.compile(r"^[+-]\s*(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s+)?\("),
        "class_def": re.compile(r"^[+-]\s*(?:export\s+)?class\s+(\w+)"),
        "interface": re.compile(r"^[+-]\s*(?:export\s+)?interface\s+(\w+)"),
        "type_alias": re.compile(r"^[+-]\s*(?:export\s+)?type\s+(\w+)"),
        "import": re.compile(r"^[+-]\s*import\s+"),
    }
    
    def __init__(self, repo_path: Path | str = "."):
        self.repo_path = Path(repo_path)
        self.doc_mappings = self._load_doc_mappings()
    
    def _load_doc_mappings(self) -> dict:
        """Load documentation mappings from config."""
        config_path = self.repo_path / ".living-docs.yaml"
        if not config_path.exists():
            return self._default_mappings()
        
        try:
            import yaml
            with open(config_path) as f:
                config = yaml.safe_load(f)
            return config.get("mappings", self._default_mappings())
        except Exception:
            return self._default_mappings()
    
    def _default_mappings(self) -> dict:
        """Default code→doc mappings."""
        return {
            "patterns": [
                {"code": "src/api/**", "docs": ["docs/api/", "README.md"]},
                {"code": "src/models/**", "docs": ["docs/models/"]},
                {"code": "src/**", "docs": ["docs/", "README.md"]},
                {"code": "lib/**", "docs": ["docs/"]},
                {"code": "**/*.py", "docs": ["docs/", "README.md"]},
                {"code": "**/*.ts", "docs": ["docs/", "README.md"]},
            ],
            "special": {
                "pyproject.toml": ["README.md", "docs/installation.md"],
                "package.json": ["README.md", "docs/installation.md"],
                "setup.py": ["README.md", "docs/installation.md"],
            }
        }
    
    def get_diff(
        self,
        base: str = "HEAD",
        target: Optional[str] = None,
        staged: bool = False,
    ) -> str:
        """Get git diff output."""
        cmd = ["git", "-C", str(self.repo_path), "diff"]
        
        if staged:
            cmd.append("--staged")
        elif target:
            cmd.extend([base, target])
        else:
            cmd.append(base)
        
        cmd.append("--unified=3")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.stdout
        except Exception as e:
            raise RuntimeError(f"Failed to get git diff: {e}")
    
    def get_changed_files(
        self,
        base: str = "HEAD",
        target: Optional[str] = None,
        staged: bool = False,
    ) -> list[str]:
        """Get list of changed files."""
        cmd = ["git", "-C", str(self.repo_path), "diff", "--name-only"]
        
        if staged:
            cmd.append("--staged")
        elif target:
            cmd.extend([base, target])
        else:
            cmd.append(base)
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        except Exception:
            return []
    
    def analyze(
        self,
        base: str = "HEAD",
        target: Optional[str] = None,
        staged: bool = False,
    ) -> DiffReport:
        """Analyze diff and generate impact report."""
        diff_text = self.get_diff(base, target, staged)
        changed_files = self.get_changed_files(base, target, staged)
        
        changes = self._parse_diff(diff_text, changed_files)
        impacts = self._map_to_docs(changes)
        
        report = DiffReport(
            changes=changes,
            impacts=impacts,
            summary=self._generate_summary(changes, impacts),
        )
        
        return report
    
    def _parse_diff(self, diff_text: str, changed_files: list[str]) -> list[CodeChange]:
        """Parse diff text to extract code changes."""
        changes = []
        current_file = None
        current_hunk_start = 0
        
        for line in diff_text.split("\n"):
            # New file
            if line.startswith("diff --git"):
                match = re.search(r"b/(.+)$", line)
                if match:
                    current_file = match.group(1)
            
            # Hunk header
            elif line.startswith("@@"):
                match = re.search(r"\+(\d+)", line)
                if match:
                    current_hunk_start = int(match.group(1))
            
            # Actual changes
            elif current_file and (line.startswith("+") or line.startswith("-")):
                if current_file.endswith(".py"):
                    changes.extend(self._parse_python_line(line, current_file, current_hunk_start))
                elif current_file.endswith((".ts", ".tsx", ".js", ".jsx")):
                    changes.extend(self._parse_typescript_line(line, current_file, current_hunk_start))
        
        # Add file-level changes
        for file in changed_files:
            if file not in [c.file for c in changes]:
                changes.append(CodeChange(
                    file=file,
                    change_type=ChangeType.FILE_ADDED if file.startswith("+") else ChangeType.CLASS_MODIFIED,
                    name=file,
                    severity="low",
                ))
        
        return changes
    
    def _parse_python_line(self, line: str, file: str, line_num: int) -> list[CodeChange]:
        """Parse a Python diff line."""
        changes = []
        
        for name, pattern in self.PYTHON_PATTERNS.items():
            match = pattern.search(line)
            if match:
                if name == "function_def":
                    changes.append(CodeChange(
                        file=file,
                        change_type=ChangeType.FUNCTION_SIGNATURE,
                        name=match.group(1),
                        new_value=match.group(2) if len(match.groups()) > 1 else None,
                        line_start=line_num,
                        severity="high" if line.startswith("-") else "medium",
                    ))
                elif name == "class_def":
                    changes.append(CodeChange(
                        file=file,
                        change_type=ChangeType.CLASS_ADDED if line.startswith("+") else ChangeType.CLASS_REMOVED,
                        name=match.group(1),
                        line_start=line_num,
                        severity="critical",
                    ))
                elif name == "import":
                    changes.append(CodeChange(
                        file=file,
                        change_type=ChangeType.IMPORT_CHANGED,
                        name="imports",
                        line_start=line_num,
                        severity="low",
                    ))
                elif name == "decorator" and match.group(1) in ("app.route", "router", "api"):
                    changes.append(CodeChange(
                        file=file,
                        change_type=ChangeType.API_ENDPOINT,
                        name=match.group(1),
                        line_start=line_num,
                        severity="critical",
                    ))
        
        return changes
    
    def _parse_typescript_line(self, line: str, file: str, line_num: int) -> list[CodeChange]:
        """Parse a TypeScript/JavaScript diff line."""
        changes = []
        
        for name, pattern in self.TS_PATTERNS.items():
            match = pattern.search(line)
            if match:
                if name in ("function_def", "arrow_fn"):
                    changes.append(CodeChange(
                        file=file,
                        change_type=ChangeType.FUNCTION_SIGNATURE,
                        name=match.group(1),
                        line_start=line_num,
                        severity="high" if line.startswith("-") else "medium",
                    ))
                elif name in ("class_def", "interface", "type_alias"):
                    changes.append(CodeChange(
                        file=file,
                        change_type=ChangeType.CLASS_MODIFIED,
                        name=match.group(1),
                        line_start=line_num,
                        severity="high",
                    ))
        
        return changes
    
    def _map_to_docs(self, changes: list[CodeChange]) -> list[DocImpact]:
        """Map code changes to affected documentation."""
        impacts = []
        seen = set()
        
        for change in changes:
            # Find matching doc patterns
            affected_docs = self._find_affected_docs(change.file)
            
            for doc in affected_docs:
                key = (doc, change.name)
                if key in seen:
                    continue
                seen.add(key)
                
                impact = DocImpact(
                    doc_file=doc,
                    section=self._guess_section(change),
                    reason=self._generate_reason(change),
                    code_change=change,
                    confidence=self._calculate_confidence(change, doc),
                    suggested_action=self._suggest_action(change),
                )
                impacts.append(impact)
        
        return sorted(impacts, key=lambda i: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(
                i.code_change.severity if i.code_change else "low", 2
            ),
            i.doc_file
        ))
    
    def _find_affected_docs(self, code_file: str) -> list[str]:
        """Find documentation files affected by a code file change."""
        docs = []
        
        # Check special mappings first
        if code_file in self.doc_mappings.get("special", {}):
            docs.extend(self.doc_mappings["special"][code_file])
        
        # Check pattern mappings
        from fnmatch import fnmatch
        for mapping in self.doc_mappings.get("patterns", []):
            if fnmatch(code_file, mapping["code"]):
                docs.extend(mapping["docs"])
        
        # Deduplicate while preserving order
        seen = set()
        return [d for d in docs if not (d in seen or seen.add(d))]
    
    def _guess_section(self, change: CodeChange) -> Optional[str]:
        """Guess which doc section is affected."""
        if change.change_type == ChangeType.API_ENDPOINT:
            return "API Reference"
        elif change.change_type in (ChangeType.CLASS_ADDED, ChangeType.CLASS_REMOVED):
            return f"Classes / {change.name}"
        elif change.change_type == ChangeType.FUNCTION_SIGNATURE:
            return f"Functions / {change.name}"
        elif change.change_type == ChangeType.CONFIG_CHANGED:
            return "Configuration"
        return None
    
    def _generate_reason(self, change: CodeChange) -> str:
        """Generate human-readable reason for doc update."""
        reasons = {
            ChangeType.FUNCTION_SIGNATURE: f"Function `{change.name}` signature changed",
            ChangeType.CLASS_ADDED: f"New class `{change.name}` added",
            ChangeType.CLASS_REMOVED: f"Class `{change.name}` removed",
            ChangeType.CLASS_MODIFIED: f"Class `{change.name}` modified",
            ChangeType.API_ENDPOINT: f"API endpoint changed in `{change.file}`",
            ChangeType.IMPORT_CHANGED: f"Dependencies changed in `{change.file}`",
            ChangeType.TYPE_CHANGED: f"Type definitions changed",
            ChangeType.CONFIG_CHANGED: f"Configuration file `{change.file}` changed",
        }
        return reasons.get(change.change_type, f"Code changed in `{change.file}`")
    
    def _calculate_confidence(self, change: CodeChange, doc: str) -> float:
        """Calculate confidence that doc needs updating."""
        base = 0.5
        
        # High severity = high confidence
        if change.severity == "critical":
            base = 0.95
        elif change.severity == "high":
            base = 0.85
        elif change.severity == "medium":
            base = 0.7
        
        # API changes always need doc updates
        if change.change_type == ChangeType.API_ENDPOINT:
            base = 0.98
        
        return min(1.0, base)
    
    def _suggest_action(self, change: CodeChange) -> str:
        """Suggest what action to take for docs."""
        if change.change_type in (ChangeType.CLASS_ADDED, ChangeType.FILE_ADDED):
            return "regenerate"
        elif change.change_type in (ChangeType.CLASS_REMOVED, ChangeType.FILE_DELETED):
            return "update"
        elif change.severity in ("critical", "high"):
            return "update"
        return "review"
    
    def _generate_summary(self, changes: list[CodeChange], impacts: list[DocImpact]) -> dict:
        """Generate summary statistics."""
        return {
            "total_changes": len(changes),
            "total_impacts": len(impacts),
            "by_severity": {
                "critical": len([c for c in changes if c.severity == "critical"]),
                "high": len([c for c in changes if c.severity == "high"]),
                "medium": len([c for c in changes if c.severity == "medium"]),
                "low": len([c for c in changes if c.severity == "low"]),
            },
            "by_action": {
                "update": len([i for i in impacts if i.suggested_action == "update"]),
                "review": len([i for i in impacts if i.suggested_action == "review"]),
                "regenerate": len([i for i in impacts if i.suggested_action == "regenerate"]),
            },
            "affected_docs": list(set(i.doc_file for i in impacts)),
        }


def analyze_pr(
    repo_path: str = ".",
    base_branch: str = "main",
    pr_branch: Optional[str] = None,
) -> DiffReport:
    """Analyze a PR for documentation impact.
    
    Args:
        repo_path: Path to the git repository
        base_branch: Base branch (usually main/master)
        pr_branch: PR branch (None = current HEAD)
    
    Returns:
        DiffReport with changes and impacts
    """
    analyzer = DiffAnalyzer(repo_path)
    return analyzer.analyze(base=base_branch, target=pr_branch)


def analyze_staged(repo_path: str = ".") -> DiffReport:
    """Analyze staged changes for documentation impact."""
    analyzer = DiffAnalyzer(repo_path)
    return analyzer.analyze(staged=True)


if __name__ == "__main__":
    # Quick test
    report = analyze_staged()
    print(report.to_markdown())
