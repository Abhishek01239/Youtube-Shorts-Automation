import Link from "next/link";
import {supabaseServer} from "../../lib/supabase-server";
export default async function Dashboard(){
 const s=await supabaseServer(); const {data:{user}}=await s.auth.getUser();
 const {data:connections}=await s.from("clipilot_connections").select("provider,provider_channel_name").eq("user_id",user?.id||"");
 const {data:subs}=await s.from("clipilot_subscriptions").select("status,current_period_end").eq("user_id",user?.id||"").order("created_at",{ascending:false}).limit(1);
 const {data:settings}=await s.from("clipilot_settings").select("enabled,shorts_per_run,interval_hours").eq("user_id",user?.id||"").single();
 const has=(p:string)=>connections?.some(x=>x.provider===p);
 const cards=[["Automation",settings?.enabled?"ON":"OFF"],["Twitch",has("twitch")?"Connected":"Not connected"],["YouTube",has("youtube")?"Connected":"Not connected"],["Plan",subs?.[0]?.status==="active"?"₹99 / month":"Not active"]];
 return <main style={{minHeight:"100vh",padding:"40px 7%",background:"#070914",color:"#fff"}}><div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><div><h1>ClipPilot Dashboard</h1><p style={{opacity:.7}}>{user?.email}</p></div><Link href="/" style={{color:"#c4b5fd"}}>Home</Link></div>
 <div style={{display:"flex",gap:12,flexWrap:"wrap",margin:"24px 0"}}><a href="/api/auth/twitch" style={{padding:"12px 18px",borderRadius:10,background:"#9146ff",color:"#fff",textDecoration:"none"}}>{has("twitch")?"Reconnect Twitch":"Connect Twitch"}</a><a href="/api/auth/youtube" style={{padding:"12px 18px",borderRadius:10,background:"#ff0033",color:"#fff",textDecoration:"none"}}>{has("youtube")?"Reconnect YouTube":"Connect YouTube"}</a><form action="/api/billing/create" method="post"><button style={{padding:"12px 18px",border:0,borderRadius:10,background:"#ff6a00",color:"#fff",fontWeight:800}}>Start ₹99/month</button></form></div>
 <section style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))",gap:16,marginTop:30}}>{cards.map(([a,b])=><div key={a} style={{padding:24,border:"1px solid #252a45",borderRadius:16,background:"#0d1020"}}><small style={{opacity:.6}}>{a}</small><h2>{b}</h2></div>)}</section>
 <div style={{marginTop:30,padding:24,borderRadius:16,background:"#10152b"}}><h2>Automation settings</h2><p>{settings?.shorts_per_run||3} Shorts per run • every {settings?.interval_hours||8} hours</p><p style={{opacity:.65}}>Pipeline: Twitch discovery → highlight detection → 9:16 processing → metadata → YouTube upload.</p></div></main>
}