"""Public, normalized performance only. No account balances or holdings are used."""
import math
import statistics


def calculate(payload, start=None, through=None, include_estimated=True, risk_free=0.0):
    records = sorted(payload.get('points', []), key=lambda row: row['date'])
    phase_start = payload['startDate']
    start = max(start or phase_start, phase_start)
    through = through or (records[-1]['date'] if records else start)
    eligible = [row for row in records if include_estimated or not row.get('estimated')]
    active = [row for row in eligible if start <= row['date'] <= through and not row.get('baseline')]
    if not active:
        return None
    anchors = [row for row in eligible if row['date'] < active[0]['date']]
    if not anchors:
        return None
    anchor = anchors[-1]
    rows = [anchor] + active
    curve = []
    peak_a = peak_b = 1.0
    for row in rows:
        a = row['strategyIndex'] / anchor['strategyIndex']
        b = row['benchmarkIndex'] / anchor['benchmarkIndex']
        peak_a, peak_b = max(peak_a, a), max(peak_b, b)
        curve.append({'date':row['date'], 'strategy':(a-1)*100, 'ndx':(b-1)*100,
                      'excess':(a-b)*100, 'drawdownStrategy':(a/peak_a-1)*100,
                      'drawdownNdx':(b/peak_b-1)*100, 'estimated':bool(row.get('estimated')),
                      'estimateSession':row.get('estimateSession'), 'observedAt':row.get('observedAt')})
    daily = [{'date':row['date'], 'strategy':row['strategyIndex']/prior['strategyIndex']-1,
              'ndx':row['benchmarkIndex']/prior['benchmarkIndex']-1,
              'estimated':bool(row.get('estimated'))} for prior, row in zip(rows, rows[1:])]
    a, b = [row['strategy'] for row in daily], [row['ndx'] for row in daily]
    active_returns = [x-y for x, y in zip(a,b)]
    sufficient = len(a) >= 5
    sd_a = statistics.stdev(a) if len(a)>1 else 0.0
    sd_b = statistics.stdev(b) if len(b)>1 else 0.0
    sd_active = statistics.stdev(active_returns) if len(a)>1 else 0.0
    covariance = statistics.covariance(a,b) if len(a)>1 else 0.0
    rf_daily = (1+max(0,min(.3,risk_free)))**(1/252)-1
    annual = math.sqrt(252)
    stats = {
        'cumulative':curve[-1]['strategy'], 'benchmark':curve[-1]['ndx'], 'excess':curve[-1]['excess'],
        'maxDrawdown':min(row['drawdownStrategy'] for row in curve),
        'benchmarkMaxDrawdown':min(row['drawdownNdx'] for row in curve),
        'volatility':sd_a*annual*100 if sufficient else None,
        'benchmarkVolatility':sd_b*annual*100 if sufficient else None,
        'sharpe':(statistics.mean(a)-rf_daily)/sd_a*annual if sufficient and sd_a>1e-12 else None,
        'benchmarkSharpe':(statistics.mean(b)-rf_daily)/sd_b*annual if sufficient and sd_b>1e-12 else None,
        'informationRatio':statistics.mean(active_returns)/sd_active*annual if sufficient and sd_active>1e-12 else None,
        'trackingError':sd_active*annual*100 if sufficient else None,
        'beta':covariance/(sd_b**2) if sufficient and sd_b>1e-12 else None,
        'correlation':covariance/(sd_a*sd_b) if sufficient and sd_a>1e-12 and sd_b>1e-12 else None,
        'positiveDays':sum(x>0 for x in a)/len(a)*100,
        'benchmarkPositiveDays':sum(x>0 for x in b)/len(b)*100,
        'outperformDays':sum(x>0 for x in active_returns)/len(a)*100,
        'bestDay':max(a)*100, 'worstDay':min(a)*100,
        'benchmarkBestDay':max(b)*100, 'benchmarkWorstDay':min(b)*100,
    }
    months = {}
    for row in daily:
        month = row['date'][:7]
        entry = months.setdefault(month, {'month':month,'strategy':1.,'ndx':1.,'days':0})
        entry['strategy'] *= 1+row['strategy']
        entry['ndx'] *= 1+row['ndx']
        entry['days'] += 1
    monthly = [{'month':m['month'],'strategy':(m['strategy']-1)*100,'ndx':(m['ndx']-1)*100,
                'excess':(m['strategy']-m['ndx'])*100,'days':m['days']} for m in months.values()]
    return {'stats':stats, 'curve':curve, 'daily':daily, 'monthly':monthly,
            'from':active[0]['date'], 'through':active[-1]['date'], 'baseline':anchor['date'],
            'observations':len(daily), 'estimatedDays':sum(bool(row.get('estimated')) for row in active)}
