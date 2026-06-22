"""Test config models and compatibility exports."""

import pytest


class TestConfigModels:
    """Test config.models exports."""

    def test_import_config_models(self) -> None:
        """Test config.models can be imported."""
        from aicarmine_broker.config.models import EvidenceContractThresholds
        thresholds = EvidenceContractThresholds()
        assert thresholds.min_chars >= 1500

    def test_import_compatibility(self) -> None:
        """Test config.compatibility can be imported."""
        from aicarmine_broker.config.compatibility import CODE_PRODUCT_BUILD_STATE_KIND
        assert CODE_PRODUCT_BUILD_STATE_KIND == "code_product"


class TestEntryPointsConfig:
    """Test entry_points_config exports."""

    def test_import_entry_points_config(self) -> None:
        """Test entry_points_config can be imported."""
        from aicarmine_broker.config.entry_points_config import EvidenceContractThresholds
        thresholds = EvidenceContractThresholds()
        assert hasattr(thresholds, 'min_chars')