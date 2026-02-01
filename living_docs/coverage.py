#!/usr/bin/env python3
"""Documentation Coverage Visualization — Gen 8 Feature

Generates visual reports showing which code is documented vs undocumented.
Includes:
- Coverage metrics by file, directory, and overall
- Visual treemaps and badges
- Trend tracking over time
- Exportable reports for dashboards
"""

from __future__ import annotations

import ast
import json
import os
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class CoverageItem:
    """Coverage data for a single code entity."""
    name: str
    kind: str  # file, class, function, method
    path: str
    line_start: int
    line_end: int
    has_docstring: bool
    docstring_length: int = 0
    doc_quality: float = 0.0  # 0.0 - 1.0
    external_docs: list[str] = field(default_factory=list)  # Related doc files
    
    @property
    def is_documented(self) -> bool:
        return self.has_docstring or len(self.external_docs) > 0
    
    @property
    def coverage_score(self) -> float:
        if not self.is_documented:
            return 0.0
        
        # Weighted scoring
        score = 0.0
        if self.has_docstring:
            score += 0.5
            score += min(0.3, self.docstring_length / 200)  # Up to 0.3 for length
        if self.external_docs:
            score += 0.2
        
        return min(1.0, score + self.doc_quality * 0.3)


@dataclass
class FileCoverage:
    """Coverage data for a single file."""
    path: str
    total_items: int
    documented_items: int
    items: list[CoverageItem] = field(default_factory=list)
    
    @property
    def coverage_percent(self) -> float:
        if self.total_items == 0:
            return 100.0  # Empty files are "covered"
        return (self.documented_items / self.total_items) * 100
    
    @property
    def badge_color(self) -> str:
        """Color for shields.io badge."""
        pct = self.coverage_percent
        if pct >= 90:
            return "brightgreen"
        elif pct >= 75:
            return "green"
        elif pct >= 60:
            return "yellowgreen"
        elif pct >= 40:
            return "yellow"
        elif pct >= 20:
            return "orange"
        else:
            return "red"


@dataclass
class CoverageReport:
    """Complete coverage report for a project."""
    project_root: str
    generated_at: str
    total_files: int = 0
    total_items: int = 0
    documented_items: int = 0
    files: list[FileCoverage] = field(default_factory=list)
    by_directory: dict[str, dict] = field(default_factory=dict)
    
    @property
    def overall_percent(self) -> float:
        if self.total_items == 0:
            return 100.0
        return (self.documented_items / self.total_items) * 100
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "project_root": self.project_root,
            "generated_at": self.generated_at,
            "summary": {
                "total_files": self.total_files,
                "total_items": self.total_items,
                "documented_items": self.documented_items,
                "coverage_percent": round(self.overall_percent, 2)
            },
            "files": [
                {
                    "path": f.path,
                    "coverage_percent": round(f.coverage_percent, 2),
                    "total_items": f.total_items,
                    "documented_items": f.documented_items,
                    "items": [asdict(item) for item in f.items]
                }
                for f in self.files
            ],
            "by_directory": self.by_directory
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class CoverageAnalyzer:
    """Analyzes documentation coverage across a codebase."""
    
    def __init__(self, project_root: Path, config: Optional[dict] = None):
        self.project_root = project_root
        self.config = config or {}
        self.history_file = project_root / ".living-docs" / "coverage_history.json"
    
    def analyze(self, patterns: Optional[list[str]] = None) -> CoverageReport:
        """Analyze coverage for the project."""
        patterns = patterns or self.config.get("sources", ["**/*.py"])
        
        report = CoverageReport(
            project_root=str(self.project_root),
            generated_at=datetime.now().isoformat()
        )
        
        dir_stats = defaultdict(lambda: {"total": 0, "documented": 0})
        
        for pattern in patterns:
            for path in self.project_root.glob(pattern):
                if path.is_file() and not self._should_ignore(path):
                    file_coverage = self._analyze_file(path)
                    if file_coverage:
                        report.files.append(file_coverage)
                        report.total_files += 1
                        report.total_items += file_coverage.total_items
                        report.documented_items += file_coverage.documented_items
                        
                        # Aggregate by directory
                        dir_path = str(path.parent.relative_to(self.project_root))
                        dir_stats[dir_path]["total"] += file_coverage.total_items
                        dir_stats[dir_path]["documented"] += file_coverage.documented_items
        
        # Calculate directory percentages
        for dir_path, stats in dir_stats.items():
            if stats["total"] > 0:
                report.by_directory[dir_path] = {
                    "total": stats["total"],
                    "documented": stats["documented"],
                    "percent": round((stats["documented"] / stats["total"]) * 100, 2)
                }
        
        # Save to history
        self._save_history(report)
        
        return report
    
    def _should_ignore(self, path: Path) -> bool:
        """Check if file should be ignored."""
        ignore_patterns = self.config.get("ignore", [
            "__pycache__", "node_modules", ".git", ".venv", "venv",
            "build", "dist", "*.egg-info"
        ])
        
        path_str = str(path)
        for pattern in ignore_patterns:
            if pattern in path_str:
                return True
        return False
    
    def _analyze_file(self, path: Path) -> Optional[FileCoverage]:
        """Analyze a single file for coverage."""
        suffix = path.suffix.lower()
        
        if suffix == ".py":
            return self._analyze_python(path)
        elif suffix in (".ts", ".tsx", ".js", ".jsx"):
            return self._analyze_javascript(path)
        
        return None
    
    def _analyze_python(self, path: Path) -> Optional[FileCoverage]:
        """Analyze a Python file."""
        try:
            content = path.read_text(errors="ignore")
            tree = ast.parse(content)
        except (SyntaxError, UnicodeDecodeError):
            return None
        
        rel_path = str(path.relative_to(self.project_root))
        items = []
        
        # Analyze module docstring
        module_doc = ast.get_docstring(tree)
        items.append(CoverageItem(
            name=path.stem,
            kind="module",
            path=rel_path,
            line_start=1,
            line_end=len(content.split("\n")),
            has_docstring=bool(module_doc),
            docstring_length=len(module_doc) if module_doc else 0,
            doc_quality=self._assess_docstring_quality(module_doc)
        ))
        
        # Analyze classes and functions
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                doc = ast.get_docstring(node)
                items.append(CoverageItem(
                    name=node.name,
                    kind="class",
                    path=rel_path,
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    has_docstring=bool(doc),
                    docstring_length=len(doc) if doc else 0,
                    doc_quality=self._assess_docstring_quality(doc)
                ))
                
                # Methods within class
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        method_doc = ast.get_docstring(item)
                        # Skip magic methods except __init__
                        if item.name.startswith("_") and not item.name == "__init__":
                            continue
                        items.append(CoverageItem(
                            name=f"{node.name}.{item.name}",
                            kind="method",
                            path=rel_path,
                            line_start=item.lineno,
                            line_end=item.end_lineno or item.lineno,
                            has_docstring=bool(method_doc),
                            docstring_length=len(method_doc) if method_doc else 0,
                            doc_quality=self._assess_docstring_quality(method_doc)
                        ))
            
            elif isinstance(node, ast.FunctionDef):
                # Skip nested functions and private
                if node.col_offset == 0 and not node.name.startswith("_"):
                    doc = ast.get_docstring(node)
                    items.append(CoverageItem(
                        name=node.name,
                        kind="function",
                        path=rel_path,
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        has_docstring=bool(doc),
                        docstring_length=len(doc) if doc else 0,
                        doc_quality=self._assess_docstring_quality(doc)
                    ))
        
        documented = sum(1 for item in items if item.is_documented)
        
        return FileCoverage(
            path=rel_path,
            total_items=len(items),
            documented_items=documented,
            items=items
        )
    
    def _analyze_javascript(self, path: Path) -> Optional[FileCoverage]:
        """Analyze a JavaScript/TypeScript file (basic JSDoc detection)."""
        try:
            content = path.read_text(errors="ignore")
        except UnicodeDecodeError:
            return None
        
        rel_path = str(path.relative_to(self.project_root))
        items = []
        
        # Basic regex-based analysis
        import re
        
        # Find exports and functions
        func_pattern = re.compile(
            r'(?:export\s+)?(?:async\s+)?function\s+(\w+)|'
            r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[a-zA-Z_]\w*)\s*=>'
        )
        
        class_pattern = re.compile(r'(?:export\s+)?class\s+(\w+)')
        jsdoc_pattern = re.compile(r'/\*\*[\s\S]*?\*/')
        
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            # Check for function/const
            func_match = func_pattern.match(line.strip())
            if func_match:
                name = func_match.group(1) or func_match.group(2)
                if name and not name.startswith("_"):
                    # Check for preceding JSDoc
                    has_doc = False
                    if i > 0:
                        prev_lines = "\n".join(lines[max(0, i-10):i])
                        if jsdoc_pattern.search(prev_lines):
                            has_doc = True
                    
                    items.append(CoverageItem(
                        name=name,
                        kind="function",
                        path=rel_path,
                        line_start=line_num,
                        line_end=line_num,
                        has_docstring=has_doc
                    ))
            
            # Check for class
            class_match = class_pattern.match(line.strip())
            if class_match:
                name = class_match.group(1)
                has_doc = False
                if i > 0:
                    prev_lines = "\n".join(lines[max(0, i-10):i])
                    if jsdoc_pattern.search(prev_lines):
                        has_doc = True
                
                items.append(CoverageItem(
                    name=name,
                    kind="class",
                    path=rel_path,
                    line_start=line_num,
                    line_end=line_num,
                    has_docstring=has_doc
                ))
        
        if not items:
            return None
        
        documented = sum(1 for item in items if item.is_documented)
        
        return FileCoverage(
            path=rel_path,
            total_items=len(items),
            documented_items=documented,
            items=items
        )
    
    def _assess_docstring_quality(self, docstring: Optional[str]) -> float:
        """Score docstring quality 0.0 - 1.0."""
        if not docstring:
            return 0.0
        
        score = 0.2  # Base for having a docstring
        doc_lower = docstring.lower()
        
        # Length bonus
        if len(docstring) > 50:
            score += 0.15
        if len(docstring) > 100:
            score += 0.1
        
        # Has parameter docs
        if any(x in doc_lower for x in [":param", "args:", "@param", "parameters:"]):
            score += 0.2
        
        # Has return docs
        if any(x in doc_lower for x in [":return", "returns:", "@return", "@returns"]):
            score += 0.15
        
        # Has examples
        if any(x in doc_lower for x in [">>>", "example", "```"]):
            score += 0.1
        
        # Has type info
        if any(x in doc_lower for x in [":type", "@type", "-> "]):
            score += 0.1
        
        return min(1.0, score)
    
    def _save_history(self, report: CoverageReport) -> None:
        """Save coverage to history for trend tracking."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        
        history = []
        if self.history_file.exists():
            try:
                with open(self.history_file) as f:
                    history = json.load(f)
            except json.JSONDecodeError:
                history = []
        
        # Add new entry
        history.append({
            "timestamp": report.generated_at,
            "total_items": report.total_items,
            "documented_items": report.documented_items,
            "percent": round(report.overall_percent, 2)
        })
        
        # Keep last 100 entries
        history = history[-100:]
        
        with open(self.history_file, "w") as f:
            json.dump(history, f, indent=2)
    
    def get_trend(self, days: int = 30) -> list[dict]:
        """Get coverage trend over time."""
        if not self.history_file.exists():
            return []
        
        with open(self.history_file) as f:
            history = json.load(f)
        
        return history[-days:]


class CoverageFormatter:
    """Format coverage reports in various outputs."""
    
    @staticmethod
    def to_ascii_treemap(report: CoverageReport, width: int = 60) -> str:
        """Generate ASCII treemap visualization."""
        lines = []
        lines.append("┌" + "─" * (width - 2) + "┐")
        lines.append("│" + f" Documentation Coverage: {report.overall_percent:.1f}%".center(width - 2) + "│")
        lines.append("├" + "─" * (width - 2) + "┤")
        
        # Sort files by coverage
        sorted_files = sorted(report.files, key=lambda f: f.coverage_percent)
        
        for file in sorted_files[:20]:  # Top 20 files
            pct = file.coverage_percent
            bar_width = int((width - 30) * pct / 100)
            bar = "█" * bar_width + "░" * (width - 30 - bar_width)
            
            # Truncate path
            path = file.path
            if len(path) > 20:
                path = "..." + path[-17:]
            
            color_char = "🟢" if pct >= 80 else "🟡" if pct >= 50 else "🔴"
            line = f"│ {path:<20} {bar} {pct:5.1f}% {color_char}"
            lines.append(line.ljust(width - 1) + "│")
        
        lines.append("└" + "─" * (width - 2) + "┘")
        
        return "\n".join(lines)
    
    @staticmethod
    def to_markdown(report: CoverageReport) -> str:
        """Generate Markdown report."""
        lines = [
            "# Documentation Coverage Report",
            "",
            f"Generated: {report.generated_at}",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Files | {report.total_files} |",
            f"| Total Items | {report.total_items} |",
            f"| Documented | {report.documented_items} |",
            f"| **Coverage** | **{report.overall_percent:.1f}%** |",
            "",
            "## By Directory",
            "",
            "| Directory | Coverage | Items |",
            "|-----------|----------|-------|",
        ]
        
        for dir_path, stats in sorted(report.by_directory.items()):
            lines.append(
                f"| `{dir_path}` | {stats['percent']:.1f}% | {stats['documented']}/{stats['total']} |"
            )
        
        lines.extend([
            "",
            "## Lowest Coverage Files",
            "",
            "| File | Coverage | Missing |",
            "|------|----------|---------|",
        ])
        
        worst_files = sorted(report.files, key=lambda f: f.coverage_percent)[:10]
        for file in worst_files:
            missing = file.total_items - file.documented_items
            lines.append(f"| `{file.path}` | {file.coverage_percent:.1f}% | {missing} |")
        
        return "\n".join(lines)
    
    @staticmethod
    def to_badge_url(report: CoverageReport) -> str:
        """Generate shields.io badge URL."""
        pct = round(report.overall_percent)
        
        # Determine color
        if pct >= 90:
            color = "brightgreen"
        elif pct >= 75:
            color = "green"
        elif pct >= 60:
            color = "yellowgreen"
        elif pct >= 40:
            color = "yellow"
        elif pct >= 20:
            color = "orange"
        else:
            color = "red"
        
        return f"https://img.shields.io/badge/doc%20coverage-{pct}%25-{color}"
    
    @staticmethod
    def to_html_treemap(report: CoverageReport) -> str:
        """Generate HTML treemap visualization."""
        # D3.js based treemap
        data = {
            "name": "root",
            "children": []
        }
        
        dir_groups = defaultdict(list)
        for file in report.files:
            dir_path = os.path.dirname(file.path) or "."
            dir_groups[dir_path].append({
                "name": os.path.basename(file.path),
                "value": file.total_items,
                "coverage": file.coverage_percent,
                "path": file.path
            })
        
        for dir_path, files in dir_groups.items():
            data["children"].append({
                "name": dir_path,
                "children": files
            })
        
        html = f'''<!DOCTYPE html>
<html>
<head>
    <title>Documentation Coverage Treemap</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        body {{ font-family: sans-serif; margin: 0; padding: 20px; }}
        .node {{ stroke: #fff; stroke-width: 1px; }}
        .node text {{ font-size: 11px; pointer-events: none; }}
        .tooltip {{ position: absolute; background: #333; color: #fff; padding: 8px; border-radius: 4px; font-size: 12px; }}
    </style>
</head>
<body>
    <h1>Documentation Coverage: {report.overall_percent:.1f}%</h1>
    <div id="treemap"></div>
    <script>
        const data = {json.dumps(data)};
        
        const width = 960;
        const height = 600;
        
        const color = d3.scaleSequential()
            .domain([0, 100])
            .interpolator(d3.interpolateRdYlGn);
        
        const treemap = d3.treemap()
            .size([width, height])
            .padding(2);
        
        const root = d3.hierarchy(data)
            .sum(d => d.value || 0)
            .sort((a, b) => b.value - a.value);
        
        treemap(root);
        
        const svg = d3.select("#treemap")
            .append("svg")
            .attr("width", width)
            .attr("height", height);
        
        const nodes = svg.selectAll(".node")
            .data(root.leaves())
            .enter()
            .append("g")
            .attr("class", "node")
            .attr("transform", d => `translate(${{d.x0}},${{d.y0}})`);
        
        nodes.append("rect")
            .attr("width", d => d.x1 - d.x0)
            .attr("height", d => d.y1 - d.y0)
            .attr("fill", d => color(d.data.coverage || 0));
        
        nodes.append("text")
            .attr("x", 4)
            .attr("y", 14)
            .text(d => d.data.name?.slice(0, 15) || "");
    </script>
</body>
</html>'''
        
        return html
    
    @staticmethod
    def to_trend_sparkline(history: list[dict], width: int = 20) -> str:
        """Generate ASCII sparkline of coverage trend."""
        if not history:
            return "No history"
        
        percentages = [h["percent"] for h in history]
        min_val = min(percentages)
        max_val = max(percentages)
        range_val = max_val - min_val or 1
        
        chars = "▁▂▃▄▅▆▇█"
        
        sparkline = ""
        for pct in percentages[-width:]:
            idx = int((pct - min_val) / range_val * (len(chars) - 1))
            sparkline += chars[idx]
        
        return f"{sparkline} ({percentages[-1]:.0f}%)"


def generate_coverage_report(project_root: Path, output_format: str = "markdown") -> str:
    """Convenience function to generate a coverage report."""
    analyzer = CoverageAnalyzer(project_root)
    report = analyzer.analyze()
    
    if output_format == "json":
        return report.to_json()
    elif output_format == "markdown":
        return CoverageFormatter.to_markdown(report)
    elif output_format == "ascii":
        return CoverageFormatter.to_ascii_treemap(report)
    elif output_format == "html":
        return CoverageFormatter.to_html_treemap(report)
    elif output_format == "badge":
        return CoverageFormatter.to_badge_url(report)
    else:
        return report.to_json()
