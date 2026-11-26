import React, { useEffect, useState } from "react";
import { get, post, postFixture } from "../api.js";

export default function 分桶规() {
  const [rows, setRows] = useState([]);
  const [讯, set讯] = useState("");
  const [归档中, set归档中] = useState("");
  const 刷 = async () => setRows(await get("/分桶规"));
  useEffect(() => { 刷().catch((e) => set讯(String(e))); }, []);

  const 归档 = async (桶键) => {
    set归档中(桶键);
    try {
      await post("/分桶/归档", { 桶键, 说明: "页面人工归档" });
      await 刷();
      set讯(`已归档 ${桶键}`);
    } catch (e) {
      set讯(String(e));
    } finally {
      set归档中("");
    }
  };

  return (
    <div>
      <h1 className="题">分桶规</h1>
      <p className="述">
        百分比桶 / 名单桶 / 环境桶。同一开关键下百分比与名单不得并行生效（乙口径：名单接管并归档百分比，
        百分比回写整拒）。归档规照样列出——只归档、不隐藏，也不可在下发时被点到。
      </p>
      <div className="行">
        <button onClick={async () => { await postFixture("分桶样例"); await 刷(); set讯("已灌分桶样例"); }}>灌分桶样例</button>
        <button className="次" onClick={async () => { try { await postFixture("互斥-百分比转名单"); await 刷(); set讯("已灌 百分比→名单"); } catch (e) { set讯(String(e)); } }}>百分比 → 名单</button>
        <button className="次" onClick={async () => { try { await postFixture("互斥-名单转百分比"); await 刷(); set讯("已灌 名单→百分比"); } catch (e) { set讯(String(e)); } }}>名单 → 百分比</button>
        <button className="次" onClick={() => 刷()}>刷新</button>
      </div>
      {讯 && <p className="讯">{讯}</p>}
      {!rows.length ? <div className="空态">尚无分桶</div> : (
        <table>
          <thead><tr><th>桶键</th><th>开关键</th><th>桶类型</th><th>规则</th><th>状态</th><th>世代</th><th>归档因 / 归档时</th><th>操作</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.桶键} className={r.状态 === "已归档" ? "归档行" : ""}>
              <td>{r.桶键}</td><td>{r.开关键}</td><td>{r.桶类型}</td>
              <td><code>{typeof r.规则 === "string" ? r.规则 : JSON.stringify(r.规则)}</code></td>
              <td><span className={"徽章 " + (r.状态 === "生效" ? "通" : r.状态 === "已归档" ? "败" : "信")}>{r.状态}</span></td>
              <td>{r.世代}</td>
              <td>{r.状态 === "已归档" ? <span className="mono">{r.归档因}<br />{r.归档时}</span> : <span className="核淡">—</span>}</td>
              <td>{r.状态 === "生效"
                ? <button className="次" disabled={归档中 === r.桶键} onClick={() => 归档(r.桶键)}>归档</button>
                : <span className="核淡">仅可下发生效规</span>}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </div>
  );
}
