import unittest
from datetime import datetime, timezone
from freshness import series_freshness

class FreshnessTests(unittest.TestCase):
    def payload(self,stamp):
        return {'lastUpdatedAt':stamp,'points':[{'date':'2026-11-11','estimated':True,'estimateSession':'intraday','observedAt':stamp}],
                'feedStatus':{'observedAt':stamp,'benchmark':{'observedAt':stamp,'exchangeAt':None,'updateMode':'delayed_streaming_900'}}}
    def test_current_three_series_keep_delay_and_quote_time_distinct(self):
        now=datetime(2026,11,11,16,tzinfo=timezone.utc)
        rows,stale=series_freshness(self.payload('2026-11-11T15:59:30Z'),{'observed':now},{'date':'2026-11-11'},now)
        self.assertFalse(stale)
        self.assertEqual([row['对象'] for row in rows],['策略','纳指100','标普500'])
        self.assertEqual(rows[1]['行情时间'],'未提供')
        self.assertEqual(rows[1]['状态'],'延迟约15分钟')
    def test_old_upload_is_visible_and_unmatched_spx_uses_previous_close_label(self):
        rows,stale=series_freshness(self.payload('2026-11-11T14:37:30Z'),None,{'date':'2026-11-10'},datetime(2026,11,11,16,tzinfo=timezone.utc))
        self.assertTrue(stale)
        self.assertEqual(rows[0]['状态'],'采集已过期')
        self.assertEqual(rows[2]['状态'],'仅前收；当前未对齐')
    def test_aligned_but_old_quotes_are_not_relabelled_live(self):
        old=datetime(2026,11,11,14,37,tzinfo=timezone.utc)
        rows,_=series_freshness(self.payload(old.isoformat()),{'observed':old},{'date':'2026-11-11'},datetime(2026,11,11,16,tzinfo=timezone.utc))
        self.assertEqual(rows[2]['状态'],'报价已过期')

if __name__=='__main__':unittest.main()
