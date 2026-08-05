"""
AICarmine Error Monitor - Passivo
Monitora gli errori dell'app esistente senza modificarne il comportamento.
"""

import json
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)


class ErrorMonitor:
    """
    Monitor passivo degli errori.
    NON modifica il comportamento dell'app, solo OSSERVA.
    """
    
    _instance: Optional["ErrorMonitor"] = None
    _errors: List[Dict] = []
    _stats: Dict[str, int] = defaultdict(int)
    _lock = threading.Lock()
    _running = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._start_monitor()
        return cls._instance
    
    def _start_monitor(self):
        """Avvia il monitor in background."""
        if self._running:
            return
        
        self._running = True
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()
    
    def _monitor_loop(self):
        """Loop di monitoraggio."""
        while self._running:
            time.sleep(60)  # Ogni minuto
            self._flush_stats()
    
    def _flush_stats(self):
        """Salva statistiche su file."""
        if not self._stats:
            return
        
        stats_dir = Path("state/error_monitor")
        stats_dir.mkdir(parents=True, exist_ok=True)
        
        with self._lock:
            stats_file = stats_dir / f"stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(stats_file, "w") as f:
                json.dump(dict(self._stats), f, indent=2)
            self._stats.clear()
    
    def record_error(self, error: Exception, context: Optional[Dict] = None):
        """Registra un errore (non modifica il comportamento)."""
        error_type = type(error).__name__
        
        with self._lock:
            self._stats[error_type] += 1
            self._errors.append({
                "timestamp": datetime.now().isoformat(),
                "error_type": error_type,
                "message": str(error),
                "context": context or {}
            })
            
            # Mantieni solo gli ultimi 1000 errori
            if len(self._errors) > 1000:
                self._errors = self._errors[-1000:]
    
    def get_stats(self) -> Dict[str, int]:
        """Ottiene le statistiche correnti."""
        with self._lock:
            return dict(self._stats)
    
    def get_errors(self, limit: int = 50) -> List[Dict]:
        """Ottiene gli ultimi errori."""
        with self._lock:
            return self._errors[-limit:]
    
    def generate_report(self) -> Dict:
        """Genera report degli errori."""
        with self._lock:
            return {
                "total_errors": len(self._errors),
                "stats": dict(self._stats),
                "recent_errors": self._errors[-10:],
                "timestamp": datetime.now().isoformat()
            }


# Singleton
monitor = ErrorMonitor()

# Funzione helper per uso rapido
def record_error(error: Exception, context: Optional[Dict] = None):
    """Registra un errore nel monitor."""
    monitor.record_error(error, context)