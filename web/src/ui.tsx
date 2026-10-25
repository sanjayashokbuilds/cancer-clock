import { useEffect, useId, useRef, useState, type ReactNode } from 'react';

export type Json = Record<string, any>;
export type Trust = Json & {org_code: string; name: string; lat: number | null; lon: number | null; latest_backlog: number | null; latest_observed_week: string | null; history: Json[]; forecasts: Json[]; direction: string};
export const C = {bg: '#080D16', surface: '#101A2B', panel: '#152133', ink: '#F4F7FC', muted: '#A8B5C7', hairline: '#2A3648', cyan: '#67E8F9', lilac: '#C4B5FD', amber: '#F4C66A', teal: '#75D8B1', orange: '#FF7B78', slate: '#94A3B8', diagnosis: '#C4B5FD', treatment: '#F4C66A'};
export const number = (n: unknown, digits = 0) => typeof n === 'number' && Number.isFinite(n) ? n.toLocaleString('en-GB', {maximumFractionDigits: digits, minimumFractionDigits: digits}) : '—';
export const day = (value?: string, short = false) => value ? new Date(value.slice(0,10) + 'T12:00:00').toLocaleDateString('en-GB', {day: 'numeric', month: 'short', ...(short ? {} : {year: 'numeric'})}) : 'Date unavailable';
export const timestamp = (v: string) => new Date(v.slice(0,10) + 'T12:00:00Z').getTime();
export const title = (name = '') => name.toLowerCase().replace(/\b\w/g, c => c.toUpperCase()).replace(/['’]S\b/g, match => match.toLowerCase()).replace(/\bNhs\b/g, 'NHS').replace(/ NHS Foundation Trust$| NHS Trust$/i, '');
export const directionColor = (d?: string) => d === 'improving' ? C.teal : d === 'worsening' ? C.orange : C.slate;
export const directionLabel = (d?: string) => d === 'improving' ? 'Forecast to improve' : d === 'worsening' ? 'Forecast to worsen' : 'Direction unclear';
export function driverName(driver?: Json | null) {
  if (!driver) return '';
  const key = driver.key || '';
  if (key === 'd31_radiotherapy') return 'Radiotherapy';
  if (key === 'd31_surgery') return 'Surgery';
  if (key === 'd31_drugs') return 'Anti-cancer medicines';
  const name = (driver.name || '').replace(/ FDS$/i, '').replace(/ 31-day$/i, '');
  const names: Record<string,string> = {'Skin': 'Skin cancer', 'Lung': 'Lung cancer', 'Breast': 'Breast cancer', 'Lower GI': 'Lower digestive tract cancer', 'Lower gastrointestinal': 'Lower digestive tract cancer', 'Upper GI': 'Upper digestive tract cancer', 'Upper gastrointestinal': 'Upper digestive tract cancer', 'Urology': 'Urinary tract cancer', 'Urological malignancies (excluding testicular)': 'Urinary tract cancer', 'Cancer - non-specific symptoms': 'Cancer with non-specific symptoms'};
  return names[name] || name;
}
export function Icon({name, size = 20}: {name: string; size?: number}) {
  const paths: Record<string, ReactNode> = {
    clock: <><circle cx="12" cy="12" r="8.5"/><path d="M12 6v6l4 2"/></>,
    arrow: <path d="M4 12h15m-5-5 5 5-5 5"/>,
    back: <path d="M20 12H5m5-5-5 5 5 5"/>,
    search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/></>,
    close: <path d="m6 6 12 12M6 18 18 6"/>,
    plus: <path d="M12 5v14M5 12h14"/>,
    play: <path d="m9 5 11 7-11 7Z"/>,
    pause: <><path d="M8 5v14M16 5v14" strokeWidth="3"/></>,
    info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/></>,
    person: <><circle cx="12" cy="7" r="3"/><path d="M5 21v-3a7 7 0 0 1 14 0v3"/></>,
    chevron: <path d="m9 5 7 7-7 7"/>,
    check: <path d="m5 12 4 4L19 6"/>,
    expand: <><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/></>,
    download: <><path d="M12 3v12m-4-4 4 4 4-4M4 17v4h16v-4"/></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.info}</svg>;
}
export function useReducedMotion() {
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {const media = window.matchMedia('(prefers-reduced-motion: reduce)'); const update = () => setReduced(media.matches); media.addEventListener('change', update); return () => media.removeEventListener('change', update);}, []);
  return reduced;
}
export function AnimatedNumber({value, digits = 0, className = '', from}: {value: number | undefined | null; digits?: number; className?: string; from?: number | null}) {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(reduced ? (value ?? 0) : (from ?? value ?? 0));
  const current = useRef(shown);
  useEffect(() => {
    if (value == null || !Number.isFinite(value)) return;
    if (reduced) {current.current = value; setShown(value); return;}
    const from = current.current; const start = performance.now(); let frame = 0;
    const tick = (now: number) => {const t = Math.min(1, (now - start) / 420); const next = from + (value - from) * (1 - (1 - t) ** 3); current.current = next; setShown(next); if (t < 1) frame = requestAnimationFrame(tick);};
    frame = requestAnimationFrame(tick); return () => cancelAnimationFrame(frame);
  }, [value, reduced]);
  return <span className={className} aria-label={value == null ? 'Unavailable' : number(value,digits)}>{value == null ? '—' : number(shown, digits)}</span>;
}
export function useAnimatedValues(values: number[], duration = 420) {
  const reduced = useReducedMotion(); const [current, setCurrent] = useState(values); const last = useRef(values); const signature = values.join(',');
  useEffect(() => {
    if (reduced || last.current.length !== values.length) {last.current = values; setCurrent(values); return;}
    const from = last.current; const start = performance.now(); let frame = 0;
    const tick = (now: number) => {const t = Math.min(1, (now - start) / duration); const e = 1 - (1-t) ** 3; const next = values.map((v,i) => from[i] + (v-from[i]) * e); last.current = next; setCurrent(next); if (t < 1) frame = requestAnimationFrame(tick);};
    frame = requestAnimationFrame(tick); return () => cancelAnimationFrame(frame);
  // A compact numeric signature keeps chart animation independent of parent render identities.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, reduced, duration]);
  return current;
}
export function useDialog(onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null); const close = useRef(onClose); close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null; const root = ref.current;
    const elements = () => Array.from(root?.querySelectorAll<HTMLElement>('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),summary,[tabindex="0"]') || []).filter(x => x.getClientRects().length);
    const timer = requestAnimationFrame(() => elements()[0]?.focus());
    const listener = (e: KeyboardEvent) => {
      if (root !== document.querySelector('[data-dialog]:last-of-type') && document.querySelectorAll('[data-dialog]').length > 1 && !root?.contains(document.activeElement)) return;
      if (e.key === 'Escape') {e.stopPropagation(); close.current();}
      if (e.key === 'Tab') {const items = elements(); const first = items[0], last = items.at(-1); if (e.shiftKey && document.activeElement === first) {e.preventDefault(); last?.focus();} else if (!e.shiftKey && document.activeElement === last) {e.preventDefault(); first?.focus();}}
    };
    root?.addEventListener('keydown', listener); return () => {cancelAnimationFrame(timer); root?.removeEventListener('keydown', listener); previous?.focus();};
  }, []);
  return ref;
}
export function Drawer({heading, children, onClose}: {heading: string; children: ReactNode; onClose: () => void}) {
  const ref = useDialog(onClose); const id = useId();
  return <div className="drawer-layer"><button className="drawer-scrim" aria-label="Close details" onClick={onClose}/><div ref={ref} data-dialog className="drawer" role="dialog" aria-modal="true" aria-labelledby={id}><div className="drawer-head"><h2 id={id}>{heading}</h2><button className="icon-button" onClick={onClose} aria-label="Close details"><Icon name="close"/></button></div><div className="drawer-body">{children}</div></div></div>;
}
export function Notice({children, warning = false}: {children: ReactNode; warning?: boolean}) {return <div className={`notice ${warning ? 'notice-warning' : ''}`}><Icon name="info" size={18}/><p>{children}</p></div>;}

export type ChartPoint = {x: number; y: number; low?: number; high?: number};
export type ChartSeries = {name: string; color: string; points: ChartPoint[]; dashed?: boolean; band?: boolean};
function niceMax(v: number) {const magnitude = 10 ** Math.floor(Math.log10(Math.max(1, v))); const fraction = v / magnitude; return Math.ceil(fraction * 2) / 2 * magnitude;}
export function LineChart({series, label, ticks, tickFormat, height = 270, fixedMax, marker, reveal = false, gap}: {series: ChartSeries[]; label: string; ticks?: number[]; tickFormat: (x: number) => string; height?: number; fixedMax?: number; marker?: {x: number; label: string}; reveal?: boolean; gap?: {from: number; to: number; label: string}}) {
  const id = useId().replaceAll(':','');
  const good = series.map(s => ({...s, points: s.points.filter(p => Number.isFinite(p.x) && Number.isFinite(p.y))})).filter(s => s.points.length);
  const all = good.flatMap(s => s.points); const minX = Math.min(...all.map(p => p.x)); const maxX = Math.max(...all.map(p => p.x));
  const maxY = fixedMax || niceMax(Math.max(10, ...all.map(p => p.high ?? p.y)) * 1.08);
  const w = 820, left = 48, right = 24, top = 30, bottom = 35, ph = height - top - bottom;
  const x = (n: number) => left + (n - minX) / (maxX - minX || 1) * (w-left-right);
  const y = (n: number) => top + ph - Math.max(0,n) / maxY * ph;
  const values = good.flatMap(s => s.points.flatMap(p => [y(p.y),y(p.low ?? p.y),y(p.high ?? p.y)])); const animated = useAnimatedValues(values);
  let offset = 0;
  const plotted = good.map(s => {const p = s.points.map(point => {const result = {x: x(point.x),y:animated[offset] ?? y(point.y), low:animated[offset+1] ?? y(point.low ?? point.y),high:animated[offset+2] ?? y(point.high ?? point.y)};offset+=3;return result;});return {...s,p};});
  const xticks = ticks || [minX, minX+(maxX-minX)/2, maxX];
  const line = (p: {x:number;y:number}[]) => p.map((v,i) => `${i ? 'L' : 'M'}${v.x.toFixed(2)},${v.y.toFixed(2)}`).join(' ');
  if (!all.length) return <div className="chart-empty">No suitable observations are available.</div>;
  return <svg className={`line-chart ${reveal ? 'chart-reveal' : ''}`} viewBox={`0 0 ${w} ${height}`} role="img" aria-label={label}>
    <title>{label}</title><desc>Solid lines show recorded counts or scenario paths. Forecasts use a dashed line. A shaded band shows the middle 80 percent range.</desc>
    <defs><clipPath id={id}><rect className="chart-clip" x={left} y="0" width={w-left} height={height}/></clipPath><pattern id={`${id}-gap`} width="7" height="7" patternUnits="userSpaceOnUse"><path d="M0 7 7 0" stroke={C.hairline} strokeWidth="0.8"/></pattern></defs>
    {[0,.5,1].map(q => <g key={q}><line x1={left} x2={w-right} y1={y(q*maxY)} y2={y(q*maxY)} stroke={C.hairline}/><text className="chart-tick" x={left-10} y={y(q*maxY)+5} textAnchor="end">{number(q*maxY)}</text></g>)}
    {gap && <g><rect x={x(gap.from)} width={Math.max(0,x(gap.to)-x(gap.from))} y={top} height={ph} fill={`url(#${id}-gap)`}/><text className="chart-gap-label" textAnchor="middle" x={(x(gap.from)+x(gap.to))/2} y="16">{gap.label}</text></g>}
    {marker && <g><line x1={x(marker.x)} x2={x(marker.x)} y1={top} y2={top+ph} stroke={C.slate} strokeDasharray="3 5"/><text className="chart-gap-label" x={x(marker.x)+7} y="16">{marker.label}</text></g>}
    <g clipPath={`url(#${id})`}>{plotted.map(s => <g key={s.name}>{s.band && <path d={`${line(s.p.map(p => ({x:p.x,y:p.high})))} ${s.p.slice().reverse().map(p => `L${p.x.toFixed(2)},${p.low.toFixed(2)}`).join(' ')} Z`} fill={s.color} opacity=".11"/>}<path d={line(s.p)} fill="none" stroke={s.color} strokeWidth="2.8" strokeLinejoin="round" strokeLinecap="round" strokeDasharray={s.dashed ? '6 6' : undefined}/>{s.points.length < 5 && s.p.map((p,i) => <circle key={i} cx={p.x} cy={p.y} r="3.8" fill={C.surface} stroke={s.color} strokeWidth="2"/>)}</g>)}</g>
    {xticks.filter(t => t >= minX && t <= maxX).map((t,i) => <text className="chart-tick" key={i} x={x(t)} y={height-8} textAnchor={i===0 ? 'start' : i===xticks.length-1 ? 'end' : 'middle'}>{tickFormat(t)}</text>)}
  </svg>;
}
export function Legend({items}: {items: {label: string; color: string; dashed?: boolean}[]}) {return <div className="legend">{items.map(item => <span key={item.label}><i style={{background: item.dashed ? 'transparent' : item.color, borderTop: item.dashed ? `2px dashed ${item.color}` : undefined}}/>{item.label}</span>)}</div>;}
export async function get(path: string, signal?: AbortSignal) {
  const response = await fetch(path, {signal});
  if (!response.ok) {let message = `Could not load the published data (${response.status}).`; try {const body = await response.json(); if (typeof body.detail === 'string') message = body.detail;} catch {} throw new Error(message);}
  return response.json();
}
