"""名单百分比互斥 · 核证与双序写入自动化。

用法（在仓库根目录）：
    python3 backend/scripts/核证_名单百分比互斥.py            # 全量演练
    python3 backend/scripts/核证_名单百分比互斥.py --保留库   # 保留临时库以便排查

依赖：fastapi / pydantic（与 backend/requirements.txt 一致）。用 TestClient 直打路由，
每次都在全新的临时库上跑，不碰 backend/data 下的既有数据。任一步断言失败即以非零码退出。

断言覆盖：
  1. 百分比 → 名单：写入后生效集不含百分比（乙口径），原百分比归档且归档字段齐全；
  2. 名单 → 百分比：百分比写入整拒，生效集仍只含名单（同一全局策略）；
  3. 下发点到归档规：必须失败，且不落票；
  4. 双序脚本：任一开关键在两次写入后生效互斥族规恰一条，绝无双类型并行；
  5. 写规与下发并发：一方必须失败闭（409），不得出现「票按旧规、库按新规」；
  6. 核证接口字段齐套：开关键 / 生效规列表 / 归档规 / 策略标记 / valid。
"""
import argparse
import json
import os
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

仓库根 = Path(__file__).resolve().parents[2]
后端 = 仓库根 / "backend"
for _p in (str(后端),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

失败 = []


def 断言(条件: bool, 说明: str) -> None:
    if 条件:
        print(f"  ✓ {说明}")
    else:
        print(f"  ✗ {说明}")
        失败.append(说明)


def 建站(临时目录: str):
    os.environ["数据目录"] = 临时目录
    os.environ["夹具目录"] = str(仓库根 / "fixtures")
    from fastapi.testclient import TestClient

    from app import seed
    from app.main import app

    seed.初始化库()
    return TestClient(app)


def 取核证(client, 开关键: str) -> dict:
    r = client.get("/api/互斥核证", params={"开关键": 开关键})
    assert r.status_code == 200, r.text
    return r.json()


def 写(client, 体: dict):
    return client.post("/api/分桶", json=体)


def 百分比(键: str, 开关键: str, 比: int = 10) -> dict:
    return {"桶键": 键, "开关键": 开关键, "桶类型": "百分比", "规则": {"percent": 比, "salt": "s"}}


def 名单(键: str, 开关键: str) -> dict:
    return {"桶键": 键, "开关键": 开关键, "桶类型": "名单", "规则": {"edges": ["edge-a", "edge-b"]}}


def 场景_核证字段(client) -> None:
    print("\n[1] 核证接口字段齐套")
    k = "ver.check"
    写(client, 百分比(f"{k}-p", k))
    核 = 取核证(client, k)
    for 字段 in ("策略标记", "开关键们", "生效规", "归档规", "valid"):
        断言(字段 in 核, f"核证含字段「{字段}」")
    键 = 核["开关键们"][0]
    for 字段 in ("开关键", "生效规", "归档规", "口径结局", "valid"):
        断言(字段 in 键, f"逐键含字段「{字段}」")
    断言(核["策略标记"]["值"] == "名单归档百分比" and 核["策略标记"]["valid"], "策略标记=名单归档百分比 且 valid")


def 场景_百分比转名单(client) -> None:
    print("\n[2] 夹具：百分比 → 名单（乙口径）")
    k = "seq.pct2list"
    assert 写(client, 百分比(f"{k}-p", k, 10)).status_code == 200
    前 = 取核证(client, k)
    断言(前["开关键们"][0]["生效含百分比"], "写前生效集含百分比")

    r = 写(client, 名单(f"{k}-l", k))
    断言(r.status_code == 200, "名单写入成功")
    后 = 取核证(client, k)
    键 = 后["开关键们"][0]
    断言(not 键["生效含百分比"], "两次写入后生效集不含百分比（乙）")
    断言(键["口径结局"] == "乙:不含百分比", f"口径结局可区分：{键['口径结局']}")
    断言([x["桶键"] for x in 键["生效规"]] == [f"{k}-l"], "生效集恰为名单规")
    归 = [x for x in 键["归档规"] if x["桶键"] == f"{k}-p"]
    断言(bool(归) and 归[0]["归档因"] == "名单接管" and 归[0]["归档时"], "原百分比归档且归档字段齐全")
    断言(后["valid"] and 键["valid"], "核证 valid=true")
    断言(后["策略标记"]["valid"], "策略标记 valid")


def 场景_名单转百分比(client) -> None:
    print("\n[3] 夹具：名单 → 百分比（同一全局策略，整拒）")
    k = "seq.list2pct"
    assert 写(client, 名单(f"{k}-l", k)).status_code == 200
    r = 写(client, 百分比(f"{k}-p", k, 20))
    断言(r.status_code == 400, f"百分比回写被拒（HTTP {r.status_code}）")
    断言("名单优先" in r.text, f"拒绝原因可读：{r.text[:80]}")
    键 = 取核证(client, k)["开关键们"][0]
    断言([x["桶键"] for x in 键["生效规"]] == [f"{k}-l"], "生效集仍只含名单")
    断言(not 键["生效含百分比"], "生效集不含百分比")
    断言(键["valid"], "核证 valid")


def 场景_下发归档规(client) -> None:
    print("\n[4] 下发点归档规必须失败")
    k = "dl.archive"
    client.post("/api/入轨", json={"批次编号": "核证-入轨", "版本": [
        {"开关键": k, "版本号": 1, "版本键": f"{k}@1", "载荷": {"enabled": True}}]})
    assert 写(client, 百分比(f"{k}-p", k)).status_code == 200
    assert 写(client, 名单(f"{k}-l", k)).status_code == 200  

    r = client.post("/api/下发", json={"票号": "票-归档", "版本键": f"{k}@1", "桶键": f"{k}-p"})
    断言(r.status_code == 409, f"下发归档规 → {r.status_code}")
    断言("已归档" in r.text, f"失败原因点明归档：{r.text[:90]}")
    票 = client.get("/api/下发票").json()
    断言(all(t["票号"] != "票-归档" for t in 票), "失败不落票")

    ok = client.post("/api/下发", json={"票号": "票-名单", "版本键": f"{k}@1", "桶键": f"{k}-l"})
    断言(ok.status_code == 200 and ok.json()["桶类型"] == "名单", "名单规可下发且票面桶类型=名单")
    断言(ok.json()["规世代"] >= 1 and ok.json()["规更新时"], "票面烙下规世代与规更新时")


def 场景_夹具双序(client) -> None:
    print("\n[5] 夹具双序（可重复演练）")
    client.post("/api/入轨", json={"批次编号": "核证-入轨2", "版本": [
        {"开关键": "mutex.pct2list", "版本号": 1, "版本键": "mutex.pct2list@1", "载荷": {}},
        {"开关键": "mutex.list2pct", "版本号": 1, "版本键": "mutex.list2pct@1", "载荷": {}}]})

    r1 = client.post("/api/装载/夹具", params={"名": "互斥-百分比转名单"})
    断言(r1.status_code == 200 and r1.json()["valid"], "百分比→名单夹具 valid")
    e1 = r1.json()["生效集"]["mutex.pct2list"]
    断言(e1["桶类型"] == ["名单"] and not e1["生效含百分比"], f"百分比→名单 生效={e1}")

    r2 = client.post("/api/装载/夹具", params={"名": "互斥-名单转百分比"})
    断言(r2.status_code == 200 and r2.json()["valid"], "名单→百分比夹具 valid")
    e2 = r2.json()["生效集"]["mutex.list2pct"]
    断言(e2["桶类型"] == ["名单"] and not e2["生效含百分比"], f"名单→百分比 生效={e2}")
    步 = r2.json()["步骤"]
    断言(any(s.get("桶类型") == "百分比" and s["结果"] == "拒" for s in 步), "夹具内百分比回写被记成「拒」")

    r3 = client.post("/api/装载/夹具", params={"名": "互斥-下发归档规"})
    报 = r3.json()["报告"]
    断言(len(报["结果"]) == 0 and len(报["失败"]) == 1, f"下发归档规夹具失败：{报.get('失败')}")


def 场景_并发(client, 临时目录: str) -> None:
    print("\n[6] 写规与下发并发 → 失败闭")
    k = "race.key"
    client.post("/api/入轨", json={"批次编号": "核证-入轨3", "版本": [
        {"开关键": k, "版本号": 1, "版本键": f"{k}@1", "载荷": {}}]})
    assert 写(client, 百分比(f"{k}-p", k)).status_code == 200

    
    库 = Path(临时目录) / "灰度轨.db"
    holder = sqlite3.connect(库, timeout=0, isolation_level=None)
    holder.execute("PRAGMA foreign_keys = ON")
    holder.execute("BEGIN IMMEDIATE")
    try:
        r = client.post("/api/下发", json={"票号": "票-并发", "版本键": f"{k}@1", "桶键": f"{k}-p"})
        断言(r.status_code == 409, f"下发遇写锁 → {r.status_code}")
        票 = client.get("/api/下发票").json()
        断言(all(t["票号"] != "票-并发" for t in 票), "失败闭：不落半截票")
        w = 写(client, 名单(f"{k}-l", k))
        断言(w.status_code == 409, f"写规遇写锁 → {w.status_code}")
    finally:
        holder.execute("ROLLBACK")
        holder.close()

    键 = 取核证(client, k)["开关键们"][0]
    断言(键["生效桶类型"] == ["百分比"] and 键["valid"], "锁释放后库仍是单一生效规，无半截")
    断言(写(client, 名单(f"{k}-l", k)).status_code == 200, "串行后名单写入成功")
    断言(not 取核证(client, k)["开关键们"][0]["生效含百分比"], "串行后仍满足乙口径")


def 场景_站规策略被改(client, 临时目录: str) -> None:
    print("\n[7] 策略标记被改坏 → 停写（valid=false）")
    k = "policy.tamper"
    assert 写(client, 百分比(f"{k}-p", k)).status_code == 200
    库 = Path(临时目录) / "灰度轨.db"
    c = sqlite3.connect(库)
    c.execute("UPDATE 站规 SET 值='后写类型整拒' WHERE 键='名单百分比互斥策略'")
    c.commit()
    c.close()
    r = 写(client, 名单(f"{k}-l", k))
    断言(r.status_code == 400, f"策略不成立时写规被拒 → {r.status_code}")
    核证_ = 取核证(client, k)
    断言(not 核证_["valid"] and not 核证_["策略标记"]["valid"], "核证 valid=false，标记暴露")
    c = sqlite3.connect(库)
    c.execute("UPDATE 站规 SET 值='名单归档百分比' WHERE 键='名单百分比互斥策略'")
    c.commit()
    c.close()


def 场景_人工归档回归(client) -> None:
    """名单人工归档后百分比可回写；票据在规漂移后的确认回读必须转「偏差」。"""
    print("\n[8] 人工归档回写 + 回读漂移")
    k = "regress.back"
    client.post("/api/入轨", json={"批次编号": "核证-入轨4", "版本": [
        {"开关键": k, "版本号": 1, "版本键": f"{k}@1", "载荷": {}}]})
    assert 写(client, 百分比(f"{k}-p", k, 5)).status_code == 200
    r = client.post("/api/下发", json={"票号": "票-漂移", "版本键": f"{k}@1", "桶键": f"{k}-p"})
    断言(r.status_code == 200 and r.json()["桶类型"] == "百分比", "百分比规可下发")

    assert 写(client, 名单(f"{k}-l", k)).status_code == 200  
    rr = client.post("/api/回读", json={"票号": "票-漂移", "边缘键": "edge-a"}).json()
    断言(rr["结果"] == "偏差" and "规漂移" in rr["说明"], f"票落归档规后确认回读转偏差：{rr['说明']}")

    a = client.post("/api/分桶/归档", json={"桶键": f"{k}-l", "说明": "退回百分比"})
    断言(a.status_code == 200 and a.json()["归档因"].startswith("人工归档"), "名单可人工归档")
    w = 写(client, 百分比(f"{k}-p2", k, 7))
    断言(w.status_code == 200, "名单人工归档后百分比可回写")
    键 = 取核证(client, k)["开关键们"][0]
    断言(键["生效桶类型"] == ["百分比"] and 键["valid"], "回写后生效集仅百分比且 valid（不误报悬空）")

    
    k2 = "regress.inplace"
    assert 写(client, 名单(f"{k2}-x", k2)).status_code == 200
    flip = 写(client, {**百分比(f"{k2}-x", k2, 3)})
    断言(flip.status_code == 400 and "原地改写" in flip.text, f"名单原地改百分比被拒：{flip.status_code}")
    键2 = 取核证(client, k2)["开关键们"][0]
    断言(键2["生效桶类型"] == ["名单"] and 键2["valid"], "原地改写被拒后仍是名单")

    
    g = client.post("/api/贯验").json()
    断言(not g["是否通过"] and "下发落在归档规" in g["说明"], f"未收口时贯验亮红：{g['说明'][:60]}")
    client.post("/api/回滚", json={"票号": "票-漂移", "说明": "票据换规后收口"})
    g2 = client.post("/api/贯验").json()
    断言("下发落在归档规" not in g2["说明"], "票据收口后不再报归档规下发")


def 场景_全站无双类型并行(client) -> None:
    """双序脚本断言收口：核证范围内任何开关键都不得两种桶类型同时生效。"""
    print("\n[9] 全站扫描：不得双类型同时生效")
    核 = 取核证(client, "*")
    坏 = [k for k in 核["开关键们"] if len(k["生效桶类型"]) > 1]
    断言(not 坏, f"无双类型并行的开关键（{len(核['开关键们'])} 个已核）")
    超一 = [k["开关键"] for k in 核["开关键们"] if len(k["生效规"]) > 1]
    断言(not 超一, "每开关键生效互斥族规至多一条")
    断言(核["valid"], "全站核证 valid")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--保留库", action="store_true")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as 临时:
        client = 建站(临时)
        场景_核证字段(client)
        场景_百分比转名单(client)
        场景_名单转百分比(client)
        场景_下发归档规(client)
        场景_夹具双序(client)
        场景_并发(client, 临时)
        场景_站规策略被改(client, 临时)
        场景_人工归档回归(client)
        场景_全站无双类型并行(client)

        g = client.post("/api/贯验").json()
        断言(g["是否通过"], f"最终贯验通过：{g['说明']}")
        if args.保留库:
            print(f"\n临时库：{Path(临时) / '灰度轨.db'}")

    print()
    if 失败:
        print(f"FAIL · {len(失败)} 条断言未过")
        for f in 失败:
            print(f"  - {f}")
        return 1
    print("PASS · 名单百分比互斥核证全绿")
    return 0


if __name__ == "__main__":
    sys.exit(main())
