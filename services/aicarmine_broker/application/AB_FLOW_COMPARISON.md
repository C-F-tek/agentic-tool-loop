# A/B Flow Comparison - Original vs Refactored

## Overview

This document compares the original `application/` module with the refactored `application2/` module.

## Key Differences

### 1. Dispatcher

| Original | Refactored |
|----------|------------|
| `RegistryToolDispatcher` with `_tools` dict | Same class but with clear logging |
| `_simple` / `_command` helper functions | `_simple_factory` / `_command_factory` |
| No logging | `logger.info/warning/error` calls |
| Cryptic diagnostic rows | Clear error messages |

### 2. Validator

| Original | Refactored |
|----------|------------|
| 2223 lines of complex nested functions | 150 lines of clear validation logic |
| `_list_or_empty`, `_repo_path_is_concrete` helpers | Direct validation checks |
| Nested contract updates | Simple violations list |

### 3. Evidence Builder

| Original | Refactored |
|----------|------------|
| 2407 lines of complex evidence analysis | 150 lines of clear evidence building |
| `_preplanner_semantic_intent_from_orientation` | Direct semantic classification |
| Complex coverage scoring | Simple coverage check |

## Testing Strategy

1. **Unit tests**: Test each refactored module independently
2. **Integration tests**: Test the full A/B flow together
3. **Migration tests**: Verify that the refactored code produces the same results as the original

## Migration Path

1. **Phase 1**: Test refactored code in isolation
2. **Phase 2**: Run A/B comparison tests
3. **Phase 3**: Gradually replace original modules
4. **Phase 4**: Remove original modules after validation