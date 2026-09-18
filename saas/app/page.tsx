"use client";
import {useState} from "react";
export default function Home(){
 const [busy,setBusy]=useState(false);
 async function checkout(){
  setBusy(true);
  const r=await fetch("/api/billing/create",{method:"POST"}); const d=await r.json();
  if(d.checkout_url) window.location.href=d.checkout_url; else alert(d.error||"Billing is not configured yet.");
  setBusy(false);
 }
 return <main style={{minHeight:"100vh",background:"radial-gradient(circle at 75% 15%,#4c1d95 0,#070914 38%)"}}>
  <nav style={{display:"flex",justifyContent:"space-between",padding:"24px 7%",alignItems:"center"}}><b style={{fontSize:24}}>⚡ ClipPilot</b><span style={{opacity:.7}}>Twitch → YouTube Shorts</span></nav>
  <section style={{maxWidth:1050,margin:"60px auto",padding:"0 24px",textAlign:"center"}}>
   <div style={{display:"inline-block",padding:"8px 14px",borderRadius:30,background:"#151a31",color:"#c4b5fd"}}>24/7 AUTOMATION</div>
   <h1 style={{fontSize:"clamp(42px,7vw,78px)",lineHeight:1,margin:"22px 0"}}>Turn Twitch streams into Shorts automatically.</h1>
   <p style={{fontSize:20,lineHeight:1.6,opacity:.75,maxWidth:720,margin:"0 auto 30px"}}>Find moments, clip, format 9:16, caption, generate metadata and publish to YouTube — without daily editing.</p>
   <button onClick={checkout} disabled={busy} style={{padding:"16px 28px",border:0,borderRadius:12,fontSize:18,fontWeight:800,cursor:"pointer",background:"#ff6a00",color:"#fff"}}>{busy?"Opening checkout…":"Start automation — ₹99/month"}</button>
   <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))",gap:14,marginTop:60,textAlign:"left"}}>
    {["Twitch connection","AI highlight pipeline","9:16 + captions","YouTube auto-upload","Scheduling & history","Razorpay billing"].map(x=><div key={x} style={{padding:20,border:"1px solid #252a45",borderRadius:16,background:"#0d1020"}}>✓ {x}</div>)}
   </div>
  </section>
 </main>
}