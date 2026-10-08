"""Детектор футбольных мифов.

Проверяем популярные убеждения болельщиков статистически
на 7080 матчах топ-5 лиг за 4 сезона.
"""
from sqlalchemy import text
from models import engine
import pandas as pd
import numpy as np
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


def verdict(p_value: float, effect: float, threshold_p: float = 0.05) -> str:
    """Возвращает вердикт на основе p-value и размера эффекта."""
    if p_value >= threshold_p:
        return "⚪ НЕТ ДОКАЗАТЕЛЬСТВ (разница случайна)"
    if abs(effect) < 0.05:
        return "🟡 ФОРМАЛЬНО ЗНАЧИМО, но эффект крошечный"
    if abs(effect) < 0.15:
        return "🟢 ПОДТВЕРЖДЁН (слабый эффект)"
    return "🟢 ПОДТВЕРЖДЁН (сильный эффект)"


def section(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


# === МИФ 1: Топ-клубы реализуют моменты лучше ===
def myth_1_top_clubs_finish_better(df: pd.DataFrame):
    section("🎯 МИФ 1: «Топ-клубы реализуют моменты лучше середняков»")

    # Считаем "силу" каждой команды: средний xG за матч
    home_df = df[["home", "home_xg", "home_goals"]].rename(
        columns={"home": "team", "home_xg": "xg", "home_goals": "goals"})
    away_df = df[["away", "away_xg", "away_goals"]].rename(
        columns={"away": "team", "away_xg": "xg", "away_goals": "goals"})
    team_stats = pd.concat([home_df, away_df])

    agg = team_stats.groupby("team").agg(
        matches=("xg", "size"),
        total_xg=("xg", "sum"),
        total_goals=("goals", "sum"),
    )
    agg = agg[agg["matches"] >= 100]  # минимум 100 матчей
    agg["conversion"] = agg["total_goals"] / agg["total_xg"]

    # Топ-8 клубов по total_xg (это "топ-клубы")
    agg = agg.sort_values("total_xg", ascending=False)
    top_8 = agg.head(8)
    rest = agg.iloc[8:]

    print("\n  Топ-8 клубов по xG за 4 сезона:")
    for team, row in top_8.iterrows():
        print(f"    {team:<25} xG: {row['total_xg']:>6.1f}  голы: {row['total_goals']:>4.0f}  "
              f"реализация: {row['conversion']*100:>5.1f}%")

    print(f"\n  Средняя реализация (голы/xG):")
    print(f"    Топ-8:      {top_8['conversion'].mean()*100:.1f}%")
    print(f"    Остальные:  {rest['conversion'].mean()*100:.1f}%")

    # t-test
    t_stat, p_value = stats.ttest_ind(top_8["conversion"], rest["conversion"], equal_var=False)
    effect = top_8["conversion"].mean() - rest["conversion"].mean()

    print(f"\n  t-тест: t={t_stat:.2f}, p={p_value:.4f}")
    print(f"  Эффект: {effect*100:+.1f} п.п.")
    print(f"\n  {verdict(p_value, effect)}")


# === МИФ 2: Домашнее преимущество слабеет ===
def myth_2_home_advantage(df: pd.DataFrame):
    section("🏟️ МИФ 2: «Домашнее преимущество слабеет из года в год»")

    seasons = sorted(df["season"].unique())
    print(f"\n  Средний xG дома vs гостей по сезонам:\n")
    print(f"  {'Сезон':<8} {'Дома':<10} {'В гостях':<10} {'Разница':<10} {'%'}")
    print(f"  {'-' * 50}")

    home_advantage = []
    for season in seasons:
        s = df[df["season"] == season]
        home_xg = s["home_xg"].mean()
        away_xg = s["away_xg"].mean()
        diff = home_xg - away_xg
        pct = diff / away_xg * 100
        home_advantage.append(diff)
        print(f"  {season:<8} {home_xg:<10.3f} {away_xg:<10.3f} {diff:<+10.3f} {pct:+.1f}%")

    # Тренд: сравним первый и последний сезон
    first, last = home_advantage[0], home_advantage[-1]
    print(f"\n  Было (2223): {first:+.3f} | Стало (2526): {last:+.3f}")

    if last < first:
        print(f"  📉 Разница уменьшилась — миф о 'слабеющем домашнем преимуществе' может быть верным")
    else:
        print(f"  📈 Разница не уменьшилась — домашнее преимущество стабильно")

    # Общая проверка: значимо ли домашнее преимущество вообще?
    t_stat, p_value = stats.ttest_rel(df["home_xg"], df["away_xg"])
    effect = df["home_xg"].mean() - df["away_xg"].mean()

    print(f"\n  Парный t-тест (home_xg vs away_xg): t={t_stat:.2f}, p={p_value:.4e}")
    print(f"  Средний эффект: {effect:+.3f} xG ({effect / df['away_xg'].mean() * 100:+.1f}%)")
    print(f"\n  {verdict(p_value, effect)}")

    # Дополнительно: % побед хозяев
    home_wins = (df["home_goals"] > df["away_goals"]).sum()
    print(f"\n  Побед хозяев: {home_wins} ({home_wins/len(df)*100:.1f}%)")


# === МИФ 3: Топ-команды чаще играют вничью ===
def myth_3_top_clubs_draw_more(df: pd.DataFrame):
    section("🤝 МИФ 3: «Топ-клубы чаще играют вничью»")

    # Определяем топ-клубы по среднему xG за матч
    home_df = df[["home", "home_xg"]].rename(columns={"home": "team", "home_xg": "xg"})
    away_df = df[["away", "away_xg"]].rename(columns={"away": "team", "away_xg": "xg"})
    team_stats = pd.concat([home_df, away_df])
    avg_xg = team_stats.groupby("team")["xg"].agg(["mean", "size"])
    avg_xg = avg_xg[avg_xg["size"] >= 100]
    top_teams = set(avg_xg.sort_values("mean", ascending=False).head(8).index)
    print(f"  Топ-8 по среднему xG: {', '.join(sorted(top_teams))}")

    # Размечаем матчи
    df = df.copy()
    df["draw"] = df["home_goals"] == df["away_goals"]
    df["has_top"] = df["home"].isin(top_teams) | df["away"].isin(top_teams)

    top_draws = df[df["has_top"]]["draw"].mean()
    other_draws = df[~df["has_top"]]["draw"].mean()

    print(f"\n  Доля ничьих:")
    print(f"    Матчи с топ-8:      {top_draws*100:.1f}%")
    print(f"    Матчи без топ-8:    {other_draws*100:.1f}%")

    # Хи-квадрат
    top_n = df["has_top"].sum()
    other_n = (~df["has_top"]).sum()
    contingency = [
        [df[df["has_top"]]["draw"].sum(), top_n - df[df["has_top"]]["draw"].sum()],
        [df[~df["has_top"]]["draw"].sum(), other_n - df[~df["has_top"]]["draw"].sum()],
    ]
    chi2, p_value, dof, _ = stats.chi2_contingency(contingency)
    effect = top_draws - other_draws

    print(f"\n  Хи-квадрат: χ²={chi2:.2f}, p={p_value:.4f}")
    print(f"  Эффект: {effect*100:+.1f} п.п.")
    print(f"\n  {verdict(p_value, effect)}")


# === МИФ 4: Гол в раздевалку деморализует ===
def myth_4_extra_time_goal(df: pd.DataFrame):
    section("⏰ МИФ 4: «Несправедливость сильнее проявляется в топ-матчах»")

    # Проверим: в матчах топ-8 vs топ-8 несправедливость выше?
    home_df = df[["home", "home_xg", "home_goals"]].rename(
        columns={"home": "team", "home_xg": "xg", "home_goals": "goals"})
    away_df = df[["away", "away_xg", "away_goals"]].rename(
        columns={"away": "team", "away_xg": "xg", "away_goals": "goals"})
    team_stats = pd.concat([home_df, away_df])
    avg_xg = team_stats.groupby("team")["xg"].agg(["mean", "size"])
    avg_xg = avg_xg[avg_xg["size"] >= 100]
    top_teams = set(avg_xg.sort_values("mean", ascending=False).head(8).index)

    df = df.copy()
    df["home_win"] = df["home_goals"] > df["away_goals"]
    df["away_win"] = df["away_goals"] > df["home_goals"]
    df["home_better_xg"] = df["home_xg"] > df["away_xg"]
    df["away_better_xg"] = df["away_xg"] > df["home_xg"]
    df["unfair"] = (df["home_better_xg"] & ~df["home_win"]) | \
                   (df["away_better_xg"] & ~df["away_win"])

    # Топ-матчи: обе команды из топ-8
    df["both_top"] = df["home"].isin(top_teams) & df["away"].isin(top_teams)
    # Матчи средняков: ни одной команды из топ-8
    df["no_top"] = ~df["home"].isin(top_teams) & ~df["away"].isin(top_teams)

    top_unfair = df[df["both_top"]]["unfair"].mean()
    mid_unfair = df[df["no_top"]]["unfair"].mean()

    print(f"\n  Доля несправедливых матчей:")
    print(f"    Топ-8 vs Топ-8:          {top_unfair*100:>5.1f}%  ({df['both_top'].sum()} матчей)")
    print(f"    Матчи без топ-8:         {mid_unfair*100:>5.1f}%  ({df['no_top'].sum()} матчей)")

    contingency = [
        [df[df["both_top"]]["unfair"].sum(), df["both_top"].sum() - df[df["both_top"]]["unfair"].sum()],
        [df[df["no_top"]]["unfair"].sum(), df["no_top"].sum() - df[df["no_top"]]["unfair"].sum()],
    ]
    chi2, p_value, dof, _ = stats.chi2_contingency(contingency)
    effect = top_unfair - mid_unfair

    print(f"\n  Хи-квадрат: χ²={chi2:.2f}, p={p_value:.4f}")
    print(f"  Эффект: {effect*100:+.1f} п.п.")
    print(f"\n  {verdict(p_value, effect)}")


# === MAIN ===
def main():
    print("🔍 ДЕТЕКТОР ФУТБОЛЬНЫХ МИФОВ")
    print("Проверяем популярные убеждения болельщиков на данных")
    df = load_matches()
    print(f"\n📊 Загружено матчей: {len(df)}")

    myth_1_top_clubs_finish_better(df)
    myth_2_home_advantage(df)
    myth_3_top_clubs_draw_more(df)
    myth_4_extra_time_goal(df)

    print("\n" + "=" * 70)
    print("🎬 РАССЛЕДОВАНИЕ ЗАВЕРШЕНО")
    print("=" * 70)


if __name__ == "__main__":
    main()