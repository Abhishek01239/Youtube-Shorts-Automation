import {NextResponse} from "next/server";
import crypto from "crypto";
import {supabaseAdmin} from "../../../../lib/supabase-admin";
export async function POST(req:Request){
 const raw=await req.text(), sig=req.headers.get("x-razorpay-signature")||"", secret=process.env.RAZORPAY_WEBHOOK_SECRET||"";
 if(!secret)return NextResponse.json({error:"Webhook secret not configured"},{status:503});
 const expected=crypto.createHmac("sha256",secret).update(raw).digest("hex");
 if(sig.length!==expected.length||!crypto.timingSafeEqual(Buffer.from(expected),Buffer.from(sig)))return NextResponse.json({error:"Invalid signature"},{status:401});
 const event=JSON.parse(raw), entity=event?.payload?.subscription?.entity;
 if(!entity?.id)return NextResponse.json({ok:true});
 const db=supabaseAdmin();
 const row=await db.from("clipilot_subscriptions").select("user_id").eq("razorpay_subscription_id",entity.id).single();
 const status=entity.status, paidCount=Number(entity.paid_count||0), periodEnd=entity.current_end?new Date(entity.current_end*1000).toISOString():null;
 await db.from("clipilot_subscriptions").update({status,paid_count:paidCount,current_period_end:periodEnd,updated_at:new Date().toISOString()}).eq("razorpay_subscription_id",entity.id);
 if(row.data?.user_id && ["active","authenticated"].includes(status))await db.from("clipilot_settings").update({enabled:true,updated_at:new Date().toISOString()}).eq("user_id",row.data.user_id);
 if(row.data?.user_id && ["cancelled","expired","halted"].includes(status))await db.from("clipilot_settings").update({enabled:false,updated_at:new Date().toISOString()}).eq("user_id",row.data.user_id);
 return NextResponse.json({ok:true});
}