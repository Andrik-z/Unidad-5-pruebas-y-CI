from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain import Order
from src.repository import OrderRow, SqlOrderRepository, make_engine


def test_repository_commit():
    engine = make_engine()
    with Session(engine) as session:
        SqlOrderRepository(session).save(1, Order(120))
        session.commit()
        assert session.scalar(select(OrderRow).where(OrderRow.id == 1)).total == 120

def test_repository_rollback():
    engine = make_engine()
    with Session(engine) as session:
        SqlOrderRepository(session).save(1, Order(120))
        session.rollback()
        assert session.scalar(select(OrderRow).where(OrderRow.id == 1)) is None

def test_repository_commit_order_250():
    engine = make_engine()
    with Session(engine) as session:
        SqlOrderRepository(session).save(2, Order(250))
        session.commit()
        row = session.scalar(select(OrderRow).where(OrderRow.id == 2))
        assert row.id == 2
        assert row.total == 250
        assert row.status == "NEW"


def test_repository_commit_survives_new_session():
    engine = make_engine()
    with Session(engine) as s1:
        SqlOrderRepository(s1).save(2, Order(250))
        s1.commit()
    with Session(engine) as s2:
        assert s2.get(OrderRow, 2).total == 250


def test_repository_rollback_not_visible_in_new_session():
    engine = make_engine()
    with Session(engine) as s1:
        SqlOrderRepository(s1).save(3, Order(99))
        s1.rollback()
    with Session(engine) as s2:
        assert s2.get(OrderRow, 3) is None