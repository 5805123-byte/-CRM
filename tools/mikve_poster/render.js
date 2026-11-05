const { chromium } = require('playwright');const path=require('path');
// הרצה: node tools/mikve_poster/render.js tools/mikve_poster out.pdf  → גיליון A2 אחד
const dir=path.resolve(process.argv[2]), out=path.resolve(process.argv[3]);
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:794,height:1123}});
 await p.goto('file://'+path.join(dir,'poster.html'));await p.evaluate(()=>document.fonts.ready);await p.waitForTimeout(300);
 const m=await p.evaluate(()=>{const c=document.getElementById('c'),n=document.getElementById('in');return {zoom:document.body.dataset.zoom,inH:n.getBoundingClientRect().height,ch:c.clientHeight,sw:n.scrollWidth,cw:n.clientWidth,
   fonts:[...document.fonts].filter(f=>f.status==='loaded').length}});
 console.log(JSON.stringify(m));
 await p.screenshot({path:path.join(dir,'shot.png'),fullPage:true});
 // אחרי ההתאמה ב-A4 — מגדילים פי 2 לגיליון A2 (וקטורי, בלי איבוד חדות)
 await p.evaluate(()=>{const st=document.createElement('style');st.textContent='@page{size:420mm 594mm;margin:0}.page{zoom:2}';document.head.appendChild(st);});
 await p.waitForTimeout(200);
 await p.pdf({path:out,printBackground:true,preferCSSPageSize:true,pageRanges:'1',margin:{top:0,right:0,bottom:0,left:0}});
 await b.close();})();
