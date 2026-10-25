import { type CSSProperties } from 'react';
import { day, Icon } from './ui';
import { mapStatuses, type MapStatus } from './mapModel';

type Props = {
  horizon: number;
  playing: boolean;
  onHorizon: (horizon:number) => void;
  onPlay: () => void;
  issueDate?: string;
  latestObserved?: string | null;
  onDetails: () => void;
};

export default function ForecastControl({horizon, playing, onHorizon, onPlay, issueDate, latestObserved, onDetails}: Props) {
  const horizons = [0,4,8,12];
  return <div className="outlook-dock">
    <div className={`forecast-control ${playing ? 'is-playing' : ''}`} aria-label="Look ahead at hospital waiting lists">
      <button className="forecast-preview" onClick={onPlay} aria-label={playing ? 'Pause outlook preview' : 'Preview the outlook'} title={playing ? 'Pause preview' : 'Play through the reported count and each forecast'}><Icon name={playing ? 'pause' : 'play'} size={21}/></button>
      <div className="forecast-intro"><strong>Look ahead</strong><span>See how waiting lists could change.</span></div>
      <div className="forecast-choices" role="group" aria-label="Choose a forecast horizon" style={{'--horizon-index':horizons.indexOf(horizon)} as CSSProperties}>
        <div className="forecast-route" aria-hidden="true"><i/></div><span className="forecast-choice-focus" aria-hidden="true"/>
        {horizons.map(value=><button key={value} className={horizon === value ? 'active' : ''} onClick={()=>onHorizon(value)} aria-pressed={horizon === value}><span className="forecast-choice-dot"/><span>{value ? `+${value} weeks` : 'Latest reported'}</span></button>)}
      </div>
    </div>
    <div className="outlook-caption"><p>Weeks after the forecast on <b>{day(issueDate)}</b>. Latest report <b>{day(latestObserved || undefined, true)}</b>.</p><div className="outlook-legend" aria-label={horizon?"Estimated direction, not certainty":"Reported counts"}>{horizon ? (Object.keys(mapStatuses) as MapStatus[]).map(key=><span key={key}><b style={{color:mapStatuses[key].color}}>{mapStatuses[key].symbol}</b>{mapStatuses[key].label}</span>) : <span>Choose a future week to see direction.</span>}</div><button className="outlook-help" onClick={onDetails} aria-label="How to read the map and forecast"><Icon name="info" size={17}/></button></div>
  </div>;
}
