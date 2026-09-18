import {NextResponse} from "next/server";
import Razorpay from "razorpay";
export async function POST(){
 if(!process.env.RAZORPAY_KEY_ID||!process.env.RAZORPAY_KEY_SECRET||!process.env.RAZORPAY_PLAN_ID)
  return NextResponse.json({error:"Razorpay is not configured. Add RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET and RAZORPAY_PLAN_ID."},{status:503});
 const rzp=new Razorpay({key_id:process.env.RAZORPAY_KEY_ID,key_secret:process.env.RAZORPAY_KEY_SECRET});
 try{
  const sub=await rzp.subscriptions.create({plan_id:process.env.RAZORPAY_PLAN_ID,total_count:12,customer_notify:1,quantity:1});
  return NextResponse.json({subscription_id:sub.id,checkout_url:(sub as any).short_url});
 }catch(e){return NextResponse.json({error:e instanceof Error?e.message:"Razorpay error"},{status:502});}
}