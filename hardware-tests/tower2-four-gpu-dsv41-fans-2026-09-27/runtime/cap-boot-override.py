"""Eliminate the previous 500 W boot configuration before further study."""
import subprocess, json
from pathlib import Path
b=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926/evidence')
before=Path('/etc/systemd/system/nvidia-powerlimit.service').read_text()
if not (b/'nvidia-powerlimit-before.service').exists():
    (b/'nvidia-powerlimit-before.service').write_text(before)
override='''[Unit]
Description=MMBT four-GPU maximum 275 W power limit
After=
After=nvidia-persistenced.service
Before=docker.service

[Service]
ExecStart=
ExecStart=/usr/bin/nvidia-smi -pm 1
ExecStart=/usr/bin/nvidia-smi -pl 275
'''
unit='''[Unit]
Description=MMBT four-GPU maximum 275 W power limit
After=nvidia-persistenced.service
Wants=nvidia-persistenced.service
Before=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/nvidia-smi -pm 1
ExecStart=/usr/bin/nvidia-smi -pl 275

[Install]
WantedBy=multi-user.target
'''
code="""import os, pathlib
p=pathlib.Path('/units')
f=p/'nvidia-powerlimit.service'
t=p/'nvidia-powerlimit.service.mmbt-tmp'
t.write_text(%r)
t.chmod(0o644)
os.replace(t,f)
drop=p/'nvidia-powerlimit.service.d/90-mmbt-275w.conf'
if drop.exists():drop.unlink()
""" % unit
subprocess.run(['docker','run','--rm','--name','mmbt-cap-boot-install',
    '--network','none','--read-only','--cap-drop','ALL','--cap-add','DAC_OVERRIDE',
    '--security-opt','no-new-privileges','-v','/usr:/usr:ro',
    '-v','/etc/systemd/system:/units','--entrypoint','/usr/bin/python3',
    'ubuntu:24.04','-c',code],check=True)
manager=['docker','run','--rm','--network','none','--read-only','--pid','host',
    '--cap-drop','ALL','--security-opt','no-new-privileges','--security-opt','apparmor=unconfined',
    '-v','/usr:/usr:ro','-v','/run/systemd:/run/systemd:ro',
    '--entrypoint','/usr/bin/systemctl','ubuntu:24.04']
subprocess.run(manager+['daemon-reload'],check=True)
effective=subprocess.check_output(['systemctl','show','nvidia-powerlimit.service','--property=ExecStart,After'],text=True)
assert '-pl 500' not in effective and '-pl 600' not in effective
assert 'multi-user.target' not in effective
subprocess.run(manager+['restart','nvidia-powerlimit.service'],check=True)
result=subprocess.run(['systemctl','show','nvidia-powerlimit.service',
    '--property=Description,ExecStart,ActiveState,SubState,Before,After'],
    text=True,capture_output=True,check=True)
(b/'cap-boot-override-verification.txt').write_text(result.stdout)
print(result.stdout)
result=subprocess.run(['nvidia-smi','--query-gpu=index,uuid,power.limit,enforced.power.limit',
    '--format=csv,noheader,nounits'],text=True,capture_output=True,check=True)
(b/'hardware-capped-after-boot-override.csv').write_text(result.stdout)
assert len(result.stdout.strip().splitlines())==4
assert all(float(v.strip())==275 for row in result.stdout.strip().splitlines() for v in row.split(',')[-2:])
print(json.dumps({'allFourCapsVerified':275,'old500WBootCommandsOverridden':True}))
