"""
TVDB API v4 Client for VMF Renamerr.
Handles authentication, search, and episode lookup with in-memory caching.
"""

import time
import requests
from typing import Any, Optional


class TVDBClient:
    """Client for TheTVDB API v4."""

    BASE_URL = "https://api4.thetvdb.com/v4"
    TOKEN_LIFETIME = 28 * 24 * 3600  # 28 days (token valid ~1 month)

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._token: str = ""
        self._token_expiry: float = 0
        # Caches
        self._search_cache: dict[str, list[dict]] = {}
        self._series_cache: dict[int, dict] = {}
        self._episodes_cache: dict[str, list[dict]] = {}  # key: "{tvdb_id}_S{season}"

    # ─── Authentication ──────────────────────────────────────────────────────────

    def _ensure_token(self) -> None:
        """Login and cache the JWT token."""
        if self._token and time.time() < self._token_expiry:
            return
        resp = requests.post(
            f"{self.BASE_URL}/login",
            json={"apikey": self.api_key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            raise RuntimeError(f"TVDB login failed: {data}")
        self._token = data["data"]["token"]
        self._token_expiry = time.time() + self.TOKEN_LIFETIME

    def _headers(self) -> dict[str, str]:
        self._ensure_token()
        return {"Authorization": f"Bearer {self._token}"}

    # ─── Search ──────────────────────────────────────────────────────────────────

    def search(self, query: str, media_type: Optional[str] = None) -> list[dict[str, Any]]:
        """
        Search TVDB for series or movies.
        media_type: 'series', 'movie', or None (both).
        Returns list of result dicts with keys: tvdb_id, name, year, type, etc.
        """
        cache_key = f"{query}|{media_type or 'all'}"
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]

        params: dict[str, str] = {"query": query}
        if media_type:
            params["type"] = media_type

        resp = requests.get(
            f"{self.BASE_URL}/search",
            headers=self._headers(),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("data", [])
        self._search_cache[cache_key] = results
        return results

    # ─── Series details ──────────────────────────────────────────────────────────

    def get_series(self, tvdb_id: int) -> dict[str, Any]:
        """Get series extended info (includes remoteIds for IMDb/TMDB)."""
        if tvdb_id in self._series_cache:
            return self._series_cache[tvdb_id]

        resp = requests.get(
            f"{self.BASE_URL}/series/{tvdb_id}/extended",
            headers=self._headers(),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        self._series_cache[tvdb_id] = data
        return data

    # ─── Episodes ────────────────────────────────────────────────────────────────

    def get_series_episodes(
        self, tvdb_id: int, season_type: str = "default", season: int = 0, page: int = 0
    ) -> list[dict[str, Any]]:
        """
        Get episodes for a series.
        season_type: 'default', 'absolute', 'dvd', etc.
        Returns list of episode dicts.
        """
        cache_key = f"{tvdb_id}_S{season}_{season_type}_p{page}"
        if cache_key in self._episodes_cache:
            return self._episodes_cache[cache_key]

        resp = requests.get(
            f"{self.BASE_URL}/series/{tvdb_id}/episodes/{season_type}",
            headers=self._headers(),
            params={"season": season, "page": page} if season else {"page": page},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        episodes = data.get("episodes", [])
        self._episodes_cache[cache_key] = episodes
        return episodes

    def find_episode(
        self, tvdb_id: int, season_num: int, episode_num: int
    ) -> Optional[dict[str, Any]]:
        """Find a specific episode by season and episode number."""
        episodes = self.get_series_episodes(tvdb_id, season=season_num)
        for ep in episodes:
            if ep.get("seasonNumber") == season_num and ep.get("number") == episode_num:
                return ep
        return None

    # ─── Movie details ───────────────────────────────────────────────────────────

    def get_movie(self, tvdb_id: int) -> dict[str, Any]:
        """Get movie extended info."""
        resp = requests.get(
            f"{self.BASE_URL}/movies/{tvdb_id}/extended",
            headers=self._headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("data", {})

    # ─── High-level lookup ───────────────────────────────────────────────────────

    def lookup(self, title: str, season: Optional[int] = None,
               episode: Optional[int] = None, year: Optional[str] = None) -> dict[str, Any]:
        """
        High-level lookup: search by title, pick best match, optionally get episode info.
        Returns dict with enriched metadata:
          - tvdb_title: official title
          - tvdb_year: first aired year
          - tvdb_id: TVDB ID
          - tvdb_episode_title: episode name (if season+episode provided)
          - tvdb_imdb_id: IMDb ID (if available)
          - tvdb_type: 'series' or 'movie'
        """
        result: dict[str, Any] = {}

        # Determine search type
        is_series = season is not None or episode is not None
        search_type = "series" if is_series else None

        matches = self.search(title, media_type=search_type)
        if not matches:
            return result

        # Pick best match — prefer exact name match, then first result
        best = matches[0]
        title_lower = title.lower().strip()
        for m in matches:
            m_name = (m.get("name") or "").lower().strip()
            if m_name == title_lower:
                best = m
                break
            # Also check translations/aliases
            aliases = m.get("aliases", []) or []
            for alias in aliases:
                if isinstance(alias, str) and alias.lower().strip() == title_lower:
                    best = m
                    break

        tvdb_id_str = best.get("tvdb_id", "")
        tvdb_id = int(tvdb_id_str) if tvdb_id_str else 0
        best_type = best.get("type", "")

        result["tvdb_id"] = tvdb_id
        result["tvdb_title"] = best.get("name", "")
        result["tvdb_year"] = best.get("year", "")
        result["tvdb_type"] = best_type

        # Extract IMDb ID from remoteIds if available
        remote_ids = best.get("remote_ids") or []
        for rid in remote_ids:
            rid_id = rid.get("id", "") if isinstance(rid, dict) else ""
            if rid_id.startswith("tt"):
                result["tvdb_imdb_id"] = rid_id
                break

        # Get episode title if this is a series lookup
        if is_series and tvdb_id and season is not None and episode is not None:
            try:
                ep = self.find_episode(tvdb_id, int(season), int(episode))
                if ep:
                    result["tvdb_episode_title"] = ep.get("name", "")
            except Exception:
                pass  # Non-critical, don't fail the whole lookup

        return result
