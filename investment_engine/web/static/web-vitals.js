"use strict";

// Módulo independente e opcional: falhas ou APIs ausentes nunca bloqueiam a
// navegação. Apenas o resumo atual é lido pelo app e agregado por hora no servidor.
const values={lcp_ms:null,inp_ms:null,cls:null};

function observe(type,callback,options={}){
  try{
    if(!("PerformanceObserver" in window))return;
    const supported=PerformanceObserver.supportedEntryTypes||[];
    if(!supported.includes(type))return;
    const observer=new PerformanceObserver(list=>callback(list.getEntries()));
    observer.observe({type,buffered:true,...options});
  }catch(_){/* medição opcional em navegadores antigos */}
}

observe("largest-contentful-paint",entries=>{
  const last=entries[entries.length-1];if(last)values.lcp_ms=Math.round(last.startTime*100)/100;
});

let cumulativeLayoutShift=0;
observe("layout-shift",entries=>{
  for(const entry of entries)if(!entry.hadRecentInput)cumulativeLayoutShift+=Number(entry.value||0);
  values.cls=Math.round(cumulativeLayoutShift*10000)/10000;
});

observe("event",entries=>{
  for(const entry of entries){
    const duration=Number(entry.duration||0);
    if(duration>Number(values.inp_ms||0))values.inp_ms=Math.round(duration*100)/100;
  }
},{durationThreshold:40});

window.FDIWebVitals={
  snapshot(){return {...values};},
};
