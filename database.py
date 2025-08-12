from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable, Optional
import os
import threading
import queue

try:
    import pymysql
    from pymysql.connections import Connection
    from pymysql.cursors import DictCursor
except ImportError as exc:
    raise ImportError(
        "PyMySQL가 필요합니다. 다음 명령으로 설치하세요: pip install pymysql"
    ) from exc


_DB_CONFIG: dict[str, Any] = {
    "host": "mmh7q.h.filess.io",
    "port": 3307,
    "user": "mapleJP_variousby",
    "password": "823ba7c681e126ebc9c8f476f128d50274f0a7da",
    "database": "mapleJP_variousby",
    "charset": "utf8mb4",
    "cursorclass": DictCursor,
    "autocommit": True,
    "connect_timeout": 10,
}

_connection: Optional[Connection] = None
_pool_queue: Optional[queue.Queue[Connection]] = None
_pool_lock = threading.Lock()
_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "5"))


def _apply_session_settings(conn: Connection) -> None:
    """세션 수준 기본 설정 적용 (격리수준 등)."""
    try:
        with conn.cursor() as cur:
            # 격리 수준 READ COMMITTED 적용
            cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
    except Exception:
        pass


def _create_connection() -> Connection:
    conn = pymysql.connect(**_DB_CONFIG)
    _apply_session_settings(conn)
    return conn

def _ensure_pool() -> None:
    global _pool_queue
    if _pool_queue is not None:
        return
    with _pool_lock:
        if _pool_queue is None:
            q: queue.Queue[Connection] = queue.Queue(maxsize=max(1, _POOL_SIZE))
            try:
                for _ in range(max(1, _POOL_SIZE)):
                    q.put_nowait(_create_connection())
            except Exception:
                # 풀 생성 중 실패해도 지연 초기화로 넘어감
                pass
            _pool_queue = q

def _acquire_conn_from_pool(timeout: float = 2.0) -> Connection:
    _ensure_pool()
    assert _pool_queue is not None
    try:
        return _pool_queue.get(timeout=timeout)
    except Exception:
        # 풀 고갈/타임아웃 시 임시 커넥션 생성
        return _create_connection()

def _release_conn_to_pool(conn: Connection) -> None:
    try:
        if conn is None:
            return
        _ensure_pool()
        assert _pool_queue is not None
        try:
            _pool_queue.put_nowait(conn)
        except Exception:
            # 풀이 가득 차면 닫아버림
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        pass


def get_connection() -> Connection:
    global _connection
    if _connection is not None:
        try:
            _connection.ping(reconnect=True)
            return _connection
        except Exception:
            try:
                _connection.close()
            except Exception:
                pass
            _connection = None
    _connection = _create_connection()
    return _connection


def close_connection() -> None:
    global _connection
    if _connection is not None:
        try:
            _connection.close()
        finally:
            _connection = None


@contextmanager
def cursor():
    """풀에서 커넥션을 빌려 커서를 제공한다."""
    conn = _acquire_conn_from_pool()
    cur = conn.cursor()
    try:
        yield cur
        try:
            conn.commit()
        except Exception:
            pass
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass
        _release_conn_to_pool(conn)


def fetch_all(query: str, params: Optional[Iterable[Any]] | dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with cursor_readonly() as cur:
        cur.execute(query, params or ())
        return list(cur.fetchall())


def fetch_one(query: str, params: Optional[Iterable[Any]] | dict[str, Any] | None = None) -> Optional[dict[str, Any]]:
    with cursor_readonly() as cur:
        cur.execute(query, params or ())
        return cur.fetchone()


def execute(query: str, params: Optional[Iterable[Any]] | dict[str, Any] | None = None) -> int:
    with cursor() as cur:
        cur.execute(query, params or ())
        return cur.rowcount


def executemany(query: str, seq_of_params: Iterable[Iterable[Any]] | Iterable[dict[str, Any]]) -> int:
    with cursor() as cur:
        cur.executemany(query, seq_of_params)
        return cur.rowcount

@contextmanager
def cursor_readonly():
    """읽기 전용 트랜잭션 커서. SELECT 전용에서 잠금 최소화.
    사용 후 자동 커밋/반환된다.
    """
    conn = _acquire_conn_from_pool()
    autocommit_prev = True
    try:
        autocommit_prev = bool(getattr(conn, "autocommit_mode", True))
    except Exception:
        pass
    try:
        try:
            conn.autocommit(False)
        except Exception:
            pass
        cur = conn.cursor()
        try:
            try:
                cur.execute("SET TRANSACTION READ ONLY")
            except Exception:
                pass
            yield cur
            try:
                conn.commit()
            except Exception:
                pass
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                cur.close()
            except Exception:
                pass
    finally:
        try:
            try:
                conn.autocommit(autocommit_prev)
            except Exception:
                pass
        finally:
            _release_conn_to_pool(conn)

# ========== 하트비트(1초 ping) ==========
import threading, time

_heartbeat_thread = None
_heartbeat_run = False

def _heartbeat_loop():
    global _heartbeat_run
    while _heartbeat_run:
        try:
            conn = get_connection()
            try:
                conn.ping(reconnect=True)
            except Exception:
                # 재연결 시도는 get_connection()에서 처리
                pass
        except Exception:
            pass
        time.sleep(5.0)  # 5초로 변경

def start_heartbeat():
    global _heartbeat_thread, _heartbeat_run
    if _heartbeat_thread and _heartbeat_thread.is_alive():
        return
    _heartbeat_run = True
    _heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
    _heartbeat_thread.start()

def stop_heartbeat():
    global _heartbeat_thread, _heartbeat_run
    _heartbeat_run = False
    try:
        if _heartbeat_thread and _heartbeat_thread.is_alive():
            _heartbeat_thread.join(timeout=0.2)
    except Exception:
        pass
    _heartbeat_thread = None


__all__ = [
    "get_connection",
    "close_connection",
    "cursor",
    "fetch_all",
    "fetch_one",
    "execute",
    "executemany",
    "start_heartbeat",
    "stop_heartbeat",
]
