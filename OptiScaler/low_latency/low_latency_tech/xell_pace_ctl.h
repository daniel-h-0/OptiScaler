/* SPDX-License-Identifier: MIT
 * Frame-start pacing controller, platform-free (ported from FreeFG; used by freefg_frame_pacer.h; tested by tests/test_xell_pace.c). Times are milliseconds on one monotonic clock.
 *
 * Problem: when XeLL's sleep does not engage, the game runs ahead into Present, which under multi-frame generation
 * returns alternately at once and after ~2 frames; frame starts then bunch in pairs (e.g. 15/60 ms) and the real
 * frames' motion alternates with them. The controller only acts on that signature:
 * - it engages after the last 16 start intervals alternate (lag-1 autocorrelation <= -0.5 with mean pair imbalance
 *   >= 0.2), so noisy CPU-bound frame times are left alone;
 * - while engaged, a frame whose natural interval (time since the previous start, after XeLL's own sleep) is below
 *   0.85 x the period is held to 0.95 x the period; the period is the trimmed mean of the last 16 intervals;
 * - XeLL's own sleep is part of the natural interval: a frame XeLL already brought to the period is not held, and one it
 *   left early (short sleeps on alternate frames were seen in Cyberpunk) is topped up to the same target, never beyond;
 * - a gap over 250 ms (loading, pause), or over 2.5 learned periods with a 50 ms floor, restarts the history
 *   without recording the gap; a gameplay hitch must not become a slower target period;
 * - 8 holds in a row means the pacer is following its own delay (load dropped or a burst of stalls):
 *   restart from natural intervals even when Present has variable waits; those waits are not GPU-throughput evidence
 *   when another output pacer is active;
 * - after 64 frames without a hold it disengages until the alternation is seen again.
 */
#include <string.h>
#define XPC_HIST 16
struct xpc{
 double last,iv[XPC_HIST],low,factor;
 unsigned n,held_run,idle;int on;
};
static void xpc_init(struct xpc*c,double low,double factor){memset(c,0,sizeof(*c));c->last=-1;c->low=low;c->factor=factor;}
static void xpc_restart(struct xpc*c,double now){c->n=0;c->held_run=0;c->idle=0;c->on=0;c->last=now;}
/* The last k intervals in chronological order into out; returns k (<= stored). */
static unsigned xpc_recent(const struct xpc*c,double*out,unsigned k){
 unsigned have=c->n<XPC_HIST?c->n:XPC_HIST;if(k>have)k=have;
 for(unsigned i=0;i<k;i++)out[i]=c->iv[(c->n-k+i)%XPC_HIST];
 return k;
}
static double xpc_period(const struct xpc*c){
 double v[XPC_HIST];unsigned k=xpc_recent(c,v,XPC_HIST),lo=0,hi=k;
 for(unsigned i=1;i<k;i++){double x=v[i];unsigned j=i;while(j&&v[j-1]>x){v[j]=v[j-1];j--;}v[j]=x;}
 if(k>=12){lo=2;hi=k-2;}double s=0;for(unsigned i=lo;i<hi;i++)s+=v[i];return hi>lo?s/(hi-lo):0;
}
static int xpc_alternating(const struct xpc*c){
 double v[XPC_HIST];unsigned k=xpc_recent(c,v,XPC_HIST);if(k<XPC_HIST)return 0;
 double m=0;for(unsigned i=0;i<k;i++)m+=v[i];m/=k;double var=0,cov=0,imb=0;
 for(unsigned i=0;i<k;i++)var+=(v[i]-m)*(v[i]-m);
 for(unsigned i=1;i<k;i++){cov+=(v[i]-m)*(v[i-1]-m);double s=v[i]+v[i-1];imb+=s>0?(v[i]>v[i-1]?v[i]-v[i-1]:v[i-1]-v[i])/s:0;}
 if(var<=0)return 0;
 return cov/(k-1)/(var/k)<=-0.5&&imb/(k-1)>=0.2;
}
/* now: when the game reached its frame start after XeLL's own sleep; xell_slept: how long that sleep took (unused by
 * the decision since q29: XeLL's sleep is inside `now`, and the wait only tops the interval up to the target, so it
 * never stacks on it); prev_block is retained for the original simulation harness, but no longer used. Returns the wait; the
 * caller then reports the actual start with xpc_started(). */
static double xpc_wait(struct xpc*c,double now,double xell_slept,double prev_block){
 (void)xell_slept;(void)prev_block;
 if(c->last<0){c->last=now;return 0;}
 double gap=now-c->last,stall=250;
 if(c->n>=8){double relative=2.5*xpc_period(c);if(relative<50)relative=50;if(relative<stall)stall=relative;}
 if(gap>stall){xpc_restart(c,now);return 0;}
 if(!c->on&&xpc_alternating(c)){c->on=1;c->idle=0;}
 double w=0;
 if(c->on&&c->n>=8){
  double p=xpc_period(c),nat=now-c->last;
  if(nat<c->low*p){w=c->last+c->factor*p-now;if(w>100)w=100;if(w<0)w=0;}
 }
 if(w>0){c->held_run++;c->idle=0;}else{c->held_run=0;c->idle++;}
 if(c->on&&c->idle>=64)c->on=0;
 if(c->held_run>=8){xpc_restart(c,now);return 0;}
 return w;
}
static void xpc_started(struct xpc*c,double start){if(c->last>=0&&start>c->last){c->iv[c->n%XPC_HIST]=start-c->last;c->n++;}c->last=start;}
