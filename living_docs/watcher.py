"""File watcher daemon for real-time doc sync."""

import os
import sys
import json
import time
import signal
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False


class DocSyncHandler(FileSystemEventHandler):
    """Handle file changes and trigger doc syncs."""
    
    def __init__(
        self,
        project_root: Path,
        on_change: Callable[[Path], None],
        patterns: list[str] = None,
        debounce_ms: int = 500
    ):
        self.project_root = project_root
        self.on_change = on_change
        self.patterns = patterns or ['*.py', '*.ts', '*.js']
        self.debounce_ms = debounce_ms
        self._last_events: dict[str, float] = {}
        self._file_hashes: dict[str, str] = {}
    
    def _matches_patterns(self, path: Path) -> bool:
        """Check if path matches any watched pattern."""
        for pattern in self.patterns:
            if path.match(pattern):
                return True
        return False
    
    def _should_process(self, path: Path) -> bool:
        """Check if we should process this event (debouncing + hash check)."""
        path_str = str(path)
        now = time.time() * 1000
        
        # Debounce
        if path_str in self._last_events:
            if now - self._last_events[path_str] < self.debounce_ms:
                return False
        
        self._last_events[path_str] = now
        
        # Check if content actually changed
        if path.exists():
            try:
                content_hash = hashlib.md5(path.read_bytes()).hexdigest()
                if self._file_hashes.get(path_str) == content_hash:
                    return False
                self._file_hashes[path_str] = content_hash
            except Exception:
                pass
        
        return True
    
    def on_modified(self, event):
        if event.is_directory:
            return
        
        path = Path(event.src_path)
        if self._matches_patterns(path) and self._should_process(path):
            self.on_change(path)
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        path = Path(event.src_path)
        if self._matches_patterns(path):
            self.on_change(path)


class Daemon:
    """File watcher daemon."""
    
    def __init__(self, project_root: Path, config: dict):
        if not HAS_WATCHDOG:
            raise ImportError("watchdog package required. Install with: pip install watchdog")
        
        self.project_root = project_root
        self.config = config
        self.observer = None
        self.running = False
        self.pid_file = project_root / '.living-docs' / 'daemon.pid'
        self.log_file = project_root / '.living-docs' / 'daemon.log'
    
    def _log(self, message: str):
        """Log a message with timestamp."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_line = f"[{timestamp}] {message}\n"
        
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_file, 'a') as f:
            f.write(log_line)
        
        print(log_line.strip())
    
    def _on_file_change(self, path: Path):
        """Handle a file change."""
        from .sync import SyncEngine
        from .parser import get_parser
        
        self._log(f"Change detected: {path}")
        
        parser = get_parser(path)
        if not parser:
            return
        
        items = parser.parse_file(path)
        if not items:
            return
        
        # Quick sync
        doc_root = self.project_root / self.config.get('docs', ['docs'])[0]
        engine = SyncEngine(self.project_root, doc_root)
        
        doc_path = engine.find_doc_for_code(path)
        if doc_path:
            suggested = engine.generate_doc_content(items, path)
            current = doc_path.read_text() if doc_path.exists() else ""
            
            if engine._content_differs(current, suggested):
                self._log(f"Doc needs update: {doc_path}")
                # For now, just log - could auto-update or queue
    
    def start(self, foreground: bool = False):
        """Start the daemon."""
        if not foreground:
            # Daemonize
            pid = os.fork()
            if pid > 0:
                # Parent - write PID and exit
                self.pid_file.parent.mkdir(parents=True, exist_ok=True)
                self.pid_file.write_text(str(pid))
                print(f"Daemon started with PID {pid}")
                return
        
        # Child/foreground - run the watcher
        self.running = True
        
        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        
        # Write PID if foreground
        if foreground:
            self.pid_file.parent.mkdir(parents=True, exist_ok=True)
            self.pid_file.write_text(str(os.getpid()))
        
        self._log("Starting file watcher...")
        
        # Set up watchdog
        patterns = self.config.get('sources', ['**/*.py', '**/*.ts'])
        handler = DocSyncHandler(
            self.project_root,
            self._on_file_change,
            patterns=[p.split('/')[-1] for p in patterns]  # Just the filename patterns
        )
        
        self.observer = Observer()
        self.observer.schedule(handler, str(self.project_root), recursive=True)
        self.observer.start()
        
        self._log(f"Watching: {self.project_root}")
        self._log(f"Patterns: {patterns}")
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
    
    def stop(self):
        """Stop the daemon."""
        self.running = False
        
        if self.observer:
            self.observer.stop()
            self.observer.join()
        
        if self.pid_file.exists():
            self.pid_file.unlink()
        
        self._log("Daemon stopped")
    
    def _handle_signal(self, signum, frame):
        """Handle termination signals."""
        self._log(f"Received signal {signum}")
        self.stop()
    
    @classmethod
    def status(cls, project_root: Path) -> dict:
        """Check daemon status."""
        pid_file = project_root / '.living-docs' / 'daemon.pid'
        
        if not pid_file.exists():
            return {'running': False, 'pid': None}
        
        try:
            pid = int(pid_file.read_text().strip())
            # Check if process is running
            os.kill(pid, 0)
            return {'running': True, 'pid': pid}
        except (ValueError, ProcessLookupError, PermissionError):
            # PID file exists but process doesn't
            pid_file.unlink(missing_ok=True)
            return {'running': False, 'pid': None}
    
    @classmethod
    def kill(cls, project_root: Path) -> bool:
        """Kill running daemon."""
        status = cls.status(project_root)
        
        if not status['running']:
            return False
        
        try:
            os.kill(status['pid'], signal.SIGTERM)
            return True
        except Exception:
            return False
