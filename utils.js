export const $=s=>document.querySelector(s);
export const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const num=n=>n==null?'—':Number(n).toLocaleString('en-US',{maximumFractionDigits:0});
export const money=(n,c='USD')=>n==null?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:c,maximumFractionDigits:0}).format(n);
export const pct=n=>n==null?'—':(n*100).toFixed(1)+'%';
export const compact=n=>n==null?'—':n>=1e6?(n/1e6).toFixed(2)+'m':n>=1e4?(n/1e3).toFixed(1)+'k':num(n);
export const ratio=(a,b)=>b?a/b:null;
export const diff=(a,b)=>b?a/b-1:null;
export const dateAdd=(day,n)=>{let d=new Date(day+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10)};
export const pill=(s,style='')=>`<span class="pill ${style}">${esc(s)}</span>`;
export const button=(title,page,extra={})=>`<button type="button" class="text-button" data-go="${page}" ${Object.entries(extra).map(([k,v])=>`data-${k}="${esc(v)}"`).join(' ')}>${esc(title)}</button>`;
export const person=(c)=>`<div class="cell-person"><span class="avatar">${esc(c.name.slice(0,1))}</span><span>${esc(c.name)}<small>@${esc(c.handle||c.id)}</small></span></div>`;
export function toast(message){$('#toast').textContent=message;$('#toast').style.display='block';clearTimeout(window.toastTimeout);window.toastTimeout=setTimeout(()=>$('#toast').style.display='none',4500)}
export const head=(n,title,right='')=>`<div class="section-head"><h2><span class="section-no">${n}</span>${title}</h2>${right}</div>`;
export const panel=(n,title,body,right='')=>`<section class="panel">${head(n,title,right)}${body}</section>`;
export function kpi(label,value,note='',index=''){return `<div class="kpi"><div class="kpi-label">${label}<span>${index}</span></div><div class="metric">${value}</div><div class="kpi-note">${note}</div></div>`}
export function delta(a,b,valid=true){let d=diff(a,b);return !valid?'基期或本期数据不完整':d==null?'基期不足':`<span class="${d<0?'negative':'positive'}">${d<0?'↘':'↗'} ${pct(Math.abs(d))}</span> 较前一等长周期`}
export function download(name,data){let blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),500)}
export function safeLink(url,label='查看原文 ↗'){return url&&/^https?:\/\//.test(url)?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`:'<span class="muted">未提供链接</span>'}
