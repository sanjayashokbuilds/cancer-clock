import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { AnimatedNumber, day, driverName, Icon, number, title, type Json, type Trust } from './ui';
import { centralStatus, forecastAt, mapStatuses } from './mapModel';

type Props = {
  trust: Trust;
  current: Json | null;
  trustError?: string;
  onChooseHospital: () => void;
  onPlan: () => void;
  onDetails: () => void;
};

/** A separate hospital story. All values are exact published snapshot outputs. */
export default function HospitalForecast({trust, current, trustError = '', onChooseHospital, onPlan, onDetails}: Props) {
  const [horizon, setHorizon] = useState(8);
  const [inView, setInView] = useState(false);
  const section = useRef<HTMLElement>(null);
  useEffect(() => {
    const node = section.current;
    if (!node) return;
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), {threshold:.2});
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const prediction = forecastAt(trust, horizon);
  const latest = trust.latest_backlog;
  const hasLatest = typeof latest === 'number' && Number.isFinite(latest) && latest >= 0;
  const estimate = prediction?.point_forecast;
  const hasEstimate = typeof estimate === 'number' && Number.isFinite(estimate) && estimate >= 0;
  const direction = centralStatus(latest, estimate);
  const status = mapStatuses[direction];
  const difference = hasLatest && hasEstimate ? Math.round(estimate) - Math.round(latest) : null;
  const low = prediction?.lower_80, high = prediction?.upper_80;
  const hasRange = hasEstimate && typeof low === 'number' && typeof high === 'number' && Number.isFinite(low) && Number.isFinite(high);
  const rangePosition = hasRange && high > low ? Math.max(0, Math.min(100, (estimate - low) / (high - low) * 100)) : 50;
  const issueDate = prediction?.issue_date || current?.forecast?.issue_date || trust.forecasts?.[0]?.issue_date;
  const diagnosis = current?.bottleneck?.diagnosis_driver;
  const treatment = current?.bottleneck?.treatment_driver;
  const drivers = [diagnosis && {stage:'Diagnosis', name:driverName(diagnosis)}, treatment && {stage:'Treatment', name:driverName(treatment)}].filter(Boolean) as {stage:string;name:string}[];
  const stages = [{name:'Referral', icon:'person', active:false}, {name:'Diagnosis', icon:'search', active:!!diagnosis}, {name:'Treatment', icon:'plus', active:!!treatment}];
  const decision = current?.decision;
  const needsReview = decision?.planning_consistency?.requires_review === true || (decision && decision.status !== 'ready');
  const motionKey = `${trust.org_code}-${horizon}`;
  const pressureSentence = drivers.length === 2
    ? 'Pressure appears in both diagnosis and treatment.'
    : treatment ? 'Treatment is the likely pressure point.'
      : diagnosis ? 'Diagnosis is the likely pressure point.'
        : current ? 'No clear pressure point stands out.'
          : trustError ? 'The pathway evidence is unavailable.' : 'Opening the pathway evidence…';

  return <section ref={section} className={`hospital-forecast ${inView ? 'is-visible' : ''}`} aria-labelledby="hospital-forecast-title" style={{'--forecast-color':status.color} as CSSProperties}>
    <div className="hf-inner">
      <header className="hf-header hf-reveal">
        <div><p className="hf-context"><span/>Your hospital outlook</p><h2 id="hospital-forecast-title">{title(trust.name)}</h2></div>
        <button className="hf-choose" onClick={onChooseHospital}><Icon name="back" size={18}/>Choose another hospital</button>
      </header>

      <div className="hf-toolbar hf-reveal">
        <p>People waiting <strong>over 62 days</strong> for cancer treatment</p>
        <div className="hf-horizons" role="group" aria-label="Hospital forecast horizon" style={{'--active-horizon':[4,8,12].indexOf(horizon)} as CSSProperties}><span aria-hidden="true"/>{[4,8,12].map(value=><button key={value} aria-pressed={horizon === value} className={horizon === value ? 'active' : ''} onClick={()=>setHorizon(value)}>{value} weeks</button>)}</div>
      </div>

      <div className="hf-story">
        <div className="hf-outlook hf-reveal">
          <div className="hf-numbers" aria-live="polite" aria-atomic="true">
            <div className="hf-count"><span className="hf-count-label">Latest reported</span><strong>{inView ? <AnimatedNumber key={trust.org_code} value={hasLatest ? latest : null}/> : number(latest)}</strong><small>Week ending {day(trust.latest_observed_week || undefined)}</small></div>
            <div className="hf-bridge" aria-hidden="true"><svg viewBox="0 0 90 52"><path className="hf-bridge-rule" d="M5 26h75m-15-14 15 14-15 14"/><circle key={motionKey} className="hf-traveller" cx="5" cy="26" r="3"/></svg></div>
            <div className="hf-count hf-estimate"><span className="hf-count-label">{horizon}-week estimate</span><strong>{inView ? <AnimatedNumber key={trust.org_code} from={hasLatest ? latest : undefined} value={hasEstimate ? estimate : null}/> : number(hasEstimate ? estimate : null)}</strong><small>{hasEstimate && prediction?.target_date ? `For ${day(prediction.target_date)}` : 'Forecast unavailable'}</small></div>
          </div>

          <div key={motionKey} className="hf-change">
            <span className={`hf-status status-${direction}`}><span aria-hidden="true">{status.symbol}</span>{status.label}</span>
            <p>{difference == null ? 'There isn’t enough recent data for this comparison.' : difference === 0 ? <>About the <strong>same number</strong> as last reported.</> : <><strong>{number(Math.abs(difference))} {difference > 0 ? 'more' : 'fewer'} {Math.abs(difference) === 1 ? 'person' : 'people'}</strong> than last reported.</>}</p>
          </div>

          {hasRange && <div className="hf-range" aria-label={`80% forecast range: ${number(low)} to ${number(high)} people; estimate ${number(estimate)}`}>
            <div><span>80% forecast range</span><strong>{number(low)}–{number(high)} <small>people</small></strong></div>
            <div className="hf-range-track" aria-hidden="true"><span style={{left:`${rangePosition}%`}}/></div>
          </div>}
          <p className="hf-estimate-note">{hasEstimate ? 'The actual number could be higher or lower.' : 'The reported count is still available above.'}</p>
        </div>

        <aside className="hf-pressure hf-reveal" aria-label="Likely pressure point">
          <p className="hf-pressure-label">Where is the pressure?</p>
          <div className="hf-pathway" aria-hidden="true">{stages.map((stage,index)=><div className={`hf-stage ${stage.active ? 'under-pressure' : ''}`} key={stage.name}><div className="hf-stage-line"><span><Icon name={stage.icon} size={20}/></span>{index < 2 && <i/>}</div><span>{stage.name}</span></div>)}</div>
          <h3>{pressureSentence}</h3>
          {drivers.length > 0 && <div className="hf-drivers">{drivers.map(driver=><div key={driver.stage}>{drivers.length > 1 && <span>{driver.stage}</span>}<strong>{driver.name}</strong></div>)}</div>}
          <button className="hf-details" onClick={onDetails} disabled={!current}>See the evidence <Icon name="chevron" size={17}/></button>
          {trustError && <p className="hf-error" role="alert">Pathway details could not be loaded.</p>}
        </aside>
      </div>

      <footer className="hf-bottom hf-reveal">
        <p>{issueDate ? <>Forecast issued <strong>{day(issueDate)}</strong>.<br/>The {horizon} weeks start from this date.</> : <>A forecast date is unavailable for this hospital.</>}</p>
        <div className="hf-plan"><button onClick={onPlan}><span>{needsReview || !decision ? 'View planning options' : 'Test a recovery plan'}</span><Icon name="arrow" size={24}/></button>{needsReview && <span>Recovery planning needs a model review.</span>}</div>
      </footer>
    </div>
  </section>;
}
