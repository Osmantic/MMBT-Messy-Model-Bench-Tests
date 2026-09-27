"""Deterministic common fan curve, bounded transitions, no hardware access."""
import math
from common import real
DEFAULT_CURVE=((40,30),(50,40),(60,55),(70,65),(75,72),(78,78),(80,80),(81,83),(82,86),(84,92),(85,95),(88,100))
def validate_curve(curve):
    if type(curve) not in (list,tuple) or not 2<=len(curve)<=32:raise ValueError('Invalid curve size')
    out=[]
    for pair in curve:
        if type(pair) not in (list,tuple) or len(pair)!=2:raise ValueError('Invalid curve point')
        c=real(pair[0],0,88);p=pair[1]
        if type(p) is not int or not 30<=p<=100:raise ValueError('Invalid fan percentage')
        if out and (c<=out[-1][0] or p<out[-1][1]):raise ValueError('Curve must be monotonic')
        out.append((c,p))
    if out[-1]!=(88,100):raise ValueError('Emergency endpoint must be88C/100%')
    return tuple(out)
def settings(raw):
    if type(raw) is not dict or set(raw)-{'power_limit_w','mode','fixed_percent','curve','startup_floor','startup_seconds'}:raise ValueError('Unknown settings')
    if type(raw.get('power_limit_w')) is not int or raw['power_limit_w']!=275:raise ValueError('Cap must be275W')
    mode=raw.get('mode')
    if mode=='fixed':
        if set(raw)!={'power_limit_w','mode','fixed_percent'} or type(raw['fixed_percent']) is not int or not 30<=raw['fixed_percent']<=100:raise ValueError('Invalid fixed settings')
        return dict(raw)
    if mode!='curve' or 'fixed_percent' in raw:raise ValueError('Invalid fan mode')
    floor=raw.get('startup_floor',80);seconds=raw.get('startup_seconds',30)
    if type(floor) is not int or not 65<=floor<=85 or type(seconds) is not int or not 5<=seconds<=60:raise ValueError('Invalid startup settings')
    return {'power_limit_w':275,'mode':'curve','curve':validate_curve(raw.get('curve',DEFAULT_CURVE)),'startup_floor':floor,'startup_seconds':seconds}
class Policy:
    def __init__(self,uuids,config):
        if len(uuids)!=4 or len(set(uuids))!=4 or any(type(u) is not str or not u for u in uuids):raise ValueError('Four exact identities required')
        self.ids=frozenset(uuids);self.config=settings(config);self.target=self.config.get('fixed_percent',80)
        self.last=self.filtered=self.idle_since=self.idle_step=self.cool_since=self.cool_step=self.startup_until=None
        self.load_armed=True;self.quiet_since=None;self.credit=0
    def demand(self,core):
        real(core,0,120)
        if self.config['mode']=='fixed':return self.config['fixed_percent'] if core<81 else max(self.config['fixed_percent'],self.interpolate(DEFAULT_CURVE,core))
        return self.interpolate(self.config['curve'],core)
    @staticmethod
    def interpolate(curve,core):
        if core<=curve[0][0]:return curve[0][1]
        for (a,x),(b,y) in zip(curve,curve[1:]):
            if core<=b:return math.ceil(x+(core-a)*(y-x)/(b-a))
        return curve[-1][1]
    def update(self,rows,now):
        real(now)
        if self.last is not None and not 0<now-self.last<=5:raise ValueError('Invalid tick interval')
        if type(rows) is not list or len(rows)!=4:raise ValueError('Four GPU rows required')
        seen=set();parsed=[]
        for row in rows:
            if type(row) is not dict or type(row.get('uuid')) is not str or row['uuid'] not in self.ids or row['uuid'] in seen:raise ValueError('Invalid identity')
            seen.add(row['uuid']);parsed.append((real(row.get('coreC'),0,120),real(row.get('utilizationGpu'),0,100)))
        # Reject all malformed data before mutating timers or target.
        dt=0 if self.last is None else now-self.last;self.last=now
        raw=max(c for c,u in parsed);active=any(u>=10 for c,u in parsed);idle=all(c<65 and u<10 for c,u in parsed)
        self.filtered=raw if self.filtered is None else self.filtered+(1-math.exp(-dt/3))*(raw-self.filtered)
        demand=self.demand(max(raw,self.filtered))
        if self.config['mode']=='fixed':self.target=demand;return self.target
        if active:
            if self.load_armed:self.startup_until=now+self.config['startup_seconds'];self.load_armed=False
            self.quiet_since=None
        else:
            if self.quiet_since is None:self.quiet_since=now
            if now-self.quiet_since>=30:self.load_armed=True
        if active:
            demand=max(65,demand)
            if self.startup_until is not None and now<self.startup_until:
                demand=max(self.config['startup_floor'],demand);self.target=max(self.target,self.config['startup_floor'])
        if idle:
            if self.idle_since is None:self.idle_since=now
        else:self.idle_since=self.idle_step=None
        if raw>=81:
            self.target=max(self.target,self.demand(raw));self.credit=0;self.cool_since=self.cool_step=None
        elif demand>self.target:
            self.credit+=2*dt;change=min(demand-self.target,math.floor(self.credit+1e-9));self.target+=change;self.credit-=change
            self.cool_since=self.cool_step=None
        else:
            self.credit=0
            if idle and now-self.idle_since>=30:
                if demand<self.target and (self.idle_step is None or now-self.idle_step>=5):self.target=max(demand,self.target-5);self.idle_step=now
                self.cool_since=self.cool_step=None
            elif demand<=self.target-3:
                if self.cool_since is None:self.cool_since=now
                if now-self.cool_since>=20 and (self.cool_step is None or now-self.cool_step>=10):self.target=max(demand,self.target-1);self.cool_step=now
            else:self.cool_since=self.cool_step=None
        return self.target
