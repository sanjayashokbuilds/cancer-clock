import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { AnimatedNumber, C, day, directionColor, Icon, number, timestamp, title, useReducedMotion, type Json, type Trust } from './ui';

type Props = {data: Json; boundary: Json | null; onSelect: (code: string) => void; onDetails: () => void; onPrefetch: (code: string) => void};
const rad = Math.PI/180;
const mercator = ([lon,lat]: number[]) => [lon*rad, -Math.log(Math.tan(Math.PI/4+lat*rad/2))];
const geoBounds = [mercator([-6.43,55.83]),mercator([1.79,49.84])];
const scale = Math.min(660/(geoBounds[1][0]-geoBounds[0][0]), 600/(geoBounds[1][1]-geoBounds[0][1]));
const mapWidth = (geoBounds[1][0]-geoBounds[0][0])*scale;
const project = (coord: number[]) => {const [x,y] = mercator(coord);return [650+(660-mapWidth)/2+(x-geoBounds[0][0])*scale,22+(y-geoBounds[0][1])*scale];};
function outline(geo: Json) {
  const features = geo.type === 'FeatureCollection' ? geo.features : geo.type === 'Feature' ? [geo] : [{geometry:geo}];
  return features.flatMap((f:Json) => f.geometry.type==='MultiPolygon' ? f.geometry.coordinates : [f.geometry.coordinates]).map((poly:number[][][]) => poly.map(ring=>ring.map((p,i)=>{const [x,y]=project(p);return `${i?'L':'M'}${x.toFixed(2)},${y.toFixed(2)}`;}).join(' ')+' Z').join(' ')).join(' ');
}
const cities = [{name:'Newcastle',lon:-1.61,lat:54.98,dx:15,dy:-10},{name:'Leeds',lon:-1.55,lat:53.80,dx:20,dy:-3},{name:'Manchester',lon:-2.24,lat:53.48,dx:-90,dy:-9},{name:'Birmingham',lon:-1.90,lat:52.49,dx:15,dy:21},{name:'Oxford',lon:-1.26,lat:51.75,dx:-49,dy:18},{name:'Bristol',lon:-2.59,lat:51.45,dx:-50,dy:18},{name:'London',lon:-.12,lat:51.51,dx:18,dy:16},{name:'Plymouth',lon:-4.14,lat:50.38,dx:-30,dy:25}];
function displayValue(trust: Trust, date: string, observedEnd: string) {
  if (date <= observedEnd) {const point = trust.history.find((p:Json)=>p.week_ending===date);return {value:point?.backlog ?? null,kind:'observed',date};}
  // A held exact value is clearly labelled; no weekly forecasts are manufactured between the three model outputs.
  const points = trust.forecasts.filter((p:Json)=>p.target_date<=date);
  const point = points.at(-1);
  if (point) return {value:point.point_forecast,kind:point.target_date===date?'forecast':'held_forecast',date:point.target_date};
  return {value:trust.latest_backlog,kind:'unobserved',date:trust.latest_observed_week};
}
export default function MapView({data,boundary,onSelect,onDetails,onPrefetch}: Props) {
  const trusts:Trust[]=data.trusts || []; const weeks:string[]=data.weeks || []; const observedEnd=data.latest_observed_week || data.national?.latest?.week_ending;
  const latestIndex=Math.max(0,weeks.indexOf(observedEnd));
  const [week,setWeek]=useState(latestIndex); const [playing,setPlaying]=useState(false); const [query,setQuery]=useState(''); const [searchOpen,setSearchOpen]=useState(false); const [active,setActive]=useState(0); const [hover,setHover]=useState<string|null>(null); const reduced=useReducedMotion();
  const timer=useRef(0); const searchRef=useRef<HTMLDivElement>(null);
  useEffect(()=>{setWeek(latestIndex);setPlaying(false);},[latestIndex]);
  useEffect(()=>{if(!playing)return;let previous=0;const animate=(now:number)=>{if(now-previous>135){previous=now;setWeek(current=>{if(current>=weeks.length-1){setPlaying(false);return current;}return current+1;});}timer.current=requestAnimationFrame(animate);};timer.current=requestAnimationFrame(animate);return()=>cancelAnimationFrame(timer.current);},[playing,weeks.length]);
  useEffect(()=>{const close=(e:PointerEvent)=>{if(!searchRef.current?.contains(e.target as Node))setSearchOpen(false);};document.addEventListener('pointerdown',close);return()=>document.removeEventListener('pointerdown',close);},[]);
  const selectedDate=weeks[week] || observedEnd; const future=selectedDate>observedEnd;
  const firstTarget=trusts.flatMap(t=>t.forecasts).map((p:Json)=>p.target_date).sort()[0];
  const knownForecast=trusts.flatMap(t=>t.forecasts).some((p:Json)=>p.target_date===selectedDate);
  const visibleForecast=firstTarget && selectedDate>=firstTarget;
  const observedNational=(data.national?.history || []).find((p:Json)=>p.week_ending===selectedDate);
  const national=data.national?.latest;
  const nationalValue=observedNational?.total ?? national?.total;
  const path=useMemo(()=>boundary?outline(boundary):'', [boundary]);
  const matches=trusts.filter(t=>`${t.name} ${t.org_code}`.toLowerCase().includes(query.toLowerCase())).slice(0,7);
  const chosen=trusts.find(t=>t.org_code===hover);
  const choose=(code:string)=>{setPlaying(false);setSearchOpen(false);setQuery('');onSelect(code);};
  const currentTime=timestamp(new Date().toISOString().slice(0,10)); const todayPosition=weeks.length>1?Math.max(0,Math.min(100,(currentTime-timestamp(weeks[0]))/(timestamp(weeks.at(-1)!)-timestamp(weeks[0]))*100)):95;
  const observedPosition=weeks.length>1?latestIndex/(weeks.length-1)*100:90;
  const flag=visibleForecast ? (knownForecast?'Forecast':'Last forecast point held') : future?'No newer observation':'Recorded week';
  return <div className="map-screen">
    <div className="map-stage">
      <svg className="england-map" viewBox="0 0 1440 660" role="group" aria-label="Map of English hospital trusts. Select a hospital to explore its history and forecast.">
        <defs><pattern id="forecast-hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(35)"><line x1="0" y1="0" x2="0" y2="5" stroke="white" strokeWidth="1.5"/></pattern></defs>
        <path d={path} className="england-outline" fillRule="evenodd"/>
        <g className="city-labels">{cities.map(city=>{const[x,y]=project([city.lon,city.lat]);return <text key={city.name} x={x+city.dx} y={y+city.dy}>{city.name}</text>;})}</g>
        <g>{trusts.filter(t=>t.lat!=null&&t.lon!=null&&t.map_eligible!==false).sort((a,b)=>(b.latest_backlog??0)-(a.latest_backlog??0)).map(t=>{
          const[x,y]=project([t.lon!,t.lat!]); const p=displayValue(t,selectedDate,observedEnd); const missing=p.value==null; const radius=missing?3:Math.max(3,Math.sqrt(Math.max(0,p.value))*0.55); const color=directionColor(t.direction);const selected=hover===t.org_code;const isForecast=p.kind==='forecast'||p.kind==='held_forecast';
          return <g key={t.org_code} className="trust-dot" style={{'--dot-delay':`${Math.min(700,Math.floor((56-t.lat!)*1.15)*90)}ms`} as CSSProperties} role="button" tabIndex={0} aria-label={`${title(t.name)}, ${number(p.value)} people waiting over 62 days, ${t.direction || 'unclear'} forecast direction`} onClick={()=>choose(t.org_code)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose(t.org_code);}}} onMouseEnter={()=>{setHover(t.org_code);onPrefetch(t.org_code);}} onMouseLeave={()=>setHover(null)} onFocus={()=>{setHover(t.org_code);onPrefetch(t.org_code);}} onBlur={()=>setHover(null)}>
            <circle cx={x} cy={y} r={Math.max(12,radius+4)} fill="transparent"/>
            <circle className={`dot-disc ${isForecast?'forecast-dot':future?'unobserved-dot':''}`} cx={x} cy={y} r={radius} fill={missing?'white':color} stroke={selected?C.ink:isForecast?color:'white'} strokeWidth={selected?2.5:isForecast?1.3:1.1} strokeDasharray={isForecast?'2 2':undefined} opacity={future ? .45 : .85}/>
            {isForecast&&!missing&&<circle cx={x} cy={y} r={radius} fill="url(#forecast-hatch)" pointerEvents="none"/>}
            {selected&&<circle className="dot-focus-ring" cx={x} cy={y} r={radius+5} fill="none" stroke={C.ink} strokeWidth="1"/>}
          </g>;
        })}</g>
        {chosen&&chosen.lon!=null&&chosen.lat!=null&&(()=>{const[x,y]=project([chosen.lon,chosen.lat]);const p=displayValue(chosen,selectedDate,observedEnd);const px=x>1100?x-300:x+20;const py=Math.min(565,Math.max(55,y-40));return <g className="map-tooltip" transform={`translate(${px},${py})`} pointerEvents="none"><rect width="284" height="91" rx="10"/><text x="16" y="26" className="tooltip-title">{title(chosen.name).length>32?title(chosen.name).slice(0,30)+'…':title(chosen.name)}</text><text x="16" y="53">{number(p.value)} people waiting over 62 days</text><text x="16" y="75" className="tooltip-date">{p.kind==='observed'?'Recorded':p.kind==='unobserved'?'Last recorded':'Forecast for'} {day(p.date,true)}</text></g>;})()}
      </svg>
      <div className="map-intro">
        <div className="scope-label">Across England</div>
        <h1><AnimatedNumber value={nationalValue}/><span>people waiting over 62 days<br className="desktop-break"/> for cancer treatment</span></h1>
        <p className="observed-date">{future?'Latest recorded week':'Week ending'} {day(observedNational?.week_ending || national?.week_ending)}</p>
        <div className="hero-rule"/>
        <p className="target-line">The 62-day target has not been met since December 2015.</p>
        <button className="quiet-link map-detail-link" onClick={onDetails}>About these numbers <Icon name="chevron" size={16}/></button>
        <div className="map-legend"><span className="legend-title">12-week forecast direction</span><span><i style={{background:C.teal}}/>Improving</span><span><i style={{background:C.orange}}/>Worsening</span><span><i style={{background:C.slate}}/>Unclear</span></div>
        <p className="dot-explanation"><span className="size-key"><i/><i/><i/></span>Larger dots mean more people waiting.</p>
      </div>
      <div className="map-search" ref={searchRef}>
        <label className="search-field"><Icon name="search"/><input placeholder="Find a hospital" aria-label="Find a hospital" role="combobox" aria-expanded={searchOpen} aria-controls="hospital-results" aria-autocomplete="list" aria-activedescendant={searchOpen&&matches[active]?`result-${matches[active].org_code}`:undefined} value={query} onFocus={()=>setSearchOpen(true)} onChange={e=>{setQuery(e.target.value);setActive(0);setSearchOpen(true);}} onKeyDown={e=>{if(e.key==='ArrowDown'){e.preventDefault();setActive(a=>Math.min(matches.length-1,a+1));setSearchOpen(true);}if(e.key==='ArrowUp'){e.preventDefault();setActive(a=>Math.max(0,a-1));}if(e.key==='Enter'&&searchOpen&&matches[active])choose(matches[active].org_code);if(e.key==='Escape')setSearchOpen(false);}}/>{query&&<button className="clear-search" onClick={()=>{setQuery('');setActive(0);}} aria-label="Clear search"><Icon name="close" size={17}/></button>}</label>
        {searchOpen&&<div className="search-results" id="hospital-results" role="listbox">{matches.length?matches.map((t,i)=><button key={t.org_code} id={`result-${t.org_code}`} role="option" aria-selected={i===active} className={i===active?'active':''} onMouseEnter={()=>{setActive(i);onPrefetch(t.org_code);}} onMouseDown={e=>e.preventDefault()} onClick={()=>choose(t.org_code)}><span>{title(t.name)}</span><Icon name="arrow" size={17}/></button>):<p>No hospitals match “{query}”.</p>}</div>}
      </div>
      <div className={`map-time-tag ${future?'future-tag':''}`}><span className="time-tag-dot"/>{flag}<strong>{day(selectedDate)}</strong></div>
      {!path&&<p className="map-asset-notice">Loading the England boundary…</p>}
      <div className="map-instruction"><Icon name="person" size={18}/><span>Select a hospital to see what could change.</span></div>
    </div>
    <div className="time-scrubber">
      <button className={`play-button ${playing?'playing':''}`} onClick={()=>{if(playing)setPlaying(false);else{if(week>=latestIndex)setWeek(0);setPlaying(true);}}} aria-label={playing?'Pause timeline':'Play history and forecast'}><Icon name={playing?'pause':'play'} size={21}/></button>
      <div className="scrubber-content"><div className="scrubber-heading"><strong>{day(selectedDate)}</strong><span>{future?(visibleForecast?'Forecasts at 4, 8 and 12 weeks':'Waiting for newer published data'):'Recorded history'}{playing&&reduced?' — automatic playback':''}</span><button className="quiet-link" onClick={()=>{setPlaying(false);setWeek(latestIndex);}}>Latest recorded week</button></div><div className="slider-track-wrap"><div className="timeline-phases"><i style={{width:`${observedPosition}%`}}/><span style={{left:`${observedPosition}%`,width:`${100-observedPosition}%`}}/></div><input type="range" aria-label="Week shown on the map" min="0" max={Math.max(0,weeks.length-1)} step="1" value={week} onChange={e=>{setPlaying(false);setWeek(Number(e.target.value));}} aria-valuetext={`${day(selectedDate)}, ${flag}`} className="time-slider"/><div className="today-marker" style={{left:`${todayPosition}%`}}><i/><span>Today</span></div></div><div className="timeline-labels">{[2023,2024,2025,2026].map(year=><span key={year} style={{left:`${weeks.length>1?Math.max(0,(timestamp(`${year}-04-09`)-timestamp(weeks[0]))/(timestamp(weeks.at(-1)!)-timestamp(weeks[0]))*100):0}%`}}>Apr {year}</span>)}<span style={{right:0}}>+12 weeks</span></div></div>
    </div>
  </div>;
}
