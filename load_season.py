"""Универсальный загрузчик: любая лига, любой сезон."""
import sys
import soccerdata as sd
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from models import engine, Team, Match, create_tables


NAME_MAP = {
    # === АПЛ ===
    "Manchester United": "Manchester Utd",
    "Nottingham Forest": "Nottingham",
    "Wolverhampton Wanderers": "Wolves",
    "Newcastle United": "Newcastle",
    "Luton": "Luton Town",
    "Leeds": "Leeds United",
    "Leicester": "Leicester City",         # ← новое
    "Ipswich": "Ipswich Town",             # ← новое

    # === La Liga ===
    "Alaves": "Alavés",
    "Atletico Madrid": "Atlético Madrid",
    "Real Oviedo": "Oviedo",
    "Almeria": "Almería",                  # ← новое
    "Cadiz": "Cádiz",                      # ← новое
    "Real Valladolid": "Valladolid",       # ← новое
    "Leganes": "Leganés",                  # ← новое

    # === Serie A ===
    "AC Milan": "Milan",
    "Parma Calcio 1913": "Parma",
    "Verona": "Hellas Verona",

    # === Bundesliga ===
    "Bayer Leverkusen": "Leverkusen",
    "Borussia Dortmund": "Dortmund",
    "Borussia M.Gladbach": "Gladbach",
    "Eintracht Frankfurt": "Frankfurt",
    "FC Cologne": "Köln",
    "FC Heidenheim": "Heidenheim",
    "RasenBallsport Leipzig": "RB Leipzig",
    "St. Pauli": "St Pauli",
    "VfB Stuttgart": "Stuttgart",
    "Hertha Berlin": "Hertha BSC",         # ← новое
    "Darmstadt": "Darmstadt 98",           # ← новое

    # === Ligue 1 ===
    "Paris Saint Germain": "Paris SG",
    "Saint-Etienne": "Saint-Étienne",      # ← новое
}


def normalize(name: str) -> str:
    name = " ".join(str(name).split())
    return NAME_MAP.get(name, name)


def get_or_create_team(session, name: str, league: str) -> Team:
    team = session.scalar(select(Team).where(Team.name == name))
    if team is None:
        team = Team(name=name, league=league)
        session.add(team)
        session.flush()
    return team


# Сезоны: FBref-код → Understat-код
SEASONS = {
    "2122": "2022",   # оставляем, но не используем
    "2223": "2022",
    "2324": "2023",   # ← для 2324 Understat код = 2023 (это 23/24 сезон)
    "2425": "2024",
    "2526": "2025",
}

# Лиги (одинаково называются в FBref и Understat)
LEAGUES = [
    "ENG-Premier League",
    "ESP-La Liga",
    "ITA-Serie A",
    "GER-Bundesliga",
    "FRA-Ligue 1",
]


def load_one(league: str, season_fb: str):
    season_us = SEASONS[season_fb]
    print(f"\n{'=' * 60}")
    print(f"📥 {league} | {season_fb}")
    print(f"{'=' * 60}")

    fbref = sd.FBref(leagues=league, seasons=season_fb)
    schedule = fbref.read_schedule().reset_index()

    us = sd.Understat(leagues=league, seasons=season_us)
    us_schedule = us.read_schedule().reset_index()

    # xG lookup
    xg_lookup = {}
    for _, row in us_schedule.iterrows():
        home = normalize(row["home_team"])
        away = normalize(row["away_team"])
        d = row["date"]
        if hasattr(d, "date"):
            d = d.date()
        xg_lookup[(d, home, away)] = (float(row["home_xg"]), float(row["away_xg"]))

    inserted = 0
    updated = 0
    skipped = 0
    no_xg = 0

    with Session(engine) as session:
        for _, row in schedule.iterrows():
            if row.get("score") is None or str(row["score"]).strip() in ("", "nan"):
                skipped += 1
                continue

            home_name = str(row["home_team"]).strip()
            away_name = str(row["away_team"]).strip()

            score_str = str(row["score"]).replace("–", "-").replace("—", "-")
            try:
                home_goals, away_goals = map(int, score_str.split("-"))
            except ValueError:
                skipped += 1
                continue

            match_date = row["date"]
            if hasattr(match_date, "date"):
                match_date = match_date.date()
            elif isinstance(match_date, str):
                match_date = datetime.strptime(match_date, "%Y-%m-%d").date()

            home_team = get_or_create_team(session, home_name, league)
            away_team = get_or_create_team(session, away_name, league)

            # xG (фоллбэк ±2 дня)
            xg = xg_lookup.get((match_date, home_name, away_name))
            if xg is None:
                for delta in (-1, 1, -2, 2):
                    xg = xg_lookup.get((match_date + timedelta(days=delta), home_name, away_name))
                    if xg:
                        break

            existing = session.scalar(
                select(Match).where(
                    Match.date == match_date,
                    Match.home_team_id == home_team.id,
                    Match.away_team_id == away_team.id,
                )
            )

            if existing:
                if existing.home_xg is None and xg is not None:
                    existing.home_xg = xg[0]
                    existing.away_xg = xg[1]
                    updated += 1
                else:
                    skipped += 1
                continue

            if xg is None:
                no_xg += 1

            match = Match(
                date=match_date,
                league=league,
                season=season_fb,
                home_team_id=home_team.id,
                away_team_id=away_team.id,
                home_goals=home_goals,
                away_goals=away_goals,
                home_xg=xg[0] if xg else None,
                away_xg=xg[1] if xg else None,
            )
            session.add(match)
            inserted += 1

        session.commit()

    print(f"   ✅ Добавлено:  {inserted}")
    print(f"   🔄 Обновлено:  {updated}")
    print(f"   ⏭️  Пропущено: {skipped}")
    if no_xg:
        print(f"   ⚠️  Без xG:    {no_xg}")
    return inserted, updated


if __name__ == "__main__":
    create_tables()

    seasons_to_load = sys.argv[1:] if len(sys.argv) > 1 else list(SEASONS.keys())

    total_added = 0
    total_updated = 0
    for season in seasons_to_load:
        if season not in SEASONS:
            print(f"⚠️  Неизвестный сезон: {season}")
            continue
        for league in LEAGUES:
            added, updated = load_one(league, season)
            total_added += added
            total_updated += updated

    print(f"\n🎉 ИТОГО: добавлено {total_added}, обновлено {total_updated}")