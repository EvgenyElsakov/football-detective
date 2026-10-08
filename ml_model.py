"""ML-модель: прогноз исхода матча по предматчевой статистике.

Признаки:
- Форма команды за последние 5 матчей (очки, средний xG)
- Средний xG команды за сезон (сила)
- Домашнее преимущество

Обучение: старые сезоны. Тест: новые сезоны.
"""
from sqlalchemy import text
from models import engine
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix


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
        ORDER BY m.date
    """
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn)


def build_team_history(df: pd.DataFrame) -> dict:
    """Возвращает для каждой команды её матчи (для расчёта формы)."""
    history = {}
    # Собираем все матчи команды — и как хозяина, и как гостя
    for _, row in df.iterrows():
        home = row["home"]
        away = row["away"]
        date = row["date"]

        # xG и очки для хозяев
        if home not in history:
            history[home] = []
        if row["home_goals"] > row["away_goals"]:
            pts_home = 3
        elif row["home_goals"] == row["away_goals"]:
            pts_home = 1
        else:
            pts_home = 0
        history[home].append({
            "date": date, "xg_for": row["home_xg"],
            "xg_against": row["away_xg"], "pts": pts_home,
        })

        # Для гостей
        if away not in history:
            history[away] = []
        if row["away_goals"] > row["home_goals"]:
            pts_away = 3
        elif row["away_goals"] == row["home_goals"]:
            pts_away = 1
        else:
            pts_away = 0
        history[away].append({
            "date": date, "xg_for": row["away_xg"],
            "xg_against": row["home_xg"], "pts": pts_away,
        })

    # Сортируем историю по дате
    for team in history:
        history[team].sort(key=lambda x: x["date"])
    return history


def form_features(history: list, current_date, n_matches: int = 5) -> dict:
    """Возвращает признаки формы команды за N матчей до current_date."""
    # Берём все матчи СТРОГО до current_date
    past = [m for m in history if m["date"] < current_date]
    recent = past[-n_matches:] if len(past) >= n_matches else past

    if not recent:
        return {"form_pts": 0, "form_xg_for": 0, "form_xg_against": 0, "n_matches": 0}

    return {
        "form_pts": np.mean([m["pts"] for m in recent]),
        "form_xg_for": np.mean([m["xg_for"] for m in recent]),
        "form_xg_against": np.mean([m["xg_against"] for m in recent]),
        "n_matches": len(recent),
    }


def build_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Строит feature matrix X и target y."""
    print("📊 Считаем формы команд...")
    history = build_team_history(df)

    rows = []
    for i, row in df.iterrows():
        if i % 1000 == 0:
            print(f"   Обработано: {i}/{len(df)}")

        h_form = form_features(history[row["home"]], row["date"])
        a_form = form_features(history[row["away"]], row["date"])

        # Пропускаем матчи, где мало истории (первые 5 матчей сезона)
        if h_form["n_matches"] < 3 or a_form["n_matches"] < 3:
            continue

        # Целевая переменная: 0 = хозяева, 1 = ничья, 2 = гости
        if row["home_goals"] > row["away_goals"]:
            target = 0
        elif row["home_goals"] == row["away_goals"]:
            target = 1
        else:
            target = 2

        rows.append({
            "season": row["season"],
            "date": row["date"],
            # Форма хозяев
            "home_form_pts": h_form["form_pts"],
            "home_form_xg_for": h_form["form_xg_for"],
            "home_form_xg_against": h_form["form_xg_against"],
            # Форма гостей
            "away_form_pts": a_form["form_pts"],
            "away_form_xg_for": a_form["form_xg_for"],
            "away_form_xg_against": a_form["form_xg_against"],
            # Разница (это самые сильные признаки обычно)
            "diff_form_pts": h_form["form_pts"] - a_form["form_pts"],
            "diff_form_xg": h_form["form_xg_for"] - a_form["form_xg_for"],
            # Домашнее преимущество — константа (для baseline)
            "is_home": 1,
            # Target
            "target": target,
        })

    return pd.DataFrame(rows)


def main():
    print("🔮 ML-МОДЕЛЬ: ПРОГНОЗ ИСХОДА МАТЧА\n")
    df = load_matches()
    print(f"📊 Загружено матчей: {len(df)}\n")

    data = build_dataset(df)
    print(f"\n✅ Собрано примеров: {len(data)}")
    print(f"   Распределение исходов:")
    target_names = {0: "победа хозяев", 1: "ничья", 2: "победа гостей"}
    for t, name in target_names.items():
        count = (data["target"] == t).sum()
        print(f"     {name}: {count} ({count/len(data)*100:.1f}%)")

    # === Разделение по времени ===
    train_seasons = ["2223", "2324"]
    test_seasons = ["2425", "2526"]

    train = data[data["season"].isin(train_seasons)].copy()
    test = data[data["season"].isin(test_seasons)].copy()

    feature_cols = [
        "home_form_pts", "home_form_xg_for", "home_form_xg_against",
        "away_form_pts", "away_form_xg_for", "away_form_xg_against",
        "diff_form_pts", "diff_form_xg",
    ]

    X_train = train[feature_cols].values
    y_train = train["target"].values
    X_test = test[feature_cols].values
    y_test = test["target"].values

    print(f"\n📚 Train: {len(train)} матчей ({train_seasons})")
    print(f"🧪 Test:  {len(test)} матчей ({test_seasons})")

    # === Масштабирование ===
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # === Обучение ===
    print("\n🎓 Обучаем Logistic Regression...")
    model = LogisticRegression(max_iter=1000)
    model.fit(X_train_scaled, y_train)

    # === Baseline: всегда ставим на хозяев ===
    baseline_pred = np.zeros_like(y_test)  # 0 = хозяева
    baseline_acc = accuracy_score(y_test, baseline_pred)

    # === Предсказание ===
    y_pred = model.predict(X_test_scaled)
    model_acc = accuracy_score(y_test, y_pred)

    print("\n" + "=" * 70)
    print("📊 РЕЗУЛЬТАТЫ")
    print("=" * 70)
    print(f"\n  Baseline (всегда хозяева):  {baseline_acc*100:.1f}%")
    print(f"  Наша модель:                {model_acc*100:.1f}%")
    print(f"  Прирост:                    +{(model_acc-baseline_acc)*100:.1f} п.п.")

    print("\n" + "=" * 70)
    print("📋 ДЕТАЛЬНЫЙ ОТЧЁТ ПО КЛАССАМ")
    print("=" * 70)
    print(classification_report(
        y_test, y_pred,
        target_names=["победа хозяев", "ничья", "победа гостей"],
        zero_division=0,
    ))

    print("=" * 70)
    print("🔍 МАТРИЦА ОШИБОК")
    print("=" * 70)
    cm = confusion_matrix(y_test, y_pred)
    print(f"\n  {'':<20} {'пред.хозяева':<15} {'пред.ничья':<15} {'пред.гости':<15}")
    labels = ["ист.хозяева", "ист.ничья", "ист.гости"]
    for i, label in enumerate(labels):
        print(f"  {label:<20} {cm[i][0]:<15} {cm[i][1]:<15} {cm[i][2]:<15}")

    # === Важность признаков ===
    print("\n" + "=" * 70)
    print("🎯 ВАЖНОСТЬ ПРИЗНАКОВ (по абсолютному весу)")
    print("=" * 70)
    for i, target_name in enumerate(["победа хозяев", "ничья", "победа гостей"]):
        print(f"\n  Для класса '{target_name}':")
        weights = model.coef_[i]
        top_idx = np.argsort(np.abs(weights))[::-1][:5]
        for idx in top_idx:
            print(f"     {feature_cols[idx]:<25} {weights[idx]:+.3f}")


if __name__ == "__main__":
    main()