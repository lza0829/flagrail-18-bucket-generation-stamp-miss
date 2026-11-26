import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

数据目录 = Path(os.environ.get("数据目录", Path(__file__).resolve().parent.parent / "data"))
夹具目录 = Path(os.environ.get("夹具目录", Path(__file__).resolve().parent.parent.parent / "fixtures"))
库路径 = 数据目录 / "灰度轨.db"
默认忙等秒 = 5.0


class 写锁冲突(RuntimeError):
    """写锁被他方占用。本站口径为「失败闭」：不排队、不重试、不半截生效。"""


def _是锁错(e: BaseException) -> bool:
    文 = str(e).lower()
    return "locked" in 文 or "busy" in 文


def 连接() -> sqlite3.Connection:
    数据目录.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(库路径, timeout=默认忙等秒)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


@contextmanager
def 写事务():
    """显式 BEGIN IMMEDIATE + 零等待。

    写规、下发这类会互相踩口径的动作必须在同一事务里「读规 + 落账」；
    拿不到写锁立刻抛 写锁冲突，由调用方翻译成 409 —— 失败闭，绝不排队后
    再以旧规则落一票半截结果。
    """
    数据目录.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(库路径, timeout=0, isolation_level=None)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA foreign_keys = ON")
        try:
            c.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as e:
            if _是锁错(e):
                raise 写锁冲突(str(e)) from e
            raise
        try:
            yield c
        except BaseException:
            try:
                c.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        else:
            c.execute("COMMIT")
    finally:
        c.close()
