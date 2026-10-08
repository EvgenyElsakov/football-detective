"""Миф 4 (версия 2): «Несправедливость сильнее в топ-матчах».

Улучшение методологии: определяем топ-4 команды ВНУТРИ КАЖДОЙ ЛИГИ
по каждому сезону отдельно. Так матчей «топ vs топ» становится
достаточно для статистического теста.
"""
from sqlalchemy import text
from models import engine
import pandas as pd
from scipy import stats


def load_matches() -> pd.DataFrame:
    query = """
        SELECT
            m.season, m.league, m.date,
            t1.name AS home, t2.name AS away,
            m.home_goals, m.away_goals,
            m.home_xg, m.away_xg
        FROM matches m
        JOIN teams t1 ON m.home_team_id = t1.id
        JOIN teams t2 ON m.away_team_id = t2.id
        WHERE m.home_xg IS NOT NULL AND m.away_xg IS NOT NULL
    """
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn)


def get_top_teams_per_league_season(df: pd.DataFrame, top_n: int = 6) -> dict:
    """Возвращает словарь {(league, season): set(топ-N команд)}."""
    # Собираем статистику по каждой команде в разрезе (лига, сезон)
    home_df = df[["league", "season", "home", "home_xg", "home_goals"]].rename(
        columns={"home": "team", "home_xg": "xg", "home_goals": "goals"})
    away_df = df[["league", "season", "away", "away_xg", "away_goals"]].rename(
        columns={"away": "team", "away_xg": "xg", "away_goals": "goals"})
    both = pd.concat([home_df, away_df])

    agg = both.groupby(["league", "season", "team"]).agg(
        matches=("xg", "size"),
        avg_xg=("xg", "mean"),
    ).reset_index()

    # Берём топ-N команд в каждой (лига, сезон) по среднему xG
    top_by_group = {}
    for (league, season), group in agg.groupby(["league", "season"]):
        top = group.sort_values("avg_xg", ascending=False).head(top_n)
        top_by_group[(league, season)] = set(top["team"])

    return top_by_group


def main():
    print("🔍 МИФ 4 (версия 2): «Несправедливость сильнее в топ-матчах»")
    print("Методология: топ-4 команды ВНУТРИ каждой лиги по каждому сезону\n")

    df = load_matches()
    print(f"📊 Загружено матчей: {len(df)}")

    # Топ-4 в каждой лиге/сезоне
    top_map = get_top_teams_per_league_season(df, top_n=6)

    # Покажем по одной лиге для примера
    print(f"\nПример: топ-4 АПЛ в сезоне 2324:")
    for team in sorted(top_map.get(("ENG-Premier League", "2324"), [])):
        print(f"   • {team}")

    # Размечаем матчи
    df = df.copy()

    def is_top(row):
        key = (row["league"], row["season"])
        tops = top_map.get(key, set())
        return row["home"] in tops, row["away"] in tops

    df[["home_is_top", "away_is_top"]] = df.apply(
        lambda r: pd.Series(is_top(r)), axis=1)

    # Категории матчей
    df["both_top"] = df["home_is_top"] & df["away_is_top"]
    df["no_top"] = ~df["home_is_top"] & ~df["away_is_top"]

    # Определяем несправедливость
    df["home_win"] = df["home_goals"] > df["away_goals"]
    df["away_win"] = df["away_goals"] > df["home_goals"]
    df["home_better_xg"] = df["home_xg"] > df["away_xg"]
    df["away_better_xg"] = df["away_xg"] > df["home_xg"]
    df["unfair"] = (df["home_better_xg"] & ~df["home_win"]) | \
                   (df["away_better_xg"] & ~df["away_win"])

    # Сравнение
    top_n_matches = df["both_top"].sum()
    no_top_matches = df["no_top"].sum()

    top_unfair = df[df["both_top"]]["unfair"].mean()
    mid_unfair = df[df["no_top"]]["unfair"].mean()

    print("\n" + "=" * 70)
    print("📊 РЕЗУЛЬТАТ")
    print("=" * 70)
    print(f"\n  Доля несправедливых матчей:")
    print(f"    Топ-4 vs Топ-4:          {top_unfair*100:>5.1f}%   ({top_n_matches} матчей)")
    print(f"    Матчи без топ-4:         {mid_unfair*100:>5.1f}%   ({no_top_matches} матчей)")
    print(f"    Разница:                 {(top_unfair - mid_unfair)*100:>+5.1f} п.п.")

    # Также посмотрим "матчи с участием топ-клуба"
    df["has_top"] = df["home_is_top"] | df["away_is_top"]
    has_top_unfair = df[df["has_top"]]["unfair"].mean()
    has_top_matches = df["has_top"].sum()
    print(f"\n  Дополнительно:")
    print(f"    Матчи с одним топ-4:     {has_top_unfair*100:>5.1f}%   ({has_top_matches} матчей)")

    # Хи-квадрат
    contingency = [
        [df[df["both_top"]]["unfair"].sum(),
         top_n_matches - df[df["both_top"]]["unfair"].sum()],
        [df[df["no_top"]]["unfair"].sum(),
         no_top_matches - df[df["no_top"]]["unfair"].sum()],
    ]
    chi2, p_value, dof, _ = stats.chi2_contingency(contingency)
    effect = top_unfair - mid_unfair

    print(f"\n  Хи-квадрат: χ²={chi2:.2f}, p={p_value:.4f}")
    print(f"  Эффект: {effect*100:+.1f} п.п.")

    # Дополнительно: сравним средний xG в топ-матчах и средняцких
    top_xg = (df[df["both_top"]]["home_xg"] + df[df["both_top"]]["away_xg"]).mean()
    no_top_xg = (df[df["no_top"]]["home_xg"] + df[df["no_top"]]["away_xg"]).mean()
    print(f"\n  Средний суммарный xG в матче:")
    print(f"    Топ-4 vs Топ-4:          {top_xg:.2f}")
    print(f"    Матчи без топ-4:         {no_top_xg:.2f}")

    # Вердикт
    print("\n" + "=" * 70)
    if p_value >= 0.05:
        print("⚪ НЕТ ДОКАЗАТЕЛЬСТВ: разница между топ-матчами и остальными случайна")
    elif abs(effect) < 0.05:
        print("🟡 ФОРМАЛЬНО ЗНАЧИМО, но эффект крошечный")
    elif effect < 0:
        print("🟢 МИФ ОПРОВЕРГНУТ: в топ-матчах несправедливость НИЖЕ, а не выше")
    else:
        print("🟢 МИФ ПОДТВЕРЖДЁН: в топ-матчах несправедливость выше")
    print("=" * 70)


if __name__ == "__main__":
    main()