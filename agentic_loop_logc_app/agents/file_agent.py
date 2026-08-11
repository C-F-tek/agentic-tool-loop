"""
File Agent - Advanced agent for filesystem navigation and file relevance analysis.

This agent can:
1. Navigate directory structures
2. Search for files by pattern or content
3. Read file contents
4. Analyze file relevance to a topic
5. Answer natural language queries about files and folders

Example queries:
- "Apri la cartella X e dimmi il file più pertinente ad A"
- "Cerca tutti i file .py che contengono 'database'"
- "Quali file sono nella cartella Y?"
- "Mostra il contenuto del file Z"
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FileResult:
    """Result of a file operation."""
    path: str
    relevance_score: float
    content_preview: str
    metadata: dict = field(default_factory=dict)


@dataclass
class DirectoryListing:
    """Directory listing result."""
    path: str
    files: list[str]
    directories: list[str]
    total_files: int
    total_dirs: int


class FileAgent:
    """Advanced agent for filesystem navigation and file analysis."""
    
    def __init__(self, root_path: str | None = None) -> None:
        """Initialize the agent with a root path."""
        self.root_path = Path(root_path) if root_path else Path.cwd()
        self.max_file_size = 10_000_000  # 10MB limit for reading
        self.search_extensions = [".py", ".md", ".yaml", ".yml", ".json", ".csv", ".sql", ".txt", ".ini", ".conf"]
    
    def navigate(self, path: str) -> DirectoryListing:
        """Navigate to a directory and list its contents."""
        full_path = self._resolve_path(path)
        
        if not full_path.exists():
            raise FileNotFoundError(f"Path not found: {full_path}")
        
        if not full_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {full_path}")
        
        files = []
        dirs = []
        
        for item in full_path.iterdir():
            if item.is_file():
                files.append(item.name)
            elif item.is_dir():
                dirs.append(item.name)
        
        return DirectoryListing(
            path=str(full_path),
            files=sorted(files),
            directories=sorted(dirs),
            total_files=len(files),
            total_dirs=len(dirs),
        )
    
    def search_files(self, pattern: str, path: str | None = None, 
                     extension: str | None = None, 
                     max_results: int = 50) -> list[dict[str, Any]]:
        """Search for files by name pattern."""
        search_path = Path(path) if path else self.root_path
        
        results = []
        for root, dirs, filenames in os.walk(search_path):
            for filename in filenames:
                # Check extension filter
                if extension and not filename.endswith(extension):
                    continue
                
                # Check pattern match
                if pattern.lower() in filename.lower() or re.search(pattern, filename, re.IGNORECASE):
                    full_path = Path(root) / filename
                    results.append({
                        "path": str(full_path),
                        "name": filename,
                        "size": full_path.stat().st_size,
                    })
                    
                    if len(results) >= max_results:
                        return results
        
        return results
    
    def search_content(self, query: str, path: str | None = None,
                       extension: str | None = None,
                       max_results: int = 50) -> list[FileResult]:
        """Search file contents for a query string."""
        search_path = Path(path) if path else self.root_path
        
        results = []
        
        for root, dirs, filenames in os.walk(search_path):
            for filename in filenames:
                # Check extension filter
                if extension and not filename.endswith(extension):
                    continue
                
                full_path = Path(root) / filename
                
                # Skip large files
                if full_path.stat().st_size > self.max_file_size:
                    continue
                
                try:
                    content = full_path.read_text(encoding="utf-8")
                    
                    # Search for query in content
                    if query.lower() in content.lower() or re.search(query, content, re.IGNORECASE):
                        # Calculate relevance score based on frequency
                        count = content.lower().count(query.lower())
                        relevance = min(1.0, count / 10)  # Normalize score
                        
                        # Get preview (surrounding context)
                        idx = content.lower().find(query.lower())
                        if idx >= 0:
                            start = max(0, idx - 100)
                            end = min(len(content), idx + 200)
                            preview = content[start:end].replace("\n", " ")
                        else:
                            preview = content[:200].replace("\n", " ")
                        
                        results.append(FileResult(
                            path=str(full_path),
                            relevance_score=relevance,
                            content_preview=preview,
                            metadata={"matches": count},
                        ))
                        
                        if len(results) >= max_results:
                            return sorted(results, key=lambda x: x.relevance_score, reverse=True)
                
                except (UnicodeDecodeError, OSError):
                    continue
        
        return sorted(results, key=lambda x: x.relevance_score, reverse=True)
    
    def find_relevant_files(self, topic: str, path: str | None = None,
                            extension: str | None = None,
                            max_results: int = 10) -> list[FileResult]:
        """Find files most relevant to a topic based on content analysis."""
        search_path = Path(path) if path else self.root_path
        
        all_results = []
        
        for root, dirs, filenames in os.walk(search_path):
            for filename in filenames:
                # Check extension filter
                if extension and not filename.endswith(extension):
                    continue
                
                full_path = Path(root) / filename
                
                # Skip large files
                if full_path.stat().st_size > self.max_file_size:
                    continue
                
                try:
                    content = full_path.read_text(encoding="utf-8")
                    
                    # Calculate relevance score
                    score = self._calculate_relevance(content, topic, filename)
                    
                    if score > 0:
                        preview = content[:300].replace("\n", " ")
                        all_results.append(FileResult(
                            path=str(full_path),
                            relevance_score=score,
                            content_preview=preview,
                            metadata={"filename_relevance": self._filename_relevance(filename, topic)},
                        ))
                        
                except (UnicodeDecodeError, OSError):
                    continue
        
        sorted_results = sorted(all_results, key=lambda x: x.relevance_score, reverse=True)
        return sorted_results[:max_results]
    
    def read_file(self, file_path: str, line_range: tuple[int, int] | None = None) -> str:
        """Read a file's contents."""
        full_path = self._resolve_path(file_path)
        
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")
        
        try:
            content = full_path.read_text(encoding="utf-8")
            
            if line_range:
                lines = content.split("\n")
                start, end = line_range
                return "\n".join(lines[start-1:end])
            
            return content
            
        except UnicodeDecodeError:
            raise ValueError(f"Cannot decode file: {full_path}")
    
    def analyze_directory(self, path: str, depth: int = 1) -> dict[str, Any]:
        """Analyze directory structure and file distribution."""
        target = self._resolve_path(path)
        
        stats = {
            "path": str(target),
            "total_files": 0,
            "total_dirs": 0,
            "file_types": {},
            "largest_files": [],
            "recent_files": [],
        }
        
        for root, dirs, files in os.walk(target):
            stats["total_dirs"] += len(dirs)
            stats["total_files"] += len(files)
            
            # Track file types
            for f in files:
                ext = Path(f).suffix.lower() or "(no extension)"
                stats["file_types"][ext] = stats["file_types"].get(ext, 0) + 1
            
            # Track largest files
            for f in files:
                fp = Path(root) / f
                try:
                    size = fp.stat().st_size
                    stats["largest_files"].append((str(fp), size))
                    stats["largest_files"].sort(key=lambda x: x[1], reverse=True)
                    stats["largest_files"] = stats["largest_files"][:20]
                except OSError:
                    continue
        
        return stats
    
    def _resolve_path(self, path: str) -> Path:
        """Resolve a relative path against the root."""
        p = Path(path)
        if not p.is_absolute():
            return self.root_path / p
        return p
    
    def _calculate_relevance(self, content: str, topic: str, filename: str) -> float:
        """Calculate relevance score of content to a topic."""
        score = 0.0
        
        # Topic frequency in content
        topic_lower = topic.lower()
        content_lower = content.lower()
        
        # Count topic occurrences
        topic_count = content_lower.count(topic_lower)
        word_count = len(content_lower.split())
        
        if word_count > 0:
            frequency = topic_count / word_count
            score += frequency * 10  # Weight for frequency
        
        # Check for topic in filename
        filename_score = self._filename_relevance(filename, topic)
        score += filename_score * 5
        
        # Check for topic-related keywords
        keywords = self._extract_keywords(topic)
        for kw in keywords:
            if kw.lower() in content_lower:
                score += 2
        
        return min(1.0, score / 10)  # Normalize to 0-1
    
    def _filename_relevance(self, filename: str, topic: str) -> float:
        """Check if filename is relevant to topic."""
        filename_lower = filename.lower()
        topic_lower = topic.lower()
        
        # Direct match
        if topic_lower in filename_lower or filename_lower in topic_lower:
            return 1.0
        
        # Word overlap
        filename_words = set(filename_lower.replace("-", " ").replace("_", " ").split())
        topic_words = set(topic_lower.split())
        
        if not filename_words or not topic_words:
            return 0.0
        
        intersection = filename_words & topic_words
        union = filename_words | topic_words
        
        return len(intersection) / len(union) if union else 0.0
    
    def _extract_keywords(self, topic: str) -> list[str]:
        """Extract keywords from a topic string."""
        # Simple keyword extraction
        words = re.findall(r'\b\w+\b', topic.lower())
        # Remove common stop words
        stop_words = {"the", "a", "an", "and", "or", "but", "is", "are", "of", "in", "to", "for"}
        return [w for w in words if w not in stop_words and len(w) > 2]
    
    def natural_language_query(self, query: str) -> dict[str, Any]:
        """Process a natural language query about files and directories."""
        start_time = time.time()
        
        # Parse query intent
        query_lower = query.lower()
        
        result = {
            "query": query,
            "intent": "unknown",
            "response": "",
            "execution_time_ms": 0,
        }
        
        try:
            # Detect intent and extract parameters - check for relevance first as compound queries may contain navigate keywords
            if "pertinente" in query_lower or "relevant" in query_lower or "file più" in query_lower or "più pertinente" in query_lower:
                # Extract topic and optional path - handle Italian syntax like "dimmi il file più pertinente a RAG"
                # Look for word after "a" or "about" or "related to"
                topic_match = re.search(r'(?:pertinente|relevant|più).*?[aA]\s+(\w+)', query_lower)
                if not topic_match:
                    # Fallback: extract last meaningful word
                    words = query_lower.split()
                    topic = [w for w in words if len(w) > 3][-1] if words else query_lower
                else:
                    topic = topic_match.group(1)
                
                # Also check for path before "pertinente"
                path_match = re.search(r'(?:cartella|folder|directory)\s+(\w+)', query_lower)
                search_path = path_match.group(1) if path_match else None
                
                files = self.find_relevant_files(topic, path=search_path, max_results=5)
                result["intent"] = "find_relevant"
                result["response"] = f"Most relevant files to '{topic}':\n" + "\n".join(f"[{f.relevance_score:.2f}] {f.path}" for f in files[:5])
                
            elif "apri" in query_lower or "cartella" in query_lower or "directory" in query_lower:
                # Extract path from query - handle Italian syntax like "Apri la cartella agents"
                # Try to find word after "cartella" or "folder" or "directory"
                path_match = re.search(r'(?:cartella|folder|directory)\s+(\w+)', query_lower)
                if path_match:
                    path = path_match.group(1)
                else:
                    # Fallback: look for any word after "la"
                    path_match2 = re.search(r'la\s+(\w+)', query_lower)
                    path = path_match2.group(1) if path_match2 else "."
                
                listing = self.navigate(path)
                result["intent"] = "navigate"
                result["response"] = f"Directory: {listing.path}\nFiles ({listing.total_files}): {', '.join(listing.files[:20])}\nDirectories ({listing.total_dirs}): {', '.join(listing.directories[:20])}"
                
            elif "cerca" in query_lower or "search" in query_lower or "trova" in query_lower:
                # Extract search pattern
                pattern_match = re.search(r'(?:cerca|search|trova)\s+(.+)', query_lower)
                if pattern_match:
                    pattern = pattern_match.group(1).strip()
                    files = self.search_files(pattern, max_results=20)
                    result["intent"] = "search"
                    result["response"] = f"Found {len(files)} files matching '{pattern}':\n" + "\n".join(f"- {f['path']}" for f in files[:20])
                
            elif "leggi" in query_lower or "read" in query_lower or "contenuto" in query_lower or "mostra" in query_lower:
                # Extract file path
                path_match = re.search(r'(?:leggi|read|contenuto|mostra)\s+(?:il\s+)?(\w+\.\w+)', query_lower)
                path = path_match.group(1) if path_match else "."
                
                content = self.read_file(path)
                result["intent"] = "read"
                result["response"] = f"Content of {path}:\n{content[:1000]}"
                
            else:
                # Default: treat as relevance search
                topic = query_lower
                files = self.find_relevant_files(topic, max_results=5)
                result["intent"] = "default_search"
                result["response"] = f"Files related to '{query}':\n" + "\n".join(f"[{f.relevance_score:.2f}] {f.path}" for f in files[:5])
                
        except Exception as e:
            logger.error(f"Query processing failed: {e}")
            result["response"] = f"Error processing query: {str(e)}"
        
        result["execution_time_ms"] = int((time.time() - start_time) * 1000)
        return result
