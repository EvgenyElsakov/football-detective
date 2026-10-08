"""Расследование №1: насколько футбол 'несправедлив'?

Анализ 7080 матчей топ-5 лиг за 4 сезона (2021/22 – 2025/26):
- Как часто команда с большим xG не выигрывает?
- Какая лига самая «несправедливая»?
- Меняется ли ситуация от сезона к сезону?
- Топ-10 самых несправедливых матчей.
"""
from sqlalchemy import text
from models import engine
import pandas as pd


def load_matches() -> pd.DataFrame:
    """Загружаем все матчи с xG в DataFrame."""
    query = """
        SELECT
            m.season,
            m.league,
            m.date,
            t1.name AS home,
            t2.name AS away,
            m.home_goals,
            m.away_goals,
            m.home_xg,
            m.away_xg
        FROM matches m
        JOIN teams t1 ON m.home_team_id = t1.id
        JOIN teams t2 ON m.away_team_id = t2.id
        WHERE m.home_xg IS NOT NULL AND m.away_xg IS NOT NULL
    """
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn)


def classify(df: pd.DataFrame) -> pd.DataFrame:
    """Добавляем колонки с классификацией матчей."""
    df = df.copy()

    # Исходы
    df["home_win"] = df["home_goals"] > df["away_goals"]
    df["draw"] = df["home_goals"] == df["away_goals"]
    df["away_win"] = df["away_goals"] > df["home_goals"]

    # Кто был лучше по xG
    df["home_better_xg"] = df["home_xg"] > df["away_xg"]
    df["away_better_xg"] = df["away_xg"] > df["home_xg"]

    # «Несправедливые» матчи — команда с большим xG НЕ выиграла
    df["unfair_home"] = df["home_better_xg"] & ~df["home_win"]
    df["unfair_away"] = df["away_better_xg"] & ~df["away_win"]
    df["unfair"] = df["unfair_home"] | df["unfair_away"]

    # Разница xG
    df["xg_diff"] = (df["home_xg"] - df["away_xg"]).abs()

    return df


def section(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main():
    df = load_matches()
    print(f"📊 Загружено матчей: {len(df)}\n")

    df = classify(df)

    # === 1. Общая картина ===
    total = len(df)
    unfair_total = df["unfair"].sum()
    unfair_home = df["unfair_home"].sum()
    unfair_away = df["unfair_away"].sum()

    section("🚨 ОБЩАЯ КАРТИНА: насколько футбол несправедлив?")
    print(f"\nВсего матчей:                             {total}")
    print(f"Команда с большим xG НЕ выиграла:         {unfair_total} ({unfair_total/total*100:.1f}%)")
    print(f"   ├─ хозяева доминировали, но не победили: {unfair_home} ({unfair_home/total*100:.1f}%)")
    print(f"   └─ гости доминировали, но не победили:   {unfair_away} ({unfair_away/total*100:.1f}%)")

    # === 2. По лигам ===
    section("🏆 ПО ЛИГАМ: где футбол самый несправедливый?")
    by_league = df.groupby("league").agg(
        matches=("unfair", "size"),
        unfair=("unfair", "sum"),
    )
    by_league["unfair_pct"] = (by_league["unfair"] / by_league["matches"] * 100).round(1)
    by_league = by_league.sort_values("unfair_pct", ascending=False)
    for league, row in by_league.iterrows():
        print(f"  {league:<20} {row['unfair']:>4} / {row['matches']:>4}  ({row['unfair_pct']:>5.1f}%)")

    # === 3. По сезонам ===
    section("📅 ПО СЕЗОНАМ: меняется ли ситуация?")
    by_season = df.groupby("season").agg(
        matches=("unfair", "size"),
        unfair=("unfair", "sum"),
    )
    by_season["unfair_pct"] = (by_season["unfair"] / by_season["matches"] * 100).round(1)
    for season, row in by_season.iterrows():
        print(f"  {season}  {row['unfair']:>4} / {row['matches']:>4}  ({row['unfair_pct']:>5.1f}%)")

    # === 4. Топ-10 самых несправедливых матчей ===
    section("🔥 ТОП-10 САМЫХ НЕСПРАВЕДЛИВЫХ МАТЧЕЙ (по разнице xG)")
    unfair = df[df["unfair"]].sort_values("xg_diff", ascending=False).head(10)
    for i, (_, row) in enumerate(unfair.iterrows(), 1):
        if row["unfair_home"]:
            better_team, better_xg = row["home"], row["home_xg"]
        else:
            better_team, better_xg = row["away"], row["away_xg"]

        print(f"\n  {i}. {row['date']} | {row['league']} {row['season']}")
        print(f"     {row['home']} {row['home_goals']}:{row['away_goals']} {row['away']}")
        print(f"     xG: {row['home_xg']:.2f} – {row['away_xg']:.2f}  "
              f"(разница {row['xg_diff']:.2f})")
        print(f"     📉 Доминировал: {better_team} ({better_xg:.2f} xG)")

    # === 5. Уровни несправедливости ===
    section("🎚️ РАСПРЕДЕЛЕНИЕ ПО СИЛЕ ДОМИНИРОВАНИЯ")
    print("\nРазница xG и % несправедливых исходов:")
    bins = [0, 0.5, 1.0, 1.5, 2.0, 3.0, 100]
    labels = ["0–0.5 (равные)", "0.5–1 (лёгкое)", "1–1.5 (заметное)",
              "1.5–2 (сильное)", "2–3 (полное)", "3+ (тотальное)"]

    for i, (lo, hi) in enumerate(zip(bins[:-1], bins[1:])):
        subset = df[(df["xg_diff"] >= lo) & (df["xg_diff"] < hi)]
        if len(subset) == 0:
            continue
        unfair_pct = subset["unfair"].mean() * 100
        print(f"  {labels[i]:<20} {len(subset):>4} матчей, "
              f"несправедливых: {unfair_pct:>5.1f}%")

    # === 6. Топ-5 «жертв» и «счастливчиков» ===
    section("😢 ТОП-5 КОМАНД, КОТОРЫЕ ЧАЩЕ ВСЕГО НЕ ДОБИРАЮТ ОЧКИ ПО XG")

    # Для каждой команды считаем: сколько матчей, где её xG > соперника,
    # но она не выиграла
    home_jobs = df[df["home_better_xg"]].copy()
    home_jobs["team"] = home_jobs["home"]
    home_jobs["robbed"] = home_jobs["unfair_home"]

    away_jobs = df[df["away_better_xg"]].copy()
    away_jobs["team"] = away_jobs["away"]
    away_jobs["robbed"] = away_jobs["unfair_away"]

    both = pd.concat([
        home_jobs[["team", "robbed"]],
        away_jobs[["team", "robbed"]],
    ])

    robbed_stats = both.groupby("team").agg(
        dominated=("robbed", "size"),
        robbed=("robbed", "sum"),
    )
    robbed_stats["robbed_pct"] = (robbed_stats["robbed"] / robbed_stats["dominated"] * 100).round(1)
    robbed_stats = robbed_stats[robbed_stats["dominated"] >= 50]  # минимум 50 матчей
    top_robbed = robbed_stats.sort_values("robbed_pct", ascending=False).head(5)

    print(f"\n  (минимум 50 матчей, где команда доминировала по xG)\n")
    for team, row in top_robbed.iterrows():
        print(f"  {team:<25} {row['robbed']:>3} из {row['dominated']:>3} "
              f"({row['robbed_pct']:>5.1f}%) — не добрали очки")

    section("🎁 ТОП-5 КОМАНД, КОТОРЫЕ ЧАЩЕ ВСЕГО ОТБИРАЮТ ОЧКИ БЕЗ xG")

    # Обратная ситуация: команда доминировала МЕНЬШЕ, но выиграла
    home_lucky = df[df["away_better_xg"] & df["home_win"]].copy()
    home_lucky["team"] = home_lucky["home"]

    away_lucky = df[df["home_better_xg"] & df["away_win"]].copy()
    away_lucky["team"] = away_lucky["away"]

    both_lucky = pd.concat([home_lucky[["team"]], away_lucky[["team"]]])
    lucky_counts = both_lucky["team"].value_counts().head(5)

    print(f"\n  (команды, чаще всех выигрывавшие при меньшем xG)\n")
    for team, count in lucky_counts.items():
        print(f"  {team:<25} {count:>3} матчей")


if __name__ == "__main__":
    main()