"""Quick test for TVDB Client integration."""

import os
import sys

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

from tvdb_client import TVDBClient


def main():
    api_key = os.environ.get("TVDB_API_KEY", "")
    if not api_key:
        print("❌ TVDB_API_KEY not set in .env")
        return

    client = TVDBClient(api_key)

    # Test 1: Search
    print("=" * 60)
    print("Test 1: Search 'Breaking Bad'")
    results = client.search("Breaking Bad", media_type="series")
    if results:
        r = results[0]
        print(f"  ✓ Found: {r.get('name')} | TVDB ID: {r.get('tvdb_id')} | Year: {r.get('year')}")
    else:
        print("  ✗ No results")

    # Test 2: High-level lookup (series with episode)
    print()
    print("Test 2: Lookup 'Breaking Bad' S03E07")
    data = client.lookup("Breaking Bad", season=3, episode=7)
    print(f"  Title: {data.get('tvdb_title')}")
    print(f"  Year:  {data.get('tvdb_year')}")
    print(f"  Ep:    {data.get('tvdb_episode_title')}")
    print(f"  ID:    {data.get('tvdb_id')}")
    if data.get("tvdb_episode_title"):
        print("  ✓ Episode lookup works!")
    else:
        print("  ✗ Episode title not found")

    # Test 3: Movie lookup
    print()
    print("Test 3: Lookup 'Spider-Man: No Way Home' (movie)")
    data = client.lookup("Spider-Man: No Way Home")
    print(f"  Title: {data.get('tvdb_title')}")
    print(f"  Year:  {data.get('tvdb_year')}")
    print(f"  Type:  {data.get('tvdb_type')}")
    print(f"  ID:    {data.get('tvdb_id')}")

    # Test 4: Cache validation (second call should be instant)
    print()
    print("Test 4: Cache test (repeat search)")
    import time
    start = time.time()
    client.search("Breaking Bad", media_type="series")
    elapsed = time.time() - start
    print(f"  Cached response in {elapsed*1000:.0f}ms")
    print(f"  ✓ Cache works!" if elapsed < 0.01 else "  ✗ Cache might not be working")

    print()
    print("=" * 60)
    print("All TVDB tests complete.")


if __name__ == "__main__":
    main()
