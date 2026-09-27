"""Plot actual complete pairs including visibly failed plateau eligibility."""
import csv,hashlib,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
W=Path(__file__).parent;O=W.parent/'outputs'
selection=O/'v2-selected-base80-review.json';raw=selection.read_bytes();r=json.loads(raw)
assert hashlib.sha256(raw).hexdigest()=='d6a790707e9a7aa09737be89722a580b5d8aee595f081da6c70e0c7adeefc4d6'
assert r['formalComparisonStatus']=='not-qualified' and not r['formalPerformanceClaimAccepted']
eligibility={p['phase']:p for p in r['eligibility']};rows=[]
for i,pair in enumerate(r['pairs']):
    for role in ('reference','candidate'):
        name=pair[role];folder=O/name;araw=(folder/'analysis.json').read_bytes();praw=(folder/'plateau-analysis.json').read_bytes()
        assert hashlib.sha256(araw).hexdigest()==eligibility[name]['analysisSha256'] and hashlib.sha256(praw).hexdigest()==eligibility[name]['plateauSha256']
        a=json.loads(araw);p=json.loads(praw)
        hottest=max(sum(c['meanCoreC']*c['coverageSeconds'] for c in g['cycles'])/sum(c['coverageSeconds'] for c in g['cycles']) for g in p['gpu'].values())
        rows.append({'pair':i+1,'role':role,'phase':name,'plateauStatus':p['status'],'decode600TokensPerSecond':a['warmDecode600']['aggregateTokensPerSecond'],'decodeCoverageSeconds':a['warmDecode600']['seconds'],'e2eTokensPerSecond':a['e2eOutputTokensPerSecond'],'steadyFanPercent':a['noiseProxy']['steady600RequestedPercent'],'hottestCycleMeanCoreC':hottest,'peakCoreC':max(g['peakCoreC'] for g in a['gpu'].values())})
fig,grid=plt.subplots(2,2,figsize=(12,8.5),layout='constrained');axes=list(grid.flat);colors=['#0072B2','#D55E00','#009E73']
for i in range(3):
    pair=[row for row in rows if row['pair']==i+1]
    for ax,key in zip(axes,['decode600TokensPerSecond','e2eTokensPerSecond','steadyFanPercent','hottestCycleMeanCoreC']):
        values=[row[key] for row in pair];ax.plot([0,1],values,'o-',color=colors[i],label=f'Pair {i+1}')
        for x,row in enumerate(pair):
            if ax is not axes[3]:ax.annotate(f'{row[key]:.1f}',(x,row[key]),xytext=(5,5),textcoords='offset points',fontsize=8)
            if row['plateauStatus']!='pass':ax.plot(x,row[key],'x',color='red',markersize=12,markeredgewidth=2)
    axes[3].plot([0,1],[row['peakCoreC'] for row in pair],'^',color=colors[i],alpha=.65)
for ax,title,label in zip(axes,['Warmed simultaneous decode','Whole-run throughput','Sustained fan effort','Hottest cycle mean / full-run peak'],['Delivered tokens/s','Output tokens/s','Requested percent','Core temperature, C']):
    ax.set(title=title,ylabel=label,xlim=(-.2,1.25));ax.set_xticks([0,1],['Fixed85%','Candidate curve']);ax.grid(axis='y',alpha=.25)
axes[0].legend(fontsize=8)
axes[3].axhspan(75,80,color='#009E73',alpha=.1);axes[3].axhline(82,color='#D55E00',linestyle='--',linewidth=1)
axes[3].set_ylim(74.5,83.5)
axes[3].text(.02,.97,'Triangles: full-run raw peak\nShaded: preferred75–80C; dashed:82C',transform=axes[3].transAxes,va='top',fontsize=8)
d=r['metrics']['warmSimultaneousDecode600'];e=r['metrics']['endToEnd']
fig.suptitle('Four-GPU DSV4.1 at275W per card — descriptive matched results\nFormal comparison NOT QUALIFIED; red X marks the ineligible third candidate',fontsize=12)
fig.supxlabel(f"Decode ratio {d['geometricMeanRatio']:.4f}, descriptive95% CI {d['twoSided95PercentLower']:.4f}–{d['twoSided95PercentUpper']:.4f}; "
               f"end-to-end {e['geometricMeanRatio']:.4f}, CI {e['twoSided95PercentLower']:.4f}–{e['twoSided95PercentUpper']:.4f}.\n"
               'These intervals include a failed plateau and cannot establish formal noninferiority. End-to-end lower bound also misses0.97.\n'
               'Final600s decode/fans; six complete-cycle temperature means. Fan% is a relative noise proxy; inlet temperature unmeasured.',fontsize=8)
output=O/'matched-descriptive-comparison.png';fig.savefig(output,dpi=180);plt.close(fig)
with output.with_suffix('.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
print(json.dumps({'figure':str(output),'formalQualification':False,'rows':len(rows)}))
