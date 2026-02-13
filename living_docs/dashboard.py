#!/usr/bin/env python3
"""Documentation Dashboard — Living Docs Enhancement

Provides a unified dashboard view of documentation health:
- ASCII terminal dashboard
- HTML dashboard for browsers
- JSON API for integrations
- Real-time metrics
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .freshness import FreshnessScorer, FreshnessReport, FreshnessGrade, grade_to_emoji
from .mapping import CodeDocMapper
from .staleness import StalenessCalculator, find_doc_code_mappings
from .coverage import CoverageAnalyzer, CoverageReport


@dataclass
class DashboardMetrics:
    """Aggregated metrics for the dashboard."""
    total_docs: int = 0
    total_code_files: int = 0
    mapped_docs: int = 0
    orphaned_docs: int = 0
    
    # Freshness
    avg_freshness: float = 0.0
    freshness_by_grade: dict = field(default_factory=dict)
    stale_count: int = 0
    critical_count: int = 0
    
    # Coverage
    coverage_percent: float = 0.0
    documented_items: int = 0
    total_items: int = 0
    
    # Trends
    freshness_trend: list = field(default_factory=list)  # Last 7 days
    coverage_trend: list = field(default_factory=list)
    
    # Top issues
    stale_docs: list = field(default_factory=list)
    missing_docs: list = field(default_factory=list)
    
    generated_at: str = ""


class Dashboard:
    """Documentation health dashboard."""
    
    def __init__(self, project_root: Path, config: Optional[dict] = None):
        self.project_root = project_root
        self.config = config or {}
        self.state_dir = project_root / ".living-docs"
    
    def collect_metrics(self) -> DashboardMetrics:
        """Collect all dashboard metrics."""
        metrics = DashboardMetrics(generated_at=datetime.now().isoformat())
        
        # 1. Mapping metrics
        mapper = CodeDocMapper(self.project_root, self.config)
        mappings = mapper.find_all_mappings()
        report = mapper.get_mapping_report()
        
        metrics.total_docs = len(mapper._doc_files)
        metrics.total_code_files = len(mapper._code_files)
        metrics.mapped_docs = len(set(m.doc_path for m in mappings))
        metrics.orphaned_docs = len(report.get("unmapped_doc_files", []))
        
        # 2. Freshness metrics
        doc_code_map = self._build_doc_code_map(mappings)
        scorer = FreshnessScorer(self.project_root, self.config)
        freshness_reports = scorer.score_all(doc_code_map)
        
        if freshness_reports:
            metrics.avg_freshness = sum(r.score for r in freshness_reports) / len(freshness_reports)
            
            metrics.freshness_by_grade = {
                "excellent": sum(1 for r in freshness_reports if r.grade == FreshnessGrade.EXCELLENT),
                "good": sum(1 for r in freshness_reports if r.grade == FreshnessGrade.GOOD),
                "fair": sum(1 for r in freshness_reports if r.grade == FreshnessGrade.FAIR),
                "stale": sum(1 for r in freshness_reports if r.grade == FreshnessGrade.STALE),
                "critical": sum(1 for r in freshness_reports if r.grade == FreshnessGrade.CRITICAL),
            }
            
            metrics.stale_count = metrics.freshness_by_grade["stale"] + metrics.freshness_by_grade["critical"]
            metrics.critical_count = metrics.freshness_by_grade["critical"]
            
            # Top stale docs
            metrics.stale_docs = [
                {
                    "path": r.doc_path,
                    "score": r.score,
                    "grade": r.grade.value,
                    "days_stale": r.days_stale,
                    "issues": r.issues[:2],
                }
                for r in freshness_reports if r.is_stale
            ][:10]
        
        # 3. Coverage metrics
        try:
            coverage_analyzer = CoverageAnalyzer(self.project_root, self.config)
            coverage_report = coverage_analyzer.analyze()
            
            metrics.coverage_percent = coverage_report.overall_percent
            metrics.documented_items = coverage_report.documented_items
            metrics.total_items = coverage_report.total_items
            
            # Missing docs (undocumented items)
            for file_cov in coverage_report.files:
                for item in file_cov.items:
                    if not item.is_documented:
                        metrics.missing_docs.append({
                            "path": item.path,
                            "name": item.name,
                            "kind": item.kind,
                        })
            
            metrics.missing_docs = metrics.missing_docs[:10]
            
            # Coverage trend
            metrics.coverage_trend = coverage_analyzer.get_trend(7)
        except Exception as e:
            pass
        
        # 4. Load freshness trend if available
        metrics.freshness_trend = self._load_freshness_trend()
        
        return metrics
    
    def _build_doc_code_map(self, mappings) -> dict[Path, list[Path]]:
        """Build doc-to-code mapping from mapping objects."""
        result = {}
        for mapping in mappings:
            doc_path = self.project_root / mapping.doc_path
            code_path = self.project_root / mapping.code_path
            
            if doc_path not in result:
                result[doc_path] = []
            result[doc_path].append(code_path)
        
        return result
    
    def _load_freshness_trend(self) -> list:
        """Load freshness history."""
        history_file = self.state_dir / "freshness_history.json"
        if history_file.exists():
            try:
                with open(history_file) as f:
                    return json.load(f)[-7:]
            except Exception:
                pass
        return []
    
    def save_metrics(self, metrics: DashboardMetrics) -> None:
        """Save metrics for trend tracking."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        # Save current snapshot
        snapshot_file = self.state_dir / "dashboard_snapshot.json"
        with open(snapshot_file, "w") as f:
            json.dump(self._metrics_to_dict(metrics), f, indent=2)
        
        # Append to freshness history
        history_file = self.state_dir / "freshness_history.json"
        history = []
        if history_file.exists():
            try:
                with open(history_file) as f:
                    history = json.load(f)
            except Exception:
                pass
        
        history.append({
            "timestamp": metrics.generated_at,
            "freshness": round(metrics.avg_freshness, 3),
            "coverage": round(metrics.coverage_percent, 2),
            "stale_count": metrics.stale_count,
        })
        
        # Keep last 90 days
        history = history[-90:]
        
        with open(history_file, "w") as f:
            json.dump(history, f, indent=2)
    
    def _metrics_to_dict(self, metrics: DashboardMetrics) -> dict:
        """Convert metrics to dictionary."""
        return {
            "generated_at": metrics.generated_at,
            "summary": {
                "total_docs": metrics.total_docs,
                "total_code_files": metrics.total_code_files,
                "mapped_docs": metrics.mapped_docs,
                "orphaned_docs": metrics.orphaned_docs,
            },
            "freshness": {
                "average": round(metrics.avg_freshness, 3),
                "by_grade": metrics.freshness_by_grade,
                "stale_count": metrics.stale_count,
                "critical_count": metrics.critical_count,
            },
            "coverage": {
                "percent": round(metrics.coverage_percent, 2),
                "documented_items": metrics.documented_items,
                "total_items": metrics.total_items,
            },
            "trends": {
                "freshness": metrics.freshness_trend,
                "coverage": metrics.coverage_trend,
            },
            "issues": {
                "stale_docs": metrics.stale_docs,
                "missing_docs": metrics.missing_docs,
            },
        }
    
    def render_ascii(self, metrics: Optional[DashboardMetrics] = None) -> str:
        """Render ASCII dashboard."""
        if metrics is None:
            metrics = self.collect_metrics()
        
        width = 70
        
        # Build the dashboard
        lines = []
        
        # Header
        lines.append("╔" + "═" * (width - 2) + "╗")
        lines.append("║" + " 📚 DOCUMENTATION HEALTH DASHBOARD ".center(width - 2) + "║")
        lines.append("║" + f" {datetime.now().strftime('%Y-%m-%d %H:%M')} ".center(width - 2) + "║")
        lines.append("╠" + "═" * (width - 2) + "╣")
        
        # Summary row
        health_score = (metrics.avg_freshness * 0.6 + (metrics.coverage_percent / 100) * 0.4)
        health_emoji = "🟢" if health_score > 0.8 else "🟡" if health_score > 0.6 else "🟠" if health_score > 0.4 else "🔴"
        
        lines.append("║" + f"  {health_emoji} Overall Health: {health_score:.0%}".ljust(width - 3) + "║")
        lines.append("╟" + "─" * (width - 2) + "╢")
        
        # Metrics grid
        lines.append("║  📊 METRICS" + " " * (width - 14) + "║")
        
        col1 = f"  Documents: {metrics.total_docs}"
        col2 = f"Code Files: {metrics.total_code_files}"
        lines.append("║" + f"  {col1:<30}{col2:<30}" + "  ║")
        
        col1 = f"  Mapped: {metrics.mapped_docs}"
        col2 = f"Orphaned: {metrics.orphaned_docs}"
        lines.append("║" + f"  {col1:<30}{col2:<30}" + "  ║")
        
        lines.append("╟" + "─" * (width - 2) + "╢")
        
        # Freshness section
        lines.append("║  🕐 FRESHNESS" + " " * (width - 16) + "║")
        
        freshness_bar = self._render_bar(metrics.avg_freshness, 30)
        lines.append("║" + f"  Average: [{freshness_bar}] {metrics.avg_freshness:.0%}".ljust(width - 3) + "║")
        
        grades_str = (
            f"🟢{metrics.freshness_by_grade.get('excellent', 0)} "
            f"🟡{metrics.freshness_by_grade.get('good', 0)} "
            f"🟠{metrics.freshness_by_grade.get('fair', 0)} "
            f"🔴{metrics.freshness_by_grade.get('stale', 0)} "
            f"🔥{metrics.freshness_by_grade.get('critical', 0)}"
        )
        lines.append("║" + f"  By Grade: {grades_str}".ljust(width - 3) + "║")
        
        if metrics.stale_count > 0:
            lines.append("║" + f"  ⚠️  {metrics.stale_count} stale docs ({metrics.critical_count} critical)".ljust(width - 3) + "║")
        
        lines.append("╟" + "─" * (width - 2) + "╢")
        
        # Coverage section
        lines.append("║  📝 COVERAGE" + " " * (width - 15) + "║")
        
        coverage_bar = self._render_bar(metrics.coverage_percent / 100, 30)
        lines.append("║" + f"  Overall: [{coverage_bar}] {metrics.coverage_percent:.1f}%".ljust(width - 3) + "║")
        lines.append("║" + f"  Documented: {metrics.documented_items}/{metrics.total_items} items".ljust(width - 3) + "║")
        
        lines.append("╟" + "─" * (width - 2) + "╢")
        
        # Issues section
        lines.append("║  ⚠️  TOP ISSUES" + " " * (width - 18) + "║")
        
        if metrics.stale_docs:
            for doc in metrics.stale_docs[:3]:
                emoji = grade_to_emoji(FreshnessGrade(doc["grade"]))
                name = Path(doc["path"]).name[:25]
                lines.append("║" + f"    {emoji} {name} - {doc['days_stale']}d stale".ljust(width - 3) + "║")
        
        if metrics.missing_docs:
            lines.append("║" + "  Missing documentation:".ljust(width - 3) + "║")
            for item in metrics.missing_docs[:2]:
                lines.append("║" + f"    • {item['name']} ({item['kind']})".ljust(width - 3) + "║")
        
        if not metrics.stale_docs and not metrics.missing_docs:
            lines.append("║" + "    ✨ No critical issues!".ljust(width - 3) + "║")
        
        lines.append("╟" + "─" * (width - 2) + "╢")
        
        # Trend sparklines
        lines.append("║  📈 TRENDS (last 7 days)" + " " * (width - 27) + "║")
        
        if metrics.freshness_trend:
            sparkline = self._render_sparkline([t.get("freshness", 0) for t in metrics.freshness_trend])
            lines.append("║" + f"    Freshness: {sparkline}".ljust(width - 3) + "║")
        
        if metrics.coverage_trend:
            sparkline = self._render_sparkline([t.get("percent", 0) for t in metrics.coverage_trend])
            lines.append("║" + f"    Coverage:  {sparkline}".ljust(width - 3) + "║")
        
        # Footer
        lines.append("╚" + "═" * (width - 2) + "╝")
        
        return "\n".join(lines)
    
    def _render_bar(self, value: float, width: int) -> str:
        """Render a progress bar."""
        filled = int(value * width)
        return "█" * filled + "░" * (width - filled)
    
    def _render_sparkline(self, values: list, width: int = 15) -> str:
        """Render a sparkline."""
        if not values:
            return "─" * width
        
        chars = "▁▂▃▄▅▆▇█"
        min_val = min(values) if values else 0
        max_val = max(values) if values else 1
        range_val = max_val - min_val or 1
        
        sparkline = ""
        for v in values[-width:]:
            idx = int((v - min_val) / range_val * (len(chars) - 1))
            sparkline += chars[idx]
        
        # Pad if needed
        sparkline = sparkline.ljust(width, "─")
        
        return sparkline
    
    def render_html(self, metrics: Optional[DashboardMetrics] = None) -> str:
        """Render HTML dashboard."""
        if metrics is None:
            metrics = self.collect_metrics()
        
        health_score = (metrics.avg_freshness * 0.6 + (metrics.coverage_percent / 100) * 0.4)
        
        html = f'''<!DOCTYPE html>
<html>
<head>
    <title>Documentation Health Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            margin: 0;
            padding: 20px;
            min-height: 100vh;
        }}
        .dashboard {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            padding: 30px;
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            margin: 0 0 10px;
            font-size: 2.5em;
        }}
        .health-score {{
            font-size: 4em;
            font-weight: bold;
            color: {"#4caf50" if health_score > 0.8 else "#ffc107" if health_score > 0.5 else "#f44336"};
        }}
        .cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        .card {{
            background: rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 20px;
            backdrop-filter: blur(10px);
        }}
        .card h3 {{
            margin: 0 0 15px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .metric {{
            display: flex;
            justify-content: space-between;
            margin: 10px 0;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        .metric:last-child {{ border-bottom: none; }}
        .metric-value {{
            font-weight: bold;
            font-size: 1.1em;
        }}
        .progress-bar {{
            height: 20px;
            background: rgba(255,255,255,0.1);
            border-radius: 10px;
            overflow: hidden;
            margin: 10px 0;
        }}
        .progress-fill {{
            height: 100%;
            border-radius: 10px;
            transition: width 0.5s ease;
        }}
        .progress-fill.freshness {{
            background: linear-gradient(90deg, #f44336, #ffc107, #4caf50);
            width: {metrics.avg_freshness * 100}%;
        }}
        .progress-fill.coverage {{
            background: linear-gradient(90deg, #2196f3, #4caf50);
            width: {metrics.coverage_percent}%;
        }}
        .grade-badges {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .badge {{
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.9em;
        }}
        .badge.excellent {{ background: #4caf50; }}
        .badge.good {{ background: #8bc34a; }}
        .badge.fair {{ background: #ffc107; color: #333; }}
        .badge.stale {{ background: #ff9800; }}
        .badge.critical {{ background: #f44336; }}
        .issues-list {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        .issues-list li {{
            padding: 10px;
            margin: 5px 0;
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .issue-icon {{ font-size: 1.5em; }}
        .timestamp {{
            text-align: center;
            color: #888;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="dashboard">
        <div class="header">
            <h1>📚 Documentation Health</h1>
            <div class="health-score">{health_score:.0%}</div>
            <p>Overall Health Score</p>
        </div>
        
        <div class="cards">
            <div class="card">
                <h3>📊 Overview</h3>
                <div class="metric">
                    <span>Total Documents</span>
                    <span class="metric-value">{metrics.total_docs}</span>
                </div>
                <div class="metric">
                    <span>Code Files</span>
                    <span class="metric-value">{metrics.total_code_files}</span>
                </div>
                <div class="metric">
                    <span>Mapped Docs</span>
                    <span class="metric-value">{metrics.mapped_docs}</span>
                </div>
                <div class="metric">
                    <span>Orphaned Docs</span>
                    <span class="metric-value">{metrics.orphaned_docs}</span>
                </div>
            </div>
            
            <div class="card">
                <h3>🕐 Freshness</h3>
                <div class="progress-bar">
                    <div class="progress-fill freshness"></div>
                </div>
                <p style="text-align:center;">{metrics.avg_freshness:.0%} Average Freshness</p>
                <div class="grade-badges">
                    <span class="badge excellent">🟢 {metrics.freshness_by_grade.get('excellent', 0)}</span>
                    <span class="badge good">🟡 {metrics.freshness_by_grade.get('good', 0)}</span>
                    <span class="badge fair">🟠 {metrics.freshness_by_grade.get('fair', 0)}</span>
                    <span class="badge stale">🔴 {metrics.freshness_by_grade.get('stale', 0)}</span>
                    <span class="badge critical">🔥 {metrics.freshness_by_grade.get('critical', 0)}</span>
                </div>
            </div>
            
            <div class="card">
                <h3>📝 Coverage</h3>
                <div class="progress-bar">
                    <div class="progress-fill coverage"></div>
                </div>
                <p style="text-align:center;">{metrics.coverage_percent:.1f}% Coverage</p>
                <div class="metric">
                    <span>Documented Items</span>
                    <span class="metric-value">{metrics.documented_items}</span>
                </div>
                <div class="metric">
                    <span>Total Items</span>
                    <span class="metric-value">{metrics.total_items}</span>
                </div>
            </div>
            
            <div class="card">
                <h3>⚠️ Issues</h3>
                <ul class="issues-list">'''
        
        # Add stale docs
        for doc in metrics.stale_docs[:5]:
            emoji = {"excellent": "🟢", "good": "🟡", "fair": "🟠", "stale": "🔴", "critical": "🔥"}.get(doc["grade"], "❓")
            html += f'''
                    <li>
                        <span class="issue-icon">{emoji}</span>
                        <div>
                            <strong>{Path(doc["path"]).name}</strong><br>
                            <small>{doc["days_stale"]} days stale</small>
                        </div>
                    </li>'''
        
        if not metrics.stale_docs:
            html += '''
                    <li>
                        <span class="issue-icon">✨</span>
                        <span>No critical issues!</span>
                    </li>'''
        
        html += f'''
                </ul>
            </div>
        </div>
        
        <p class="timestamp">Generated: {metrics.generated_at}</p>
    </div>
</body>
</html>'''
        
        return html
    
    def render_json(self, metrics: Optional[DashboardMetrics] = None) -> str:
        """Render JSON dashboard data."""
        if metrics is None:
            metrics = self.collect_metrics()
        
        return json.dumps(self._metrics_to_dict(metrics), indent=2)


def run_dashboard(project_root: Path, format: str = "ascii", output: Optional[Path] = None) -> str:
    """Run dashboard and return/save output."""
    from .cli import load_config
    
    config = load_config(project_root)
    dashboard = Dashboard(project_root, config)
    
    metrics = dashboard.collect_metrics()
    dashboard.save_metrics(metrics)
    
    if format == "html":
        result = dashboard.render_html(metrics)
    elif format == "json":
        result = dashboard.render_json(metrics)
    else:
        result = dashboard.render_ascii(metrics)
    
    if output:
        output.write_text(result)
        return f"Dashboard saved to {output}"
    
    return result
