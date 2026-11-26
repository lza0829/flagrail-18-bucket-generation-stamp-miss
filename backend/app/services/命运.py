from datetime import datetime, timezone

from app.db import 连接
from fastapi import HTTPException


def 此刻() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def 回滚票(体: dict) -> dict:
    conn = 连接()
    try:
        票号 = 体["票号"]
        ticket = conn.execute("SELECT * FROM 下发票 WHERE 票号=?", (票号,)).fetchone()
        if not ticket:
            raise HTTPException(400, f"下发票不存在:{票号}")
        if ticket["状态"] == "已回滚":
            return {"票号": 票号, "状态": "已回滚", "幂等": True}
        conn.execute(
            "UPDATE 下发票 SET 状态='已回滚' WHERE 票号=?", (票号,)
        )
        conn.execute(
            "UPDATE 开关版本 SET 状态='已回滚' WHERE 版本键=?",
            (ticket["版本键"],),
        )
        conn.execute(
            "INSERT INTO 命运账(对象类型, 对象键, 命运, 时刻, 说明) VALUES (?,?,?,?,?)",
            ("下发票", 票号, "回滚", 此刻(), 体.get("说明", "灰度回滚")),
        )
        conn.execute(
            "INSERT INTO 命运账(对象类型, 对象键, 命运, 时刻, 说明) VALUES (?,?,?,?,?)",
            ("开关版本", ticket["版本键"], "回滚", 此刻(), 体.get("说明", "随票回滚")),
        )
        conn.commit()
        return {"票号": 票号, "状态": "已回滚", "幂等": False}
    finally:
        conn.close()


def 失效版本(体: dict) -> dict:
    conn = 连接()
    try:
        版本键 = 体["版本键"]
        ver = conn.execute("SELECT * FROM 开关版本 WHERE 版本键=?", (版本键,)).fetchone()
        if not ver:
            raise HTTPException(400, f"版本不存在:{版本键}")
        conn.execute("UPDATE 开关版本 SET 状态='已失效' WHERE 版本键=?", (版本键,))
        conn.execute(
            "UPDATE 下发票 SET 状态='已失效' WHERE 版本键=? AND 状态='已下发'",
            (版本键,),
        )
        conn.execute(
            "INSERT INTO 命运账(对象类型, 对象键, 命运, 时刻, 说明) VALUES (?,?,?,?,?)",
            ("开关版本", 版本键, "失效", 此刻(), 体.get("说明", "版本失效")),
        )
        conn.commit()
        return {"版本键": 版本键, "状态": "已失效"}
    finally:
        conn.close()

