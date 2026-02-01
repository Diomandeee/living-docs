#!/usr/bin/env python3
"""Documentation Knowledge Graph — Gen 8 Feature

Builds a graph of relationships between documentation concepts,
code entities, and cross-references. Enables:
- Finding related docs via graph traversal
- Detecting orphaned documentation
- Understanding documentation topology
- Smart navigation suggestions
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Iterator
import hashlib


class EdgeType(Enum):
    """Types of relationships in the doc graph."""
    REFERENCES = "references"       # Doc A mentions Doc B
    IMPLEMENTS = "implements"       # Doc describes code
    DEPENDS_ON = "depends_on"       # Code depends on other code
    EXTENDS = "extends"            # Subclass/inheritance
    EXAMPLE_OF = "example_of"      # Example demonstrates concept
    RELATED = "related"            # Semantic similarity
    NEXT = "next"                  # Sequential reading order
    PARENT = "parent"              # Hierarchical containment
    CROSS_REFERENCE = "cross_reference"  # Explicit [link]() or [[wikilink]]


class NodeType(Enum):
    """Types of nodes in the graph."""
    DOC = "doc"          # Documentation file
    SECTION = "section"  # Doc section (heading)
    CODE = "code"        # Code file
    FUNCTION = "function"
    CLASS = "class"
    CONCEPT = "concept"  # Abstract concept/topic
    EXAMPLE = "example"  # Code example block


@dataclass
class Node:
    """A node in the documentation graph."""
    id: str
    node_type: NodeType
    name: str
    path: Optional[str] = None
    line_start: int = 0
    line_end: int = 0
    content_hash: str = ""
    metadata: dict = field(default_factory=dict)
    
    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other):
        return isinstance(other, Node) and self.id == other.id


@dataclass
class Edge:
    """A directed edge in the documentation graph."""
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = 1.0
    metadata: dict = field(default_factory=dict)
    
    def __hash__(self):
        return hash((self.source_id, self.target_id, self.edge_type))


class DocGraph:
    """Knowledge graph of documentation relationships."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self._adjacency: dict[str, list[Edge]] = defaultdict(list)
        self._reverse_adjacency: dict[str, list[Edge]] = defaultdict(list)
        
        # Storage
        self.cache_dir = project_root / ".living-docs" / "graph"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def add_node(self, node: Node) -> None:
        """Add a node to the graph."""
        self.nodes[node.id] = node
    
    def add_edge(self, edge: Edge) -> None:
        """Add an edge to the graph."""
        self.edges.append(edge)
        self._adjacency[edge.source_id].append(edge)
        self._reverse_adjacency[edge.target_id].append(edge)
    
    def get_node(self, node_id: str) -> Optional[Node]:
        """Get a node by ID."""
        return self.nodes.get(node_id)
    
    def get_neighbors(
        self,
        node_id: str,
        edge_types: Optional[list[EdgeType]] = None,
        direction: str = "outgoing"
    ) -> list[tuple[Node, Edge]]:
        """Get neighboring nodes with their connecting edges."""
        adjacency = self._adjacency if direction == "outgoing" else self._reverse_adjacency
        
        results = []
        for edge in adjacency.get(node_id, []):
            if edge_types and edge.edge_type not in edge_types:
                continue
            
            target_id = edge.target_id if direction == "outgoing" else edge.source_id
            node = self.nodes.get(target_id)
            if node:
                results.append((node, edge))
        
        return results
    
    def find_path(
        self,
        start_id: str,
        end_id: str,
        max_depth: int = 5
    ) -> Optional[list[str]]:
        """Find shortest path between two nodes using BFS."""
        if start_id not in self.nodes or end_id not in self.nodes:
            return None
        
        if start_id == end_id:
            return [start_id]
        
        visited = {start_id}
        queue = [(start_id, [start_id])]
        
        while queue:
            current, path = queue.pop(0)
            
            if len(path) > max_depth:
                continue
            
            for node, _ in self.get_neighbors(current):
                if node.id == end_id:
                    return path + [end_id]
                
                if node.id not in visited:
                    visited.add(node.id)
                    queue.append((node.id, path + [node.id]))
        
        return None
    
    def get_orphans(self) -> list[Node]:
        """Find documentation nodes with no connections."""
        connected = set()
        
        for edge in self.edges:
            connected.add(edge.source_id)
            connected.add(edge.target_id)
        
        return [
            node for node_id, node in self.nodes.items()
            if node_id not in connected and node.node_type == NodeType.DOC
        ]
    
    def get_hubs(self, top_n: int = 10) -> list[tuple[Node, int]]:
        """Find highly connected nodes (hubs)."""
        connection_counts = defaultdict(int)
        
        for edge in self.edges:
            connection_counts[edge.source_id] += 1
            connection_counts[edge.target_id] += 1
        
        sorted_nodes = sorted(
            connection_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return [
            (self.nodes[node_id], count)
            for node_id, count in sorted_nodes[:top_n]
            if node_id in self.nodes
        ]
    
    def get_subgraph(
        self,
        center_id: str,
        depth: int = 2,
        edge_types: Optional[list[EdgeType]] = None
    ) -> "DocGraph":
        """Extract a subgraph around a node."""
        subgraph = DocGraph(self.project_root)
        
        if center_id not in self.nodes:
            return subgraph
        
        visited = set()
        queue = [(center_id, 0)]
        
        while queue:
            node_id, current_depth = queue.pop(0)
            
            if node_id in visited or current_depth > depth:
                continue
            
            visited.add(node_id)
            
            if node := self.nodes.get(node_id):
                subgraph.add_node(node)
            
            for neighbor, edge in self.get_neighbors(node_id, edge_types, "outgoing"):
                if current_depth < depth:
                    subgraph.add_edge(edge)
                    queue.append((neighbor.id, current_depth + 1))
            
            for neighbor, edge in self.get_neighbors(node_id, edge_types, "incoming"):
                if current_depth < depth:
                    subgraph.add_edge(edge)
                    queue.append((neighbor.id, current_depth + 1))
        
        return subgraph
    
    def to_dict(self) -> dict:
        """Serialize graph to dictionary."""
        return {
            "nodes": [
                {
                    "id": n.id,
                    "type": n.node_type.value,
                    "name": n.name,
                    "path": n.path,
                    "line_start": n.line_start,
                    "line_end": n.line_end,
                    "content_hash": n.content_hash,
                    "metadata": n.metadata
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {
                    "source": e.source_id,
                    "target": e.target_id,
                    "type": e.edge_type.value,
                    "weight": e.weight,
                    "metadata": e.metadata
                }
                for e in self.edges
            ]
        }
    
    @classmethod
    def from_dict(cls, data: dict, project_root: Path) -> "DocGraph":
        """Deserialize graph from dictionary."""
        graph = cls(project_root)
        
        for n in data.get("nodes", []):
            node = Node(
                id=n["id"],
                node_type=NodeType(n["type"]),
                name=n["name"],
                path=n.get("path"),
                line_start=n.get("line_start", 0),
                line_end=n.get("line_end", 0),
                content_hash=n.get("content_hash", ""),
                metadata=n.get("metadata", {})
            )
            graph.add_node(node)
        
        for e in data.get("edges", []):
            edge = Edge(
                source_id=e["source"],
                target_id=e["target"],
                edge_type=EdgeType(e["type"]),
                weight=e.get("weight", 1.0),
                metadata=e.get("metadata", {})
            )
            graph.add_edge(edge)
        
        return graph
    
    def save(self, filename: str = "graph.json") -> Path:
        """Save graph to file."""
        path = self.cache_dir / filename
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        return path
    
    def load(self, filename: str = "graph.json") -> bool:
        """Load graph from file."""
        path = self.cache_dir / filename
        if not path.exists():
            return False
        
        with open(path) as f:
            data = json.load(f)
        
        loaded = DocGraph.from_dict(data, self.project_root)
        self.nodes = loaded.nodes
        self.edges = loaded.edges
        self._adjacency = loaded._adjacency
        self._reverse_adjacency = loaded._reverse_adjacency
        return True
    
    def to_mermaid(self, max_nodes: int = 50) -> str:
        """Generate Mermaid diagram of the graph."""
        lines = ["graph LR"]
        
        # Limit nodes for readability
        shown_nodes = list(self.nodes.values())[:max_nodes]
        shown_ids = {n.id for n in shown_nodes}
        
        # Node styles by type
        type_styles = {
            NodeType.DOC: "([%s])",       # Stadium
            NodeType.CODE: "[%s]",        # Rectangle
            NodeType.FUNCTION: "{{%s}}", # Hexagon
            NodeType.CLASS: "[/%s/]",    # Parallelogram
            NodeType.CONCEPT: "((%s))",   # Circle
            NodeType.EXAMPLE: ">%s]",    # Asymmetric
            NodeType.SECTION: "[%s]",
        }
        
        # Add nodes
        for node in shown_nodes:
            style = type_styles.get(node.node_type, "[%s]")
            safe_name = node.name.replace('"', "'")[:30]
            lines.append(f"    {node.id}{style % safe_name}")
        
        # Edge styles by type
        edge_arrows = {
            EdgeType.REFERENCES: "-->",
            EdgeType.IMPLEMENTS: "-.->",
            EdgeType.DEPENDS_ON: "==>",
            EdgeType.EXTENDS: "-->>",
            EdgeType.EXAMPLE_OF: "-.->",
            EdgeType.RELATED: "-.-",
            EdgeType.CROSS_REFERENCE: "-->",
        }
        
        # Add edges between shown nodes
        for edge in self.edges:
            if edge.source_id in shown_ids and edge.target_id in shown_ids:
                arrow = edge_arrows.get(edge.edge_type, "-->")
                lines.append(f"    {edge.source_id} {arrow} {edge.target_id}")
        
        return "\n".join(lines)


class GraphBuilder:
    """Builds the documentation graph from project files."""
    
    # Patterns for detecting cross-references
    MARKDOWN_LINK = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    WIKILINK = re.compile(r'\[\[([^\]]+)\]\]')
    CODE_REF = re.compile(r'`([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)`')
    HEADING = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    CODE_BLOCK = re.compile(r'```(\w*)\n(.*?)```', re.DOTALL)
    
    def __init__(self, project_root: Path, config: Optional[dict] = None):
        self.project_root = project_root
        self.config = config or {}
        self.graph = DocGraph(project_root)
    
    def build(self) -> DocGraph:
        """Build the complete documentation graph."""
        # 1. Add doc nodes
        self._add_doc_nodes()
        
        # 2. Add code nodes
        self._add_code_nodes()
        
        # 3. Extract cross-references
        self._extract_references()
        
        # 4. Link docs to code via naming conventions
        self._link_docs_to_code()
        
        # 5. Save the graph
        self.graph.save()
        
        return self.graph
    
    def _add_doc_nodes(self) -> None:
        """Add documentation files as nodes."""
        doc_patterns = self.config.get("docs", ["docs", "*.md", "README.md"])
        
        for pattern in doc_patterns:
            for path in self.project_root.glob(f"**/{pattern}"):
                if path.is_file() and path.suffix in (".md", ".mdx", ".rst", ".txt"):
                    self._add_doc_file(path)
    
    def _add_doc_file(self, path: Path) -> None:
        """Add a doc file and its sections as nodes."""
        rel_path = path.relative_to(self.project_root)
        content = path.read_text(errors="ignore")
        
        # File node
        file_id = f"doc:{rel_path}"
        self.graph.add_node(Node(
            id=file_id,
            node_type=NodeType.DOC,
            name=path.stem,
            path=str(rel_path),
            content_hash=hashlib.md5(content.encode()).hexdigest()[:8]
        ))
        
        # Section nodes from headings
        for match in self.HEADING.finditer(content):
            level = len(match.group(1))
            title = match.group(2).strip()
            
            section_id = f"section:{rel_path}#{title.lower().replace(' ', '-')}"
            self.graph.add_node(Node(
                id=section_id,
                node_type=NodeType.SECTION,
                name=title,
                path=str(rel_path),
                line_start=content[:match.start()].count('\n') + 1,
                metadata={"level": level}
            ))
            
            # Link section to parent doc
            self.graph.add_edge(Edge(
                source_id=file_id,
                target_id=section_id,
                edge_type=EdgeType.PARENT
            ))
        
        # Example nodes from code blocks
        for i, match in enumerate(self.CODE_BLOCK.finditer(content)):
            lang = match.group(1) or "unknown"
            code = match.group(2).strip()
            
            if len(code) > 20:  # Skip trivial examples
                example_id = f"example:{rel_path}:{i}"
                self.graph.add_node(Node(
                    id=example_id,
                    node_type=NodeType.EXAMPLE,
                    name=f"Example {i+1} ({lang})",
                    path=str(rel_path),
                    line_start=content[:match.start()].count('\n') + 1,
                    metadata={"language": lang, "code": code[:500]}
                ))
                
                self.graph.add_edge(Edge(
                    source_id=file_id,
                    target_id=example_id,
                    edge_type=EdgeType.PARENT
                ))
    
    def _add_code_nodes(self) -> None:
        """Add code files and entities as nodes."""
        source_patterns = self.config.get("sources", ["**/*.py", "**/*.ts", "**/*.js"])
        
        for pattern in source_patterns:
            for path in self.project_root.glob(pattern):
                if path.is_file():
                    self._add_code_file(path)
    
    def _add_code_file(self, path: Path) -> None:
        """Add a code file and its entities as nodes."""
        rel_path = path.relative_to(self.project_root)
        
        try:
            content = path.read_text(errors="ignore")
        except Exception:
            return
        
        # File node
        file_id = f"code:{rel_path}"
        self.graph.add_node(Node(
            id=file_id,
            node_type=NodeType.CODE,
            name=path.stem,
            path=str(rel_path),
            content_hash=hashlib.md5(content.encode()).hexdigest()[:8]
        ))
        
        # Parse Python files for classes/functions
        if path.suffix == ".py":
            try:
                import ast
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        class_id = f"class:{rel_path}:{node.name}"
                        self.graph.add_node(Node(
                            id=class_id,
                            node_type=NodeType.CLASS,
                            name=node.name,
                            path=str(rel_path),
                            line_start=node.lineno,
                            line_end=node.end_lineno or node.lineno
                        ))
                        self.graph.add_edge(Edge(
                            source_id=file_id,
                            target_id=class_id,
                            edge_type=EdgeType.PARENT
                        ))
                    
                    elif isinstance(node, ast.FunctionDef):
                        func_id = f"func:{rel_path}:{node.name}"
                        self.graph.add_node(Node(
                            id=func_id,
                            node_type=NodeType.FUNCTION,
                            name=node.name,
                            path=str(rel_path),
                            line_start=node.lineno,
                            line_end=node.end_lineno or node.lineno
                        ))
                        self.graph.add_edge(Edge(
                            source_id=file_id,
                            target_id=func_id,
                            edge_type=EdgeType.PARENT
                        ))
            except SyntaxError:
                pass
    
    def _extract_references(self) -> None:
        """Extract cross-references from documentation."""
        for node in list(self.graph.nodes.values()):
            if node.node_type != NodeType.DOC or not node.path:
                continue
            
            path = self.project_root / node.path
            if not path.exists():
                continue
            
            content = path.read_text(errors="ignore")
            
            # Markdown links [text](url)
            for match in self.MARKDOWN_LINK.finditer(content):
                target_path = match.group(2)
                if not target_path.startswith(('http://', 'https://', '#')):
                    target_id = f"doc:{target_path}"
                    if target_id in self.graph.nodes:
                        self.graph.add_edge(Edge(
                            source_id=node.id,
                            target_id=target_id,
                            edge_type=EdgeType.CROSS_REFERENCE
                        ))
            
            # Code references `function_name` or `module.function`
            for match in self.CODE_REF.finditer(content):
                ref = match.group(1)
                
                # Try to find matching code node
                for code_node in self.graph.nodes.values():
                    if code_node.node_type in (NodeType.FUNCTION, NodeType.CLASS):
                        if code_node.name == ref or code_node.name == ref.split('.')[-1]:
                            self.graph.add_edge(Edge(
                                source_id=node.id,
                                target_id=code_node.id,
                                edge_type=EdgeType.REFERENCES
                            ))
    
    def _link_docs_to_code(self) -> None:
        """Link docs to code via naming conventions and path patterns."""
        # Common patterns: docs/api.md → src/api.py
        mappings = self.config.get("mappings", [
            {"docs": "docs/*.md", "code": "src/*.py"},
            {"docs": "docs/*.md", "code": "lib/*.py"},
            {"docs": "docs/api/*.md", "code": "src/api/*.py"},
        ])
        
        # Simple name matching fallback
        doc_nodes = [n for n in self.graph.nodes.values() if n.node_type == NodeType.DOC]
        code_nodes = [n for n in self.graph.nodes.values() if n.node_type == NodeType.CODE]
        
        for doc in doc_nodes:
            doc_name = doc.name.lower().replace("-", "_").replace(" ", "_")
            
            for code in code_nodes:
                code_name = code.name.lower()
                
                # Exact match or prefix match
                if doc_name == code_name or doc_name.startswith(code_name):
                    self.graph.add_edge(Edge(
                        source_id=doc.id,
                        target_id=code.id,
                        edge_type=EdgeType.IMPLEMENTS,
                        weight=0.8
                    ))


def get_reading_order(graph: DocGraph, start_id: str) -> list[Node]:
    """Suggest optimal reading order from a starting point."""
    visited = []
    queue = [start_id]
    seen = set()
    
    while queue:
        node_id = queue.pop(0)
        if node_id in seen:
            continue
        seen.add(node_id)
        
        if node := graph.get_node(node_id):
            visited.append(node)
            
            # Follow NEXT edges first, then REFERENCES
            for neighbor, edge in graph.get_neighbors(node_id, [EdgeType.NEXT]):
                queue.insert(0, neighbor.id)
            
            for neighbor, edge in graph.get_neighbors(node_id, [EdgeType.REFERENCES]):
                queue.append(neighbor.id)
    
    return visited


def suggest_navigation(graph: DocGraph, current_id: str) -> dict:
    """Suggest where to navigate from current position."""
    current = graph.get_node(current_id)
    if not current:
        return {"error": "Node not found"}
    
    suggestions = {
        "current": {
            "id": current.id,
            "name": current.name,
            "type": current.node_type.value
        },
        "related_docs": [],
        "code_references": [],
        "examples": [],
        "next_reading": []
    }
    
    for neighbor, edge in graph.get_neighbors(current_id, direction="outgoing"):
        item = {"id": neighbor.id, "name": neighbor.name, "relation": edge.edge_type.value}
        
        if neighbor.node_type == NodeType.DOC:
            suggestions["related_docs"].append(item)
        elif neighbor.node_type in (NodeType.CODE, NodeType.FUNCTION, NodeType.CLASS):
            suggestions["code_references"].append(item)
        elif neighbor.node_type == NodeType.EXAMPLE:
            suggestions["examples"].append(item)
    
    # Suggest next reading based on graph structure
    hubs = graph.get_hubs(3)
    for hub, _ in hubs:
        if hub.id != current_id and hub.node_type == NodeType.DOC:
            suggestions["next_reading"].append({"id": hub.id, "name": hub.name})
    
    return suggestions
