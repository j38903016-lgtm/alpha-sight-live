import unittest
from spx import batch_spx,add_spx_comparison
from performance import calculate
from freshness import series_freshness
from datetime import datetime,timezone

class BatchTests(unittest.TestCase):
    def payload(self):
        stamp='2026-11-11T16:20:30+00:00'
        return {'startDate':'2026-11-11','points':[{'date':'2026-11-10','strategyIndex':1,'benchmarkIndex':1,'baseline':True},{'date':'2026-11-11','strategyIndex':1.01,'benchmarkIndex':1.02,'estimated':True,'estimateSession':'intraday','observedAt':stamp,'batchId':stamp}],
            'synchronizedBatch':{'id':stamp,'observedAt':stamp,'quotes':{'SP:SPX':{'price':103,'change':3,'delaySeconds':600,'exchangeAt':None},'NASDAQ:NDX':{'price':102,'change':2,'delaySeconds':900,'exchangeAt':None}}},'feedStatus':{'observedAt':stamp},'lastUpdatedAt':stamp}
    def test_same_batch_replaces_separate_live_spx_and_preserves_delay(self):
        p=self.payload();spx=batch_spx(p,{'closes':{'2026-11-10':100},'price':999})
        r=calculate(p);add_spx_comparison(r,spx)
        self.assertAlmostEqual(r['curve'][-1]['spx'],3)
        rows,_=series_freshness(p,spx,r['curve'][-1],datetime(2026,11,11,16,21,tzinfo=timezone.utc))
        self.assertEqual(rows[0]['采集时间'],rows[1]['采集时间']);self.assertEqual(rows[1]['采集时间'],rows[2]['采集时间']);self.assertIn('10分钟',rows[2]['状态'])
    def test_different_batch_does_not_use_independent_quote(self):
        p=self.payload();p['synchronizedBatch']['id']='other'
        spx=batch_spx(p,{'closes':{'2026-11-10':100},'price':999})
        r=calculate(p);add_spx_comparison(r,spx);self.assertIsNone(r['curve'][-1]['spx'])

if __name__=='__main__':unittest.main()
