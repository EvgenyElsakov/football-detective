"""ML-модель (бинарная версия): «победит хозяин или нет».

Убираем ничьи из рассмотрения — предсказываем только 2 класса:
- 1: победа хозяев
- 0: ничья или победа гостей
"""
from sqlalchemy import text
from models import engine
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    classification_report, confusion_matrix, roc_auc_score
)

# Импорт функций из существующего ml_model.py
from ml_model import load_matches, build_team_history, form_features


def build_binary_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Строит feature matrix для бинарной задачи."""
    print("📊 Считаем формы команд...")
    history = build_team_history(df)

    rows = []
    for i, row in df.iterrows():
        if i % 1000 == 0:
            print(f"   Обработано: {i}/{len(df)}")

        h_form = form_features(history[row["home"]], row["date"])
        a_form = form_features(history[row["away"]], row["date"])

        if h_form["n_matches"] < 3 or a_form["n_matches"] < 3:
            continue

        # Target: 1 = победа хозяев, 0 = всё остальное
        target = 1 if row["home_goals"] > row["away_goals"] else 0

        rows.append({
            "season": row["season"],
            "date": row["date"],
            "home_form_pts": h_form["form_pts"],
            "home_form_xg_for": h_form["form_xg_for"],
            "home_form_xg_against": h_form["form_xg_against"],
            "away_form_pts": a_form["form_pts"],
            "away_form_xg_for": a_form["form_xg_for"],
            "away_form_xg_against": a_form["form_xg_against"],
            "diff_form_pts": h_form["form_pts"] - a_form["form_pts"],
            "diff_form_xg": h_form["form_xg_for"] - a_form["form_xg_for"],
            "target": target,
        })

    return pd.DataFrame(rows)


def main():
    print("🔮 ML-МОДЕЛЬ (бинарная): «победит хозяин или нет»\n")
    df = load_matches()
    print(f"📊 Загружено матчей: {len(df)}\n")

    data = build_binary_dataset(df)
    print(f"\n✅ Собрано примеров: {len(data)}")
    pos = (data["target"] == 1).sum()
    neg = (data["target"] == 0).sum()
    print(f"   Победа хозяев:            {pos} ({pos/len(data)*100:.1f}%)")
    print(f"   Ничья или победа гостей:  {neg} ({neg/len(data)*100:.1f}%)")

    # Разделение по времени
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

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # === Baseline 1: всегда ставим на хозяев ===
    baseline_always_home = np.ones_like(y_test)
    acc_always_home = accuracy_score(y_test, baseline_always_home)

    # === Baseline 2: мажоритарный класс (большинство в трейне) ===
    majority = int(np.round(y_train.mean()))
    baseline_majority = np.full_like(y_test, majority)
    acc_majority = accuracy_score(y_test, baseline_majority)

    # === Обучение ===
    print("\n🎓 Обучаем Logistic Regression...")
    model = LogisticRegression(max_iter=1000)
    model.fit(X_train_scaled, y_train)

    # Предсказание класса и вероятности
    y_pred = model.predict(X_test_scaled)
    y_proba = model.predict_proba(X_test_scaled)[:, 1]

    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    auc = roc_auc_score(y_test, y_proba)

    print("\n" + "=" * 70)
    print("📊 РЕЗУЛЬТАТЫ")
    print("=" * 70)
    print(f"\n  Baseline 1 (всегда хозяева):       {acc_always_home*100:.1f}%")
    print(f"  Baseline 2 (мажоритарный класс):   {acc_majority*100:.1f}%")
    print(f"  Наша модель:                       {acc*100:.1f}%")
    print(f"\n  Precision:  {prec*100:.1f}%")
    print(f"  Recall:     {rec*100:.1f}%")
    print(f"  F1-score:   {f1*100:.1f}%")
    print(f"  ROC-AUC:    {auc:.3f}")

    print("\n" + "=" * 70)
    print("📋 ДЕТАЛЬНЫЙ ОТЧЁТ")
    print("=" * 70)
    print(classification_report(
        y_test, y_pred,
        target_names=["не победа хозяев", "победа хозяев"],
    ))

    print("=" * 70)
    print("🔍 МАТРИЦА ОШИБОК")
    print("=" * 70)
    cm = confusion_matrix(y_test, y_pred)
    print(f"\n  {'':<25} {'пред.0':<12} {'пред.1':<12}")
    print(f"  {'ист.0 (не победа)':<25} {cm[0][0]:<12} {cm[0][1]:<12}")
    print(f"  {'ист.1 (победа)':<25} {cm[1][0]:<12} {cm[1][1]:<12}")

    print("\n" + "=" * 70)
    print("🎯 ВАЖНОСТЬ ПРИЗНАКОВ")
    print("=" * 70)
    weights = model.coef_[0]
    sorted_idx = np.argsort(np.abs(weights))[::-1]
    for idx in sorted_idx:
        bar = "█" * int(abs(weights[idx]) * 100)
        sign = "+" if weights[idx] > 0 else "−"
        print(f"  {feature_cols[idx]:<25} {sign}{abs(weights[idx]):.3f}  {bar}")


if __name__ == "__main__":
    main()