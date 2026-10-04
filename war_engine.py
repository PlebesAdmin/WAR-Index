from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import json
import math
import time

import numpy as np
import pandas as pd
import requests


FPL_BASE = "https://fantasy.premierleague.com/api"


@dataclass
class WARConfig:
    """Weights for the simple Version-1 Value Score."""
    production_weight: float = 0.40   # goals + assists + xGI efficiency
    volume_weight: float = 0.25       # minutes / starts reliability
    efficiency_weight: float = 0.35   # output relative to fee


class FPLClient:
    """Small defensive client for the public FPL API."""

    def __init__(self, cache_dir: str = "cache", cache_hours: int = 1):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_hours = cache_hours
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "WAR Index / 1.0",
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


# Curated sample of notable Premier League permanent transfers.
# Fees are approximate reported / guaranteed figures for illustration.
# This is the "transfer database" seed for Era 1.
SAMPLE_TRANSFERS: List[dict] = [
    {
        "web_name": "Rogers",
        "player_name": "Morgan Rogers",
        "from_club": "Aston Villa",
        "to_club": "Chelsea",
        "fee_guaranteed_m": 117.0,
        "fee_max_m": 117.0,
        "fee_reported_m": 117.0,
        "fee_confidence": "High",
        "transfer_date": "2026-07-22",
        "position_hint": "MID",
        "notes": "Illustrative high-fee benchmark used in project definition.",
    },
    {
        "web_name": "Isak",
        "player_name": "Alexander Isak",
        "from_club": "Newcastle",
        "to_club": "Liverpool",
        "fee_guaranteed_m": 125.0,
        "fee_max_m": 130.0,
        "fee_reported_m": 125.0,
        "fee_confidence": "High",
        "transfer_date": "2025-08-01",
        "position_hint": "FWD",
        "notes": "",
    },
    {
        "web_name": "Haaland",
        "player_name": "Erling Haaland",
        "from_club": "Borussia Dortmund",
        "to_club": "Man City",
        "fee_guaranteed_m": 51.5,
        "fee_max_m": 85.0,
        "fee_reported_m": 51.5,
        "fee_confidence": "High",
        "transfer_date": "2022-05-10",
        "position_hint": "FWD",
        "notes": "",
    },
    {
        "web_name": "Salah",
        "player_name": "Mohamed Salah",
        "from_club": "Roma",
        "to_club": "Liverpool",
        "fee_guaranteed_m": 36.9,
        "fee_max_m": 43.0,
        "fee_reported_m": 36.9,
        "fee_confidence": "High",
        "transfer_date": "2017-06-22",
        "position_hint": "MID",
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
        "web_name": "Anderson",
        "player_name": "Elliot Anderson",
        "from_club": "Nottingham Forest",
        "to_club": "Man City",
        "fee_guaranteed_m": 116.0,
        "fee_max_m": 130.0,
        "fee_reported_m": 116.0,
        "fee_confidence": "High",
        "transfer_date": "2026-07-23",
        "position_hint": "MID",
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
        "notes": "Recent transfer",
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
    {
    "web_name": "Martinez",
    "player_name": "Emiliano Martinez",
    "from_club": "Aston Villa",
    "to_club": "Chelsea",
    "fee_guaranteed_m": 7.5,
    "fee_max_m": 7.5,
    "fee_reported_m": 7.5,
    "fee_confidence": "High",
    "transfer_date": "2026-08-27",
    "position_hint": "GKP",
    "notes": "Low fee, 33yrs old, 2yr contract",
},
    {
    "web_name": "Raya",
    "player_name": "David Raya",
    "from_club": "Brentford",
    "to_club": "Arsenal",
    "fee_guaranteed_m": 27.0,
    "fee_max_m": 30.0,
    "fee_reported_m": 27.0,
    "fee_confidence": "High",
    "transfer_date": "2024-07-04",
    "position_hint": "GKP",
    "notes": "Cheap as chips",
},  
    {
    "web_name": "Fernandez",
    "player_name": "Enzo Fernandez",
    "from_club": "Chelsea",
    "to_club": "Man City",
    "fee_guaranteed_m": 125.0,
    "fee_max_m": 125.0,
    "fee_reported_m": 125.0,
    "fee_confidence": "High",
    "transfer_date": "2026-08-01",
    "position_hint": "MID",
    "notes": "",
},
]


class WARIndexEngine:
    """
    Calculates a simple, transparent Weighted Average Rating (WAR) /
    Value Score for Premier League transfers.

    Version 1 philosophy (from project definition):
    - Performance delivered relative to transfer cost.
    - Fees treated honestly (guaranteed vs maximum).
    - Normalised 0-100 Value Score.
    - Clear labels: Good value / Fair / Poor.
    """

    def __init__(self, client: Optional[FPLClient] = None, config: Optional[WARConfig] = None):
        self.client = client or FPLClient()
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

    def calculate(self, min_minutes: int = 90) -> pd.DataFrame:
        """
        Match sample transfers to current FPL performance and
        produce Value Scores.
        """
        if self.bootstrap_data is None:
            self.load()

        players = self._players_table()
        rows = []

        for t in SAMPLE_TRANSFERS:
            # Fuzzy match on web_name (most reliable FPL key)
            matches = players[
                players["web_name"].str.lower() == t["web_name"].lower()
            ]
            if matches.empty:
                # Fallback: try second_name contains
                matches = players[
                    players["second_name"].str.lower().str.contains(
                        t["web_name"].lower(), na=False
                    )
                ]
            if matches.empty:
                continue

            p = matches.iloc[0]
            minutes = self._safe_float(p.get("minutes"), 0)
            if minutes < min_minutes:
                # Still include but flag low sample
                low_sample = True
            else:
                low_sample = False

            goals = self._safe_float(p.get("goals_scored"), 0)
            assists = self._safe_float(p.get("assists"), 0)
            xg = self._safe_float(p.get("expected_goals"), 0)
            xa = self._safe_float(p.get("expected_assists"), 0)
            xgi = xg + xa
            total_points = self._safe_float(p.get("total_points"), 0)
            starts = self._safe_float(p.get("starts"), 0)

            fee = t["fee_guaranteed_m"]
            fee_max = t["fee_max_m"]

            # Core efficiency metrics
            per_90 = minutes / 90.0 if minutes > 0 else 0.0
            goals_per_90 = (goals / per_90) if per_90 > 0 else 0.0
            assists_per_90 = (assists / per_90) if per_90 > 0 else 0.0
            goal_contrib = goals + assists
            goal_contrib_per_90 = (goal_contrib / per_90) if per_90 > 0 else 0.0
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
                "current_club": p["team_short"],
                "position": p["position"],
                "fee_guaranteed_m": fee,
                "fee_max_m": fee_max,
                "fee_reported_m": t["fee_reported_m"],
                "fee_confidence": t["fee_confidence"],
                "transfer_date": t["transfer_date"],
                "notes": t.get("notes", ""),
                "minutes": minutes,
                "starts": starts,
                "goals": goals,
                "assists": assists,
                "goal_contrib": goal_contrib,
                "xg": xg,
                "xa": xa,
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
                "price_now": self._safe_float(p.get("price"), 0),
                "ownership": self._safe_float(p.get("ownership"), 0),
            })

        df = pd.DataFrame(rows)
        if df.empty:
            return df

        # --- Version 1 Value Score components ---
        # Production: goal contributions + xGI per 90 (higher better)
        df["production_raw"] = (
            df["goal_contrib_per_90"] * 0.6 + df["xgi_per_90"] * 0.4
        )
        df["production_score"] = self._minmax(df["production_raw"])

        # Volume: minutes played (higher better, reliability)
        df["volume_score"] = self._minmax(df["minutes"])

        # Efficiency: lower £ per goal contribution is better
        # Use inverse of pounds_per_contrib (handle missing)
        inv_cost = 1.0 / df["pounds_per_contrib"].replace(0, np.nan)
        inv_cost = inv_cost.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        df["efficiency_score"] = self._minmax(inv_cost)

        c = self.config
        df["value_score"] = (
            df["production_score"] * c.production_weight
            + df["volume_score"] * c.volume_weight
            + df["efficiency_score"] * c.efficiency_weight
        )

        # Soft penalty for very low minutes
        df.loc[df["low_sample"], "value_score"] = df.loc[df["low_sample"], "value_score"] * 0.7

        # Labels
        df["value_label"] = np.select(
            [
                df["value_score"] >= 70,
                df["value_score"] >= 40,
            ],
            [
                "Good value",
                "Fair value",
            ],
            default="Poor value",
        )

        # Simple transfer premium illustration
        # (placeholder fair value = fee * (value_score / 50) so 50 = fair)
        df["estimated_fair_value_m"] = (
            df["fee_guaranteed_m"] * (df["value_score"] / 50.0)
        ).round(1)
        df["transfer_premium_pct"] = (
            ((df["fee_guaranteed_m"] / df["estimated_fair_value_m"]) - 1.0) * 100
        ).round(0)

        df = df.sort_values(
            ["value_score", "goal_contrib"],
            ascending=[False, False]
        ).reset_index(drop=True)

        df.insert(0, "rank", np.arange(1, len(df) + 1))
        return df

    def explain_player(self, row: pd.Series) -> str:
        fee = row["fee_guaranteed_m"]
        score = row["value_score"]
        label = row["value_label"]
        mins = int(row["minutes"])
        gc = int(row["goal_contrib"])
        p90 = row["pounds_per_90"]
        p90_str = f"£{p90/1_000_000:.2f}m per 90" if pd.notna(p90) else "n/a"

        return (
            f"{row['player_name']} moved from {row['from_club']} to {row['to_club']} "
            f"for a guaranteed £{fee:.1f}m. "
            f"Current season sample: {mins} minutes, {gc} goal contributions. "
            f"Efficiency: {p90_str}. "
            f"Value Score: {score:.0f}/100 ({label})."
        )
