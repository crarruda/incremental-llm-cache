# examples/basic_usage.py
#
# Example script demonstrating the incremental cache against a fake
# "expensive" function. Runs without API keys, network access, or any
# external dependency beyond pandas and tqdm.

import os
import random
import time

import pandas as pd

from incremental_llm_cache import incremental_cache, build_cache_path


# Setup

CACHE_PATH = build_cache_path(
    base_dir="cache",
    file_name="demo",
    version=1,
)

# Clean start so reruns of the script are reproducible.
if os.path.exists(CACHE_PATH):
    os.remove(CACHE_PATH)

df = pd.DataFrame(
    {
        "id": list(range(1, 21)),
        "text": [
            "apple", "banana", "cherry", "date", "elderberry",
            "fig", "grape", "honeydew", "kiwi", "lemon",
            "mango", "nectarine", "orange", "papaya", "quince",
            "raspberry", "strawberry", "tangerine", "ugli", "watermelon",
        ],
    }
)


# The "expensive" computation
#
# build_input maps a row into the argument that compute will receive.
# compute is the function whose results we want to cache. The sleep
# simulates a slow per-row call (e.g. an LLM or geocoding request).

def build_input(row):
    return row.text


def fake_compute(text):
    time.sleep(random.uniform(0.05, 0.15))
    return text.upper()


# 1. First run — every row is processed and cached

print("\n--- First run (cold cache) ---")
result = incremental_cache(
    df=df,
    key_col="id",
    build_input=build_input,
    compute=fake_compute,
    cache_path=CACHE_PATH,
)
print(f"Cache size: {len(result)}")


# 2. Second run — every row is already cached, nothing is recomputed

print("\n--- Second run (warm cache) ---")
result = incremental_cache(
    df=df,
    key_col="id",
    build_input=build_input,
    compute=fake_compute,
    cache_path=CACHE_PATH,
)
print(f"Cache size: {len(result)}")


# 3. Force run — recompute every row, ignoring the cache

print("\n--- Forced rerun (force=True) ---")
result = incremental_cache(
    df=df,
    key_col="id",
    build_input=build_input,
    compute=fake_compute,
    cache_path=CACHE_PATH,
    force=True,
)
print(f"Cache size: {len(result)}")


# 4. Error path — flaky compute raises on one specific input
#
# The raised exception is captured into an error envelope rather than
# killing the loop. Other rows continue to be processed and saved.

def flaky_compute(text):
    if text == "banana":
        raise RuntimeError("simulated upstream failure")
    time.sleep(random.uniform(0.05, 0.15))
    return text.upper()


os.remove(CACHE_PATH)

print("\n--- Run where one row raises ---")
result = incremental_cache(
    df=df,
    key_col="id",
    build_input=build_input,
    compute=flaky_compute,
    cache_path=CACHE_PATH,
)
banana_key = str(df.loc[df["text"] == "banana", "id"].iloc[0])
print(f"Banana entry after failed run: {result[banana_key]}")


# 5. Retry-on-error — fix the compute, only the banana row reruns
#
# retry_policy="on_error" (the default) reprocesses only entries whose
# classification is "error". The 19 successful rows from step 4 are left
# alone.

print("\n--- Retry run with working compute ---")
result = incremental_cache(
    df=df,
    key_col="id",
    build_input=build_input,
    compute=fake_compute,
    cache_path=CACHE_PATH,
)
print(f"Banana entry after retry: {result[banana_key]}")


# 6. Bypass — skip all processing and return whatever is on disk

print("\n--- Bypass mode ---")
result = incremental_cache(
    df=df,
    key_col="id",
    build_input=build_input,
    compute=fake_compute,
    cache_path=CACHE_PATH,
    bypass=True,
)
print(f"Bypass returned {len(result)} entries")
