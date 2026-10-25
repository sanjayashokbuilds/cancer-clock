import { useMemo, useState, type CSSProperties } from 'react';
import { AnimatedNumber, C, day, Icon, Legend, LineChart, Notice, number, title, type ChartSeries, type Json, type Trust } from './ui';

const pressures=[{key:'strike',label:"5-day doctors’ strike",note:''},{key:'winter',label:'Winter pressure',note:''},{key:'surge',label:'Referral surge',note:'For example, after a celebrity diagnosis'}];
export default function PlanView({trust,decision,onBack,onHow,onExamplePlan}: {trust:Trust;decision:Json;onBack:()=>void;onHow:()=>void;onExamplePlan?:()=>void}) {
  const [flags,setFlags]=useState({strike:true,winter:false,surge:false});
  const [stage,setStage]=useState<'diagnosis'|'treatment'>(decision.bottleneck_label==='diagnosis-limited'?'diagnosis':'treatment');
  const [capacity,setCapacity]=useState(0);
  const grid=decision.planning_grid;
  const doses:number[]=grid?.capacity_percent || [0,1,2,3,4,5,10,15,20];
  const scenario=grid?.scenarios?.find((s:Json)=>s.flags.strike===flags.strike&&s.flags.winter===flags.winter&&s.flags.surge===flags.surge);
  const plans=scenario?.plans?.[stage] || []; const active=plans.find((p:Json)=>p.extra_capacity_pct===capacity); const baseline=plans.find((p:Json)=>p.extra_capacity_pct===0);
  const dates:string[]=grid?.dates || [];
  const days:number[]=grid?.day_offsets || dates.map((_,i)=>i*7);
  const marginal=scenario?.marginal_benefit?.[stage];
  const effect=(active?.final_backlog?.median ?? 0)-(baseline?.final_backlog?.median ?? 0);
  const outcomeColor=effect<-.5?C.teal:effect>.5?C.orange:C.slate;
  const stageColor=stage==='diagnosis'?C.diagnosis:C.treatment;
  const treatmentLabel=(decision.treatment_label || 'Treatment capacity').replace(/ \(stage proxy\)/,'');
  const meaningful=marginal?.median>=.5&&marginal?.lower_80>.05;
  const little=marginal&&Math.abs(marginal.median)<.5;
  const inconsistent=decision.planning_consistency?.requires_review===true;
  const conflict=decision.planning_consistency?.status==='conflict';
  const review=decision.planning_consistency;
  const hasComparison=conflict&&Number.isFinite(review?.forecast?.median)&&Number.isFinite(review?.simulator_baseline?.median);
  const unavailable=decision.status!=='ready'||!grid?.scenarios?.length;
  const maxY=useMemo(()=>{
    const all=(scenario?.plans?.[stage] || []).flatMap((p:Json)=>p.backlog_62?.upper_80 || []);
    const raw=Math.max(10,...all)*1.08; const magnitude=10**Math.floor(Math.log10(raw));return Math.ceil(raw/magnitude*2)/2*magnitude;
  },[scenario,stage]);
  const series:ChartSeries[]=[{name:'Do nothing',color:C.slate,points:(baseline?.backlog_62?.median||[]).map((v:number,i:number)=>({x:days[i],y:v}))},{name:'Your plan',color:outcomeColor,band:true,points:(active?.backlog_62?.median||[]).map((v:number,i:number)=>({x:days[i],y:v,low:active.backlog_62.lower_80[i],high:active.backlog_62.upper_80[i]}))}];
  const chooseDose=(n:number)=>setCapacity(doses.reduce((a,b)=>Math.abs(b-n)<Math.abs(a-n)?b:a));
  return <section className="plan-screen"><div className="plan-heading"><div><button className="quiet-link back-link" onClick={onBack}><Icon name="back" size={18}/>Hospital outlook</button><h1>{inconsistent||unavailable?'Recovery planning':'What could change here?'}</h1><p>{title(trust.name)}</p></div><button className="quiet-link how-link" onClick={onHow}><Icon name="info" size={18}/>How this works</button></div>
    {inconsistent||unavailable?<div className="recovery-review" aria-label="Recovery model review">
      <section className="recovery-review-main">
        <div className="review-status"><span/><span>Model review needed</span></div>
        <h2>{unavailable?'Planning is not available here yet.':conflict?'A model check comes first.':'A forecast check comes first.'}</h2>
        <p className="review-explanation">{unavailable?'A complete recovery model is not available for this hospital in the current snapshot.':conflict?'The recovery model’s baseline is outside the forecast’s 80% range. We are holding its planning results until this difference has been reviewed.':'A matching forecast is missing, so we cannot check this recovery model yet.'}</p>
        {hasComparison?<div className="review-comparison">
          <p>People waiting over 62 days on <b>{day(review.comparison_date)}</b></p>
          <div className="review-comparison-values"><div><span>Forecast estimate</span><strong><AnimatedNumber value={review.forecast.median}/></strong></div><span className="review-comparison-divider" aria-hidden="true"/><div><span>Recovery model</span><strong><AnimatedNumber value={review.simulator_baseline.median}/></strong></div></div>
          <p className="review-comparison-note">Without extra capacity or disruptions. The recovery estimate is {number(review.simulator_baseline.median,1)}; the forecast’s 80% range is {number(review.forecast.lower_80,1)}–{number(review.forecast.upper_80,1)}.</p>
        </div>:<div className="review-available"><Icon name="clock" size={31}/><p>You can still explore the hospital’s reported waiting list and pathway evidence.</p></div>}
        <div className="review-secondary-actions"><button className="quiet-link" onClick={onBack}><Icon name="back" size={17}/>Hospital outlook</button><button className="quiet-link" onClick={onHow}>Why this needs review <Icon name="chevron" size={16}/></button></div>
      </section>
      {onExamplePlan&&trust.org_code!=='RTH'?<aside className="recovery-example">
        <div className="recovery-example-clock" aria-hidden="true"><span/><Icon name="clock" size={57}/></div>
        <p className="review-example-kicker">Keep exploring</p>
        <h3>Try a recovery plan<br/>in Oxford.</h3>
        <p>Compare extra capacity and disruptions using Oxford University Hospitals’ data.</p>
        <div className="review-example-flow" aria-hidden="true"><span>Choose capacity</span><Icon name="arrow" size={17}/><span>See the effect</span></div>
        <button className="review-example-button" onClick={onExamplePlan}>Open Oxford example <Icon name="arrow" size={21}/></button>
        <small>This switches hospitals. The model’s assumptions still apply.</small>
      </aside>:<aside className="recovery-example"><div className="recovery-example-clock" aria-hidden="true"><Icon name="clock" size={57}/></div><p className="review-example-kicker">Keep exploring</p><h3>The hospital story<br/>is still here.</h3><p>Return to the waiting-list outlook and the evidence behind its pressure point.</p><button className="review-example-button" onClick={onBack}>Open hospital outlook <Icon name="arrow" size={21}/></button></aside>}
    </div>:<div className="plan-layout">
      <aside className="plan-controls panel"><h2>Choose the pressures</h2><div className="pressure-toggles">{pressures.map(p=><label className="pressure-control" key={p.key}><span><b>{p.label}</b>{p.note&&<small>{p.note}</small>}</span><button type="button" role="switch" aria-label={p.label} aria-checked={flags[p.key as keyof typeof flags]} className={`switch ${flags[p.key as keyof typeof flags]?'on':''}`} onClick={()=>setFlags(previous=>({...previous,[p.key]:!previous[p.key as keyof typeof flags]}))}><i/></button></label>)}</div><div className="capacity-controls"><h2>Add capacity to</h2><div className="segmented" role="group" aria-label="Stage receiving extra capacity"><button className={stage==='diagnosis'?'selected diagnosis':''} onClick={()=>setStage('diagnosis')} aria-pressed={stage==='diagnosis'}>Diagnosis</button><button className={stage==='treatment'?'selected treatment':''} onClick={()=>setStage('treatment')} aria-pressed={stage==='treatment'}>Treatment</button></div><div className="capacity-value"><span>{stage==='diagnosis'?'Diagnosis capacity':treatmentLabel}</span><strong style={{color:stageColor}}>+<AnimatedNumber value={capacity}/>%</strong></div><div className="capacity-slider-wrap" style={{'--stage-color':stageColor,'--capacity-progress':`${capacity/20*100}%`} as CSSProperties}><input className="capacity-slider" type="range" min="0" max="20" step="1" value={capacity} aria-label={`Extra ${stage} capacity`} aria-valuetext={`${capacity}% extra capacity`} onChange={e=>chooseDose(Number(e.target.value))} onKeyDown={e=>{if(['ArrowRight','ArrowUp','ArrowLeft','ArrowDown'].includes(e.key)){e.preventDefault();const delta=['ArrowRight','ArrowUp'].includes(e.key)?1:-1;setCapacity(doses[Math.max(0,Math.min(doses.length-1,doses.indexOf(capacity)+delta))]);}}}/><div className="capacity-marks" aria-hidden="true">{doses.map(d=><i key={d} style={{left:`${d/20*100}%`}}/>)}{[0,5,10,15,20].map(d=><span key={d} style={{left:`${d/20*100}%`}}>{d}%</span>)}</div></div><p className="capacity-timing">Extra capacity starts in week 4.</p>{stage==='treatment'&&treatmentLabel!=='Treatment capacity'&&<p className="stage-proxy-note">{treatmentLabel.replace(' capacity','')} is the observed pressure. This changes the whole treatment stage.</p>}</div></aside>
      <div className="plan-result panel">
        {decision.prior_conflict&&<Notice warning>Pathway evidence and fitted capacity disagree here. <button className="inline-link" onClick={onHow}>Read the assumptions.</button></Notice>}
        {decision.acceptable_fit===false&&<Notice warning>This model is a weak fit to the recent history.</Notice>}
        <div className="outcome-heading">In 6 months</div><div className="outcome-numbers" aria-live="polite" aria-atomic="true"><span className="outcome-baseline"><AnimatedNumber value={baseline?.final_backlog?.median}/></span><span className="outcome-arrow"><Icon name="arrow" size={42}/></span><strong style={{color:outcomeColor}}><AnimatedNumber value={active?.final_backlog?.median}/></strong></div><p className="outcome-unit">people waiting over 62 days</p><p className="outcome-range">Your plan: {number(active?.final_backlog?.lower_80)}–{number(active?.final_backlog?.upper_80)} people <span>(80% model range)</span></p>
        <div className="scenario-chart"><div className="chart-heading"><Legend items={[{label:'Do nothing',color:C.slate},{label:'Your plan',color:outcomeColor}]}/><span className="chart-end-date">{dates.length?`${day(dates[0],true)} to ${day(dates.at(-1))}`:''}</span></div><LineChart series={series} label="People waiting over 62 days under no extra capacity and your selected recovery plan" height={260} fixedMax={maxY} ticks={[0,28,91,182]} tickFormat={x=>x===0?'Start':x===28?'Week 4':x===91?'3 months':'6 months'} marker={{x:28,label:'Plan begins'}}/></div>
        <div className={`plan-takeaway ${meaningful?'supported':''}`}><span className="takeaway-line" style={{background:meaningful?C.teal:C.slate}}/>{meaningful?<p>Each extra <b>1%</b> of {stage==='diagnosis'?'diagnosis':'treatment'} capacity ≈ <b><AnimatedNumber value={marginal.median}/></b> fewer people waiting.<small>Near 0–5% extra capacity, under these assumptions.</small></p>:little?<p>Extra {stage} capacity makes little difference in this model.<small>The other stage may be limiting progress.</small></p>:<p>The effect of extra {stage} capacity is uncertain.<small>Review the assumptions before interpreting this comparison.</small></p>}</div>
        <p className="plan-footnote">“Do nothing” includes the same pressures, with no extra capacity. This is a planning scenario, not a forecast or a staffing recommendation.</p>
      </div>
    </div>}
  </section>;
}
