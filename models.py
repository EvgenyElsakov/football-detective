from sqlalchemy import (
    create_engine, Column, Integer, String, Date,
    Numeric, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship

# Замени ТВОЙ_ПАРОЛЬ на реальный пароль
DB_URL = "postgresql+psycopg://postgres:5848@localhost:5432/football_detective"
engine = create_engine(DB_URL)
Base = declarative_base()


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    league = Column(String(50), nullable=False)

    def __repr__(self):
        return f"<Team {self.name} ({self.league})>"


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    league = Column(String(50), nullable=False)
    season = Column(String(10), nullable=False)

    home_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    away_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)

    home_goals = Column(Integer)
    away_goals = Column(Integer)
    home_xg = Column(Numeric(4, 2))   # например, 1.85
    away_xg = Column(Numeric(4, 2))

    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])

    # Защита от дублей: один матч в один день между теми же командами
    __table_args__ = (
        UniqueConstraint("date", "home_team_id", "away_team_id", name="uq_match"),
    )

    def __repr__(self):
        return f"<Match {self.date} {self.home_team_id} vs {self.away_team_id}>"


def create_tables():
    """Создаёт все таблицы в БД"""
    Base.metadata.create_all(engine)
    print("✅ Таблицы созданы (или уже существовали)")


if __name__ == "__main__":
    create_tables()