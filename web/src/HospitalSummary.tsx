import { type CSSProperties } from 'react';
import { AnimatedNumber, day, driverName, Icon, number, title, type Json, type Trust } from './ui';
import { centralStatus, forecastAt, mapStatuses } from './mapModel';

type Props = {
  selected: Trust;
  current: Json | null;
  trustError: string;
  horizon: number;
  onHospital: () => void;
  onPlan: () => void;
};

/** Values and dates are exact snapshot outputs; the clock is decoration only. */
export default function HospitalSummary({selected, current, trustError, horizon, onHospital, onPlan}: Props) {
  const prediction = horizon ? forecastAt(selected, horizon) : undefined;
  const latest = selected.latest_backlog;
  const hasEstimate = typeof prediction?.point_forecast === 'number' && Number.isFinite(prediction.point_forecast);
  const hasLatest = typeof latest === 'number' && Number.isFinite(latest);
  const direction = centralStatus(latest, prediction?.point_forecast);
  const status = mapStatuses[direction];
  const difference = hasEstimate && hasLatest ? Math.round(prediction!.point_forecast) - Math.round(latest!) : null;
  const diagnosis = current?.bottleneck?.diagnosis_driver;
  const treatment = current?.bottleneck?.treatment_driver;
  const drivers = [diagnosis && {stage:'Diagnosis', name:driverName(diagnosis)}, treatment && {stage:'Treatment', name:driverName(treatment)}].filter(Boolean) as {stage:string;name:string}[];
  const stages = [{name:'Referral', active:false}, {name:'Diagnosis', active:!!diagnosis}, {name:'Treatment', active:!!treatment}];
  const motionKey = `${selected.org_code}-${horizon}`;
  const planningNeedsReview = current?.decision?.planning_consistency?.requires_review || (current?.decision && current.decision.status !== 'ready');
  const forecastDate = prediction?.target_date ? day(prediction.target_date) : 'Date unavailable';

  return <article className={`hospital-summary ${drivers.length > 1 ? 'has-two-drivers' : ''}`} aria-labelledby="selected-hospital-name" style={{'--outlook-color':horizon ? status.color : '#67E8F9'} as CSSProperties}>
    <header className="summary-heading">
      <div className="summary-kicker"><span className="summary-selection-dot"/>Selected hospital <span className="summary-horizon-label"><Icon name="clock" size={14}/>{horizon ? `${horizon}-week outlook` : 'Latest report'}</span></div>
      <h1 id="selected-hospital-name">{title(selected.name)}</h1>
    </header>

    <section className={`summary-comparison ${horizon ? '' : 'is-reported'}`} aria-label="People waiting over 62 days for cancer treatment">
      <svg className="summary-clock-art" viewBox="0 0 220 220" aria-hidden="true"><circle cx="110" cy="110" r="96"/>{Array.from({length:12},(_,i)=><path key={i} d="M110 14v8" transform={`rotate(${i*30} 110 110)`}/>)}<path key={motionKey} className="summary-clock-hand" d="M110 110V48m0 62 40 23"/><circle className="summary-clock-centre" cx="110" cy="110" r="3"/></svg>
      <p className="summary-unit">People waiting <strong>over 62 days</strong></p>
      <div className="summary-hero-row" aria-live="polite" aria-atomic="true">
        <div className="summary-hero-value"><AnimatedNumber key={selected.org_code} from={horizon ? latest : undefined} value={horizon ? (hasEstimate ? prediction!.point_forecast : null) : latest}/></div>
        <div className={`summary-status status-${horizon ? direction : 'reported'}`}><span aria-hidden="true">{horizon ? status.symbol : '•'}</span><span>{horizon ? status.label : 'Reported'}</span></div>
      </div>
      <p className="summary-hero-date">{horizon ? <>Estimated for <strong>{hasEstimate ? forecastDate : 'this horizon'}</strong></> : <>Reported week ending <strong>{day(selected.latest_observed_week || undefined)}</strong></>}</p>

      {horizon > 0 && <div className="summary-baseline"><div><span className="summary-baseline-dot"/><span>Last reported</span><strong><AnimatedNumber key={selected.org_code} value={latest}/></strong></div><svg viewBox="0 0 65 16" aria-hidden="true"><path d="M1 8h59"/><circle key={motionKey} className="summary-baseline-traveller" cx="4" cy="8" r="2"/></svg><span>{day(selected.latest_observed_week || undefined,true)}</span></div>}
      <div className="summary-explanation" key={`${motionKey}-explanation`}>
        {!horizon ? <p>Choose a future week to see what could change.</p> : difference == null ? <p>There isn’t enough recent data for an outlook.</p> : difference === 0 ? <p>About the <strong>same number</strong> as last reported.</p> : <p><strong>{number(Math.abs(difference))} {difference > 0 ? 'more' : 'fewer'} {Math.abs(difference)===1?'person':'people'}</strong> than last reported.</p>}
      </div>
      {horizon > 0 && hasEstimate && <p className="summary-range"><span>80% forecast range</span><strong>{number(prediction!.lower_80)}–{number(prediction!.upper_80)}</strong></p>}
    </section>

    <section className="summary-pressure" aria-label="Likely pressure point">
      <div className="summary-section-title"><span>Likely pressure point</span><Icon name="clock" size={16}/></div>
      <div className="summary-pathway" aria-hidden="true">{stages.map((stage,index)=><div className={`summary-pathway-item ${stage.active ? 'under-pressure' : ''}`} key={stage.name}><div className="summary-pathway-rail"><i/>{index < 2 && <span/>}</div><span>{stage.name}</span></div>)}</div>
      <div className="summary-drivers">{drivers.length ? drivers.map(driver=><strong key={driver.stage} aria-label={`${driver.stage}: ${driver.name}`}><span>{drivers.length > 1 ? `${driver.stage}: ` : ''}</span>{driver.name}</strong>) : <strong className="summary-no-driver">{current ? 'No clear pressure point' : trustError ? 'Pathway evidence unavailable' : 'Opening pathway evidence…'}</strong>}</div>
    </section>

    <button className="summary-recovery-button" onClick={onPlan}><span>{planningNeedsReview ? 'View planning options' : 'Test a recovery plan'}</span><span className="summary-button-arrow"><Icon name="arrow" size={21}/></span></button>
    <div className="summary-foot"><span>{horizon ? 'Estimate, not a guarantee.' : 'Reported public data.'}</span><button onClick={onHospital}>Details <Icon name="chevron" size={14}/></button></div>
    {trustError && <p className="summary-error" role="alert">Pathway details are temporarily unavailable.</p>}
  </article>;
}
