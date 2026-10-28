import {ACCESS_LABELS,formatDate,csvEncode,normalize,marketOn} from './ledger-engine.mjs';
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const url=value=>{try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)?esc(u.href):'#';}catch{return '#';}};
const number=n=>new Intl.NumberFormat('en-US').format(n);
const money=n=>n===null?'—':`$${n<0.01&&n>0?n.toPrecision(2):new Intl.NumberFormat('en-US',{maximumFractionDigits:3}).format(n)}`;
const SOURCE_LABELS={models_dev:'models.dev',openrouter:'OpenRouter',openai_api:'OpenAI API',anthropic_api:'Anthropic API',google_api:'Google API',mistral_api:'Mistral API'};
const PAGE=50;
let market, listings=[], rows=[];
const state={day:'',query:'',provider:'',sort:'model',page:1};

function modelOf(id){const [name,org,access]=market.models[id];return {name,org,access,orgName:market.orgs[org]||org};}
function load(){
 listings=marketOn(market,state.day).map(r=>({...r,model:modelOf(r.modelId)}));
 const providers=[...new Set(listings.map(r=>r.provider))].sort();
 if(state.provider&&!providers.includes(state.provider))state.provider='';
 $('provider-filter').innerHTML='<option value="">All providers</option>'+providers.map(p=>`<option value="${esc(p)}"${p===state.provider?' selected':''}>${esc(p)}</option>`).join('');
 render();
}
function render(){
 const words=normalize(state.query).split(/\s+/).filter(Boolean);
 rows=listings.filter(r=>(!state.provider||r.provider===state.provider)&&words.every(w=>normalize([r.model.name,r.modelId,r.model.orgName,r.provider,r.apiId].join(' ')).includes(w)));
 const by={model:(a,b)=>a.model.name.localeCompare(b.model.name),
  output:(a,b)=>(a.price?.output??Infinity)-(b.price?.output??Infinity),
  context:(a,b)=>(Number(b.cap?.context)||0)-(Number(a.cap?.context)||0)}[state.sort];
 rows.sort((a,b)=>by(a,b)||a.model.name.localeCompare(b.model.name)||a.provider.localeCompare(b.provider));
 const pages=Math.max(1,Math.ceil(rows.length/PAGE));state.page=Math.min(Math.max(1,state.page),pages);
 const models=new Set(rows.map(r=>r.modelId)).size,providers=new Set(rows.map(r=>r.provider)).size;
 $('market-summary').textContent=`On ${formatDate(state.day)}: ${number(rows.length)} listings of ${number(models)} ledger models from ${number(providers)} providers.`;
 $('market-body').innerHTML=rows.length?rows.slice((state.page-1)*PAGE,state.page*PAGE).map(r=>`<tr>
  <td><span class="model-name">${esc(r.model.name)}</span><span class="model-meta">${esc(r.model.orgName)} <span aria-hidden="true">·</span> ${esc(ACCESS_LABELS[r.model.access]||r.model.access)}</span></td>
  <td><span class="event-label">${esc(r.provider)}<span class="model-meta">${esc(SOURCE_LABELS[r.source]||r.source)} · ${esc(r.apiId)}</span></span></td>
  <td><span class="number">${money(r.price?.input??null)}</span></td>
  <td><span class="number">${money(r.price?.output??null)}</span></td>
  <td><span class="number">${r.cap?.context?number(Number(r.cap.context)):'—'}</span></td>
  <td><span class="date-cell">${esc(formatDate(r.observedFrom))}</span></td>
  <td><a class="source-link" href="${url(r.url)}" target="_blank" rel="noopener noreferrer" aria-label="Open source for ${esc(r.model.name)} on ${esc(r.provider)}">Source ↗</a></td></tr>`).join('')
  :'<tr><td colspan="7" class="empty-state"><strong>No listings match</strong>Try another day, provider, or search.</td></tr>';
 $('market-page').textContent=`${state.page} / ${pages}`;$('market-prev').disabled=state.page===1;$('market-next').disabled=state.page===pages||!rows.length;
 $('market-export').disabled=!rows.length;
}
function exportView(){
 const exported=rows.map(r=>({date:state.day,model_id:r.modelId,model_name:r.model.name,developer:r.model.orgName,access_type:r.model.access,provider:r.provider,source:r.source,api_id:r.apiId,price_input_usd_per_1m:r.price?.input??'',price_output_usd_per_1m:r.price?.output??'',price_cached_usd_per_1m:r.price?.cached??'',context_length:r.cap?.context||'',max_output:r.cap?.maxOutput||'',observed_from:r.observedFrom,source_url:r.url}));
 const blob=new Blob(['\ufeff',csvEncode(exported,Object.keys(exported[0]))],{type:'text/csv;charset=utf-8;'});
 const href=URL.createObjectURL(blob),a=document.createElement('a');a.href=href;a.download=`llm-ledger-market-${state.day}.csv`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(href),1000);
}
async function init(){
 try{
  const response=await fetch('./data/market.json');if(!response.ok)throw new Error('market request failed');
  market=await response.json();
  const picked=new URLSearchParams(location.search).get('date');
  state.day=picked&&picked>=market.first&&picked<=market.last?picked:market.last;
  Object.assign($('market-date'),{min:market.first,max:market.last,value:state.day});
  $('market-first').textContent=formatDate(market.first);
  $('market-snapshot').href=`https://github.com/YasamanAnsari/llm-ledger/tree/${encodeURIComponent(market.commit)}/data/observations`;
  load();
 }catch(error){console.error(error);$('market-summary').textContent='The observations could not load.';$('market-body').innerHTML='<tr><td colspan="7" class="empty-state"><strong>The observations couldn’t be loaded.</strong><a class="source-link" href="./data/market_on_date.csv" download>Download the newest day ↗</a></td></tr>';}
}
$('market-filters').addEventListener('submit',e=>e.preventDefault());
$('market-date').addEventListener('change',e=>{const v=e.target.value;if(!v||v<market.first||v>market.last)return;state.day=v;state.page=1;history.replaceState(null,'',`?date=${v}`);load();});
$('market-search').addEventListener('input',e=>{state.query=e.target.value;state.page=1;render();});
$('provider-filter').addEventListener('change',e=>{state.provider=e.target.value;state.page=1;render();});
$('market-sort').addEventListener('change',e=>{state.sort=e.target.value;state.page=1;render();});
$('market-prev').addEventListener('click',()=>{state.page--;render();});
$('market-next').addEventListener('click',()=>{state.page++;render();});
$('market-export').addEventListener('click',exportView);
init();
