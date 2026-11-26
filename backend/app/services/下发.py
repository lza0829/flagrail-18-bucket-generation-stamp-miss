import json

from fastapi import HTTPException

from app.db import 连接, 写锁冲突, 写事务
from app.modules.分桶世代戳 import 选规闸, 世代戳拒绝
from app.seed import 此刻


class 下发拒绝(HTTPException):
    """选规闸拒绝（无戳/错戳/归档/戳外/旧集），统一翻 409。"""


def _下一票(conn, 体: dict) -> dict:
    版本键 = 体["版本键"]
    桶键 = 体["桶键"]
    票号 = 体.get("票号") or f"票-{版本键}-{桶键}"
    已 = conn.execute("SELECT * FROM 下发票 WHERE 票号=?", (票号,)).fetchone()
    if 已 and 已["状态"] == "已下发":
        # 甲口径：热更新后幂等重投也不得继续绑旧集合——旧票按旧集拒绝，不新增已下发
        from app.modules.分桶世代戳 import 票绑旧集
        if 票绑旧集(conn, 已):
            raise HTTPException(
                409,
                f"票 {票号} 绑定的是旧世代集合（戳世代号={已['戳世代号']}），"
                "热更新后已下发不得绑旧集合；请改点当前戳内生效规另开新票",
            )
        return {
            "票号": 票号, "状态": "已下发", "幂等": True,
            "桶类型": 已["桶类型"], "规世代": 已["规世代"],
            "世代号": 已["戳世代号"], "集合哈希": 已["戳集合哈希"],
        }

    ver = conn.execute("SELECT * FROM 开关版本 WHERE 版本键=?", (版本键,)).fetchone()
    if not ver:
        raise HTTPException(400, f"版本未入轨:{版本键}")
    if ver["状态"] not in ("已入轨", "灰度中"):
        raise HTTPException(400, f"版本状态不可下发:{ver['状态']}")

    # 选规硬闸：无戳/错戳/归档/戳外/串键一律拒绝，票不落
    try:
        戳 = 选规闸(conn, ver["开关键"], 桶键)
    except 世代戳拒绝 as e:
        raise HTTPException(409, f"选规闸拒绝：{e}") from e

    bucket = conn.execute(
        "SELECT * FROM 分桶规 WHERE 桶键=? AND 开关键=?", (桶键, ver["开关键"])
    ).fetchone()
    if bucket["开关键"] != ver["开关键"]:
        raise HTTPException(400, "分桶开关键与版本不一致")

    conn.execute(
        """INSERT INTO 下发票(票号, 开关键, 版本键, 桶键, 桶类型, 规世代, 规更新时,
                            状态, 下发时, 世代, 说明, 戳世代号, 戳集合哈希, 戳时)
           VALUES (?,?,?,?,?,?,?, '已下发', ?, 1, ?, ?, ?, ?)
           ON CONFLICT(票号) DO UPDATE SET
             状态='已下发', 下发时=excluded.下发时, 世代=下发票.世代+1,
             桶类型=excluded.桶类型, 规世代=excluded.规世代, 规更新时=excluded.规更新时,
             戳世代号=excluded.戳世代号, 戳集合哈希=excluded.戳集合哈希, 戳时=excluded.戳时""",
        (票号, ver["开关键"], 版本键, 桶键, bucket["桶类型"], bucket["世代"], bucket["更新时"],
         此刻(), 体.get("说明", ""),
         戳["世代号"], 戳["集合哈希"], 戳["戳时"]),
    )
    conn.execute("UPDATE 开关版本 SET 状态='灰度中' WHERE 版本键=?", (版本键,))
    return {
        "票号": 票号, "状态": "已下发", "幂等": False,
        "桶类型": bucket["桶类型"], "规世代": bucket["世代"], "规更新时": bucket["更新时"],
        "世代号": 戳["世代号"], "集合哈希": 戳["集合哈希"], "戳时": 戳["戳时"],
        "生效集合": json.loads(戳["生效集合"]), "工单": "",
    }


def 下一票(体: dict) -> dict:
    """读规 + 验戳 + 落票同事务。写规并发时拿不到写锁 → 409，票不落、版本态不动。"""
    try:
        with 写事务() as conn:
            return _下一票(conn, 体)
    except 写锁冲突 as e:
        raise HTTPException(409, f"下发与写规并发，已失败闭：{e}") from e


def 装下发夹具(体: dict) -> dict:
    批次 = 体.get("批次编号") or f"下发-{此刻()}"
    结果 = []
    失败 = []
    for item in 体.get("下发") or []:
        try:
            结果.append(下一票(item))
        except HTTPException as e:
            失败.append({"票号": item.get("票号", ""), "桶键": item.get("桶键", ""),
                        "状态码": e.status_code, "原因": str(e.detail)})
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
