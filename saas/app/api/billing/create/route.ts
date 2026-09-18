import {NextResponse} from "next/server";
import Razorpay from "razorpay";
import {supabaseServer} from "../../../../lib/supabase-server";
import {supabaseAdmin} from "../../../../lib/supabase-admin";
export async function POST(){
 const auth=await supabaseServer(); const {data:{user}}=await auth.auth.getUser();
 if(!user)return NextResponse.json({error:"Login required"},{status:401});
 if(!process.env.RAZORPAY_KEY_ID||!process.env.RAZORPAY_KEY_SECRET||!process.env.RAZORPAY_PLAN_ID)return NextResponse.json({error:"Razorpay is not configured"},{status:503});
 const rzp=new Razorpay({key_id:process.env.RAZORPAY_KEY_ID,key_secret:process.env.RAZORPAY_KEY_SECRET});
 try{
  const sub=await rzp.subscriptions.create({plan_id:process.env.RAZORPAY_PLAN_ID,total_count:12,customer_notify:1,quantity:1});
  const db=supabaseAdmin();
  await db.from("clipilot_profiles").upsert({user_id:user.id,email:user.email||null});
  await db.from("clipilot_settings").upsert({user_id:user.id});
  await db.from("clipilot_subscriptions").upsert({user_id:user.id,razorpay_subscription_id:sub.id,razorpay_plan_id:process.env.RAZORPAY_PLAN_ID,status:sub.status||"created",total_count:sub.total_count||12},{onConflict:"razorpay_subscription_id"});
  return NextResponse.json({subscription_id:sub.id,checkout_url:(sub as any).short_url});
 }catch(e){return NextResponse.json({error:e instanceof Error?e.message:"Razorpay error"},{status:502});}
}