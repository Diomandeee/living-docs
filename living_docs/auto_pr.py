"""
Auto-PR Creation Module (Gen 9)

Automatically creates pull requests with documentation fixes.
Integrates with GitHub/GitLab APIs to:
- Create branches for doc updates
- Generate meaningful commit messages
- Open PRs with detailed descriptions
- Request reviews from relevant maintainers
"""

import os
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


class PRProvider(Enum):
    """Supported PR providers."""
    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"


@dataclass
class DocFix:
    """Represents a documentation fix to be included in a PR."""
    file_path: str
    original_content: str
    fixed_content: str
    fix_type: str  # 'stale', 'missing', 'example', 'typo', 'structure'
    description: str
    severity: str  # 'critical', 'high', 'medium', 'low'
    line_range: Optional[tuple] = None
    related_code: Optional[str] = None


@dataclass
class PRConfig:
    """Configuration for auto-PR creation."""
    provider: PRProvider = PRProvider.GITHUB
    base_branch: str = "main"
    branch_prefix: str = "docs/"
    auto_merge: bool = False
    draft: bool = True
    reviewers: List[str] = field(default_factory=list)
    labels: List[str] = field(default_factory=lambda: ["documentation", "auto-generated"])
    commit_prefix: str = "docs:"
    max_files_per_pr: int = 10
    group_by: str = "severity"  # 'severity', 'type', 'directory', 'single'


class AutoPRCreator:
    """Creates pull requests for documentation fixes."""
    
    def __init__(self, config: Optional[PRConfig] = None, project_root: Optional[Path] = None):
        self.config = config or PRConfig()
        self.project_root = project_root or Path.cwd()
        self._detect_provider()
    
    def _detect_provider(self) -> None:
        """Auto-detect PR provider from git remote."""
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, cwd=self.project_root
            )
            remote = result.stdout.strip().lower()
            
            if "github" in remote:
                self.config.provider = PRProvider.GITHUB
            elif "gitlab" in remote:
                self.config.provider = PRProvider.GITLAB
            elif "bitbucket" in remote:
                self.config.provider = PRProvider.BITBUCKET
        except Exception:
            pass  # Default to GitHub
    
    def _run_git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command."""
        return subprocess.run(
            ["git", *args],
            capture_output=True, text=True,
            cwd=self.project_root, check=check
        )
    
    def _generate_branch_name(self, fixes: List[DocFix]) -> str:
        """Generate a meaningful branch name."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M")
        
        if len(fixes) == 1:
            fix = fixes[0]
            file_stem = Path(fix.file_path).stem.replace("_", "-")
            return f"{self.config.branch_prefix}{fix.fix_type}-{file_stem}-{timestamp}"
        
        # Group name
        types = set(f.fix_type for f in fixes)
        if len(types) == 1:
            type_name = types.pop()
        else:
            type_name = "mixed"
        
        return f"{self.config.branch_prefix}{type_name}-{len(fixes)}-fixes-{timestamp}"
    
    def _generate_commit_message(self, fixes: List[DocFix]) -> str:
        """Generate a conventional commit message."""
        if len(fixes) == 1:
            fix = fixes[0]
            file_name = Path(fix.file_path).name
            return f"{self.config.commit_prefix} {fix.fix_type}: {fix.description} ({file_name})"
        
        # Summary for multiple fixes
        by_type: Dict[str, int] = {}
        for fix in fixes:
            by_type[fix.fix_type] = by_type.get(fix.fix_type, 0) + 1
        
        type_summary = ", ".join(f"{count} {t}" for t, count in sorted(by_type.items()))
        return f"{self.config.commit_prefix} update {len(fixes)} docs ({type_summary})"
    
    def _generate_pr_title(self, fixes: List[DocFix]) -> str:
        """Generate a PR title."""
        if len(fixes) == 1:
            fix = fixes[0]
            return f"📚 {fix.fix_type.title()}: {fix.description}"
        
        severities = [f.severity for f in fixes]
        critical = severities.count("critical")
        high = severities.count("high")
        
        priority = ""
        if critical > 0:
            priority = "🔴 "
        elif high > 0:
            priority = "🟠 "
        
        return f"{priority}📚 Documentation Updates ({len(fixes)} fixes)"
    
    def _generate_pr_body(self, fixes: List[DocFix]) -> str:
        """Generate a detailed PR description."""
        lines = [
            "## 📚 Auto-Generated Documentation Update",
            "",
            "This PR was automatically created by **Living Documentation** to keep docs in sync with code.",
            "",
            "### Summary",
            "",
            f"- **Total fixes:** {len(fixes)}",
        ]
        
        # Severity breakdown
        by_severity: Dict[str, List[DocFix]] = {}
        for fix in fixes:
            by_severity.setdefault(fix.severity, []).append(fix)
        
        severity_icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
        for sev in ["critical", "high", "medium", "low"]:
            if sev in by_severity:
                icon = severity_icons[sev]
                lines.append(f"- **{icon} {sev.title()}:** {len(by_severity[sev])}")
        
        lines.extend(["", "### Changes", ""])
        
        # List each fix
        for i, fix in enumerate(fixes, 1):
            icon = {"stale": "🕰️", "missing": "➕", "example": "💡", "typo": "✏️", "structure": "🏗️"}.get(fix.fix_type, "📝")
            lines.append(f"#### {i}. {icon} `{fix.file_path}`")
            lines.append(f"- **Type:** {fix.fix_type}")
            lines.append(f"- **Severity:** {fix.severity}")
            lines.append(f"- **Description:** {fix.description}")
            if fix.related_code:
                lines.append(f"- **Related code:** `{fix.related_code}`")
            lines.append("")
        
        lines.extend([
            "### Validation",
            "",
            "- [ ] Documentation renders correctly",
            "- [ ] Links are valid",
            "- [ ] Examples are runnable",
            "- [ ] No sensitive information exposed",
            "",
            "---",
            "",
            "*🤖 Generated by [Living Documentation](https://github.com/living-docs/living-docs)*",
        ])
        
        return "\n".join(lines)
    
    def group_fixes(self, fixes: List[DocFix]) -> List[List[DocFix]]:
        """Group fixes according to configuration."""
        if self.config.group_by == "single":
            return [[fix] for fix in fixes]
        
        if self.config.group_by == "severity":
            groups: Dict[str, List[DocFix]] = {}
            for fix in fixes:
                groups.setdefault(fix.severity, []).append(fix)
            return list(groups.values())
        
        if self.config.group_by == "type":
            groups = {}
            for fix in fixes:
                groups.setdefault(fix.fix_type, []).append(fix)
            return list(groups.values())
        
        if self.config.group_by == "directory":
            groups = {}
            for fix in fixes:
                dir_path = str(Path(fix.file_path).parent)
                groups.setdefault(dir_path, []).append(fix)
            return list(groups.values())
        
        # Default: all in one
        return [fixes] if fixes else []
    
    def create_branch(self, branch_name: str) -> bool:
        """Create and checkout a new branch."""
        try:
            # Ensure we're on the base branch
            self._run_git("checkout", self.config.base_branch)
            self._run_git("pull", "--rebase")
            
            # Create new branch
            self._run_git("checkout", "-b", branch_name)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to create branch: {e.stderr}")
            return False
    
    def apply_fixes(self, fixes: List[DocFix]) -> List[str]:
        """Apply fixes to files and stage them."""
        changed_files = []
        
        for fix in fixes:
            file_path = self.project_root / fix.file_path
            
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(fix.fixed_content)
                changed_files.append(fix.file_path)
            except Exception as e:
                print(f"Failed to apply fix to {fix.file_path}: {e}")
        
        # Stage all changed files
        if changed_files:
            self._run_git("add", *changed_files)
        
        return changed_files
    
    def commit(self, message: str) -> bool:
        """Commit staged changes."""
        try:
            self._run_git("commit", "-m", message)
            return True
        except subprocess.CalledProcessError:
            return False
    
    def push(self, branch_name: str, force: bool = False) -> bool:
        """Push branch to remote."""
        try:
            args = ["push", "-u", "origin", branch_name]
            if force:
                args.insert(1, "--force")
            self._run_git(*args)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to push: {e.stderr}")
            return False
    
    def create_github_pr(self, branch_name: str, title: str, body: str) -> Optional[Dict]:
        """Create a PR on GitHub using gh CLI."""
        try:
            cmd = [
                "gh", "pr", "create",
                "--title", title,
                "--body", body,
                "--base", self.config.base_branch,
                "--head", branch_name,
            ]
            
            if self.config.draft:
                cmd.append("--draft")
            
            for label in self.config.labels:
                cmd.extend(["--label", label])
            
            for reviewer in self.config.reviewers:
                cmd.extend(["--reviewer", reviewer])
            
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                cwd=self.project_root, check=True
            )
            
            # Parse PR URL from output
            pr_url = result.stdout.strip()
            return {"url": pr_url, "branch": branch_name}
            
        except subprocess.CalledProcessError as e:
            print(f"Failed to create PR: {e.stderr}")
            return None
        except FileNotFoundError:
            print("gh CLI not found. Please install: https://cli.github.com/")
            return None
    
    def create_gitlab_mr(self, branch_name: str, title: str, body: str) -> Optional[Dict]:
        """Create a merge request on GitLab using glab CLI."""
        try:
            cmd = [
                "glab", "mr", "create",
                "--title", title,
                "--description", body,
                "--source-branch", branch_name,
                "--target-branch", self.config.base_branch,
            ]
            
            if self.config.draft:
                cmd.append("--draft")
            
            for label in self.config.labels:
                cmd.extend(["--label", label])
            
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                cwd=self.project_root, check=True
            )
            
            return {"url": result.stdout.strip(), "branch": branch_name}
            
        except subprocess.CalledProcessError as e:
            print(f"Failed to create MR: {e.stderr}")
            return None
        except FileNotFoundError:
            print("glab CLI not found. Please install GitLab CLI.")
            return None
    
    def create_pr(self, fixes: List[DocFix], dry_run: bool = False) -> Optional[Dict]:
        """Create a PR for a group of fixes."""
        if not fixes:
            return None
        
        branch_name = self._generate_branch_name(fixes)
        commit_message = self._generate_commit_message(fixes)
        pr_title = self._generate_pr_title(fixes)
        pr_body = self._generate_pr_body(fixes)
        
        if dry_run:
            return {
                "dry_run": True,
                "branch": branch_name,
                "commit_message": commit_message,
                "title": pr_title,
                "body": pr_body,
                "files": [f.file_path for f in fixes],
            }
        
        # Create branch
        if not self.create_branch(branch_name):
            return None
        
        # Apply and commit
        changed = self.apply_fixes(fixes)
        if not changed:
            self._run_git("checkout", self.config.base_branch, check=False)
            return None
        
        if not self.commit(commit_message):
            self._run_git("checkout", self.config.base_branch, check=False)
            return None
        
        # Push
        if not self.push(branch_name):
            self._run_git("checkout", self.config.base_branch, check=False)
            return None
        
        # Create PR/MR
        if self.config.provider == PRProvider.GITHUB:
            result = self.create_github_pr(branch_name, pr_title, pr_body)
        elif self.config.provider == PRProvider.GITLAB:
            result = self.create_gitlab_mr(branch_name, pr_title, pr_body)
        else:
            result = {"branch": branch_name, "manual": True}
        
        # Return to base branch
        self._run_git("checkout", self.config.base_branch, check=False)
        
        return result
    
    def create_prs(
        self,
        fixes: List[DocFix],
        dry_run: bool = False,
        interactive: bool = False
    ) -> List[Dict]:
        """Create PRs for all fixes, grouped according to config."""
        groups = self.group_fixes(fixes)
        results = []
        
        for group in groups:
            if len(group) > self.config.max_files_per_pr:
                # Split into smaller chunks
                for i in range(0, len(group), self.config.max_files_per_pr):
                    chunk = group[i:i + self.config.max_files_per_pr]
                    
                    if interactive:
                        files = [f.file_path for f in chunk]
                        print(f"\n📋 PR would include: {', '.join(files)}")
                        response = input("Create this PR? [Y/n/s(kip)] ").strip().lower()
                        if response == 's':
                            continue
                        if response == 'n':
                            return results
                    
                    result = self.create_pr(chunk, dry_run=dry_run)
                    if result:
                        results.append(result)
            else:
                if interactive:
                    files = [f.file_path for f in group]
                    print(f"\n📋 PR would include: {', '.join(files)}")
                    response = input("Create this PR? [Y/n/s(kip)] ").strip().lower()
                    if response == 's':
                        continue
                    if response == 'n':
                        return results
                
                result = self.create_pr(group, dry_run=dry_run)
                if result:
                    results.append(result)
        
        return results


class DocFixCollector:
    """Collects documentation fixes from various sources."""
    
    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path.cwd()
        self.fixes: List[DocFix] = []
    
    def from_staleness_report(self, report: Dict) -> List[DocFix]:
        """Create fixes from staleness analysis."""
        fixes = []
        
        for item in report.get("stale_docs", []):
            # This would integrate with the staleness module
            fixes.append(DocFix(
                file_path=item["path"],
                original_content=item.get("content", ""),
                fixed_content=item.get("suggested_content", item.get("content", "")),
                fix_type="stale",
                description=f"Doc outdated by {item.get('days_stale', '?')} days",
                severity=item.get("severity", "medium"),
                related_code=item.get("related_code"),
            ))
        
        return fixes
    
    def from_ai_improvements(self, improvements: List[Dict]) -> List[DocFix]:
        """Create fixes from AI improvement suggestions."""
        fixes = []
        
        for imp in improvements:
            fixes.append(DocFix(
                file_path=imp["path"],
                original_content=imp["original"],
                fixed_content=imp["improved"],
                fix_type=imp.get("type", "structure"),
                description=imp.get("description", "AI-suggested improvement"),
                severity=imp.get("severity", "low"),
            ))
        
        return fixes
    
    def from_example_validation(self, report: Dict) -> List[DocFix]:
        """Create fixes from example validation failures."""
        fixes = []
        
        for invalid in report.get("invalid", []):
            # Would need AI to generate fixes
            fixes.append(DocFix(
                file_path=invalid["file"],
                original_content=invalid.get("example", ""),
                fixed_content=invalid.get("fixed", invalid.get("example", "")),
                fix_type="example",
                description=f"Invalid example: {invalid.get('error', 'unknown')}",
                severity="high",
                line_range=(invalid.get("line"), invalid.get("line_end")),
            ))
        
        return fixes
    
    def from_coverage_gaps(self, report: Dict) -> List[DocFix]:
        """Create fixes for undocumented code."""
        fixes = []
        
        for gap in report.get("undocumented", []):
            # Would use AI to generate documentation
            fixes.append(DocFix(
                file_path=gap.get("suggested_doc_path", f"docs/{gap['code_file']}.md"),
                original_content="",
                fixed_content=gap.get("generated_doc", "# TODO: Document this"),
                fix_type="missing",
                description=f"Missing docs for {gap['code_file']}",
                severity="medium",
                related_code=gap["code_file"],
            ))
        
        return fixes


def format_pr_results(results: List[Dict], format_type: str = "human") -> str:
    """Format PR creation results."""
    if format_type == "json":
        return json.dumps(results, indent=2)
    
    if format_type == "markdown":
        lines = ["# Auto-PR Results", ""]
        for r in results:
            if r.get("dry_run"):
                lines.append(f"## 🔍 Dry Run: `{r['branch']}`")
                lines.append(f"- **Files:** {len(r['files'])}")
                lines.append(f"- **Title:** {r['title']}")
            elif r.get("url"):
                lines.append(f"## ✅ Created: [{r['branch']}]({r['url']})")
            else:
                lines.append(f"## ⚠️ Manual: `{r['branch']}`")
            lines.append("")
        return "\n".join(lines)
    
    # Human readable
    lines = ["\n=== Auto-PR Results ===\n"]
    for r in results:
        if r.get("dry_run"):
            lines.append(f"🔍 [DRY RUN] Would create: {r['branch']}")
            lines.append(f"   Files: {', '.join(r['files'])}")
            lines.append(f"   Title: {r['title']}")
        elif r.get("url"):
            lines.append(f"✅ Created PR: {r['url']}")
        elif r.get("manual"):
            lines.append(f"⚠️ Branch pushed: {r['branch']} (create PR manually)")
        lines.append("")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Demo usage
    print("Living Documentation - Auto-PR Creator (Gen 9)")
    print("=" * 50)
    
    creator = AutoPRCreator()
    
    # Example fixes
    demo_fixes = [
        DocFix(
            file_path="docs/api.md",
            original_content="# API\nOld content",
            fixed_content="# API\n\nUpdated content with new endpoints",
            fix_type="stale",
            description="Updated API documentation with new endpoints",
            severity="high",
            related_code="src/api.py",
        ),
        DocFix(
            file_path="docs/quickstart.md",
            original_content="```python\nold_function()\n```",
            fixed_content="```python\nnew_function(arg1, arg2)\n```",
            fix_type="example",
            description="Fixed deprecated function call in example",
            severity="critical",
        ),
    ]
    
    # Dry run
    results = creator.create_prs(demo_fixes, dry_run=True)
    print(format_pr_results(results))
