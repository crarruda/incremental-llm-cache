# incremental_llm_cache/cache.py

import os
from tqdm import tqdm
from typing import Callable
from .json_io import load_json_dict, save_json_dict


def incremental_cache(
    *,
    df,
    key_col: str,
    build_input: Callable,
    compute: Callable,
    cache_path: str,
    filter_df: Callable = None,
    force: bool = False,
    bypass: bool = False,
    flush_every: int = 200,
    verbose: bool = True,
    retry_policy: str = "on_error",
) -> dict[str, object]:
    
    """
    Generic incremental cache-backed computation.

    Parameters
    
    df : DataFrame
        Input dataframe.
    key_col : str
        Column used as unique identifier (will be cast to str).
    build_input : callable(row) -> Any
        Builds the input passed to `compute`.
    compute : callable(input) -> Any
        Pure function applied to each input.
    cache_path : str
        Full path to JSON cache file.
    filter_df : callable(df) -> df, optional
        Optional pre-filtering (e.g. only English).
    force : bool
        Ignore existing cache and recompute everything.
    bypass : bool
        Do not reprocess anything, just go with the cache.
    flush_every : int
        Save cache every N new entries.
    retry_policy : str
        - "never"     → never retry cached entries
        - "on_error"  → retry only entries classified as error
        - "always"    → always recompute
    
    """

    cache = {} if force else load_json_dict(cache_path)
    if bypass:
        if verbose:
            print(
                f"Cache bypass enabled — returning {len(cache)} cached entries "
                f"from {cache_path}"
            )
        return cache
    work = df.copy()
    work[key_col] = work[key_col].astype(str)

    if filter_df is not None:
        work = filter_df(work)

    def should_process(key: str) -> bool:
        # FORCE: recompute everything
        if force:
            return True
        
        # Not cached → process
        if key not in cache:
            return True
        
        entry = cache[key]
        classification = classify_cache_entry(entry)

        if retry_policy == "never":
            return False

        if retry_policy == "on_error":
            return classification == "error"

        if retry_policy == "always":
            return True

        return False

    work = work[work[key_col].apply(should_process)]

    new_count = 0

    iterator = (
        tqdm(work.itertuples(index=False), total=len(work))
        if verbose
        else work.itertuples(index=False)
        )

    try:
        for row in iterator:
            key = getattr(row, key_col)
            inp = build_input(row)
            try:
                cache[key] = compute(inp)
            except Exception as e:
                cache[key] = {
                    "status": "error",
                    "error": str(e),
                    "error_type": type(e).__name__
                    }
                if verbose:
                    tqdm.write(f"[error] key={key}: {type(e).__name__}: {e}")
            new_count += 1

            # BATCHED, NON-ATOMIC SAVE (Windows-safe)
            if flush_every and new_count % flush_every == 0:
                save_json_dict(cache, cache_path)

    finally:
        # FINAL SAVE
        save_json_dict(cache, cache_path)

    if verbose:
        print(
            f"Cache updated: {len(cache)} entries total "
            f"({new_count} processed)"
        )

    return cache

def build_cache_path(
    *,
    base_dir: str,
    file_name: str,
    version: int | None = None,
    extension: str = ".json",
    make_dirs: bool = True,
) -> str:
    """
    Build a canonical cache file path.

    Example:
    cache/sentiment_v2.json
    """

    if make_dirs:
        os.makedirs(base_dir, exist_ok=True)

    full_name = file_name
    if version is not None:
        full_name = f"{full_name}_v{version}"

    cache_path = os.path.join(base_dir, f"{full_name}{extension}")
    return cache_path

def classify_cache_entry(entry):
    
    """
    Classifies a cache entry into one of:
    - "missing"
    - "ok"
    - "error"
    - "terminal_null"
    """
    

    # 1. Entry does not exist
    if entry is None:
        return "missing"

    # 2. New-style envelope
    if isinstance(entry, dict) and "status" in entry:
        return entry["status"]

    # 3. Old-style deterministic outputs
    # user_country, language, roberta sentiment
    if not isinstance(entry, dict):
        return "terminal_null"

    # 4. Old-style LLM sentiment / overtourism
    if "error" in entry and entry.get("error"):
        return "error"

    # 5. Valid object but empty result
    if "result" in entry and entry["result"] in (None, [], {}):
        return "ok"

    return "ok"
