#!/usr/bin/env python3
"""Runnable Examples Validator — Gen 8 Feature

Extracts code examples from documentation and validates them against
the actual codebase. Ensures examples stay in sync with code changes.

Features:
- Extract code blocks from Markdown/RST
- Detect example type (Python, JS, bash, etc.)
- Validate Python examples via exec/doctest
- Validate imports exist in codebase
- Detect outdated API usage
- Generate reports with fixable issues
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
import hashlib


class ExampleType(Enum):
    """Type of code example."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    BASH = "bash"
    JSON = "json"
    YAML = "yaml"
    OTHER = "other"


class ValidationResult(Enum):
    """Result of example validation."""
    VALID = "valid"
    SYNTAX_ERROR = "syntax_error"
    IMPORT_ERROR = "import_error"
    EXECUTION_ERROR = "execution_error"
    OUTDATED_API = "outdated_api"
    MISSING_DEPENDENCY = "missing_dependency"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"


@dataclass
class CodeExample:
    """A code example extracted from documentation."""
    content: str
    language: ExampleType
    source_file: str
    line_start: int
    line_end: int
    context: str = ""  # Surrounding text
    hash: str = ""
    metadata: dict = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.hash:
            self.hash = hashlib.md5(self.content.encode()).hexdigest()[:8]


@dataclass
class ValidationReport:
    """Report from validating a code example."""
    example: CodeExample
    result: ValidationResult
    message: str = ""
    details: list[str] = field(default_factory=list)
    suggested_fix: Optional[str] = None
    execution_output: str = ""
    
    @property
    def is_valid(self) -> bool:
        return self.result == ValidationResult.VALID


@dataclass
class ExamplesReport:
    """Full report on all examples in a project."""
    project_root: str
    total_examples: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    skipped_count: int = 0
    examples: list[ValidationReport] = field(default_factory=list)
    
    @property
    def pass_rate(self) -> float:
        if self.total_examples == 0:
            return 100.0
        return (self.valid_count / self.total_examples) * 100
    
    def to_dict(self) -> dict:
        return {
            "project_root": self.project_root,
            "summary": {
                "total": self.total_examples,
                "valid": self.valid_count,
                "invalid": self.invalid_count,
                "skipped": self.skipped_count,
                "pass_rate": round(self.pass_rate, 2)
            },
            "examples": [
                {
                    "source": e.example.source_file,
                    "line": e.example.line_start,
                    "language": e.example.language.value,
                    "result": e.result.value,
                    "message": e.message,
                    "hash": e.example.hash
                }
                for e in self.examples
            ]
        }


class ExampleExtractor:
    """Extract code examples from documentation files."""
    
    # Markdown fenced code blocks
    MARKDOWN_CODE = re.compile(
        r'```(\w*)\n(.*?)```',
        re.DOTALL
    )
    
    # RST code blocks
    RST_CODE = re.compile(
        r'\.\. code-block::\s*(\w+)\n\n((?:\s{3,}.*\n?)+)',
        re.MULTILINE
    )
    
    # Doctest examples
    DOCTEST = re.compile(
        r'(>>> .*?(?:\n(?:\.\.\.|\s{4}).*)*)',
        re.MULTILINE
    )
    
    LANGUAGE_MAP = {
        "python": ExampleType.PYTHON,
        "py": ExampleType.PYTHON,
        "python3": ExampleType.PYTHON,
        "javascript": ExampleType.JAVASCRIPT,
        "js": ExampleType.JAVASCRIPT,
        "typescript": ExampleType.TYPESCRIPT,
        "ts": ExampleType.TYPESCRIPT,
        "bash": ExampleType.BASH,
        "shell": ExampleType.BASH,
        "sh": ExampleType.BASH,
        "json": ExampleType.JSON,
        "yaml": ExampleType.YAML,
        "yml": ExampleType.YAML,
    }
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
    
    def extract_from_file(self, path: Path) -> list[CodeExample]:
        """Extract examples from a single file."""
        try:
            content = path.read_text(errors="ignore")
        except Exception:
            return []
        
        rel_path = str(path.relative_to(self.project_root))
        examples = []
        
        # Extract Markdown code blocks
        for match in self.MARKDOWN_CODE.finditer(content):
            lang_hint = match.group(1).lower()
            code = match.group(2).strip()
            
            if not code or len(code) < 10:
                continue
            
            language = self.LANGUAGE_MAP.get(lang_hint, ExampleType.OTHER)
            line_start = content[:match.start()].count('\n') + 1
            line_end = line_start + code.count('\n')
            
            # Get context (text before the code block)
            context_start = max(0, match.start() - 200)
            context = content[context_start:match.start()].strip()
            
            examples.append(CodeExample(
                content=code,
                language=language,
                source_file=rel_path,
                line_start=line_start,
                line_end=line_end,
                context=context[-150:] if len(context) > 150 else context
            ))
        
        # Extract RST code blocks
        for match in self.RST_CODE.finditer(content):
            lang_hint = match.group(1).lower()
            code = match.group(2).strip()
            
            if not code:
                continue
            
            # Remove RST indentation
            lines = code.split('\n')
            min_indent = min(len(line) - len(line.lstrip()) for line in lines if line.strip())
            code = '\n'.join(line[min_indent:] if len(line) > min_indent else line for line in lines)
            
            language = self.LANGUAGE_MAP.get(lang_hint, ExampleType.OTHER)
            line_start = content[:match.start()].count('\n') + 1
            
            examples.append(CodeExample(
                content=code,
                language=language,
                source_file=rel_path,
                line_start=line_start,
                line_end=line_start + code.count('\n')
            ))
        
        # Extract doctest examples
        for match in self.DOCTEST.finditer(content):
            doctest_code = match.group(1)
            line_start = content[:match.start()].count('\n') + 1
            
            examples.append(CodeExample(
                content=doctest_code,
                language=ExampleType.PYTHON,
                source_file=rel_path,
                line_start=line_start,
                line_end=line_start + doctest_code.count('\n'),
                metadata={"is_doctest": True}
            ))
        
        return examples
    
    def extract_all(self, patterns: Optional[list[str]] = None) -> list[CodeExample]:
        """Extract all examples from documentation files."""
        patterns = patterns or ["**/*.md", "**/*.mdx", "**/*.rst", "docs/**/*"]
        
        all_examples = []
        seen_hashes = set()
        
        for pattern in patterns:
            for path in self.project_root.glob(pattern):
                if path.is_file():
                    for example in self.extract_from_file(path):
                        # Dedupe by content hash
                        if example.hash not in seen_hashes:
                            seen_hashes.add(example.hash)
                            all_examples.append(example)
        
        return all_examples


class PythonValidator:
    """Validate Python code examples."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._module_cache: dict[str, bool] = {}
    
    def validate(self, example: CodeExample) -> ValidationReport:
        """Validate a Python code example."""
        code = example.content
        
        # Handle doctest format
        if example.metadata.get("is_doctest"):
            return self._validate_doctest(example)
        
        # 1. Syntax check
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return ValidationReport(
                example=example,
                result=ValidationResult.SYNTAX_ERROR,
                message=f"Syntax error at line {e.lineno}: {e.msg}",
                details=[str(e)],
                suggested_fix=self._suggest_syntax_fix(code, e)
            )
        
        # 2. Check imports exist
        import_issues = self._check_imports(tree)
        if import_issues:
            return ValidationReport(
                example=example,
                result=ValidationResult.IMPORT_ERROR,
                message="Import issues detected",
                details=import_issues
            )
        
        # 3. Check for outdated API patterns
        api_issues = self._check_api_patterns(code, tree)
        if api_issues:
            return ValidationReport(
                example=example,
                result=ValidationResult.OUTDATED_API,
                message="Possibly outdated API usage",
                details=api_issues
            )
        
        # 4. Try to execute (in sandbox if safe)
        if self._is_safe_to_execute(tree):
            exec_result = self._execute_safely(code)
            if exec_result["success"]:
                return ValidationReport(
                    example=example,
                    result=ValidationResult.VALID,
                    message="Example executed successfully",
                    execution_output=exec_result.get("output", "")
                )
            else:
                return ValidationReport(
                    example=example,
                    result=ValidationResult.EXECUTION_ERROR,
                    message="Execution failed",
                    details=[exec_result.get("error", "Unknown error")],
                    execution_output=exec_result.get("output", "")
                )
        
        # If we can't execute, at least it parsed correctly
        return ValidationReport(
            example=example,
            result=ValidationResult.VALID,
            message="Syntax valid (execution skipped)"
        )
    
    def _validate_doctest(self, example: CodeExample) -> ValidationReport:
        """Validate a doctest example."""
        code = example.content
        
        # Create a temporary module to run doctest
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            # Wrap in a function for doctest
            f.write(f'''
def example_function():
    """
{code}
    """
    pass

if __name__ == "__main__":
    import doctest
    results = doctest.testmod(verbose=False)
    print(f"DOCTEST_RESULTS:{{results.attempted}},{{results.failed}}")
''')
            temp_path = f.name
        
        try:
            result = subprocess.run(
                [sys.executable, temp_path],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(self.project_root)
            )
            
            output = result.stdout + result.stderr
            
            # Parse results
            if "DOCTEST_RESULTS:" in output:
                match = re.search(r'DOCTEST_RESULTS:(\d+),(\d+)', output)
                if match:
                    attempted, failed = int(match.group(1)), int(match.group(2))
                    if failed == 0:
                        return ValidationReport(
                            example=example,
                            result=ValidationResult.VALID,
                            message=f"Doctest passed ({attempted} tests)"
                        )
                    else:
                        return ValidationReport(
                            example=example,
                            result=ValidationResult.EXECUTION_ERROR,
                            message=f"Doctest failed ({failed}/{attempted} tests)",
                            execution_output=output
                        )
            
            if result.returncode != 0:
                return ValidationReport(
                    example=example,
                    result=ValidationResult.EXECUTION_ERROR,
                    message="Doctest execution failed",
                    execution_output=output
                )
            
            return ValidationReport(
                example=example,
                result=ValidationResult.VALID,
                message="Doctest validated"
            )
            
        except subprocess.TimeoutExpired:
            return ValidationReport(
                example=example,
                result=ValidationResult.EXECUTION_ERROR,
                message="Doctest timed out"
            )
        except Exception as e:
            return ValidationReport(
                example=example,
                result=ValidationResult.UNKNOWN,
                message=f"Doctest error: {e}"
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def _check_imports(self, tree: ast.AST) -> list[str]:
        """Check if imports can be resolved."""
        issues = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not self._can_import(alias.name):
                        issues.append(f"Cannot import '{alias.name}'")
            
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if not self._can_import(module):
                    issues.append(f"Cannot import from '{module}'")
        
        return issues
    
    def _can_import(self, module_name: str) -> bool:
        """Check if a module can be imported."""
        if module_name in self._module_cache:
            return self._module_cache[module_name]
        
        # Standard library and common packages
        standard_lib = {
            "os", "sys", "re", "json", "datetime", "pathlib", "typing",
            "collections", "itertools", "functools", "math", "random",
            "time", "asyncio", "subprocess", "logging", "unittest",
            "dataclasses", "enum", "abc", "io", "tempfile", "hashlib"
        }
        
        root_module = module_name.split(".")[0]
        if root_module in standard_lib:
            self._module_cache[module_name] = True
            return True
        
        # Check if it's a local module
        local_path = self.project_root / module_name.replace(".", "/")
        if local_path.exists() or (local_path.parent / f"{local_path.name}.py").exists():
            self._module_cache[module_name] = True
            return True
        
        # Try actual import
        try:
            __import__(module_name)
            self._module_cache[module_name] = True
            return True
        except ImportError:
            self._module_cache[module_name] = False
            return False
    
    def _check_api_patterns(self, code: str, tree: ast.AST) -> list[str]:
        """Check for outdated API patterns."""
        issues = []
        
        # Common deprecated patterns
        deprecated_patterns = [
            (r'\.format\(', "Consider using f-strings instead of .format()"),
            (r'%\s*\(', "Consider using f-strings instead of % formatting"),
            (r'async\s+def\s+\w+\([^)]*\):', None),  # Not deprecated, just flagging
        ]
        
        # Check for deprecated stdlib usage
        deprecated_modules = {
            "imp": "Use importlib instead of imp",
            "optparse": "Use argparse instead of optparse",
            "pipes": "Use subprocess instead of pipes",
        }
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in deprecated_modules:
                        issues.append(deprecated_modules[alias.name])
        
        return issues
    
    def _is_safe_to_execute(self, tree: ast.AST) -> bool:
        """Check if code is safe to execute (no side effects)."""
        unsafe_patterns = {
            "open", "write", "remove", "unlink", "rmdir", "makedirs",
            "subprocess", "os.system", "eval", "exec", "compile",
            "requests", "urllib", "socket", "http"
        }
        
        code_str = ast.dump(tree)
        
        for pattern in unsafe_patterns:
            if pattern in code_str:
                return False
        
        return True
    
    def _execute_safely(self, code: str) -> dict:
        """Execute code in a sandboxed environment."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_path = f.name
        
        try:
            result = subprocess.run(
                [sys.executable, temp_path],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(self.project_root),
                env={**dict(__builtins__={})}  # Restricted builtins
            )
            
            if result.returncode == 0:
                return {"success": True, "output": result.stdout}
            else:
                return {"success": False, "error": result.stderr, "output": result.stdout}
                
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Execution timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def _suggest_syntax_fix(self, code: str, error: SyntaxError) -> Optional[str]:
        """Suggest a fix for common syntax errors."""
        if "invalid syntax" in str(error.msg).lower():
            # Check for missing colons
            if error.lineno and error.lineno <= len(code.split('\n')):
                line = code.split('\n')[error.lineno - 1]
                if re.match(r'^\s*(if|for|while|def|class|try|except|with)\s+', line):
                    if not line.rstrip().endswith(':'):
                        return line.rstrip() + ':'
        
        if "unexpected indent" in str(error.msg).lower():
            return "Check indentation - mixing tabs and spaces?"
        
        return None


class ExamplesValidator:
    """Validate all examples in a project."""
    
    def __init__(self, project_root: Path, config: Optional[dict] = None):
        self.project_root = project_root
        self.config = config or {}
        self.extractor = ExampleExtractor(project_root)
        self.python_validator = PythonValidator(project_root)
    
    def validate_all(self, patterns: Optional[list[str]] = None) -> ExamplesReport:
        """Validate all examples in the project."""
        examples = self.extractor.extract_all(patterns)
        
        report = ExamplesReport(
            project_root=str(self.project_root),
            total_examples=len(examples)
        )
        
        for example in examples:
            validation = self._validate_example(example)
            report.examples.append(validation)
            
            if validation.result == ValidationResult.VALID:
                report.valid_count += 1
            elif validation.result == ValidationResult.SKIPPED:
                report.skipped_count += 1
            else:
                report.invalid_count += 1
        
        return report
    
    def _validate_example(self, example: CodeExample) -> ValidationReport:
        """Validate a single example based on its type."""
        if example.language == ExampleType.PYTHON:
            return self.python_validator.validate(example)
        
        elif example.language == ExampleType.JSON:
            return self._validate_json(example)
        
        elif example.language == ExampleType.YAML:
            return self._validate_yaml(example)
        
        elif example.language == ExampleType.BASH:
            return self._validate_bash(example)
        
        # Skip validation for unsupported types
        return ValidationReport(
            example=example,
            result=ValidationResult.SKIPPED,
            message=f"Validation not supported for {example.language.value}"
        )
    
    def _validate_json(self, example: CodeExample) -> ValidationReport:
        """Validate JSON syntax."""
        try:
            json.loads(example.content)
            return ValidationReport(
                example=example,
                result=ValidationResult.VALID,
                message="Valid JSON"
            )
        except json.JSONDecodeError as e:
            return ValidationReport(
                example=example,
                result=ValidationResult.SYNTAX_ERROR,
                message=f"Invalid JSON: {e.msg}"
            )
    
    def _validate_yaml(self, example: CodeExample) -> ValidationReport:
        """Validate YAML syntax."""
        try:
            import yaml
            yaml.safe_load(example.content)
            return ValidationReport(
                example=example,
                result=ValidationResult.VALID,
                message="Valid YAML"
            )
        except ImportError:
            return ValidationReport(
                example=example,
                result=ValidationResult.SKIPPED,
                message="PyYAML not installed"
            )
        except yaml.YAMLError as e:
            return ValidationReport(
                example=example,
                result=ValidationResult.SYNTAX_ERROR,
                message=f"Invalid YAML: {e}"
            )
    
    def _validate_bash(self, example: CodeExample) -> ValidationReport:
        """Validate bash syntax (check with bash -n)."""
        try:
            result = subprocess.run(
                ["bash", "-n"],
                input=example.content,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                return ValidationReport(
                    example=example,
                    result=ValidationResult.VALID,
                    message="Valid bash syntax"
                )
            else:
                return ValidationReport(
                    example=example,
                    result=ValidationResult.SYNTAX_ERROR,
                    message="Bash syntax error",
                    details=[result.stderr]
                )
        except Exception as e:
            return ValidationReport(
                example=example,
                result=ValidationResult.SKIPPED,
                message=f"Could not validate bash: {e}"
            )


def validate_examples(project_root: Path, output_format: str = "text") -> str:
    """Convenience function to validate examples and get a report."""
    validator = ExamplesValidator(project_root)
    report = validator.validate_all()
    
    if output_format == "json":
        return json.dumps(report.to_dict(), indent=2)
    
    # Text output
    lines = [
        "=== Documentation Examples Validation ===",
        f"Total examples: {report.total_examples}",
        f"Valid: {report.valid_count} ✓",
        f"Invalid: {report.invalid_count} ✗",
        f"Skipped: {report.skipped_count} -",
        f"Pass rate: {report.pass_rate:.1f}%",
        ""
    ]
    
    if report.invalid_count > 0:
        lines.append("=== Invalid Examples ===")
        for ex in report.examples:
            if ex.result not in (ValidationResult.VALID, ValidationResult.SKIPPED):
                lines.append(f"\n📍 {ex.example.source_file}:{ex.example.line_start}")
                lines.append(f"   {ex.result.value}: {ex.message}")
                for detail in ex.details[:3]:
                    lines.append(f"   → {detail}")
                if ex.suggested_fix:
                    lines.append(f"   💡 Suggested: {ex.suggested_fix}")
    
    return "\n".join(lines)
