import React, { useEffect, useState } from "react";
import { get, postFixture } from "../api.js";

export default function 回读台() {
  const [rows, setRows] = useState([]);
  const [讯, set讯] = useState("");
  const 刷 = async () => setRows(await get("/回读证"));
  useEffect(() => { 刷().catch((e) => set讯(String(e))); }, []);
  return (
    <div>
      <h1 className="题">回读台</h1>
      <p className="述">边缘对下发票的确认。所见版本与票面不一致 → 记「偏差」。</p>
      <div className="行">
        <button onClick={async () => { await postFixture("回读样例"); await 刷(); set讯("已灌回读样例"); }}>灌回读样例</button>
        <button className="次" onClick={() => 刷()}>刷新</button>
      </div>
      {讯 && <p className="讯">{讯}</p>}
      {!rows.length ? <div className="空态">尚无回读证</div> : (
        <table>
          <thead><tr><th>证号</th><th>票号</th><th>边缘</th><th>所见版本</th><th>结果</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.证号}><td>{r.证号}</td><td>{r.票号}</td><td>{r.边缘键}</td>
            <td>{r.所见版本键}</td>
            <td><span className={"徽章 " + (r.结果 === "确认" ? "通" : "败")}>{r.结果}</span></td></tr>
          ))}</tbody>
        </table>
      )}
    </div>
  );
}
