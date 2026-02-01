#!/usr/bin/env python3
"""AI-powered documentation improvement engine.

Uses Claude or compatible LLMs to analyze documentation quality,
suggest improvements, and generate enhanced versions.
"""

import os
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Literal


@dataclass
class DocAnalysis:
    """Analysis result for a documentation file."""
    path: str
    quality_score: float  # 0.0 - 1.0
    readability_score: float
    completeness_score: float
    issues: list[dict] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    improved_content: Optional[str] = None
    summary: str = ""


@dataclass 
class AIConfig:
    """AI provider configuration."""
    provider: Literal["anthropic", "openai", "local"] = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.3


class DocImprover:
    """AI-powered documentation improvement engine."""
    
    ANALYSIS_PROMPT = """Analyze this documentation for quality and provide improvement suggestions.

## Documentation Content
```
{content}
```

## Related Code (if available)
```
{code_context}
```

Analyze the documentation and respond in this JSON format:
{{
    "quality_score": 0.0-1.0,
    "readability_score": 0.0-1.0, 
    "completeness_score": 0.0-1.0,
    "issues": [
        {{"type": "missing_example|unclear|outdated|incomplete|wrong", "line": 1, "description": "..."}}
    ],
    "suggestions": [
        "Specific actionable suggestion 1",
        "Specific actionable suggestion 2"
    ],
    "summary": "One paragraph summary of documentation quality"
}}

Be specific and actionable. Focus on:
- Missing examples or use cases
- Unclear explanations
- Missing parameter/return documentation
- Outdated information based on code
- Missing edge cases or error handling docs"""

    IMPROVE_PROMPT = """Improve this documentation based on the analysis and code context.

## Current Documentation
```
{content}
```

## Related Code
```
{code_context}
```

## Issues Found
{issues}

## Improvement Suggestions
{suggestions}

Write an improved version of the documentation that:
1. Fixes all identified issues
2. Implements the suggestions
3. Maintains the original structure where appropriate
4. Adds clear examples where missing
5. Improves readability and clarity

Return ONLY the improved documentation content, no explanations."""

    def __init__(self, config: Optional[AIConfig] = None):
        self.config = config or AIConfig()
        self._client = None
        
    def _get_api_key(self) -> str:
        """Get API key from config or environment."""
        if self.config.api_key:
            return self.config.api_key
            
        if self.config.provider == "anthropic":
            key = os.environ.get("ANTHROPIC_API_KEY")
        elif self.config.provider == "openai":
            key = os.environ.get("OPENAI_API_KEY")
        else:
            return ""
            
        if not key:
            raise ValueError(f"No API key found for {self.config.provider}. "
                           f"Set {self.config.provider.upper()}_API_KEY environment variable.")
        return key
    
    def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic Claude API."""
        try:
            import anthropic
        except ImportError:
            raise ImportError("anthropic package required. Install with: pip install anthropic")
            
        client = anthropic.Anthropic(api_key=self._get_api_key())
        
        response = client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return response.content[0].text
    
    def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API."""
        try:
            import openai
        except ImportError:
            raise ImportError("openai package required. Install with: pip install openai")
            
        client = openai.OpenAI(api_key=self._get_api_key())
        
        response = client.chat.completions.create(
            model=self.config.model or "gpt-4o",
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return response.choices[0].message.content
    
    def _call_local(self, prompt: str) -> str:
        """Call local LLM via OpenAI-compatible API."""
        try:
            import openai
        except ImportError:
            raise ImportError("openai package required for local LLM. Install with: pip install openai")
            
        client = openai.OpenAI(
            api_key=self.config.api_key or "local",
            base_url=self.config.base_url or "http://localhost:11434/v1"
        )
        
        response = client.chat.completions.create(
            model=self.config.model or "llama3",
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return response.choices[0].message.content
    
    def _call_llm(self, prompt: str) -> str:
        """Route to appropriate LLM provider."""
        if self.config.provider == "anthropic":
            return self._call_anthropic(prompt)
        elif self.config.provider == "openai":
            return self._call_openai(prompt)
        elif self.config.provider == "local":
            return self._call_local(prompt)
        else:
            raise ValueError(f"Unknown provider: {self.config.provider}")
    
    def _extract_json(self, text: str) -> dict:
        """Extract JSON from LLM response, handling markdown code blocks."""
        # Try to find JSON in code block
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
        
        # Try to parse directly
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            # Find first { to last }
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
            raise
    
    def analyze(self, doc_path: Path, code_context: str = "") -> DocAnalysis:
        """Analyze a documentation file and return quality assessment."""
        content = doc_path.read_text()
        
        prompt = self.ANALYSIS_PROMPT.format(
            content=content[:8000],  # Limit content size
            code_context=code_context[:4000] if code_context else "No related code provided"
        )
        
        response = self._call_llm(prompt)
        
        try:
            data = self._extract_json(response)
        except (json.JSONDecodeError, ValueError):
            # Fallback for malformed response
            return DocAnalysis(
                path=str(doc_path),
                quality_score=0.5,
                readability_score=0.5,
                completeness_score=0.5,
                issues=[{"type": "unknown", "description": "Could not parse AI response"}],
                suggestions=["Re-run analysis"],
                summary="Analysis failed - could not parse AI response"
            )
        
        return DocAnalysis(
            path=str(doc_path),
            quality_score=data.get("quality_score", 0.5),
            readability_score=data.get("readability_score", 0.5),
            completeness_score=data.get("completeness_score", 0.5),
            issues=data.get("issues", []),
            suggestions=data.get("suggestions", []),
            summary=data.get("summary", "")
        )
    
    def improve(self, doc_path: Path, code_context: str = "", 
                analysis: Optional[DocAnalysis] = None) -> DocAnalysis:
        """Generate improved version of documentation."""
        content = doc_path.read_text()
        
        # Run analysis first if not provided
        if analysis is None:
            analysis = self.analyze(doc_path, code_context)
        
        # Format issues and suggestions
        issues_text = "\n".join([
            f"- [{i.get('type', 'issue')}] Line {i.get('line', '?')}: {i.get('description', '')}"
            for i in analysis.issues
        ]) or "No specific issues found"
        
        suggestions_text = "\n".join([
            f"- {s}" for s in analysis.suggestions
        ]) or "No specific suggestions"
        
        prompt = self.IMPROVE_PROMPT.format(
            content=content[:8000],
            code_context=code_context[:4000] if code_context else "No related code provided",
            issues=issues_text,
            suggestions=suggestions_text
        )
        
        improved_content = self._call_llm(prompt)
        
        # Clean up markdown code blocks if LLM wrapped the response
        if improved_content.strip().startswith("```"):
            lines = improved_content.strip().split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            improved_content = "\n".join(lines)
        
        analysis.improved_content = improved_content
        return analysis
    
    def batch_analyze(self, doc_paths: list[Path], 
                      code_map: Optional[dict[str, str]] = None) -> list[DocAnalysis]:
        """Analyze multiple documentation files."""
        results = []
        code_map = code_map or {}
        
        for doc_path in doc_paths:
            code_context = code_map.get(str(doc_path), "")
            try:
                analysis = self.analyze(doc_path, code_context)
                results.append(analysis)
            except Exception as e:
                results.append(DocAnalysis(
                    path=str(doc_path),
                    quality_score=0.0,
                    readability_score=0.0,
                    completeness_score=0.0,
                    issues=[{"type": "error", "description": str(e)}],
                    summary=f"Analysis failed: {e}"
                ))
        
        return results


def load_ai_config(config: dict) -> AIConfig:
    """Load AI config from living-docs configuration."""
    ai_config = config.get("ai", {})
    return AIConfig(
        provider=ai_config.get("provider", "anthropic"),
        model=ai_config.get("model", "claude-sonnet-4-20250514"),
        api_key=ai_config.get("api_key"),
        base_url=ai_config.get("base_url"),
        max_tokens=ai_config.get("max_tokens", 4096),
        temperature=ai_config.get("temperature", 0.3)
    )
