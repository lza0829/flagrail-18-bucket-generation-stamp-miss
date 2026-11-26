from app.db import 连接
from app.modules.名单百分比互斥 import 读策略标记
from app.modules.分桶世代戳 import 核证 as 戳核证


def 总览() -> dict:
    conn = 连接()
    try:
        def c(sql: str) -> int:
            return conn.execute(sql).fetchone()[0]

        标记 = 读策略标记(conn)
        戳 = 戳核证(conn)
        return {
            "开关版本": c("SELECT COUNT(*) FROM 开关版本"),
            "分桶规": c("SELECT COUNT(*) FROM 分桶规 WHERE 状态='生效'"),
            "归档规": c("SELECT COUNT(*) FROM 分桶规 WHERE 状态='已归档'"),
            "名单百分比互斥valid": 标记["valid"],
            "名单百分比互斥策略": 标记["值"],
            "世代戳valid": 戳["valid"],
            "世代戳口径": 戳["口径"],
            "世代戳键数": len(戳["开关键们"]),
            "下发票": c("SELECT COUNT(*) FROM 下发票"),
            "已下发": c("SELECT COUNT(*) FROM 下发票 WHERE 状态='已下发'"),
            "回读证": c("SELECT COUNT(*) FROM 回读证"),
            "确认回读": c("SELECT COUNT(*) FROM 回读证 WHERE 结果='确认'"),
            "命运条": c("SELECT COUNT(*) FROM 命运账"),
            "最近贯验通过": bool(
                (conn.execute(
                    "SELECT 是否通过 FROM 轨贯验 ORDER BY 编号 DESC LIMIT 1"
                ).fetchone() or [0])[0]
            ),
        }
    finally:
        conn.close()

