const THEME_STORAGE_KEY='thunder-archive-theme';
const THEME_OPTIONS=[
  ['system','跟隨系統'],
  ['storm','雷雨夜空 · 深色'],
  ['midnight','天文台午夜 · 深色'],
  ['radar','雷達綠光 · 深色'],
  ['cloud','雲層日光 · 淺色'],
  ['paper','琥珀天氣稿 · 淺色'],
];
const LIGHT_THEMES=new Set(['cloud','paper']);
const systemDark=()=>matchMedia('(prefers-color-scheme: dark)').matches;
function applyTheme(preference){
  const valid=THEME_OPTIONS.some(([id])=>id===preference)?preference:'system';
  const resolved=valid==='system'?(systemDark()?'storm':'cloud'):valid;
  document.documentElement.dataset.theme=resolved;
  document.documentElement.dataset.mode=LIGHT_THEMES.has(resolved)?'light':'dark';
  document.documentElement.style.colorScheme=LIGHT_THEMES.has(resolved)?'light':'dark';
  const colours={storm:'#080713',midnight:'#050b18',radar:'#04110e',cloud:'#f4f7fb',paper:'#f8f1e3'};
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content',colours[resolved]);
  return valid;
}
function installThemePicker(){
  const saved=localStorage.getItem(THEME_STORAGE_KEY)||'system';
  const selected=applyTheme(saved);
  const label=document.createElement('label');
  label.className='theme-picker';
  label.innerHTML=`<span aria-hidden="true">◐</span><span class="theme-picker-label">配色</span><select aria-label="網站配色">${THEME_OPTIONS.map(([id,name])=>`<option value="${id}" ${id===selected?'selected':''}>${name}</option>`).join('')}</select>`;
  document.body.append(label);
  label.querySelector('select').addEventListener('change',event=>{
    localStorage.setItem(THEME_STORAGE_KEY,event.target.value);
    applyTheme(event.target.value);
  });
}
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',()=>{
  if((localStorage.getItem(THEME_STORAGE_KEY)||'system')==='system')applyTheme('system');
});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',installThemePicker);else installThemePicker();
