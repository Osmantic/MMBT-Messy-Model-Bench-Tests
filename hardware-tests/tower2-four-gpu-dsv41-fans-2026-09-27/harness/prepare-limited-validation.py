"""Prepare separate orchestration for an explicitly unqualified selection.

Original comparison-gated harnesses and their receipts remain unchanged.
Every other identity, cap, workload, thermal and recovery guard remains.
"""
from pathlib import Path
W=Path(__file__).parent
pin='d6a790707e9a7aa09737be89722a580b5d8aee595f081da6c70e0c7adeefc4d6'
def check(variable,path):
    return f"assert {variable}['status']=='selected-with-performance-uncertainty' and {variable}['formalComparisonStatus']=='not-qualified' and {variable}['formalPerformanceClaimAccepted'] is False;assert hashlib.sha256({path}.read_bytes()).hexdigest()=='{pin}'"
src=(W/'v2-selected-preboot-tests.py').read_text()
src=src.replace('Runs only the exact selected qualified curve.','Runs only the exact reviewed curve; formal performance remains unqualified.')
src=src.replace("and arg.comparison.startswith('v2-matched-')","and arg.comparison=='v2-selected-base80-review.json'")
src=src.replace("assert c['status']=='qualified'",check('c','comparison'))
src=src.replace("run('v3-verify-series-bytes.py',arg.comparison)","assert c['sourceByteVerification']=='all six actual profile, source snapshots, live controller/harness and analysis linkage passed'")
src=src.replace("receipt={'status':'starting'","receipt={'formalPerformanceQualification':False,'selectionStatus':c['status'],'status':'starting'")
(W/'v3-selected-preboot-uncertain.py').write_text(src)
src=(W/'v2-recreate-bounded-native-logs.py').read_text()
src=src.replace("assert comparison['status']=='qualified'",check('comparison','comparison_path'))
src=src.replace("'qualifiedComparison':a.qualified_comparison","'selectionReceipt':a.qualified_comparison,'formalPerformanceQualification':False")
(W/'v3-recreate-bounded-native-logs-uncertain.py').write_text(src)
src=(W/'v2-request-real-reboot.py').read_text()
src=src.replace("comparison['status']=='qualified'","comparison['status']=='selected-with-performance-uncertainty' and comparison['formalComparisonStatus']=='not-qualified'")
src=src.replace("now=datetime.datetime.now(datetime.timezone.utc)",f"assert hashlib.sha256((E/a.comparison).read_bytes()).hexdigest()=='{pin}'\nnow=datetime.datetime.now(datetime.timezone.utc)")
src=src.replace("'status':'reboot-requested'","'formalPerformanceQualification':False,'selectionReceipt':a.comparison,'status':'reboot-requested'")
(W/'v3-request-real-reboot-uncertain.py').write_text(src)
print('Prepared three separate bounded validation orchestrators; original formal gates unchanged.')
