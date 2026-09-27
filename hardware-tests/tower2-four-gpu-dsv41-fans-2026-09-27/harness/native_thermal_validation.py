import math
from statistics import median

EXPECTED_UUIDS = {
    'GPU-708ffb68-e356-930d-4f83-980567b5ae3a',
    'GPU-ff71102f-22f8-52bb-da93-2076a6531329',
    'GPU-6b6dd6f9-2850-043f-b545-6ff4a60df2ca',
    'GPU-fe3fb4d0-5ddc-9c05-587b-1bc84c75c1a0'
}
UUIDS = EXPECTED_UUIDS

def _parse_float(s):
    if isinstance(s, bool):return None
    try:
        v = float(s)
        if not math.isfinite(v):
            return None
        return v
    except (ValueError, TypeError):
        return None

def _parse_int(s):
    if type(s) not in (int,str) or (type(s) is str and not s.isdigit()):return None
    try:
        v = int(s)
        if v < 0:
            return None
        return v
    except (ValueError, TypeError):
        return None

def _ols_slope(xs, ys):
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return (num / den) * 60.0

def _collect_thermal(samples, baseline, run_start, total_elapsed, tail_seconds=180, operating_max_c=None):
    reasons = []
    if operating_max_c is not None and (type(operating_max_c) is not int or operating_max_c not in (80,82)):
        raise ValueError('Quiet operating maximum must be80 or82C')
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (run_start,total_elapsed,tail_seconds)):
        raise ValueError('Invalid time parameters')
    
    # 1. Validate Baseline Structure
    b_rows = baseline.get('rows', [])
    if len(b_rows) != 4 or {r.get('uuid') for r in b_rows} != EXPECTED_UUIDS:
        reasons.append("Baseline missing or invalid UUIDs")
        return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}
    
    b_vm = baseline.get('vmstat', {})
    b_mem = baseline.get('memory', {})
    if any(type(b_vm.get(k)) is not int or b_vm[k]<0 for k in ('pswpin','pswpout','oom_kill')):
        reasons.append("Baseline vmstat invalid")
        return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}
    if type(b_mem.get('MemAvailable')) is not int or b_mem['MemAvailable'] < 10 * (2**30):
        reasons.append("Baseline MemAvailable invalid")
        return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}

    # 2. Process Samples
    processed = []
    for i, s in enumerate(samples):
        sm = s.get('sample', {})
        mono = sm.get('monotonic')
        if type(mono) not in (int,float) or not math.isfinite(mono):
            reasons.append(f"Sample {i} invalid monotonic")
            return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}
        
        rel_t = mono - run_start
        rows = sm.get('rows', [])
        if len(rows) != 4 or {r.get('uuid') for r in rows} != EXPECTED_UUIDS:
            reasons.append(f"Sample {i} invalid rows/UUIDs")
            return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}
        
        # Validate Rows
        valid_sample = True
        for r in rows:
            uuid = r.get('uuid')
            # Counters check
            for k in ['clocks_event_reasons_counters.sw_thermal_slowdown', 
                       'clocks_event_reasons_counters.hw_thermal_slowdown', 
                       'clocks_event_reasons_counters.hw_power_brake_slowdown']:
                val = _parse_int(r.get(k))
                if val is None:
                    valid_sample = False
                    break
                # Check against baseline
                b_val = _parse_int(next((br.get(k) for br in b_rows if br.get('uuid') == uuid), None))
                if b_val is None or val != b_val:
                    valid_sample = False
                    break
            if not valid_sample: break
            
            # Numeric fields
            temp_gpu = _parse_float(r.get('temperature.gpu'))
            if temp_gpu is None or temp_gpu < 0 or (temp_gpu>82 if operating_max_c==82 else temp_gpu>=82):
                valid_sample = False; break
            if operating_max_c is not None and temp_gpu>operating_max_c:
                reasons.append(f'Sample {i} {uuid} exceeded{operating_max_c}C quiet operating maximum')
                valid_sample=False;break
            
            mem_temp_str = r.get('temperature.memory')
            mem_temp = None
            if mem_temp_str not in ('N/A', '[N/A]'):
                mem_temp = _parse_float(mem_temp_str)
                if mem_temp is None or not (0 <= mem_temp < 90):
                    valid_sample = False; break
            
            p_lim = _parse_float(r.get('power.limit'))
            e_lim = _parse_float(r.get('enforced.power.limit'))
            if p_lim is None or e_lim is None or not (150 <= p_lim <= 275) or not (150 <= e_lim <= 275):
                valid_sample = False; break
            
            fan = _parse_float(r.get('fan.speed'))
            if fan is None or not (0 <= fan <= 100):
                valid_sample = False; break
            
            clk_gr = _parse_float(r.get('clocks.gr'))
            if clk_gr is None or not (0 <= clk_gr <= 4000):
                valid_sample = False; break
            
            p_avg = _parse_float(r.get('power.draw.average'))
            p_inst = _parse_float(r.get('power.draw.instant'))
            if p_avg is None or p_inst is None or not (0 <= p_avg <= 1000) or not (0 <= p_inst <= 1000):
                valid_sample = False; break
        
        if not valid_sample:
            reasons.append(f"Sample {i} row validation failed")
            return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}

        # Memory & VMStat
        cur_mem = sm.get('memory', {})
        cur_vm = sm.get('vmstat', {})
        
        mem_avail = cur_mem.get('MemAvailable')
        if type(mem_avail) is not int or mem_avail < 10 * (2**30):
            reasons.append(f"Sample {i} MemAvailable invalid")
            return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}
            
        pswpin = cur_vm.get('pswpin')
        pswpout = cur_vm.get('pswpout')
        oom = cur_vm.get('oom_kill')
        
        if any(type(v) is not int or v<0 for v in (pswpin,pswpout,oom)):
            reasons.append(f"Sample {i} vmstat invalid types")
            return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}
            
        if pswpout != b_vm['pswpout'] or oom != b_vm['oom_kill']:
            reasons.append(f"Sample {i} vmstat swapout/oom changed")
            return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}
        if pswpin < (processed[-1]['pswpin'] if processed else b_vm['pswpin']):
            raise ValueError('Swap-in counter regressed')
            
        processed.append({
            'rel_t': rel_t,
            'rows': rows,
            'mem_avail': mem_avail,
            'pswpin': pswpin
        })

    if not processed:
        reasons.append("No valid samples")
        return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}

    # 3. Time Validation
    # Strictly increasing monotonic (rel_t)
    for i in range(1, len(processed)):
        if processed[i]['rel_t'] <= processed[i-1]['rel_t']:
            reasons.append("Samples not strictly increasing")
            return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}

    first_t = processed[0]['rel_t']
    last_t = processed[-1]['rel_t']
    
    if abs(first_t) > 3.0:
        reasons.append("First sample not within 3s of run_start")
        return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}
    if abs(last_t - total_elapsed) > 3.0:
        reasons.append("Last sample not within 3s of total_elapsed")
        return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}

    # 4. Tail Selection
    tail_start = max(0, total_elapsed - tail_seconds)
    tail_samples = [p for p in processed if p['rel_t'] >= tail_start]
    
    if len(tail_samples) < 170:
        reasons.append(f"Tail has {len(tail_samples)} samples, need >= 170")
        return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}
    
    tail_span = tail_samples[-1]['rel_t'] - tail_samples[0]['rel_t']
    if tail_span < 170.0:
        reasons.append(f"Tail span {tail_span:.2f}s < 170s")
        return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}
    
    tail_intervals = [tail_samples[i]['rel_t'] - tail_samples[i-1]['rel_t'] for i in range(1, len(tail_samples))]
    if not tail_intervals:
        reasons.append("Tail intervals empty")
        return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}
        
    med_int = median(tail_intervals)
    max_int = max(tail_intervals)
    
    if med_int > 1.5:
        reasons.append(f"Tail median interval {med_int:.2f}s > 1.5s")
        return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}
    if max_int > 5.0:
        reasons.append(f"Tail max interval {max_int:.2f}s > 5.0s")
        return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}

    # Full trial max interval check
    full_intervals = [processed[i]['rel_t'] - processed[i-1]['rel_t'] for i in range(1, len(processed))]
    if full_intervals and max(full_intervals) > 5.0:
        reasons.append(f"Full trial max interval {max(full_intervals):.2f}s > 5.0s")
        return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}

    # 5. Compute Stats
    per_gpu = {}
    for uuid in EXPECTED_UUIDS:
        # Filter rows for this GPU in tail
        gpu_data = []
        for p in tail_samples:
            row = next((r for r in p['rows'] if r['uuid'] == uuid), None)
            if row:
                gpu_data.append({
                    't': p['rel_t'],
                    'temp': float(row['temperature.gpu']),
                    'fan': float(row['fan.speed']),
                    'clk': float(row['clocks.gr']),
                    'p_avg': float(row['power.draw.average']),
                    'p_inst': float(row['power.draw.instant']),
                    'mem_temp': float(row['temperature.memory']) if row['temperature.memory'] not in ('N/A', '[N/A]') else None
                })
        
        if not gpu_data:
            reasons.append(f"No data for {uuid}")
            return {'qualified': False, 'reasons': reasons, 'tail': {}, 'full': {}}

        temps = [d['temp'] for d in gpu_data]
        fans = [d['fan'] for d in gpu_data]
        clks = [d['clk'] for d in gpu_data]
        p_avgs = [d['p_avg'] for d in gpu_data]
        p_insts = [d['p_inst'] for d in gpu_data]
        
        # Slope
        xs = [d['t'] for d in gpu_data]
        ys = temps
        slope = _ols_slope(xs, ys)
        if abs(slope) > 0.3:
            reasons.append(f"{uuid} temp slope {slope:.3f} C/min > 0.3")
            
        # Above 275 counts
        above_avg = sum(1 for v in p_avgs if v > 275)
        above_inst = sum(1 for v in p_insts if v > 275)
        
        # Mem Temp Stats (null if unsupported)
        mem_temps = [d['mem_temp'] for d in gpu_data if d['mem_temp'] is not None]
        mem_stats = None
        if mem_temps:
            mem_stats = {
                'min': min(mem_temps),
                'mean': sum(mem_temps)/len(mem_temps),
                'max': max(mem_temps)
            }

        per_gpu[uuid] = {
            'temperature_c': {'min': min(temps), 'mean': sum(temps)/len(temps), 'max': max(temps)},
            'fan_percent': {'min': min(fans), 'mean': sum(fans)/len(fans), 'max': max(fans)},
            'graphics_mhz': {'min': min(clks), 'mean': sum(clks)/len(clks), 'max': max(clks)},
            'power_average_w': {'min': min(p_avgs), 'mean': sum(p_avgs)/len(p_avgs), 'max': max(p_avgs)},
            'power_instant_w': {'min': min(p_insts), 'mean': sum(p_insts)/len(p_insts), 'max': max(p_insts)},
            'temperature_slope_c_per_min': slope,
            'above275_average_samples': above_avg,
            'above275_instant_samples': above_inst,
            'vram_temperature_c': mem_stats
        }

    # Full Trial Stats
    min_ram = min(p['mem_avail'] for p in processed)
    
    # VMStat Deltas
    # pswpin is monotonic increasing, pswpout/oom constant
    full_pswpin_delta = processed[-1]['pswpin'] - b_vm['pswpin']
    tail_pswpin_delta = tail_samples[-1]['pswpin'] - tail_samples[0]['pswpin']
    
    # Aggregate above 275 counts for full trial (sum of per-gpu above counts in tail? Or full?)
    # Prompt says "summary perGPU ... actualabove275 counts separate" in tail section.
    # Full section asks for "above275_counts". Usually implies total or per gpu. 
    # Given structure, let's sum the tail counts as representative of the load period, 
    # or compute full. The prompt says "Fulltrial ... above275_counts". 
    # Let's compute total above 275 events across all GPUs in the FULL trial for completeness, 
    # but the tail stats are already computed. 
    # Re-reading: "summary perGPU ... actualabove275 counts separate" is under Tail.
    # "Fulltrial ... above275_counts" is under Full.
    # I will sum the tail counts for the full object as it's the qualified period, 
    # or compute full. Let's compute full to be safe.
    
    full_above_counts = {u:{'average':0,'instant':0} for u in EXPECTED_UUIDS}
    for p in processed:
        for r in p['rows']:
            p_avg = float(r['power.draw.average'])
            p_inst = float(r['power.draw.instant'])
            if p_avg > 275: full_above_counts[r['uuid']]['average'] += 1
            if p_inst > 275: full_above_counts[r['uuid']]['instant'] += 1

    return {
        'qualified': not reasons,
        'reasons': reasons,
        'tail': {
            'sample_count': len(tail_samples),
            'span_seconds': tail_span,
            'median_interval': med_int,
            'max_interval': max_int,
            'per_gpu': per_gpu
        },
        'full': {
            'sample_count': len(processed),
            'min_ram_available_bytes': min_ram,
            'vmstat_delta': {'pswpin':full_pswpin_delta,'pswpout':0,'oom_kill':0},
            'tail_vmstat_delta': {'pswpin':tail_pswpin_delta,'pswpout':0,'oom_kill':0},
            'above275_counts': full_above_counts
        }
    }

def collect_thermal(samples, baseline, run_start, total_elapsed, tail_seconds=180, operating_max_c=None):
    try:return _collect_thermal(samples,baseline,run_start,total_elapsed,tail_seconds,operating_max_c)
    except (ValueError,TypeError,KeyError,IndexError,OverflowError) as exc:
        return {'qualified':False,'reasons':[type(exc).__name__+': '+str(exc)],'tail':{},'full':{}}
