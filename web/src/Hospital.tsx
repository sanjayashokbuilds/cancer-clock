import { AnimatedNumber, C, day, directionColor, Drawer, driverName, Icon, Legend, LineChart, Notice, number, timestamp, title, useDialog, type ChartSeries, type Json, type Trust } from './ui';

export function verdict(forecast: Json, bottleneck: Json, direction: string) {
  const predictions = forecast.forecasts || [];
  const outlook = !predictions.length ? 'There is not enough recent data for a forecast' : direction === 'improving' ? 'Backlog forecast to fall over the next 12 weeks' : direction === 'worsening' ? 'Backlog forecast to rise over the next 12 weeks' : 'The 12-week backlog outlook is unclear';
  const d = bottleneck.diagnosis_driver, t = bottleneck.treatment_driver;
  if (bottleneck.label === 'mixed' && d && t) return `${outlook}; pressure appears in both diagnosis and treatment.`;
  if (d) return `${outlook}; pressure is in diagnosis: ${driverName(d).toLowerCase()}, ${number(d.trust_rate_pct)}% diagnosed within 28 days vs ${number(d.national_rate_pct)}% across England.`;
  if (t) return `${outlook}; pressure is in treatment: ${driverName(t).toLowerCase()}, ${number(t.trust_rate_pct)}% started within 31 days vs ${number(t.national_rate_pct)}% across England.`;
  return `${outlook}; no clear bottleneck stands out in the recent pathway data.`;
}
export function Pathway({bottleneck}: {bottleneck: Json}) {
  const diagnosis = bottleneck.diagnosis_driver; const treatment = bottleneck.treatment_driver;
  const nodes=[{name:'Referral',icon:'person',active:false,stage:'referral'},{name:'Diagnosis',icon:'search',active:!!diagnosis,stage:'diagnosis'},{name:'Treatment',icon:'plus',active:!!treatment,stage:'treatment'}];
  const drivers=[diagnosis,treatment].filter(Boolean);
  return <section className="pathway-section" aria-label="Pressure in the cancer pathway"><div className="pathway-nodes">{nodes.map((node,i)=><div className="pathway-slot" key={node.name}><div className={`pathway-node ${node.active?'under-pressure':''} stage-${node.stage}`}><span className="pathway-icon"><Icon name={node.icon} size={21}/></span><span>{node.name}</span>{node.active&&<small>Under pressure</small>}</div>{i<2&&<span className="pathway-arrow"><Icon name="arrow" size={29}/></span>}</div>)}</div><div className={`pathway-drivers ${drivers.length===2?'two-drivers':''}`}>{drivers.length?drivers.map((d:Json)=><div key={d.key} className={`pathway-driver stage-${d.side}`}><strong>{driverName(d)}</strong><p><b>{number(d.trust_rate_pct)}%</b> {d.side==='diagnosis'?'diagnosed within 28 days':'treatment started within 31 days'} <span>vs {number(d.national_rate_pct)}% across England</span></p></div>):<p className="pathway-calm">No clear bottleneck in the available evidence.</p>}</div></section>;
}
export function HospitalPanel({trust,current,onClose,onPlan,onDetails}: {trust: Trust; current: Json | null; onClose:()=>void; onPlan:()=>void; onDetails:()=>void}) {
  const ref=useDialog(onClose); const forecast=current?.forecast || trust; const bottleneck=current?.bottleneck || {}; const history=(forecast.history || trust.history || []).filter((p:Json)=>typeof p.backlog==='number').slice(-39); const predictions=forecast.forecasts || trust.forecasts || [];
  const latest=history.at(-1); const color=directionColor(trust.direction); const firstPrediction=predictions[0];
  const series:ChartSeries[]=[{name:'Recorded',color:C.ink,points:history.map((p:Json)=>({x:timestamp(p.week_ending),y:p.backlog}))}];
  if(latest&&firstPrediction) series.push({name:'Unobserved gap',color:C.slate,dashed:true,points:[{x:timestamp(latest.week_ending),y:latest.backlog},{x:timestamp(firstPrediction.target_date),y:firstPrediction.point_forecast}]});
  series.push({name:'Forecast',color,dashed:true,band:true,points:predictions.map((p:Json)=>({x:timestamp(p.target_date),y:p.point_forecast,low:p.lower_80,high:p.upper_80}))});
  return <div className="hospital-layer"><button className="hospital-scrim" aria-label="Back to the map" onClick={onClose}/><div ref={ref} data-dialog className="hospital-panel" role="dialog" aria-modal="true" aria-labelledby="hospital-title">
    <div className="hospital-head"><div><p className="panel-context">Hospital outlook</p><h2 id="hospital-title">{title(trust.name)}</h2></div><button className="icon-button" aria-label="Close hospital" onClick={onClose}><Icon name="close"/></button></div>
    <p className="hospital-verdict">{current ? verdict(forecast,bottleneck,trust.direction) : 'Opening the recent pathway evidence…'}</p>
    <section className="hospital-chart"><div className="chart-heading"><h3>People waiting over 62 days</h3><Legend items={[{label:'Recorded',color:C.ink},{label:'Forecast',color,dashed:true}]}/></div><LineChart key={trust.org_code} series={series} label={`Recorded backlog and forecast for ${title(trust.name)}`} height={210} tickFormat={x=>day(new Date(x).toISOString(),true)} ticks={history.length?[timestamp(history[0].week_ending),timestamp(latest.week_ending),...(predictions.length?[timestamp(predictions.at(-1).target_date)]:[])]:undefined} reveal gap={latest&&firstPrediction?{from:timestamp(latest.week_ending),to:timestamp(firstPrediction.target_date),label:'No newer observation'}:undefined}/><div className="forecast-numbers">{[4,8,12].map(h=>{const p=predictions.find((p:Json)=>p.horizon_weeks===h);return <div key={h}><span>In {h} weeks</span><strong><AnimatedNumber value={p?.point_forecast}/></strong><small>{p?<><span>{day(p.target_date,true)}</span><span>Range {number(p.lower_80)}–{number(p.upper_80)}</span></>:'Forecast unavailable'}</small></div>;})}</div><p className="chart-caption">Forecast made {day(forecast.issue_date || predictions[0]?.issue_date)}. Shading shows the 80% range.</p></section>
    <Pathway bottleneck={bottleneck}/>
    <div className="hospital-actions"><button className="primary-button" onClick={onPlan} disabled={!current}>Test a recovery plan <Icon name="arrow"/></button><button className="quiet-link" onClick={onDetails} disabled={!current}>Details <Icon name="chevron" size={17}/></button></div>
  </div></div>;
}
export function HospitalDetails({current,trust,onClose}: {current:Json;trust:Trust;onClose:()=>void}) {
  const b=current.bottleneck || {};
  const latest=current.history?.latest;
  const max=Math.max(1,...(latest?.bands || []).map((x:Json)=>x.count ?? 0));
  const forecast=current.forecast || trust;
  const history=(forecast.history || trust.history || []).filter((p:Json)=>typeof p.backlog==='number'&&Number.isFinite(p.backlog)).slice(-39);
  const predictions=(forecast.forecasts || trust.forecasts || []).filter((p:Json)=>[4,8,12].includes(p.horizon_weeks)&&typeof p.point_forecast==='number'&&Number.isFinite(p.point_forecast)).sort((a:Json,b:Json)=>a.horizon_weeks-b.horizon_weeks);
  const lastRecorded=history.at(-1),firstPrediction=predictions[0];
  const series:ChartSeries[]=[{name:'Recorded',color:C.ink,points:history.map((p:Json)=>({x:timestamp(p.week_ending),y:p.backlog}))}];
  if(lastRecorded&&firstPrediction)series.push({name:'Reporting gap',color:C.slate,dashed:true,points:[{x:timestamp(lastRecorded.week_ending),y:lastRecorded.backlog},{x:timestamp(firstPrediction.target_date),y:firstPrediction.point_forecast}]});
  if(predictions.length)series.push({name:'Forecast',color:C.cyan,dashed:true,band:true,points:predictions.map((p:Json)=>({x:timestamp(p.target_date),y:p.point_forecast,low:p.lower_80,high:p.upper_80}))});
  return <Drawer heading="Hospital details" onClose={onClose}>
    <p className="drawer-intro">{title(trust.name)}</p>
    <section>
      <div className="chart-heading"><h3>Waiting-list history and forecast</h3><Legend items={[{label:'Recorded',color:C.ink},...(predictions.length?[{label:'Forecast',color:C.cyan,dashed:true}]:[])]}/></div>
      <p>People waiting over 62 days. The latest 39 reported weeks{predictions.length?', followed by the 4-, 8- and 12-week estimates.':'.'}</p>
      {history.length||predictions.length?<LineChart key={trust.org_code} series={series} label={`Recorded backlog and 4-, 8- and 12-week forecasts for ${title(trust.name)}`} height={270} tickFormat={x=>day(new Date(x).toISOString(),true)} ticks={history.length?[timestamp(history[0].week_ending),timestamp(lastRecorded.week_ending),...(predictions.length?[timestamp(predictions.at(-1).target_date)]:[])]:undefined} reveal gap={lastRecorded&&firstPrediction?{from:timestamp(lastRecorded.week_ending),to:timestamp(firstPrediction.target_date),label:'No newer observation'}:undefined}/>:<Notice>No suitable history or forecast is available.</Notice>}
      <p className="chart-caption">{predictions.length?<>Forecast issued {day(forecast.issue_date || firstPrediction?.issue_date)}. Shading shows the 80% forecast range.</>:'A forecast is not available for this hospital.'} The dashed bridge across the reporting gap only connects displayed points; it is not an observed or predicted weekly path.</p>
    </section>
    <section>
      <h3>How strong is the pathway evidence?</h3>
      <p>“Diagnosed within 28 days” includes a cancer diagnosis or cancer being ruled out within that time. The 31-day treatment clock starts at the decision to treat.</p>
      <p><b>{b.confidence==='high'?'Strong':b.confidence==='medium'?'Moderate':'Limited'}</b> evidence from recent published data. This is a screening signal, not proof of the cause of a delay. Clinical review is still pending.</p>
      {[b.diagnosis_driver,b.treatment_driver].filter(Boolean).map((d:Json)=><div className="detail-fact" key={d.key}><b>{driverName(d)}</b><span><b>{number(d.trust_rate_pct,1)}%</b> {d.side==='diagnosis'?'diagnosed within 28 days':'started treatment within 31 days'} vs <b>{number(d.national_rate_pct,1)}%</b> across England</span><span>{number(d.denominator)} completed pathways over {d.months_used} months</span><span>{d.positive_months} months worse than the England comparison</span></div>)}
      <p>Small samples are reduced in weight. A driver needs enough patients and at least two adverse months.</p>
    </section>
    <section>
      <h3>How long completed treatment pathways took</h3>
      <p>{latest?day(latest.period):'No suitable record is available.'} These people have already started treatment. This is not the age of the current waiting list.</p>
      {latest?.bands_available===false?<Notice>Some wait bands are missing or suppressed. We cannot show a complete distribution.</Notice>:latest&&<div className="wait-bands">{latest.bands.map((band:Json)=><div key={band.label}><span>{band.label}</span><i><b style={{width:`${(band.count??0)/max*100}%`}}/></i><strong>{number(band.count)}</strong></div>)}</div>}
    </section>
    <section>
      <h3>Routine diagnostic queues</h3>
      <p>These queues also include people without suspected cancer. They support the picture; they do not set the main bottleneck.</p>
      <div className="table-scroll"><table><thead><tr><th>Test</th><th>Waiting 6+ weeks</th><th>England</th><th>Matching cancer signal</th></tr></thead><tbody>{(b.indicators||[]).filter((d:Json)=>d.role==='context').map((d:Json)=><tr key={d.key}><td>{d.name}</td><td>{number(d.trust_rate_pct)}%</td><td>{number(d.national_rate_pct)}%</td><td>{d.corroboration==='corroborated'?'Also adverse':'Not adverse or unavailable'}</td></tr>)}</tbody></table></div>
    </section>
    <section>
      <h3>How to read the forecast</h3>
      <p>Targets are 4, 8 and 12 weeks after the forecast date, not the older observation date.</p>
      <p>Map arrows compare the rounded estimated count with the rounded latest reported count: coral for an estimated rise, mint for an estimated fall, and yellow when unchanged. A rise can be as small as one person; colour does not measure severity or confidence. The 80% range may include either direction. Missing forecasts have a slate question mark.</p>
      <p>Past counts follow current merged hospital organisations. Latest revised data use approximate first-release dates; original historical versions have not been verified.</p>
    </section>
  </Drawer>;
}
export function AssumptionsDrawer({decision,onClose}: {decision:Json;onClose:()=>void}) {
  const grid=decision.planning_grid;
  const legacy=decision.absolute_simulator_evidence||{};
  const assumptions={...Object.fromEntries(Object.entries(decision.assumptions||{}).filter(([key])=>key!=='scenario_grid')),...(grid?.assumptions||{})};
  const absolutePlans:Json[]=legacy.scenario_comparison||[];
  const reasons:string[]=decision.eligibility?.reasons||grid?.eligibility?.reasons||[];
  return <Drawer heading="How this works" onClose={onClose}>
    <p className="drawer-intro">The forecast sets the waiting-list level. The queue model estimates what a change could do.</p>
    <section><h3>What does “do nothing” mean?</h3>
      <p>Without extra capacity or pressures, the path is the statistical forecast. Weekly values connect the latest report with the 4-, 8- and 12-week forecast points. The comparison starts on the forecast issue date and ends 12 weeks later.</p>
      <p>Selected pressures add their modelled change to that forecast. “No extra capacity” and “Your plan” both include the same selected pressures.</p>
    </section>
    <section><h3>What changes when you add capacity?</h3>
      <p>We run the queue model twice with the same capacity draws and day-to-day variation: once with extra capacity and once without it. We add the difference to the forecast, keeping the result at or above zero.</p>
      <p>The selected stage can complete more work each day, from week four until week twelve. The people-per-1% figure measures the paired benefit between 0% and 5% extra capacity at week twelve.</p>
      <p>{decision.treatment_label_caveat||'The model changes the whole treatment stage. It cannot isolate the staffing effect of one treatment.'}</p>
    </section>
    <section><h3>The pressures are assumptions</h3>
      <ul><li>A five-day doctors’ strike reduces both stages to 95.2% of their usual capacity.</li><li>Winter pressure reduces capacity by 10% for six weeks.</li><li>A referral surge increases arrivals by 20% for four weeks.</li></ul>
      <p>All pressures start in week four. Strike and winter capacity reductions multiply when selected together. Their effects are calculated from paired queue-model runs and added to the forecast. These are stress tests, not measured effects of a future event.</p>
    </section>
    <section><h3>What does the range include?</h3>
      <p>The displayed 80% plan range uses the 10th–90th percentiles of the paired modelled change, added to the central forecast. Capacity parameters, arrivals and daily service vary together across paired runs. We calculate each run’s difference before taking percentiles.</p>
      <p>The forecast level is held fixed. Its own uncertainty is not included, so this is not a full prediction interval. The assumed age mix, queue structure, conversion to treatment and service order also remain fixed.</p>
    </section>
    <section><h3>When is a plan held back?</h3>
      <p>A plan is withheld if the queue model fails its history-fit check, its optimisation fails, or the data do not distinguish the two stage capacities well enough. A complete forecast is also required to anchor a plan.</p>
      <p>A difference between the old absolute queue-model level and the forecast no longer blocks a plan. The forecast now supplies the level by construction.</p>
      {reasons.length>0&&<Notice warning>{reasons.join(' ')}</Notice>}
      {decision.prior_conflict&&<Notice warning>The fitted capacity pattern and the pathway evidence disagree for this hospital. Treat the capacity comparison with extra caution.</Notice>}
    </section>
    <section><h3>What is known, and what is assumed?</h3>
      <p>The total number waiting over 62 days is observed. The split between diagnosis and treatment uses a weak prior from pathway evidence. Referral age is tracked in days throughout both stages. Extra capacity represents an effective service budget, not a measured staffing change.</p>
    </section>
    {absolutePlans.length>0&&<details className="raw-assumptions"><summary>Old absolute queue-model outputs</summary>
      <p>These six-month model levels are retained for inspection only. They do not set the level or the range of the 12-week recovery plan.</p>
      <div className="table-scroll"><table><thead><tr><th>Original scenario</th><th>Day 182</th><th>10–90% model range</th></tr></thead><tbody>{absolutePlans.map(plan=><tr key={plan.key}><th>{plan.name}</th><td>{number(plan.final_backlog?.median,1)}</td><td>{number(plan.final_backlog?.lower_80,1)}–{number(plan.final_backlog?.upper_80,1)}</td></tr>)}</tbody></table></div>
      <p>Absolute outputs vary process noise and capacity parameters under the original model. They are assumption-led sensitivity results, not validated forecasts.</p>
    </details>}
    <details className="raw-assumptions"><summary>Parameter values and sources</summary>{Object.entries(assumptions).map(([key,value])=>{const item=value as Json;return <div className="detail-fact" key={key}><b>{key.replaceAll('_',' ')}</b><span>{typeof item?.value==='object'?JSON.stringify(item.value):String(item?.value??(typeof value==='object'?JSON.stringify(value):value))}</span>{item?.unit&&<small>{item.unit}</small>}{item?.source&&<small>Source: {item.source}</small>}{item?.note&&<p>{item.note}</p>}</div>;})}</details>
  </Drawer>;
}
