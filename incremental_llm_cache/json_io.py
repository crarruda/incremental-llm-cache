# incremental_llm_cache/json_io.py

import os
import json
import time

def load_json_dict(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json_dict(data, path, *,
                   max_retries=5,
                   base_delay=0.1,
                   backoff_factor=2.0):
    """
    Windows + sync-folder safe JSON save using atomic replace
    with bounded exponential backoff on PermissionError.

    Parameters
    ----------
    max_retries : int
        Maximum number of replace attempts.
    base_delay : float
        Initial sleep time (seconds).
    backoff_factor : float
        Multiplier for exponential backoff.
    """
    
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    tmp_path = path + ".tmp"

    # Write temp file first (safe)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
            sort_keys=True
        )

    delay = base_delay

    for attempt in range(1, max_retries + 1):
        try:
            os.replace(tmp_path, path)
            return  # ✅ success
        except PermissionError as e:
            if attempt == max_retries:
                # Last attempt → rethrow with context
                raise PermissionError(
                    f"Failed to replace JSON cache after {max_retries} attempts: {path}"
                ) from e

            # Backoff before retry
            time.sleep(delay)
            delay *= backoff_factor