"""Display freshness separately from return dates and exchange quote times."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")

def parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (TypeError, ValueError, AttributeError):
        return None

def age_seconds(value, now):
    parsed = parse_time(value)
    return max(0, (now - parsed).total_seconds()) if parsed else None

def display_time(value):
    parsed = parse_time(value)
    return parsed.astimezone(NY).strftime("%m-%d %H:%M:%S ET") if parsed else "未提供"

def series_freshness(payload, spx, matched_spx, now=None):
    now = now or datetime.now(timezone.utc)
    latest = payload["points"][-1]
    feed = payload.get("feedStatus") or {}
    benchmark = feed.get("benchmark") or {}
    observed = latest.get("observedAt")
    upload_time = feed.get("observedAt") or payload.get("lastUpdatedAt")
    upload_age = age_seconds(upload_time, now)
    live_estimate = latest.get("estimated") and latest.get("estimateSession") != "after_hours"
    stale = live_estimate and (upload_age is None or upload_age > 180)
    strategy_age = age_seconds(observed, now)
    strategy_status = ("采集已过期" if stale or (live_estimate and strategy_age is not None and strategy_age > 180)
                       else "盘中估算" if live_estimate else "盘后估算" if latest.get("estimated") else "正式收盘")
    mode = benchmark.get("updateMode") or ""
    delay = "延迟约15分钟" if "900" in mode else "行情可能延迟" if "delay" in mode else "行情时间未核实"
    ndx_observed = benchmark.get("observedAt")
    ndx_age = age_seconds(ndx_observed, now)
    ndx_status = "采集已过期" if stale or (ndx_age is not None and ndx_age > 180) else delay
    spx_time = spx["observed"].isoformat() if spx and spx.get("observed") else None
    spx_age = age_seconds(spx_time, now)
    matched = matched_spx and matched_spx["date"] == latest["date"]
    spx_status = ("仅前收；当前未对齐" if not matched else "报价已过期" if live_estimate and spx_age is not None and spx_age > 300
                  else "盘中估算" if live_estimate else "正式收盘")
    rows = [
        {"对象": "策略", "曲线截至": latest["date"], "采集时间": display_time(observed or upload_time),
         "行情时间": "账户快照", "状态": strategy_status},
        {"对象": "纳指100", "曲线截至": latest["date"], "采集时间": display_time(ndx_observed),
         "行情时间": display_time(benchmark.get("exchangeAt")), "状态": ndx_status},
        {"对象": "标普500", "曲线截至": matched_spx["date"] if matched_spx else "暂无匹配",
         "采集时间": "页面每分钟查询", "行情时间": display_time(spx_time), "状态": spx_status},
    ]
    batch = payload.get('synchronizedBatch')
    if batch and latest.get('batchId') == batch.get('id'):
        for row,symbol in zip(rows[1:],('NASDAQ:NDX','SP:SPX')):
            quote = batch.get('quotes',{}).get(symbol,{})
            delay = quote.get('delaySeconds')
            row['采集时间'] = display_time(batch.get('observedAt'))
            row['行情时间'] = display_time(quote.get('exchangeAt'))
            row['状态'] = '采集已过期' if stale else f'同批采集；延迟约{delay//60}分钟' if isinstance(delay,int) else '同批采集；行情时间未核实'
        rows[0]['状态'] = '采集已过期' if stale else '同批采集；账户估算'
    return rows, stale

