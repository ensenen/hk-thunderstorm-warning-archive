const $=s=>document.querySelector(s);
const fmt=new Intl.NumberFormat('zh-HK');
const escapeHtml=s=>(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const dateFmt=v=>new Intl.DateTimeFormat('zh-HK',{year:'numeric',month:'long',day:'numeric',timeZone:'Asia/Hong_Kong'}).format(new Date(v));
let payload,category='全部';
async function init(){
  const response=await fetch('/api/language-evolution');if(!response.ok)throw new Error(`HTTP ${response.status}`);payload=await response.json();
  $('#evolutionUpdated').textContent=payload.source_fetched_at?`資料更新：${new Intl.DateTimeFormat('zh-HK',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Hong_Kong'}).format(new Date(payload.source_fetched_at))}`:'資料更新時間未能取得';
  $('#methodNote').textContent=payload.method_note;
  const categories=['全部',...new Set(payload.terms.map(t=>t.category))];
  $('#termFilters').innerHTML=categories.map(c=>`<button class="${c===category?'active':''}" data-category="${escapeHtml(c)}">${escapeHtml(c)}</button>`).join('');
  document.querySelectorAll('#termFilters button').forEach(button=>button.onclick=()=>{category=button.dataset.category;document.querySelectorAll('#termFilters button').forEach(x=>x.classList.toggle('active',x===button));render()});render();
}
function render(){const terms=payload.terms.filter(t=>category==='全部'||t.category===category);$('#termTimeline').innerHTML=terms.map(termCard).join('')}
function termCard(term){
  const max=Math.max(1,...term.yearly.map(x=>x.count)),years=new Map(term.yearly.map(x=>[+x.year,x.count])),bars=[];
  for(let year=payload.archive_start_year;year<=payload.archive_end_year;year++){const count=years.get(year)||0;bars.push(`<i tabindex="0" role="img" aria-label="${year}年，${count}份天氣稿" style="--value:${count/max}" title="${year}：${count}份"></i>`)}
  const samples=term.samples.map((sample,index)=>`<article class="word-sample"><div><span>${index?'較近期例子':'最早例子'}</span><time>${dateFmt(sample.bulletin_at)}</time></div><p>${escapeHtml(sample.body_text)}</p><a href="${sample.source_url}" target="_blank" rel="noopener">政府原文 ↗</a></article>`).join('');
  return `<article class="term-card"><div class="term-copy"><div class="term-category">${escapeHtml(term.category)}</div><h3>「${escapeHtml(term.term)}」</h3><p>${escapeHtml(term.description)}</p><div class="term-stats"><strong>${fmt.format(term.count)}</strong>份天氣稿 <span>${term.first_year||'—'} → ${term.last_year||'—'}</span></div></div><div class="term-data"><div class="mini-years">${bars.join('')}</div><div class="year-axis"><span>${payload.archive_start_year}</span><span>2005</span><span>2012</span><span>2019</span><span>${payload.archive_end_year}</span></div><div class="word-samples">${samples}</div></div></article>`;
}
init().catch(error=>{$('#termTimeline').innerHTML=`<div class="empty">載入失敗：${escapeHtml(error.message)}</div>`});
