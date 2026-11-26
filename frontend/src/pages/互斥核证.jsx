import React, { useEffect, useState } from "react";
import { get, post } from "../api.js";

const 场景 = [
  ["互斥-百分比转名单", "百分比 → 名单"],
  ["互斥-名单转百分比", "名单 → 百分比"],
  ["互斥-下发归档规", "下发归档规"],
];

export default function 互斥核证() {
  const [核, set核] = useState(null);
  const [讯, set讯] = useState("");
  const [键, set键] = useState("");

  const 刷 = async (开关键 = "") => {
    const q = 开关键 || 键 ? `?开关键=${encodeURIComponent(开关键 || 键)}` : "";
    set核(await get(`/互斥核证${q}`));
  };
  useEffect(() => { 刷().catch((e) => set讯(String(e))); }, []);

  const 跑夹具 = async (名) => {
    set讯("RUNNING…");
    try {
      await post("/装载/夹具?名=" + encodeURIComponent(名));
      await 刷();
      set讯(`已跑 ${名}`);
    } catch (e) {
      set讯(String(e));
    }
  };

  const 标记 = 核?.策略标记;
  return (
    <div>
      <h1 className="题">互斥核证</h1>
      <p className="述">
        同一开关键下百分比规与名单规不得并行生效。本站落地口径为「乙：名单归档百分比」——
        名单写入成功则原百分比归档失效；百分比回写整拒（须先人工归档名单）。两口径结局可区分：
        甲=生效集仍含百分比，乙=不含。
      </p>

      <div className="行">
        <input
          className="输入"
          placeholder="开关键（留空=全站）"
          value={键}
          onChange={(e) => set键(e.target.value)}
        />
        <button className="信" onClick={() => 刷().catch((e) => set讯(String(e)))}>核证</button>
        <button className="次" onClick={() => { set键(""); 刷("").catch((e) => set讯(String(e))); }}>全站</button>
      </div>

      <div className="行">
        {场景.map(([名, 标]) => (
          <button className="次" key={名} onClick={() => 跑夹具(名)}>{标}</button>
        ))}
      </div>
      {讯 && <p className="讯">{讯}</p>}

      {标记 && (
        <div className={标记.valid ? "提示条" : "提示条 坏"}>
          策略标记：<b>{标记.值 || "（缺失）"}</b>
          <span className={"徽章 " + (标记.valid ? "通" : "败")} style={{ marginLeft: 8 }}>
            {标记.valid ? "valid" : "invalid · 停写"}
          </span>
          <div style={{ marginTop: 6, fontSize: "0.85rem" }}>{标记.口径}</div>
        </div>
      )}

      {核 && (
        <>
          <p className="讯">
            全站 valid：{核.valid ? "是" : "否"} · 开关键 {核.开关键们.length} 个 ·
            归档规 {核.归档规.length} 条
            {核.违规.length ? ` · 违规 ${核.违规.length} 条` : ""}
          </p>
          {核.违规.length > 0 && (
            <ul className="违规">
              {核.违规.map((v, i) => <li key={i}>{v}</li>)}
            </ul>
          )}
          {!核.开关键们.length ? <div className="空态">尚无可核证的分桶规</div> : 核.开关键们.map((k) => (
            <div key={k.开关键} className="核块">
              <div className="核头">
                <b>{k.开关键}</b>
                <span className={"徽章 " + (k.valid ? "通" : "败")}>{k.valid ? "valid" : "invalid"}</span>
                <span className="徽章 信">{k.口径结局}</span>
                <span className="核淡">生效 {k.生效规.length} · 归档 {k.归档规.length} · 票据 {k.票据.length}</span>
              </div>
              <table>
                <thead><tr><th>生效桶键</th><th>类型</th><th>世代</th><th>更新时</th></tr></thead>
                <tbody>{k.生效规.map((r) => (
                  <tr key={r.桶键}><td>{r.桶键}</td><td>{r.桶类型}</td><td>{r.世代}</td><td>{r.更新时}</td></tr>
                ))}</tbody>
              </table>
              <table style={{ marginTop: 8 }}>
                <thead><tr><th>归档桶键</th><th>类型</th><th>归档因</th><th>归档时</th><th>票据</th></tr></thead>
                <tbody>{k.归档规.length ? k.归档规.map((r) => (
                  <tr key={r.桶键}><td>{r.桶键}</td><td>{r.桶类型}</td>
                    <td><span className="徽章 败">{r.归档因}</span></td>
                    <td>{r.归档时}</td>
                    <td>{k.票据.filter((t) => t.桶键 === r.桶键).map((t) => (
                      <div key={t.票号} className="mono">{t.票号} · {t.状态}{t.需复核 ? ` · ${t.需复核}` : ""}</div>
                    ))}</td>
                  </tr>
                )) : <tr><td colSpan={5} className="核淡">无</td></tr>}</tbody>
              </table>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
