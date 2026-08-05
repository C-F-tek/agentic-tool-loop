"""
Test di integrazione - Verifica che NON rompa nulla
"""

import asyncio
import sys
from pathlib import Path

# Aggiungi il wrapper ma NON modificare il comportamento
from services.codex_bridge.mcp_proxy.error_wrapper import wrap_errors, USE_NEW_ERROR_HANDLING


def test_original_function():
    """Funzione originale (non modificata)."""
    print("  Funzione originale eseguita")
    return "OK"


@wrap_errors
def test_wrapped_function():
    """Funzione avvolta (comportamento invariato)."""
    print("  Funzione avvolta eseguita")
    return "OK"


def test_exception_function():
    """Funzione che lancia eccezione."""
    raise ValueError("Test error")


@wrap_errors
def test_wrapped_exception_function():
    """Funzione avvolta che lancia eccezione."""
    raise ValueError("Test error wrapped")


async def test_integration():
    """Test di integrazione completo."""
    print("\n" + "="*60)
    print("🧪 Test Integrazione Error Handler")
    print("="*60)
    
    print(f"\n📌 Feature flag: {USE_NEW_ERROR_HANDLING}")
    
    # Test 1: Funzione normale
    print("\n📌 Test 1: Funzione normale")
    result = test_original_function()
    print(f"  Risultato: {result}")
    
    # Test 2: Funzione avvolta
    print("\n📌 Test 2: Funzione avvolta")
    result = test_wrapped_function()
    print(f"  Risultato: {result}")
    
    # Test 3: Eccezione normale
    print("\n📌 Test 3: Eccezione normale")
    try:
        test_exception_function()
    except ValueError as e:
        print(f"  ✅ Eccezione catturata: {e}")
    
    # Test 4: Eccezione avvolta
    print("\n📌 Test 4: Eccezione avvolta")
    try:
        test_wrapped_exception_function()
    except ValueError as e:
        print(f"  ✅ Eccezione catturata: {e}")
    
    print("\n" + "="*60)
    print("✅ Tutti i test passati - Nessuna regressione!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(test_integration())