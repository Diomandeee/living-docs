"""
Interactive Documentation Explorer (Gen 9)

A terminal-based browsable documentation interface.
Features:
- Tree navigation of documentation
- Full-text search with highlighting
- Preview pane with syntax highlighting
- Keyboard shortcuts for power users
- Integration with health/staleness data
"""

import os
import sys
import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple, Callable
from enum import Enum


class NodeType(Enum):
    """Types of nodes in the doc tree."""
    ROOT = "root"
    DIRECTORY = "directory"
    FILE = "file"
    SECTION = "section"
    CODE_BLOCK = "code_block"


@dataclass
class DocNode:
    """A node in the documentation tree."""
    name: str
    node_type: NodeType
    path: Optional[str] = None
    children: List['DocNode'] = field(default_factory=list)
    content: Optional[str] = None
    line_number: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Health indicators
    staleness_score: float = 0.0
    coverage_score: float = 1.0
    last_updated: Optional[str] = None
    
    def add_child(self, child: 'DocNode') -> None:
        """Add a child node."""
        self.children.append(child)
    
    def find_by_path(self, path: str) -> Optional['DocNode']:
        """Find a node by its path."""
        if self.path == path:
            return self
        for child in self.children:
            result = child.find_by_path(path)
            if result:
                return result
        return None
    
    def flatten(self) -> List['DocNode']:
        """Flatten tree to list."""
        result = [self]
        for child in self.children:
            result.extend(child.flatten())
        return result


class DocTreeBuilder:
    """Builds a navigable tree from documentation files."""
    
    DOC_EXTENSIONS = {".md", ".rst", ".txt", ".adoc"}
    
    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path.cwd()
    
    def _extract_sections(self, content: str, file_path: str) -> List[DocNode]:
        """Extract sections from markdown content."""
        sections = []
        lines = content.split("\n")
        current_content = []
        current_section = None
        
        for i, line in enumerate(lines):
            # Markdown headers
            if line.startswith("#"):
                if current_section:
                    current_section.content = "\n".join(current_content)
                    sections.append(current_section)
                
                level = len(line) - len(line.lstrip("#"))
                title = line.lstrip("#").strip()
                current_section = DocNode(
                    name=title,
                    node_type=NodeType.SECTION,
                    path=f"{file_path}#L{i+1}",
                    line_number=i + 1,
                    metadata={"level": level}
                )
                current_content = []
            else:
                current_content.append(line)
        
        if current_section:
            current_section.content = "\n".join(current_content)
            sections.append(current_section)
        
        return sections
    
    def _load_health_data(self) -> Dict[str, Dict]:
        """Load health data from .living-docs directory."""
        health_file = self.project_root / ".living-docs" / "health.json"
        if health_file.exists():
            try:
                return json.loads(health_file.read_text())
            except Exception:
                pass
        return {}
    
    def build(
        self,
        doc_paths: Optional[List[str]] = None,
        include_sections: bool = True,
        max_depth: int = 10
    ) -> DocNode:
        """Build the documentation tree."""
        root = DocNode(
            name=self.project_root.name,
            node_type=NodeType.ROOT,
            path=str(self.project_root)
        )
        
        health_data = self._load_health_data()
        
        # Find doc files
        if doc_paths:
            doc_files = []
            for p in doc_paths:
                path = Path(p)
                if path.is_dir():
                    doc_files.extend(path.rglob("*"))
                else:
                    doc_files.append(path)
        else:
            doc_files = []
            for ext in self.DOC_EXTENSIONS:
                doc_files.extend(self.project_root.rglob(f"*{ext}"))
        
        # Build tree structure
        dir_nodes: Dict[str, DocNode] = {str(self.project_root): root}
        
        for file_path in sorted(doc_files):
            if file_path.suffix not in self.DOC_EXTENSIONS:
                continue
            
            # Create parent directories
            parent = file_path.parent
            parents = []
            while parent != self.project_root and str(parent) not in dir_nodes:
                parents.append(parent)
                parent = parent.parent
            
            for p in reversed(parents):
                parent_node = dir_nodes.get(str(p.parent), root)
                dir_node = DocNode(
                    name=p.name,
                    node_type=NodeType.DIRECTORY,
                    path=str(p)
                )
                parent_node.add_child(dir_node)
                dir_nodes[str(p)] = dir_node
            
            # Create file node
            try:
                content = file_path.read_text()
            except Exception:
                content = ""
            
            rel_path = str(file_path.relative_to(self.project_root))
            file_health = health_data.get(rel_path, {})
            
            file_node = DocNode(
                name=file_path.name,
                node_type=NodeType.FILE,
                path=rel_path,
                content=content,
                staleness_score=file_health.get("staleness", 0.0),
                coverage_score=file_health.get("coverage", 1.0),
                last_updated=file_health.get("last_updated"),
            )
            
            # Add sections
            if include_sections and file_path.suffix in {".md", ".rst"}:
                sections = self._extract_sections(content, rel_path)
                for section in sections:
                    file_node.add_child(section)
            
            parent_node = dir_nodes.get(str(file_path.parent), root)
            parent_node.add_child(file_node)
        
        return root


class SearchEngine:
    """Full-text search with highlighting."""
    
    def __init__(self, tree: DocNode):
        self.tree = tree
        self._index: Dict[str, List[Tuple[DocNode, int]]] = {}
        self._build_index()
    
    def _build_index(self) -> None:
        """Build search index from tree."""
        for node in self.tree.flatten():
            if node.content:
                # Index words with positions
                words = re.findall(r'\w+', node.content.lower())
                for i, word in enumerate(words):
                    if word not in self._index:
                        self._index[word] = []
                    self._index[word].append((node, i))
    
    def search(
        self,
        query: str,
        max_results: int = 20,
        context_lines: int = 2
    ) -> List[Dict[str, Any]]:
        """Search documentation."""
        results = []
        query_words = query.lower().split()
        
        if not query_words:
            return results
        
        # Find nodes containing all query words
        matching_nodes: Dict[str, int] = {}
        
        for word in query_words:
            for node, pos in self._index.get(word, []):
                key = node.path or node.name
                matching_nodes[key] = matching_nodes.get(key, 0) + 1
        
        # Filter to nodes with all words
        relevant = [k for k, v in matching_nodes.items() if v >= len(query_words)]
        
        for path in relevant[:max_results]:
            node = self.tree.find_by_path(path)
            if not node:
                continue
            
            # Find matching lines with context
            if node.content:
                lines = node.content.split("\n")
                for i, line in enumerate(lines):
                    if all(w in line.lower() for w in query_words):
                        start = max(0, i - context_lines)
                        end = min(len(lines), i + context_lines + 1)
                        context = lines[start:end]
                        
                        results.append({
                            "node": node,
                            "path": path,
                            "line": i + 1,
                            "match": line,
                            "context": "\n".join(context),
                            "score": matching_nodes.get(path, 0),
                        })
        
        # Sort by score
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:max_results]
    
    def highlight(self, text: str, query: str) -> str:
        """Add ANSI highlighting to matches."""
        words = query.lower().split()
        result = text
        
        for word in words:
            # Case-insensitive replacement with highlighting
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            result = pattern.sub(lambda m: f"\033[1;33m{m.group()}\033[0m", result)
        
        return result


class TerminalExplorer:
    """Terminal-based interactive explorer."""
    
    def __init__(self, tree: DocNode):
        self.tree = tree
        self.search_engine = SearchEngine(tree)
        self.current_node = tree
        self.history: List[DocNode] = []
        self.view_mode = "tree"  # tree, preview, search
        self.search_results: List[Dict] = []
        self.selected_index = 0
        self.scroll_offset = 0
    
    def _clear_screen(self) -> None:
        """Clear terminal screen."""
        print("\033[2J\033[H", end="")
    
    def _get_terminal_size(self) -> Tuple[int, int]:
        """Get terminal dimensions."""
        try:
            import shutil
            size = shutil.get_terminal_size()
            return size.columns, size.lines
        except Exception:
            return 80, 24
    
    def _render_tree_node(self, node: DocNode, depth: int = 0, prefix: str = "") -> List[str]:
        """Render a tree node with box-drawing characters."""
        lines = []
        
        # Icon based on type
        icons = {
            NodeType.ROOT: "🏠",
            NodeType.DIRECTORY: "📁",
            NodeType.FILE: "📄",
            NodeType.SECTION: "📝",
        }
        
        # Health indicator
        health = ""
        if node.staleness_score > 0.7:
            health = " 🔴"
        elif node.staleness_score > 0.4:
            health = " 🟡"
        elif node.staleness_score > 0:
            health = " 🟢"
        
        icon = icons.get(node.node_type, "•")
        line = f"{prefix}{icon} {node.name}{health}"
        lines.append(line)
        
        # Render children
        for i, child in enumerate(node.children):
            is_last = i == len(node.children) - 1
            child_prefix = prefix + ("└── " if is_last else "├── ")
            continuation = prefix + ("    " if is_last else "│   ")
            
            child_lines = self._render_tree_node(child, depth + 1, "")
            if child_lines:
                lines.append(child_prefix + child_lines[0].lstrip())
                for cl in child_lines[1:]:
                    lines.append(continuation + cl.lstrip())
        
        return lines
    
    def _render_header(self, width: int) -> List[str]:
        """Render the header bar."""
        title = " Living Documentation Explorer "
        path = self.current_node.path or self.current_node.name
        
        header = [
            "═" * width,
            f"│{title.center(width - 2)}│",
            f"│ 📍 {path[:width-6].ljust(width - 6)} │",
            "═" * width,
        ]
        return header
    
    def _render_footer(self, width: int) -> List[str]:
        """Render the footer with keybindings."""
        keys = [
            "↑↓ Navigate",
            "Enter Open",
            "b Back",
            "/ Search",
            "h Health",
            "q Quit",
        ]
        footer_text = " │ ".join(keys)
        
        return [
            "─" * width,
            f" {footer_text[:width-2]} ",
        ]
    
    def _render_tree_view(self, width: int, height: int) -> List[str]:
        """Render the tree navigation view."""
        lines = []
        
        # Get all visible nodes
        tree_lines = self._render_tree_node(self.current_node)
        
        # Apply scroll and selection
        visible_lines = tree_lines[self.scroll_offset:self.scroll_offset + height]
        
        for i, line in enumerate(visible_lines):
            actual_idx = i + self.scroll_offset
            if actual_idx == self.selected_index:
                # Highlight selected
                line = f"\033[7m{line[:width].ljust(width)}\033[0m"
            else:
                line = line[:width].ljust(width)
            lines.append(line)
        
        # Pad to fill height
        while len(lines) < height:
            lines.append(" " * width)
        
        return lines
    
    def _render_preview_view(self, width: int, height: int) -> List[str]:
        """Render content preview."""
        lines = []
        
        if not self.current_node.content:
            lines.append("(No content to preview)")
            while len(lines) < height:
                lines.append(" " * width)
            return lines
        
        content_lines = self.current_node.content.split("\n")
        visible = content_lines[self.scroll_offset:self.scroll_offset + height]
        
        for line in visible:
            # Truncate long lines
            lines.append(line[:width].ljust(width))
        
        while len(lines) < height:
            lines.append(" " * width)
        
        return lines
    
    def _render_search_view(self, width: int, height: int) -> List[str]:
        """Render search results."""
        lines = []
        
        if not self.search_results:
            lines.append("No results found")
        else:
            lines.append(f"Found {len(self.search_results)} results:")
            lines.append("")
            
            for i, result in enumerate(self.search_results[:height - 2]):
                prefix = "→ " if i == self.selected_index else "  "
                line = f"{prefix}{result['path']}:{result['line']}"
                
                if i == self.selected_index:
                    line = f"\033[7m{line[:width].ljust(width)}\033[0m"
                else:
                    line = line[:width]
                
                lines.append(line)
        
        while len(lines) < height:
            lines.append(" " * width)
        
        return lines
    
    def render(self) -> None:
        """Render the current view."""
        width, height = self._get_terminal_size()
        
        self._clear_screen()
        
        # Header
        header = self._render_header(width)
        for line in header:
            print(line)
        
        # Content area (subtract header and footer)
        content_height = height - len(header) - 3
        
        if self.view_mode == "tree":
            content = self._render_tree_view(width, content_height)
        elif self.view_mode == "preview":
            content = self._render_preview_view(width, content_height)
        elif self.view_mode == "search":
            content = self._render_search_view(width, content_height)
        else:
            content = [" " * width] * content_height
        
        for line in content:
            print(line)
        
        # Footer
        footer = self._render_footer(width)
        for line in footer:
            print(line)
    
    def handle_input(self, key: str) -> bool:
        """Handle keyboard input. Returns False to quit."""
        if key == "q":
            return False
        
        elif key == "up" or key == "k":
            self.selected_index = max(0, self.selected_index - 1)
            # Adjust scroll
            if self.selected_index < self.scroll_offset:
                self.scroll_offset = self.selected_index
        
        elif key == "down" or key == "j":
            tree_lines = self._render_tree_node(self.current_node)
            max_idx = len(tree_lines) - 1
            self.selected_index = min(max_idx, self.selected_index + 1)
            # Adjust scroll
            _, height = self._get_terminal_size()
            visible_height = height - 7
            if self.selected_index >= self.scroll_offset + visible_height:
                self.scroll_offset = self.selected_index - visible_height + 1
        
        elif key == "enter":
            if self.view_mode == "tree":
                # Navigate into selected node
                nodes = self.current_node.flatten()
                if self.selected_index < len(nodes):
                    selected = nodes[self.selected_index]
                    if selected.children:
                        self.history.append(self.current_node)
                        self.current_node = selected
                        self.selected_index = 0
                        self.scroll_offset = 0
                    elif selected.content:
                        self.view_mode = "preview"
                        self.scroll_offset = 0
            
            elif self.view_mode == "search":
                if self.search_results and self.selected_index < len(self.search_results):
                    result = self.search_results[self.selected_index]
                    node = result["node"]
                    self.current_node = node
                    self.view_mode = "preview"
                    self.scroll_offset = max(0, result["line"] - 5)
        
        elif key == "b":
            if self.view_mode == "preview":
                self.view_mode = "tree"
            elif self.view_mode == "search":
                self.view_mode = "tree"
            elif self.history:
                self.current_node = self.history.pop()
                self.selected_index = 0
                self.scroll_offset = 0
        
        elif key == "/":
            # Enter search mode
            print("\033[2J\033[H", end="")  # Clear
            print("Search: ", end="", flush=True)
            query = input()
            if query:
                self.search_results = self.search_engine.search(query)
                self.view_mode = "search"
                self.selected_index = 0
        
        elif key == "h":
            # Show health summary
            self.view_mode = "health"
        
        elif key == "p":
            # Toggle preview
            if self.view_mode == "tree":
                if self.current_node.content:
                    self.view_mode = "preview"
            else:
                self.view_mode = "tree"
        
        return True
    
    def run_simple(self) -> None:
        """Run in simple mode (no curses)."""
        print("\n=== Living Documentation Explorer ===\n")
        print("(Simple mode - for full interactive mode, install 'blessed' or 'curses')\n")
        
        # Show tree
        tree_lines = self._render_tree_node(self.tree)
        for line in tree_lines[:30]:
            print(line)
        
        if len(tree_lines) > 30:
            print(f"\n... and {len(tree_lines) - 30} more nodes")
        
        print("\nCommands: /search <query>, open <path>, quit")
        
        while True:
            try:
                cmd = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            
            if cmd == "quit" or cmd == "q":
                break
            elif cmd.startswith("/"):
                query = cmd[1:].strip()
                results = self.search_engine.search(query)
                print(f"\nFound {len(results)} results:")
                for r in results[:10]:
                    print(f"  {r['path']}:{r['line']}")
                    print(f"    {r['match'][:60]}...")
            elif cmd.startswith("open "):
                path = cmd[5:].strip()
                node = self.tree.find_by_path(path)
                if node and node.content:
                    print(f"\n--- {path} ---")
                    print(node.content[:2000])
                    if len(node.content) > 2000:
                        print("\n... (truncated)")
                else:
                    print("Node not found or has no content")
            elif cmd == "tree":
                for line in tree_lines[:30]:
                    print(line)
    
    def run(self) -> None:
        """Run the interactive explorer."""
        try:
            import blessed
            term = blessed.Terminal()
            
            with term.fullscreen(), term.cbreak(), term.hidden_cursor():
                running = True
                while running:
                    self.render()
                    
                    key = term.inkey(timeout=0.1)
                    if key:
                        if key.name == "KEY_UP":
                            running = self.handle_input("up")
                        elif key.name == "KEY_DOWN":
                            running = self.handle_input("down")
                        elif key.name == "KEY_ENTER":
                            running = self.handle_input("enter")
                        elif key == "/":
                            # Search input
                            print(term.move_xy(0, term.height - 1) + "Search: ", end="", flush=True)
                            with term.location(8, term.height - 1):
                                query = ""
                                while True:
                                    ch = term.inkey()
                                    if ch.name == "KEY_ENTER":
                                        break
                                    elif ch.name == "KEY_ESCAPE":
                                        query = ""
                                        break
                                    elif ch.name == "KEY_BACKSPACE":
                                        query = query[:-1]
                                    elif ch.is_sequence:
                                        continue
                                    else:
                                        query += str(ch)
                                    print(term.move_xy(8, term.height - 1) + query + " ", end="", flush=True)
                                
                                if query:
                                    self.search_results = self.search_engine.search(query)
                                    self.view_mode = "search"
                                    self.selected_index = 0
                        else:
                            running = self.handle_input(str(key))
        
        except ImportError:
            # Fallback to simple mode
            self.run_simple()


def format_tree_ascii(tree: DocNode, format_type: str = "human") -> str:
    """Format tree as ASCII art."""
    builder = DocTreeBuilder()
    
    def render_node(node: DocNode, prefix: str = "", is_last: bool = True) -> List[str]:
        lines = []
        
        # Node icon
        icons = {
            NodeType.ROOT: "🏠",
            NodeType.DIRECTORY: "📁",
            NodeType.FILE: "📄",
            NodeType.SECTION: "§",
        }
        
        connector = "└── " if is_last else "├── "
        icon = icons.get(node.node_type, "•")
        
        line = f"{prefix}{connector}{icon} {node.name}"
        
        # Add health indicator
        if node.staleness_score > 0.5:
            line += " 🔴"
        elif node.staleness_score > 0.2:
            line += " 🟡"
        
        lines.append(line)
        
        # Children
        new_prefix = prefix + ("    " if is_last else "│   ")
        for i, child in enumerate(node.children):
            child_is_last = i == len(node.children) - 1
            lines.extend(render_node(child, new_prefix, child_is_last))
        
        return lines
    
    lines = [f"🏠 {tree.name}"]
    for i, child in enumerate(tree.children):
        is_last = i == len(tree.children) - 1
        lines.extend(render_node(child, "", is_last))
    
    return "\n".join(lines)


if __name__ == "__main__":
    print("Living Documentation - Interactive Explorer (Gen 9)")
    print("=" * 52)
    
    # Build tree
    builder = DocTreeBuilder()
    tree = builder.build()
    
    # Print tree
    print("\nDocumentation Tree:")
    print(format_tree_ascii(tree))
    
    # Run explorer
    print("\nLaunching explorer...")
    explorer = TerminalExplorer(tree)
    explorer.run()
