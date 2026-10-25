import { useEffect, useId, useMemo, useState } from 'react';
import { day, number, useReducedMotion } from './ui';
import './landing.css';

type Props = {
  total: number | null;
  reportedDate: string | null;
  onExplore: () => void;
  onEvidence: () => void;
  onAbout: () => void;
};

const FULL = 112, TARGET = 62, END = 104, RADIUS = 196;
const angle = (days: number) => days / FULL * Math.PI * 2;
const clamp = (value: number) => Math.max(0, Math.min(1, value));
const easeInOut = (value: number) => value < .5 ? 4 * value ** 3 : 1 - (-2 * value + 2) ** 3 / 2;
const easeOut = (value: number) => 1 - (1 - value) ** 3;
const point = (r: number, a: number) => [Math.sin(a) * r, -Math.cos(a) * r];

/** The same annular arc as the supplied page, without its D3 dependency. */
function ringArc(start: number, end: number) {
  if (end <= start) return '';
  const inner = RADIUS - 13, outer = RADIUS + 13;
  const a = point(outer, start), b = point(outer, end), c = point(inner, end), d = point(inner, start);
  const large = end - start > Math.PI ? 1 : 0;
  return `M${a[0]},${a[1]} A${outer},${outer} 0 ${large} 1 ${b[0]},${b[1]} L${c[0]},${c[1]} A${inner},${inner} 0 ${large} 0 ${d[0]},${d[1]} Z`;
}

export default function Landing({total, reportedDate, onExplore, onEvidence, onAbout}: Props) {
  const reduced = useReducedMotion();
  const [elapsed, setElapsed] = useState(reduced ? 4700 : 0);
  const gradient = `landing-late-${useId().replaceAll(':', '')}`;
  useEffect(() => {
    if (reduced) { setElapsed(4700); return; }
    const start = performance.now(); let frame = 0;
    const update = (now: number) => { const value = Math.min(4700, now - start); setElapsed(value); if (value < 4700) frame = requestAnimationFrame(update); };
    frame = requestAnimationFrame(update);
    return () => cancelAnimationFrame(frame);
  }, [reduced]);
  const clockDay = elapsed < 2500
    ? TARGET * easeInOut(clamp((elapsed - 300) / 2200))
    : TARGET + (END - TARGET) * easeOut(clamp((elapsed - 2900) / 1400));
  const ticks = useMemo(() => Array.from({length: FULL}, (_, index) => {
    const a = angle(index), week = index % 7 === 0;
    const start = point(RADIUS + 24, a), end = point(RADIUS + (week ? 38 : 30), a);
    return <line key={index} className={`landing-tick ${week ? 'is-week' : ''}`} x1={start[0]} y1={start[1]} x2={end[0]} y2={end[1]}/>;
  }), []);
  const targetAngle = angle(TARGET), targetInner = point(RADIUS - 30, targetAngle), targetOuter = point(RADIUS + 48, targetAngle), targetText = point(RADIUS + 64, targetAngle);
  const validTotal = typeof total === 'number' && Number.isFinite(total) && total >= 0;
  const shownTotal = validTotal ? total * (1 - (1 - clamp((elapsed - 3100) / 1600)) ** 4) : null;

  return <section id="hero" tabIndex={-1} className={`cc-landing ${reduced ? 'is-reduced-motion' : ''}`} aria-labelledby="landing-hero-title">
    <header className="landing-topbar">
      <button type="button" className="landing-brand" onClick={onAbout} aria-label="About Cancer Clock">
        <svg viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="13"/><path className="landing-brand-arc" d="M16 3a13 13 0 0 1 12.4 9"/><path d="M16 9v7l4 3"/></svg>
        <span>Cancer Clock</span>
      </button>
      <nav className="landing-topnav" aria-label="Introduction navigation">
        <button type="button" onClick={onExplore}>England</button>
        <button type="button" onClick={onEvidence}>How we know</button>
      </nav>
    </header>
    <div className="landing-hero">
      <div className="landing-hero-copy">
        <h1 id="landing-hero-title"><span className="landing-line">Cancer treatment</span><span className="landing-line">should start within</span><span className="landing-line">62 days.</span></h1>
        <p className="landing-hero-sub">
          <span className="landing-big-num" aria-label={validTotal ? number(total) : 'Published count loading'}><span aria-hidden="true">{validTotal ? number(shownTotal) : '—'}</span></span>
          <span className="landing-hero-sub-text">people in England are still waiting past that point.</span>
        </p>
        <p className="landing-hero-note">The target has not been met since December 2015.<span className="landing-reported">{reportedDate ? `Reported week ending ${day(reportedDate)}.` : 'Opening the latest published England count…'}</span></p>
        <button type="button" className="landing-cta" onClick={onExplore}>Take me to Cancer Clock</button>
      </div>
      <div className="landing-hero-clock">
        <svg className="landing-clock" viewBox="0 0 520 520" aria-hidden="true">
          <defs><linearGradient id={gradient} x1="0" y1="1" x2="1" y2="0"><stop offset="0" stopColor="#F2674E"/><stop offset="1" stopColor="#9E0F2E"/></linearGradient></defs>
          <g transform="translate(260,260)">
            {ticks}<circle className="landing-track" r={RADIUS}/>
            <path fill="#15142B" d={ringArc(0, angle(Math.min(clockDay, TARGET)))}/>
            <path fill={`url(#${gradient})`} d={clockDay > TARGET ? ringArc(targetAngle, angle(clockDay)) : ''}/>
            <g opacity={1 - (1 - clamp((elapsed - 2500) / 400)) ** 2}>
              <line className="landing-target-mark" x1={targetInner[0]} y1={targetInner[1]} x2={targetOuter[0]} y2={targetOuter[1]}/>
              <text className="landing-target-label" x={targetText[0]} y={targetText[1] + 5} textAnchor="end">Target: day 62</text>
            </g>
            <text className={`landing-face-num ${clockDay > TARGET ? 'is-late' : ''}`} y="20">{Math.round(clockDay)}</text>
            <text className="landing-face-label" y="62">{elapsed >= 2900 ? 'and still waiting' : 'days since referral'}</text>
          </g>
        </svg>
        <p className="landing-clock-caption">Illustrative clock, not a patient’s wait.</p>
      </div>
      <button type="button" className="landing-scroll-cue" onClick={onExplore} aria-label="Go to the hospital map"><span/></button>
    </div>
  </section>;
}
