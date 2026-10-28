import {createLedger,EVENT_LABELS,ACCESS_LABELS,PAGE_SIZE,NO_COUNTRY,formatDate,csvEncode} from './ledger-engine.mjs';
import {annotateGroups,annualCounts,opennessTier,gapBins,mentionBins,retirementFates,scatterPoints,renderGap,renderFates,renderAnnual,renderScatter,capabilityFrontier,frontierLag,renderFrontier,arenaBest,ARENA_METRIC,METRICS,ACCESS,OPENNESS,COUNTRIES} from './charts.mjs';
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const url=value=>{try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)?esc(u.href):'#';}catch{return '#';}};
const number=n=>new Intl.NumberFormat('en-US').format(n);
const title=value=>String(value||'').split('_').map(s=>s.charAt(0).toUpperCase()+s.slice(1)).join(' ');
let ledger, rows=[], selectedModel=null, toastTimer;
const state={view:'models',query:'',org:'',country:'',event:'',confidence:'',access:'',sort:'newest',page:1};
const regionName=new Intl.DisplayNames(['en'],{type:'region'});
const countryName=code=>code===NO_COUNTRY?'Not recorded':regionName.of(code);
const badge=(confidence,undated=false)=>`<span class="badge ${esc(undated?'undated':confidence)}" title="${esc(undated?'No qualifying availability date recorded.':confidence==='verified'?'Verified under ledger policy; may be automated or project-assisted, not necessarily human-reviewed.':confidence==='inferred'?'Single-source or insufficiently corroborated date.':'Conflicting source dates are retained in the event notes.')} ">${esc(undated?'Undated':title(confidence))}</span>`;
function orgIcon(id){const org=ledger.organizations.get(id);return ledger.data.meta.icons.includes(id)?`<img class="org-icon" src="./assets/orgs/${encodeURIComponent(id)}.svg" alt="" loading="lazy" width="17" height="17">`:`<span class="org-fallback" aria-hidden="true">${esc((org?.short_name||id).slice(0,2).toUpperCase())}</span>`;}
function orgName(model){const org=ledger.organizations.get(model.developer_org_id);return org?.short_name||org?.canonical_name||model.developer_org_id;}
function eventName(event){return EVENT_LABELS[event?.event_type]||title(event?.event_type);}
function isFuture(event){return Boolean(event?.date&&event.date>ledger.data.meta.snapshot);}
function announcedHTML(model){
 const a=(ledger.eventsByModel.get(model.model_id)||[]).find(e=>e.event_type==='announced');
 if(!a)return '<span class="date-cell muted-date">—</span>';
 const gap=model.anticipation_days===''?'':Number(model.anticipation_days);
 return `<span class="date-cell">${esc(formatDate(a.date,a.precision))}${gap!==''&&gap!==0?`<small>${gap>0?`${number(gap)} d before launch`:`${number(-gap)} d after launch`}</small>`:''}</span>`;
}
function dateHTML(row){return `<span class="date-cell">${esc(formatDate(row.date,row.event?.precision))}${isFuture(row.event)?'<small>Scheduled in snapshot</small>':''}</span>`;}
function showToast(message){$('toast').textContent=message;$('toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('visible'),3200);}
function setState(next){Object.assign(state,next,{page:1});render();}
function render(){
 if(!ledger)return;
 rows=ledger.query(state);
 const pages=Math.max(1,Math.ceil(rows.length/PAGE_SIZE));state.page=Math.min(Math.max(1,state.page),pages);
 const pageRows=rows.slice((state.page-1)*PAGE_SIZE,state.page*PAGE_SIZE);
 const modelView=state.view==='models';
 $('table-caption').textContent=modelView?(state.event?'Models and their earliest matching milestone':'Models and their first public availability dates'):'Dated model lifecycle events, including future schedules';
 $('dataset-panel').setAttribute('aria-labelledby',modelView?'models-tab':'events-tab');
 const headers=modelView?['MODEL','DEVELOPER','ANNOUNCED',state.event?'MILESTONE DATE':'FIRST AVAILABLE','VIA','CONFIDENCE','EVENTS']:['MODEL','DEVELOPER','EVENT DATE','MILESTONE / PLATFORM','CONFIDENCE','SOURCE'];
 const dateColumn=modelView?3:2;
 $('table-head').innerHTML='<tr>'+headers.map((h,i)=>`<th scope="col">${h}${i===dateColumn&&state.sort!=='name'?(state.sort==='newest'?' ↓':' ↑'):''}</th>`).join('')+'<th scope="col"><span class="sr-only">Details</span></th></tr>';
 $('table-body').innerHTML=pageRows.length?pageRows.map(row=>{
  const m=row.model,e=row.event;
  const modelButton=`<button class="model-name" data-model="${esc(m.model_id)}" ${modelView?'':`data-event="${esc(e.event_id)}"`} title="Open ${esc(m.canonical_name)} timeline">${esc(m.canonical_name)}</button><span class="model-meta">${esc(m.family)} <span aria-hidden="true">·</span> ${esc(ACCESS_LABELS[m.access_type]||title(m.access_type))}</span>`;
  const org=`<div class="org-cell">${orgIcon(m.developer_org_id)}<span>${esc(orgName(m))}</span></div>`;
  const milestone=`<span class="event-label">${e?esc(eventName(e)):'—'}${m.first_availability_via.endsWith('_fallback')&&modelView&&!state.event?' <span title="Fallback availability event">*</span>':''}${!modelView&&e.platform?`<span class="model-meta">${esc(title(e.platform))}</span>`:''}</span>`;
  const source=modelView?`<span class="event-count">${ledger.eventsByModel.get(m.model_id)?.length||0}</span>`:`<a class="source-link" href="${url(e.source_url)}" target="_blank" rel="noopener noreferrer" aria-label="Open source for ${esc(m.canonical_name)} ${esc(eventName(e))}">Source ↗</a>`;
  const announced=modelView?`<td>${announcedHTML(m)}</td>`:'';
  return `<tr><td>${modelButton}</td><td>${org}</td>${announced}<td>${dateHTML(row)}</td><td>${milestone}</td><td>${badge(row.confidence,!row.date)}</td><td>${source}</td><td><button class="row-arrow" data-model="${esc(m.model_id)}" ${e?`data-event="${esc(e.event_id)}"`:''} aria-label="View ${esc(m.canonical_name)} timeline">↗</button></td></tr>`;
 }).join(''):`<tr><td colspan="${headers.length+1}" class="empty-state"><strong>No matching ${modelView?'models':'events'}</strong>Try another search or broaden the filters.<button data-reset>Clear all filters</button></td></tr>`;
 const first=rows.length?(state.page-1)*PAGE_SIZE+1:0,last=Math.min(state.page*PAGE_SIZE,rows.length);
 $('result-count').textContent=`Showing ${number(first)}–${number(last)} of ${number(rows.length)} ${modelView?'models':'events'}`;
 $('page-number').textContent=`${state.page} / ${pages}`;$('prev-page').disabled=state.page===1;$('next-page').disabled=state.page===pages||!rows.length;
 $('reset-filters').hidden=!['query','org','country','event','confidence','access'].some(k=>state[k]);
 $('export-filtered').disabled=!rows.length;
 document.querySelectorAll('[data-view]').forEach(b=>{const active=b.dataset.view===state.view;b.classList.toggle('active',active);b.setAttribute('aria-selected',String(active));b.tabIndex=active?0:-1;});
 document.querySelectorAll('[data-access]').forEach(b=>{const active=b.dataset.access===state.access;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
 const undated=$('confidence-filter').querySelector('[value="undated"]');undated.disabled=!modelView||Boolean(state.event);
}
function reset(){Object.assign(state,{query:'',org:'',country:'',event:'',confidence:'',access:'',sort:'newest',page:1});for(const id of ['search','org-filter','country-filter','event-filter','confidence-filter'])$(id).value='';$('sort').value='newest';render();}
function openModel(id,eventId=''){
 const m=ledger.models.get(id);if(!m)return;selectedModel=id;
 const events=ledger.eventsByModel.get(id)||[];const anchor=ledger.anchorEvent(m);const attr=ledger.attributesByModel.get(id);
 const links=ledger.aliasesByModel.get(id)||[];
 const facts=[['First available',formatDate(m.first_public_availability_date,anchor?.precision)],['Access',ACCESS_LABELS[m.access_type]||title(m.access_type)],['Date confidence',m.first_availability_confidence?title(m.first_availability_confidence):'Undated'],['Model type',m.model_type.toUpperCase()],['License',m.license||'Not recorded'],['Availability via',anchor?`${eventName(anchor)}${m.first_availability_via.endsWith('_fallback')?' (fallback)':''}`:'Not recorded']];
 if(attr?.context_length)facts.push(['Context window',number(Number(attr.context_length))+' tokens']);
 $('dialog-content').innerHTML=`<div class="dialog-model-title">${orgIcon(m.developer_org_id)}<div><h2 id="dialog-title">${esc(m.canonical_name)}</h2><p>${esc(orgName(m))} · ${esc(m.family)}</p></div></div><p class="dialog-model-id">${esc(m.model_id)}</p><div class="record-facts">${facts.map(([label,value])=>`<div><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('')}</div>${m.notes?`<p class="record-note">${esc(m.notes)}</p>`:''}<div class="dialog-section-heading"><h3>Lifecycle & source evidence</h3><span>${number(events.length)} dated ${events.length===1?'event':'events'}</span></div><div class="model-timeline">${events.map(e=>{
  const claims=ledger.claimsByEvent.get(e.event_id)||[];const live=claims.filter(c=>!c.superseded_on),historical=claims.filter(c=>c.superseded_on);const verifier=e.verified_by||'Not independently verified';
  return `<article class="lifecycle-event ${esc(e.confidence)}${e.event_id===eventId?' highlight':''}" id="detail-${esc(e.event_id)}"><div class="event-top"><div><h4>${esc(eventName(e))}</h4>${e.platform?`<span class="platform-tag">${esc(title(e.platform))}</span>`:''}</div>${badge(e.confidence)}</div><div class="event-meta"><time datetime="${esc(e.date)}">${esc(formatDate(e.date,e.precision))}</time><span>${esc(title(e.precision))} precision · ${esc(e.region)}</span>${isFuture(e)?'<span class="scheduled-label">Scheduled as of snapshot</span>':''}${anchor?.event_id===e.event_id?'<span>Sets first availability</span>':''}</div><a class="event-source" href="${url(e.source_url)}" target="_blank" rel="noopener noreferrer">${esc(new URL(e.source_url).hostname.replace(/^www\./,''))} ↗</a>${e.detail?`<p class="event-notes"><strong>Detail:</strong> ${esc(e.detail)}</p>`:''}${e.notes?`<p class="event-notes">${esc(e.notes)}</p>`:''}<details class="evidence-details" ${e.event_id===eventId?'open':''}><summary>${live.length?`${live.length} live source ${live.length===1?'claim':'claims'}`:'Source & verification record'}${historical.length?` · ${historical.length} earlier ${historical.length===1?'claim':'claims'}`:''}</summary><div><p>Source type: ${esc(title(e.source_type))}<br>Verifier: ${esc(verifier)}${e.verified_date?` · ${esc(formatDate(e.verified_date))}`:''}</p>${[...live,...historical].map(c=>`<div class="claim-row${c.superseded_on?' superseded':''}"><span class="claim-date">${esc(formatDate(c.date,c.precision))}</span><a href="${url(c.source_url)}" target="_blank" rel="noopener noreferrer">${esc(c.label||new URL(c.source_url).hostname)} ↗</a><p>${c.first_party==='true'?'First-party record':c.bound==='true'?'Bracketing timestamp; not a stated launch date':'Stated date'}${c.superseded_on?` · superseded on ${esc(formatDate(c.superseded_on))}`:''}</p></div>`).join('')}</div></details></article>`;
 }).join('')||'<p class="record-note">No events recorded for this model.</p>'}</div>${links.length?`<details class="evidence-details" style="margin-top:28px"><summary>Names across catalogs (${links.length})</summary><div>${links.map(a=>`<div class="claim-row"><strong>${esc(a.namespace)}</strong><p>${esc(a.identifier)}</p></div>`).join('')}</div></details>`:''}<a class="evidence-link" href="https://github.com/YasamanAnsari/llm-ledger/blob/${ledger.data.meta.commit}/data/core/events.csv" target="_blank" rel="noopener noreferrer">View original events at this snapshot ↗</a>`;
 const dialog=$('model-dialog');if(!dialog.open)dialog.showModal();document.body.style.overflow='hidden';
 if(eventId){requestAnimationFrame(()=>document.getElementById(`detail-${eventId}`)?.scrollIntoView({block:'nearest',behavior:'instant'}));}else{dialog.scrollTop=0;}
}
const EXAMPLE_MODEL='openai-o3';
const EXAMPLE_EVENTS=['announced','api_ga','price_changed','retired'];
function renderExample(){
 const events=(ledger.eventsByModel.get(EXAMPLE_MODEL)||[]).filter(e=>EXAMPLE_EVENTS.includes(e.event_type)&&!e.platform);
 if(!events.length){$('example-timeline').closest('.hero-visual').hidden=true;return;}
 const announced=events.find(e=>e.event_type==='announced'),api=events.find(e=>e.event_type==='api_ga');
 const days=(a,b)=>Math.round((Date.parse(b.date)-Date.parse(a.date))/864e5);
 const priceLabel=e=>{const m=/output:([\d.]+)->([\d.]+)/.exec(e.detail||'');if(!m)return 'Price changed';const [from,to]=[Number(m[1]),Number(m[2])];return `Output price ${to<from?'cut':'raised'} ${Math.round(Math.abs(1-to/from)*100)}%`;};
 const label=e=>e.event_type==='price_changed'?priceLabel(e):e.event_type==='retired'&&isFuture(e)?'Shutdown scheduled':eventName(e);
 $('example-timeline').innerHTML=events.map((e,i)=>`<div class="example-event${i===events.length-1?' last':''}"><span class="timeline-point${e.event_type==='announced'?' muted':isFuture(e)?' hollow':''}"></span><time datetime="${esc(e.date)}">${esc(formatDate(e.date,e.precision).toUpperCase())}</time><div><strong>${esc(label(e))}</strong><span class="small-status ${esc(e.confidence)}">${esc(title(e.confidence))}</span></div></div>${e===announced&&api?`<div class="elapsed"><span></span><span>${number(days(announced,api))} days between announcement &amp; API access</span></div>`:''}`).join('');
}
function renderFindings(){
 const {meta}=ledger.data;
 for(const [id,value] of [['stat-models',meta.models],['stat-orgs',meta.organizations],['stat-events',meta.events],['stat-claims',meta.liveClaims]])$(id).textContent=number(value);
 document.querySelector('#models-tab span').textContent=number(meta.models);document.querySelector('#events-tab span').textContent=number(meta.events);
 $('snapshot-date').textContent=formatDate(meta.snapshot).toUpperCase();$('snapshot-date').setAttribute('datetime',meta.snapshot);
 $('snapshot-link').href=`https://github.com/YasamanAnsari/llm-ledger/tree/${encodeURIComponent(meta.commit)}`;$('snapshot-link').textContent=`Data as of ${formatDate(meta.snapshot)} ↗`;
 renderExample();
 const gaps=gapBins(ledger.data.models);
 $('gap-summary').textContent=ACCESS.filter(a=>gaps[a.key].n).map(a=>`${Math.round(gaps[a.key].later/gaps[a.key].n*100)}% of ${a.noun} (${number(gaps[a.key].later)} of ${number(gaps[a.key].n)})`).join(' and ')+' became usable only after the day they were announced.';
 $('gap-chart').innerHTML=renderGap(gaps);
 $('fate-chart').innerHTML=renderFates(retirementFates(ledger.data.models,ledger.data.events,meta.snapshot));
 $('annual-chart').innerHTML=renderAnnual(annualCounts(ledger.data.models,m=>m.access_group),meta.snapshot.slice(0,4));
 $('undated-count').textContent=number(meta.undated);
 renderScatterFigure('price_output');
 const frontier=capabilityFrontier(ledger.data.capability);
 const openOrApi=capabilityFrontier(ledger.data.capability,[{key:'open'},{key:'api_only'}],r=>({fully_open:'open',open_weights:'open',api_only:'api_only'})[r.access_group]);
 const lag=frontierLag(openOrApi.open,openOrApi.api_only);
 $('frontier-chart').innerHTML=renderFrontier(frontier,'2023-01-01',meta.snapshot);
 $('frontier-summary').textContent=lag?.days>0?`The best open-weights model, ${lag.best.name} (${formatDate(lag.best.date)}), scores ${lag.best.value}; an API-only model, ${lag.first.name}, scored that high on ${formatDate(lag.first.date)}, ${number(lag.days)} days (${(lag.days/30.44).toFixed(1)} months) earlier.`:'No API-only model scored as high as the best open-weights model before it.';
 renderOpenness();
 renderCountryFigure('annual');
 const mentions=mentionBins(ledger.data.first_mentions);
 $('mention-chart').innerHTML=renderGap(mentions,'Days from first availability to the first arXiv paper naming the model, by access type');
 $('mention-summary').textContent='Median days to a first paper: '+ACCESS.filter(a=>mentions[a.key].n).map(a=>`${a.noun} ${number(Math.round(mentions[a.key].median))} (n=${number(mentions[a.key].n)})`).join(', ')+'.';
 const verified=meta.confidence.verified/meta.events*100,inferred=meta.confidence.inferred/meta.events*100;
 $('confidence-ring').style.background=`conic-gradient(#447759 0% ${verified}%,#d5c196 ${verified}% ${verified+inferred}%,#b05a50 ${verified+inferred}% 100%)`;
 $('verified-pct').innerHTML=verified.toFixed(1)+'<span>%</span>';
 $('confidence-breakdown').innerHTML=['verified','inferred','disputed'].map(k=>`<div><span class="confidence-label"><i class="legend-dot ${k}"></i>${title(k)}</span><span class="number">${number(meta.confidence[k]||0)} <span class="share">/ ${((meta.confidence[k]||0)/meta.events*100).toFixed(1)}%</span></span></div>`).join('');
}
function renderOpenness(){
 const open=ledger.data.models.filter(m=>m.access_type==='open_weights');
 const tiers=Object.fromEntries(OPENNESS.map(t=>[t.key,0]));for(const m of open)tiers[opennessTier(m)]++;
 $('openness-chart').innerHTML=renderAnnual(annualCounts(open,opennessTier),ledger.data.meta.snapshot.slice(0,4),OPENNESS,'Open-weight models by year of first public availability and openness');
 $('openness-summary').textContent=`Of ${number(open.length)} open-weight models, ${number(tiers.fully_open)} (${Math.round(tiers.fully_open/open.length*100)}%) are fully open, ${Math.round(tiers.open_license/open.length*100)}% carry an OSI or permissive license without released data and code on record, ${Math.round(tiers.restricted/open.length*100)}% a restricted license, and ${Math.round(tiers.unknown/open.length*100)}% no recorded license.`;
}
let arenaRows;
async function loadArena(){
 if(!arenaRows){const res=await fetch('./data/arena.json');if(!res.ok)throw new Error(`arena.json: HTTP ${res.status}`);
  const byId=new Map(ledger.data.models.map(m=>[m.model_id,m]));
  arenaRows=(await res.json()).map(([id,date,rating,name])=>({id,date,value:Math.round(Number(rating)),name,country:byId.get(id)?.country_group}));}
 return arenaRows;
}
async function renderCountryFigure(view){
 const {models,capability,meta}=ledger.data;
 const share=c=>{const group=models.filter(m=>m.country_group===c);return `${number(group.length)} ${c==='US'?'US':'Chinese'} models (${Math.round(group.filter(m=>m.access_type==='open_weights').length/group.length*100)}% open weights)`;};
 const pair=COUNTRIES.slice(0,2);
 document.querySelectorAll('[data-country-view]').forEach(b=>{const on=b.dataset.countryView===view;b.classList.toggle('active',on);b.setAttribute('aria-pressed',String(on));});
 if(view==='arena'){
  let rows;
  try{rows=await loadArena();}catch(err){$('country-chart').innerHTML=`<p class="loading-state">Arena data could not be loaded (${esc(err.message)}).</p>`;return;}
  if(document.querySelector('[data-country-view].active')?.dataset.countryView!=='arena')return;
  const best=arenaBest(rows,pair,r=>r.country),last=best.US.at(-1),cn=best.CN.at(-1);
  $('country-summary').textContent=`${share('US')} and ${share('CN')}. `+(last&&cn&&last.date===cn.date?`On LMArena's ${formatDate(last.date)} text leaderboard, the top US model in the ledger, ${last.name}, rates ${number(last.value)}; the top Chinese one, ${cn.name}, ${number(cn.value)}.`:'');
  $('country-chart').innerHTML=renderFrontier(best,best.US[0]?.date||'2024-01-01',meta.snapshot,pair,'developer country',ARENA_METRIC);
  return;
 }
 const frontier=capabilityFrontier(capability,pair,r=>r.country_group);
 const cn=frontierLag(frontier.CN,frontier.US),us=frontierLag(frontier.US,frontier.CN);
 const [lag,behind,ahead]=cn?.days>0?[cn,'Chinese','US']:us?.days>0?[us,'US','Chinese']:[null];
 $('country-summary').textContent=`${share('US')} and ${share('CN')}. `+(lag?`The best ${behind} model, ${lag.best.name} (${formatDate(lag.best.date)}), scores ${lag.best.value} on ECI; a ${ahead} model, ${lag.first.name}, scored that high on ${formatDate(lag.first.date)}, ${number(lag.days)} days earlier.`:'');
 $('country-chart').innerHTML=view==='annual'?renderAnnual(annualCounts(models,m=>m.country_group),meta.snapshot.slice(0,4),COUNTRIES,'Models by year of first public availability and developer country'):renderFrontier(frontier,'2023-01-01',meta.snapshot,pair,'developer country');
}
function renderScatterFigure(metric){
 const {points,zero}=scatterPoints(ledger.data.models,ledger.data.attributes,metric);
 $('scatter-chart').innerHTML=renderScatter(points,metric,'2022-01-01',ledger.data.meta.snapshot);
 const counts=ACCESS.map(a=>`${number(points.filter(p=>p.access===a.key).length)} ${a.noun}`).join(' and ');
 $('scatter-caption').innerHTML=`${esc(METRICS[metric].label)} in ${esc(METRICS[metric].unit)}, log scale: ${esc(counts)} with a listing.${zero?` ${number(zero)} ${metric==='price_output'?'free ($0)':'zero-valued'} ${zero===1?'listing is':'listings are'} left out because zero has no place on a log axis.`:''} ${metric==='price_output'?'Prices are today’s list prices, not launch prices; for open weights they are what hosting providers charge.':'Context is the longest window the model is listed with.'} Click a mark to open its record.`;
 document.querySelectorAll('[data-metric]').forEach(b=>{const on=b.dataset.metric===metric;b.classList.toggle('active',on);b.setAttribute('aria-pressed',String(on));});
}
async function copyCitation(){
 const citation='@misc{llmledger2026,\n  author = {Ansari, Yasaman},\n  title  = {llm-ledger: a provenance-tracked dataset of dated events in the lifecycle of large language models},\n  year   = {2026},\n  url    = {https://github.com/YasamanAnsari/llm-ledger}\n}';
 try{await navigator.clipboard.writeText(citation);$('copy-citation').textContent='Copied ✓';showToast('Citation copied to clipboard');setTimeout(()=>$('copy-citation').innerHTML='Copy <span aria-hidden="true">⧉</span>',2500);}catch{const range=document.createRange();range.selectNodeContents($('citation'));window.getSelection().removeAllRanges();window.getSelection().addRange(range);showToast('Citation selected. Use your copy shortcut.');}
}
function exportView(){
 if(!rows.length)return;
 const exported=rows.map(r=>({model_id:r.model.model_id,model_name:r.model.canonical_name,developer:orgName(r.model),developer_country:ledger.organizations.get(r.model.developer_org_id)?.country||'',family:r.model.family,access_type:r.model.access_type,date:r.date,precision:r.event?.precision||'',event_type:r.event?.event_type||'',platform:r.event?.platform||'',confidence:r.confidence,source_url:r.event?.source_url||'',...(state.view==='events'?{event_id:r.event.event_id,region:r.event.region,verified_by:r.event.verified_by,notes:r.event.notes}:{first_availability_via:r.model.first_availability_via}),snapshot_date:ledger.data.meta.snapshot}));
 const blob=new Blob(['\ufeff',csvEncode(exported,Object.keys(exported[0]))],{type:'text/csv;charset=utf-8;'});const href=URL.createObjectURL(blob);const a=document.createElement('a');a.href=href;a.download=`llm-ledger-${state.view}-${ledger.data.meta.snapshot}.csv`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(href),1000);showToast(`Exported ${number(rows.length)} ${state.view}`);
}
$('filters').addEventListener('submit',e=>e.preventDefault());
$('search').addEventListener('input',e=>setState({query:e.target.value}));
for(const [id,key] of [['org-filter','org'],['country-filter','country'],['event-filter','event'],['confidence-filter','confidence'],['sort','sort']])$(id).addEventListener('change',e=>{const next={[key]:e.target.value};if(key==='event'&&state.confidence==='undated'){next.confidence='';$('confidence-filter').value='';}setState(next);});
document.querySelectorAll('[data-view]').forEach(button=>{button.addEventListener('click',()=>{const next={view:button.dataset.view};if(next.view==='events'&&state.confidence==='undated'){next.confidence='';$('confidence-filter').value='';}setState(next);});button.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const target=e.key==='Home'?$('models-tab'):e.key==='End'?$('events-tab'):button.dataset.view==='models'?$('events-tab'):$('models-tab');target.click();target.focus();}});});
document.querySelectorAll('[data-access]').forEach(button=>button.addEventListener('click',()=>setState({access:button.dataset.access})));
$('prev-page').addEventListener('click',()=>{state.page--;render();});$('next-page').addEventListener('click',()=>{state.page++;render();});
$('reset-filters').addEventListener('click',reset);$('export-filtered').addEventListener('click',exportView);$('copy-citation').addEventListener('click',copyCitation);
$('table-body').addEventListener('click',e=>{const model=e.target.closest('[data-model]');if(model)openModel(model.dataset.model,model.dataset.event);if(e.target.closest('[data-reset]'))reset();});
$('open-example').addEventListener('click',()=>{if(ledger)openModel(EXAMPLE_MODEL);else showToast('The dataset is still loading.');});
document.querySelectorAll('[data-metric]').forEach(b=>b.addEventListener('click',()=>{if(ledger)renderScatterFigure(b.dataset.metric);}));
document.querySelectorAll('[data-country-view]').forEach(b=>b.addEventListener('click',()=>{if(ledger)renderCountryFigure(b.dataset.countryView);}));
for(const id of ['scatter-chart','frontier-chart','country-chart'])$(id).addEventListener('click',e=>{const point=e.target.closest('[data-model]');if(point)openModel(point.dataset.model);});
$('close-dialog').addEventListener('click',()=>$('model-dialog').close());
$('model-dialog').addEventListener('click',e=>{if(e.target===$('model-dialog')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}});
$('model-dialog').addEventListener('close',()=>{document.body.style.overflow='';selectedModel=null;});
document.addEventListener('keydown',e=>{if(e.key==='/'&&!/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName)&&!$('model-dialog').open){e.preventDefault();$('search').focus();}});
async function init(){
 try{
  const response=await fetch('./data/ledger.json');if(!response.ok)throw new Error('Dataset request failed');
  ledger=createLedger(await response.json());
  annotateGroups(ledger.data.models,ledger.data.organizations,[...ledger.data.capability,...ledger.data.first_mentions]);
  const orgCounts=new Map();for(const m of ledger.data.models)orgCounts.set(m.developer_org_id,(orgCounts.get(m.developer_org_id)||0)+1);
  const options=[...ledger.organizations.values()].filter(o=>orgCounts.has(o.org_id)).sort((a,b)=>a.short_name.localeCompare(b.short_name));
  $('org-filter').innerHTML='<option value="">All developers</option>'+options.map(o=>`<option value="${esc(o.org_id)}">${esc(o.short_name||o.canonical_name)} (${orgCounts.get(o.org_id)})</option>`).join('');
  const countryCounts=new Map();for(const m of ledger.data.models){const c=ledger.organizations.get(m.developer_org_id)?.country||NO_COUNTRY;countryCounts.set(c,(countryCounts.get(c)||0)+1);}
  $('country-filter').innerHTML='<option value="">All countries</option>'+[...countryCounts].sort((a,b)=>b[1]-a[1]||countryName(a[0]).localeCompare(countryName(b[0]))).map(([c,n])=>`<option value="${esc(c)}">${esc(countryName(c))} (${number(n)})</option>`).join('');
  const eventTypes=new Set(ledger.data.events.map(e=>e.event_type));
  $('event-filter').innerHTML='<option value="">All milestones</option>'+Object.entries(EVENT_LABELS).filter(([k])=>eventTypes.has(k)).map(([k,v])=>`<option value="${k}">${esc(v)}</option>`).join('');
  renderFindings();render();
 }catch(error){console.error(error);$('result-count').textContent='The interactive dataset could not load.';$('table-body').innerHTML='<tr><td colspan="8" class="empty-state"><strong>The dataset couldn’t be loaded.</strong><a class="source-link" href="./data/models.csv" download>Download models CSV ↗</a> · <a class="source-link" href="./data/events.csv" download>Download events CSV ↗</a><button id="retry-load">Try again</button></td></tr>';$('retry-load').addEventListener('click',init);}
}
init();
const backToTop=$('back-to-top');
addEventListener('scroll',()=>backToTop.classList.toggle('visible',scrollY>innerHeight),{passive:true});
