import React, { useEffect, useState } from "react";
import { get, post, postFixture } from "../api.js";

export default function 分桶规() {
  const [rows, setRows] = useState([]);
  const [戳包, set戳包] = useState(null);
  const [讯, set讯] = useState("");
  const [归档中, set归档中] = useState("");
  const 刷 = async () => {
    const [规, 戳] = await Promise.all([get("/分桶规"), get("/核证/分桶世代")]);
    setRows(规);
    set戳包(戳);
  };
  useEffect(() => { 刷().catch((e) => set讯(String(e))); }, []);

  const 戳by键 = Object.fromEntries((戳包?.开关键们 || []).map((k) => [k.开关键, k]));
  const 键们 = [...new Set(rows.map((r) => r.开关键))].sort();

  const 归档 = async (桶键) => {
    set归档中(桶键);
    try {
      await post("/分桶/归档", { 桶键, 说明: "页面人工归档" });
      await 刷();
      set讯(`已归档 ${桶键}（同票升世代戳）`);
    } catch (e) {
      set讯(String(e));
    } finally {
      set归档中("");
    }
  };

  const 规表 = (list, 归档) => (
    <table>
      <thead><tr>
        <th>桶键</th><th>桶类型</th><th>规则</th><th>规世代</th>
        {归档 ? <><th>归档因</th><th>归档时</th></> : <><th>更新时</th><th>操作</th></>}
      </tr></thead>
      <tbody>{list.length ? list.map((r) => (
        <tr key={r.桶键} className={归档 ? "归档行" : ""}>
          <td>{r.桶键}</td><td>{r.桶类型}</td>
          <td><code>{typeof r.规则 === "string" ? r.规则 : JSON.stringify(r.规则)}</code></td>
          <td>{r.世代}</td>
          {归档 ? (
            <><td><span className="徽章 败">{r.归档因}</span></td><td className="mono">{r.归档时}</td></>
          ) : (
            <><td className="mono">{r.更新时}</td>
            <td><button className="次" disabled={归档中 === r.桶键} onClick={() => 归档(r.桶键)}>归档</button></td></>
          )}
        </tr>
      )) : <tr><td colSpan={6} className="核淡">无</td></tr>}</tbody>
    </table>
  );

  return (
    <div>
      <h1 className="题">分桶规</h1>
      <p className="述">
        百分比桶 / 名单桶 / 环境桶。同一开关键下百分比与名单不得并行生效（乙口径：名单接管并归档百分比，
        百分比回写整拒）。生效集与归档集并排列出、归档规不隐藏；每条写规同票落分桶世代戳，
        下发只认当前戳内生效规，归档（戳外）规不可被点中。
      </p>
      <div className="行">
        <button onClick={async () => { await postFixture("分桶样例"); await 刷(); set讯("已灌分桶样例"); }}>灌分桶样例</button>
        <button className="次" onClick={async () => { try { await postFixture("世代-热更归档"); await 刷(); set讯("已灌 百分比→名单（热更升戳）"); } catch (e) { set讯(String(e)); } }}>热更：百分比→名单</button>
        <button className="次" onClick={() => 刷()}>刷新</button>
      </div>
      {讯 && <p className="讯">{讯}</p>}
      {!rows.length ? <div className="空态">尚无分桶</div> : 键们.map((k) => {
        const 生效 = rows.filter((r) => r.开关键 === k && r.状态 === "生效");
        const 归档 = rows.filter((r) => r.开关键 === k && r.状态 === "已归档");
        const 戳 = 戳by键[k];
        return (
          <div key={k} className="核块">
            <div className="核头">
              <b>{k}</b>
              {戳 && (
                <>
                  <span className="徽章 信">戳世代号 {戳.世代号}</span>
                  <span className={"徽章 " + (戳.工单有无 ? "败" : "通")}>工单 {戳.工单有无 ? "有" : "无"}</span>
                  <span className={"徽章 " + (戳.valid ? "通" : "败")}>{戳.valid ? "valid" : "invalid"}</span>
                  <span className="核淡 mono">戳时 {戳.戳时 || "—"} · 哈希 {(戳.集合哈希 || "").slice(0, 12)}…</span>
                </>
              )}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <div className="核头" style={{ padding: "4px 0" }}><span className="徽章 通">生效集（戳内可下发）</span><span className="核淡">{生效.length} 条</span></div>
                {规表(生效, false)}
              </div>
              <div>
                <div className="核头" style={{ padding: "4px 0" }}><span className="徽章 败">归档集（戳外·禁点）</span><span className="核淡">{归档.length} 条</span></div>
                {规表(归档, true)}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
