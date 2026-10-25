import { useCallback, useEffect, useRef, useState } from 'react';
import { get, Icon, title, useReducedMotion, type Json, type Trust } from './ui';
import Landing from './Landing';
import MapView from './MapView';
import HospitalForecast from './HospitalForecast';
import { AssumptionsDrawer, HospitalDetails } from './Hospital';
import PlanView from './PlanView';
import Evidence, { DemoDetails, MapDetails } from './Evidence';

type View='home'|'map'|'hospital'|'plan'|'evidence';
type OpenDrawer='map'|'hospital'|'assumptions'|'demo'|null;
const validViews=['home','map','hospital','plan','evidence'];
const demoUrl='https://www.youtube.com/watch?v=L5Cd3Bld5f8';
export default function App() {
  const initial=useRef(new URLSearchParams(window.location.search));
  const requested=initial.current.get('view') || 'home';
  const initialView=validViews.includes(requested)?requested as View:'home';
  const [view,setView]=useState<View>(initialView);
  const [activeSection,setActiveSection]=useState<View>(initialView);
  const [code,setCode]=useState(initial.current.get('trust') || 'RTH');
  const [hasSelection,setHasSelection]=useState(['hospital','plan'].includes(initialView));
  const [showPlan,setShowPlan]=useState(initialView==='plan');
  const [scrollRequest,setScrollRequest]=useState<{target:View;serial:number;instant?:boolean}|null>(initialView==='home'?null:{target:initialView,serial:0,instant:true});
  const [map,setMap]=useState<Json|null>(null);
  const [boundary,setBoundary]=useState<Json|null>(null);
  const [context,setContext]=useState<Json|null>(null);
  const [roads,setRoads]=useState<Json|null>(null);
  const [backtest,setBacktest]=useState<Json>({});
  const [national,setNational]=useState<Json>({});
  const [current,setCurrent]=useState<Json|null>(null);
  const [drawer,setDrawer]=useState<OpenDrawer>(null);
  const [error,setError]=useState('');
  const [trustError,setTrustError]=useState('');
  const [retry,setRetry]=useState(0);
  const cache=useRef(new Map<string,Json>());
  const pending=useRef(new Map<string,Promise<Json>>());
  const reduced=useReducedMotion();
  const prefetch=useCallback((trustCode:string)=>{
    if(cache.current.has(trustCode))return Promise.resolve(cache.current.get(trustCode)!);
    if(pending.current.has(trustCode))return pending.current.get(trustCode)!;
    const task=Promise.all(['forecast','bottleneck','history','decision'].map(kind=>get(`/api/trust/${encodeURIComponent(trustCode)}/${kind}`))).then(([forecast,bottleneck,history,decision])=>{const result={forecast,bottleneck,history,decision};cache.current.set(trustCode,result);pending.current.delete(trustCode);return result;}).catch(e=>{pending.current.delete(trustCode);throw e;});
    pending.current.set(trustCode,task);return task;
  },[]);
  useEffect(()=>{
    const controller=new AbortController();setError('');
    Promise.all([get('/api/map',controller.signal),get('/api/backtest',controller.signal),get('/api/national',controller.signal),get('/assets/england-boundary.geojson',controller.signal)]).then(([m,b,n,g])=>{setMap(m);setBacktest(b);setNational(n);setBoundary(g);}).catch(e=>{if(e.name!=='AbortError')setError(e.message);});
    get('/assets/uk-context.geojson',controller.signal).then(setContext).catch(()=>{});
    get('/assets/uk-roads.geojson',controller.signal).then(setRoads).catch(()=>{});
    return()=>controller.abort();
  },[retry]);
  useEffect(()=>{let active=true;setTrustError('');setCurrent(cache.current.get(code)||null);prefetch(code).then(value=>{if(active)setCurrent(value);}).catch(e=>{if(active)setTrustError(e.message);});return()=>{active=false;};},[code,prefetch,retry]);
  useEffect(()=>{
    const params=new URLSearchParams(window.location.search);
    if(view==='home'){params.delete('view');params.delete('trust');}else{params.set('view',view);if(hasSelection)params.set('trust',code);else params.delete('trust');}
    window.history.replaceState(null,'',`${window.location.pathname}${params.size?`?${params}`:''}`);
  },[view,code,hasSelection]);
  useEffect(()=>{
    if(!scrollRequest)return;
    const element=document.getElementById(scrollRequest.target==='home'?'hero':scrollRequest.target);
    if(!element)return;
    const frame=requestAnimationFrame(()=>{
      element.scrollIntoView({behavior:reduced||scrollRequest.instant?'instant':'smooth',block:'start'});
      element.focus({preventScroll:true});
      setScrollRequest(null);
    });
    return()=>cancelAnimationFrame(frame);
  },[scrollRequest,map,hasSelection,showPlan,reduced,view]);
  const navigate=(next:View)=>{
    setView(next);setDrawer(null);
    if(next==='plan'){setHasSelection(true);setShowPlan(true);}
    setScrollRequest(previous=>({target:next,serial:(previous?.serial||0)+1}));
  };
  useEffect(()=>{
    if(map?.trusts?.length && !map.trusts.some((trust:Trust)=>trust.org_code===code)) {
      setCode(map.trusts.some((trust:Trust)=>trust.org_code==='RTH')?'RTH':map.trusts[0].org_code);
      setHasSelection(false);setShowPlan(false);setView('map');
      setScrollRequest({target:'map',serial:Date.now(),instant:true});
    }
  },[map,code]);
  const select=(next:string)=>{setCode(next);setHasSelection(true);setShowPlan(false);navigate('hospital');};
  const trusts:Trust[]=map?.trusts || [];
  const selected=trusts.find(t=>t.org_code===code);
  const selectedCurrent=current?.forecast?.org_code===code?current:null;
  const isEvidence=view==='evidence';
  useEffect(()=>{
    if(isEvidence){setActiveSection('evidence');return;}
    let frame=0;
    const update=()=>{
      if(frame)return;
      frame=requestAnimationFrame(()=>{
        frame=0;
        const offset=(document.querySelector('.journey-header')?.getBoundingClientRect().height||72)+40;
        const ids:View[]=['home','map',...(hasSelection?['hospital'] as View[]:[]),...(showPlan?['plan'] as View[]:[])];
        let active:View='home';
        for(const id of ids){const node=document.getElementById(id==='home'?'hero':id);if(node && node.getBoundingClientRect().top<=offset)active=id;}
        setActiveSection(active);
      });
    };
    update();window.addEventListener('scroll',update,{passive:true});
    return()=>{cancelAnimationFrame(frame);window.removeEventListener('scroll',update);};
  },[isEvidence,hasSelection,showPlan,map]);

  const openPlan=()=>navigate('plan');
  const retryData=()=>{setError('');cache.current.clear();setRetry(r=>r+1);};
  return <div className={`clock-journey ${isEvidence?'showing-evidence':''}`}><a className="skip-link" href="#map">Skip to the hospital map</a>
    {!isEvidence&&<Landing total={national.latest?.total??map?.national?.latest?.total??null} reportedDate={national.latest?.week_ending??map?.latest_observed_week??null} demoUrl={demoUrl} onExplore={()=>navigate('map')} onEvidence={()=>navigate('evidence')} onAbout={()=>setDrawer('demo')}/>}
    <div className="journey-tool">
      <header className="app-header atlas-header journey-header"><button className="brand" onClick={()=>navigate('home')} aria-label="Cancer Clock home"><span className="brand-mark"><Icon name="clock" size={29}/></span><span>Cancer Clock</span></button><nav className="atlas-nav" aria-label="Main navigation"><button className={activeSection==='map'?'active':''} onClick={()=>navigate('map')}>Find a hospital</button>{hasSelection&&<button className={activeSection==='hospital'?'active':''} onClick={()=>navigate('hospital')}>Hospital outlook</button>}{hasSelection&&<button className={activeSection==='plan'?'active':''} onClick={openPlan}>Recovery plan</button>}<button className={isEvidence?'active':''} onClick={()=>navigate('evidence')}>Evidence</button></nav><a className="journey-about quiet-link" href={demoUrl} target="_blank" rel="noopener noreferrer" aria-label="Play demo on YouTube (opens in a new tab)">Play demo <Icon name="play" size={16}/></a></header>
      <main id="main">
        {isEvidence?<div id="evidence" tabIndex={-1} className="journey-section">{error?<section className="app-error panel" role="alert"><h2>We couldn’t open the evidence.</h2><p>{error}</p><button className="primary-button" onClick={retryData}>Try again</button></section>:!map?<section className="opening-screen" role="status"><h2>Opening the evidence…</h2></section>:<Evidence data={backtest} national={national} onBack={()=>navigate('map')}/>}</div>:<>
          <div id="map" tabIndex={-1} className="journey-section journey-map-section">
            {error?<section className="app-error panel" role="alert"><Icon name="info" size={30}/><h2>We couldn’t open the published data.</h2><p>{error}</p><button className="primary-button" onClick={retryData}>Try again <Icon name="arrow"/></button></section>:!map?<section className="opening-screen" role="status"><span className="opening-clock"><Icon name="clock" size={40}/></span><h2>Find your hospital.</h2><p>Opening the published hospital data…</p></section>:<MapView data={map} boundary={boundary} context={context} roads={roads} selected={hasSelection?selected:undefined} current={selectedCurrent} trustError={trustError} onSelect={select} onDetails={()=>setDrawer('map')} onHospital={()=>navigate('hospital')} onPlan={openPlan} onPrefetch={next=>{void prefetch(next).catch(()=>{});}}/>}
          </div>
          {hasSelection&&selected&&<div id="hospital" tabIndex={-1} className="journey-section journey-hospital-section"><HospitalForecast key={code} trust={selected} current={selectedCurrent} trustError={trustError} onChooseHospital={()=>navigate('map')} onPlan={openPlan} onDetails={()=>setDrawer('hospital')}/>{trustError&&<button className="primary-button journey-retry" onClick={()=>setRetry(r=>r+1)}>Retry hospital data</button>}</div>}
          {showPlan&&selected&&<div id="plan" tabIndex={-1} className="journey-section journey-plan-section">{selectedCurrent?<PlanView key={code} trust={selected} decision={selectedCurrent.decision} onBack={()=>navigate('hospital')} onHow={()=>setDrawer('assumptions')} onExamplePlan={()=>{setCode('RTH');setHasSelection(true);navigate('plan');}}/>:<section className="opening-screen" role="status"><h2>{title(selected.name)}</h2><p>{trustError||'Opening the precomputed plans…'}</p>{trustError&&<button className="primary-button" onClick={()=>setRetry(r=>r+1)}>Try again</button>}</section>}</div>}
        </>}
      </main>
      <footer className="app-footer atlas-footer journey-footer"><span>England data only <span aria-hidden="true">·</span> Independent planning tool</span><button onClick={()=>setDrawer('map')}>About the data <Icon name="info" size={14}/></button></footer>
    </div>
    {drawer==='demo'&&<DemoDetails onClose={()=>setDrawer(null)}/>}
    {drawer==='map'&&map&&<MapDetails data={map} onClose={()=>setDrawer(null)}/>}
    {drawer==='hospital'&&selectedCurrent&&selected&&<HospitalDetails current={selectedCurrent} trust={selected} onClose={()=>setDrawer(null)}/>}
    {drawer==='assumptions'&&selectedCurrent&&<AssumptionsDrawer decision={selectedCurrent.decision} onClose={()=>setDrawer(null)}/>}
  </div>;
}
