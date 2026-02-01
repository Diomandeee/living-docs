"""
Test-to-Example Generation Module (Gen 9)

Transforms test files into documentation examples using LLM intelligence.
Features:
- Extract meaningful test cases
- Generate human-readable examples
- Preserve edge case demonstrations
- Create runnable code snippets
"""

import ast
import os
import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum


class ExampleQuality(Enum):
    """Quality rating for generated examples."""
    EXCELLENT = "excellent"  # Clear, concise, educational
    GOOD = "good"           # Usable with minor improvements
    FAIR = "fair"           # Needs editing but salvageable
    POOR = "poor"           # Rewrite recommended


@dataclass
class TestCase:
    """Represents an extracted test case."""
    file_path: str
    function_name: str
    class_name: Optional[str]
    docstring: Optional[str]
    code: str
    setup_code: Optional[str] = None
    teardown_code: Optional[str] = None
    assertions: List[str] = field(default_factory=list)
    fixtures: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    line_number: int = 0
    complexity: int = 1  # 1-10 scale


@dataclass
class GeneratedExample:
    """A documentation example generated from tests."""
    source_test: TestCase
    title: str
    description: str
    code: str
    output: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    quality: ExampleQuality = ExampleQuality.GOOD
    target_doc: Optional[str] = None
    tags: List[str] = field(default_factory=list)


class TestExtractor:
    """Extracts test cases from Python test files."""
    
    # Patterns for test file detection
    TEST_FILE_PATTERNS = [
        r"test_.*\.py$",
        r".*_test\.py$",
        r"tests?\.py$",
    ]
    
    # Patterns for test function detection
    TEST_FUNC_PATTERNS = [
        r"^test_",
        r"^it_",
        r"^should_",
    ]
    
    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path.cwd()
    
    def is_test_file(self, path: Path) -> bool:
        """Check if a file is a test file."""
        name = path.name
        return any(re.match(p, name) for p in self.TEST_FILE_PATTERNS)
    
    def find_test_files(self, paths: Optional[List[str]] = None) -> List[Path]:
        """Find all test files in the project."""
        if paths:
            return [Path(p) for p in paths if self.is_test_file(Path(p))]
        
        test_files = []
        for pattern in ["**/test_*.py", "**/*_test.py", "**/tests/*.py"]:
            test_files.extend(self.project_root.glob(pattern))
        
        return sorted(set(test_files))
    
    def _is_test_function(self, name: str) -> bool:
        """Check if a function name indicates a test."""
        return any(re.match(p, name) for p in self.TEST_FUNC_PATTERNS)
    
    def _extract_docstring(self, node: ast.FunctionDef) -> Optional[str]:
        """Extract docstring from a function."""
        if (node.body and isinstance(node.body[0], ast.Expr) and
            isinstance(node.body[0].value, ast.Constant) and
            isinstance(node.body[0].value.value, str)):
            return node.body[0].value.value
        return None
    
    def _extract_assertions(self, node: ast.FunctionDef) -> List[str]:
        """Extract assertion statements from a function."""
        assertions = []
        
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Assert):
                # Get the assertion as source code (simplified)
                assertions.append(f"assert ...")
            elif isinstance(stmt, ast.Call):
                if isinstance(stmt.func, ast.Attribute):
                    name = stmt.func.attr
                    if name.startswith(("assert", "expect", "should")):
                        assertions.append(f"{name}(...)")
                elif isinstance(stmt.func, ast.Name):
                    name = stmt.func.id
                    if name.startswith(("assert", "expect")):
                        assertions.append(f"{name}(...)")
        
        return assertions
    
    def _extract_fixtures(self, node: ast.FunctionDef) -> List[str]:
        """Extract pytest fixture names from function arguments."""
        fixtures = []
        for arg in node.args.args:
            name = arg.arg
            # Skip common non-fixture args
            if name not in ("self", "cls"):
                fixtures.append(name)
        return fixtures
    
    def _calculate_complexity(self, node: ast.FunctionDef) -> int:
        """Calculate test complexity (1-10 scale)."""
        complexity = 1
        
        # Lines of code
        lines = len([n for n in ast.walk(node) if isinstance(n, ast.stmt)])
        complexity += min(lines // 5, 3)
        
        # Control flow
        for stmt in ast.walk(node):
            if isinstance(stmt, (ast.If, ast.For, ast.While, ast.Try)):
                complexity += 1
            if isinstance(stmt, ast.With):
                complexity += 0.5
        
        return min(int(complexity), 10)
    
    def _infer_tags(self, test: TestCase) -> List[str]:
        """Infer tags from test name and content."""
        tags = []
        name = test.function_name.lower()
        
        # From name
        tag_patterns = {
            "api": ["api", "endpoint", "route", "request", "response"],
            "database": ["db", "database", "sql", "query", "model"],
            "auth": ["auth", "login", "permission", "token", "session"],
            "validation": ["valid", "invalid", "error", "exception"],
            "integration": ["integration", "e2e", "end_to_end"],
            "performance": ["perf", "benchmark", "slow", "fast"],
            "edge_case": ["edge", "corner", "boundary", "limit"],
            "regression": ["regression", "bug", "fix", "issue"],
        }
        
        for tag, keywords in tag_patterns.items():
            if any(kw in name for kw in keywords):
                tags.append(tag)
        
        # From docstring
        if test.docstring:
            doc_lower = test.docstring.lower()
            for tag, keywords in tag_patterns.items():
                if tag not in tags and any(kw in doc_lower for kw in keywords):
                    tags.append(tag)
        
        return tags
    
    def extract_from_file(self, file_path: Path) -> List[TestCase]:
        """Extract test cases from a single file."""
        tests = []
        
        try:
            content = file_path.read_text()
            tree = ast.parse(content)
        except (SyntaxError, OSError) as e:
            print(f"Failed to parse {file_path}: {e}")
            return []
        
        # Get source lines for code extraction
        source_lines = content.splitlines()
        
        # Find setup/teardown at module level
        module_setup = None
        module_teardown = None
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name in ("setup_module", "setUpModule"):
                    start = node.lineno - 1
                    end = node.end_lineno if hasattr(node, 'end_lineno') else start + 10
                    module_setup = "\n".join(source_lines[start:end])
                elif node.name in ("teardown_module", "tearDownModule"):
                    start = node.lineno - 1
                    end = node.end_lineno if hasattr(node, 'end_lineno') else start + 10
                    module_teardown = "\n".join(source_lines[start:end])
        
        # Extract test functions
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and self._is_test_function(node.name):
                # Get code
                start = node.lineno - 1
                end = node.end_lineno if hasattr(node, 'end_lineno') else start + 20
                code = "\n".join(source_lines[start:end])
                
                test = TestCase(
                    file_path=str(file_path.relative_to(self.project_root)),
                    function_name=node.name,
                    class_name=None,  # Will be set if inside class
                    docstring=self._extract_docstring(node),
                    code=code,
                    setup_code=module_setup,
                    teardown_code=module_teardown,
                    assertions=self._extract_assertions(node),
                    fixtures=self._extract_fixtures(node),
                    line_number=node.lineno,
                    complexity=self._calculate_complexity(node),
                )
                
                test.tags = self._infer_tags(test)
                tests.append(test)
            
            # Handle test classes
            elif isinstance(node, ast.ClassDef) and (
                node.name.startswith("Test") or
                any(base.id == "TestCase" for base in node.bases if isinstance(base, ast.Name))
            ):
                # Find setup/teardown methods
                class_setup = None
                class_teardown = None
                
                for method in node.body:
                    if isinstance(method, ast.FunctionDef):
                        if method.name in ("setUp", "setup_method"):
                            start = method.lineno - 1
                            end = method.end_lineno if hasattr(method, 'end_lineno') else start + 10
                            class_setup = "\n".join(source_lines[start:end])
                        elif method.name in ("tearDown", "teardown_method"):
                            start = method.lineno - 1
                            end = method.end_lineno if hasattr(method, 'end_lineno') else start + 10
                            class_teardown = "\n".join(source_lines[start:end])
                
                # Extract test methods
                for method in node.body:
                    if isinstance(method, ast.FunctionDef) and self._is_test_function(method.name):
                        start = method.lineno - 1
                        end = method.end_lineno if hasattr(method, 'end_lineno') else start + 20
                        code = "\n".join(source_lines[start:end])
                        
                        test = TestCase(
                            file_path=str(file_path.relative_to(self.project_root)),
                            function_name=method.name,
                            class_name=node.name,
                            docstring=self._extract_docstring(method),
                            code=code,
                            setup_code=class_setup or module_setup,
                            teardown_code=class_teardown or module_teardown,
                            assertions=self._extract_assertions(method),
                            fixtures=self._extract_fixtures(method),
                            line_number=method.lineno,
                            complexity=self._calculate_complexity(method),
                        )
                        
                        test.tags = self._infer_tags(test)
                        tests.append(test)
        
        return tests
    
    def extract_all(self, paths: Optional[List[str]] = None) -> List[TestCase]:
        """Extract test cases from all test files."""
        all_tests = []
        
        for file_path in self.find_test_files(paths):
            tests = self.extract_from_file(file_path)
            all_tests.extend(tests)
        
        return all_tests


class ExampleGenerator:
    """Generates documentation examples from test cases."""
    
    def __init__(
        self,
        ai_provider: Optional[str] = None,
        ai_model: Optional[str] = None,
        project_root: Optional[Path] = None
    ):
        self.ai_provider = ai_provider or os.getenv("LIVING_DOCS_AI_PROVIDER", "anthropic")
        self.ai_model = ai_model or os.getenv("LIVING_DOCS_AI_MODEL", "claude-sonnet-4-20250514")
        self.project_root = project_root or Path.cwd()
    
    def _clean_test_code(self, test: TestCase) -> str:
        """Clean test code for example generation."""
        code = test.code
        
        # Remove test function definition line
        lines = code.split("\n")
        if lines and lines[0].strip().startswith("def test_"):
            # Remove function def and adjust indentation
            lines = lines[1:]
            # Remove one level of indentation
            lines = [l[4:] if l.startswith("    ") else l for l in lines]
        
        # Remove assert statements (we want examples, not tests)
        clean_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped.startswith(("assert", "self.assert", "pytest.raises")):
                clean_lines.append(line)
        
        code = "\n".join(clean_lines)
        
        # Remove trailing whitespace and empty lines at end
        return code.rstrip()
    
    def _infer_title(self, test: TestCase) -> str:
        """Generate a human-readable title from test name."""
        name = test.function_name
        
        # Remove test_ prefix
        name = re.sub(r"^test_", "", name)
        name = re.sub(r"^it_", "", name)
        name = re.sub(r"^should_", "", name)
        
        # Convert to title case with spaces
        name = re.sub(r"_+", " ", name)
        name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
        
        return name.title()
    
    def _infer_description(self, test: TestCase) -> str:
        """Generate a description from docstring or test name."""
        if test.docstring:
            # Use first sentence of docstring
            first_line = test.docstring.split("\n")[0].strip()
            if first_line:
                return first_line
        
        # Generate from test name
        title = self._infer_title(test)
        return f"Demonstrates how to {title.lower()}"
    
    def _simple_transform(self, test: TestCase) -> GeneratedExample:
        """Transform test to example without AI."""
        code = self._clean_test_code(test)
        title = self._infer_title(test)
        description = self._infer_description(test)
        
        # Determine quality
        if test.complexity <= 3 and len(code.split("\n")) <= 10:
            quality = ExampleQuality.GOOD
        elif test.complexity <= 5:
            quality = ExampleQuality.FAIR
        else:
            quality = ExampleQuality.POOR
        
        return GeneratedExample(
            source_test=test,
            title=title,
            description=description,
            code=code,
            quality=quality,
            tags=test.tags,
            notes=self._generate_notes(test),
        )
    
    def _generate_notes(self, test: TestCase) -> List[str]:
        """Generate usage notes from test details."""
        notes = []
        
        if test.fixtures:
            notes.append(f"Uses fixtures: {', '.join(test.fixtures)}")
        
        if "edge_case" in test.tags:
            notes.append("⚠️ This example demonstrates an edge case")
        
        if test.setup_code:
            notes.append("Requires setup (see test file for details)")
        
        return notes
    
    def _ai_transform(self, test: TestCase) -> GeneratedExample:
        """Transform test to example using AI."""
        try:
            if self.ai_provider == "anthropic":
                return self._anthropic_transform(test)
            elif self.ai_provider == "openai":
                return self._openai_transform(test)
            else:
                return self._simple_transform(test)
        except Exception as e:
            print(f"AI transform failed: {e}")
            return self._simple_transform(test)
    
    def _anthropic_transform(self, test: TestCase) -> GeneratedExample:
        """Transform using Anthropic Claude."""
        try:
            import anthropic
            client = anthropic.Anthropic()
            
            prompt = f"""Transform this test case into a clean, educational code example for documentation.

TEST CODE:
```python
{test.code}
```

TEST INFO:
- Name: {test.function_name}
- Docstring: {test.docstring or 'None'}
- Tags: {', '.join(test.tags) or 'None'}

Generate:
1. A clear title (no "Test" prefix)
2. A one-sentence description
3. Clean, runnable example code (remove asserts, simplify)
4. Expected output (if deterministic)
5. Any important notes

Respond in JSON:
{{
  "title": "...",
  "description": "...",
  "code": "...",
  "output": "...",  // null if non-deterministic
  "notes": ["...", "..."],
  "quality": "excellent|good|fair|poor"
}}"""
            
            response = client.messages.create(
                model=self.ai_model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Parse JSON from response
            text = response.content[0].text
            
            # Extract JSON if wrapped in markdown
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            data = json.loads(text)
            
            return GeneratedExample(
                source_test=test,
                title=data.get("title", self._infer_title(test)),
                description=data.get("description", self._infer_description(test)),
                code=data.get("code", self._clean_test_code(test)),
                output=data.get("output"),
                notes=data.get("notes", []),
                quality=ExampleQuality(data.get("quality", "good")),
                tags=test.tags,
            )
            
        except ImportError:
            print("anthropic package not installed")
            return self._simple_transform(test)
        except Exception as e:
            print(f"Anthropic API error: {e}")
            return self._simple_transform(test)
    
    def _openai_transform(self, test: TestCase) -> GeneratedExample:
        """Transform using OpenAI."""
        try:
            import openai
            client = openai.OpenAI()
            
            prompt = f"""Transform this test into a documentation example.

TEST:
```python
{test.code}
```

Return JSON with: title, description, code (clean example), output, notes, quality (excellent/good/fair/poor)"""
            
            response = client.chat.completions.create(
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            data = json.loads(response.choices[0].message.content)
            
            return GeneratedExample(
                source_test=test,
                title=data.get("title", self._infer_title(test)),
                description=data.get("description", ""),
                code=data.get("code", self._clean_test_code(test)),
                output=data.get("output"),
                notes=data.get("notes", []),
                quality=ExampleQuality(data.get("quality", "good")),
                tags=test.tags,
            )
            
        except ImportError:
            return self._simple_transform(test)
        except Exception as e:
            print(f"OpenAI API error: {e}")
            return self._simple_transform(test)
    
    def generate(
        self,
        test: TestCase,
        use_ai: bool = True,
        target_doc: Optional[str] = None
    ) -> GeneratedExample:
        """Generate an example from a test case."""
        if use_ai:
            example = self._ai_transform(test)
        else:
            example = self._simple_transform(test)
        
        if target_doc:
            example.target_doc = target_doc
        
        return example
    
    def generate_batch(
        self,
        tests: List[TestCase],
        use_ai: bool = True,
        min_quality: ExampleQuality = ExampleQuality.FAIR,
        max_complexity: int = 7
    ) -> List[GeneratedExample]:
        """Generate examples from multiple tests."""
        examples = []
        
        # Filter by complexity
        suitable = [t for t in tests if t.complexity <= max_complexity]
        
        for test in suitable:
            example = self.generate(test, use_ai=use_ai)
            
            # Filter by quality
            quality_order = [ExampleQuality.POOR, ExampleQuality.FAIR, 
                           ExampleQuality.GOOD, ExampleQuality.EXCELLENT]
            if quality_order.index(example.quality) >= quality_order.index(min_quality):
                examples.append(example)
        
        return examples


class ExampleFormatter:
    """Formats generated examples for documentation."""
    
    @staticmethod
    def to_markdown(example: GeneratedExample, include_source: bool = False) -> str:
        """Format example as Markdown."""
        lines = [
            f"### {example.title}",
            "",
            example.description,
            "",
            "```python",
            example.code,
            "```",
        ]
        
        if example.output:
            lines.extend([
                "",
                "**Output:**",
                "```",
                example.output,
                "```",
            ])
        
        if example.notes:
            lines.extend(["", "**Notes:**"])
            for note in example.notes:
                lines.append(f"- {note}")
        
        if include_source:
            lines.extend([
                "",
                f"*Source: `{example.source_test.file_path}:{example.source_test.line_number}`*",
            ])
        
        return "\n".join(lines)
    
    @staticmethod
    def to_rst(example: GeneratedExample) -> str:
        """Format example as reStructuredText."""
        lines = [
            example.title,
            "=" * len(example.title),
            "",
            example.description,
            "",
            ".. code-block:: python",
            "",
        ]
        
        for line in example.code.split("\n"):
            lines.append(f"    {line}")
        
        if example.output:
            lines.extend([
                "",
                "Output:",
                "",
                ".. code-block::",
                "",
            ])
            for line in example.output.split("\n"):
                lines.append(f"    {line}")
        
        return "\n".join(lines)
    
    @staticmethod
    def to_json(example: GeneratedExample) -> Dict:
        """Format example as JSON-serializable dict."""
        return {
            "title": example.title,
            "description": example.description,
            "code": example.code,
            "output": example.output,
            "notes": example.notes,
            "quality": example.quality.value,
            "tags": example.tags,
            "source": {
                "file": example.source_test.file_path,
                "function": example.source_test.function_name,
                "line": example.source_test.line_number,
            }
        }


def format_examples_report(examples: List[GeneratedExample], format_type: str = "human") -> str:
    """Format a batch of examples."""
    if format_type == "json":
        return json.dumps([ExampleFormatter.to_json(e) for e in examples], indent=2)
    
    if format_type == "markdown":
        lines = ["# Generated Examples", ""]
        
        # Group by quality
        by_quality: Dict[ExampleQuality, List[GeneratedExample]] = {}
        for ex in examples:
            by_quality.setdefault(ex.quality, []).append(ex)
        
        for quality in [ExampleQuality.EXCELLENT, ExampleQuality.GOOD, 
                       ExampleQuality.FAIR, ExampleQuality.POOR]:
            if quality in by_quality:
                lines.extend([
                    f"## {quality.value.title()} Quality",
                    "",
                ])
                for ex in by_quality[quality]:
                    lines.append(ExampleFormatter.to_markdown(ex, include_source=True))
                    lines.append("")
        
        return "\n".join(lines)
    
    # Human readable
    lines = ["\n=== Test-to-Example Generation ===\n"]
    lines.append(f"Generated {len(examples)} examples\n")
    
    quality_counts = {}
    for ex in examples:
        quality_counts[ex.quality.value] = quality_counts.get(ex.quality.value, 0) + 1
    
    for q, count in sorted(quality_counts.items()):
        icon = {"excellent": "🌟", "good": "✅", "fair": "⚠️", "poor": "❌"}.get(q, "?")
        lines.append(f"  {icon} {q.title()}: {count}")
    
    lines.append("")
    
    for ex in examples:
        icon = {"excellent": "🌟", "good": "✅", "fair": "⚠️", "poor": "❌"}.get(ex.quality.value, "?")
        lines.append(f"{icon} {ex.title}")
        lines.append(f"   From: {ex.source_test.file_path}:{ex.source_test.line_number}")
        lines.append(f"   Tags: {', '.join(ex.tags) or 'none'}")
        lines.append("")
    
    return "\n".join(lines)


if __name__ == "__main__":
    print("Living Documentation - Test-to-Example Generator (Gen 9)")
    print("=" * 55)
    
    # Demo extraction
    extractor = TestExtractor()
    generator = ExampleGenerator()
    
    # Find test files
    test_files = extractor.find_test_files()
    print(f"\nFound {len(test_files)} test files")
    
    if test_files:
        # Extract from first file
        tests = extractor.extract_from_file(test_files[0])
        print(f"Extracted {len(tests)} tests from {test_files[0].name}")
        
        if tests:
            # Generate examples (without AI for demo)
            examples = generator.generate_batch(tests, use_ai=False)
            print(format_examples_report(examples))
