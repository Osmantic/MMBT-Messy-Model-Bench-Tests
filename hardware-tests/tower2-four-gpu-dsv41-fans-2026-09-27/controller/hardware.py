"""NVML observations and explicitly owned fan writes."""
import ctypes,time
from common import UUIDS,real,utc,boot
class Hardware:
    def __init__(self,n):self.n=n;self.handles={};self.initialized=False
    def open(self):
        self.n.nvmlInit();self.initialized=True
        if self.n.nvmlDeviceGetCount()!=4:raise ValueError('Four GPUs required')
        for i in range(4):
            h=self.n.nvmlDeviceGetHandleByIndex(i);u=self.n.nvmlDeviceGetUUID(h)
            if u not in UUIDS or u in self.handles or self.n.nvmlDeviceGetNumFans(h)!=2:raise ValueError('GPU/fan identity differs')
            self.handles[u]=h
    def close(self):
        if self.initialized:self.n.nvmlShutdown();self.initialized=False
    def caps(self,repair=False):
        for u,h in self.handles.items():
            if self.n.nvmlDeviceGetUUID(h)!=u:raise ValueError('GPU identity changed')
            req=real(self.n.nvmlDeviceGetPowerManagementLimit(h),150000,600000);enf=real(self.n.nvmlDeviceGetEnforcedPowerLimit(h),150000,600000)
            if repair and (req!=275000 or enf>275000):self.n.nvmlDeviceSetPowerManagementLimit(h,275000);req=self.n.nvmlDeviceGetPowerManagementLimit(h);enf=self.n.nvmlDeviceGetEnforcedPowerLimit(h)
            if req!=275000 or not 150000<=enf<=275000:raise ValueError('275W caps not confirmed')
    def rpm(self,h,f):
        v=self.n.c_nvmlFanSpeedInfo_t(version=self.n.nvmlFanSpeedInfo_v1,fan=f)
        self.n._nvmlCheckReturn(self.n._nvmlGetFunctionPointer('nvmlDeviceGetFanSpeedRPM')(h,ctypes.byref(v)))
        return real(v.speed,0,10000)
    def read(self,temperature=True):
        began=time.monotonic();n=self.n
        if n.nvmlDeviceGetCount()!=4 or set(self.handles)!=UUIDS:raise ValueError('GPU set changed')
        self.caps();rows=[]
        for u,h in self.handles.items():
            if n.nvmlDeviceGetNumFans(h)!=2:raise ValueError('Fan count changed')
            fans=[]
            for f in (0,1):
                policy=n.nvmlDeviceGetFanControlPolicy_v2(h,f)
                if type(policy) is not int or policy not in (0,1):raise ValueError('Unknown fan policy')
                fans.append({'fan':f,'policy':policy,'target':real(n.nvmlDeviceGetTargetFanSpeed(h,f),0,100),'current':real(n.nvmlDeviceGetFanSpeed_v2(h,f),0,100),'rpm':self.rpm(h,f)})
            row={'uuid':u,'requestedPowerW':n.nvmlDeviceGetPowerManagementLimit(h)/1000,'enforcedPowerW':n.nvmlDeviceGetEnforcedPowerLimit(h)/1000,'fans':fans,'vramC':None}
            if row['requestedPowerW']!=275 or not 150<=row['enforcedPowerW']<=275:raise ValueError('Cap changed during sample')
            if temperature:row.update(coreC=real(n.nvmlDeviceGetTemperature(h,n.NVML_TEMPERATURE_GPU),0,120),utilizationGpu=real(n.nvmlDeviceGetUtilizationRates(h).gpu,0,100))
            rows.append(row)
        if time.monotonic()-began>5:raise TimeoutError('Sensor sample exceeded5s')
        return {'utc':utc(),'bootId':boot(),'monotonic':time.monotonic(),'gpus':rows}
    def command(self,target,lease):
        if lease.fd is None:raise RuntimeError('Fan write without ownership')
        if type(target) is not int or not 30<=target<=100:raise ValueError('Invalid shared target')
        # Complete identity/cap validation before the first fan write.
        self.caps()
        for h in self.handles.values():
            for f in (0,1):self.n.nvmlDeviceSetFanSpeed_v2(h,f,target)
    def automatic(self,lease):
        if lease.fd is None:raise RuntimeError('Automatic handoff without ownership')
        self.caps(repair=True)
        errors=[]
        for u,h in self.handles.items():
            for f in (0,1):
                try:self.n.nvmlDeviceSetDefaultFanSpeed_v2(h,f)
                except Exception as exc:errors.append({'uuid':u,'fan':f,'error':type(exc).__name__})
        sample=self.read(temperature=False)
        if errors or any(f['policy']!=0 for g in sample['gpus'] for f in g['fans']):raise RuntimeError('Automatic handoff unconfirmed: '+str(errors))
        sample['verifiedAutomatic']=True;return sample
def manual_proof(sample,target,transitions,now):
    settled=True
    for g in sample['gpus']:
        for f in g['fans']:
            key=(g['uuid'],f['fan'])
            if f['policy']!=1 or f['target']!=target:raise ValueError('Manual target/policy differs')
            if f['rpm']<=0:raise ValueError('Manual fan stalled')
            if abs(f['current']-target)>8:
                settled=False;transitions.setdefault(key,now)
                if now-transitions[key]>15:raise ValueError('Fan settling timeout')
                f['settlingSince']=transitions[key]
            else:transitions.pop(key,None);f['settlingSince']=None
    return settled
