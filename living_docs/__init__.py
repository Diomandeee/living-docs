"""Living Documentation - Docs that evolve with your code.

Gen 8 Evolution:
- Knowledge Graph: Map relationships between docs, code, concepts
- Coverage Visualization: Visual reports of documentation coverage
- Runnable Examples: Validate code examples in documentation
"""

__version__ = "0.8.0"

from .parser import get_parser, DocItem
from .staleness import StalenessCalculator, StalenessReport
from .sync import SyncEngine, SyncAction
from .graph import DocGraph, GraphBuilder, Node, Edge, EdgeType, NodeType
from .coverage import CoverageAnalyzer, CoverageReport, CoverageFormatter
from .examples import ExamplesValidator, ExampleExtractor, CodeExample

__all__ = [
    # Core
    "get_parser", "DocItem",
    "StalenessCalculator", "StalenessReport",
    "SyncEngine", "SyncAction",
    # Gen 8
    "DocGraph", "GraphBuilder", "Node", "Edge", "EdgeType", "NodeType",
    "CoverageAnalyzer", "CoverageReport", "CoverageFormatter",
    "ExamplesValidator", "ExampleExtractor", "CodeExample",
]
