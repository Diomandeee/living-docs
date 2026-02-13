#!/usr/bin/env python3
"""Enhanced Freshness Scoring System — Living Docs Enhancement

Provides a multi-factor freshness scoring system that considers:
- Time since last update (decay)
- Code change frequency
- API surface changes
- Semantic drift detection
- External dependency changes
"""

from __future__ import annotations

import subprocess
import re
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from enum import Enum


class FreshnessGrade(Enum):
    """Freshness grades for documentation."""
    EXCELLENT = "excellent"  # 90-100%
    GOOD = "good"           # 70-89%
    FAIR = "fair"           # 50-69%
    STALE = "stale"         # 30-49%
    CRITICAL = "critical"   # 0-29%


@dataclass
class FreshnessFactors:
    """Individual factors contributing to freshness score."""
    time_decay: float = 1.0          # Based on age since last update
    code_velocity: float = 1.0       # How often related code changes
    api_drift: float = 1.0           # Signature/interface changes
    semantic_alignment: float = 1.0  # Content still matches code
    completeness: float = 1.0        # Doc covers all public APIs
    example_validity: float = 1.0    # Code examples still work
    
    def weighted_score(self, weights: Optional[dict] = None) -> float:
        """Calculate weighted freshness score."""
        default_weights = {
            "time_decay": 0.25,
            "code_velocity": 0.15,
            "api_drift": 0.25,
            "semantic_alignment": 0.15,
            "completeness": 0.10,
            "example_validity": 0.10,
        }
        weights = weights or default_weights
        
        score = 0.0
        for factor, weight in weights.items():
            factor_value = getattr(self, factor, 1.0)
            score += factor_value * weight
        
        return min(1.0, max(0.0, score))
    
    def to_dict(self) -> dict:
        return {
            "time_decay": round(self.time_decay, 3),
            "code_velocity": round(self.code_velocity, 3),
            "api_drift": round(self.api_drift, 3),
            "semantic_alignment": round(self.semantic_alignment, 3),
            "completeness": round(self.completeness, 3),
            "example_validity": round(self.example_validity, 3),
        }


@dataclass
class FreshnessReport:
    """Detailed freshness report for a documentation file."""
    doc_path: str
    related_code: list[str]
    score: float
    grade: FreshnessGrade
    factors: FreshnessFactors
    last_doc_update: Optional[datetime] = None
    last_code_update: Optional[datetime] = None
    days_stale: int = 0
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    
    @property
    def is_stale(self) -> bool:
        return self.grade in (FreshnessGrade.STALE, FreshnessGrade.CRITICAL)
    
    @property
    def needs_attention(self) -> bool:
        return self.grade != FreshnessGrade.EXCELLENT
    
    def to_dict(self) -> dict:
        return {
            "doc_path": self.doc_path,
            "related_code": self.related_code,
            "score": round(self.score, 3),
            "grade": self.grade.value,
            "factors": self.factors.to_dict(),
            "last_doc_update": self.last_doc_update.isoformat() if self.last_doc_update else None,
            "last_code_update": self.last_code_update.isoformat() if self.last_code_update else None,
            "days_stale": self.days_stale,
            "issues": self.issues,
            "recommendations": self.recommendations,
        }


class FreshnessScorer:
    """Advanced freshness scoring engine."""
    
    def __init__(
        self,
        repo_root: Path,
        config: Optional[dict] = None
    ):
        self.repo_root = repo_root
        self.config = config or {}
        
        # Thresholds
        self.excellent_days = self.config.get("excellent_days", 7)
        self.good_days = self.config.get("good_days", 30)
        self.fair_days = self.config.get("fair_days", 60)
        self.stale_days = self.config.get("stale_days", 90)
        
        # Decay curve factor (higher = faster decay)
        self.decay_factor = self.config.get("decay_factor", 0.03)
    
    def score_document(
        self,
        doc_path: Path,
        related_code: list[Path],
    ) -> FreshnessReport:
        """Calculate comprehensive freshness score for a document."""
        factors = FreshnessFactors()
        issues = []
        recommendations = []
        
        # 1. Time decay factor
        doc_modified = self._get_last_modified(doc_path)
        code_modified = self._get_latest_code_modified(related_code)
        
        if doc_modified and code_modified:
            if code_modified > doc_modified:
                days_stale = (code_modified - doc_modified).days
                # Exponential decay: score = e^(-k*days)
                factors.time_decay = math.exp(-self.decay_factor * days_stale)
                
                if days_stale > self.stale_days:
                    issues.append(f"Documentation is {days_stale} days behind code")
                    recommendations.append("Urgent: Review and update documentation")
                elif days_stale > self.fair_days:
                    issues.append(f"Documentation lagging {days_stale} days")
                    recommendations.append("Schedule documentation review")
            else:
                days_stale = 0
                factors.time_decay = 1.0
        else:
            days_stale = 0
            factors.time_decay = 0.5  # Unknown state
            issues.append("Could not determine modification dates")
        
        # 2. Code velocity factor
        factors.code_velocity = self._calculate_code_velocity(related_code)
        if factors.code_velocity < 0.5:
            issues.append("High code churn detected")
            recommendations.append("Increase documentation update frequency")
        
        # 3. API drift factor
        factors.api_drift = self._calculate_api_drift(doc_path, related_code, doc_modified)
        if factors.api_drift < 0.7:
            issues.append("API signatures may have changed")
            recommendations.append("Verify function/class signatures in documentation")
        
        # 4. Semantic alignment (check if doc mentions current code entities)
        factors.semantic_alignment = self._calculate_semantic_alignment(doc_path, related_code)
        if factors.semantic_alignment < 0.6:
            issues.append("Documentation may reference outdated code entities")
            recommendations.append("Update code references in documentation")
        
        # 5. Completeness factor
        factors.completeness = self._calculate_completeness(doc_path, related_code)
        if factors.completeness < 0.8:
            issues.append(f"Documentation covers only {factors.completeness:.0%} of public APIs")
            recommendations.append("Add documentation for missing functions/classes")
        
        # 6. Example validity (check if code blocks still parse)
        factors.example_validity = self._check_example_validity(doc_path)
        if factors.example_validity < 0.9:
            issues.append("Some code examples may be invalid")
            recommendations.append("Test and update code examples")
        
        # Calculate overall score
        score = factors.weighted_score()
        
        # Determine grade
        if score >= 0.9:
            grade = FreshnessGrade.EXCELLENT
        elif score >= 0.7:
            grade = FreshnessGrade.GOOD
        elif score >= 0.5:
            grade = FreshnessGrade.FAIR
        elif score >= 0.3:
            grade = FreshnessGrade.STALE
        else:
            grade = FreshnessGrade.CRITICAL
        
        return FreshnessReport(
            doc_path=str(doc_path),
            related_code=[str(p) for p in related_code],
            score=score,
            grade=grade,
            factors=factors,
            last_doc_update=doc_modified,
            last_code_update=code_modified,
            days_stale=days_stale,
            issues=issues,
            recommendations=recommendations,
        )
    
    def _get_last_modified(self, path: Path) -> Optional[datetime]:
        """Get last modification date from git."""
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%cI", "--", str(path)],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                return datetime.fromisoformat(result.stdout.strip().replace("Z", "+00:00"))
        except Exception:
            pass
        
        if path.exists():
            return datetime.fromtimestamp(path.stat().st_mtime)
        return None
    
    def _get_latest_code_modified(self, code_paths: list[Path]) -> Optional[datetime]:
        """Get most recent modification among code files."""
        latest = None
        for path in code_paths:
            modified = self._get_last_modified(path)
            if modified and (latest is None or modified > latest):
                latest = modified
        return latest
    
    def _calculate_code_velocity(self, code_paths: list[Path]) -> float:
        """Calculate how fast code is changing (lower = more changes)."""
        try:
            # Count commits in last 90 days
            since = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
            total_commits = 0
            
            for path in code_paths:
                result = subprocess.run(
                    ["git", "log", "--oneline", f"--since={since}", "--", str(path)],
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    total_commits += len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0
            
            # More commits = lower score (harder to keep docs fresh)
            # 0-5 commits = 1.0, 10+ commits = 0.5
            if total_commits <= 5:
                return 1.0
            elif total_commits >= 20:
                return 0.3
            else:
                return 1.0 - (total_commits - 5) * 0.05
        except Exception:
            return 0.7  # Unknown
    
    def _calculate_api_drift(
        self,
        doc_path: Path,
        code_paths: list[Path],
        since: Optional[datetime]
    ) -> float:
        """Check if function/class signatures changed since doc update."""
        if not since:
            return 0.5
        
        try:
            signature_changes = 0
            since_str = since.strftime("%Y-%m-%d")
            
            for code_path in code_paths:
                result = subprocess.run(
                    ["git", "diff", f"@{{\"{since_str}\"}}", "--", str(code_path)],
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                )
                
                if result.returncode == 0:
                    diff = result.stdout
                    # Count signature-changing patterns
                    signature_changes += len(re.findall(r"[-+]\s*def \w+\(", diff))
                    signature_changes += len(re.findall(r"[-+]\s*class \w+", diff))
                    signature_changes += len(re.findall(r"[-+]\s*async def \w+", diff))
            
            # Fewer signature changes = higher score
            if signature_changes == 0:
                return 1.0
            elif signature_changes <= 3:
                return 0.8
            elif signature_changes <= 10:
                return 0.5
            else:
                return 0.2
        except Exception:
            return 0.7
    
    def _calculate_semantic_alignment(
        self,
        doc_path: Path,
        code_paths: list[Path]
    ) -> float:
        """Check if doc mentions current code entities."""
        if not doc_path.exists():
            return 0.0
        
        try:
            doc_content = doc_path.read_text().lower()
            code_entities = set()
            
            for code_path in code_paths:
                if not code_path.exists():
                    continue
                
                content = code_path.read_text()
                
                # Extract function and class names
                code_entities.update(re.findall(r"def (\w+)\(", content))
                code_entities.update(re.findall(r"class (\w+)", content))
                code_entities.update(re.findall(r"async def (\w+)\(", content))
            
            if not code_entities:
                return 1.0
            
            # Check how many code entities are mentioned in docs
            mentioned = sum(1 for entity in code_entities if entity.lower() in doc_content)
            return mentioned / len(code_entities)
        except Exception:
            return 0.5
    
    def _calculate_completeness(
        self,
        doc_path: Path,
        code_paths: list[Path]
    ) -> float:
        """Calculate what percentage of public APIs are documented."""
        if not doc_path.exists():
            return 0.0
        
        try:
            doc_content = doc_path.read_text().lower()
            public_apis = set()
            
            for code_path in code_paths:
                if not code_path.exists():
                    continue
                
                content = code_path.read_text()
                
                # Only count public (non-underscore) APIs
                for match in re.findall(r"def (\w+)\(", content):
                    if not match.startswith("_"):
                        public_apis.add(match)
                
                for match in re.findall(r"class (\w+)", content):
                    if not match.startswith("_"):
                        public_apis.add(match)
            
            if not public_apis:
                return 1.0
            
            documented = sum(1 for api in public_apis if api.lower() in doc_content)
            return documented / len(public_apis)
        except Exception:
            return 0.5
    
    def _check_example_validity(self, doc_path: Path) -> float:
        """Check if code examples in documentation are syntactically valid."""
        if not doc_path.exists():
            return 1.0
        
        try:
            content = doc_path.read_text()
            
            # Find Python code blocks
            code_blocks = re.findall(r"```python\n(.*?)```", content, re.DOTALL)
            
            if not code_blocks:
                return 1.0
            
            valid = 0
            for block in code_blocks:
                try:
                    compile(block, "<string>", "exec")
                    valid += 1
                except SyntaxError:
                    pass
            
            return valid / len(code_blocks)
        except Exception:
            return 0.5
    
    def score_all(self, doc_code_map: dict[Path, list[Path]]) -> list[FreshnessReport]:
        """Score all documentation files."""
        reports = []
        
        for doc_path, code_paths in doc_code_map.items():
            if doc_path.exists():
                report = self.score_document(doc_path, code_paths)
                reports.append(report)
        
        # Sort by score (lowest first = most urgent)
        reports.sort(key=lambda r: r.score)
        
        return reports


def grade_to_emoji(grade: FreshnessGrade) -> str:
    """Convert grade to emoji."""
    return {
        FreshnessGrade.EXCELLENT: "🟢",
        FreshnessGrade.GOOD: "🟡",
        FreshnessGrade.FAIR: "🟠",
        FreshnessGrade.STALE: "🔴",
        FreshnessGrade.CRITICAL: "🔥",
    }.get(grade, "❓")


def format_freshness_report(reports: list[FreshnessReport]) -> str:
    """Format freshness reports as human-readable text."""
    lines = [
        "📊 Documentation Freshness Report",
        "=" * 50,
        "",
    ]
    
    # Summary
    total = len(reports)
    excellent = sum(1 for r in reports if r.grade == FreshnessGrade.EXCELLENT)
    good = sum(1 for r in reports if r.grade == FreshnessGrade.GOOD)
    fair = sum(1 for r in reports if r.grade == FreshnessGrade.FAIR)
    stale = sum(1 for r in reports if r.grade == FreshnessGrade.STALE)
    critical = sum(1 for r in reports if r.grade == FreshnessGrade.CRITICAL)
    
    avg_score = sum(r.score for r in reports) / total if total else 0
    
    lines.extend([
        f"Total documents: {total}",
        f"Average freshness: {avg_score:.1%}",
        "",
        f"🟢 Excellent: {excellent}",
        f"🟡 Good: {good}",
        f"🟠 Fair: {fair}",
        f"🔴 Stale: {stale}",
        f"🔥 Critical: {critical}",
        "",
    ])
    
    # Details for non-excellent docs
    needs_attention = [r for r in reports if r.needs_attention]
    
    if needs_attention:
        lines.extend([
            "📋 Documents Needing Attention:",
            "-" * 40,
        ])
        
        for report in needs_attention[:10]:
            emoji = grade_to_emoji(report.grade)
            lines.append(f"\n{emoji} {Path(report.doc_path).name} ({report.score:.1%})")
            
            for issue in report.issues[:2]:
                lines.append(f"   ⚠️  {issue}")
            
            for rec in report.recommendations[:1]:
                lines.append(f"   💡 {rec}")
    
    return "\n".join(lines)
