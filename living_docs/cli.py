#!/usr/bin/env python3
"""Living Documentation CLI."""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

from .parser import get_parser
from .sync import SyncEngine
from .staleness import StalenessCalculator, find_doc_code_mappings


CONFIG_FILE = '.living-docs.yaml'
DEFAULT_CONFIG = {
    'sources': ['src/**/*.py', 'lib/**/*.py', '**/*.py'],
    'docs': ['docs'],
    'staleness': {'warning': 30, 'critical': 90}
}


def load_config(project_root: Path) -> dict:
    """Load config from file or return defaults."""
    config_path = project_root / CONFIG_FILE
    
    if config_path.exists():
        try:
            import yaml
            with open(config_path) as f:
                return {**DEFAULT_CONFIG, **yaml.safe_load(f)}
        except ImportError:
            print("Warning: PyYAML not installed, using defaults")
        except Exception as e:
            print(f"Warning: Could not load config: {e}")
    
    return DEFAULT_CONFIG


def cmd_init(args):
    """Initialize Living Docs in current project."""
    project_root = Path(args.path).resolve()
    
    # Create config file
    config_path = project_root / CONFIG_FILE
    if config_path.exists() and not args.force:
        print(f"Config already exists: {config_path}")
        print("Use --force to overwrite")
        return 1
    
    config_content = """# Living Documentation Configuration

# Code sources to watch
sources:
  - src/**/*.py
  - lib/**/*.ts

# Documentation directories
docs:
  - docs/
  - README.md

# Staleness thresholds (days)
staleness:
  warning: 30
  critical: 90

# AI provider (optional)
# ai:
#   provider: anthropic
#   model: claude-sonnet-4-20250514
"""
    
    config_path.write_text(config_content)
    print(f"✓ Created {config_path}")
    
    # Create docs directory
    docs_dir = project_root / 'docs'
    docs_dir.mkdir(exist_ok=True)
    print(f"✓ Created {docs_dir}")
    
    # Create .living-docs for state
    state_dir = project_root / '.living-docs'
    state_dir.mkdir(exist_ok=True)
    (state_dir / '.gitignore').write_text("daemon.pid\ndaemon.log\n")
    print(f"✓ Created {state_dir}")
    
    print("\n🎉 Living Docs initialized!")
    print("Run `living-docs watch` to start watching for changes.")
    return 0


def cmd_health(args):
    """Show documentation health report."""
    project_root = Path(args.path).resolve()
    config = load_config(project_root)
    
    # Scan code
    doc_root = project_root / config['docs'][0]
    engine = SyncEngine(project_root, doc_root)
    
    items = engine.scan_code(config['sources'])
    
    # Calculate stats
    total = len(items)
    documented = sum(1 for i in items if i.is_documented)
    quality_sum = sum(i.doc_quality_score for i in items)
    
    # Check staleness
    mappings = find_doc_code_mappings(project_root)
    staleness_cfg = config.get('staleness', {})
    calculator = StalenessCalculator(
        project_root,
        warning_days=staleness_cfg.get('warning', 30),
        critical_days=staleness_cfg.get('critical', 90)
    )
    staleness_reports = calculator.scan_project(mappings)
    
    stale_count = sum(1 for r in staleness_reports if r.is_stale)
    
    # Print report
    print("\n📊 Documentation Health Report")
    print("=" * 40)
    print(f"Project: {project_root.name}")
    print(f"Scanned: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print()
    
    # Coverage
    coverage = (documented / total * 100) if total > 0 else 0
    coverage_bar = "█" * int(coverage / 5) + "░" * (20 - int(coverage / 5))
    print(f"Coverage: {documented}/{total} ({coverage:.1f}%)")
    print(f"  [{coverage_bar}]")
    print()
    
    # Quality
    avg_quality = (quality_sum / total * 100) if total > 0 else 0
    quality_bar = "█" * int(avg_quality / 5) + "░" * (20 - int(avg_quality / 5))
    print(f"Quality:  {avg_quality:.1f}%")
    print(f"  [{quality_bar}]")
    print()
    
    # Staleness
    print(f"Staleness:")
    for report in staleness_reports[:5]:  # Top 5
        icon = {"fresh": "✓", "warning": "⚠", "stale": "⏰", "critical": "🔥"}.get(report.severity, "?")
        print(f"  {icon} {Path(report.doc_path).name}: {report.reason}")
    
    if len(staleness_reports) > 5:
        print(f"  ... and {len(staleness_reports) - 5} more")
    print()
    
    # Overall score
    overall = (coverage * 0.4 + avg_quality * 0.4 + (100 - stale_count * 10) * 0.2)
    grade = "A" if overall >= 90 else "B" if overall >= 80 else "C" if overall >= 70 else "D" if overall >= 60 else "F"
    print(f"Overall: {grade} ({overall:.1f}/100)")
    
    return 0


def cmd_stale(args):
    """List stale documentation."""
    project_root = Path(args.path).resolve()
    config = load_config(project_root)
    
    mappings = find_doc_code_mappings(project_root)
    staleness_cfg = config.get('staleness', {})
    calculator = StalenessCalculator(
        project_root,
        warning_days=staleness_cfg.get('warning', 30),
        critical_days=staleness_cfg.get('critical', 90)
    )
    
    reports = calculator.scan_project(mappings)
    stale = [r for r in reports if r.severity in ('warning', 'stale', 'critical')]
    
    if not stale:
        print("✓ All documentation is fresh!")
        return 0
    
    print(f"\n⏰ Stale Documentation ({len(stale)} files)")
    print("=" * 50)
    
    for report in stale:
        icon = {"warning": "⚠️ ", "stale": "🕐", "critical": "🔥"}.get(report.severity, "")
        print(f"\n{icon} {report.doc_path}")
        print(f"   Last doc update: {report.doc_last_modified.strftime('%Y-%m-%d')}")
        print(f"   Last code change: {report.code_last_modified.strftime('%Y-%m-%d')}")
        print(f"   Days stale: {report.days_stale}")
        print(f"   Reason: {report.reason}")
        if report.suggested_action:
            print(f"   Action: {report.suggested_action}")
    
    return 0


def cmd_generate(args):
    """Generate documentation for undocumented code."""
    project_root = Path(args.path).resolve()
    config = load_config(project_root)
    
    doc_root = project_root / config['docs'][0]
    engine = SyncEngine(project_root, doc_root)
    
    actions = engine.compute_sync_actions(config['sources'])
    creates = [a for a in actions if a.action == 'create']
    
    if not creates:
        print("✓ All code has documentation!")
        return 0
    
    print(f"\n📝 Missing Documentation ({len(creates)} files)")
    print("=" * 50)
    
    for action in creates:
        print(f"\n→ {action.doc_path}")
        print(f"  From: {action.code_path}")
        
        if args.dry_run:
            print("  [DRY RUN - would create]")
        else:
            engine.apply_action(action, dry_run=False)
            print("  ✓ Created")
    
    return 0


def cmd_sync(args):
    """One-shot sync of all documentation."""
    project_root = Path(args.path).resolve()
    config = load_config(project_root)
    
    doc_root = project_root / config['docs'][0]
    engine = SyncEngine(project_root, doc_root)
    
    actions = engine.compute_sync_actions(config['sources'])
    
    if not actions:
        print("✓ All documentation is in sync!")
        return 0
    
    print(f"\n🔄 Sync Actions ({len(actions)} pending)")
    print("=" * 50)
    
    for action in actions:
        icon = {"create": "➕", "update": "✏️", "delete": "🗑️"}.get(action.action, "?")
        print(f"\n{icon} {action.action.upper()}: {action.doc_path}")
        print(f"   From: {action.code_path}")
        print(f"   Reason: {action.reason}")
        print(f"   Confidence: {action.confidence * 100:.0f}%")
        
        if not args.dry_run and (args.yes or input("   Apply? [y/N] ").lower() == 'y'):
            engine.apply_action(action, dry_run=False)
            print("   ✓ Applied")
    
    return 0


def cmd_watch(args):
    """Start file watcher daemon."""
    from .watcher import Daemon, HAS_WATCHDOG
    
    if not HAS_WATCHDOG:
        print("Error: watchdog package required")
        print("Install with: pip install watchdog")
        return 1
    
    project_root = Path(args.path).resolve()
    config = load_config(project_root)
    
    # Check if already running
    status = Daemon.status(project_root)
    if status['running']:
        print(f"Daemon already running (PID {status['pid']})")
        return 1
    
    daemon = Daemon(project_root, config)
    daemon.start(foreground=args.foreground)
    return 0


def cmd_stop(args):
    """Stop file watcher daemon."""
    from .watcher import Daemon
    
    project_root = Path(args.path).resolve()
    
    if Daemon.kill(project_root):
        print("✓ Daemon stopped")
        return 0
    else:
        print("Daemon not running")
        return 1


def cmd_status(args):
    """Show daemon status."""
    from .watcher import Daemon
    
    project_root = Path(args.path).resolve()
    status = Daemon.status(project_root)
    
    if status['running']:
        print(f"✓ Daemon running (PID {status['pid']})")
    else:
        print("○ Daemon not running")
    
    return 0


def cmd_improve(args):
    """AI-powered documentation improvement."""
    from .ai import DocImprover, load_ai_config
    from .semantic import SemanticIndex, get_embedding_provider
    
    project_root = Path(args.path).resolve()
    config = load_config(project_root)
    
    # Initialize AI improver
    ai_config = load_ai_config(config)
    improver = DocImprover(ai_config)
    
    # Get doc file to improve
    doc_path = Path(args.file).resolve() if args.file else None
    
    if doc_path is None:
        # Find docs needing improvement
        doc_dir = project_root / config['docs'][0]
        if doc_dir.is_dir():
            docs = list(doc_dir.glob("**/*.md"))[:5]  # Top 5
        else:
            docs = [doc_dir]
    else:
        docs = [doc_path]
    
    # Get code context via semantic similarity
    code_context = ""
    if args.with_context:
        try:
            cache_dir = project_root / '.living-docs' / 'embeddings'
            provider = get_embedding_provider(config)
            index = SemanticIndex(provider, cache_dir)
            
            # Index code files
            for pattern in config.get('sources', ['**/*.py'])[:3]:
                for code_file in list(project_root.glob(pattern))[:20]:
                    if code_file.is_file():
                        try:
                            index.add_file(code_file, "code")
                        except Exception:
                            pass
            
            # Index doc
            for doc in docs:
                index.add_file(doc, "doc")
            
            code_context = index.get_code_context_for_doc(docs[0])
        except Exception as e:
            print(f"Warning: Could not get code context: {e}")
    
    for doc in docs:
        print(f"\n🔍 Analyzing: {doc.name}")
        print("-" * 40)
        
        try:
            if args.analyze_only:
                analysis = improver.analyze(doc, code_context)
                
                print(f"Quality Score:      {analysis.quality_score:.0%}")
                print(f"Readability:        {analysis.readability_score:.0%}")
                print(f"Completeness:       {analysis.completeness_score:.0%}")
                print()
                print(f"Summary: {analysis.summary}")
                
                if analysis.issues:
                    print("\n⚠️  Issues Found:")
                    for issue in analysis.issues:
                        print(f"  • [{issue.get('type', 'issue')}] {issue.get('description', '')}")
                
                if analysis.suggestions:
                    print("\n💡 Suggestions:")
                    for suggestion in analysis.suggestions:
                        print(f"  • {suggestion}")
            else:
                analysis = improver.improve(doc, code_context)
                
                print(f"Quality: {analysis.quality_score:.0%} → improved")
                
                if args.dry_run:
                    print("\n📝 Improved version (preview):")
                    print("-" * 40)
                    # Show diff-like preview
                    print(analysis.improved_content[:2000])
                    if len(analysis.improved_content) > 2000:
                        print(f"\n... ({len(analysis.improved_content) - 2000} more chars)")
                else:
                    # Write improved version
                    if args.inplace:
                        doc.write_text(analysis.improved_content)
                        print(f"✓ Updated {doc}")
                    else:
                        improved_path = doc.with_suffix('.improved.md')
                        improved_path.write_text(analysis.improved_content)
                        print(f"✓ Saved to {improved_path}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
    
    return 0


def cmd_ci(args):
    """Run CI/CD documentation check."""
    from .cicd import run_ci_check, CIResult
    
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
        import json as json_module
        print(json_module.dumps({
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


def cmd_related(args):
    """Find related documentation for code changes."""
    from .semantic import SemanticIndex, get_embedding_provider
    
    project_root = Path(args.path).resolve()
    config = load_config(project_root)
    
    cache_dir = project_root / '.living-docs' / 'embeddings'
    
    try:
        provider = get_embedding_provider(config)
    except Exception as e:
        print(f"Error initializing embeddings: {e}")
        print("\nTip: For local embeddings, install sentence-transformers:")
        print("  pip install sentence-transformers")
        return 1
    
    index = SemanticIndex(provider, cache_dir)
    
    print("📊 Building semantic index...")
    
    # Index code files
    code_count = 0
    for pattern in config.get('sources', ['**/*.py']):
        for code_file in project_root.glob(pattern):
            if code_file.is_file() and '.living-docs' not in str(code_file):
                try:
                    index.add_file(code_file, "code")
                    code_count += 1
                except Exception:
                    pass
    
    # Index doc files
    doc_count = 0
    for doc_path in config.get('docs', ['docs']):
        doc_dir = project_root / doc_path
        if doc_dir.is_dir():
            for doc_file in doc_dir.glob("**/*.md"):
                try:
                    index.add_file(doc_file, "doc")
                    doc_count += 1
                except Exception:
                    pass
        elif doc_dir.is_file():
            try:
                index.add_file(doc_dir, "doc")
                doc_count += 1
            except Exception:
                pass
    
    print(f"   Indexed {code_count} code files, {doc_count} doc files")
    
    # Build embeddings
    print("   Computing embeddings...")
    index.build_embeddings()
    
    # If specific file provided, find related docs
    if args.file:
        code_path = Path(args.file).resolve()
        print(f"\n🔗 Documentation related to: {code_path.name}")
        print("-" * 50)
        
        results = index.find_related_docs(code_path, top_k=args.top, min_score=args.threshold)
        
        if not results:
            print("No related documentation found.")
        else:
            for result in results:
                score_bar = "█" * int(result.score * 10)
                print(f"\n📄 {Path(result.target.path).name}")
                print(f"   Score: [{score_bar}{'░' * (10 - len(score_bar))}] {result.score:.0%}")
                print(f"   {result.explanation}")
    else:
        # Find docs needing update based on recent git changes
        print("\n🔍 Finding docs potentially affected by recent changes...")
        
        # Get recently changed files from git
        import subprocess
        try:
            result = subprocess.run(
                ['git', 'diff', '--name-only', 'HEAD~5', 'HEAD'],
                capture_output=True, text=True, cwd=project_root
            )
            changed_files = [project_root / f for f in result.stdout.strip().split('\n') if f]
            changed_code = [f for f in changed_files if f.suffix in ['.py', '.ts', '.js']]
            
            if changed_code:
                results = index.find_docs_needing_update(changed_code, threshold=args.threshold)
                
                if results:
                    print(f"\n⚠️  {len(results)} docs may need updates:")
                    for result in results:
                        print(f"\n   📄 {Path(result.target.path).name}")
                        print(f"      Related to: {Path(result.source.path).name}")
                        print(f"      Similarity: {result.score:.0%}")
                else:
                    print("✓ No documentation appears to need updating.")
            else:
                print("No recent code changes found.")
        except Exception as e:
            print(f"Could not analyze git changes: {e}")
    
    # Save index
    index.save(cache_dir / 'index.json')
    
    return 0


def cmd_setup_ci(args):
    """Generate CI/CD configuration files."""
    from .cicd import generate_github_action, generate_pre_commit_hook, generate_gitlab_ci
    
    project_root = Path(args.path).resolve()
    
    if args.provider == "github" or args.provider == "all":
        workflow_dir = project_root / '.github' / 'workflows'
        workflow_dir.mkdir(parents=True, exist_ok=True)
        workflow_file = workflow_dir / 'doc-health.yml'
        workflow_file.write_text(generate_github_action())
        print(f"✓ Created {workflow_file}")
    
    if args.provider == "gitlab" or args.provider == "all":
        gitlab_file = project_root / '.gitlab-ci-docs.yml'
        gitlab_file.write_text(generate_gitlab_ci())
        print(f"✓ Created {gitlab_file}")
        print("  (Merge into your .gitlab-ci.yml)")
    
    if args.provider == "pre-commit" or args.provider == "all":
        hook_content = generate_pre_commit_hook()
        print("\n📋 Pre-commit hook configuration:")
        print("-" * 40)
        print(hook_content)
    
    print("\n🎉 CI/CD setup complete!")
    return 0


def cmd_diff(args):
    """Analyze git diff for documentation impact (Gen 7)."""
    from .diff_analyzer import DiffAnalyzer
    
    project_root = Path(args.path).resolve()
    analyzer = DiffAnalyzer(project_root)
    
    try:
        report = analyzer.analyze(
            base=args.base,
            target=getattr(args, 'target', None),
            staged=args.staged,
        )
    except Exception as e:
        print(f"Error analyzing diff: {e}")
        return 1
    
    if args.format == "json":
        print(report.to_json())
    elif args.format == "markdown":
        print(report.to_markdown())
    elif args.format == "github":
        # Output GitHub Actions annotations
        for annotation in report.to_github_annotations():
            level = annotation['level']
            file = annotation['file']
            line = annotation['line']
            msg = annotation['message']
            title = annotation['title']
            print(f"::{level} file={file},line={line},title={title}::{msg}")
        if not report.impacts:
            print("✅ No documentation updates needed")
    else:
        # Human-readable output
        print("\n📊 Documentation Impact Analysis")
        print("=" * 50)
        
        if not report.changes:
            print("\n✅ No code changes detected.")
            return 0
        
        print(f"\n📝 {len(report.changes)} code changes analyzed")
        
        # Show changes by severity
        summary = report.summary
        if summary['by_severity']['critical']:
            print(f"   🚨 {summary['by_severity']['critical']} critical")
        if summary['by_severity']['high']:
            print(f"   ⚠️  {summary['by_severity']['high']} high priority")
        if summary['by_severity']['medium']:
            print(f"   📋 {summary['by_severity']['medium']} medium")
        if summary['by_severity']['low']:
            print(f"   📎 {summary['by_severity']['low']} low")
        
        if not report.impacts:
            print("\n✅ No documentation updates needed for these changes.")
            return 0
        
        print(f"\n📚 {len(report.impacts)} documentation files affected:")
        
        for impact in report.impacts:
            severity_icon = {
                "critical": "🚨",
                "high": "⚠️",
                "medium": "📋",
                "low": "📎"
            }.get(impact.code_change.severity if impact.code_change else "low", "📎")
            
            print(f"\n   {severity_icon} {impact.doc_file}")
            if impact.section:
                print(f"      Section: {impact.section}")
            print(f"      Reason: {impact.reason}")
            print(f"      Action: {impact.suggested_action}")
    
    return 0


def cmd_pr_check(args):
    """Check PR for documentation impact (Gen 7)."""
    from .diff_analyzer import analyze_pr
    
    project_root = Path(args.path).resolve()
    
    try:
        report = analyze_pr(
            repo_path=str(project_root),
            base_branch=args.base,
        )
    except Exception as e:
        print(f"Error analyzing PR: {e}")
        return 1
    
    if args.format == "json":
        print(report.to_json())
    elif args.format == "markdown":
        print(report.to_markdown())
    elif args.format == "github":
        for annotation in report.to_github_annotations():
            level = annotation['level']
            file = annotation['file']
            line = annotation['line']
            msg = annotation['message']
            title = annotation['title']
            print(f"::{level} file={file},line={line},title={title}::{msg}")
    else:
        print(report.to_markdown())
    
    # Check for critical issues
    if args.fail_on_critical:
        critical_count = sum(
            1 for i in report.impacts
            if i.code_change and i.code_change.severity == "critical"
        )
        if critical_count > 0:
            print(f"\n❌ {critical_count} critical documentation updates required!")
            return 1
    
    return 0


def cmd_graph(args):
    """Build and query the documentation knowledge graph."""
    from .graph import GraphBuilder, DocGraph, suggest_navigation
    
    project_root = Path(args.path).resolve()
    config = load_config(project_root)
    
    if args.action == 'build':
        print("🔗 Building documentation knowledge graph...")
        builder = GraphBuilder(project_root, config)
        graph = builder.build()
        
        print(f"\n✓ Graph built:")
        print(f"  Nodes: {len(graph.nodes)}")
        print(f"  Edges: {len(graph.edges)}")
        
        # Summary by type
        from collections import Counter
        types = Counter(n.node_type.value for n in graph.nodes.values())
        for t, count in types.most_common():
            print(f"    {t}: {count}")
        
        return 0
    
    # Load existing graph
    graph = DocGraph(project_root)
    if not graph.load():
        print("❌ No graph found. Run `living-docs graph build` first.")
        return 1
    
    if args.action == 'orphans':
        orphans = graph.get_orphans()
        if not orphans:
            print("✓ No orphaned documentation found!")
        else:
            print(f"⚠️  {len(orphans)} orphaned docs (no connections):\n")
            for node in orphans:
                print(f"  - {node.path or node.name}")
    
    elif args.action == 'hubs':
        hubs = graph.get_hubs(args.top)
        print(f"📊 Top {len(hubs)} most connected nodes:\n")
        for node, count in hubs:
            print(f"  {count:3d} connections: {node.name} ({node.node_type.value})")
    
    elif args.action == 'path':
        if not args.node or not args.target:
            print("❌ --node and --target required for path finding")
            return 1
        
        path = graph.find_path(args.node, args.target)
        if path:
            print(f"🛤️  Path from {args.node} to {args.target}:\n")
            for i, node_id in enumerate(path):
                node = graph.get_node(node_id)
                prefix = "└─" if i == len(path) - 1 else "├─"
                print(f"  {prefix} {node.name if node else node_id}")
        else:
            print(f"❌ No path found between {args.node} and {args.target}")
    
    elif args.action == 'query':
        if not args.node:
            print("❌ --node required for query")
            return 1
        
        nav = suggest_navigation(graph, args.node)
        if "error" in nav:
            print(f"❌ {nav['error']}")
            return 1
        
        print(f"📍 Navigation from: {nav['current']['name']}\n")
        
        if nav['related_docs']:
            print("  📄 Related docs:")
            for item in nav['related_docs'][:5]:
                print(f"     → {item['name']} ({item['relation']})")
        
        if nav['code_references']:
            print("  💻 Code references:")
            for item in nav['code_references'][:5]:
                print(f"     → {item['name']}")
        
        if nav['examples']:
            print("  📝 Examples:")
            for item in nav['examples'][:3]:
                print(f"     → {item['name']}")
    
    elif args.action == 'mermaid':
        mermaid = graph.to_mermaid()
        print(mermaid)
    
    return 0


def cmd_coverage(args):
    """Analyze documentation coverage."""
    from .coverage import CoverageAnalyzer, CoverageFormatter
    
    project_root = Path(args.path).resolve()
    config = load_config(project_root)
    
    analyzer = CoverageAnalyzer(project_root, config)
    
    if args.trend:
        trend = analyzer.get_trend(30)
        if not trend:
            print("No coverage history yet. Run `living-docs coverage` to start tracking.")
            return 0
        
        sparkline = CoverageFormatter.to_trend_sparkline(trend)
        print(f"📈 Coverage trend (last {len(trend)} checks): {sparkline}")
        
        # Show first and last
        if len(trend) >= 2:
            delta = trend[-1]['percent'] - trend[0]['percent']
            direction = "↑" if delta > 0 else "↓" if delta < 0 else "→"
            print(f"   {trend[0]['percent']:.1f}% → {trend[-1]['percent']:.1f}% ({direction} {abs(delta):.1f}%)")
        return 0
    
    print("📊 Analyzing documentation coverage...")
    report = analyzer.analyze()
    
    # Format output
    if args.format == 'json':
        output = report.to_json()
    elif args.format == 'markdown':
        output = CoverageFormatter.to_markdown(report)
    elif args.format == 'ascii':
        output = CoverageFormatter.to_ascii_treemap(report)
    elif args.format == 'html':
        output = CoverageFormatter.to_html_treemap(report)
    elif args.format == 'badge':
        output = CoverageFormatter.to_badge_url(report)
    else:
        output = CoverageFormatter.to_ascii_treemap(report)
    
    # Write or print
    if args.output:
        Path(args.output).write_text(output)
        print(f"✓ Written to {args.output}")
    else:
        print(output)
    
    # Check threshold
    if args.min and report.overall_percent < args.min:
        print(f"\n❌ Coverage {report.overall_percent:.1f}% is below minimum {args.min}%")
        return 1
    
    return 0


def cmd_examples(args):
    """Validate code examples in documentation."""
    from .examples import ExamplesValidator, validate_examples
    
    project_root = Path(args.path).resolve()
    
    print("🧪 Validating code examples in documentation...")
    
    if args.file:
        # Validate single file
        from .examples import ExampleExtractor, PythonValidator
        extractor = ExampleExtractor(project_root)
        file_path = Path(args.file)
        if not file_path.is_absolute():
            file_path = project_root / file_path
        
        examples = extractor.extract_from_file(file_path)
        print(f"Found {len(examples)} examples in {args.file}\n")
        
        validator = PythonValidator(project_root)
        for ex in examples:
            if ex.language.value == "python":
                result = validator.validate(ex)
                status = "✓" if result.is_valid else "✗"
                print(f"{status} Line {ex.line_start}: {result.message}")
                if not result.is_valid:
                    for detail in result.details[:2]:
                        print(f"    {detail}")
        return 0
    
    # Full validation
    output = validate_examples(project_root, args.format)
    print(output)
    
    if args.fail_on_invalid:
        validator = ExamplesValidator(project_root)
        report = validator.validate_all()
        if report.invalid_count > 0:
            return 1
    
    return 0


# ============================================================
# Gen 9 Commands
# ============================================================

def cmd_auto_pr(args):
    """Create PRs for documentation fixes."""
    from .auto_pr import AutoPRCreator, PRConfig, DocFixCollector, DocFix, format_pr_results
    
    project_root = Path(args.path).resolve()
    
    # Configure PR creator
    config = PRConfig(
        group_by=args.group_by,
        draft=args.draft,
        reviewers=args.reviewers or [],
    )
    
    creator = AutoPRCreator(config, project_root)
    collector = DocFixCollector(project_root)
    
    # Collect fixes from various sources
    fixes = []
    
    if args.source in ('stale', 'all'):
        print("🔍 Checking for stale documentation...")
        calc = StalenessCalculator(project_root)
        stale_docs = calc.analyze_all()
        for doc in stale_docs:
            if doc.get('score', 0) > 0.5:
                path = doc.get('path', doc.get('doc', ''))
                if path:
                    full_path = project_root / path
                    if full_path.exists():
                        fixes.append(DocFix(
                            file_path=path,
                            original_content=full_path.read_text() if full_path.exists() else "",
                            fixed_content=full_path.read_text() if full_path.exists() else "",
                            fix_type="stale",
                            description=f"Documentation outdated (staleness: {doc.get('score', 0):.0%})",
                            severity="high" if doc.get('score', 0) > 0.7 else "medium",
                            related_code=doc.get('code'),
                        ))
        print(f"   Found {len([f for f in fixes if f.fix_type == 'stale'])} stale docs")
    
    if args.source in ('coverage', 'all'):
        print("🔍 Checking for missing documentation...")
        try:
            from .coverage import CoverageAnalyzer
            analyzer = CoverageAnalyzer(project_root)
            report = analyzer.analyze()
            for gap in report.get('undocumented', [])[:5]:  # Limit to 5
                fixes.append(DocFix(
                    file_path=f"docs/{Path(gap).stem}.md",
                    original_content="",
                    fixed_content=f"# {Path(gap).stem}\n\nTODO: Document {gap}\n",
                    fix_type="missing",
                    description=f"Missing documentation for {gap}",
                    severity="medium",
                    related_code=gap,
                ))
            print(f"   Found {len([f for f in fixes if f.fix_type == 'missing'])} missing docs")
        except Exception as e:
            print(f"   Coverage check failed: {e}")
    
    if not fixes:
        print("\n✅ No documentation fixes needed!")
        return 0
    
    print(f"\n📋 Total fixes to create PRs for: {len(fixes)}")
    
    # Create PRs
    results = creator.create_prs(
        fixes,
        dry_run=args.dry_run,
        interactive=args.interactive
    )
    
    # Output results
    output = format_pr_results(results, args.format)
    print(output)
    
    return 0


def cmd_from_tests(args):
    """Generate documentation examples from test files."""
    from .test_to_example import (
        TestExtractor, ExampleGenerator, ExampleFormatter,
        ExampleQuality, format_examples_report
    )
    
    project_root = Path(args.path).resolve()
    
    print("🧪 Test-to-Example Generator (Gen 9)\n")
    
    # Extract tests
    extractor = TestExtractor(project_root)
    
    if args.files:
        test_files = [project_root / f for f in args.files]
    else:
        test_files = extractor.find_test_files()
    
    print(f"📁 Found {len(test_files)} test files")
    
    all_tests = []
    for tf in test_files:
        tests = extractor.extract_from_file(tf)
        all_tests.extend(tests)
    
    print(f"🔬 Extracted {len(all_tests)} test cases")
    
    # Filter by tags if specified
    if args.tags:
        all_tests = [t for t in all_tests if any(tag in t.tags for tag in args.tags)]
        print(f"🏷️  After tag filter: {len(all_tests)} tests")
    
    # Generate examples
    generator = ExampleGenerator(project_root=project_root)
    
    quality_map = {
        'excellent': ExampleQuality.EXCELLENT,
        'good': ExampleQuality.GOOD,
        'fair': ExampleQuality.FAIR,
        'poor': ExampleQuality.POOR,
    }
    min_quality = quality_map.get(args.min_quality, ExampleQuality.FAIR)
    
    examples = generator.generate_batch(
        all_tests,
        use_ai=args.use_ai,
        min_quality=min_quality,
        max_complexity=args.max_complexity
    )
    
    print(f"✨ Generated {len(examples)} examples\n")
    
    # Format output
    if args.format == 'json':
        import json
        output = json.dumps([ExampleFormatter.to_json(e) for e in examples], indent=2)
    elif args.format == 'rst':
        output = "\n\n".join(ExampleFormatter.to_rst(e) for e in examples)
    else:  # markdown
        output = "\n\n".join(ExampleFormatter.to_markdown(e, include_source=True) for e in examples)
    
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output)
        print(f"📝 Written to {output_path}")
    else:
        print(output)
    
    # Also print summary
    print("\n" + format_examples_report(examples, "human"))
    
    return 0


def cmd_explore(args):
    """Interactive documentation explorer."""
    from .explorer import DocTreeBuilder, TerminalExplorer, SearchEngine, format_tree_ascii
    
    project_root = Path(args.path).resolve()
    
    print("📚 Documentation Explorer (Gen 9)\n")
    
    # Build tree
    builder = DocTreeBuilder(project_root)
    tree = builder.build(include_sections=True)
    
    node_count = len(tree.flatten())
    print(f"📊 Indexed {node_count} documentation nodes")
    
    if args.tree_only:
        # Just print tree
        if args.format == 'json':
            def node_to_dict(n):
                return {
                    'name': n.name,
                    'type': n.node_type.value,
                    'path': n.path,
                    'staleness': n.staleness_score,
                    'children': [node_to_dict(c) for c in n.children]
                }
            import json
            print(json.dumps(node_to_dict(tree), indent=2))
        else:
            print(format_tree_ascii(tree))
        return 0
    
    if args.search:
        # Non-interactive search
        engine = SearchEngine(tree)
        results = engine.search(args.search)
        
        print(f"\n🔍 Search results for '{args.search}':\n")
        for r in results[:10]:
            print(f"📍 {r['path']}:{r['line']}")
            highlighted = engine.highlight(r['match'], args.search)
            print(f"   {highlighted}")
            print()
        
        return 0
    
    # Full interactive mode
    explorer = TerminalExplorer(tree)
    
    if args.simple:
        explorer.run_simple()
    else:
        explorer.run()
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog='living-docs',
        description='Living Documentation - Docs that evolve with your code'
    )
    parser.add_argument('--path', '-p', default='.', help='Project root path')
    
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # init
    init_parser = subparsers.add_parser('init', help='Initialize Living Docs')
    init_parser.add_argument('--force', '-f', action='store_true', help='Overwrite existing config')
    
    # health
    subparsers.add_parser('health', help='Show documentation health report')
    
    # stale
    subparsers.add_parser('stale', help='List stale documentation')
    
    # generate
    gen_parser = subparsers.add_parser('generate', help='Generate missing documentation')
    gen_parser.add_argument('--dry-run', '-n', action='store_true', help='Show what would be created')
    
    # sync
    sync_parser = subparsers.add_parser('sync', help='Sync all documentation')
    sync_parser.add_argument('--dry-run', '-n', action='store_true', help='Show what would change')
    sync_parser.add_argument('--yes', '-y', action='store_true', help='Apply all changes without prompting')
    
    # watch
    watch_parser = subparsers.add_parser('watch', help='Start file watcher daemon')
    watch_parser.add_argument('--foreground', '-f', action='store_true', help='Run in foreground')
    
    # stop
    subparsers.add_parser('stop', help='Stop file watcher daemon')
    
    # status
    subparsers.add_parser('status', help='Show daemon status')
    
    # improve (Gen 6)
    improve_parser = subparsers.add_parser('improve', help='AI-powered documentation improvement')
    improve_parser.add_argument('file', nargs='?', help='Specific doc file to improve')
    improve_parser.add_argument('--analyze-only', '-a', action='store_true', help='Only analyze, don\'t generate improvements')
    improve_parser.add_argument('--dry-run', '-n', action='store_true', help='Preview improvements without writing')
    improve_parser.add_argument('--inplace', '-i', action='store_true', help='Update file in place')
    improve_parser.add_argument('--with-context', '-c', action='store_true', help='Include related code context')
    
    # ci (Gen 6)
    ci_parser = subparsers.add_parser('ci', help='Run CI/CD documentation check')
    ci_parser.add_argument('--format', '-f', choices=['human', 'github', 'gitlab', 'markdown', 'json'], default='human')
    ci_parser.add_argument('--fail-on-critical', action='store_true', help='Exit 1 if critical issues found')
    ci_parser.add_argument('--strict', action='store_true', help='Exit 1 on any warning')
    
    # related (Gen 6)
    related_parser = subparsers.add_parser('related', help='Find semantically related docs/code')
    related_parser.add_argument('file', nargs='?', help='Code file to find related docs for')
    related_parser.add_argument('--top', '-t', type=int, default=5, help='Number of results')
    related_parser.add_argument('--threshold', type=float, default=0.4, help='Minimum similarity score')
    
    # setup-ci (Gen 6)
    setup_ci_parser = subparsers.add_parser('setup-ci', help='Generate CI/CD configuration')
    setup_ci_parser.add_argument('--provider', choices=['github', 'gitlab', 'pre-commit', 'all'], default='github')
    
    # diff (Gen 7)
    diff_parser = subparsers.add_parser('diff', help='Analyze git diff for doc impact')
    diff_parser.add_argument('--staged', '-s', action='store_true', help='Analyze staged changes')
    diff_parser.add_argument('--base', '-b', default='HEAD', help='Base ref (default: HEAD)')
    diff_parser.add_argument('--target', '-t', help='Target ref (for comparing branches)')
    diff_parser.add_argument('--format', '-f', choices=['human', 'markdown', 'json', 'github'], default='human')
    
    # pr-check (Gen 7)
    pr_parser = subparsers.add_parser('pr-check', help='Check PR for documentation impact')
    pr_parser.add_argument('--base', '-b', default='main', help='Base branch (default: main)')
    pr_parser.add_argument('--format', '-f', choices=['human', 'markdown', 'json', 'github'], default='markdown')
    pr_parser.add_argument('--fail-on-critical', action='store_true', help='Exit 1 if critical updates needed')
    
    # graph (Gen 8)
    graph_parser = subparsers.add_parser('graph', help='Build/query documentation knowledge graph')
    graph_parser.add_argument('action', nargs='?', default='build', 
                              choices=['build', 'query', 'orphans', 'hubs', 'path', 'mermaid'],
                              help='Graph action')
    graph_parser.add_argument('--node', '-n', help='Node ID for query/path')
    graph_parser.add_argument('--target', '-t', help='Target node for path finding')
    graph_parser.add_argument('--depth', '-d', type=int, default=2, help='Traversal depth')
    graph_parser.add_argument('--top', type=int, default=10, help='Number of results')
    
    # coverage (Gen 8)
    coverage_parser = subparsers.add_parser('coverage', help='Documentation coverage analysis')
    coverage_parser.add_argument('--format', '-f', 
                                 choices=['text', 'json', 'markdown', 'ascii', 'html', 'badge'],
                                 default='ascii', help='Output format')
    coverage_parser.add_argument('--output', '-o', help='Write output to file')
    coverage_parser.add_argument('--trend', action='store_true', help='Show coverage trend')
    coverage_parser.add_argument('--min', type=float, help='Fail if coverage below threshold')
    
    # examples (Gen 8)
    examples_parser = subparsers.add_parser('examples', help='Validate code examples in docs')
    examples_parser.add_argument('--format', '-f', choices=['text', 'json'], default='text')
    examples_parser.add_argument('--fail-on-invalid', action='store_true', help='Exit 1 if invalid examples')
    examples_parser.add_argument('--file', help='Check specific doc file')
    
    # auto-pr (Gen 9)
    auto_pr_parser = subparsers.add_parser('auto-pr', help='Create PRs for documentation fixes')
    auto_pr_parser.add_argument('--dry-run', '-n', action='store_true', help='Preview without creating PRs')
    auto_pr_parser.add_argument('--interactive', '-i', action='store_true', help='Confirm each PR')
    auto_pr_parser.add_argument('--source', '-s', choices=['stale', 'ai', 'examples', 'coverage', 'all'], 
                                default='all', help='Source of fixes')
    auto_pr_parser.add_argument('--group-by', '-g', choices=['severity', 'type', 'directory', 'single'],
                                default='severity', help='How to group fixes into PRs')
    auto_pr_parser.add_argument('--draft', action='store_true', default=True, help='Create as draft PRs')
    auto_pr_parser.add_argument('--reviewers', '-r', nargs='+', help='Add reviewers to PRs')
    auto_pr_parser.add_argument('--format', '-f', choices=['human', 'json', 'markdown'], default='human')
    
    # from-tests (Gen 9)
    from_tests_parser = subparsers.add_parser('from-tests', help='Generate documentation examples from test files')
    from_tests_parser.add_argument('files', nargs='*', help='Specific test files (default: all)')
    from_tests_parser.add_argument('--output', '-o', help='Output file for generated examples')
    from_tests_parser.add_argument('--format', '-f', choices=['markdown', 'json', 'rst'], default='markdown')
    from_tests_parser.add_argument('--use-ai', action='store_true', help='Use AI to improve examples')
    from_tests_parser.add_argument('--min-quality', choices=['excellent', 'good', 'fair', 'poor'],
                                   default='fair', help='Minimum example quality to include')
    from_tests_parser.add_argument('--max-complexity', type=int, default=7, help='Max test complexity (1-10)')
    from_tests_parser.add_argument('--tags', nargs='+', help='Filter by tags (api, edge_case, etc.)')
    
    # explore (Gen 9)
    explore_parser = subparsers.add_parser('explore', help='Interactive documentation explorer')
    explore_parser.add_argument('--simple', '-s', action='store_true', help='Use simple mode (no TUI)')
    explore_parser.add_argument('--tree-only', '-t', action='store_true', help='Just print tree and exit')
    explore_parser.add_argument('--search', '-q', help='Search query (non-interactive)')
    explore_parser.add_argument('--format', '-f', choices=['ascii', 'json'], default='ascii')
    
    args = parser.parse_args()
    
    commands = {
        'init': cmd_init,
        'health': cmd_health,
        'stale': cmd_stale,
        'generate': cmd_generate,
        'sync': cmd_sync,
        'watch': cmd_watch,
        'stop': cmd_stop,
        'status': cmd_status,
        'improve': cmd_improve,
        'ci': cmd_ci,
        'related': cmd_related,
        'setup-ci': cmd_setup_ci,
        'diff': cmd_diff,
        'pr-check': cmd_pr_check,
        'graph': cmd_graph,
        'coverage': cmd_coverage,
        'examples': cmd_examples,
        # Gen 9
        'auto-pr': cmd_auto_pr,
        'from-tests': cmd_from_tests,
        'explore': cmd_explore,
    }
    
    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
