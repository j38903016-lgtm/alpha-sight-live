"""S&P 500 price-index data and date-aligned comparisons."""
from datetime import datetime
from math import isfinite
from threading import Lock
from zoneinfo import ZoneInfo

import requests


EASTERN = ZoneInfo('America/New_York')
QUOTE_ALIGNMENT_SECONDS = 300


class SpxCloseCache:
    """Keep the completed closes when a refresh loses the upstream connection."""

    def __init__(self):
        self._lock = Lock()
        self._closes = {}

    def resolve(self, fresh):
        with self._lock:
            if fresh:
                self._closes.update(fresh['closes'])
            if not self._closes:
                return None
            return {
                **(fresh or {'price': None, 'intraday': False}),
                'closes': dict(self._closes),
                'history_only': fresh is None,
            }


def _market_time(timestamp):
    return datetime.fromtimestamp(timestamp, EASTERN)


def _positive(value):
    return isinstance(value, (int, float)) and isfinite(value) and value > 0


def load_spx(opening_date):
    """Read closes and the separately timestamped regular-session quote."""
    start = datetime.fromisoformat(opening_date).replace(tzinfo=EASTERN)
    for host in ('query1.finance.yahoo.com', 'query2.finance.yahoo.com'):
        try:
            response = requests.get(
                f'https://{host}/v8/finance/chart/%5EGSPC',
                params={'period1': int(start.timestamp()), 'period2': int(datetime.now().timestamp()),
                        'interval': '1d', 'includePrePost': 'false'},
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=5,
            )
            response.raise_for_status()
            return parse_spx(response.json()['chart']['result'][0])
        except (requests.RequestException, KeyError, ValueError, TypeError, IndexError, OSError):
            continue
    return None


def parse_spx(result):
    meta = result['meta']
    if meta['symbol'] != '^GSPC' or meta['instrumentType'] != 'INDEX':
        raise ValueError('Unexpected S&P 500 data')
    observed = _market_time(meta['regularMarketTime'])
    quote_date = observed.date().isoformat()
    regular = meta.get('currentTradingPeriod', {}).get('regular', {})
    session_start, session_end = regular.get('start'), regular.get('end')
    session_known = session_start is not None and session_end is not None
    session_date = _market_time(session_start).date() if session_known else None
    same_session = session_date == observed.date()
    quote_timestamp = observed.timestamp()
    closed = same_session and quote_timestamp >= session_end
    intraday = same_session and session_start <= quote_timestamp < session_end
    latest_bar_closed = closed or (session_date is not None and observed.date() < session_date)
    closes = {}
    for timestamp, value in zip(result['timestamp'], result['indicators']['quote'][0]['close'], strict=True):
        day = _market_time(timestamp).date().isoformat()
        if _positive(value) and (day < quote_date or (day == quote_date and latest_bar_closed)):
            closes[day] = value
    if not closes:
        raise ValueError('No completed SPX daily closes')
    price = meta.get('regularMarketPrice')
    previous = next((value for day, value in sorted(closes.items(), reverse=True) if day < quote_date), None)
    return {
        'closes': closes, 'observed': observed, 'price': price if _positive(price) else None,
        'intraday': intraday,
        'change': (price / previous - 1) * 100 if _positive(price) and previous else None,
    }


def add_spx_comparison(result, spx):
    """Use the strategy/NDX opening close and leave unmatched sessions empty."""
    closes = spx['closes'] if spx else {}
    baseline = closes.get(result['baseline'])
    peak = baseline
    prior_close = baseline
    for row, daily in zip(result['curve'][1:], result['daily'], strict=True):
        close = closes.get(row['date'])
        is_intraday_estimate = row['estimated'] and row.get('estimateSession') != 'after_hours'
        if is_intraday_estimate:
            close = None
            if spx and spx['intraday'] and row.get('observedAt'):
                strategy_time = datetime.fromisoformat(row['observedAt'])
                quote_time = spx['observed']
                same_batch = bool(row.get('batchId') and row.get('batchId') == spx.get('batch_id'))
                if (strategy_time.tzinfo is not None
                        and quote_time.date().isoformat() == row['date']
                        and (same_batch or (not row.get('batchId') and abs((strategy_time - quote_time).total_seconds()) <= QUOTE_ALIGNMENT_SECONDS))):
                    close = spx['price']

        row['spxEstimated'] = is_intraday_estimate and close is not None
        daily['spx'] = close / prior_close - 1 if close and prior_close and baseline else None
        prior_close = close
        row['spx'] = row['excessSpx'] = row['drawdownSpx'] = None
        if baseline and close:
            peak = max(peak, close)
            row['spx'] = (close / baseline - 1) * 100
            row['excessSpx'] = row['strategy'] - row['spx']
            row['drawdownSpx'] = (close / peak - 1) * 100

    anchor = result['curve'][0]
    for field in ('spx', 'excessSpx', 'drawdownSpx'):
        anchor[field] = 0.0 if baseline else None


def spx_summary_point(curve):
    """Use the current matched point or the last jointly confirmed session."""
    sessions = curve[1:]
    if sessions and sessions[-1]['spx'] is not None:
        return sessions[-1]
    return next((row for row in reversed(sessions)
                 if not row['estimated'] and row['spx'] is not None), None)


def batch_spx(payload, history):
    """Use Yahoo only for completed historical closes; live SPX comes with NAV/NDX."""
    batch = payload.get('synchronizedBatch')
    if not batch:
        return history
    point = payload['points'][-1]
    if not point.get('batchId') or point['batchId'] != batch.get('id') or point.get('observedAt') != batch.get('observedAt'):
        return {'closes':(history or {}).get('closes',{}),'price':None,'intraday':False,'history_only':True}
    quote = batch.get('quotes',{}).get('SP:SPX',{})
    if not _positive(quote.get('price')):
        return {'closes':(history or {}).get('closes',{}),'price':None,'intraday':False,'history_only':True}
    observed = datetime.fromisoformat(batch['observedAt'].replace('Z','+00:00')).astimezone(EASTERN)
    return {'closes':(history or {}).get('closes',{}),'price':quote['price'],'observed':observed,
            'intraday':point.get('estimateSession')=='intraday','change':quote.get('change'),
            'history_only':False,'batch_id':batch['id'],'source':'TradingView watchlist',
            'delay_seconds':quote.get('delaySeconds'),'exchange_at':quote.get('exchangeAt')}
