import React, { useEffect, useState } from "react";
import { get, postFixture } from "../api.js";

export default function 下发票() {
  const [rows, setRows] = useState([]);
  const [讯, set讯] = useState("");
  const 刷 = async () => setRows(await get("/下发票"));
  useEffect(() => { 刷().catch((e) => set讯(String(e))); }, []);

  const 跑夹具 = async (名) => {
    set讯("RUNNING…");
    try {
      const r = await postFixture(名);
      await 刷();
      const 败 = r.报告?.失败 || [];
      set讯(败.length ? `已跑 ${名}：${败.length} 条按戳闸拒绝（409）` : `已跑 ${名}`);
    } catch (e) {
      set讯(String(e));
    }
  };

  return (
    <div>
      <h1 className="题">下发票</h1>
      <p className="述">
        版本对分桶的一次灰度下发。读规 + 验世代戳 + 落票同事务：无戳/错戳/点归档（戳外）规一律 409、票不落；
        回执烙戳世代号与集合哈希。热更新后旧票幂等重投也按旧集合拒绝——已下发不得绑旧世代。
      </p>
      <div className="行">
        <button onClick={async () => { await postFixture("下发样例"); await 刷(); set讯("已灌下发样例"); }}>灌下发样例</button>
        <button className="次" onClick={() => 跑夹具("世代-无工单再下发")}>热更后无工单再下发</button>
        <button className="次" onClick={() => 刷()}>刷新</button>
      </div>
      {讯 && <p className="讯">{讯}</p>}
      {!rows.length ? <div className="空态">尚无下发票（需先入轨+分桶）</div> : (
        <table>
          <thead><tr>
            <th>票号</th><th>版本键</th><th>桶键</th><th>桶类型</th><th>状态</th>
            <th>戳世代号</th><th>戳集合哈希</th><th>戳时</th><th>下发时</th>
          </tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.票号}>
              <td>{r.票号}</td><td>{r.版本键}</td><td>{r.桶键}</td><td>{r.桶类型}</td>
              <td><span className="徽章 通">{r.状态}</span></td>
              <td><b>{r.戳世代号}</b></td>
              <td className="mono">{(r.戳集合哈希 || "").slice(0, 12)}…</td>
              <td className="mono">{r.戳时 || "—"}</td>
              <td className="mono">{r.下发时}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </div>
  );
}
