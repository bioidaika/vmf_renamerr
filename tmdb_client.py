"""
TMDB API v3 Client for VMF Renamerr.
Handles movie search and metadata retrieval with in-memory caching.
"""

import requests
from typing import Any, Optional


class TMDBClient:
    """Client for The Movie Database (TMDB) API v3."""

    BASE_URL = "https://api.themoviedb.org/3"
    IMG_BASE = "https://image.tmdb.org/t/p/w185"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._search_cache: dict[str, list[dict]] = {}
        self._movie_cache: dict[int, dict] = {}

    def _params(self, **extra) -> dict:
        return {"api_key": self.api_key, **extra}

    # ─── Search ──────────────────────────────────────────────────────────────────

    def search(self, query: str, year: Optional[str] = None) -> list[dict[str, Any]]:
        """
        Search for movies on TMDB.
        Returns a normalized list of results with keys:
            tmdb_id, name, year, overview, image_url, type
        """
        cache_key = f"{query}|{year or ''}"
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]

        params = self._params(query=query)
        if year:
            params["year"] = year

        resp = requests.get(
            f"{self.BASE_URL}/search/movie",
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        raw_results = resp.json().get("results", [])

        results = []
        for r in raw_results[:15]:  # Limit to top 15
            poster = r.get("poster_path")
            release_date = r.get("release_date", "") or ""
            results.append({
                "tmdb_id": r.get("id"),
                "tvdb_id": r.get("id"),  # Alias for UI compatibility
                "name": r.get("title", ""),
                "original_name": r.get("original_title", ""),
                "year": release_date[:4] if len(release_date) >= 4 else "",
                "overview": r.get("overview", ""),
                "image_url": f"{self.IMG_BASE}{poster}" if poster else "",
                "type": "movie",
            })

        self._search_cache[cache_key] = results
        return results

    # ─── Movie details ───────────────────────────────────────────────────────────

    def get_movie(self, tmdb_id: int) -> dict[str, Any]:
        """Get movie details including external IDs."""
        if tmdb_id in self._movie_cache:
            return self._movie_cache[tmdb_id]

        resp = requests.get(
            f"{self.BASE_URL}/movie/{tmdb_id}",
            params=self._params(append_to_response="external_ids"),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._movie_cache[tmdb_id] = data
        return data

    # ─── High-level lookup ───────────────────────────────────────────────────────

    def lookup(self, title: str, year: Optional[str] = None,
               force_id: Optional[int] = None) -> dict[str, Any]:
        """
        High-level movie lookup: search by title, pick best match.
        Returns dict with enriched metadata:
          - tmdb_title: official title
          - tmdb_year: release year
          - tmdb_id: TMDB ID
          - tmdb_imdb_id: IMDb ID (if available)
        """
        result: dict[str, Any] = {}

        if force_id:
            movie = self.get_movie(force_id)
        else:
            matches = self.search(title, year=year)
            if not matches:
                return result
            # Pick best match — prefer exact name match
            best = matches[0]
            title_lower = title.lower().strip()
            for m in matches:
                if (m.get("name") or "").lower().strip() == title_lower:
                    best = m
                    break
            movie = self.get_movie(best["tmdb_id"])

        release_date = movie.get("release_date", "") or ""
        result["tmdb_id"] = movie.get("id")
        result["tmdb_title"] = movie.get("title", "")
        result["tmdb_year"] = release_date[:4] if len(release_date) >= 4 else ""

        # IMDb ID
        ext_ids = movie.get("external_ids") or {}
        imdb_id = ext_ids.get("imdb_id", "")
        if imdb_id:
            result["tmdb_imdb_id"] = imdb_id

        return result
