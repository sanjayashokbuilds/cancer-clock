import { useCallback, useEffect, useRef, useState } from 'react';
import { C, get, Icon, title, type Json, type Trust } from './ui';
import MapView from './MapView';
import { AssumptionsDrawer, HospitalDetails, HospitalPanel } from './Hospital';
import PlanView from './PlanView';
import Evidence, { MapDetails } from './Evidence';

type View='map'|'hospital'|'plan'|'evidence';
type OpenDrawer='map'|'hospital'|'assumptions'|null;
const validViews=['map','hospital','plan','evidence'];
export default function App() {
  const initial=useRef(new URLSearchParams(window.location.search));
  const initialView=initial.current.get('view') || 'map';
  const [view,setView]=useState<View>(validViews.includes(initialView)?initialView as View:'map');
  const [code,setCode]=useState(initial.current.get('trust') || 'RTH');
  const [map,setMap]=useState<Json|null>(null); const [boundary,setBoundary]=useState<Json|null>(null); const [backtest,setBacktest]=useState<Json>({}); const [national,setNational]=useState<Json>({});
  const [current,setCurrent]=useState<Json|null>(null);const [drawer,setDrawer]=useState<OpenDrawer>(null);const [error,setError]=useState('');const [retry,setRetry]=useState(0);
  const cache=useRef(new Map<string,Json>());const pending=useRef(new Map<string,Promise<Json>>());
  const prefetch=useCallback((trustCode:string)=>{
    if(cache.current.has(trustCode))return Promise.resolve(cache.current.get(trustCode)!);
    if(pending.current.has(trustCode))return pending.current.get(trustCode)!;
    const task=Promise.all(['forecast','bottleneck','history','decision'].map(kind=>get(`/api/trust/${encodeURIComponent(trustCode)}/${kind}`))).then(([forecast,bottleneck,history,decision])=>{const result={forecast,bottleneck,history,decision};cache.current.set(trustCode,result);pending.current.delete(trustCode);return result;}).catch(e=>{pending.current.delete(trustCode);throw e;});
    pending.current.set(trustCode,task);return task;
  },[]);
  useEffect(()=>{
    const controller=new AbortController();setError('');
    Promise.all([get('/api/map',controller.signal),get('/api/backtest',controller.signal),get('/api/national',controller.signal),get('/assets/england-boundary.geojson',controller.signal)]).then(([m,b,n,g])=>{setMap(m);setBacktest(b);setNational(n);setBoundary(g);}).catch(e=>{if(e.name!=='AbortError')setError(e.message);});
    return()=>controller.abort();
  },[retry]);
  useEffect(()=>{let active=true;setCurrent(cache.current.get(code)||null);prefetch(code).then(value=>{if(active){setCurrent(value);}}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[code,prefetch,retry]);
  useEffect(()=>{const params=new URLSearchParams(window.location.search);params.set('view',view);if(view==='hospital'||view==='plan')params.set('trust',code);else params.delete('trust');window.history.replaceState(null,'',`?${params}`);},[view,code]);
  const select=(next:string)=>{setCode(next);setView('hospital');setDrawer(null);};
  const showMap=()=>{setView('map');setDrawer(null);};
  const trusts:Trust[]=map?.trusts || [];
  const selected=trusts.find(t=>t.org_code===code);
  const selectedCurrent=current?.forecast?.org_code===code?current:null;
  const step=view==='map'?1:view==='hospital'?2:view==='plan'?3:0;
  return <><a className="skip-link" href="#main">Skip to content</a><header className="app-header"><button className="brand" onClick={showMap} aria-label="Cancer Clock home"><span className="brand-mark"><Icon name="clock" size={27}/></span><span>Cancer Clock</span></button><nav className="story-steps" aria-label="Planning steps">{[{n:1,label:'England',target:'map'},{n:2,label:'Hospital',target:'hospital'},{n:3,label:'Recovery plan',target:'plan'}].map((item,i)=><div className="story-step-wrap" key={item.n}><button className={`story-step ${step===item.n?'active':''} ${step>item.n?'done':''}`} onClick={()=>{setView(item.target as View);setDrawer(null);}} disabled={item.n>1&&!selected||item.n===3&&!selectedCurrent} aria-current={step===item.n?'step':undefined}><span>{step>item.n?<Icon name="check" size={13}/>:item.n}</span>{item.label}</button>{i<2&&<i className="step-connector"/>}</div>)}</nav><div className="header-right"><button className={`evidence-nav ${view==='evidence'?'active':''}`} onClick={()=>{setView('evidence');setDrawer(null);}}>Evidence</button><span className="independent-note">Independent planning tool</span></div></header>
    <main id="main" className={view==='map'||view==='hospital'?'main-map':'main-content'}>
      {error?<section className="app-error panel" role="alert"><Icon name="info" size={30}/><h1>We couldn’t open the published data.</h1><p>{error}</p><button className="primary-button" onClick={()=>{setError('');cache.current.clear();setRetry(r=>r+1);}}>Try again <Icon name="arrow"/></button></section>:!map?<section className="opening-screen" role="status"><span className="opening-clock"><Icon name="clock" size={40}/></span><h1>Time to make a difference.</h1><p>Opening the published hospital data…</p></section>:<>
        {(view==='map'||view==='hospital')&&<MapView data={map} boundary={boundary} onSelect={select} onDetails={()=>setDrawer('map')} onPrefetch={next=>{void prefetch(next).catch(()=>{});}}/>}
        {view==='hospital'&&selected&&<HospitalPanel trust={selected} current={selectedCurrent} onClose={showMap} onPlan={()=>setView('plan')} onDetails={()=>setDrawer('hospital')}/>}
        {view==='plan'&&selected&&(selectedCurrent?<PlanView key={code} trust={selected} decision={selectedCurrent!.decision} onBack={()=>setView('hospital')} onHow={()=>setDrawer('assumptions')}/>:<section className="opening-screen" role="status"><h1>{title(selected.name)}</h1><p>Opening the precomputed plans…</p></section>)}
        {view==='evidence'&&<Evidence data={backtest} national={national} onBack={showMap}/>}
      </>}
    </main>
    <footer className="app-footer"><span>Public NHS England data. Independent interpretation.</span><span>Hospital planning, not individual waiting-time predictions.</span></footer>
    {drawer==='map'&&map&&<MapDetails data={map} onClose={()=>setDrawer(null)}/>}
    {drawer==='hospital'&&selectedCurrent&&selected&&<HospitalDetails current={selectedCurrent!} trust={selected} onClose={()=>setDrawer(null)}/>}
    {drawer==='assumptions'&&selectedCurrent&&<AssumptionsDrawer decision={selectedCurrent!.decision} onClose={()=>setDrawer(null)}/>}
  </>;
}
