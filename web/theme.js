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
function installThemePicker(){
  const saved=localStorage.getItem(THEME_STORAGE_KEY)||'';
  const selected=applyTheme(saved);
  const label=document.createElement('label');
  label.className='theme-picker';
  label.innerHTML=`<span aria-hidden="true">◐</span><span class="theme-picker-label">配色</span><select aria-label="網站配色">${THEME_OPTIONS.map(([id,name])=>`<option value="${id}" ${id===selected?'selected':''}>${name}</option>`).join('')}</select>`;
  document.body.append(label);
  localStorage.setItem(THEME_STORAGE_KEY,selected);
  label.querySelector('select').addEventListener('change',event=>{
    localStorage.setItem(THEME_STORAGE_KEY,event.target.value);
    applyTheme(event.target.value);
  });
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',installThemePicker);else installThemePicker();
