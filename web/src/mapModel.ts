import type { Json, Trust } from './ui';

export type MapStatus = 'growing' | 'stable' | 'falling' | 'unclear';
export const mapStatuses = {
  growing:{label:'Estimated rise',symbol:'↑',color:'#FF7B78'},
  stable:{label:'Unchanged',symbol:'→',color:'#F4C66A'},
  falling:{label:'Estimated fall',symbol:'↓',color:'#75D8B1'},
  unclear:{label:'No forecast',symbol:'?',color:'#94A3B8'},
};
/** Direction of the displayed whole-person estimates, not confidence or risk. */
export function centralStatus(latest:unknown, forecast:unknown):MapStatus {
  if(typeof latest!=='number'||!Number.isFinite(latest)||typeof forecast!=='number'||!Number.isFinite(forecast)||latest<0||forecast<0)return 'unclear';
  const change=Math.round(forecast)-Math.round(latest);
  return change>0?'growing':change<0?'falling':'stable';
}
export function forecastAt(trust:Trust|undefined,horizon:number):Json|undefined {return trust?.forecasts?.find((point:Json)=>point.horizon_weeks===horizon);}
export function searchTrusts(trusts:Trust[],query:string):Trust[] {
  const term=query.trim().toLowerCase();
  const rank=(trust:Trust)=>trust.org_code.toLowerCase()===term?0:trust.name.toLowerCase().startsWith(term)?1:2;
  return trusts.filter(trust=>`${trust.name} ${trust.org_code}`.toLowerCase().includes(term)).sort((a,b)=>rank(a)-rank(b)).slice(0,7);
}
const radians=Math.PI/180;
export const mercator=([lon,lat]:number[])=>[lon*radians,-Math.log(Math.tan(Math.PI/4+lat*radians/2))];
const centre=mercator([-2,53.4]);
export type MapCamera={zoom:number;x:number;y:number};
export const MIN_MAP_ZOOM=1;
export const MAX_MAP_ZOOM=3;
export const HOME_CAMERA:MapCamera={zoom:MIN_MAP_ZOOM,x:0,y:0};
/** Keep the camera over Britain. The fitted overview cannot be panned away. */
export function constrainCamera(camera:MapCamera):MapCamera {
  const zoom=Math.max(MIN_MAP_ZOOM,Math.min(MAX_MAP_ZOOM,Number.isFinite(camera.zoom)?camera.zoom:MIN_MAP_ZOOM));
  const extra=zoom-MIN_MAP_ZOOM;
  if(extra===0)return {...HOME_CAMERA};
  return {zoom,x:Math.max(-260*extra,Math.min(260*extra,Number.isFinite(camera.x)?camera.x:0)),y:Math.max(-330*extra,Math.min(250*extra,Number.isFinite(camera.y)?camera.y:0))};
}
export function zoomCamera(camera:MapCamera,change:number):MapCamera {
  const nextZoom=Math.max(MIN_MAP_ZOOM,Math.min(MAX_MAP_ZOOM,camera.zoom+change));
  const ratio=nextZoom/camera.zoom;
  return constrainCamera({zoom:nextZoom,x:camera.x*ratio,y:camera.y*ratio});
}
export function project(coordinates:number[],camera:MapCamera={zoom:1,x:0,y:0}):number[] {const[x,y]=mercator(coordinates);return [965+(x-centre[0])*3450*camera.zoom+camera.x,320+(y-centre[1])*3450*camera.zoom+camera.y];}
export function geometryPath(geometry:Json,camera:MapCamera):string {
  const line=(points:number[][])=>points.map((p,i)=>{const[x,y]=project(p,camera);return `${i?'L':'M'}${x.toFixed(1)},${y.toFixed(1)}`;}).join('');
  if(!geometry)return '';
  if(geometry.type==='LineString')return line(geometry.coordinates);
  if(geometry.type==='MultiLineString')return geometry.coordinates.map(line).join('');
  if(geometry.type==='Polygon')return geometry.coordinates.map((ring:number[][])=>line(ring)+'Z').join('');
  if(geometry.type==='MultiPolygon')return geometry.coordinates.flatMap((polygon:number[][][])=>polygon.map(ring=>line(ring)+'Z')).join('');
  if(geometry.type==='GeometryCollection')return geometry.geometries.map((g:Json)=>geometryPath(g,camera)).join('');
  return '';
}
export function featureList(geo:Json|null):Json[] {return !geo?[]:geo.type==='FeatureCollection'?geo.features:geo.type==='Feature'?[geo]:[{geometry:geo,properties:{}}];}
