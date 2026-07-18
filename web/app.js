const state={year:'',terminal:'',status:'',sort:'newest',q:'',page:1,pageSize:20,meta:null,directId:'',directOpened:false};
const $=s=>document.querySelector(s);
const fmt=new Intl.NumberFormat('zh-HK');
const eventNames={issued:'發出',extended:'延長',updated:'內容更新',cancelled:'取消'};
const terminalNames={expired:'自然過期',cancelled_early:'提早取消',unknown:'無法判斷'};
const statusNames={available:'有天氣稿',not_archived:'只有官方紀錄',not_downloaded:'尚未下載',archive_incomplete:'Archive缺漏'};
const sortNames={newest:'最新警告先',oldest:'最舊警告先',duration_desc:'有效時間最長先',duration_asc:'有效時間最短先',events_desc:'事件最多先',cancellation_margin_desc:'提早取消幅度最大先'};
const parseWarningNames={
  'explicit-date midnight 12 is date-boundary ambiguous':'原文使用「午夜12時」，所屬日期可能有歧義',
  'original warning start omitted from extension bulletin':'延長稿沒有重述原警告的發出時間',
  'gust update does not repeat warning start or valid-until time':'陣風更新沒有重述警告發出時間或有效時間',
  'effective-until timestamp not found':'未能從原文辨認警告有效至何時',
  'event wording not recognised':'未能辨認原文所述的警告事件類型',
};
function parseWarningName(message){
  const typo=message.match(/^source time typo normalised: (.+) -> (.+)$/);
  if(typo)return `原文時間疑有筆誤，解析時已由「${typo[1]}」修正為「${typo[2]}」`;
  return parseWarningNames[message]||message;
}
const HK_TIME_ZONE='Asia/Hong_Kong';
const dateFmt=v=>new Intl.DateTimeFormat('zh-HK',{year:'numeric',month:'long',day:'numeric',timeZone:HK_TIME_ZONE}).format(new Date(v));
const shortDateFmt=v=>new Intl.DateTimeFormat('zh-HK',{month:'numeric',day:'numeric',timeZone:HK_TIME_ZONE}).format(new Date(v));
const timeFmt=v=>new Intl.DateTimeFormat('zh-HK',{hour:'2-digit',minute:'2-digit',hour12:false,timeZone:HK_TIME_ZONE}).format(new Date(v));
const dateTimeFmt=v=>`${dateFmt(v)} ${timeFmt(v)}`;
const timeStandard=offset=>offset==='+0900'?'香港夏令時間（UTC+9）':'香港標準時間（UTC+8）';
const usesSummerTime=s=>s.start_utc_offset==='+0900'||s.end_utc_offset==='+0900';
function historicTimeBadge(s){
  if(!usesSummerTime(s))return '';
  return s.start_utc_offset===s.end_utc_offset?'<span class="badge historic-time">香港夏令時間 · UTC+9</span>':'<span class="badge historic-time">轉夏令時間 · UTC+8 → UTC+9</span>';
}
function historicTimeNote(s){
  if(!usesSummerTime(s))return '';
  const transition=s.start_utc_offset!==s.end_utc_offset;
  return `<div class="detail-note historic-time-note"><strong>歷史時間：</strong>${dateTimeFmt(s.started_at)} ${timeStandard(s.start_utc_offset)} → ${dateTimeFmt(s.ended_at)} ${timeStandard(s.end_utc_offset)}。${transition?`期間時鐘撥快一小時，所以實際有效時間係 ${duration(s.duration_minutes)}。`:''}</div>`;
}
const duration=m=>m<60?`${m}分鐘`:`${Math.floor(m/60)}小時${m%60?`${m%60}分鐘`:''}`;
const escapeHtml=s=>(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
async function get(url){const r=await fetch(url);if(!r.ok)throw new Error((await r.json()).error||r.statusText);return r.json()}
const locationSeriesId=()=>{const path=location.pathname.match(/^\/warnings\/(WTS-\d{8}-\d{4})$/);if(path)return path[1];const query=new URLSearchParams(location.search).get('q');return /^WTS-\d{8}-\d{4}$/.test(query||'')?query:''};
const detailLocation=id=>window.THUNDER_STATIC?`?q=${encodeURIComponent(id)}`:`/warnings/${encodeURIComponent(id)}`;

async function init(){
  state.directId=locationSeriesId();
  const initial=new URLSearchParams(location.search);if(initial.get('q')){state.q=initial.get('q');if(/^WTS-\d{8}-\d{4}$/.test(state.q))state.directId=state.q;}
  state.meta=await get('/api/meta');
  const select=$('#yearFilter');
  state.meta.years.forEach(({year,count})=>select.insertAdjacentHTML('beforeend',`<option value="${year}">${year} · ${count}</option>`));
  state.year=state.directId||state.q?'':state.meta.years[0]?.year||'';select.value=state.year;
  if(state.q)$('#searchInput').value=state.q;if(state.directId&&!state.q){state.q=state.directId;$('#searchInput').value=state.directId;}
  const years=state.meta.years.map(row=>row.year);$('#coverageRange').textContent=`${years.at(-1)}—${years[0]}`;
  $('#lastUpdated').textContent=state.meta.source_fetched_at?`資料更新：${dateTimeFmt(state.meta.source_fetched_at)}`:'資料更新時間未能取得';
  const [yearly]=await Promise.all([get('/api/yearly'),loadAll()]);
  renderYearChart(yearly);
  bind();
}
async function loadAll(){await Promise.all([loadStats(),loadSeries()])}
async function loadStats(){
  const s=await get(`/api/stats${state.year?`?year=${state.year}`:''}`);
  const coverage=s.total_series?Math.round(s.with_bulletins/s.total_series*100):0;
  $('#stats').innerHTML=`
    <div class="stat"><div class="stat-value">${fmt.format(s.total_series||0)}</div><div class="stat-label">${state.year||'全部年份'}警告系列</div></div>
    <div class="stat"><div class="stat-value stat-accent">${fmt.format(s.total_events||0)}</div><div class="stat-label">天氣稿事件</div></div>
    <div class="stat"><div class="stat-value">${fmt.format(s.cancelled_early||0)}</div><div class="stat-label">提早取消</div></div>
    <div class="stat"><div class="stat-value">${coverage}%</div><div class="stat-label">有天氣稿覆蓋</div></div>`;
}
function renderYearChart(data){
  const max=Math.max(...data.map(d=>d.total));
  $('#yearChart').innerHTML=data.map(d=>`<button class="year-bar ${d.year===state.year?'active':''}" style="--height:${Math.max(3,d.total/max*100)}%;--available:${d.total?d.available/d.total*100:0}%" data-year="${d.year}" aria-label="${d.year}年 ${d.total}組"><span>${d.year} · ${d.total}組</span></button>`).join('');
  document.querySelectorAll('.year-bar').forEach(b=>b.onclick=()=>{state.year=b.dataset.year;state.page=1;$('#yearFilter').value=state.year;document.querySelectorAll('.year-bar').forEach(x=>x.classList.toggle('active',x===b));loadAll();renderChips();document.querySelector('.archive-section').scrollIntoView()});
}
async function loadSeries(){
  $('#seriesList').innerHTML='<div class="loading">正在讀取警告紀錄…</div>';
  const p=new URLSearchParams({page:state.page,page_size:state.pageSize});
  ['year','terminal','status','sort','q'].forEach(k=>state[k]&&p.set(k,state[k]));
  const data=await get(`/api/series?${p}`);
  $('#resultCount').textContent=`${fmt.format(data.total)} 組 · 第 ${data.page}/${data.pages} 頁`;
  if(!data.items.length){$('#seriesList').innerHTML='<div class="empty">搵唔到符合條件嘅警告。</div>';$('#pagination').innerHTML='';return}
  $('#seriesList').innerHTML=data.items.map(card).join('');
  document.querySelectorAll('.series-card').forEach(c=>c.onclick=()=>openDetail(c.dataset.id,true));
  renderPages(data);
  renderChips();
  if(state.directId&&!state.directOpened&&data.items.some(item=>item.id===state.directId)){state.directOpened=true;await openDetail(state.directId);}
}
function card(s){
  const teaser=s.first_body||s.weather_bulletin_note||'只有天文台官方起訖紀錄，沒有詳細天氣稿。';
  return `<button class="series-card" data-id="${s.id}">
    <div><div class="series-time">${timeFmt(s.started_at)} → ${timeFmt(s.ended_at)}</div><div class="series-date">${dateFmt(s.started_at)}</div></div>
    <div class="series-main"><h3>${duration(s.duration_minutes)}雷暴警告</h3><p>${escapeHtml(teaser)}</p><div class="badges"><span class="badge ${s.terminal_type==='cancelled_early'?'early':s.terminal_type}">${terminalNames[s.terminal_type]}</span><span class="badge ${s.weather_bulletin_status}">${statusNames[s.weather_bulletin_status]}</span><span class="badge">${s.event_count}個事件</span>${s.crosses_day?'<span class="badge">跨日</span>':''}${historicTimeBadge(s)}</div></div>
    <div class="series-arrow">↗</div></button>`
}
function renderPages(d){
  const pages=[];for(let i=Math.max(1,d.page-2);i<=Math.min(d.pages,d.page+2);i++)pages.push(i);
  $('#pagination').innerHTML=`<button ${d.page===1?'disabled':''} data-page="${d.page-1}">←</button>${pages[0]>1?'<span class="pagination-ellipsis">…</span>':''}${pages.map(i=>`<button class="${i===d.page?'active':''}" data-page="${i}">${i}</button>`).join('')}${pages.at(-1)<d.pages?'<span class="pagination-ellipsis">…</span>':''}<button ${d.page===d.pages?'disabled':''} data-page="${d.page+1}">→</button>`;
  document.querySelectorAll('#pagination button:not([disabled])').forEach(b=>b.onclick=()=>{state.page=+b.dataset.page;loadSeries();document.querySelector('.archive-heading').scrollIntoView()});
}
function renderChips(){const labels=[];if(state.year)labels.push(`${state.year}年`);if(state.terminal)labels.push(terminalNames[state.terminal]);if(state.status)labels.push(statusNames[state.status]);if(state.sort!=='newest')labels.push(`排序：${sortNames[state.sort]}`);if(state.q)labels.push(`搜尋：${escapeHtml(state.q)}`);$('#activeFilters').innerHTML=labels.map(x=>`<span class="filter-chip">${x}</span>`).join('')}
async function openDetail(id,updateUrl=false){
  const d=$('#detailDialog');$('#detailContent').innerHTML='<div class="loading">正在建立時間線…</div>';if(!d.open)d.showModal();
  if(updateUrl)history.pushState({seriesId:id},'',detailLocation(id));
  const s=await get(`/api/series/${encodeURIComponent(id)}`);
  const note=s.weather_bulletin_note?`<div class="detail-note">${escapeHtml(s.weather_bulletin_note)}</div>`:'';
  $('#detailContent').innerHTML=`<div class="detail-header"><p class="eyebrow">${s.id}</p><h2>${dateFmt(s.started_at)}<br>雷暴警告</h2><div class="detail-summary"><span>${dateTimeFmt(s.started_at)} → ${dateTimeFmt(s.ended_at)}</span><span>${duration(s.duration_minutes)}</span><span>${terminalNames[s.terminal_type]}</span><span>${statusNames[s.weather_bulletin_status]}</span></div>${historicTimeNote(s)}${note}</div>
  <div class="timeline">${s.events.length?s.events.map(eventHtml).join(''):`<div class="empty">呢組舊警告只有官方起訖紀錄，沒有天氣稿時間線。<br><a class="source-link" target="_blank" rel="noopener" href="${s.official_source_url}">查看官方資料來源 ↗</a></div>`}</div>`;
}
function eventHtml(e){const until=e.valid_until?`新有效時間 ${dateTimeFmt(e.valid_until)}`:' ';return `<article class="event"><div class="event-time"><small>${shortDateFmt(e.event_at)}</small>${timeFmt(e.event_at)}</div><div class="event-dot"></div><div class="event-content"><h3>${eventNames[e.event_type]||e.event_type}</h3><div class="event-meta">${until}${e.is_correction?' · 更正稿':''}</div><p>${escapeHtml(e.body_text)}</p>${e.parse_warnings?.length?`<div class="detail-note">解析備註：${escapeHtml(e.parse_warnings.map(parseWarningName).join('；'))}</div>`:''}<a class="source-link" href="${e.source_url}" target="_blank" rel="noopener">政府天氣稿原文 ↗</a></div></article>`}
function closeDetail(){const d=$('#detailDialog');if(d.open)d.close();if(locationSeriesId())history.replaceState({},'',window.THUNDER_STATIC?location.pathname:'/');}
function bind(){
  $('#filters').onsubmit=e=>{e.preventDefault();state.year=$('#yearFilter').value;state.terminal=$('#terminalFilter').value;state.status=$('#statusFilter').value;state.sort=$('#sortFilter').value;state.q=$('#searchInput').value.trim();state.directId='';state.directOpened=false;state.page=1;document.querySelectorAll('.year-bar').forEach(x=>x.classList.toggle('active',x.dataset.year===state.year));loadAll()};
  $('#closeDialog').onclick=closeDetail;
  $('#detailDialog').onclick=e=>{if(e.target===$('#detailDialog'))closeDetail()};
  window.onpopstate=()=>{const id=locationSeriesId();if(id){openDetail(id,false)}else if($('#detailDialog').open){$('#detailDialog').close()}};
}
init().catch(e=>{$('#seriesList').innerHTML=`<div class="empty">載入失敗：${escapeHtml(e.message)}</div>`;console.error(e)});
