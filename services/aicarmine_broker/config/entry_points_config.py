"""Configurazione threshold evidence contract."""

from dataclasses import dataclass


@dataclass
class EvidenceContractThresholds:
    """Configurazione threshold evidence contract."""
    
    # Threshold ridotti per evitare rejections non necessari
    min_chars: int = 1500  # Ridotto da 2200
    
    # Mantenuto valore attuale (già sufficiente)
    min_path_hits: int = 6
    
    @property
    def min_chars_reduced(self) -> bool:
        """Verifica se threshold è stato ridotto."""
        return self.min_chars < 2200