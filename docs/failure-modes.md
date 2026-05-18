# Failure Modes

The cache is designed around four recurrent failure modes. Each is handled
explicitly; understanding which ones the layer covers (and which it does
not) is important when integrating the cache into a larger pipeline.

## 1. Process interruption mid-run

A long-running job may be interrupted by a user (Ctrl-C), an out-of-memory
kill, a host reboot, or a parent process timeout.

- **Periodic flush.** Every `flush_every` rows, the in-memory dictionary
  is written to disk via `save_json_dict`. The next run resumes from that
  checkpoint.
- **`try/finally` around the loop.** On any normal exit path, including
  `KeyboardInterrupt` and unhandled exceptions thrown by code outside
  `compute`, the cache is flushed one last time before the exception
  propagates.
- **Loss bound.** Between two checkpoints, up to `flush_every - 1` rows of
  work can be lost. With `flush_every=200` and a 0.5 s per-row computation,
  that is at most ~100 s of lost compute per interruption.
- **What is *not* handled:** abrupt kills that bypass `finally` (such as
  `SIGKILL`, host hardware failure, or a kernel panic) drop the in-memory
  delta entirely. The on-disk file remains valid up to the last successful
  flush.

## 2. Per-row computation errors

Any exception raised inside the caller-supplied `compute` would otherwise
kill the loop and discard the in-memory progress since the last flush.

- **Inner try/except.** The cache wraps the `compute(inp)` call. On
  exception, an error envelope is written to the cache for that key:
  `{"status": "error", "error": str(e), "error_type": type(e).__name__}`.
- **The loop continues.** Subsequent rows are processed normally.
- **Errors are visible.** When `verbose=True`, each failure is reported
  via `tqdm.write(...)` so it does not break the progress bar.
- **Retry path.** A subsequent run with `retry_policy="on_error"` (the
  default) re-processes only the keys whose classification is `"error"`,
  leaving successful entries untouched.

## 3. Schema drift in the cache file

The on-disk format is plain JSON. Over time the shape of cached values may
evolve: bare strings → flat dicts → envelope dicts with `status`.

- **Polymorphic classification.** `classify_cache_entry` accepts both
  legacy and envelope shapes:
  - `None` → `"missing"`
  - dict with `status` field → that status (`"ok"`, `"error"`,
    `"terminal_null"`, etc.)
  - non-dict scalar → `"terminal_null"` (e.g. legacy language codes)
  - dict with truthy `error` field → `"error"` (legacy LLM outputs)
  - dict with empty `result` → `"ok"`
- **Migration is manual.** The cache does not rewrite legacy entries into
  the new envelope shape. If the caller wants uniform shapes, they must
  write a one-off migration script.
- **What is *not* handled:** changes to the *meaning* of an entry. If
  `compute` is rewritten such that its successful output structure
  changes, the cached entries from the previous version are still
  considered `"ok"` and will be served verbatim. A version suffix on the
  cache path (`build_cache_path(..., version=2)`) is the recommended way
  to invalidate after a behavior change.

## 4. Disk write contention

The cache file is written atomically via a `tmp + os.replace` pattern.
On Windows and cloud-sync folders (Dropbox, OneDrive), the destination is
sometimes briefly locked by indexers or sync agents.

- **Exponential backoff.** `save_json_dict` retries the `os.replace` up to
  five times with a doubling delay, raising a contextualized
  `PermissionError` only on persistent failure.
- **Atomic semantics.** Because the temp file is written fully before the
  replace, an interrupted save cannot leave the cache file in a partially
  written state.

## Not covered

The following failure modes are out of scope for this layer:

- **Concurrent writers.** Two processes pointing at the same cache file
  will race; the last flush wins.
- **Schema migrations across versions.** Adding fields to envelopes
  requires a manual rewrite of the cache file.
- **Exponential backoff inside `compute`.** API-level retries (rate
  limits, transient 5xx) belong inside the caller's `compute`, not in the
  cache. The cache only sees the final outcome.
- **Cache rotation.** Files grow unboundedly with the number of distinct
  keys. The caller is responsible for pruning.
