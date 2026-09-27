"""Delivered-token rate during intersections of C simultaneous decode streams."""
import bisect,math
from collections import defaultdict

def measure(streams,origin,begin,end,concurrency=8):
    assert all(type(x) in (int,float) and math.isfinite(x) for x in (origin,begin,end)) and end>begin
    boundaries=defaultdict(int);deliveries=[]
    for stream in streams:
        positive=[];previous=0
        for event in stream['events']:
            count=event['cumulativeTokens']
            if count is None:continue
            assert type(count) is int and count>=previous
            stamp=origin+event['t'];assert math.isfinite(stamp)
            if count>previous:positive.append((stamp,count-previous))
            previous=count
        assert positive
        a=max(begin,positive[0][0]);b=min(end,positive[-1][0])
        if b>a:boundaries[a]+=1;boundaries[b]-=1
        deliveries.extend((stamp,delta) for stamp,delta in positive if begin<stamp<=end)
    count=0;last=begin;windows=[]
    for stamp,delta in sorted(boundaries.items()):
        if count==concurrency and stamp>last:windows.append((last,stamp))
        count+=delta;assert 0<=count<=concurrency,'More than C streams decoding'
        last=stamp
    assert count==0
    starts=[a for a,b in windows];tokens=0
    for stamp,delta in deliveries:
        index=bisect.bisect_left(starts,stamp)-1
        if index>=0 and windows[index][0]<stamp<=windows[index][1]:tokens+=delta
    seconds=sum(b-a for a,b in windows)
    return {'tokens':tokens,'seconds':seconds,'aggregateTokensPerSecond':tokens/seconds if seconds else None,'windowDurationSeconds':end-begin,'simultaneousStreams':concurrency,'intervals':len(windows),'coverageFraction':seconds/(end-begin),'meaning':'Delivered token increments during intervals from first to last positive delivery with all C streams decoding; excludes observed prefill/drain gaps. Not GPU kernel timing.'}
