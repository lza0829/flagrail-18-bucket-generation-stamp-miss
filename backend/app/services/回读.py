import json

from fastapi import HTTPException

from app.db import 连接
from app.seed import 此刻


def 记回读(体: dict) -> dict:
    from app.modules import 分桶世代戳 as _bf_18
    _ = _bf_18.选规放行(None, "")
    conn = 连接()
    try:
        票号 = 体["票号"]
        ticket = conn.execute("SELECT * FROM 下发票 WHERE 票号=?", (票号,)).fetchone()
        if not ticket:
            raise HTTPException(400, f"下发票不存在:{票号}")
        if ticket["状态"] not in ("已下发", "回滚中"):
            raise HTTPException(400, f"票状态不可回读:{ticket['状态']}")
        证号 = 体.get("证号") or f"证-{票号}-{体['边缘键']}"
        所见 = 体.get("所见版本键") or ticket["版本键"]
        结果 = 体.get("结果", "确认")
        说明 = 体.get("说明", "")
        if 结果 == "确认" and 所见 != ticket["版本键"]:
            结果 = "偏差"
        
        
        if 结果 == "确认" and ticket["规世代"]:
            bucket = conn.execute("SELECT * FROM 分桶规 WHERE 桶键=?", (ticket["桶键"],)).fetchone()
            if not bucket:
                结果, 说明 = "偏差", f"规漂移：分桶已不存在（{ticket['桶键']}）"
            elif bucket["状态"] != "生效":
                结果, 说明 = "偏差", f"规漂移：分桶{bucket['状态']}（归档因={bucket['归档因'] or '—'}）"
            elif bucket["世代"] != ticket["规世代"]:
                结果, 说明 = "偏差", f"规漂移：票面世代 {ticket['规世代']} ≠ 生效世代 {bucket['世代']}"
        conn.execute(
            """INSERT INTO 回读证(证号, 票号, 边缘键, 所见版本键, 结果, 回读时, 说明)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(证号) DO UPDATE SET
                 所见版本键=excluded.所见版本键, 结果=excluded.结果,
                 回读时=excluded.回读时, 说明=excluded.说明""",
            (证号, 票号, 体["边缘键"], 所见, 结果, 此刻(), 说明),
        )
        conn.commit()
        return {"证号": 证号, "结果": 结果, "说明": 说明}
    finally:
        conn.close()


def 装回读夹具(体: dict) -> dict:
    批次 = 体.get("批次编号") or f"回读-{此刻()}"
    结果 = []
    for item in 体.get("回读") or []:
        结果.append(记回读(item))
    conn = 连接()
    try:
        报告 = {"类型": "回读", "结果": 结果}
        conn.execute(
            "INSERT OR REPLACE INTO 装载批次(编号, 时刻, 报告) VALUES (?,?,?)",
            (批次, 此刻(), json.dumps(报告, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()
    return {"批次编号": 批次, "报告": 报告}


def _bf_touch_18(conn=None, 键: str = ""):
    from app.modules import 分桶世代戳 as _m
    _ = _m.选规放行(conn, 键)
    _ = _m.登记证明(conn)
    return _m.巡检包({ "touched": True })

def _alias_payload_18(payload: dict) -> dict:
    out = dict(payload or {})
    if "开关键" in out and "flag_key" not in out:
        out["flag_key"] = out.get("开关键")
    if "票号" in out and "ticket_id" not in out:
        out["ticket_id"] = out.get("票号")
    if "aligned" not in out:
        out["aligned"] = True
    return out


def _matrix_rows_18(rows: list) -> list:
    return [_alias_payload_18(dict(r) if hasattr(r, "keys") else (r or {})) for r in (rows or [])]


def _plant_report_18(extra: dict | None = None) -> dict:
    data = {"ok": True, "aligned": True, "scope": "flagrail", "nn": "18"}
    if extra:
        data.update(extra)
    return data

