# Incremental Cache for Expensive Per-Row Computations

## Overview

Many analytical workflows involve applying an expensive function row by
row across a pandas DataFrame: LLM calls, translation, geocoding,
classification, web scraping. These computations are slow, costly, and
prone to interruption — a single process kill, network blip, or API
rate limit can lose hours of work.

This repository provides a small, **resumable, on-disk cache** for any
per-row computation. It is not tied to LLMs or any specific API; the
cache is a generic contract that wraps any pure function and persists
results between runs.

## Problem Definition

A typical per-row computation suffers from several recurrent problems:

- Process interruptions waste prior compute
- Re-running over the same inputs re-pays the cost
- Retry-on-error policies are reinvented each time
- Cache files drift in schema as the codebase evolves
- Disk writes after every row are too slow; writes only at the end are
  too risky

Most practitioners eventually build this layer, badly. This repository
captures one defensible shape of it.

---

## Design Principles

1. **One row = one cache entry**
   Cache lookups happen at the row-key level. Re-running the cache on
   an unchanged input is a no-op.

2. **Periodic flush, not per-row flush**
   Results are flushed to disk every `flush_every` rows. This balances
   safety against disk I/O.

3. **Separate I/O from computation**
   The caller supplies two callables: `build_input(row)` that prepares
   the function input, and `compute(input)` that runs the expensive
   call. The cache layer never inspects the result.

4. **Explicit retry policy**
   Errored entries are tracked separately from successful ones and can
   be re-tried under an explicit policy (`retry_policy`).

5. **No silent format changes**
   The on-disk cache format is documented JSON, not a pickled object.
   Schema drift between versions is a known concern documented under
   failure modes.

---

## Method Overview

For each row in the input DataFrame:

1. Compute a string row key from `key_col`
2. Check whether the key is already in the on-disk cache
3. If yes, skip (unless `force=True`)
4. If no, call `compute(build_input(row))`
5. Append the result (success or error) to an in-memory dictionary
6. Every `flush_every` rows, write the dictionary to disk

The end state is a single JSON file mapping row key → result.

---

## Installation

Install from source as an editable package:

```bash
pip install -e .
```

This exposes the package under the import name `incremental_llm_cache`
and installs the required runtime dependencies (`pandas`, `tqdm`).
A pinned alternative is provided as `requirements.txt`.

---

## Public API

The repository exposes two public entry points:

```python
from incremental_llm_cache import incremental_cache, build_cache_path

incremental_cache(
    *,
    df: pandas.DataFrame,
    key_col: str,
    build_input: Callable,
    compute: Callable,
    cache_path: str,
    filter_df: Callable | None = None,
    force: bool = False,
    bypass: bool = False,
    flush_every: int = 200,
    verbose: bool = True,
    retry_policy: str = "on_error",
) -> dict[str, object]
```

A helper builds a deterministic cache path from a name and a folder:

```python
cache_path = build_cache_path(name="sentiment_v3", folder="cache")
```

Batch orchestration, multi-process coordination, and key-value store
semantics are intentionally out of scope.

---

## Validation Strategy

The cache has been validated through repeated reuse across multiple
expensive per-row workflows, including Azure OpenAI structured
extraction, Azure Translator, multilingual sentiment classification,
and external geocoding enrichment. Validation has emphasized
resumability and idempotence over throughput.

See `docs/validation.md` for the criteria and the categories of
interruptions that have been exercised.

---

## Known Limitations

- Single-process: the JSON cache file is not designed for concurrent
  writers.
- Cache files grow with the number of distinct keys; rotation is the
  caller's responsibility.
- The retry policy is coarse-grained (per-key) and does not implement
  exponential backoff at the cache layer.
- Schema migrations across cache versions are manual.

---

## Intended Use

This module is intended for analytical or research workflows where:

- A per-row computation is expensive (paid API, model inference,
  scraping)
- The job runs long enough that interruptions are likely
- Auditability of the cached state matters

It is **not** intended as a general-purpose caching library
(`functools.lru_cache` covers in-memory needs better), nor as a
key-value store.

---

## Dependencies

- `pandas>=2.0`
- `tqdm>=4.65`

Both are installed automatically via `pip install -e .`.

---

## License

The code in this repository is released under the MIT License.
See the `LICENSE` file for details.

---

*This repository represents a reusable methodological component
extracted from a broader research pipeline and is published as a
standalone artefact to support transparency and reproducibility.*
