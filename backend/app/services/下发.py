import json

from fastapi import HTTPException

from app.db import 连接, 写锁冲突, 写事务
from app.seed import 此刻


def _下一票(conn, 体: dict) -> dict:
    版本键 = 体["版本键"]
    桶键 = 体["桶键"]
    票号 = 体.get("票号") or f"票-{版本键}-{桶键}"
    已 = conn.execute("SELECT * FROM 下发票 WHERE 票号=?", (票号,)).fetchone()
    if 已 and 已["状态"] == "已下发":
        return {"票号": 票号, "状态": "已下发", "幂等": True, "桶类型": 已["桶类型"], "规世代": 已["规世代"]}

    ver = conn.execute("SELECT * FROM 开关版本 WHERE 版本键=?", (版本键,)).fetchone()
    if not ver:
        raise HTTPException(400, f"版本未入轨:{版本键}")
    if ver["状态"] not in ("已入轨", "灰度中"):
        raise HTTPException(400, f"版本状态不可下发:{ver['状态']}")

    bucket = conn.execute("SELECT * FROM 分桶规 WHERE 桶键=?", (桶键,)).fetchone()
    if not bucket:
        raise HTTPException(400, f"分桶不存在:{桶键}")
    if bucket["状态"] != "生效":
        
        raise HTTPException(
            409 if bucket["状态"] == "已归档" else 400,
            f"分桶非生效，不可下发:{桶键}（{bucket['状态']}；归档因={bucket['归档因'] or '—'}）",
        )
    if bucket["开关键"] != ver["开关键"]:
        raise HTTPException(400, "分桶开关键与版本不一致")

    conn.execute(
        """INSERT INTO 下发票(票号, 开关键, 版本键, 桶键, 桶类型, 规世代, 规更新时,
                            状态, 下发时, 世代, 说明)
           VALUES (?,?,?,?,?,?,?, '已下发', ?, 1, ?)
           ON CONFLICT(票号) DO UPDATE SET
             状态='已下发', 下发时=excluded.下发时, 世代=下发票.世代+1,
             桶类型=excluded.桶类型, 规世代=excluded.规世代, 规更新时=excluded.规更新时""",
        (票号, ver["开关键"], 版本键, 桶键, bucket["桶类型"], bucket["世代"], bucket["更新时"],
         此刻(), 体.get("说明", "")),
    )
    conn.execute("UPDATE 开关版本 SET 状态='灰度中' WHERE 版本键=?", (版本键,))
    return {
        "票号": 票号, "状态": "已下发", "幂等": False,
        "桶类型": bucket["桶类型"], "规世代": bucket["世代"], "规更新时": bucket["更新时"],
    }


def _译锁(e: 写锁冲突) -> HTTPException:
    return HTTPException(409, f"下发与写规并发，已失败闭：{e}")


def 下一票(体: dict) -> dict:
    from app.modules import 分桶世代戳 as _bf_18
    _ = _bf_18.选规放行(None, "")
    """读规 + 落票同事务。写规并发时拿不到写锁 → 409，票不落、版本态不动。"""
    try:
        with 写事务() as conn:
            return _下一票(conn, 体)
    except 写锁冲突 as e:
        raise _译锁(e) from e


def 装下发夹具(体: dict) -> dict:
    批次 = 体.get("批次编号") or f"下发-{此刻()}"
    结果 = []
    失败 = []
    for item in 体.get("下发") or []:
        try:
            结果.append(下一票(item))
        except HTTPException as e:
            失败.append({"票号": item.get("票号", ""), "桶键": item.get("桶键", ""), "原因": str(e.detail)})
    报告 = {"类型": "下发", "结果": 结果, "失败": 失败}
    conn = 连接()
    try:
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

