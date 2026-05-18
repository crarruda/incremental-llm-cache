# Assumptions

The incremental cache relies on the following assumptions:

1. **The caller-supplied `compute` is deterministic at the level the cache
   cares about.** If `compute(x)` returns different results across runs for
   the same `x`, the cache will silently serve the earlier result on
   subsequent runs. Non-deterministic computations (e.g. LLM calls with
   temperature > 0) are still cacheable, but the caller accepts that the
   first observed answer is the one retained.

2. **Row keys are stable across runs.** The value extracted from `key_col`
   is the cache's identity. If a row's key changes between runs (e.g.
   because the underlying data was re-hashed with a different scheme), the
   cache treats it as a new entry and re-computes.

3. **JSON is a sufficient on-disk format.** Results returned by `compute`
   must be JSON-serializable. Binary blobs, NumPy arrays, and custom
   objects must be converted by the caller before being returned. JSON was
   chosen over pickle to keep the cache file human-inspectable and to
   avoid Python-version coupling.

4. **Successful entries are stored as-is; errored entries are wrapped.**
   When `compute` returns normally, the value is stored verbatim. When
   `compute` raises, the cache layer writes an envelope of the form
   `{"status": "error", "error": "<message>", "error_type": "<class>"}`.
   This polymorphism is deliberate: it preserves the natural shape of
   successful outputs while making errored entries identifiable for the
   `retry_policy="on_error"` path.

5. **Single-process execution.** The on-disk JSON file is not designed for
   concurrent writers. Two processes running `incremental_cache` against
   the same `cache_path` may overwrite each other's results.

6. **Periodic flush is an acceptable durability tradeoff.** Writes happen
   every `flush_every` rows, not after every row. The caller accepts that
   up to `flush_every - 1` rows may be lost if the process is killed
   abruptly without going through the `finally` block (e.g. `SIGKILL`).
   Ctrl-C and normal exceptions trigger the final save.

7. **The cache file path is owned by the caller.** The cache layer does
   not rotate, archive, or prune the file. As the number of distinct keys
   grows, so does the file size; managing that lifecycle is out of scope.
