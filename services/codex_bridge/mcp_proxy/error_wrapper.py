"""
AICarmine Error Wrapper - Non Invasivo
Integra il nuovo error handling nel codice esistente SENZA modificarlo.
"""

import functools
import logging
import sys
import traceback
from typing import Any, Callable, Dict, Optional, Type
from pathlib import Path

logger = logging.getLogger(__name__)

# Feature flag - attiva/disattiva facilmente
USE_NEW_ERROR_HANDLING = False  # Default: OFF per sicurezza

# Configurazione da environment
import os
USE_NEW_ERROR_HANDLING = os.getenv("AICARMINE_USE_NEW_ERROR_HANDLING", "false").lower() == "true"
RAISE_ON_ERROR = os.getenv("AICARMINE_RAISE_ON_ERROR", "false").lower() == "true"
LOG_STRUCTURED = os.getenv("AICARMINE_LOG_STRUCTURED", "false").lower() == "true"


class ErrorWrapper:
    """
    Wrapper non invasivo per error handling.
    NON modifica il comportamento esistente, aggiunge solo logging e monitoring.
    """
    
    _instance: Optional["ErrorWrapper"] = None
    _errors: list = []
    _max_errors: int = 1000
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def wrap_function(self, func: Callable) -> Callable:
        """
        Avvolge una funzione con error handling.
        La funzione originale NON viene modificata.
        """
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not USE_NEW_ERROR_HANDLING:
                # Modalità legacy: comportamento originale
                return func(*args, **kwargs)
            
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Cattura e logga, MA NON MODIFICA il comportamento
                self._log_error(e, func.__name__, args, kwargs)
                
                if RAISE_ON_ERROR:
                    # Modalità debug: rilancia l'errore originale
                    raise
                
                # Modalità produzione: logga ma NON blocca
                # L'eccezione viene passata al chiamante (comportamento originale)
                raise
        
        return wrapper
    
    def _log_error(self, error: Exception, func_name: str, args: tuple, kwargs: dict):
        """Logga l'errore con contesto."""
        error_data = {
            "timestamp": self._get_timestamp(),
            "function": func_name,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "stack_trace": traceback.format_exc() if LOG_STRUCTURED else None,
        }
        
        if LOG_STRUCTURED:
            # Log strutturato in JSON
            import json
            logger.error(json.dumps(error_data, ensure_ascii=False))
        else:
            logger.error(f"[{func_name}] {type(error).__name__}: {error}")
        
        # Salva in memoria per debugging
        self._errors.append(error_data)
        if len(self._errors) > self._max_errors:
            self._errors = self._errors[-self._max_errors:]
    
    def _get_timestamp(self):
        from datetime import datetime
        return datetime.now().isoformat()
    
    def get_errors(self, limit: int = 50) -> list:
        """Ottiene gli ultimi errori."""
        return self._errors[-limit:]
    
    def clear_errors(self):
        self._errors.clear()


# Singleton
error_wrapper = ErrorWrapper()

# Decorator per uso rapido
def wrap_errors(func):
    """Decorator: avvolge una funzione con error handling."""
    return error_wrapper.wrap_function(func)


# Decorator per classi intere
def wrap_class_errors(cls):
    """Decorator: avvolge TUTTI i metodi di una classe."""
    for attr_name in dir(cls):
        if not attr_name.startswith("_") and callable(getattr(cls, attr_name)):
            original = getattr(cls, attr_name)
            setattr(cls, attr_name, error_wrapper.wrap_function(original))
    return cls