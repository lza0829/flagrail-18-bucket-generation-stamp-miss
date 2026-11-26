import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import 夹具目录, 连接
from app.services import 入轨, 分桶, 下发, 回读, 命运, 贯验, 目录
from app.modules import 分桶世代戳 as 世代戳

路由 = APIRouter(prefix="/api")


class 入轨请求(BaseModel):
    批次编号: str = ""
    版本: list = Field(default_factory=list)


class 分桶请求(BaseModel):
    桶键: str
    开关键: str
    桶类型: str = "百分比"
    规则: dict = Field(default_factory=dict)
    状态: str = "生效"


class 下发请求(BaseModel):
    票号: str = ""
    版本键: str
    桶键: str
    说明: str = ""


class 回读请求(BaseModel):
    证号: str = ""
    票号: str
    边缘键: str
    所见版本键: str = ""
    结果: str = "确认"
    说明: str = ""


class 归档请求(BaseModel):
    桶键: str
    说明: str = ""


class 回滚请求(BaseModel):
    票号: str
    说明: str = ""


class 失效请求(BaseModel):
    版本键: str
    说明: str = ""


@路由.get("/健康")
def 健康():
    return {
        "正常": True,
        "项目": "灰度轨",
        "领域": "基础设施",
        "子方向": "中间件",
        "骨架": "开关版本入轨→分桶灰度下发→回读确认→失效/回滚互证",
    }


@路由.get("/总览")
def 取总览():
    return 目录.总览()


@路由.get("/站规")
def 站规():
    conn = 连接()
    try:
        return {r["键"]: r["值"] for r in conn.execute("SELECT 键, 值 FROM 站规")}
    finally:
        conn.close()


@路由.get("/开关版本")
def 列版本(状态: str = ""):
    conn = 连接()
    try:
        if 状态:
            rows = conn.execute(
                "SELECT * FROM 开关版本 WHERE 状态=? ORDER BY 入轨时 DESC", (状态,)
            )
        else:
            rows = conn.execute("SELECT * FROM 开关版本 ORDER BY 入轨时 DESC")
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["载荷"] = json.loads(d["载荷"])
            except Exception:
                pass
            out.append(d)
        return out
    finally:
        conn.close()


@路由.get("/分桶规")
def 列分桶(状态: str = ""):
    """分桶规页：生效规在前，归档规随后列出（带归档时/归档因），页面不藏桶类型。"""
    conn = 连接()
    try:
        if 状态:
            rows = conn.execute(
                "SELECT * FROM 分桶规 WHERE 状态=? ORDER BY 更新时 DESC, 桶键", (状态,)
            )
        else:
            rows = conn.execute(
                "SELECT * FROM 分桶规 ORDER BY 状态<>'生效', 更新时 DESC, 桶键"
            )
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["规则"] = json.loads(d["规则"])
            except Exception:
                pass
            out.append(d)
        return out
    finally:
        conn.close()


@路由.get("/互斥核证")
def 互斥核证(开关键: str = ""):
    """核证口径：开关键 / 生效规列表 / 归档规 / 策略标记 / valid。留空或 * 为全站。"""
    return 分桶.做核证(None if 开关键 in ("", "*") else 开关键)


@路由.post("/分桶/归档")
def 归档分桶(体: 归档请求):
    try:
        return 分桶.归档桶(体.model_dump())
    except 分桶.互斥拒绝 as e:
        raise HTTPException(400, str(e))
    except 分桶.写锁冲突 as e:
        raise HTTPException(409, f"归档与写规并发，已失败闭：{e}")


@路由.get("/下发票")
def 列下发(状态: str = ""):
    conn = 连接()
    try:
        if 状态:
            rows = conn.execute(
                "SELECT * FROM 下发票 WHERE 状态=? ORDER BY 下发时 DESC", (状态,)
            )
        else:
            rows = conn.execute("SELECT * FROM 下发票 ORDER BY 下发时 DESC")
        return [dict(r) for r in rows]
    finally:
        conn.close()


@路由.get("/回读证")
def 列回读():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 回读证 ORDER BY 回读时 DESC LIMIT 200")]
    finally:
        conn.close()


@路由.get("/命运账")
def 列命运():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 命运账 ORDER BY 编号 DESC LIMIT 100")]
    finally:
        conn.close()


@路由.get("/批次")
def 列批次():
    conn = 连接()
    try:
        out = []
        for r in conn.execute("SELECT * FROM 装载批次 ORDER BY 时刻 DESC LIMIT 30"):
            d = dict(r)
            try:
                d["报告"] = json.loads(d["报告"])
            except Exception:
                pass
            out.append(d)
        return out
    finally:
        conn.close()


@路由.get("/空桩")
def 列空桩():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 空桩 ORDER BY 名")]
    finally:
        conn.close()


@路由.post("/入轨")
def 做入轨(体: 入轨请求):
    return 入轨.入一批(体.model_dump())


@路由.post("/分桶")
def 做分桶(体: 分桶请求):
    try:
        return 分桶.写桶(体.model_dump())
    except 分桶.互斥拒绝 as e:
        raise HTTPException(400, f"互斥口径拒绝：{e}")
    except 分桶.写锁冲突 as e:
        raise HTTPException(409, f"写规与下发并发，已失败闭：{e}")


@路由.post("/下发")
def 做下发(体: 下发请求):
    return 下发.下一票(体.model_dump())


@路由.post("/回读")
def 做回读(体: 回读请求):
    return 回读.记回读(体.model_dump())


@路由.post("/回滚")
def 做回滚(体: 回滚请求):
    return 命运.回滚票(体.model_dump())


@路由.post("/失效")
def 做失效(体: 失效请求):
    return 命运.失效版本(体.model_dump())


@路由.post("/装载/夹具")
def 装夹具(名: str = "入轨样例"):
    路径 = 夹具目录 / f"{名}.json"
    if not 路径.exists():
        raise HTTPException(404, f"夹具不存在:{名}")
    体 = json.loads(路径.read_text(encoding="utf-8"))
    类型 = 体.get("类型", "入轨")
    if 类型 == "入轨":
        return 入轨.入一批(体)
    if 类型 == "分桶":
        return 分桶.装一批(体)
    if 类型 == "互斥场景":
        return 分桶.跑互斥场景(体)
    if 类型 == "下发":
        return 下发.装下发夹具(体)
    if 类型 == "回读":
        return 回读.装回读夹具(体)
    if 类型 == "回滚":
        return 命运.回滚票(体)
    raise HTTPException(400, f"未知夹具类型:{类型}")


@路由.post("/贯验")
def 做贯验():
    return 贯验.跑贯验()


@路由.get("/贯验")
def 列贯验():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 轨贯验 ORDER BY 编号 DESC LIMIT 20")]
    finally:
        conn.close()


@路由.get("/核证/分桶世代")
def 取核证_18(键: str | None = None):
    """分桶世代戳只读核证：世代号、生效集合、工单有无、valid（含归档集/绑旧集票/历史）。"""
    conn = 连接()
    try:
        return 世代戳.核证(conn, 键)
    finally:
        conn.close()


@路由.get("/核证/分桶世代/历史")
def 戳历史_18(键: str, 限: int = 50):
    """分桶规页翻世代号：按开关键取世代戳历史（旧→新），每票带生效集与归档集。"""
    限 = max(1, min(int(限), 200))
    conn = 连接()
    try:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT 开关键, 世代号, 生效集合, 集合哈希, 戳时, 工单, 变更, 时刻, 载荷 "
                "FROM 分桶世代戳表 WHERE 开关键=? ORDER BY 世代号 DESC LIMIT ?",
                (键, 限),
            )
        ]
        for r in rows:
            try:
                r["生效集合"] = json.loads(r["生效集合"])
            except Exception:
                pass
            try:
                r["载荷"] = json.loads(r["载荷"])
            except Exception:
                pass
            r["工单有无"] = bool((r.get("工单") or "").strip())
        return {"开关键": 键, "口径": 世代戳.口径, "历史": rows}
    finally:
        conn.close()


@路由.post("/核证/分桶世代/巡检")
def 巡检核证_18(payload: dict | None = None):
    return 世代戳.巡检包(payload or {})

