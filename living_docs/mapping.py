#!/usr/bin/env python3
"""Intelligent Code-to-Doc Mapping — Living Docs Enhancement

Provides smart mapping between code and documentation using:
- Path-based heuristics
- Content analysis (mentions, imports)
- Annotation-based explicit links
- Fuzzy name matching
- Module structure analysis
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from enum import Enum


class MappingConfidence(Enum):
    """Confidence level of a code-doc mapping."""
    EXPLICIT = "explicit"      # Annotated or configured
    HIGH = "high"              # Strong heuristic match
    MEDIUM = "medium"          # Name/path match
    LOW = "low"                # Fuzzy/weak match
    INFERRED = "inferred"      # Best guess


@dataclass
class CodeDocMapping:
    """A mapping between code and documentation."""
    code_path: str
    doc_path: str
    confidence: MappingConfidence
    match_reasons: list[str] = field(default_factory=list)
    code_entities: list[str] = field(default_factory=list)  # Classes/functions in code
    doc_sections: list[str] = field(default_factory=list)   # Headings in doc
    
    @property
    def confidence_score(self) -> float:
        """Numeric confidence score 0-1."""
        return {
            MappingConfidence.EXPLICIT: 1.0,
            MappingConfidence.HIGH: 0.9,
            MappingConfidence.MEDIUM: 0.7,
            MappingConfidence.LOW: 0.4,
            MappingConfidence.INFERRED: 0.2,
        }.get(self.confidence, 0.5)
    
    def to_dict(self) -> dict:
        return {
            "code_path": self.code_path,
            "doc_path": self.doc_path,
            "confidence": self.confidence.value,
            "confidence_score": self.confidence_score,
            "match_reasons": self.match_reasons,
            "code_entities": self.code_entities,
            "doc_sections": self.doc_sections,
        }


class CodeDocMapper:
    """Intelligent mapper between code files and documentation."""
    
    # Annotation patterns for explicit linking
    DOC_ANNOTATION = re.compile(
        r'#\s*@doc[s]?\s*:\s*([^\n]+)|'
        r'""".*?@doc[s]?\s*:\s*([^\n]+).*?"""',
        re.IGNORECASE | re.DOTALL
    )
    
    # Common doc directory patterns
    DOC_DIRS = ['docs', 'doc', 'documentation', 'wiki', 'manual']
    
    # Common code directory patterns
    CODE_DIRS = ['src', 'lib', 'app', 'pkg', 'core', 'internal']
    
    def __init__(self, project_root: Path, config: Optional[dict] = None):
        self.project_root = project_root
        self.config = config or {}
        
        # Explicit mappings from config
        self.explicit_mappings = self.config.get("mappings", {})
        
        # Cache
        self._code_files: list[Path] = []
        self._doc_files: list[Path] = []
        self._entity_index: dict[str, list[str]] = {}  # entity_name -> [code_paths]
    
    def find_all_mappings(self) -> list[CodeDocMapping]:
        """Find all code-to-doc mappings in the project."""
        self._scan_files()
        self._build_entity_index()
        
        mappings = []
        seen_pairs = set()
        
        # 1. First, process explicit mappings from config
        for code_pattern, doc_pattern in self.explicit_mappings.items():
            for code_file in self.project_root.glob(code_pattern):
                for doc_file in self.project_root.glob(doc_pattern):
                    pair = (str(code_file), str(doc_file))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        mappings.append(CodeDocMapping(
                            code_path=str(code_file.relative_to(self.project_root)),
                            doc_path=str(doc_file.relative_to(self.project_root)),
                            confidence=MappingConfidence.EXPLICIT,
                            match_reasons=["Configured mapping"],
                        ))
        
        # 2. Check for annotation-based mappings
        for code_file in self._code_files:
            annotated_docs = self._find_annotated_docs(code_file)
            for doc_path, reason in annotated_docs:
                pair = (str(code_file), str(doc_path))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    mappings.append(CodeDocMapping(
                        code_path=str(code_file.relative_to(self.project_root)),
                        doc_path=str(doc_path.relative_to(self.project_root)),
                        confidence=MappingConfidence.EXPLICIT,
                        match_reasons=[reason],
                    ))
        
        # 3. Path-based matching
        for code_file in self._code_files:
            matches = self._match_by_path(code_file)
            for doc_file, reasons in matches:
                pair = (str(code_file), str(doc_file))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    mappings.append(CodeDocMapping(
                        code_path=str(code_file.relative_to(self.project_root)),
                        doc_path=str(doc_file.relative_to(self.project_root)),
                        confidence=MappingConfidence.HIGH if len(reasons) > 1 else MappingConfidence.MEDIUM,
                        match_reasons=reasons,
                    ))
        
        # 4. Content-based matching
        for doc_file in self._doc_files:
            matches = self._match_by_content(doc_file)
            for code_file, reasons in matches:
                pair = (str(code_file), str(doc_file))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    mappings.append(CodeDocMapping(
                        code_path=str(code_file.relative_to(self.project_root)),
                        doc_path=str(doc_file.relative_to(self.project_root)),
                        confidence=MappingConfidence.MEDIUM,
                        match_reasons=reasons,
                    ))
        
        # 5. Fuzzy name matching for remaining docs
        unmapped_docs = set(self._doc_files) - {
            self.project_root / m.doc_path for m in mappings
        }
        
        for doc_file in unmapped_docs:
            matches = self._match_fuzzy(doc_file)
            for code_file, reasons in matches:
                pair = (str(code_file), str(doc_file))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    mappings.append(CodeDocMapping(
                        code_path=str(code_file.relative_to(self.project_root)),
                        doc_path=str(doc_file.relative_to(self.project_root)),
                        confidence=MappingConfidence.LOW,
                        match_reasons=reasons,
                    ))
        
        # Enrich mappings with entity info
        for mapping in mappings:
            self._enrich_mapping(mapping)
        
        # Sort by confidence
        mappings.sort(key=lambda m: m.confidence_score, reverse=True)
        
        return mappings
    
    def find_doc_for_code(self, code_path: Path) -> Optional[CodeDocMapping]:
        """Find the best documentation match for a code file."""
        mappings = self.find_all_mappings()
        
        code_str = str(code_path.relative_to(self.project_root) if code_path.is_absolute() else code_path)
        
        matches = [m for m in mappings if m.code_path == code_str]
        
        if matches:
            return matches[0]  # Highest confidence
        
        return None
    
    def find_code_for_doc(self, doc_path: Path) -> list[CodeDocMapping]:
        """Find all code files related to a documentation file."""
        mappings = self.find_all_mappings()
        
        doc_str = str(doc_path.relative_to(self.project_root) if doc_path.is_absolute() else doc_path)
        
        return [m for m in mappings if m.doc_path == doc_str]
    
    def _scan_files(self) -> None:
        """Scan project for code and doc files."""
        self._code_files = []
        self._doc_files = []
        
        # Code files
        code_patterns = self.config.get("sources", ["**/*.py", "**/*.ts", "**/*.js"])
        for pattern in code_patterns:
            for path in self.project_root.glob(pattern):
                if path.is_file() and not self._should_ignore(path):
                    self._code_files.append(path)
        
        # Doc files
        doc_patterns = self.config.get("docs", ["docs/**/*.md", "**/*.md"])
        for pattern in doc_patterns:
            for path in self.project_root.glob(pattern):
                if path.is_file() and not self._should_ignore(path):
                    self._doc_files.append(path)
    
    def _should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored."""
        ignore_patterns = [
            "__pycache__", "node_modules", ".git", ".venv", "venv",
            "build", "dist", ".egg-info", ".living-docs"
        ]
        path_str = str(path)
        return any(p in path_str for p in ignore_patterns)
    
    def _build_entity_index(self) -> None:
        """Build index of code entities (classes, functions) to files."""
        self._entity_index = {}
        
        for code_file in self._code_files:
            if code_file.suffix == ".py":
                entities = self._extract_python_entities(code_file)
                for entity in entities:
                    if entity not in self._entity_index:
                        self._entity_index[entity] = []
                    self._entity_index[entity].append(str(code_file))
    
    def _extract_python_entities(self, path: Path) -> list[str]:
        """Extract class and function names from Python file."""
        entities = []
        
        try:
            content = path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    entities.append(node.name)
                elif isinstance(node, ast.FunctionDef):
                    if not node.name.startswith("_"):
                        entities.append(node.name)
        except Exception:
            pass
        
        return entities
    
    def _find_annotated_docs(self, code_file: Path) -> list[tuple[Path, str]]:
        """Find docs explicitly linked in code annotations."""
        results = []
        
        try:
            content = code_file.read_text()
            
            for match in self.DOC_ANNOTATION.finditer(content):
                doc_ref = match.group(1) or match.group(2)
                if doc_ref:
                    doc_ref = doc_ref.strip()
                    
                    # Try to resolve the path
                    candidates = [
                        self.project_root / doc_ref,
                        self.project_root / "docs" / doc_ref,
                        self.project_root / "docs" / f"{doc_ref}.md",
                    ]
                    
                    for candidate in candidates:
                        if candidate.exists():
                            results.append((candidate, f"Annotation: @doc: {doc_ref}"))
                            break
        except Exception:
            pass
        
        return results
    
    def _match_by_path(self, code_file: Path) -> list[tuple[Path, list[str]]]:
        """Match code file to docs by path/name patterns."""
        results = []
        
        code_rel = code_file.relative_to(self.project_root)
        code_stem = code_file.stem.lower().replace("_", "-")
        code_stem_underscore = code_file.stem.lower().replace("-", "_")
        
        for doc_file in self._doc_files:
            reasons = []
            doc_rel = doc_file.relative_to(self.project_root)
            doc_stem = doc_file.stem.lower().replace("_", "-")
            
            # Exact name match
            if code_stem == doc_stem or code_stem_underscore == doc_file.stem.lower():
                reasons.append(f"Name match: {code_file.stem} = {doc_file.stem}")
            
            # Parent directory matches
            if code_rel.parent.name == doc_rel.parent.name:
                reasons.append(f"Same parent directory: {code_rel.parent.name}")
            
            # Code in src/, doc in docs/ with same subpath
            code_parts = code_rel.parts
            doc_parts = doc_rel.parts
            
            if code_parts and doc_parts:
                # Remove common prefixes (src, lib, docs, etc.)
                code_path_normalized = [p for p in code_parts if p not in self.CODE_DIRS]
                doc_path_normalized = [p for p in doc_parts if p not in self.DOC_DIRS]
                
                if code_path_normalized and doc_path_normalized:
                    # Compare normalized paths
                    code_subpath = "/".join(code_path_normalized[:-1])  # Exclude filename
                    doc_subpath = "/".join(doc_path_normalized[:-1])
                    
                    if code_subpath and code_subpath == doc_subpath:
                        reasons.append(f"Matching subpath: {code_subpath}")
            
            # API/reference doc patterns
            if "api" in str(doc_rel).lower() or "reference" in str(doc_rel).lower():
                if code_stem in doc_stem or doc_stem in code_stem:
                    reasons.append("API/reference doc name overlap")
            
            if reasons:
                results.append((doc_file, reasons))
        
        return results
    
    def _match_by_content(self, doc_file: Path) -> list[tuple[Path, list[str]]]:
        """Match doc to code by analyzing doc content."""
        results = []
        
        try:
            content = doc_file.read_text()
            content_lower = content.lower()
        except Exception:
            return results
        
        for code_file in self._code_files:
            reasons = []
            
            # Check if doc imports/references the code file
            code_rel = code_file.relative_to(self.project_root)
            code_module = str(code_rel).replace("/", ".").replace(".py", "")
            
            if code_module in content or str(code_rel) in content:
                reasons.append(f"Doc references module: {code_module}")
            
            # Check if doc mentions code entities
            entities = self._extract_python_entities(code_file)
            mentioned = [e for e in entities if e.lower() in content_lower]
            
            if len(mentioned) >= 2:
                reasons.append(f"Doc mentions entities: {', '.join(mentioned[:3])}")
            
            # Check for code blocks that look like they're from this file
            code_blocks = re.findall(r"```(?:python)?\n(.*?)```", content, re.DOTALL)
            for block in code_blocks:
                for entity in entities:
                    if entity in block:
                        reasons.append(f"Code example contains: {entity}")
                        break
            
            if reasons:
                results.append((code_file, reasons))
        
        return results
    
    def _match_fuzzy(self, doc_file: Path) -> list[tuple[Path, list[str]]]:
        """Fuzzy match doc to code using various heuristics."""
        results = []
        
        doc_stem = doc_file.stem.lower()
        doc_words = set(re.split(r"[-_\s]+", doc_stem))
        
        for code_file in self._code_files:
            code_stem = code_file.stem.lower()
            code_words = set(re.split(r"[-_\s]+", code_stem))
            
            # Word overlap
            common_words = doc_words & code_words
            if common_words and len(common_words) >= len(doc_words) * 0.5:
                results.append((code_file, [f"Word overlap: {', '.join(common_words)}"]))
        
        return results
    
    def _enrich_mapping(self, mapping: CodeDocMapping) -> None:
        """Add entity and section info to mapping."""
        code_path = self.project_root / mapping.code_path
        doc_path = self.project_root / mapping.doc_path
        
        # Extract code entities
        if code_path.exists():
            mapping.code_entities = self._extract_python_entities(code_path)
        
        # Extract doc sections (headings)
        if doc_path.exists():
            try:
                content = doc_path.read_text()
                headings = re.findall(r"^#{1,6}\s+(.+)$", content, re.MULTILINE)
                mapping.doc_sections = headings[:10]  # Limit
            except Exception:
                pass
    
    def get_mapping_report(self) -> dict:
        """Generate a summary report of all mappings."""
        mappings = self.find_all_mappings()
        
        # Stats
        by_confidence = {}
        for m in mappings:
            conf = m.confidence.value
            by_confidence[conf] = by_confidence.get(conf, 0) + 1
        
        unmapped_code = set(str(f.relative_to(self.project_root)) for f in self._code_files) - {
            m.code_path for m in mappings
        }
        
        unmapped_docs = set(str(f.relative_to(self.project_root)) for f in self._doc_files) - {
            m.doc_path for m in mappings
        }
        
        return {
            "total_mappings": len(mappings),
            "by_confidence": by_confidence,
            "unmapped_code_files": list(unmapped_code)[:20],
            "unmapped_doc_files": list(unmapped_docs)[:20],
            "mappings": [m.to_dict() for m in mappings],
        }


def format_mapping_report(mapper: CodeDocMapper) -> str:
    """Format mapping report as human-readable text."""
    report = mapper.get_mapping_report()
    
    lines = [
        "📎 Code-to-Documentation Mapping Report",
        "=" * 50,
        "",
        f"Total mappings found: {report['total_mappings']}",
        "",
        "By confidence:",
    ]
    
    confidence_emoji = {
        "explicit": "🎯",
        "high": "✅",
        "medium": "🟡",
        "low": "🟠",
        "inferred": "❓",
    }
    
    for conf, count in report["by_confidence"].items():
        emoji = confidence_emoji.get(conf, "")
        lines.append(f"  {emoji} {conf}: {count}")
    
    if report["unmapped_code_files"]:
        lines.extend([
            "",
            f"⚠️  Unmapped code files ({len(report['unmapped_code_files'])}):",
        ])
        for f in report["unmapped_code_files"][:5]:
            lines.append(f"  - {f}")
        if len(report["unmapped_code_files"]) > 5:
            lines.append(f"  ... and {len(report['unmapped_code_files']) - 5} more")
    
    if report["unmapped_doc_files"]:
        lines.extend([
            "",
            f"📄 Orphaned doc files ({len(report['unmapped_doc_files'])}):",
        ])
        for f in report["unmapped_doc_files"][:5]:
            lines.append(f"  - {f}")
        if len(report["unmapped_doc_files"]) > 5:
            lines.append(f"  ... and {len(report['unmapped_doc_files']) - 5} more")
    
    lines.extend([
        "",
        "📋 Mapping Details:",
        "-" * 40,
    ])
    
    for m in report["mappings"][:15]:
        lines.append(f"\n{confidence_emoji.get(m['confidence'], '')} {m['code_path']}")
        lines.append(f"   → {m['doc_path']}")
        lines.append(f"   Confidence: {m['confidence']} ({m['confidence_score']:.0%})")
        for reason in m["match_reasons"][:2]:
            lines.append(f"   • {reason}")
    
    return "\n".join(lines)
