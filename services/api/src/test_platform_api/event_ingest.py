from sqlalchemy.orm import sessionmaker
from test_platform_contracts import TestRunEvent, TestRunEventType

from test_platform_api.db import SqlAlchemyRepository
from test_platform_api.redis_bus import RedisEventConsumer


def apply_event(repo: SqlAlchemyRepository, event: TestRunEvent) -> None:
    repo.append_event(event)
    if event.event_type == TestRunEventType.RUN_FAILED:
        repo.update_run_status(event.run_id, "failed")
        repo.update_run_duration(event.run_id, event.duration_ms)
    elif event.event_type == TestRunEventType.RUN_FINISHED:
        repo.update_run_status(event.run_id, "finished")
        repo.update_run_duration(event.run_id, event.duration_ms)
    elif event.event_type == TestRunEventType.RUN_STARTED:
        repo.update_run_status(event.run_id, "running")


def poll_events_once(
    consumer: RedisEventConsumer,
    session_factory: sessionmaker,
    last_id: str,
) -> str:
    newest, events = consumer.read_new(last_id=last_id)
    if not events:
        return last_id

    session = session_factory()
    try:
        repo = SqlAlchemyRepository(session)
        for event in events:
            apply_event(repo, event)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return newest
