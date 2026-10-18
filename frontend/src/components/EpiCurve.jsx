import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

function parseOnset(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDay(date) {
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

function CaseTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return <div className="chart-tooltip"><span>{label}</span><strong>{payload[0].value} {payload[0].value === 1 ? "case" : "cases"}</strong></div>;
}

export default function EpiCurve({ cases = [] }) {
  const data = useMemo(() => {
    const counts = new Map();
    for (const item of cases) {
      const date = parseOnset(item?.onset);
      if (!date) continue;
      const key = date.toISOString().slice(0, 10);
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([key, count]) => ({
      date: formatDay(new Date(`${key}T00:00:00Z`)),
      cases: count,
    }));
  }, [cases]);

  if (!data.length) return <div className="chart-empty"><div className="chart-empty-art"><span /><span /><span /><span /><span /><span /></div><strong>Case curve is ready to take shape</strong><p>Symptom-onset dates will appear here as cases are linked to the investigation.</p><small>EPIDEMIC CURVE · ONSET DATE</small></div>;

  return <div className="epi-chart" aria-label="Epidemic curve based on case onset dates">
    <div className="chart-summary"><div><span>CASES WITH ONSET DATE</span><strong>{cases.filter((item) => parseOnset(item?.onset)).length}</strong></div><div><span>PEAK ONSET DAY</span><strong>{data.reduce((peak, row) => row.cases > peak.cases ? row : peak, data[0]).date}</strong></div><div className="chart-legend-item"><i /> Cases by symptom onset</div></div>
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 12, right: 14, left: -20, bottom: 6 }} barCategoryGap="24%">
        <defs><linearGradient id="caseBar" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--chart-accent)" /><stop offset="100%" stopColor="var(--chart-accent-deep)" /></linearGradient></defs>
        <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeDasharray="3 6" />
        <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: "var(--chart-label)", fontSize: 10 }} dy={9} />
        <YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fill: "var(--chart-label)", fontSize: 9 }} />
        <Tooltip content={<CaseTooltip />} cursor={{ fill: "var(--chart-cursor)" }} />
        <Bar dataKey="cases" fill="url(#caseBar)" radius={[6, 6, 2, 2]} maxBarSize={42} />
      </BarChart>
    </ResponsiveContainer>
  </div>;
}
