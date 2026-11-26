import React, { useEffect, useState } from "react";
import { get } from "../api.js";

export default function 核证分桶世代() {
  const [包, set包] = useState(null);
  const [历史, set历史] = useState({});
  const [键, set键] = useState("");
  const [err, setErr] = useState("");

  const 刷 = async (开关键 = "") => {
    const q = 开关键 || 键 ? `?键=${encodeURIComponent(开关键 || 键)}` : "";
    const 核 = await get(`/核证/分桶世代${q}`);
    set包(核);
    const h = {};
    for (const k of 核.开关键们 || []) {
      // 核证已带历史；另拉历史接口验证只读翻页路由
      h[k.开关键] = (await get(`/核证/分桶世代/历史?键=${encodeURIComponent(k.开关键)}&限=50`)).历史;
    }
    set历史(h);
  };
  useEffect(() => { 刷().catch((e) => setErr(String(e.message || e))); }, []);

  return (
    <div>
      <h1 className="题">分桶世代戳核证</h1>
      <p className="述">
        口径甲·<b>以戳锁现行规为准</b>：规写入成功同票落世代戳（开关键、生效规集合哈希、世代号、戳时）；
        下发只能绑定戳内生效规集合，戳外/归档规一律拒绝，已下发不得绑旧集合。本站无换世代工单实体，
        「工单」恒为无——与乙口径（持工单才可改绑升号）在此可区分。世代号严格单调。
      </p>
      <div className="行">
        <input className="输入" placeholder="开关键（留空=全站）" value={键} onChange={(e) => set键(e.target.value)} />
        <button className="信" onClick={() => 刷().catch((e) => setErr(String(e.message || e)))}>核证</button>
        <button className="次" onClick={() => { set键(""); 刷("").catch((e) => setErr(String(e.message || e))); }}>全站</button>
      </div>
      {err && <pre className="码">{err}</pre>}
      {包 && (
        <>
          <div className={包.valid ? "提示条" : "提示条 坏"}>
            口径：<b>{包.口径}</b>
            <span className={"徽章 " + (包.valid ? "通" : "败")} style={{ marginLeft: 8 }}>
              {包.valid ? "valid" : "invalid"}
            </span>
            <span className="核淡" style={{ marginLeft: 8 }}>范围 {包.范围} · 开关键 {包.开关键们.length} 个</span>
          </div>
          {包.违规.length > 0 && (
            <ul className="违规">{包.违规.map((v, i) => <li key={i}>{v}</li>)}</ul>
          )}
          {!包.开关键们.length ? <div className="空态">尚无分桶规，无世代戳可核</div> : 包.开关键们.map((k) => (
            <div key={k.开关键} className="核块">
              <div className="核头">
                <b>{k.开关键}</b>
                <span className={"徽章 " + (k.valid ? "通" : "败")}>{k.valid ? "valid" : "invalid"}</span>
                <span className="徽章 信">世代号 {k.世代号}</span>
                <span className={"徽章 " + (k.工单有无 ? "败" : "通")}>工单 {k.工单有无 ? "有" : "无"}</span>
                <span className="核淡 mono">{(k.集合哈希 || "").slice(0, 16)}… · 戳时 {k.戳时 || "—"}</span>
              </div>
              {k.违规.length > 0 && <ul className="违规">{k.违规.map((v, i) => <li key={i}>{v}</li>)}</ul>}

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <div className="核头" style={{ padding: "4px 0" }}><span className="徽章 通">生效集（戳内）</span><span className="核淡">{k.生效集合.length} 条</span></div>
                  <table>
                    <thead><tr><th>桶键</th><th>类型</th><th>规世代</th><th>更新时</th></tr></thead>
                    <tbody>{k.生效规.length ? k.生效规.map((r) => (
                      <tr key={r.桶键}><td>{r.桶键}</td><td>{r.桶类型}</td><td>{r.规世代}</td><td className="mono">{r.更新时}</td></tr>
                    )) : <tr><td colSpan={4} className="核淡">空（生效集无规）</td></tr>}</tbody>
                  </table>
                </div>
                <div>
                  <div className="核头" style={{ padding: "4px 0" }}><span className="徽章 败">归档集（戳外）</span><span className="核淡">{k.归档集合.length} 条</span></div>
                  <table>
                    <thead><tr><th>桶键</th><th>类型</th><th>归档因</th><th>归档时</th></tr></thead>
                    <tbody>{k.归档规.length ? k.归档规.map((r) => (
                      <tr key={r.桶键} className="归档行"><td>{r.桶键}</td><td>{r.桶类型}</td>
                        <td><span className="徽章 败">{r.归档因}</span></td><td className="mono">{r.归档时}</td></tr>
                    )) : <tr><td colSpan={4} className="核淡">无</td></tr>}</tbody>
                  </table>
                </div>
              </div>

              {k.绑旧集票据.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <span className="徽章 败">绑旧集合票据 {k.绑旧集票据.length}</span>
                  {k.绑旧集票据.map((t) => (
                    <div key={t.票号} className="mono" style={{ fontSize: "0.82rem" }}>
                      {t.票号} · 桶 {t.桶键} · 票戳世代 {t.戳世代号} ≠ 现行 {k.世代号} · {t.需复核}
                    </div>
                  ))}
                </div>
              )}

              <details style={{ marginTop: 8 }}>
                <summary className="核淡" style={{ cursor: "pointer" }}>翻世代号（{(历史[k.开关键] || k.历史 || []).length} 代，旧→新）</summary>
                <table style={{ marginTop: 6 }}>
                  <thead><tr><th>世代号</th><th>生效集合</th><th>归档集合</th><th>工单</th><th>变更</th><th>戳时</th></tr></thead>
                  <tbody>{(历史[k.开关键] || k.历史 || []).slice().reverse().map((h) => (
                    <tr key={h.世代号}>
                      <td><b>{h.世代号}</b></td>
                      <td className="mono">{JSON.stringify(h.生效集合)}</td>
                      <td className="mono">{JSON.stringify((h.载荷 && h.载荷.归档集合) || [])}</td>
                      <td>{h.工单有无 ? "有" : "无"}</td>
                      <td>{h.变更 || "—"}</td>
                      <td className="mono">{h.戳时}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </details>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
