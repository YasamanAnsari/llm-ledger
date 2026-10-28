export const EVENT_LABELS = {
 announced:'Announced',preview:'Limited preview',paper_published:'Paper published',system_card:'System card',api_preview:'API preview',api_ga:'API available',weights_released:'Weights released',consumer_rollout:'Consumer rollout',free_tier:'Free-tier access',platform_availability:'Platform listing',price_changed:'Price changed',feature_added:'Feature added',alias_repointed:'Alias repointed',renamed:'Renamed',deprecation_announced:'Deprecation announced',retired:'Retired'
};
export const ACCESS_LABELS={open_weights:'Open weights',api_only:'API only',consumer_only:'Consumer only',internal:'Internal',never_released:'Never released'};
export const PAGE_SIZE=20;
export function normalize(text){return String(text??'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();}
export function baseEvent(via){return (via||'').replace(/_fallback$/,'');}
export function createLedger(data){
 const organizations=new Map(data.organizations.map(o=>[o.org_id,o]));
 const models=new Map(data.models.map(m=>[m.model_id,m]));
 const eventsByModel=new Map();
 const claimsByEvent=new Map();
 const aliasesByModel=new Map();
 const attributesByModel=new Map(data.attributes.map(a=>[a.model_id,a]));
 for(const e of data.events){if(!eventsByModel.has(e.model_id))eventsByModel.set(e.model_id,[]);eventsByModel.get(e.model_id).push(e);}
 for(const list of eventsByModel.values())list.sort((a,b)=>a.date.localeCompare(b.date)||a.event_id.localeCompare(b.event_id));
 for(const c of data.claims){if(!claimsByEvent.has(c.event_id))claimsByEvent.set(c.event_id,[]);claimsByEvent.get(c.event_id).push(c);}
 for(const c of data.crosswalk){if(!aliasesByModel.has(c.model_id))aliasesByModel.set(c.model_id,[]);aliasesByModel.get(c.model_id).push(c);}
 const searchText=new Map(data.models.map(m=>{const org=organizations.get(m.developer_org_id)||{};return[m.model_id,normalize([m.canonical_name,m.model_id,m.family,org.canonical_name,org.short_name,org.aliases,...(aliasesByModel.get(m.model_id)||[]).map(a=>a.identifier)].join(' '))];}));
 function anchorEvent(model){
  const via=baseEvent(model.first_availability_via);
  return (eventsByModel.get(model.model_id)||[]).find(e=>e.date===model.first_public_availability_date&&e.event_type===via&&e.region==='global')||null;
 }
 function query(state={}){
  const {view='models',query='',org='',event='',confidence='',access='',sort='newest'}=state;
  const words=normalize(query).split(/\s+/).filter(Boolean);
  const matches=m=>(!org||m.developer_org_id===org)&&(!access||(access==='fully_open'?m.access_group==='fully_open':m.access_type===access))&&words.every(w=>searchText.get(m.model_id).includes(w));
  let rows;
  if(view==='events'){
   rows=data.events.filter(e=>(!event||e.event_type===event)&&(!confidence||e.confidence===confidence)).map(e=>({model:models.get(e.model_id),event:e,date:e.date,confidence:e.confidence})).filter(r=>r.model&&matches(r.model));
  }else{
   rows=data.models.filter(matches).map(model=>{
    const chosen=event?(eventsByModel.get(model.model_id)||[]).find(e=>e.event_type===event):anchorEvent(model);
    return {model,event:chosen,date:event?(chosen?.date||''):model.first_public_availability_date,confidence:event?(chosen?.confidence||''):model.first_availability_confidence};
   }).filter(r=>(!event||r.event)&&(!confidence||(confidence==='undated'?!r.date:r.confidence===confidence)));
  }
  return rows.sort((a,b)=>{
   if(sort==='name')return a.model.canonical_name.localeCompare(b.model.canonical_name)||a.date.localeCompare(b.date);
   if(!a.date!==!b.date)return a.date?-1:1;
   return (sort==='oldest'?a.date.localeCompare(b.date):b.date.localeCompare(a.date))||a.model.model_id.localeCompare(b.model.model_id)||(a.event?.event_id||'').localeCompare(b.event?.event_id||'');
  });
 }
 return {data,organizations,models,eventsByModel,claimsByEvent,aliasesByModel,attributesByModel,anchorEvent,query};
}
export function formatDate(date,precision='day'){
 if(!date)return 'Undated';
 if(precision==='year')return date.slice(0,4);
 if(precision==='quarter')return `Q${Math.floor((Number(date.slice(5,7))-1)/3)+1} ${date.slice(0,4)}`;
 const value=new Date(`${date}T12:00:00Z`);
 if(Number.isNaN(value.getTime()))return date;
 return new Intl.DateTimeFormat('en-GB',{...(precision==='month'?{}:{day:'2-digit'}),month:'short',year:'numeric',timeZone:'UTC'}).format(value);
}
const PER_MILLION={per_1m_tokens:1,per_token:1e6};
// USD per 1M tokens; a negative value is OpenRouter's variable-price marker, not a price.
export function perMillion(value,unit){
 if(value==='')return null;
 const n=Number(value);
 return !Number.isFinite(n)||n<0?null:Number((n*PER_MILLION[unit]).toPrecision(12));
}
// Listings on one ISO day from market.json runs, each joined to the same
// source's price and capability run for that id on that day.
export function marketOn(market,day){
 const covers=(first,last)=>first<=day&&day<=last;
 const price=new Map(),cap=new Map();
 for(const [key,input,output,cached,unit,first,last] of market.price)if(covers(first,last))price.set(key,{input:perMillion(input,unit),output:perMillion(output,unit),cached:perMillion(cached,unit)});
 for(const [key,context,maxOutput,modalities,toolUse,first,last] of market.capability)if(covers(first,last))cap.set(key,{context,maxOutput,modalities,toolUse});
 return market.availability.filter(r=>covers(r[4],r[5])).map(([source,provider,apiId,modelId,first,,url])=>{
  const key=`${source}|${provider}|${apiId}`;
  return {source,provider,apiId,modelId,observedFrom:first,url,price:price.get(key)||null,cap:cap.get(key)||null};
 });
}
export function csvEncode(records,columns){
 const escape=value=>{let text=String(value??'');if(/^[=+@\-\t\r]/.test(text))text="'"+text;return /[",\n\r]/.test(text)?'"'+text.replaceAll('"','""')+'"':text;};
 return [columns.map(escape).join(','),...records.map(r=>columns.map(k=>escape(r[k])).join(','))].join('\r\n')+'\r\n';
}
