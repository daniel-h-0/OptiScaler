/* SPDX-License-Identifier: MIT
 * Tests the frame-start pacing controller (xell_pace_ctl.h) against the pipeline model of
 * research/pacing/xell_pace_sim.py: the game runs C ms of CPU work, then Present blocks until a queue slot frees
 * (depth 2, freed in pairs: the 3x bunching), the GPU consumes frames in order G ms each, and XeLL either does not
 * sleep or sleeps the game into just-in-time submission.
 * Build: gcc -O1 -g -fsanitize=address,undefined tests/test_xell_pace.c -o test_xell_pace -lm
 */
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include "../OptiScaler/low_latency/low_latency_tech/xell_pace_ctl.h"
#define N 900
static unsigned long long rng=88172645463325252ULL;
static double urand(void){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return (rng>>11)*(1.0/9007199254740992.0);}
static double gauss(void){double u=urand(),v=urand();if(u<1e-12)u=1e-12;return sqrt(-2*log(u))*cos(6.283185307179586*v);}
typedef double(*fn)(int);
static double start[N];
static double g_const,c_const,c_noise,g_drop_at,g_after,c_spike_at,c_spike;
static double G(int k){return g_drop_at>0&&k>=g_drop_at?g_after:g_const;}
static double C(int k){if(c_spike_at>0&&k==c_spike_at)return c_spike;double c=c_const*(1+c_noise*gauss());return c<1?1:c;}
/* Returns the number of held frames. */
static int run(int paced,int xell_working){
 struct xpc ctl;xpc_init(&ctl,0.85,0.95);double end_gpu[N],last_ret=0,e_prev=0,prev_block=-1;int held=0;
 for(int k=0;k<N;k++){
  double call=last_ret,xs=0;
  if(xell_working==1&&k>=2){double want=end_gpu[k-1]-C(k)*0.9;if(want>call)xs=want-call;}
  if(xell_working==2)xs=k%2?0:1.2;  /* XeLL engaged but ineffective: short sleeps on alternate frames (seen in Cyberpunk) */
  double now=call+xs,w=paced?xpc_wait(&ctl,now,xs,prev_block):0;if(w>0)held++;
  double s=now+w;if(paced)xpc_started(&ctl,s);start[k]=s;
  double submit=s+C(k),e=(e_prev>submit?e_prev:submit)+G(k);e_prev=e;end_gpu[k]=e;
  int fk=k-2;double slot=0;
  if(fk>=0)slot=(fk%2==0&&fk+1<=k-1)?end_gpu[fk+1]:end_gpu[fk];
  double ret=submit+1.5>slot?submit+1.5:slot;prev_block=ret-submit;last_ret=ret;
 }
 return held;
}
static double mean_iv(int a,int b){return (start[b]-start[a])/(b-a);}
static double imbalanced(int a,int b){int n=0,t=0;for(int k=a+2;k<b;k++){double d1=start[k-1]-start[k-2],d2=start[k]-start[k-1];t++;if(fabs(d2-d1)/(d1+d2)>0.3)n++;}return (double)n/t;}
static int fails;
static void check(int ok,const char*what,double got,double want){printf("%s %-58s got %.3f want %.3f\n",ok?"ok  ":"FAIL",what,got,want);if(!ok)fails++;}
static void reset(void){g_const=37.5;c_const=13;c_noise=0;g_drop_at=0;g_after=0;c_spike_at=0;c_spike=0;rng=88172645463325252ULL;}
int main(void){
 /* 3x bunching, XeLL not sleeping: unpaced alternates, paced is even at the same rate. */
 double depths[]={5,13,20,26};
 for(int i=0;i<4;i++){
  reset();c_const=depths[i];run(0,0);double base=mean_iv(100,N-1),bi=imbalanced(100,N-1);
  reset();c_const=depths[i];run(1,0);double m=mean_iv(100,N-1),im=imbalanced(100,N-1);char what[96];
  snprintf(what,sizeof what,"bunching CPU %.0f ms: unpaced imbalanced share",depths[i]);if(i<3)check(bi>0.9,what,bi,1);
  snprintf(what,sizeof what,"bunching CPU %.0f ms: paced imbalanced share",depths[i]);check(im<0.02,what,im,0);
  snprintf(what,sizeof what,"bunching CPU %.0f ms: paced rate within 0.5%%",depths[i]);check(fabs(m/base-1)<0.005,what,m,base);
 }
 /* XeLL pacing correctly: never hold. */
 reset();{int h=run(1,1);check(h==0,"XeLL working: frames held",h,0);}
 /* XeLL sleeping ~1 ms on alternate frames without evening them: frames it left early are topped up too. */
 reset();run(0,2);{double b=mean_iv(100,N-1),bi=imbalanced(100,N-1);reset();run(1,2);double m=mean_iv(100,N-1),im=imbalanced(100,N-1);
  check(bi>0.9,"XeLL short sleeps: unpaced imbalanced share",bi,1);check(im<0.02,"XeLL short sleeps: paced imbalanced share",im,0);
  check(fabs(m/b-1)<0.005,"XeLL short sleeps: paced rate within 0.5%",m,b);}
 /* CPU-bound noise and a fast noisy menu: throughput cost small. */
 reset();g_const=20;c_const=30;c_noise=0.2;run(0,0);{double b=mean_iv(100,N-1);reset();g_const=20;c_const=30;c_noise=0.2;run(1,0);double m=mean_iv(100,N-1);check(m/b-1<0.01,"CPU-bound 30 ms +-20%: interval cost",m/b-1,0);}
 reset();g_const=6;c_const=6;c_noise=0.3;run(0,0);{double b=mean_iv(100,N-1);reset();g_const=6;c_const=6;c_noise=0.3;run(1,0);double m=mean_iv(100,N-1);check(m/b-1<0.05,"menu 6/6 ms +-30%: interval cost",m/b-1,0);}
 /* Load drop 50 -> 30 ms: back to the new rate within 40 frames. */
 reset();g_const=50;g_drop_at=300;g_after=30;run(1,0);{double m=mean_iv(340,400);check(fabs(m-30)<0.6,"load drop 50->30: frames 340-400 interval",m,30);}
 /* A 200 ms hitch and a 400 ms loading gap: no lasting slowdown. */
 reset();c_spike_at=300;c_spike=200;run(1,0);{double m=mean_iv(340,400);check(fabs(m-37.5)<0.5,"200 ms hitch: frames 340-400 interval",m,37.5);}
 reset();c_spike_at=300;c_spike=400;run(1,0);{double m=mean_iv(310,340),m2=mean_iv(340,400),im=imbalanced(340,N-1);check(m<39,"400 ms gap: frames 310-340 interval",m,37.5);check(fabs(m2-37.5)<0.5,"400 ms gap: frames 340-400 interval",m2,37.5);check(im<0.02,"400 ms gap: bunching removed again",im,0);}
 /* A burst of stalls followed by faster work, with variable Present waits from a second output scheduler.
  * The waits do not justify preserving a stale slow rate. Do not carry the stall burst into the following game frames. */
 {struct xpc ctl;xpc_init(&ctl,0.85,0.95);double t=1000,last_interval=0;
  for(int i=0;i<60;i++){
   double natural=i<32?(i%2?35:15):i<35?(i==32?100:i==33?80:60):20;
   double w=xpc_wait(&ctl,t+natural,0,i%2?2:5);t+=natural+w;xpc_started(&ctl,t);
   if(i>=35)last_interval=fmax(last_interval,natural+w);
  }
  check(last_interval<=20.1,"stall burst + variable Present: recover natural 20 ms",last_interval,20);
 }
 printf(fails?"FAIL %d\n":"PASS\n",fails);return fails!=0;
}
