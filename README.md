# ⚽ Football Detective

ETL-пайплайн для сбора и анализа футбольной статистики топ-5 европейских лиг (АПЛ, Ла Лига, Серия А, Бундеслига, Лига 1).

## 📊 Что собрано

- **7096 матчей** за 4 сезона (2021/22 – 2025/26)
- **7080 матчей с xG** (99.8% покрытия)
- Источники: [FBref](https://fbref.com) (результаты) + [Understat](https://understat.com) (xG)

## 🛠️ Стек

- Python 3.14
- PostgreSQL 18
- SQLAlchemy + psycopg3
- soccerdata
- pandas

## 📁 Структура

| Файл | Назначение |
|---|---|
| `models.py` | Схема БД (таблицы `teams`, `matches`) |
| `load_season.py` | Универсальный загрузчик: любая лига, любой сезон |
| `check_final.py` | Проверка состояния БД |

## 🚀 Как запустить

1. Установить зависимости: `pip install -r requirements.txt`
2. Настроить подключение к PostgreSQL в `models.py`
3. Создать таблицы: `python models.py`
4. Загрузить сезоны: `python load_season.py 2324 2425`

## 🗺️ Roadmap

- [x] ETL-пайплайн с FBref и Understat
- [x] Нормализация названий команд (25+ маппингов)
- [ ] Детектор футбольных мифов
- [ ] ML-модель прогноза исходов
- [ ] Дашборд в DataLens