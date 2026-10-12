# 📊 Источники данных

[← Назад в README](../README.md)

## Что собрано

- **7 096 матчей** за 4 сезона (2021/22 – 2025/26)
- **7 080 матчей с xG** — 99.8% покрытия
- **5 лиг:** Англия, Испания, Италия, Германия, Франция

## Источники

### FBref (результаты)
- **URL:** [fbref.com](https://fbref.com)
- **Что даёт:** расписание матчей, счёт, статистика команд
- **Как парсим:** через библиотеку `soccerdata`
- **Обход защиты:** Cloudflare блокирует простые запросы, используем TLS-обход

### Understat (xG)
- **URL:** [understat.com](https://understat.com)
- **Что даёт:** expected goals (xG) для каждой команды в каждом матче
- **Как парсим:** через `soccerdata`
- **Особенность:** сезоны кодируются годом начала (`2023` = сезон 2023/24)

## Нормализация команд

FBref и Understat по-разному называют команды. Мы собрали **25+ маппингов** в `NAME_MAP`:

| Understat | FBref |
|---|---|
| Manchester United | Manchester Utd |
| Nottingham Forest | Nottingham |
| Wolverhampton Wanderers | Wolves |
| Paris Saint Germain | Paris SG |
| Almeria | Almería |
| ... | ... |

## Обработка ошибок

- **Кодировки:** PostgreSQL в UTF-8, psql на Windows переключается через `SET client_encoding TO 'UTF8'`.
- **Форматы сезонов:** Understat использует «год начала», FBref — «XXYY».
- **Даты:** фоллбэк ±2 дня при поиске xG для матча.
- **Дубли:** защита через `UniqueConstraint` в схеме БД.
- **NULL-значения:** скрипт обновляет матчи с NULL xG, а не пропускает их.