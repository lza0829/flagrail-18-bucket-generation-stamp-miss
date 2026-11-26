"""名单百分比互斥：同一开关键下，百分比规与名单规不得并行生效。

落地的全局策略（策略键 `名单百分比互斥策略`）只有一种，即「乙：名单归档百分比」：

* 百分比 → 名单：名单写入成功，同键原百分比规**归档失效**；生效集只剩名单规。
* 名单 → 百分比：名单优先，百分比写入**整拒**（须先人工归档名单），生效集仍只有名单规。
* 同类型多桶：后写的桶接管，旧桶归档（归档因 = 同类型替换）。
* 下发只能点到生效规；点到归档规整拒。下发在写事务内读规并落票，票面烙下
  `桶类型 / 规世代 / 规更新时` 快照——写规与下发并发时，拿不到写锁的一方
  立即失败闭，不会出现「票按旧规、库按新规」的半截。

本模块不提供「甲：后写类型冲突整拒」。若站规里的策略键被改成乙以外的值，
核证直接判 valid=false，写规整拒——宁可停写，也不让两套口径并行。
"""

import json
from datetime import datetime, timezone

策略键 = "名单百分比互斥策略"
策略乙 = "名单归档百分比"
策略口径 = "名单写入成功则同键原百分比规归档失效，生效集只留名单规；百分比回写整拒（须先人工归档名单）。"
桶族 = ("百分比", "名单")
归档因_名单接管 = "名单接管"
归档因_同类型 = "同类型替换"
归档因_人工前缀 = "人工归档"


class 互斥拒绝(ValueError):
    """互斥口径拒绝写入。调用方翻译成 400，库不得留下半截。"""


def 此刻() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _解析(r) -> dict:
    d = dict(r)
    try:
        d["规则"] = json.loads(d["规则"])
    except Exception:
        pass
    return d


def 读策略标记(conn) -> dict:
    row = conn.execute("SELECT 值 FROM 站规 WHERE 键=?", (策略键,)).fetchone()
    值 = (row["值"] if row else "").strip()
    return {
        "键": 策略键,
        "值": 值,
        "口径": 策略口径,
        "valid": 值 == 策略乙,
    }


def _生效族(conn, 开关键: str) -> list:
    return [
        _解析(r)
        for r in conn.execute(
            "SELECT * FROM 分桶规 WHERE 开关键=? AND 状态='生效' AND 桶类型 IN (?,?) "
            "ORDER BY 更新时 DESC, 桶键",
            (开关键, 桶族[0], 桶族[1]),
        )
    ]


def _规范规则(桶类型: str, 规则: dict) -> dict:
    if not isinstance(规则, dict):
        raise 互斥拒绝("规则必须是对象")
    规则 = dict(规则)
    if 桶类型 == "百分比":
        比 = 规则.get("percent", 规则.get("百分比"))
        if isinstance(比, bool) or not isinstance(比, (int, float)) or not (0 <= 比 <= 100):
            raise 互斥拒绝("百分比规须带 percent（0..100）")
    elif 桶类型 == "名单":
        名单 = 规则.get("edges", 规则.get("名单"))
        if not isinstance(名单, list) or not 名单:
            raise 互斥拒绝("名单规须带非空 edges（或 名单）")
        if not all(isinstance(e, str) and e.strip() for e in 名单):
            raise 互斥拒绝("名单项必须是非空字符串")
        if len({e.strip() for e in 名单}) != len(名单):
            raise 互斥拒绝("名单项重复")
    return 规则


def _归档(conn, rows: list, 因: str, 时: str) -> list:
    归档 = []
    for r in rows:
        cur = conn.execute(
            "UPDATE 分桶规 SET 状态='已归档', 归档时=?, 归档因=?, 世代=世代+1 "
            "WHERE 桶键=? AND 状态='生效'",
            (时, 因, r["桶键"]),
        )
        if cur.rowcount:
            归档.append({"桶键": r["桶键"], "桶类型": r["桶类型"], "归档因": 因, "归档时": 时})
    return 归档


def _落库(conn, 开关键: str, 桶键: str, 桶类型: str, 规则: dict, 时: str) -> int:
    已 = conn.execute("SELECT 世代 FROM 分桶规 WHERE 桶键=?", (桶键,)).fetchone()
    世代 = (已["世代"] + 1) if 已 else 1
    conn.execute(
        """INSERT INTO 分桶规(桶键, 开关键, 桶类型, 规则, 状态, 更新时, 归档时, 归档因, 世代)
           VALUES (?,?,?,?, '生效', ?, '', '', ?)
           ON CONFLICT(桶键) DO UPDATE SET
             开关键=excluded.开关键, 桶类型=excluded.桶类型, 规则=excluded.规则,
             状态='生效', 更新时=excluded.更新时, 归档时='', 归档因='', 世代=excluded.世代""",
        (桶键, 开关键, 桶类型, json.dumps(规则, ensure_ascii=False), 时, 世代),
    )
    return 世代


def 写规(conn, 体: dict) -> dict:
    """在调用方提供的写事务内落一条分桶规。互斥族走口径，非互斥族原样落库。"""
    桶键 = (体.get("桶键") or "").strip()
    开关键 = (体.get("开关键") or "").strip()
    桶类型 = 体.get("桶类型", "百分比")
    if not 桶键 or not 开关键:
        raise 互斥拒绝("桶键与开关键必填")
    if 体.get("状态", "生效") != "生效":
        raise 互斥拒绝("互斥口只接受写入生效；归档须走 /api/分桶/归档 或由接管产生")

    规则 = 体.get("规则") or {}
    if isinstance(规则, str):
        try:
            规则 = json.loads(规则)
        except Exception:
            raise 互斥拒绝("规则不是合法 JSON")
    if 桶类型 not in 桶族:
        
        时 = 此刻()
        _规范 = 规则 if isinstance(规则, dict) else {}
        世代 = _落库(conn, 开关键, 桶键, 桶类型, _规范, 时)
        return {
            "桶键": 桶键, "开关键": 开关键, "桶类型": 桶类型, "状态": "生效",
            "世代": 世代, "互斥族": False, "归档": [], "归档因": "",
        }

    标记 = 读策略标记(conn)
    if not 标记["valid"]:
        raise 互斥拒绝(f"全局互斥策略不成立:{标记['值'] or '缺失'}")

    规则 = _规范规则(桶类型, 规则)
    时 = 此刻()
    生效 = _生效族(conn, 开关键)

    
    原 = conn.execute("SELECT * FROM 分桶规 WHERE 桶键=?", (桶键,)).fetchone()
    if 原 and 原["状态"] == "生效" and 原["桶类型"] == "名单" and 桶类型 == "百分比":
        raise 互斥拒绝(
            f"名单优先：桶键 {桶键} 当前生效为名单，不可原地改写为百分比；"
            "如确需退回百分比，先人工归档该名单"
        )

    他桶 = [r for r in 生效 if r["桶键"] != 桶键]
    归档 = []

    if 桶类型 == "百分比":
        名单 = [r for r in 他桶 if r["桶类型"] == "名单"]
        if 名单:
            raise 互斥拒绝(
                f"名单优先：开关键 {开关键} 的生效名单 {名单[0]['桶键']} 仍在，"
                "百分比写入整拒；如确需退回百分比，先人工归档该名单"
            )
        归档 = _归档(conn, [r for r in 他桶 if r["桶类型"] == "百分比"], 归档因_同类型, 时)
    else:  
        归档 = _归档(conn, [r for r in 他桶 if r["桶类型"] == "百分比"], 归档因_名单接管, 时)
        归档 += _归档(conn, [r for r in 他桶 if r["桶类型"] == "名单"], 归档因_同类型, 时)

    世代 = _落库(conn, 开关键, 桶键, 桶类型, 规则, 时)
    return {
        "桶键": 桶键,
        "开关键": 开关键,
        "桶类型": 桶类型,
        "状态": "生效",
        "世代": 世代,
        "互斥族": True,
        "归档": 归档,
        "归档因": "",
    }


def 人工归档(conn, 桶键: str, 说明: str = "") -> dict:
    row = conn.execute("SELECT * FROM 分桶规 WHERE 桶键=?", (桶键,)).fetchone()
    if not row:
        raise 互斥拒绝(f"分桶不存在:{桶键}")
    if row["状态"] != "生效":
        raise 互斥拒绝(f"分桶非生效态，不可归档:{桶键}:{row['状态']}")
    因 = f"{归档因_人工前缀}:{说明}" if 说明 else f"{归档因_人工前缀}:未注明"
    时 = 此刻()
    conn.execute(
        "UPDATE 分桶规 SET 状态='已归档', 归档时=?, 归档因=?, 世代=世代+1 WHERE 桶键=?",
        (时, 因, 桶键),
    )
    return {"桶键": 桶键, "开关键": row["开关键"], "桶类型": row["桶类型"], "状态": "已归档", "归档因": 因, "归档时": 时}


def _口径结局(生效: list) -> str:
    """两口径结局必须可区分：甲=两次写入后生效集仍含百分比；乙=不含。"""
    if any(r["桶类型"] == "百分比" for r in 生效):
        return "甲:含百分比"
    if any(r["桶类型"] == "名单" for r in 生效):
        return "乙:不含百分比"
    return "空:无生效规"


def 核证(conn, 开关键: str | None = None) -> dict:
    """核证接口口径：开关键、生效规列表、归档规、策略标记、valid。

    valid 只看「规集合」不变量；票据另列，给需要复核的归档票打标记。
    """
    标记 = 读策略标记(conn)
    if 开关键:
        键们 = [开关键]
    else:
        键们 = [
            r["开关键"]
            for r in conn.execute("SELECT DISTINCT 开关键 FROM 分桶规 ORDER BY 开关键")
        ]
        键们 = [k for k in 键们 if k]

    逐键 = []
    全局违规 = []
    生效全部 = []
    归档全部 = []
    for k in 键们:
        行 = [_解析(r) for r in conn.execute("SELECT * FROM 分桶规 WHERE 开关键=? ORDER BY 更新时, 桶键", (k,))]
        生效 = [r for r in 行 if r["状态"] == "生效" and r["桶类型"] in 桶族]
        归档 = [r for r in 行 if r["状态"] == "已归档" and r["桶类型"] in 桶族]
        违规 = []

        if len(生效) > 1:
            类 = sorted({r["桶类型"] for r in 生效})
            违规.append(
                "双规并行:{}({})".format(k, ",".join(f"{r['桶键']}/{r['桶类型']}" for r in 生效))
                + ("；双类型" if len(类) > 1 else "；同类型")
            )

        for r in 归档:
            if not (r.get("归档时") or "") or not (r.get("归档因") or ""):
                违规.append(f"归档缺字段:{r['桶键']}")
                continue
            因 = r["归档因"]
            if 因 == 归档因_名单接管 and r["桶类型"] != "百分比":
                违规.append(f"名单接管标记挂在非百分比:{r['桶键']}")
            
            
            if r["桶类型"] == "名单" and not 因.startswith(归档因_人工前缀):
                违规.append(f"名单规被自动归档（乙口径只允许人工归档名单）:{r['桶键']}")

        if not 标记["valid"]:
            违规.append(f"策略标记不成立:{标记['值'] or '缺失'}")

        票据 = []
        for t in conn.execute(
            "SELECT t.票号, t.状态, t.桶键, t.桶类型, t.规世代, t.下发时, b.状态 AS 桶状态 "
            "FROM 下发票 t LEFT JOIN 分桶规 b ON b.桶键=t.桶键 WHERE t.开关键=? ORDER BY t.下发时",
            (k,),
        ):
            d = dict(t)
            if d["状态"] == "已下发" and d["桶状态"] == "已归档":
                d["需复核"] = "票据桶已归档"
            票据.append(d)

        逐键.append(
            {
                "开关键": k,
                "生效规": 生效,
                "归档规": 归档,
                "生效含百分比": any(r["桶类型"] == "百分比" for r in 生效),
                "生效桶类型": sorted({r["桶类型"] for r in 生效}),
                "口径结局": _口径结局(生效),
                "票据": 票据,
                "valid": not 违规,
                "违规": 违规,
            }
        )
        生效全部 += 生效
        归档全部 += 归档
        全局违规 += 违规

    return {
        "策略标记": 标记,
        "范围": 开关键 or "*",
        "valid": not 全局违规,
        "开关键们": 逐键,
        "生效规": 生效全部,
        "归档规": 归档全部,
        "违规": 全局违规,
    }
