# Validation

The cache has been validated through repeated reuse across multiple
expensive per-row workflows in a research pipeline on user-generated
content (UGC). Validation has emphasized **resumability** and
**idempotence** over throughput.

## Validation criteria

Four properties have been monitored across runs:

1. **Idempotence**
   Running `incremental_cache` twice with identical arguments produces
   identical on-disk state. The second run performs zero `compute` calls
   when all keys are already classified as `"ok"` or `"terminal_null"`.

2. **Resumability under interruption**
   A run interrupted between flushes can be resumed without re-paying for
   work that survived to the previous checkpoint. Up to `flush_every - 1`
   rows of in-flight work may be lost; everything before that is
   preserved.

3. **Error isolation**
   A `compute` that raises on a subset of inputs does not corrupt the
   entries for inputs it succeeds on. The errored rows are visible as
   `{"status": "error", ...}` envelopes and are the only rows reprocessed
   under `retry_policy="on_error"`.

4. **On-disk durability**
   The cache file remains valid JSON after every save, including saves
   interrupted by Ctrl-C. The atomic `tmp + replace` pattern prevents
   partially written files.

## Categories of interruptions exercised

The cache has been used through the following interruption scenarios:

- Ctrl-C during a long batch
- Process kill via the OS task manager (in-memory delta lost; on-disk
  state preserved up to the last flush)
- Host reboot mid-run
- Network failure inside `compute` (handled as a per-row error, loop
  continues)
- Rate-limit responses from a paid API (handled as a per-row error,
  retried on the next run)
- Cloud-sync indexer briefly locking the cache file during `os.replace`
  (handled by exponential backoff)

## Workflows the cache has backed

The same cache module, with different `compute` callables, has been used
to cache:

- Azure OpenAI structured-extraction calls (function calling)
- Azure Translator requests
- Multilingual sentiment classification (XLM-RoBERTa)
- Language detection
- Google Places enrichment

In each case the cache shape was the same: one JSON file per workflow
version, keyed by a row-level identifier, with successful results stored
verbatim and errors stored as envelopes.

## What validation does *not* cover

- The cache has not been benchmarked against high-throughput
  alternatives (SQLite, LMDB, key-value stores). Throughput optimization
  was not a design goal.
- Concurrent-writer safety has not been validated and is explicitly out
  of scope.
- Behavior under partial filesystem failures (e.g. ENOSPC mid-flush) has
  not been systematically exercised; the design assumes the filesystem
  is healthy.
- Cross-platform behavior on macOS and Linux has had less exposure than
  on Windows, where the atomic-replace + backoff design was originally
  motivated.

## Reproducing the validation

The `examples/basic_usage.py` script exercises a representative set of
the criteria above: cold-cache compute, warm-cache no-op, forced
recompute, an error path with `retry_policy="on_error"`, and bypass mode.
It runs end-to-end without API keys or network access and should produce
stable on-disk state on repeated runs.

A systematic test suite (`tests/`) covering the same criteria is on the
roadmap.
