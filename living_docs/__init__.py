"""Living Documentation - Docs that evolve with your code.

Gen 9 Evolution:
- Auto-PR Creation: Automatically create PRs for documentation fixes
- Test-to-Example: Generate documentation examples from test files
- Interactive Explorer: Terminal-based browsable documentation
"""

__version__ = "0.9.0"

from .parser import get_parser, DocItem
from .staleness import StalenessCalculator, StalenessReport
from .sync import SyncEngine, SyncAction
from .graph import DocGraph, GraphBuilder, Node, Edge, EdgeType, NodeType
from .coverage import CoverageAnalyzer, CoverageReport, CoverageFormatter
from .examples import ExamplesValidator, ExampleExtractor, CodeExample
# Gen 9
from .auto_pr import AutoPRCreator, PRConfig, DocFix, PRProvider
from .test_to_example import TestExtractor, ExampleGenerator, GeneratedExample, ExampleQuality
from .explorer import DocTreeBuilder, TerminalExplorer, SearchEngine, DocNode

__all__ = [
    # Core
    "get_parser", "DocItem",
    "StalenessCalculator", "StalenessReport",
    "SyncEngine", "SyncAction",
    # Gen 8
    "DocGraph", "GraphBuilder", "Node", "Edge", "EdgeType", "NodeType",
    "CoverageAnalyzer", "CoverageReport", "CoverageFormatter",
    "ExamplesValidator", "ExampleExtractor", "CodeExample",
    # Gen 9
    "AutoPRCreator", "PRConfig", "DocFix", "PRProvider",
    "TestExtractor", "ExampleGenerator", "GeneratedExample", "ExampleQuality",
    "DocTreeBuilder", "TerminalExplorer", "SearchEngine", "DocNode",
]
