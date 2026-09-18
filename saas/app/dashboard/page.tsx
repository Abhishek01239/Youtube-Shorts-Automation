"use client";
import {useSearchParams} from "next/navigation";
export default function Dashboard(){
 const q=useSearchParams(); const twitch=q.get("twitch")==="connected"; const youtube=q.get("youtube")==="connected";
 const cards=[["Automation","OFF"],["Twitch",twitch?"Connected":"Not connected"],["YouTube",youtube?"Connected":"Not connected"],["Plan","₹99 / month"]];
 return <main style={{minHeight:"100vh",padding:"40px 7%",background:"#070914"}}><h1>ClipPilot Dashboard</h1><p style={{opacity:.7}}>Your Twitch → YouTube Shorts control center.</p>
 <div style={{display:"flex",gap:12,flexWrap:"wrap",margin:"24px 0"}}><a href="/api/auth/twitch" style={{padding:"12px 18px",borderRadius:10,background:"#9146ff",color:"#fff",textDecoration:"none"}}>Connect Twitch</a><a href="/api/auth/youtube" style={{padding:"12px 18px",borderRadius:10,background:"#ff0033",color:"#fff",textDecoration:"none"}}>Connect YouTube</a></div>
 <section style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))",gap:16,marginTop:30}}>{cards.map(([a,b])=><div key={a} style={{padding:24,border:"1px solid #252a45",borderRadius:16,background:"#0d1020"}}><small style={{opacity:.6}}>{a}</small><h2>{b}</h2></div>)}</section>
 <div style={{marginTop:30,padding:24,borderRadius:16,background:"#10152b"}}><h2>Automation pipeline</h2><p>Discover Twitch moments → download → highlight detection → 9:16 processing → metadata → YouTube upload.</p><p style={{opacity:.65}}>The existing Python pipeline in this repository is the processing engine. The SaaS layer handles customer onboarding, billing and connections.</p></div></main>
}