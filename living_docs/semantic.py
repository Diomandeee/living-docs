#!/usr/bin/env python3
"""Semantic similarity engine for doc-to-code matching.

Uses embeddings to find related documentation when code changes,
enabling intelligent suggestions and automatic cross-referencing.
"""

import os
import json
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Literal
import math


@dataclass
class Chunk:
    """A chunk of content with its embedding."""
    content: str
    path: str
    chunk_type: Literal["code", "doc"]
    start_line: int
    end_line: int
    hash: str
    embedding: Optional[list[float]] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class SimilarityResult:
    """Result of a similarity search."""
    source: Chunk
    target: Chunk
    score: float  # 0.0 - 1.0
    explanation: str = ""


class EmbeddingProvider:
    """Abstract base for embedding providers."""
    
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError
    
    def embed_single(self, text: str) -> list[float]:
        return self.embed([text])[0]


class AnthropicEmbeddings(EmbeddingProvider):
    """Voyage AI embeddings (Anthropic partner)."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "voyage-code-2"):
        self.api_key = api_key or os.environ.get("VOYAGE_API_KEY")
        self.model = model
        
    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            import voyageai
        except ImportError:
            raise ImportError("voyageai package required. Install with: pip install voyageai")
        
        client = voyageai.Client(api_key=self.api_key)
        result = client.embed(texts, model=self.model, input_type="document")
        return result.embeddings


class OpenAIEmbeddings(EmbeddingProvider):
    """OpenAI embeddings."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "text-embedding-3-small"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        
    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            import openai
        except ImportError:
            raise ImportError("openai package required. Install with: pip install openai")
        
        client = openai.OpenAI(api_key=self.api_key)
        response = client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]


class LocalEmbeddings(EmbeddingProvider):
    """Local embeddings via sentence-transformers or Ollama."""
    
    def __init__(self, model: str = "all-MiniLM-L6-v2", use_ollama: bool = False,
                 ollama_url: str = "http://localhost:11434"):
        self.model = model
        self.use_ollama = use_ollama
        self.ollama_url = ollama_url
        self._st_model = None
        
    def _get_st_model(self):
        if self._st_model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError:
                raise ImportError("sentence-transformers required. Install with: "
                                "pip install sentence-transformers")
            self._st_model = SentenceTransformer(self.model)
        return self._st_model
    
    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.use_ollama:
            return self._embed_ollama(texts)
        
        model = self._get_st_model()
        embeddings = model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()
    
    def _embed_ollama(self, texts: list[str]) -> list[list[float]]:
        import urllib.request
        import json
        
        embeddings = []
        for text in texts:
            data = json.dumps({"model": self.model, "prompt": text}).encode()
            req = urllib.request.Request(
                f"{self.ollama_url}/api/embeddings",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read())
                embeddings.append(result["embedding"])
        return embeddings


class SemanticIndex:
    """Semantic similarity index for code and documentation."""
    
    def __init__(self, provider: EmbeddingProvider, cache_dir: Optional[Path] = None):
        self.provider = provider
        self.cache_dir = cache_dir
        self.chunks: list[Chunk] = []
        self._embeddings_dirty = False
        
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _compute_hash(self, content: str) -> str:
        """Compute content hash for caching."""
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    def _chunk_code(self, path: Path, content: str, 
                    chunk_size: int = 50, overlap: int = 10) -> list[Chunk]:
        """Chunk code file into semantic units."""
        lines = content.split("\n")
        chunks = []
        
        i = 0
        while i < len(lines):
            end = min(i + chunk_size, len(lines))
            chunk_content = "\n".join(lines[i:end])
            
            if chunk_content.strip():
                chunks.append(Chunk(
                    content=chunk_content,
                    path=str(path),
                    chunk_type="code",
                    start_line=i + 1,
                    end_line=end,
                    hash=self._compute_hash(chunk_content),
                    metadata={"language": path.suffix}
                ))
            
            i += chunk_size - overlap
        
        return chunks
    
    def _chunk_doc(self, path: Path, content: str, 
                   chunk_size: int = 100, overlap: int = 20) -> list[Chunk]:
        """Chunk documentation into semantic units."""
        lines = content.split("\n")
        chunks = []
        
        # Try to chunk by headers first
        current_chunk = []
        current_start = 1
        
        for i, line in enumerate(lines):
            if line.startswith("#") and current_chunk:
                # Save current chunk
                chunk_content = "\n".join(current_chunk)
                if chunk_content.strip():
                    chunks.append(Chunk(
                        content=chunk_content,
                        path=str(path),
                        chunk_type="doc",
                        start_line=current_start,
                        end_line=i,
                        hash=self._compute_hash(chunk_content)
                    ))
                current_chunk = [line]
                current_start = i + 1
            else:
                current_chunk.append(line)
                
                # If chunk gets too big, split it
                if len(current_chunk) >= chunk_size:
                    chunk_content = "\n".join(current_chunk[:-overlap])
                    if chunk_content.strip():
                        chunks.append(Chunk(
                            content=chunk_content,
                            path=str(path),
                            chunk_type="doc",
                            start_line=current_start,
                            end_line=i - overlap + 1,
                            hash=self._compute_hash(chunk_content)
                        ))
                    current_chunk = current_chunk[-overlap:]
                    current_start = i - overlap + 2
        
        # Don't forget last chunk
        if current_chunk:
            chunk_content = "\n".join(current_chunk)
            if chunk_content.strip():
                chunks.append(Chunk(
                    content=chunk_content,
                    path=str(path),
                    chunk_type="doc",
                    start_line=current_start,
                    end_line=len(lines),
                    hash=self._compute_hash(chunk_content)
                ))
        
        return chunks
    
    def add_file(self, path: Path, file_type: Optional[Literal["code", "doc"]] = None):
        """Add a file to the index."""
        content = path.read_text()
        
        # Auto-detect type
        if file_type is None:
            if path.suffix in [".md", ".rst", ".txt"]:
                file_type = "doc"
            else:
                file_type = "code"
        
        if file_type == "code":
            new_chunks = self._chunk_code(path, content)
        else:
            new_chunks = self._chunk_doc(path, content)
        
        # Remove old chunks for this path
        self.chunks = [c for c in self.chunks if c.path != str(path)]
        self.chunks.extend(new_chunks)
        self._embeddings_dirty = True
    
    def build_embeddings(self, batch_size: int = 32):
        """Compute embeddings for all chunks without embeddings."""
        chunks_needing_embedding = [c for c in self.chunks if c.embedding is None]
        
        if not chunks_needing_embedding:
            return
        
        # Check cache
        if self.cache_dir:
            cache_file = self.cache_dir / "embeddings.json"
            if cache_file.exists():
                with open(cache_file) as f:
                    cache = json.load(f)
            else:
                cache = {}
            
            # Load from cache where possible
            for chunk in chunks_needing_embedding:
                if chunk.hash in cache:
                    chunk.embedding = cache[chunk.hash]
            
            chunks_needing_embedding = [c for c in chunks_needing_embedding 
                                       if c.embedding is None]
        
        # Compute new embeddings in batches
        for i in range(0, len(chunks_needing_embedding), batch_size):
            batch = chunks_needing_embedding[i:i + batch_size]
            texts = [c.content for c in batch]
            embeddings = self.provider.embed(texts)
            
            for chunk, embedding in zip(batch, embeddings):
                chunk.embedding = embedding
                
                # Cache
                if self.cache_dir:
                    cache[chunk.hash] = embedding
        
        # Save cache
        if self.cache_dir and chunks_needing_embedding:
            with open(self.cache_dir / "embeddings.json", "w") as f:
                json.dump(cache, f)
        
        self._embeddings_dirty = False
    
    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot / (norm_a * norm_b)
    
    def find_related_docs(self, code_path: Path, top_k: int = 5,
                          min_score: float = 0.3) -> list[SimilarityResult]:
        """Find documentation related to a code file."""
        self.build_embeddings()
        
        # Get code chunks for this path
        code_chunks = [c for c in self.chunks 
                      if c.path == str(code_path) and c.chunk_type == "code"]
        doc_chunks = [c for c in self.chunks if c.chunk_type == "doc"]
        
        if not code_chunks or not doc_chunks:
            return []
        
        results = []
        seen_docs = set()  # Avoid duplicate doc paths
        
        for code_chunk in code_chunks:
            for doc_chunk in doc_chunks:
                if doc_chunk.path in seen_docs:
                    continue
                    
                score = self._cosine_similarity(
                    code_chunk.embedding, doc_chunk.embedding
                )
                
                if score >= min_score:
                    results.append(SimilarityResult(
                        source=code_chunk,
                        target=doc_chunk,
                        score=score,
                        explanation=f"Code lines {code_chunk.start_line}-{code_chunk.end_line} "
                                   f"relates to doc lines {doc_chunk.start_line}-{doc_chunk.end_line}"
                    ))
                    seen_docs.add(doc_chunk.path)
        
        # Sort by score and return top-k
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]
    
    def find_docs_needing_update(self, changed_code_paths: list[Path],
                                  threshold: float = 0.5) -> list[SimilarityResult]:
        """Find docs that likely need updating based on changed code."""
        all_results = []
        
        for code_path in changed_code_paths:
            results = self.find_related_docs(code_path, top_k=10, min_score=threshold)
            all_results.extend(results)
        
        # Deduplicate and sort
        seen = set()
        unique_results = []
        for r in sorted(all_results, key=lambda r: r.score, reverse=True):
            if r.target.path not in seen:
                seen.add(r.target.path)
                unique_results.append(r)
        
        return unique_results
    
    def get_code_context_for_doc(self, doc_path: Path, top_k: int = 3,
                                  min_score: float = 0.4) -> str:
        """Get related code context for a documentation file."""
        self.build_embeddings()
        
        doc_chunks = [c for c in self.chunks 
                     if c.path == str(doc_path) and c.chunk_type == "doc"]
        code_chunks = [c for c in self.chunks if c.chunk_type == "code"]
        
        if not doc_chunks or not code_chunks:
            return ""
        
        results = []
        for doc_chunk in doc_chunks:
            for code_chunk in code_chunks:
                score = self._cosine_similarity(
                    doc_chunk.embedding, code_chunk.embedding
                )
                if score >= min_score:
                    results.append((score, code_chunk))
        
        results.sort(key=lambda x: x[0], reverse=True)
        
        # Deduplicate by path and combine
        seen_paths = set()
        context_parts = []
        for score, chunk in results[:top_k * 2]:
            if chunk.path not in seen_paths:
                seen_paths.add(chunk.path)
                context_parts.append(f"# From {chunk.path} (lines {chunk.start_line}-{chunk.end_line})\n{chunk.content}")
                if len(seen_paths) >= top_k:
                    break
        
        return "\n\n".join(context_parts)
    
    def save(self, path: Path):
        """Save index to file."""
        data = {
            "chunks": [
                {
                    "content": c.content,
                    "path": c.path,
                    "chunk_type": c.chunk_type,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "hash": c.hash,
                    "embedding": c.embedding,
                    "metadata": c.metadata
                }
                for c in self.chunks
            ]
        }
        with open(path, "w") as f:
            json.dump(data, f)
    
    def load(self, path: Path):
        """Load index from file."""
        with open(path) as f:
            data = json.load(f)
        
        self.chunks = [
            Chunk(
                content=c["content"],
                path=c["path"],
                chunk_type=c["chunk_type"],
                start_line=c["start_line"],
                end_line=c["end_line"],
                hash=c["hash"],
                embedding=c.get("embedding"),
                metadata=c.get("metadata", {})
            )
            for c in data["chunks"]
        ]


def get_embedding_provider(config: dict) -> EmbeddingProvider:
    """Get embedding provider from config."""
    embedding_config = config.get("embeddings", {})
    provider = embedding_config.get("provider", "local")
    
    if provider == "voyage":
        return AnthropicEmbeddings(
            api_key=embedding_config.get("api_key"),
            model=embedding_config.get("model", "voyage-code-2")
        )
    elif provider == "openai":
        return OpenAIEmbeddings(
            api_key=embedding_config.get("api_key"),
            model=embedding_config.get("model", "text-embedding-3-small")
        )
    else:  # local
        return LocalEmbeddings(
            model=embedding_config.get("model", "all-MiniLM-L6-v2"),
            use_ollama=embedding_config.get("use_ollama", False),
            ollama_url=embedding_config.get("ollama_url", "http://localhost:11434")
        )
