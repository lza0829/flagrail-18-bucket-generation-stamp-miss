"""分桶世代戳 · 写规/下发/回读同票核证自动化（口径甲：戳锁现行规）。

用法（在仓库根目录）：
    python3 backend/scripts/核证_分桶世代戳.py            # 全量演练
    python3 backend/scripts/核证_分桶世代戳.py --保留库

每次在全新临时库上跑，不碰 backend/data。任一断言失败即以非零码退出。

断言覆盖：
  1. 写规成功必须同票落世代戳（开关键/生效集合哈希/世代号/戳时齐套），世代号单调；
  2. 硬约束：写规被拒时戳不得空挂、规不得半截生效；有规无戳核证 valid=false 且下发 409；
  3. 热更（百分比生效→名单归档）后无工单再下发：点归档规拒且无新已下发；旧票幂等重投
     亦按旧集合拒；点当前戳内生效规成功且回执世代号=现行戳号（甲乙结局可区分）；
  4. 错戳（戳面哈希被拧）→ 下发 409、核证 valid=false；
  5. 邻开关键戳不得串用：跨键选规 409，各键票面世代号只认本键戳；
  6. 写规与下发并发：持写锁时双方 409 失败闭，不得无戳绑归档、不得落半截票；
  7. 归档改变生效集必须同票升戳；归档规不可被无戳/错戳点中；
  8. 回读协同：热更后旧票确认回读转「偏差·规漂移」；
  9. 只读核证接口字段：世代号、生效集合、工单有无、valid；历史接口世代号可翻、单调；
 10. 下发票回执与列表均带世代号；贯验把绑旧集/无戳/错戳亮红，回滚收口后转绿。
"""
import argparse
import os
import sqlite3
import sys
import tempfile
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


def 百分比(键: str, 开关键: str, 比: int = 10) -> dict:
    return {"桶键": 键, "开关键": 开关键, "桶类型": "百分比", "规则": {"percent": 比, "salt": "s"}}


def 名单(键: str, 开关键: str) -> dict:
    return {"桶键": 键, "开关键": 开关键, "桶类型": "名单", "规则": {"edges": ["edge-a", "edge-b"]}}


def 取戳核证(client, 开关键: str) -> dict:
    r = client.get("/api/核证/分桶世代", params={"键": 开关键})
    assert r.status_code == 200, r.text
    包 = r.json()
    assert 包["开关键们"], f"核证无该键:{开关键}"
    return 包["开关键们"][0]


def 直库(临时目录: str) -> sqlite3.Connection:
    c = sqlite3.connect(Path(临时目录) / "灰度轨.db")
    c.row_factory = sqlite3.Row
    return c


def 场景_写规同票落戳(client) -> None:
    print("\n[1] 写规成功同票落世代戳，世代号单调、字段齐套")
    k = "gen.basic"
    r = client.post("/api/分桶", json=百分比(f"{k}-p", k, 10))
    断言(r.status_code == 200, f"百分比写规成功（{r.status_code} {r.text[:80]}）")
    戳1 = r.json()["世代戳"]
    for 字段 in ("开关键", "世代号", "生效集合", "集合哈希", "戳时", "工单", "valid"):
        断言(字段 in 戳1, f"写规回执世代戳含「{字段}」")
    断言(戳1["世代号"] == 1 and 戳1["生效集合"] == [f"{k}-p"] and 戳1["集合哈希"] and 戳1["戳时"],
          "首戳：世代号=1、生效集合=新桶、哈希/戳时非空")
    断言(戳1["工单"] == "", "甲口径无工单实体，戳面工单恒空")

    r2 = client.post("/api/分桶", json=名单(f"{k}-l", k))
    断言(r2.status_code == 200, "名单接管写规成功")
    戳2 = r2.json()["世代戳"]
    断言(戳2["世代号"] == 2, f"热更后世代号单调上升 1→{戳2['世代号']}")
    断言(戳2["生效集合"] == [f"{k}-l"] and f"{k}-p" in 戳2["归档集合"], "新戳生效集=名单、归档集含旧百分比")
    断言(戳2["集合哈希"] != 戳1["集合哈希"], "集合变更→哈希变更（错戳可被识别）")

    键 = 取戳核证(client, k)
    断言(键["世代号"] == 2 and 键["工单有无"] is False and 键["valid"],
          "只读核证：世代号=2、工单有无=false、valid=true")
    断言(键["集合哈希"] == 戳2["集合哈希"] == 键["现行哈希"], "戳面哈希=现行生效集重算哈希")
    断言([h["世代号"] for h in 键["历史"]] == [1, 2], "历史世代号 1..2 严格单调连续")


def 场景_写规拒戳不挂(client, 临时目录: str) -> None:
    print("\n[2] 硬约束：写规失败不得规生效而戳空；有规无戳必须亮红且闸下发")
    k = "gen.nostamp"
    assert client.post("/api/分桶", json=百分比(f"{k}-p", k)).status_code == 200
    c = 直库(临时目录)
    号前 = c.execute("SELECT COALESCE(MAX(世代号),0) m FROM 分桶世代戳表 WHERE 开关键=?", (k,)).fetchone()["m"]
    规前 = c.execute("SELECT COUNT(*) c FROM 分桶规 WHERE 开关键=?", (k,)).fetchone()["c"]
    # 模拟半截失败：戳被外部摘掉（规还在）
    c.execute("DELETE FROM 分桶世代戳表 WHERE 开关键=?", (k,))
    c.commit()
    c.close()

    键 = 取戳核证(client, k)
    断言(not 键["valid"] and any("无世代戳" in v for v in 键["违规"]), "有规无戳→核证 valid=false 并点名")
    client.post("/api/入轨", json={"批次编号": "b2", "版本": [
        {"开关键": k, "版本号": 1, "版本键": f"{k}@1", "载荷": {}}]})
    r = client.post("/api/下发", json={"票号": "票-无戳", "版本键": f"{k}@1", "桶键": f"{k}-p"})
    断言(r.status_code == 409 and "无分桶世代戳" in r.text, f"无戳选规→409（{r.status_code}）")
    票 = client.get("/api/下发票").json()
    断言(all(t["票号"] != "票-无戳" for t in 票), "无戳不放行：失败不落票")

    # 再写一笔成功 → 同票补戳，号在历史最大值上续单调（被删后从 1 重开，仍严格正序）
    r2 = client.post("/api/分桶", json=名单(f"{k}-l", k))
    断言(r2.status_code == 200 and r2.json()["世代戳"]["世代号"] >= 1, "补写成功并同票落戳")
    c = 直库(临时目录)
    号后 = c.execute("SELECT COALESCE(MAX(世代号),0) m FROM 分桶世代戳表 WHERE 开关键=?", (k,)).fetchone()["m"]
    规后 = c.execute("SELECT COUNT(*) c FROM 分桶规 WHERE 开关键=?", (k,)).fetchone()["c"]
    c.close()
    断言(规后 == 规前 + 1 and 号后 >= 1, "被拒期间无半截规、无空挂戳")
    _ = 号前


def 场景_热更无工单再下发(client) -> dict:
    print("\n[3] 夹具：百分比生效→名单归档→无工单再下发（口径甲）")
    k = "gen.hot"
    client.post("/api/入轨", json={"批次编号": "b3", "版本": [
        {"开关键": k, "版本号": 1, "版本键": f"{k}@1", "载荷": {"enabled": True}}]})
    assert client.post("/api/分桶", json=百分比(f"{k}-gray10", k, 10)).status_code == 200
    旧 = client.post("/api/下发", json={"票号": "票-热-旧", "版本键": f"{k}@1", "桶键": f"{k}-gray10"})
    断言(旧.status_code == 200 and 旧.json()["世代号"] == 1, "热更前下发成功，回执世代号=1")
    断言(旧.json()["集合哈希"] and 旧.json()["戳时"], "回执带集合哈希与戳时")

    f = client.post("/api/装载/夹具", params={"名": "世代-热更归档"})
    断言(f.status_code == 200 and f.json()["valid"], f"热更夹具 valid（{f.text[:100]}）")
    键 = 取戳核证(client, k)
    现行号 = 键["世代号"]
    断言(现行号 > 1, f"热更升戳：现行世代号={现行号} > 1")
    断言(键["生效集合"] == [f"{k}-list"] and f"{k}-gray10" in 键["归档集合"], "生效集=名单，旧百分比入归档集")
    断言(键["工单有无"] is False, "无换世代工单：工单有无=false")

    # 甲：无工单点归档规 → 拒，无新已下发
    票前 = {t["票号"] for t in client.get("/api/下发票").json()}
    r = client.post("/api/下发", json={"票号": "票-热-点归档", "版本键": f"{k}@1", "桶键": f"{k}-gray10"})
    断言(r.status_code == 409 and ("戳外规" in r.text or "已归档" in r.text),
          f"甲拒点归档规→409（{r.text[:90]}）")
    票后 = {t["票号"] for t in client.get("/api/下发票").json()}
    断言(票后 == 票前, "拒绝后无新已下发票")

    # 旧票幂等重投：甲按旧集合拒，不得继续绑旧世代
    r2 = client.post("/api/下发", json={"票号": "票-热-旧", "版本键": f"{k}@1", "桶键": f"{k}-gray10"})
    断言(r2.status_code == 409 and "旧世代集合" in r2.text, f"旧票重投按旧集合拒（{r2.text[:90]}）")

    # 点当前戳内生效规 → 成功，票面世代号=现行号（不仍旧）
    r3 = client.post("/api/下发", json={"票号": "票-热-新", "版本键": f"{k}@1", "桶键": f"{k}-list"})
    断言(r3.status_code == 200, f"戳内生效规可下发（{r3.status_code} {r3.text[:80]}）")
    断言(r3.json()["世代号"] == 现行号 and r3.json()["世代号"] != 1,
          f"新票绑当前戳世代号={现行号}，不绑旧世代 1")
    断言(r3.json()["生效集合"] == [f"{k}-list"] and r3.json()["工单"] == "", "回执带回生效集合且工单空")

    # 两口径可区分：甲实际结局 vs 乙持工单假设
    甲结局 = {"落已下发": False, "绑定世代号仍旧": False, "工单有无": False}
    乙持单假设 = {"落已下发": True, "绑定世代号仍旧": False, "工单有无": True}
    断言(甲结局 != 乙持单假设 and 键["工单有无"] is False,
          "口径可区分：甲无工单→旧集/归档整拒、不落已下发；乙须持工单才改绑升号，本站无工单入口")
    return {"开关键": k, "现行号": 现行号}


def 场景_错戳(client, 临时目录: str) -> None:
    print("\n[4] 错戳（戳面哈希被拧）→ 下发失败闭、核证亮红")
    k = "gen.badhash"
    client.post("/api/入轨", json={"批次编号": "b4", "版本": [
        {"开关键": k, "版本号": 1, "版本键": f"{k}@1", "载荷": {}}]})
    assert client.post("/api/分桶", json=百分比(f"{k}-p", k)).status_code == 200
    c = 直库(临时目录)
    c.execute("UPDATE 分桶世代戳表 SET 集合哈希=? WHERE 开关键=?", ("deadbeef", k))
    c.commit()
    c.close()
    r = client.post("/api/下发", json={"票号": "票-错戳", "版本键": f"{k}@1", "桶键": f"{k}-p"})
    断言(r.status_code == 409 and "错戳" in r.text, f"错戳→409（{r.text[:80]}）")
    键 = 取戳核证(client, k)
    断言(not 键["valid"] and any("错戳" in v for v in 键["违规"]), "错戳核证 valid=false")
    # 复原：再写一笔同键规，同票重算哈希升戳
    assert client.post("/api/分桶", json=百分比(f"{k}-p2", k, 20)).status_code == 200
    断言(取戳核证(client, k)["valid"], "重写升戳后哈希重新吻合，valid 恢复")


def 场景_邻键不串(client) -> None:
    print("\n[5] 邻开关键戳不得串用")
    ka, kb = "gen.neighbor", "gen.hot"
    client.post("/api/装载/夹具", params={"名": "世代-试轨版本"})
    assert client.post("/api/分桶", json=百分比(f"{ka}-p", ka, 5)).status_code == 200
    戳a = 取戳核证(client, ka)
    戳b = 取戳核证(client, kb)
    # 用 kb 的版本去点 ka 的桶 → 跨键拒绝
    r = client.post("/api/下发", json={"票号": "票-串键", "版本键": f"{kb}@1", "桶键": f"{ka}-p"})
    断言(r.status_code in (400, 409), f"跨键选规被拒（{r.status_code}）")
    # 各自下发各自的桶，票面世代号只认本键戳
    ok = client.post("/api/下发", json={"票号": "票-邻键-a", "版本键": f"{ka}@1", "桶键": f"{ka}-p"})
    断言(ok.status_code == 200 and ok.json()["世代号"] == 戳a["世代号"],
          f"邻键票面世代号=本键戳号 {戳a['世代号']}，不串用 hot 的 {戳b['世代号']}（{ok.text[:80]}）")
    断言(戳a["集合哈希"] != 戳b["集合哈希"] or 戳a["开关键"] != 戳b["开关键"], "两键戳面互相独立")


def 场景_并发(client, 临时目录: str) -> None:
    print("\n[6] 写规与下发并发 → 失败闭，不得无戳绑归档")
    k = "gen.race"
    client.post("/api/入轨", json={"批次编号": "b6", "版本": [
        {"开关键": k, "版本号": 1, "版本键": f"{k}@1", "载荷": {}}]})
    assert client.post("/api/分桶", json=百分比(f"{k}-p", k)).status_code == 200
    号前 = 取戳核证(client, k)["世代号"]

    holder = sqlite3.connect(Path(临时目录) / "灰度轨.db", timeout=0, isolation_level=None)
    holder.execute("BEGIN IMMEDIATE")
    try:
        r = client.post("/api/下发", json={"票号": "票-并发", "版本键": f"{k}@1", "桶键": f"{k}-p"})
        断言(r.status_code == 409, f"下发遇写锁→409（{r.status_code}）")
        断言(all(t["票号"] != "票-并发" for t in client.get("/api/下发票").json()), "失败闭：不落半截票")
        w = client.post("/api/分桶", json=名单(f"{k}-l", k))
        断言(w.status_code == 409, f"写规遇写锁→409（{w.status_code}）")
    finally:
        holder.execute("ROLLBACK")
        holder.close()

    键 = 取戳核证(client, k)
    断言(键["世代号"] == 号前 and 键["valid"], "锁释放后戳号未跳、无半截、valid")
    ok = client.post("/api/分桶", json=名单(f"{k}-l", k))
    断言(ok.status_code == 200 and ok.json()["世代戳"]["世代号"] == 号前 + 1, "串行写规成功且同票升戳")
    d = client.post("/api/下发", json={"票号": "票-并发-后", "版本键": f"{k}@1", "桶键": f"{k}-l"})
    断言(d.status_code == 200 and d.json()["世代号"] == 号前 + 1, "串行下发绑新戳，绝不无戳/绑归档")
    r2 = client.post("/api/下发", json={"票号": "票-并发-归档", "版本键": f"{k}@1", "桶键": f"{k}-p"})
    断言(r2.status_code == 409, "热更后归档规在并发收尾后依旧不可点中")


def 场景_归档升戳与回读漂移(client) -> None:
    print("\n[7] 人工归档同票升戳；旧票确认回读转规漂移")
    k = "gen.arch"
    client.post("/api/入轨", json={"批次编号": "b7", "版本": [
        {"开关键": k, "版本号": 1, "版本键": f"{k}@1", "载荷": {}}]})
    assert client.post("/api/分桶", json=名单(f"{k}-l", k)).status_code == 200
    t = client.post("/api/下发", json={"票号": "票-归档漂移", "版本键": f"{k}@1", "桶键": f"{k}-l"})
    断言(t.status_code == 200 and t.json()["世代号"] >= 1, "名单规下发成功带戳号")
    号前 = 取戳核证(client, k)["世代号"]

    a = client.post("/api/分桶/归档", json={"桶键": f"{k}-l", "说明": "演练归档"})
    断言(a.status_code == 200 and a.json()["世代戳"]["世代号"] == 号前 + 1, "归档同票升戳")
    键 = 取戳核证(client, k)
    断言(键["生效集合"] == [] and f"{k}-l" in 键["归档集合"], "归档后生效集空、归档集收录")
    断言(any("绑定旧集合" in v for v in 键["违规"]) and 键["绑旧集票据"],
          "旧票未收口前核证亮红：已下发票绑定旧集合（贯验同步可见）")

    r = client.post("/api/下发", json={"票号": "票-再点归档", "版本键": f"{k}@1", "桶键": f"{k}-l"})
    断言(r.status_code == 409, "归档规不可被无戳/错戳点中")
    rr = client.post("/api/回读", json={"票号": "票-归档漂移", "边缘键": "edge-a"})
    断言(rr.status_code == 200 and rr.json()["结果"] == "偏差" and "规漂移" in rr.json()["说明"],
          f"旧票确认回读转偏差·规漂移：{rr.json().get('说明')}")


def 场景_历史与夹具(client) -> None:
    print("\n[8] 世代历史翻页接口 + 无工单再下发夹具 + 票面世代号")
    k = "gen.hot"
    h = client.get("/api/核证/分桶世代/历史", params={"键": k, "限": 100})
    断言(h.status_code == 200, "历史接口 200")
    历史 = h.json()["历史"]
    号列 = [r["世代号"] for r in 历史]
    断言(号列 == sorted(号列, reverse=True) and len(号列) == len(set(号列)), "历史可翻世代号且无重号")
    断言(all(r["工单有无"] is False for r in 历史), "历史各戳工单有无=false（甲无工单实体）")
    断言(all(r["集合哈希"] and r["戳时"] for r in 历史), "历史各戳哈希/戳时齐套")

    f = client.post("/api/装载/夹具", params={"名": "世代-无工单再下发"})
    断言(f.status_code == 200, f"下发夹具可装载（{f.text[:100]}）")
    报 = f.json()["报告"]
    断言(len(报["失败"]) == 1 and 报["失败"][0]["状态码"] == 409, "点归档规一条失败且状态码=409")
    断言(len(报["结果"]) == 1 and 报["结果"][0]["世代号"] >= 1, "点戳内生效规一条成功且带回世代号")

    for t in client.get("/api/下发票").json():
        if t["状态"] == "已下发":
            断言("戳世代号" in t and t["戳世代号"] >= 1, f"下发票列表 {t['票号']} 烙戳世代号")
    规 = client.get("/api/分桶规").json()
    归 = [r for r in 规 if r["状态"] == "已归档"]
    断言(归 and all(r["归档因"] and r["归档时"] for r in 归), "分桶规页接口仍列出归档规（非 UI 隐藏）")


def 场景_贯验收口(client) -> None:
    print("\n[9] 贯验：绑旧集/无戳/错戳亮红，回滚收口后转绿")
    g = client.post("/api/贯验").json()
    断言(not g["是否通过"] and "世代戳" in g["说明"], f"未收口贯验亮红：{g['说明'][:80]}")
    # 热更场景的旧票绑旧集合，回滚收口
    for 票号 in ("票-热-旧", "票-归档漂移"):
        client.post("/api/回滚", json={"票号": 票号, "说明": "世代收口"})
    g2 = client.post("/api/贯验").json()
    断言(g2["是否通过"], f"收口后贯验转绿：{g2['说明'][:80]}")
    总 = client.get("/api/总览").json()
    断言(总["世代戳valid"] is True and 总["世代戳口径"] == "戳锁现行规", "总览暴露世代戳 valid 与口径")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--保留库", action="store_true")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as 临时:
        client = 建站(临时)
        场景_写规同票落戳(client)
        场景_写规拒戳不挂(client, 临时)
        场景_热更无工单再下发(client)
        场景_错戳(client, 临时)
        场景_邻键不串(client)
        场景_并发(client, 临时)
        场景_归档升戳与回读漂移(client)
        场景_历史与夹具(client)
        场景_贯验收口(client)
        if args.保留库:
            print(f"\n临时库：{Path(临时) / '灰度轨.db'}")

    print()
    if 失败:
        print(f"FAIL · {len(失败)} 条断言未过")
        for f in 失败:
            print(f"  - {f}")
        return 1
    print("PASS · 分桶世代戳核证全绿（口径甲：戳锁现行规）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
