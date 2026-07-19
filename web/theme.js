const THEME_STORAGE_KEY='thunder-archive-theme';
const THEME_OPTIONS=[
  ['midnight','深色'],
  ['paper','淺色'],
];
const systemDark=()=>matchMedia('(prefers-color-scheme: dark)').matches;
const normaliseTheme=preference=>{
  if(preference==='paper'||preference==='cloud'||preference==='light')return 'paper';
  if(preference==='midnight'||preference==='storm'||preference==='radar'||preference==='dark')return 'midnight';
  return systemDark()?'midnight':'paper';
};
function applyTheme(preference){
  const resolved=normaliseTheme(preference);
  document.documentElement.dataset.theme=resolved;
  document.documentElement.dataset.mode=resolved==='paper'?'light':'dark';
  document.documentElement.style.colorScheme=resolved==='paper'?'light':'dark';
  const colours={midnight:'#050b18',paper:'#f8f1e3'};
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content',colours[resolved]);
  return resolved;
}
function installThemeToggle(){
  const saved=localStorage.getItem(THEME_STORAGE_KEY)||'';
  let selected=applyTheme(saved);
  const button=document.createElement('button');
  button.type='button';button.className='theme-toggle';
  const describe=()=>{const next=selected==='paper'?'midnight':'paper',name=THEME_OPTIONS.find(([id])=>id===next)?.[1]||next;button.textContent=next==='paper'?'☀':'☾';button.setAttribute('aria-label',`切換至${name}模式`);button.title=`切換至${name}模式`};
  describe();
  const nav=document.querySelector('nav');nav?.insertBefore(button,nav.querySelector('.nav-meta'));
  localStorage.setItem(THEME_STORAGE_KEY,selected);
  button.addEventListener('click',()=>{
    selected=selected==='paper'?'midnight':'paper';localStorage.setItem(THEME_STORAGE_KEY,selected);applyTheme(selected);describe();
  });
}
function installDataTips(){
  const tip=document.createElement('div');tip.id='dataTipPopover';tip.className='data-tip-popover';tip.hidden=true;tip.setAttribute('role','tooltip');document.body.append(tip);let active=null;
  const show=target=>{if(!target?.dataset.tip)return;active=target;tip.textContent=target.dataset.tip;tip.hidden=false;target.setAttribute('aria-describedby',tip.id);requestAnimationFrame(()=>{const rect=target.getBoundingClientRect(),box=tip.getBoundingClientRect(),left=Math.min(innerWidth-box.width-8,Math.max(8,rect.left+(rect.width-box.width)/2)),above=rect.top-box.height-10;tip.style.left=`${left}px`;tip.style.top=`${above>=8?above:Math.min(innerHeight-box.height-8,rect.bottom+10)}px`})};
  const hide=()=>{active?.removeAttribute('aria-describedby');active=null;tip.hidden=true};
  document.addEventListener('mouseover',event=>{const target=event.target.closest?.('[data-tip]');if(target&&target!==active)show(target)});
  document.addEventListener('mouseout',event=>{if(active&&!active.contains(event.relatedTarget))hide()});
  document.addEventListener('focusin',event=>{const target=event.target.closest?.('[data-tip]');if(target)show(target)});
  document.addEventListener('focusout',event=>{if(active&&!active.contains(event.relatedTarget))hide()});
  addEventListener('scroll',hide,{passive:true,capture:true});addEventListener('resize',hide,{passive:true});
}
function installUi(){installThemeToggle();installDataTips()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',installUi);else installUi();
