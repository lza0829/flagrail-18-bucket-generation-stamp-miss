from app.db import 写锁冲突, 写事务
from app.modules.名单百分比互斥 import 互斥拒绝, 人工归档, 核证, 写规
from app.modules.分桶世代戳 import 落戳, 戳写入失败
__all__ = ["写桶", "归档桶", "做核证", "互斥拒绝", "写锁冲突"]


def 写桶(体: dict) -> dict:
    """写一条分桶规。互斥族的接管/归档、写入与世代戳同票落库。

    硬约束：规写入成功必须同票落世代戳；落戳失败整笔回滚——禁止规生效而戳空。
    """
    try:
        with 写事务() as conn:
            回 = 写规(conn, 体)
            戳 = 落戳(conn, 回["开关键"], 变更=f"写规:{回['桶键']}/{回['桶类型']}")
            回["世代戳"] = 戳
            return 回
    except 写锁冲突 as e:
        raise 写锁冲突(f"写规并发，已失败闭：{e}") from e
    except 戳写入失败 as e:
        # 落戳在写事务内抛出 → 事务已回滚，规不会半截生效
        raise 互斥拒绝(f"世代戳同票落库失败，写规整票回滚：{e}") from e


def 归档桶(体: dict) -> dict:
    try:
        with 写事务() as conn:
            回 = 人工归档(conn, 体["桶键"], 体.get("说明", ""))
            # 归档改变生效集 → 必须同票升戳，否则下发还会按旧集选规
            戳 = 落戳(conn, 回["开关键"], 变更=f"人工归档:{回['桶键']}")
            回["世代戳"] = 戳
            return 回
    except KeyError:
        raise 互斥拒绝("桶键必填")
    except 戳写入失败 as e:
        raise 互斥拒绝(f"世代戳同票落库失败，归档整票回滚：{e}") from e


def 做核证(开关键: str | None = None) -> dict:
    from app.db import 连接

    conn = 连接()
    try:
        return 核证(conn, 开关键)
    finally:
        conn.close()


def 装一批(体: dict) -> dict:
    """夹具：逐条写桶，单条被拒记入报告而不中断整批（每条各自成事务）。
    批次报告里给出最终生效集，供「不得双类型同时生效」断言使用。"""
    结果 = []
    拒 = []
    for x in 体.get("分桶") or []:
        try:
            结果.append(写桶(x))
        except (互斥拒绝, 写锁冲突) as e:
            拒.append({"桶键": x.get("桶键", ""), "原因": str(e)})
    键们 = sorted({x.get("开关键") for x in (体.get("分桶") or []) if x.get("开关键")})
    核 = {k: 做核证(k) for k in 键们}
    return {
        "类型": "分桶",
        "结果": 结果,
        "拒": 拒,
        "生效集": {k: [r["桶键"] for r in v["生效规"]] for k, v in 核.items()},
        "valid": all(v["valid"] for v in 核.values()),
    }


def 跑互斥场景(体: dict) -> dict:
    """互斥两序夹具：逐条「可选重置 → 写规」，把拒绝也记成一步，别让整批中断。

    每条 `分桶` 项可带 `"先归档": true`，表示先人工归档该开关键下所有生效规
    （归档因=人工归档:夹具重置），使同一夹具可重复演练。
    """
    步 = []
    for x in 体.get("分桶") or []:
        开关键 = x.get("开关键", "")
        步项 = {"开关键": 开关键, "桶键": x.get("桶键", ""), "桶类型": x.get("桶类型", "")}
        if x.get("先归档"):
            try:
                with 写事务() as conn:
                    现 = [
                        dict(r)["桶键"]
                        for r in conn.execute(
                            "SELECT 桶键 FROM 分桶规 WHERE 开关键=? AND 状态='生效'", (开关键,)
                        )
                    ]
                    for 键 in 现:
                        人工归档(conn, 键, "夹具重置")
                    if 现:
                        步项["重置戳"] = 落戳(conn, 开关键, 变更="夹具重置归档")
                步项["重置归档"] = 现
            except 写锁冲突 as e:
                步项.update(结果="失败闭", 原因=str(e))
                步.append(步项)
                continue
        try:
            步项.update(结果="生效", 写入=写桶(x))
        except (互斥拒绝, 写锁冲突) as e:
            步项.update(结果="拒", 原因=str(e))
        步.append(步项)
    键们 = sorted({s["开关键"] for s in 步 if s["开关键"]})
    核 = {k: (做核证(k)["开关键们"] or [{}])[0] for k in 键们}
    return {
        "类型": "互斥场景",
        "批次编号": 体.get("批次编号", ""),
        "步骤": 步,
        "生效集": {
            k: {
                "桶键": [r["桶键"] for r in v["生效规"]],
                "桶类型": v["生效桶类型"],
                "生效含百分比": v["生效含百分比"],
                "归档规": [r["桶键"] for r in v["归档规"]],
                "valid": v["valid"],
            }
            for k, v in 核.items()
        },
        "valid": all(v["valid"] for v in 核.values()),
    }
