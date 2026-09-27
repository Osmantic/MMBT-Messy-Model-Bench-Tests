"""Narrow systemd bridge for this study's installed units only."""
import subprocess,sys
allowed={'mmbt-gpu-control.service','mmbt-native-watchdog.service','mmbt-dsv41.service'}
action=sys.argv[1];assert action in {'daemon-reload','start','stop','restart','enable','disable','reset-failed','kill'}
values=sys.argv[2:]
if action=='daemon-reload':assert not values
elif action=='kill':
    assert len(values)==2 and values[0] in ('--signal=SIGSTOP','--signal=SIGKILL','--signal=SIGCONT') and values[1] in allowed
else:assert values and set(values)<=allowed
args=['docker','run','--rm','--network','none','--read-only','--pid','host',
      '--cap-drop','ALL','--security-opt','no-new-privileges','--security-opt','apparmor=unconfined',
      '-v','/usr:/usr:ro','-v','/run/systemd:/run/systemd:ro',
      '--entrypoint','/usr/bin/systemctl','ubuntu:24.04',action,*values]
raise SystemExit(subprocess.run(args,timeout=60).returncode)
