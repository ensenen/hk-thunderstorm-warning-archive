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
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',installThemeToggle);else installThemeToggle();
