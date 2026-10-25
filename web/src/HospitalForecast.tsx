import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { AnimatedNumber, C, day, driverName, Icon, LineChart, number, timestamp, title, useAnimatedValues, type ChartSeries, type Json, type Trust } from './ui';
import { centralStatus, forecastAt, mapStatuses } from './mapModel';

type Props = {trust:Trust;current:Json|null;trustError?:string;onChooseHospital:()=>void;onPlan:()=>void;onDetails:()=>void};
/** History and the three published horizon estimates; no weekly forecast is invented. */
export default function HospitalForecast({trust,current,trustError='',onChooseHospital,onPlan,onDetails}:Props) {
  const [horizon,setHorizon]=useState(8),[inView,setInView]=useState(false);
  const section=useRef<HTMLElement>(null);
  useEffect(()=>{const node=section.current;if(!node)return;const observer=new IntersectionObserver(([entry])=>setInView(entry.isIntersecting),{threshold:.2});observer.observe(node);return()=>observer.disconnect();},[]);
  const prediction=forecastAt(trust,horizon),latest=trust.latest_backlog;
  const hasLatest=typeof latest==='number'&&Number.isFinite(latest)&&latest>=0;
  const estimate=prediction?.point_forecast,hasEstimate=typeof estimate==='number'&&Number.isFinite(estimate)&&estimate>=0;
  const direction=centralStatus(latest,estimate),status=mapStatuses[direction];
  const difference=hasLatest&&hasEstimate?Math.round(estimate)-Math.round(latest):null;
  const low=prediction?.lower_80,high=prediction?.upper_80;
  const hasRange=hasEstimate&&typeof low==='number'&&typeof high==='number'&&Number.isFinite(low)&&Number.isFinite(high);
  const source=current?.forecast||trust;
  const history:Json[]=(source.history||trust.history||[]).filter((point:Json)=>typeof point.backlog==='number'&&Number.isFinite(point.backlog)).slice(-39);
  const predictions:Json[]=(source.forecasts||trust.forecasts||[]).filter((point:Json)=>typeof point.point_forecast==='number'&&Number.isFinite(point.point_forecast));
  const lastObservation=history.at(-1),firstPrediction=predictions[0];
  const issueDate=prediction?.issue_date||source.issue_date||predictions[0]?.issue_date;
  const selectedDate=hasEstimate&&prediction?.target_date?timestamp(prediction.target_date):0;
  const animatedMarkerDate=useAnimatedValues([selectedDate])[0];
  const markerDate=firstPrediction?Math.max(timestamp(firstPrediction.target_date),Math.min(timestamp(predictions.at(-1)!.target_date),animatedMarkerDate)):selectedDate;
  const series:ChartSeries[]=[{name:'Reported',color:'#A8B5C7',points:history.map(point=>({x:timestamp(point.week_ending),y:point.backlog}))}];
  if(lastObservation&&firstPrediction)series.push({name:'Unobserved gap',color:'#647990',dashed:true,points:[{x:timestamp(lastObservation.week_ending),y:lastObservation.backlog},{x:timestamp(firstPrediction.target_date),y:firstPrediction.point_forecast}]});
  series.push({name:'Forecast',color:C.cyan,dashed:true,band:true,points:predictions.map(point=>({x:timestamp(point.target_date),y:point.point_forecast,low:point.lower_80,high:point.upper_80}))});
  if(hasEstimate&&prediction?.target_date)series.push({name:'Selected estimate',color:C.cyan,points:[{x:selectedDate,y:estimate}]});
  const ticks=[...(history.length?[timestamp(history[0].week_ending)]:[]),...(lastObservation?[timestamp(lastObservation.week_ending)]:[]),...(predictions.length?[timestamp(predictions.at(-1)!.target_date)]:[])];
  const diagnosis=current?.bottleneck?.diagnosis_driver,treatment=current?.bottleneck?.treatment_driver;
  const drivers=[diagnosis&&`Diagnosis: ${driverName(diagnosis)}`,treatment&&`Treatment: ${driverName(treatment)}`].filter(Boolean) as string[];
  const pressure=drivers.length?drivers.join('. '):current?'No clear pressure point in the available evidence.':trustError?'Pathway evidence unavailable.':'Opening the pathway evidence…';
  const decision=current?.decision,needsReview=decision&&(decision.status!=='ready'||decision.planning_grid?.status!=='ready');
  return <section ref={section} className={`hospital-forecast ${inView?'is-visible':''}`} aria-labelledby="hospital-forecast-title" style={{'--forecast-color':status.color} as CSSProperties}><div className="hf-inner">
    <header className="hf-header hf-reveal"><div><p className="hf-context">{title(trust.name)}</p><h2 id="hospital-forecast-title">What happens <em>next?</em></h2></div><button className="hf-choose" onClick={onChooseHospital}><Icon name="back" size={18}/>Choose another hospital</button></header>
    <div className="hf-story">
      <div className="hf-metric hf-reveal"><p className="hf-unit">People waiting <strong>over 62 days</strong></p>
        <div className="hf-horizons" role="group" aria-label="Hospital forecast horizon" style={{'--active-horizon':[4,8,12].indexOf(horizon)} as CSSProperties}><span aria-hidden="true"/>{[4,8,12].map(value=><button key={value} aria-pressed={horizon===value} className={horizon===value?'active':''} onClick={()=>setHorizon(value)}>{value} weeks</button>)}</div>
        <div className="hf-prediction" aria-live="polite" aria-atomic="true"><strong>{inView?<AnimatedNumber key={trust.org_code} from={hasLatest?latest:undefined} value={hasEstimate?estimate:null}/>:number(hasEstimate?estimate:null)}</strong><span>{hasEstimate&&prediction?.target_date?`Estimated for ${day(prediction.target_date)}`:'Forecast unavailable'}</span></div>
        <p className="hf-baseline">Last reported <strong>{number(latest)}</strong></p>
        <p className="hf-change" key={`${trust.org_code}-${horizon}`}><span aria-hidden="true">{hasEstimate?status.symbol:'?'}</span>{difference==null?'Not enough data for a forecast.':difference===0?'About the same number.':<>{number(Math.abs(difference))} {difference>0?'more':'fewer'} {Math.abs(difference)===1?'person':'people'} than last reported.</>}</p>
        {hasRange&&<p className="hf-range"><span>80% forecast range</span><strong>{number(low)}–{number(high)}</strong></p>}
      </div>
      <div className="hf-chart hf-reveal"><div className="hf-chart-key" aria-label="Chart key"><span><i className="hf-key-reported"/>Reported</span>{predictions.length>0&&<><span><i className="hf-key-forecast"/>Forecast</span><span><i className="hf-key-band"/>80% range</span></>}</div>
        <div className="hf-main-chart">{inView?<LineChart key={trust.org_code} series={series} label={`Recorded weekly waiting list and 4-, 8- and 12-week estimates for ${title(trust.name)}. Selected horizon: ${horizon} weeks.`} height={365} tickFormat={value=>day(new Date(value).toISOString(),true)} ticks={ticks} marker={hasEstimate?{x:markerDate,label:''}:undefined} gap={lastObservation&&firstPrediction?{from:timestamp(lastObservation.week_ending),to:timestamp(firstPrediction.target_date),label:'No newer report'}:undefined} reveal/>:<div className="hf-chart-placeholder" aria-hidden="true"/>}</div>
        <p className="hf-chart-note">{predictions.length?'The dashed bridge spans the reporting gap. Dots show the forecast estimates.':'Published waiting-list counts. A forecast is not available for this hospital.'}</p>
      </div>
    </div>
    <div className="hf-pressure hf-reveal"><p><span>Likely pressure point</span><strong>{pressure}</strong></p><button className="hf-details" onClick={onDetails} disabled={!current}>See evidence <Icon name="chevron" size={17}/></button></div>
    <footer className="hf-bottom hf-reveal"><p>Last report <strong>{day(trust.latest_observed_week||undefined)}</strong>.<br/>{issueDate?<>Forecast issued <strong>{day(issueDate)}</strong>; horizons start from this date.</>:'Forecast date unavailable.'}</p><div className="hf-plan"><button onClick={onPlan}><span>{needsReview||!decision?'View planning options':'Test a recovery plan'}</span><Icon name="arrow" size={23}/></button>{needsReview&&<span>A recovery plan is not available here yet.</span>}</div></footer>
  </div></section>;
}
