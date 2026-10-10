from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import math
import time
import unicodedata
from datetime import datetime

import numpy as np
import pandas as pd
import requests


def _strip_accents(text: str) -> str:
    """Remove diacritics so 'Núñez' matches 'Nunez'."""
    if not isinstance(text, str):
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


FPL_BASE = "https://fantasy.premierleague.com/api"
VAASTAV_BASE = (
    "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
)

# Seasons available in the vaastav historical archive (inclusive).
# Current season is still taken from the live FPL API for freshness.
HISTORICAL_SEASONS: List[str] = [
    "2016-17", "2017-18", "2018-19", "2019-20",
    "2020-21", "2021-22", "2022-23", "2023-24",
    "2024-25", "2025-26", "2026-27",
]


@dataclass
class WARConfig:
    """Weights for the transparent Value Score."""
    production_weight: float = 0.40   # goal contributions (+ xGI when available)
    volume_weight: float = 0.25       # minutes reliability
    efficiency_weight: float = 0.35   # output relative to fee
    # Cumulative minutes below this are flagged and softly penalised
    low_sample_minutes: int = 900


class FPLClient:
    """Small defensive client for the public FPL API (current season)."""

    def __init__(self, cache_dir: str = "cache", cache_hours: int = 1):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_hours = cache_hours
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "WAR Index / 1.5",
            "Accept": "application/json",
        })

    def _get(self, path: str, cache_name: str):
        cache_file = self.cache_dir / cache_name
        if cache_file.exists():
            age = time.time() - cache_file.stat().st_mtime
            if age < self.cache_hours * 3600:
                return json.loads(cache_file.read_text(encoding="utf-8"))

        response = self.session.get(f"{FPL_BASE}/{path}", timeout=30)
        response.raise_for_status()
        data = response.json()
        cache_file.write_text(json.dumps(data), encoding="utf-8")
        return data

    def bootstrap(self):
        return self._get("bootstrap-static/", "bootstrap-static.json")


class HistoricalClient:
    """
    Loads season-level aggregates from the public vaastav FPL archive.
    https://github.com/vaastav/Fantasy-Premier-League
    """

    def __init__(self, cache_dir: str = "cache", cache_hours: int = 24):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_hours = cache_hours
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "WAR Index / 1.5",
            "Accept": "text/csv",
        })
        self._season_cache: Dict[str, pd.DataFrame] = {}

    def _cache_path(self, season: str) -> Path:
        return self.cache_dir / f"vaastav_{season}_cleaned_players.csv"

    def load_season(self, season: str) -> pd.DataFrame:
        if season in self._season_cache:
            return self._season_cache[season]

        cache_file = self._cache_path(season)
        if cache_file.exists():
            age = time.time() - cache_file.stat().st_mtime
            if age < self.cache_hours * 3600:
                df = pd.read_csv(cache_file)
                self._season_cache[season] = df
                return df

        url = f"{VAASTAV_BASE}/{season}/cleaned_players.csv"
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            cache_file.write_text(response.text, encoding="utf-8")
            df = pd.read_csv(cache_file)
            self._season_cache[season] = df
            return df
        except Exception:
            # Season may not exist or network issue – return empty
            empty = pd.DataFrame()
            self._season_cache[season] = empty
            return empty

    def find_player_season_stats(
        self,
        season: str,
        web_name: str,
        player_name: str,
    ) -> Optional[dict]:
        """
        Return minutes / goals / assists / points for one player in one season.
        Matching is accent-insensitive and tolerates multi-part surnames.
        """
        df = self.load_season(season)
        if df.empty:
            return None

        if "second_name" not in df.columns or "first_name" not in df.columns:
            return None

        # Accent-stripped working columns
        df = df.copy()
        df["_sn"] = df["second_name"].fillna("").map(
            lambda x: _strip_accents(str(x)).lower()
        )
        df["_fn"] = df["first_name"].fillna("").map(
            lambda x: _strip_accents(str(x)).lower()
        )

        web = _strip_accents(web_name).lower().strip()
        full = _strip_accents(player_name).lower().strip()

        # 1. second_name starts with / equals web_name
        mask = df["_sn"] == web
        matches = df[mask]

        # 2. second_name contains web_name (handles "Núñez Ribeiro")
        if matches.empty:
            mask = df["_sn"].str.contains(web, na=False)
            matches = df[mask]

        # 3. Token match on full player name
        if matches.empty:
            tokens = [t for t in full.replace("-", " ").split() if len(t) > 2]
            if tokens:
                mask = pd.Series(True, index=df.index)
                for tok in tokens:
                    mask = mask & (
                        df["_fn"].str.contains(tok, na=False)
                        | df["_sn"].str.contains(tok, na=False)
                    )
                matches = df[mask]

        if matches.empty:
            return None

        row = matches.sort_values("minutes", ascending=False).iloc[0]
        return {
            "minutes": float(row.get("minutes", 0) or 0),
            "goals": float(row.get("goals_scored", 0) or 0),
            "assists": float(row.get("assists", 0) or 0),
            "total_points": float(row.get("total_points", 0) or 0),
        }


def transfer_date_to_first_season(transfer_date: str) -> str:
    """
    Map a transfer date (YYYY-MM-DD) to the first Premier League season
    that should be counted.
    July–June window: a transfer on 2022-08-26 belongs to 2022-23.
    """
    try:
        dt = datetime.strptime(transfer_date[:10], "%Y-%m-%d")
    except ValueError:
        return "2016-17"

    # Season runs roughly Aug Y → May Y+1.  Transfers from July onwards
    # belong to the new season Y-(Y+1).
    if dt.month >= 7:
        start = dt.year
    else:
        start = dt.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


# Curated sample of notable Premier League permanent transfers.
# Fees are approximate reported / guaranteed figures for illustration.
# This is the "transfer database" seed for Era 1.
SAMPLE_TRANSFERS: List[dict] = [
    {
        "web_name": "Rogers",
        "player_name": "Morgan Rogers",
        "from_club": "Middlesbrough",
        "to_club": "Aston Villa",
        "fee_guaranteed_m": 117.0,
        "fee_max_m": 117.0,
        "fee_reported_m": 117.0,
        "fee_confidence": "Medium",
        "transfer_date": "2024-07-01",
        "position_hint": "MID",
        "notes": "Illustrative high-fee benchmark used in project definition.",
    },
    {
        "web_name": "Isak",
        "player_name": "Alexander Isak",
        "from_club": "Real Sociedad",
        "to_club": "Newcastle",
        "fee_guaranteed_m": 63.0,
        "fee_max_m": 70.0,
        "fee_reported_m": 63.0,
        "fee_confidence": "High",
        "transfer_date": "2022-08-26",
        "position_hint": "FWD",
        "notes": "",
    },
    {
        "web_name": "Haaland",
        "player_name": "Erling Haaland",
        "from_club": "Borussia Dortmund",
        "to_club": "Man City",
        "fee_guaranteed_m": 51.2,
        "fee_max_m": 60.0,
        "fee_reported_m": 51.2,
        "fee_confidence": "High",
        "transfer_date": "2022-07-01",
        "position_hint": "FWD",
        "notes": "",
    },
    {
        "web_name": "Vuskovic",
        "player_name": "Luka Vuskovic",
        "from_club": "Tottenham",
        "to_club": "Brighton",
        "fee_guaranteed_m": 46.0,
        "fee_max_m": 50.0,
        "fee_reported_m": 46.0,
        "fee_confidence": "High",
        "transfer_date": "2017-07-14",
        "position_hint": "DEF",
        "notes": "Long-term bargain reference.",
    },
    {
        "web_name": "Palmer",
        "player_name": "Cole Palmer",
        "from_club": "Man City",
        "to_club": "Chelsea",
        "fee_guaranteed_m": 42.5,
        "fee_max_m": 45.0,
        "fee_reported_m": 42.5,
        "fee_confidence": "High",
        "transfer_date": "2023-09-01",
        "position_hint": "MID",
        "notes": "",
    },
    {
        "web_name": "Rice",
        "player_name": "Declan Rice",
        "from_club": "West Ham",
        "to_club": "Arsenal",
        "fee_guaranteed_m": 105.0,
        "fee_max_m": 105.0,
        "fee_reported_m": 105.0,
        "fee_confidence": "High",
        "transfer_date": "2023-07-15",
        "position_hint": "MID",
        "notes": "",
    },
    {
        "web_name": "Caicedo",
        "player_name": "Moises Caicedo",
        "from_club": "Brighton",
        "to_club": "Chelsea",
        "fee_guaranteed_m": 100.0,
        "fee_max_m": 115.0,
        "fee_reported_m": 100.0,
        "fee_confidence": "High",
        "transfer_date": "2023-08-14",
        "position_hint": "MID",
        "notes": "",
    },
    {
        "web_name": "Mudryk",
        "player_name": "Mykhailo Mudryk",
        "from_club": "Shakhtar",
        "to_club": "Chelsea",
        "fee_guaranteed_m": 62.0,
        "fee_max_m": 89.0,
        "fee_reported_m": 62.0,
        "fee_confidence": "Medium",
        "transfer_date": "2023-01-15",
        "position_hint": "MID",
        "notes": "",
    },
    {
        "web_name": "Nunez",
        "player_name": "Darwin Nunez",
        "from_club": "Benfica",
        "to_club": "Liverpool",
        "fee_guaranteed_m": 64.0,
        "fee_max_m": 85.0,
        "fee_reported_m": 64.0,
        "fee_confidence": "High",
        "transfer_date": "2022-07-01",
        "position_hint": "FWD",
        "notes": "",
    },
    {
        "web_name": "Gakpo",
        "player_name": "Cody Gakpo",
        "from_club": "PSV",
        "to_club": "Liverpool",
        "fee_guaranteed_m": 37.0,
        "fee_max_m": 44.0,
        "fee_reported_m": 37.0,
        "fee_confidence": "High",
        "transfer_date": "2023-01-01",
        "position_hint": "FWD",
        "notes": "",
    },
    {
        "web_name": "Wirtz",
        "player_name": "Florian Wirtz",
        "from_club": "Bayer Leverkusen",
        "to_club": "Liverpool",
        "fee_guaranteed_m": 100.0,
        "fee_max_m": 116.0,
        "fee_reported_m": 100.0,
        "fee_confidence": "Medium",
        "transfer_date": "2025-06-01",
        "position_hint": "MID",
        "notes": "Recent high-profile arrival – limited sample.",
    },
    {
        "web_name": "Gyokeres",
        "player_name": "Viktor Gyokeres",
        "from_club": "Sporting CP",
        "to_club": "Arsenal",
        "fee_guaranteed_m": 63.5,
        "fee_max_m": 72.0,
        "fee_reported_m": 63.5,
        "fee_confidence": "Medium",
        "transfer_date": "2025-07-01",
        "position_hint": "FWD",
        "notes": "Recent arrival – limited sample.",
    },
    {
        "web_name": "Eze",
        "player_name": "Eberechi Eze",
        "from_club": "Crystal Palace",
        "to_club": "Arsenal",
        "fee_guaranteed_m": 60.0,
        "fee_max_m": 68.0,
        "fee_reported_m": 60.0,
        "fee_confidence": "High",
        "transfer_date": "2025-07-01",
        "position_hint": "MID",
        "notes": "",
    },
    {
        "web_name": "Mbeumo",
        "player_name": "Bryan Mbeumo",
        "from_club": "Brentford",
        "to_club": "Man Utd",
        "fee_guaranteed_m": 65.0,
        "fee_max_m": 71.0,
        "fee_reported_m": 65.0,
        "fee_confidence": "Medium",
        "transfer_date": "2025-07-01",
        "position_hint": "FWD",
        "notes": "",
    },
    {
        "web_name": "Cunha",
        "player_name": "Matheus Cunha",
        "from_club": "Wolves",
        "to_club": "Man Utd",
        "fee_guaranteed_m": 62.5,
        "fee_max_m": 62.5,
        "fee_reported_m": 62.5,
        "fee_confidence": "High",
        "transfer_date": "2025-06-01",
        "position_hint": "FWD",
        "notes": "",
    },
    # --- Summer 2026 permanent arrivals into PL (from ESPN grading article) ---
    {
        "web_name": "Enzo",
        "player_name": "Enzo Fernández",
        "from_club": "Chelsea",
        "to_club": "Man City",
        "fee_guaranteed_m": 125.0,
        "fee_max_m": 125.0,
        "fee_reported_m": 125.0,
        "fee_confidence": "High",
        "transfer_date": "2026-09-01",
        "position_hint": "MID",
        "notes": "Joint-British record fee. Source: ESPN summer grades.",
    },
    {
        "web_name": "Barcola",
        "player_name": "Bradley Barcola",
        "from_club": "PSG",
        "to_club": "Liverpool",
        "fee_guaranteed_m": 106.0,
        "fee_max_m": 122.0,
        "fee_reported_m": 106.0,
        "fee_confidence": "Medium",
        "transfer_date": "2026-08-31",
        "position_hint": "MID",
        "notes": "€123m base; add-ons reported. Source: ESPN summer grades.",
    },
    {
        "web_name": "Bouaddi",
        "player_name": "Ayyoub Bouaddi",
        "from_club": "Lille",
        "to_club": "Man City",
        "fee_guaranteed_m": 81.0,
        "fee_max_m": 85.0,
        "fee_reported_m": 81.0,
        "fee_confidence": "Medium",
        "transfer_date": "2026-08-26",
        "position_hint": "MID",
        "notes": "€95m + add-ons. Source: ESPN summer grades.",
    },
    {
        "web_name": "Sávio",
        "player_name": "Savio",
        "from_club": "Man City",
        "to_club": "Tottenham",
        "fee_guaranteed_m": 75.0,
        "fee_max_m": 85.0,
        "fee_reported_m": 75.0,
        "fee_confidence": "Medium",
        "transfer_date": "2026-08-25",
        "position_hint": "MID",
        "notes": "Source: ESPN summer grades.",
    },
    {
        "web_name": "Baleba",
        "player_name": "Carlos Baleba",
        "from_club": "Brighton",
        "to_club": "Man Utd",
        "fee_guaranteed_m": 65.0,
        "fee_max_m": 70.0,
        "fee_reported_m": 65.0,
        "fee_confidence": "High",
        "transfer_date": "2026-08-25",
        "position_hint": "MID",
        "notes": "Source: ESPN summer grades.",
    },
    {
        "web_name": "Ndiaye",
        "player_name": "Iliman Ndiaye",
        "from_club": "Everton",
        "to_club": "Man City",
        "fee_guaranteed_m": 60.0,
        "fee_max_m": 60.0,
        "fee_reported_m": 60.0,
        "fee_confidence": "High",
        "transfer_date": "2026-09-01",
        "position_hint": "MID",
        "notes": "Source: ESPN summer grades.",
    },
    {
        "web_name": "Konsa",
        "player_name": "Ezri Konsa",
        "from_club": "Aston Villa",
        "to_club": "Arsenal",
        "fee_guaranteed_m": 51.0,
        "fee_max_m": 55.0,
        "fee_reported_m": 51.0,
        "fee_confidence": "High",
        "transfer_date": "2026-08-21",
        "position_hint": "DEF",
        "notes": "Source: ESPN summer grades.",
    },
    {
        "web_name": "Fernandez-Pardo",
        "player_name": "Matias Fernandez-Pardo",
        "from_club": "Lille",
        "to_club": "Newcastle",
        "fee_guaranteed_m": 51.0,
        "fee_max_m": 55.0,
        "fee_reported_m": 51.0,
        "fee_confidence": "Medium",
        "transfer_date": "2026-09-01",
        "position_hint": "FWD",
        "notes": "€60m. Source: ESPN summer grades.",
    },
    {
        "web_name": "N.Gonzalez",
        "player_name": "Nico González",
        "from_club": "Man City",
        "to_club": "Newcastle",
        "fee_guaranteed_m": 48.0,
        "fee_max_m": 52.0,
        "fee_reported_m": 48.0,
        "fee_confidence": "High",
        "transfer_date": "2026-08-26",
        "position_hint": "MID",
        "notes": "Source: ESPN summer grades.",
    },
    {
        "web_name": "N.Jackson",
        "player_name": "Nicolas Jackson",
        "from_club": "Chelsea",
        "to_club": "Aston Villa",
        "fee_guaranteed_m": 47.5,
        "fee_max_m": 65.0,
        "fee_reported_m": 47.5,
        "fee_confidence": "Medium",
        "transfer_date": "2026-08-28",
        "position_hint": "FWD",
        "notes": "Add-ons up to £65m. Source: ESPN summer grades.",
    },
    {
        "web_name": "Mbaye",
        "player_name": "Ibrahim Mbaye",
        "from_club": "PSG",
        "to_club": "Aston Villa",
        "fee_guaranteed_m": 47.0,
        "fee_max_m": 47.0,
        "fee_reported_m": 47.0,
        "fee_confidence": "Medium",
        "transfer_date": "2026-09-01",
        "position_hint": "MID",
        "notes": "€55m. Source: ESPN summer grades.",
    },
    {
        "web_name": "Delap",
        "player_name": "Liam Delap",
        "from_club": "Chelsea",
        "to_club": "Nott'm Forest",
        "fee_guaranteed_m": 45.0,
        "fee_max_m": 50.0,
        "fee_reported_m": 45.0,
        "fee_confidence": "High",
        "transfer_date": "2026-08-27",
        "position_hint": "FWD",
        "notes": "Source: ESPN summer grades.",
    },
    {
        "web_name": "Allan",
        "player_name": "Allan Elias",
        "from_club": "Palmeiras",
        "to_club": "Man City",
        "fee_guaranteed_m": 32.0,
        "fee_max_m": 34.0,
        "fee_reported_m": 32.0,
        "fee_confidence": "Medium",
        "transfer_date": "2026-08-31",
        "position_hint": "MID",
        "notes": "€37.5m. Source: ESPN summer grades.",
    },
    {
        "web_name": "Suzuki",
        "player_name": "Zion Suzuki",
        "from_club": "Parma",
        "to_club": "Aston Villa",
        "fee_guaranteed_m": 26.0,
        "fee_max_m": 26.0,
        "fee_reported_m": 26.0,
        "fee_confidence": "Medium",
        "transfer_date": "2026-08-20",
        "position_hint": "GKP",
        "notes": "€30m. Source: ESPN summer grades.",
    },
    {
        "web_name": "Harwood-Bellis",
        "player_name": "Taylor Harwood-Bellis",
        "from_club": "Southampton",
        "to_club": "Aston Villa",
        "fee_guaranteed_m": 25.0,
        "fee_max_m": 30.0,
        "fee_reported_m": 25.0,
        "fee_confidence": "High",
        "transfer_date": "2026-09-01",
        "position_hint": "DEF",
        "notes": "Source: ESPN summer grades.",
    },
    {
        "web_name": "Martinez",
        "player_name": "Emiliano Martínez",
        "from_club": "Aston Villa",
        "to_club": "Chelsea",
        "fee_guaranteed_m": 7.5,
        "fee_max_m": 7.5,
        "fee_reported_m": 7.5,
        "fee_confidence": "High",
        "transfer_date": "2026-08-28",
        "position_hint": "GKP",
        "notes": "Source: ESPN summer grades.",
    },
    {
        "web_name": "Tosin",
        "player_name": "Tosin Adarabioyo",
        "from_club": "Chelsea",
        "to_club": "Tottenham",
        "fee_guaranteed_m": 7.0,
        "fee_max_m": 7.0,
        "fee_reported_m": 7.0,
        "fee_confidence": "High",
        "transfer_date": "2026-09-01",
        "position_hint": "DEF",
        "notes": "Source: ESPN summer grades.",
    },
]


class WARIndexEngine:
    """
    Calculates a transparent Weighted Average Rating (WAR) / Value Score
    for Premier League transfers.

    Phase 1 (history):
    - Performance is measured as the cumulative Premier League output
      delivered since the transfer date (not just the current season).
    - Historical seasons come from the public vaastav archive.
    - The current season is taken from the live FPL API (freshest data).
    - Fees remain the curated SAMPLE_TRANSFERS list.
    """

    def __init__(
        self,
        client: Optional[FPLClient] = None,
        hist_client: Optional[HistoricalClient] = None,
        config: Optional[WARConfig] = None,
    ):
        self.client = client or FPLClient()
        self.hist = hist_client or HistoricalClient()
        self.config = config or WARConfig()
        self.bootstrap_data = None

    def load(self):
        self.bootstrap_data = self.client.bootstrap()
        return self

    @staticmethod
    def _safe_float(value, default=0.0):
        try:
            if value is None or value == "":
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _minmax(series: pd.Series, reverse: bool = False) -> pd.Series:
        s = pd.to_numeric(series, errors="coerce").fillna(0.0)
        lo, hi = s.min(), s.max()
        if math.isclose(lo, hi):
            out = pd.Series(50.0, index=s.index)
        else:
            out = 100.0 * (s - lo) / (hi - lo)
        return 100.0 - out if reverse else out

    def _players_table(self) -> pd.DataFrame:
        b = self.bootstrap_data
        teams = pd.DataFrame(b["teams"])
        players = pd.DataFrame(b["elements"])

        team_map = teams.set_index("id")["name"].to_dict()
        short_map = teams.set_index("id")["short_name"].to_dict()
        position_map = {
            x["id"]: x["singular_name_short"]
            for x in b.get("element_types", [])
        }

        players["team_name"] = players["team"].map(team_map)
        players["team_short"] = players["team"].map(short_map)
        players["position"] = players["element_type"].map(position_map)
        players["price"] = players["now_cost"] / 10.0
        players["ownership"] = pd.to_numeric(
            players["selected_by_percent"], errors="coerce"
        ).fillna(0.0)

        return players

    def _cumulative_since_transfer(
        self,
        web_name: str,
        player_name: str,
        transfer_date: str,
        live_minutes: float,
        live_goals: float,
        live_assists: float,
        live_points: float,
    ) -> Tuple[float, float, float, float, int]:
        """
        Sum minutes / goals / assists / points from the first relevant
        historical season onwards.

        If live FPL data is available we treat it as the freshest
        current-season numbers and skip the last historical season
        (avoids double-counting).  If the player is absent from the
        live snapshot we keep every historical season.

        Returns: (minutes, goals, assists, points, seasons_counted)
        """
        first_season = transfer_date_to_first_season(transfer_date)

        try:
            start_idx = HISTORICAL_SEASONS.index(first_season)
        except ValueError:
            start_idx = 0

        has_live = live_minutes > 0 or live_goals > 0 or live_assists > 0

        if has_live:
            # Live data replaces the most recent historical season
            hist_seasons = HISTORICAL_SEASONS[start_idx:-1]
        else:
            hist_seasons = HISTORICAL_SEASONS[start_idx:]

        total_minutes = 0.0
        total_goals = 0.0
        total_assists = 0.0
        total_points = 0.0
        seasons_found = 0

        for season in hist_seasons:
            stats = self.hist.find_player_season_stats(
                season, web_name, player_name
            )
            if stats is None:
                continue
            total_minutes += stats["minutes"]
            total_goals += stats["goals"]
            total_assists += stats["assists"]
            total_points += stats["total_points"]
            seasons_found += 1

        if has_live:
            total_minutes += live_minutes
            total_goals += live_goals
            total_assists += live_assists
            total_points += live_points
            seasons_found += 1

        return (
            total_minutes,
            total_goals,
            total_assists,
            total_points,
            seasons_found,
        )

    def calculate(self, min_minutes: int = 90) -> pd.DataFrame:
        """
        Match sample transfers to cumulative Premier League performance
        since the transfer and produce Value Scores.
        """
        if self.bootstrap_data is None:
            self.load()

        players = self._players_table()
        rows = []

        for t in SAMPLE_TRANSFERS:
            # Live match (accent-insensitive)
            web_clean = _strip_accents(t["web_name"]).lower()
            matches = players[
                players["web_name"].fillna("").map(
                    lambda x: _strip_accents(str(x)).lower()
                ) == web_clean
            ]
            if matches.empty:
                matches = players[
                    players["second_name"].fillna("").map(
                        lambda x: _strip_accents(str(x)).lower()
                    ).str.contains(web_clean, na=False)
                ]

            if not matches.empty:
                p = matches.iloc[0]
                live_minutes = self._safe_float(p.get("minutes"), 0)
                live_goals = self._safe_float(p.get("goals_scored"), 0)
                live_assists = self._safe_float(p.get("assists"), 0)
                live_points = self._safe_float(p.get("total_points"), 0)
                live_xg = self._safe_float(p.get("expected_goals"), 0)
                live_xa = self._safe_float(p.get("expected_assists"), 0)
                live_starts = self._safe_float(p.get("starts"), 0)
                current_club = p["team_short"]
                position = p["position"]
                price_now = self._safe_float(p.get("price"), 0)
                ownership = self._safe_float(p.get("ownership"), 0)
            else:
                # Player not in current FPL snapshot – pure historical path
                live_minutes = live_goals = live_assists = live_points = 0.0
                live_xg = live_xa = live_starts = 0.0
                current_club = t["to_club"][:3].upper()
                position = t.get("position_hint", "")
                price_now = 0.0
                ownership = 0.0

            # Cumulative since transfer
            minutes, goals, assists, total_points, seasons_counted = (
                self._cumulative_since_transfer(
                    t["web_name"],
                    t["player_name"],
                    t["transfer_date"],
                    live_minutes,
                    live_goals,
                    live_assists,
                    live_points,
                )
            )

            # Keep zero-minute recent signings in the table so they remain visible.
            # They will be flagged as low sample and soft-penalised.

            low_sample = minutes < self.config.low_sample_minutes

            fee = t["fee_guaranteed_m"]
            fee_max = t["fee_max_m"]

            per_90 = minutes / 90.0 if minutes > 0 else 0.0
            goals_per_90 = (goals / per_90) if per_90 > 0 else 0.0
            assists_per_90 = (assists / per_90) if per_90 > 0 else 0.0
            goal_contrib = goals + assists
            goal_contrib_per_90 = (goal_contrib / per_90) if per_90 > 0 else 0.0

            # xGI only available live; scale by current-season minute share
            if minutes > 0 and live_minutes > 0:
                live_share = live_minutes / minutes
                xgi = (live_xg + live_xa) * live_share
            else:
                xgi = 0.0
            xgi_per_90 = (xgi / per_90) if per_90 > 0 else 0.0

            pounds_per_90 = (fee * 1_000_000) / per_90 if per_90 > 0 else None
            pounds_per_goal = (fee * 1_000_000) / goals if goals > 0 else None
            pounds_per_contrib = (
                (fee * 1_000_000) / goal_contrib if goal_contrib > 0 else None
            )

            rows.append({
                "web_name": t["web_name"],
                "player_name": t["player_name"],
                "from_club": t["from_club"],
                "to_club": t["to_club"],
                "current_club": current_club,
                "position": position,
                "fee_guaranteed_m": fee,
                "fee_max_m": fee_max,
                "fee_reported_m": t["fee_reported_m"],
                "fee_confidence": t["fee_confidence"],
                "transfer_date": t["transfer_date"],
                "notes": t.get("notes", ""),
                "minutes": minutes,
                "starts": live_starts,
                "goals": goals,
                "assists": assists,
                "goal_contrib": goal_contrib,
                "xg": live_xg,
                "xa": live_xa,
                "xgi": xgi,
                "total_points": total_points,
                "goals_per_90": goals_per_90,
                "assists_per_90": assists_per_90,
                "goal_contrib_per_90": goal_contrib_per_90,
                "xgi_per_90": xgi_per_90,
                "pounds_per_90": pounds_per_90,
                "pounds_per_goal": pounds_per_goal,
                "pounds_per_contrib": pounds_per_contrib,
                "low_sample": low_sample,
                "price_now": price_now,
                "ownership": ownership,
                "seasons_counted": seasons_counted,
                "live_minutes": live_minutes,
                "live_goals": live_goals,
                "live_assists": live_assists,
            })

        df = pd.DataFrame(rows)
        if df.empty:
            return df

        # ------------------------------------------------------------------
        # 1. TRANSFER VALUE SCORE
        #    Cost base = original transfer fee
        #    Performance = cumulative PL output since the transfer
        # ------------------------------------------------------------------
        df["production_raw"] = (
            df["goal_contrib_per_90"] * 0.6 + df["xgi_per_90"] * 0.4
        )
        df["production_score"] = self._minmax(df["production_raw"])
        df["volume_score"] = self._minmax(df["minutes"])

        inv_cost = 1.0 / df["pounds_per_contrib"].replace(0, np.nan)
        inv_cost = inv_cost.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        df["efficiency_score"] = self._minmax(inv_cost)

        c = self.config
        df["value_score"] = (
            df["production_score"] * c.production_weight
            + df["volume_score"] * c.volume_weight
            + df["efficiency_score"] * c.efficiency_weight
        )
        df.loc[df["low_sample"], "value_score"] = (
            df.loc[df["low_sample"], "value_score"] * 0.7
        )
        df["value_label"] = np.select(
            [df["value_score"] >= 70, df["value_score"] >= 40],
            ["Good value", "Fair value"],
            default="Poor value",
        )
        df["estimated_fair_value_m"] = (
            df["fee_guaranteed_m"] * (df["value_score"] / 50.0)
        ).round(1)
        df["transfer_premium_pct"] = (
            ((df["fee_guaranteed_m"] / df["estimated_fair_value_m"]) - 1.0) * 100
        ).round(0)

        # ------------------------------------------------------------------
        # 2. CURRENT VALUE SCORE
        #    Cost base = current FPL price (£m)
        #    Performance = this season only (live FPL data)
        # ------------------------------------------------------------------
        live_mins = df["live_minutes"].fillna(0.0)
        live_gc = (
            df["live_goals"].fillna(0.0) + df["live_assists"].fillna(0.0)
        )
        live_per_90 = live_mins / 90.0
        live_gc_per_90 = np.where(live_per_90 > 0, live_gc / live_per_90, 0.0)
        live_xgi = df["xg"].fillna(0.0) + df["xa"].fillna(0.0)
        live_xgi_per_90 = np.where(live_per_90 > 0, live_xgi / live_per_90, 0.0)

        df["live_goal_contrib"] = live_gc
        df["live_goal_contrib_per_90"] = live_gc_per_90
        df["live_xgi_per_90"] = live_xgi_per_90

        # £ per contribution this season (using current FPL price)
        price = df["price_now"].replace(0, np.nan)
        df["price_per_contrib"] = np.where(
            live_gc > 0,
            (price * 1_000_000) / live_gc,
            np.nan,
        )

        df["current_production_raw"] = (
            pd.Series(live_gc_per_90) * 0.6
            + pd.Series(live_xgi_per_90) * 0.4
        )
        df["current_production_score"] = self._minmax(df["current_production_raw"])
        df["current_volume_score"] = self._minmax(live_mins)

        inv_price = 1.0 / df["price_per_contrib"].replace(0, np.nan)
        inv_price = inv_price.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        df["current_efficiency_score"] = self._minmax(inv_price)

        df["current_value_score"] = (
            df["current_production_score"] * c.production_weight
            + df["current_volume_score"] * c.volume_weight
            + df["current_efficiency_score"] * c.efficiency_weight
        )
        # Soft penalty when this-season sample is tiny
        live_low = live_mins < 90
        df.loc[live_low, "current_value_score"] = (
            df.loc[live_low, "current_value_score"] * 0.7
        )
        df["current_value_label"] = np.select(
            [df["current_value_score"] >= 70, df["current_value_score"] >= 40],
            ["Good value", "Fair value"],
            default="Poor value",
        )

        # Narrative flag: how the two scores relate
        df["value_gap"] = (
            df["current_value_score"] - df["value_score"]
        ).round(0)
        no_live = df["live_minutes"].fillna(0) < 1
        df["value_story"] = np.select(
            [
                no_live & (df["value_score"] >= 55),
                no_live,
                (df["value_score"] >= 55) & (df["current_value_score"] >= 55),
                (df["value_score"] >= 55) & (df["current_value_score"] < 40),
                (df["value_score"] < 40) & (df["current_value_score"] >= 55),
                (df["value_score"] < 40) & (df["current_value_score"] < 40),
            ],
            [
                "Strong transfer (no current-season sample)",
                "Limited current-season sample",
                "Strong transfer & still delivering",
                "Good transfer, currently underperforming",
                "Expensive transfer, currently justifying price",
                "Weak transfer & currently poor value",
            ],
            default="Mixed picture",
        )

        df = df.sort_values(
            ["value_score", "goal_contrib"],
            ascending=[False, False],
        ).reset_index(drop=True)

        df.insert(0, "rank", np.arange(1, len(df) + 1))
        return df

    def explain_player(self, row: pd.Series) -> str:
        fee = row["fee_guaranteed_m"]
        score = row["value_score"]
        label = row["value_label"]
        mins = int(row["minutes"])
        gc = int(row["goal_contrib"])
        seasons = int(row.get("seasons_counted", 1))
        p90 = row["pounds_per_90"]
        p90_str = f"£{p90/1_000_000:.2f}m per 90" if pd.notna(p90) else "n/a"

        cur_score = row.get("current_value_score", 0)
        cur_label = row.get("current_value_label", "")
        price = row.get("price_now", 0)
        live_mins = int(row.get("live_minutes", 0))
        live_gc = int(row.get("live_goal_contrib", 0))
        story = row.get("value_story", "")

        return (
            f"{row['player_name']} moved from {row['from_club']} to {row['to_club']} "
            f"for a guaranteed £{fee:.1f}m. "
            f"Since the transfer ({seasons} season(s)): {mins:,} minutes, "
            f"{gc} goal contributions. Efficiency: {p90_str}. "
            f"**Transfer Value Score: {score:.0f}/100 ({label}).** "
            f"This season: {live_mins} minutes, {live_gc} G+A at a current FPL price "
            f"of £{price:.1f}m. "
            f"**Current Value Score: {cur_score:.0f}/100 ({cur_label}).** "
            f"{story}."
        )
