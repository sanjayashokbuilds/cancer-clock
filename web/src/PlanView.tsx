import { useMemo, useState, type CSSProperties } from 'react';
import { AnimatedNumber, C, day, Icon, Legend, LineChart, number, title, type ChartSeries, type Json, type Trust } from './ui';
import './plan-focus.css';

const pressures=[{key:'strike',label:"5-day doctors’ strike",note:''},{key:'winter',label:'Winter pressure',note:''},{key:'surge',label:'Referral surge',note:'For example, after a celebrity diagnosis'}];
export default function PlanView({trust,decision,onBack,onHow,onExamplePlan}: {trust:Trust;decision:Json;onBack:()=>void;onHow:()=>void;onExamplePlan?:()=>void}) {
  const [flags,setFlags]=useState({strike:false,winter:false,surge:false});
  const [stage,setStage]=useState<'diagnosis'|'treatment'>(decision.bottleneck_label==='diagnosis-limited'?'diagnosis':'treatment');
  const [capacity,setCapacity]=useState(0);
  const activePressures=Object.values(flags).filter(Boolean).length;
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
  const unavailable=decision.status!=='ready'||grid?.status!=='ready'||!grid?.scenarios?.length;
  const reasonCodes:string[]=decision.eligibility?.reason_codes||grid?.eligibility?.reason_codes||[];
  const missingForecast=reasonCodes.includes('forecast_unavailable');
  const maxY=useMemo(()=>{
    const all=(scenario?.plans?.[stage] || []).flatMap((p:Json)=>p.backlog_62?.upper_80 || []);
    const raw=Math.max(10,...all)*1.08; const magnitude=10**Math.floor(Math.log10(raw));return Math.ceil(raw/magnitude*2)/2*magnitude;
  },[scenario,stage]);
  const series:ChartSeries[]=[{name:'No extra capacity',color:C.slate,points:(baseline?.backlog_62?.median||[]).map((v:number,i:number)=>({x:days[i],y:v}))},{name:'Your plan',color:C.cyan,band:true,points:(active?.backlog_62?.median||[]).map((v:number,i:number)=>({x:days[i],y:v,low:active.backlog_62.lower_80[i],high:active.backlog_62.upper_80[i]}))}];
  const chooseDose=(n:number)=>setCapacity(doses.reduce((a,b)=>Math.abs(b-n)<Math.abs(a-n)?b:a));
  return <section className={`plan-screen ${!unavailable?'plan-focused':''}`}><div className="plan-heading"><div><button className="quiet-link back-link" onClick={onBack} aria-label="Back to hospital outlook"><Icon name="back" size={18}/>{unavailable?'Hospital outlook':title(trust.name)}</button><h1>{unavailable?'Recovery planning':'What could extra capacity change?'}</h1>{(unavailable)&&<p>{title(trust.name)}</p>}</div><button className="quiet-link how-link" onClick={onHow}><Icon name="info" size={18}/>How this works</button></div>
    {unavailable?<div className="recovery-hold" aria-label="Recovery plan availability">
      <div className="recovery-hold-icon" aria-hidden="true"><Icon name="clock" size={31}/></div>
      <h2>We don't show a recovery plan for this hospital yet</h2>
      <p>{missingForecast?"This hospital doesn't have a complete forecast in the current snapshot. A recovery plan needs that starting point, so we hold it back until the forecast is available.":"Before showing any plan, we check our queue model fits this hospital's history well. Here it doesn't fit closely enough, usually because recent figures are erratic. Rather than show a number we can't stand behind, we hold it back."}</p>
      {onExamplePlan&&trust.org_code!=='RTH'&&<button className="primary-button" onClick={onExamplePlan}>Try Oxford instead <Icon name="arrow" size={21}/></button>}
    </div>:<div className="plan-layout focus-plan-layout">
      <aside className="plan-controls panel focus-plan-controls">
        <div className="focus-capacity-heading"><h2>Add capacity</h2><Icon name="plus" size={19}/></div>
        <div className="segmented" role="group" aria-label="Stage receiving extra capacity"><button className={stage==='diagnosis'?'selected diagnosis':''} onClick={()=>setStage('diagnosis')} aria-pressed={stage==='diagnosis'}>Diagnosis</button><button className={stage==='treatment'?'selected treatment':''} onClick={()=>setStage('treatment')} aria-pressed={stage==='treatment'}>Treatment</button></div>
        <div className="capacity-value"><span>Extra {stage} capacity</span><strong style={{color:stageColor}}>+<AnimatedNumber value={capacity}/>%</strong></div>
        {stage==='treatment'&&treatmentLabel!=='Treatment capacity'&&<p className="focus-modality">Observed pressure: {treatmentLabel.replace(/ capacity$/i,'')}</p>}
        <div className="capacity-slider-wrap" style={{'--stage-color':stageColor,'--capacity-progress':`${capacity/20*100}%`} as CSSProperties}><input className="capacity-slider" type="range" min="0" max="20" step="1" value={capacity} aria-label={`Extra ${stage} capacity`} aria-valuetext={`${capacity}% extra capacity`} onChange={e=>chooseDose(Number(e.target.value))} onKeyDown={e=>{if(['ArrowRight','ArrowUp','ArrowLeft','ArrowDown'].includes(e.key)){e.preventDefault();const delta=['ArrowRight','ArrowUp'].includes(e.key)?1:-1;setCapacity(doses[Math.max(0,Math.min(doses.length-1,doses.indexOf(capacity)+delta))]);}}}/><div className="capacity-marks" aria-hidden="true">{doses.map(d=><i key={d} style={{left:`${d/20*100}%`}}/>)}{[0,5,10,15,20].map(d=><span key={d} style={{left:`${d/20*100}%`}}>{d}%</span>)}</div></div>
        <p className="capacity-timing">Any extra capacity starts in week 4.</p>
        <details className="focus-disruptions"><summary><span>Add disruptions</span><span className={`focus-disruption-count ${activePressures?'is-active':''}`}>{activePressures} active</span><Icon name="chevron" size={16}/></summary><div className="pressure-toggles">{pressures.map(p=><label className="pressure-control" key={p.key}><span><b>{p.label}</b></span><button type="button" role="switch" aria-label={p.label} aria-checked={flags[p.key as keyof typeof flags]} className={`switch ${flags[p.key as keyof typeof flags]?'on':''}`} onClick={()=>setFlags(previous=>({...previous,[p.key]:!previous[p.key as keyof typeof flags]}))}><i/></button></label>)}</div></details>
        <button className="focus-assumptions" onClick={onHow}>View assumptions <Icon name="chevron" size={15}/></button>
      </aside>
      <div className="plan-result panel focus-plan-result">
        {decision.prior_conflict&&<div className="focus-model-caution"><Icon name="info" size={16}/><span>Pathway evidence and fitted capacity disagree.</span><button onClick={onHow}>Details</button></div>}
        <div className="focus-outcome-header"><h2>In 12 weeks</h2><span>{dates.length?day(dates.at(-1)):''}</span></div>
        <div className="focus-outcome-comparison" aria-live="polite" aria-atomic="true">
          <div className="focus-outcome-baseline"><span>No extra capacity</span><strong><AnimatedNumber value={baseline?.final_backlog?.median}/></strong></div>
          <span className="focus-outcome-arrow" aria-hidden="true"><Icon name="arrow" size={32}/></span>
          <div className="focus-outcome-plan"><span>Your plan</span><strong style={{color:capacity>0?outcomeColor:C.ink}}><AnimatedNumber value={active?.final_backlog?.median}/></strong></div>
          <div className="focus-outcome-context"><p>people waiting<br/>over 62 days</p><span>80% plan range: <b>{number(active?.final_backlog?.lower_80)}–{number(active?.final_backlog?.upper_80)}</b></span></div>
        </div>
        <div className="scenario-chart focus-scenario-chart"><div className="chart-heading"><Legend items={[{label:'No extra capacity',color:C.slate},{label:'Your plan',color:C.cyan}]}/><span className="chart-end-date">{dates.length?`From ${day(dates[0],true)}`:''}</span></div><LineChart series={series} label="People waiting over 62 days under no extra capacity and your selected recovery plan" height={320} fixedMax={maxY} ticks={[0,28,56,84]} tickFormat={x=>x===0?'Start':`Week ${x/7}`} marker={capacity>0?{x:28,label:'Extra capacity starts'}:undefined}/></div>
        <div className={`focus-plan-takeaway ${capacity>0&&meaningful?'supported':''}`}>
          {capacity===0?<p><Icon name="arrow" size={18}/>Add capacity to compare a plan.</p>:meaningful?<p>Near 0–5%, each extra 1% of {stage} capacity ≈ <b><AnimatedNumber value={marginal.median}/></b> fewer people waiting at 12 weeks.</p>:little?<p>Extra {stage} capacity makes little difference in this model.</p>:<p>The effect of extra {stage} capacity is uncertain.</p>}
        </div>
        <p className="focus-plan-footnote">Both paths include selected pressures. The range reflects the simulated change only; forecast uncertainty is not included.</p>
      </div>
    </div>}
  </section>;
}
