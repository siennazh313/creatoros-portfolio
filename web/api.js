export async function api(path,body,signal){let r=await fetch('/api/'+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal}:{signal});let data=await r.json();if(!r.ok)throw Error(data.error||'请求失败');return data}

export async function publicDataset(){return api("analysis-dataset")}
