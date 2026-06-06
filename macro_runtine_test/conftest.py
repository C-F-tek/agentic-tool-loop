from __future__ import annotations


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "operator_runtime: operator-only macro tests requiring a live OpenWebUI/3571/3572 runtime",
    )

