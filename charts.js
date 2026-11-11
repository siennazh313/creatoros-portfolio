import {esc,num,compact} from './utils.js';
export function chart(series,label='播放／浏览',grain='day'){
 if(!series.length||series.every(x=>x.missing))return '<div class="empty">该周期暂无观测数据</div>';
 const W=680,H=185,L=48,R=15,T=18,B=23,iw=W-L-R,ih=H-T-B,max=Math.max(...series.map(r=>r.views),1)*1.15;
 const xy=(r,i)=>[L+i*iw/Math.max(series.length-1,1),T+ih-(r.views/max)*ih];
 let segments=[],seg=[];series.forEach((r,i)=>{if(r.missing){if(seg.length)segments.push(seg);seg=[]}else seg.push({r,i})});if(seg.length)segments.push(seg);
 let paths=segments.map(seg=>{let points=seg.map(({r,i})=>xy(r,i).join(',')).join(' ');let start=xy(seg[0].r,seg[0].i)[0],end=xy(seg.at(-1).r,seg.at(-1).i)[0];return `<polygon points="${start},${H-B} ${points} ${end},${H-B}" fill="#e9efdf"/><polyline points="${points}" fill="none" stroke="#6d875d" stroke-width="2" vector-effect="non-scaling-stroke"/>`}).join('');
 return `<div class="legend"><span><i></i>${esc(label)}</span><span>单位：次</span></div><svg class="trend" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}趋势">${[0,.33,.66,1].map(v=>{let y=T+ih-v*ih;return `<line x1="${L}" y1="${y}" x2="${W-R}" y2="${y}" stroke="#e9ecdf" stroke-dasharray="3 4"/><text x="0" y="${y+4}">${compact(v*max)}</text>`}).join('')}${paths}${series.filter(x=>!x.missing).map(r=>{let i=series.indexOf(r),[x,y]=xy(r,i);return `<circle cx="${x}" cy="${y}" r="3" fill="#6d875d" tabindex="0"><title>${esc(r.date)}${r.partial?' · 周期未完整覆盖':''}：${num(r.views)} 次；发布 ${num(r.posts)} 篇</title></circle>`}).join('')}<text x="${L}" y="${H-2}">${esc(series[0].date.slice(5))}</text><text x="${W-R}" y="${H-2}" text-anchor="end">${esc(series.at(-1).date.slice(5))}</text></svg><div class="chart-caption"><span>${grain==='day'?'日度':grain==='week'?'自然周 · 周一开始':'自然月'}观测</span><span>${series.some(r=>r.partial)?'边界周期未完整覆盖 · ':''}缺失日期断线显示</span></div>`
}
export function countriesBars(countries,metric='contribution'){
 const sorted=[...countries].sort((a,b)=>Math.abs(b[metric])-Math.abs(a[metric])),max=Math.max(...sorted.map(r=>Math.abs(r[metric])),1);
 return sorted.map(r=>`<div class="country-row"><div class="row"><button class="text-button country-name" data-go="countries" data-country="${esc(r.country)}"><span class="country-code">${esc(r.country)}</span>${esc(r.name)}</button><span class="${r[metric]<0?'negative':'positive'}">${r[metric]>0?'+':''}${num(r[metric])}</span></div><div class="bartrack"><i class="${r[metric]<0?'down':''}" style="width:${Math.abs(r[metric])/max*100}%"></i></div></div>`).join('')||'<div class="empty">暂无国家数据</div>';
}
