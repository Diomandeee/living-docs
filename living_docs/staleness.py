"""Staleness detection for documentation."""

import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional
import re


@dataclass
class StalenessReport:
    """Report on documentation freshness."""
    doc_path: str
    code_paths: list[str]
    doc_last_modified: datetime
    code_last_modified: datetime
    days_stale: int
    severity: str  # fresh, warning, stale, critical
    reason: str
    suggested_action: Optional[str] = None
    
    @property
    def is_stale(self) -> bool:
        return self.severity in ('stale', 'critical')


class StalenessCalculator:
    """Calculate documentation staleness based on git history."""
    
    def __init__(self, repo_root: Path, warning_days: int = 30, critical_days: int = 90):
        self.repo_root = repo_root
        self.warning_days = warning_days
        self.critical_days = critical_days
    
    def check_doc(self, doc_path: Path, related_code: list[Path]) -> StalenessReport:
        """Check staleness of a doc file against its related code."""
        doc_modified = self._get_last_modified(doc_path)
        
        # Get most recent code change
        code_modified = None
        latest_code_path = None
        
        for code_path in related_code:
            modified = self._get_last_modified(code_path)
            if modified and (code_modified is None or modified > code_modified):
                code_modified = modified
                latest_code_path = code_path
        
        if not doc_modified or not code_modified:
            return StalenessReport(
                doc_path=str(doc_path),
                code_paths=[str(p) for p in related_code],
                doc_last_modified=doc_modified or datetime.now(),
                code_last_modified=code_modified or datetime.now(),
                days_stale=0,
                severity="unknown",
                reason="Could not determine modification dates"
            )
        
        # Calculate staleness
        if code_modified > doc_modified:
            days_stale = (code_modified - doc_modified).days
            reason = f"Code updated {days_stale} days after docs"
            
            if days_stale > self.critical_days:
                severity = "critical"
            elif days_stale > self.warning_days:
                severity = "stale"
            else:
                severity = "warning"
            
            # Check what changed
            changes = self._get_signature_changes(latest_code_path, doc_modified)
            if changes:
                reason += f". Changed: {', '.join(changes)}"
        else:
            days_stale = 0
            severity = "fresh"
            reason = "Documentation is up to date"
        
        return StalenessReport(
            doc_path=str(doc_path),
            code_paths=[str(p) for p in related_code],
            doc_last_modified=doc_modified,
            code_last_modified=code_modified,
            days_stale=days_stale,
            severity=severity,
            reason=reason,
            suggested_action=self._suggest_action(severity, latest_code_path)
        )
    
    def _get_last_modified(self, path: Path) -> Optional[datetime]:
        """Get last modification date from git."""
        try:
            result = subprocess.run(
                ['git', 'log', '-1', '--format=%cI', '--', str(path)],
                cwd=self.repo_root,
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                date_str = result.stdout.strip()
                # Parse ISO format with timezone
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except Exception:
            pass
        
        # Fallback to file mtime
        if path.exists():
            return datetime.fromtimestamp(path.stat().st_mtime)
        return None
    
    def _get_signature_changes(self, code_path: Path, since: datetime) -> list[str]:
        """Detect significant changes since a date."""
        changes = []
        
        try:
            # Get diff since the date
            since_str = since.strftime('%Y-%m-%d')
            result = subprocess.run(
                ['git', 'diff', f'@{{"{since_str}"}}', '--', str(code_path)],
                cwd=self.repo_root,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                diff = result.stdout
                
                # Check for function signature changes
                if re.search(r'[-+]\s*def \w+\(', diff):
                    changes.append("function signatures")
                
                # Check for class changes
                if re.search(r'[-+]\s*class \w+', diff):
                    changes.append("class definitions")
                
                # Check for new exports
                if re.search(r'\+\s*export', diff):
                    changes.append("new exports")
                
                # Check for type changes
                if re.search(r'[-+]\s*:\s*\w+', diff) or 'typing' in diff:
                    changes.append("type annotations")
        
        except Exception:
            pass
        
        return changes
    
    def _suggest_action(self, severity: str, code_path: Optional[Path]) -> Optional[str]:
        """Suggest action based on staleness."""
        if severity == "fresh":
            return None
        elif severity == "warning":
            return f"Review doc for accuracy"
        elif severity == "stale":
            return f"Update documentation to match current code"
        elif severity == "critical":
            return f"Urgent: Documentation may be significantly outdated"
        return None
    
    def scan_project(self, doc_map: dict[Path, list[Path]]) -> list[StalenessReport]:
        """Scan all doc-code mappings and return reports."""
        reports = []
        
        for doc_path, code_paths in doc_map.items():
            if doc_path.exists():
                report = self.check_doc(doc_path, code_paths)
                reports.append(report)
        
        # Sort by severity (critical first)
        severity_order = {'critical': 0, 'stale': 1, 'warning': 2, 'fresh': 3, 'unknown': 4}
        reports.sort(key=lambda r: (severity_order.get(r.severity, 5), -r.days_stale))
        
        return reports


def find_doc_code_mappings(project_root: Path) -> dict[Path, list[Path]]:
    """Auto-detect documentation to code mappings."""
    mappings = {}
    
    # Look for docs folder
    docs_dir = project_root / 'docs'
    if not docs_dir.exists():
        docs_dir = project_root / 'documentation'
    
    if docs_dir.exists():
        for doc_file in docs_dir.rglob('*.md'):
            # Try to find matching code
            code_files = []
            
            # Match by name
            stem = doc_file.stem.lower().replace('-', '_').replace(' ', '_')
            
            for ext in ['.py', '.ts', '.js', '.tsx', '.jsx']:
                for src_dir in ['src', 'lib', 'app', '.']:
                    candidate = project_root / src_dir / f"{stem}{ext}"
                    if candidate.exists():
                        code_files.append(candidate)
                    
                    # Also check plurals and common variations
                    for variation in [f"{stem}s{ext}", f"{stem}_handler{ext}", f"{stem}_service{ext}"]:
                        candidate = project_root / src_dir / variation
                        if candidate.exists():
                            code_files.append(candidate)
            
            if code_files:
                mappings[doc_file] = code_files
    
    # Also check README against main entry points
    readme = project_root / 'README.md'
    if readme.exists():
        entry_points = []
        for pattern in ['src/index.*', 'src/main.*', 'lib/index.*', 'app/main.*', '__init__.py']:
            entry_points.extend(project_root.glob(pattern))
        if entry_points:
            mappings[readme] = entry_points
    
    return mappings
