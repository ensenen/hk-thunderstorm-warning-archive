/* Browser-side replacement for the Python API in the GitHub Pages build. */
(()=>{
  if(!window.THUNDER_STATIC)return;
  const nativeFetch=window.fetch.bind(window);
  const dataRoot=new URL('data/',document.baseURI);
  let indexPromise,searchPromise,statsPromise;
  const read=name=>nativeFetch(new URL(name,dataRoot)).then(response=>{
    if(!response.ok)throw new Error(`靜態資料載入失敗：${response.status}`);
    return response.json();
  });
  const index=()=>indexPromise??=read('series-index.json');
  const searchIndex=()=>searchPromise??=read('search-index.json');
  const response=(payload,status=200)=>Promise.resolve(new Response(JSON.stringify(payload),{status,headers:{'Content-Type':'application/json; charset=utf-8'}}));
  const yearOf=row=>row.started_at.slice(0,4);
  const cancellationMargin=row=>row.terminal_type==='cancelled_early'&&row.scheduled_until_at_end?(new Date(row.scheduled_until_at_end)-new Date(row.ended_at))/60000:-1;
  const orderers={
    newest:(a,b)=>b.started_at.localeCompare(a.started_at),
    oldest:(a,b)=>a.started_at.localeCompare(b.started_at),
    duration_desc:(a,b)=>b.duration_minutes-a.duration_minutes||b.started_at.localeCompare(a.started_at),
    duration_asc:(a,b)=>a.duration_minutes-b.duration_minutes||b.started_at.localeCompare(a.started_at),
    events_desc:(a,b)=>b.event_count-a.event_count||b.started_at.localeCompare(a.started_at),
    cancellation_margin_desc:(a,b)=>cancellationMargin(b)-cancellationMargin(a)||b.started_at.localeCompare(a.started_at),
  };
  async function stats(url){const payload=await(statsPromise??=read('stats.json')),year=url.searchParams.get('year');return year?payload.years[year]:payload.all}
  async function series(url){
    const year=url.searchParams.get('year')||'',terminal=url.searchParams.get('terminal')||'',status=url.searchParams.get('status')||'',query=(url.searchParams.get('q')||'').trim().toLocaleLowerCase('zh-HK');
    const requestedSort=url.searchParams.get('sort')||'newest',sort=orderers[requestedSort]?requestedSort:'newest';
    const page=Math.max(1,Number.parseInt(url.searchParams.get('page')||'1',10)||1),pageSize=Math.min(50,Math.max(5,Number.parseInt(url.searchParams.get('page_size')||'20',10)||20));
    const corpus=query&&!/^wts-\d{8}-\d{4}$/i.test(query)?await searchIndex():{};
    const matches=(await index()).filter(row=>(!year||yearOf(row)===year)&&(!terminal||row.terminal_type===terminal)&&(!status||row.weather_bulletin_status===status)&&(!query||row.id.toLocaleLowerCase('zh-HK').includes(query)||(corpus[row.id]||'').toLocaleLowerCase('zh-HK').includes(query))).sort(orderers[sort]);
    const start=(page-1)*pageSize,items=matches.slice(start,start+pageSize);
    return {items,total:matches.length,page,page_size:pageSize,pages:Math.max(1,Math.ceil(matches.length/pageSize)),sort};
  }
  window.fetch=(input,options)=>{
    const url=new URL(typeof input==='string'?input:input.url,location.href),path=url.pathname;
    if(!path.includes('/api/'))return nativeFetch(input,options);
    if(path.endsWith('/api/meta'))return nativeFetch(new URL('meta.json',dataRoot),options);
    if(path.endsWith('/api/yearly'))return nativeFetch(new URL('yearly.json',dataRoot),options);
    if(path.endsWith('/api/analysis'))return nativeFetch(new URL('analysis.json',dataRoot),options);
    if(path.endsWith('/api/language-evolution'))return nativeFetch(new URL('language-evolution.json',dataRoot),options);
    if(path.endsWith('/api/stats'))return stats(url).then(response);
    if(path.endsWith('/api/series'))return series(url).then(response);
    const detail=path.match(/\/api\/series\/(WTS-\d{8}-\d{4})$/);
    if(detail)return nativeFetch(new URL(`series/${encodeURIComponent(detail[1])}.json`,dataRoot),options);
    return response({error:'not found'},404);
  };
})();
