#!/usr/bin/env python3
"""CI/CD integration for Living Documentation.

Provides GitHub Actions, pre-commit hooks, and CI pipelines
that fail builds when documentation is too stale.
"""

import json
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class CIResult(Enum):
    """CI check result."""
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class CIReport:
    """Report from CI check."""
    result: CIResult
    score: float  # 0.0 - 1.0
    coverage: float  # 0.0 - 1.0
    stale_count: int
    critical_count: int
    warnings: list[str]
    errors: list[str]
    summary: str
    
    def to_github_output(self) -> str:
        """Format as GitHub Actions output."""
        lines = [
            f"result={self.result.value}",
            f"score={self.score:.2f}",
            f"coverage={self.coverage:.2f}",
            f"stale_count={self.stale_count}",
            f"critical_count={self.critical_count}",
        ]
        return "\n".join(lines)
    
    def to_github_annotations(self) -> list[str]:
        """Generate GitHub Actions annotations."""
        annotations = []
        
        for warning in self.warnings:
            annotations.append(f"::warning ::{warning}")
        
        for error in self.errors:
            annotations.append(f"::error ::{error}")
        
        return annotations
    
    def to_markdown(self) -> str:
        """Format as markdown for PR comments."""
        emoji = "✅" if self.result == CIResult.PASS else "⚠️" if self.result == CIResult.WARN else "❌"
        
        md = f"""## {emoji} Documentation Health Report

| Metric | Value |
|--------|-------|
| **Overall Score** | {self.score:.0%} |
| **Coverage** | {self.coverage:.0%} |
| **Stale Files** | {self.stale_count} |
| **Critical Issues** | {self.critical_count} |

### Summary
{self.summary}
"""
        
        if self.errors:
            md += "\n### ❌ Errors\n"
            for error in self.errors:
                md += f"- {error}\n"
        
        if self.warnings:
            md += "\n### ⚠️ Warnings\n"
            for warning in self.warnings:
                md += f"- {warning}\n"
        
        return md


def run_ci_check(project_root: Path, config: dict) -> CIReport:
    """Run documentation CI check and return report."""
    from .staleness import StalenessCalculator, find_doc_code_mappings
    from .parser import get_parser
    
    ci_config = config.get("ci", {})
    fail_on_stale = ci_config.get("fail_on_stale", True)
    min_coverage = ci_config.get("min_coverage", 0.5)
    min_score = ci_config.get("min_score", 0.6)
    staleness_threshold = config.get("staleness", {}).get("critical", 90)
    
    warnings = []
    errors = []
    
    # Find all source files and doc files
    import glob
    sources = []
    for pattern in config.get("sources", ["**/*.py"]):
        sources.extend(project_root.glob(pattern))
    
    docs = []
    for doc_path in config.get("docs", ["docs"]):
        doc_dir = project_root / doc_path
        if doc_dir.is_dir():
            docs.extend(doc_dir.glob("**/*.md"))
        elif doc_dir.is_file():
            docs.append(doc_dir)
    
    # Calculate coverage
    total_functions = 0
    documented_functions = 0
    quality_scores = []
    
    for source in sources:
        if not source.is_file():
            continue
        try:
            parser = get_parser(source.suffix)
            if parser:
                content = source.read_text()
                result = parser.parse(content, str(source))
                for func in result.functions:
                    total_functions += 1
                    if func.docstring:
                        documented_functions += 1
                        quality_scores.append(func.quality_score)
        except Exception:
            pass  # Skip unparseable files
    
    coverage = documented_functions / max(total_functions, 1)
    avg_quality = sum(quality_scores) / max(len(quality_scores), 1) if quality_scores else 0.5
    
    # Check staleness
    calc = StalenessCalculator(project_root)
    mappings = find_doc_code_mappings(project_root, config)
    
    stale_count = 0
    critical_count = 0
    
    for mapping in mappings:
        staleness = calc.calculate(mapping["doc"], mapping.get("code"))
        if staleness.is_stale:
            stale_count += 1
            if staleness.days_stale > staleness_threshold:
                critical_count += 1
                errors.append(f"{mapping['doc']}: {staleness.days_stale} days stale (critical)")
            else:
                warnings.append(f"{mapping['doc']}: {staleness.days_stale} days stale")
    
    # Determine result
    result = CIResult.PASS
    
    if coverage < min_coverage:
        warnings.append(f"Coverage {coverage:.0%} below minimum {min_coverage:.0%}")
        result = CIResult.WARN
    
    if avg_quality < min_score:
        warnings.append(f"Quality score {avg_quality:.0%} below minimum {min_score:.0%}")
        result = CIResult.WARN
    
    if critical_count > 0 and fail_on_stale:
        result = CIResult.FAIL
    
    overall_score = (coverage * 0.3 + avg_quality * 0.4 + 
                    (1 - min(stale_count / max(len(docs), 1), 1)) * 0.3)
    
    summary = f"Found {total_functions} functions, {documented_functions} documented. "
    summary += f"{stale_count} stale docs, {critical_count} critical."
    
    return CIReport(
        result=result,
        score=overall_score,
        coverage=coverage,
        stale_count=stale_count,
        critical_count=critical_count,
        warnings=warnings,
        errors=errors,
        summary=summary
    )


def generate_github_action() -> str:
    """Generate GitHub Actions workflow file."""
    return """name: Documentation Health

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  doc-check:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history for staleness detection
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install living-docs
        run: pip install living-docs[all]
      
      - name: Run documentation health check
        id: doc-health
        run: |
          living-docs ci --format github >> $GITHUB_OUTPUT
        continue-on-error: true
      
      - name: Generate report
        run: living-docs ci --format markdown > doc-report.md
      
      - name: Comment on PR
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const report = fs.readFileSync('doc-report.md', 'utf8');
            
            // Find existing comment
            const { data: comments } = await github.rest.issues.listComments({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number
            });
            
            const botComment = comments.find(c => 
              c.user.type === 'Bot' && c.body.includes('Documentation Health Report')
            );
            
            if (botComment) {
              await github.rest.issues.updateComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                comment_id: botComment.id,
                body: report
              });
            } else {
              await github.rest.issues.createComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: context.issue.number,
                body: report
              });
            }
      
      - name: Check result
        if: steps.doc-health.outputs.result == 'fail'
        run: |
          echo "Documentation health check failed!"
          exit 1
"""


def generate_pre_commit_hook() -> str:
    """Generate pre-commit hook configuration."""
    return """# Add to .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: living-docs-check
        name: Documentation Health Check
        entry: living-docs ci --fail-on-critical
        language: python
        types: [python, markdown]
        pass_filenames: false
        additional_dependencies: ['living-docs[all]']
"""


def generate_gitlab_ci() -> str:
    """Generate GitLab CI configuration."""
    return """# Add to .gitlab-ci.yml
doc-health:
  image: python:3.11
  stage: test
  script:
    - pip install living-docs[all]
    - living-docs ci --format gitlab
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
  artifacts:
    reports:
      junit: doc-report.xml
    paths:
      - doc-report.md
"""


def cmd_ci(args):
    """Run CI check from command line."""
    from .cli import load_config
    
    project_root = Path(args.path).resolve()
    config = load_config(project_root)
    
    report = run_ci_check(project_root, config)
    
    if args.format == "github":
        print(report.to_github_output())
        for annotation in report.to_github_annotations():
            print(annotation)
    elif args.format == "markdown":
        print(report.to_markdown())
    elif args.format == "json":
        print(json.dumps({
            "result": report.result.value,
            "score": report.score,
            "coverage": report.coverage,
            "stale_count": report.stale_count,
            "critical_count": report.critical_count,
            "warnings": report.warnings,
            "errors": report.errors,
            "summary": report.summary
        }, indent=2))
    else:
        # Default human-readable
        emoji = "✅" if report.result == CIResult.PASS else "⚠️" if report.result == CIResult.WARN else "❌"
        print(f"\n{emoji} Documentation Health: {report.result.value.upper()}")
        print(f"   Score: {report.score:.0%}")
        print(f"   Coverage: {report.coverage:.0%}")
        print(f"   Stale: {report.stale_count} files ({report.critical_count} critical)")
        print(f"\n   {report.summary}\n")
        
        for warning in report.warnings:
            print(f"   ⚠️  {warning}")
        for error in report.errors:
            print(f"   ❌  {error}")
    
    # Exit with appropriate code
    if args.fail_on_critical and report.result == CIResult.FAIL:
        sys.exit(1)
    elif args.strict and report.result != CIResult.PASS:
        sys.exit(1)
    
    return 0
