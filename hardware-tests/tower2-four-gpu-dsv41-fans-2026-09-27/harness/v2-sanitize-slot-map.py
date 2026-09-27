"""Retain only GPU slot designations/BDFs; omit private board/system records."""
import csv,datetime,hashlib,json,subprocess
from pathlib import Path
B=Path('/mnt/bulk/codex-work/four-gpu-dsv41-20260926');raw=(B/'evidence/board-slots.json').read_bytes()
slots=[]
for r in json.loads(raw):
    if r.get('type')==9 and r.get('segment')==0 and r.get('devfunc')==0 and r.get('bus') in (225,1,193,2):
        slots.append({'designation':r['strings'][0],'pciBdf':f"0000:{r['bus']:02x}:00.0"})
rows=list(csv.reader(subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,pci.bus_id','--format=csv,noheader'],text=True,timeout=5).splitlines()))
for slot in slots:
    matches=[r for r in rows if r[2].strip().lower().endswith(slot['pciBdf'][4:])];assert len(matches)==1
    slot.update(index=int(matches[0][0]),uuid=matches[0][1].strip())
assert len(slots)==4
result={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'firmwareEvidenceSha256':hashlib.sha256(raw).hexdigest(),'slotEvidence':'SMBIOS type9 designation and segment/bus/devfunc records matched to fresh GPU PCI addresses','orderBasis':'Motherboard manual slot ordering, corroborated by owner original top/bottom cards','slotsTopToBottom':sorted(slots,key=lambda s:int(s['designation'].rsplit('_',1)[1])),'gapOrRiserDimensions':'Not directly measured','manualUrl':'https://dlcdnets.asus.com/pub/ASUS/mb/SocketsTR5/Pro_WS_WRX90E-SAGE_SE/E23789_Pro_WS_WRX90E-SAGE_SE_EM_V2_WEB.pdf'}
path=B/'evidence/v2-sanitized-gpu-slot-map.json';path.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
