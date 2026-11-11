from datetime import date
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from performance import calculate
from freshness import series_freshness
from spx import SpxCloseCache, add_spx_comparison, load_spx, spx_summary_point, batch_spx

PUBLIC_DATA_URL = 'https://alpha-sight-live-1023.j38903016.chatgpt.site/api/public-performance'
LIME, BLUE, TEAL, AMBER = '#C8FF70', '#7DACF7', '#43D9C4', '#FFB86B'

st.set_page_config(page_title='Alpha Sight · Strategy vs NDX and SPX', page_icon='📈', layout='wide')
st.markdown('<style>.block-container{max-width:1400px;padding-top:2rem}div[data-testid="stMetric"]{background:#17212D;padding:18px;border:1px solid #2A3544;border-radius:10px}h1{font-size:2rem}div[data-testid="stMetricValue"]{font-size:1.9rem}</style>', unsafe_allow_html=True)
st.caption('ALPHA SIGHT  /  PUBLIC PERFORMANCE')
st.title('Live Strategy × Nasdaq 100 × S&P 500')
st.caption('Normalized live performance and risk metrics. Account balances, positions, individual executions and access credentials are private.')


@st.cache_data(ttl=45, show_spinner=False)
def load_data():
    response = requests.get(PUBLIC_DATA_URL, timeout=20)
    response.raise_for_status()
    payload = response.json()
    if not payload.get('ready'):
        raise ValueError('The live performance baseline is not available yet')
    return payload


cached_spx = st.cache_data(ttl=45, show_spinner=False)(load_spx)


@st.cache_resource
def spx_close_cache():
    return SpxCloseCache()


def percent(value, suffix='%'):
    return '—' if value is None else f'{value:+.2f}{suffix}'


def figure(title, rows, series, y_title='Return (%)'):
    fig = go.Figure()
    for field, name, color in series:
        if not any(r.get(field) is not None for r in rows[1:]):
            continue
        first_estimate = next((i for i, r in enumerate(rows) if (
            r.get('spxEstimated') if field in ('spx', 'drawdownSpx') else
            r.get('estimated') and (field not in ('ndx', 'drawdownNdx') or r.get('estimateSession') != 'after_hours')
        )), len(rows))
        solid = rows[:first_estimate]
        if solid:
            fig.add_trace(go.Scatter(x=[r['date'] for r in solid],y=[r[field] for r in solid],name=name,
                                    mode='lines',connectgaps=False,line=dict(color=color,width=2.5),hovertemplate='%{x}<br>%{y:.2f}%<extra>'+name+'</extra>'))
        if first_estimate < len(rows):
            tail = rows[max(0,first_estimate-1):]
            fig.add_trace(go.Scatter(x=[r['date'] for r in tail],y=[r[field] for r in tail],name=name+' · Estimate',
                                    mode='lines+markers',connectgaps=False,line=dict(color=color,width=2.5,dash='dot'),marker=dict(size=5),
                                    hovertemplate='%{x}<br>%{y:.2f}%<extra>Provisional estimate</extra>'))
    ticks = sorted(set(round(i*(len(rows)-1)/min(4,max(1,len(rows)-1))) for i in range(min(5,len(rows)))))
    fig.update_layout(title=title,height=340,margin=dict(l=10,r=10,t=50,b=20),paper_bgcolor='rgba(0,0,0,0)',
                      plot_bgcolor='rgba(0,0,0,0)',font=dict(color='#CBD5E3'),legend=dict(orientation='h',y=1.12),
                      xaxis=dict(type='category',tickmode='array',tickvals=[rows[i]['date'] for i in ticks],ticktext=[rows[i]['date'] for i in ticks],showgrid=False),yaxis=dict(title=y_title,gridcolor='#273242',zerolinecolor='#516079'),hovermode='x unified')
    return fig


@st.fragment(run_every='60s')
def dashboard():
    try:
        payload = load_data()
    except (requests.RequestException, ValueError, KeyError):
        st.error('Verified strategy data is temporarily unavailable. Please refresh shortly.')
        return
    first = date.fromisoformat(payload['startDate'])
    last = date.fromisoformat(payload['points'][-1]['date'])
    last_is_estimated = payload['points'][-1].get('estimated',False)
    after_hours = payload['points'][-1].get('estimateSession') == 'after_hours'
    quality = 'After-hours estimate; not official TWR' if after_hours else ('Live P&L estimate; not official TWR' if last_is_estimated else 'Confirmed')
    st.caption(f"Latest strategy data: {last.isoformat()} ({quality}) · Official through {payload.get('officialThrough','—')}")
    if after_hours:
        observed = pd.Timestamp(payload['points'][-1]['observedAt']).tz_convert('America/New_York').strftime('%Y-%m-%d %H:%M:%S ET')
        method = ('净值变化扣除已知出入金' if payload['points'][-1].get('estimateMethod') == 'nav_change'
                  else '账户盈亏')
        st.info(f"{last.isoformat()} 虚线为截至 {observed} 的盘后{method}估算，基准采用当日已完成的 NDX 日K。"
                "晚间重置后的 Daily PnL 不作为当天收益。此值不是16:00正式收盘TWR，出入金时点尚未核验；IBKR Flex 日报到达后自动替换。")
    if payload.get('lastUpdatedAt'):
        received = pd.Timestamp(payload['lastUpdatedAt']).tz_convert('America/New_York')
        updated = received.strftime('%Y-%m-%d %H:%M:%S ET')
        st.caption(f"Latest data received: {updated} · This is not the return-curve date")
        if received.date() > last and received.weekday() < 5:
            st.info(f"数据接收时间：{updated}；收益曲线截至 {last.isoformat()}。"
                    "后续交易日的已核验收益尚未齐备，等待 IBKR Flex 日报自动补齐。"
                    "刷新页面不会生成缺失的日收益；深夜账户快照不能替代正式收盘收益。")
    controls = st.columns([2,2,2,2])
    full_period = controls[0].checkbox('Full live history', value=True)
    start = controls[1].date_input('Start date',value=first,format='YYYY-MM-DD',min_value=first,max_value=last,disabled=full_period)
    end = controls[2].date_input('End date',value=last,format='YYYY-MM-DD',min_value=first,max_value=last,disabled=full_period)
    include_estimated = controls[3].toggle('Include latest API estimates', value=True)
    if full_period:
        start, end = first, last
    if start > end:
        st.error('The start date must be on or before the end date.')
        return
    risk_free = st.number_input('Annual risk-free rate for Sharpe (%)',min_value=0.,max_value=30.,value=0.,step=.1)
    result = calculate(payload,start.isoformat(),end.isoformat(),include_estimated,risk_free/100)
    if not result:
        st.info('No matching strategy and index returns are available for this period.')
        return
    spx = batch_spx(payload, spx_close_cache().resolve(cached_spx(payload['points'][0]['date'])))
    add_spx_comparison(result, spx)
    stats = result['stats']
    st.caption(f"Period: {result['from']} → {result['through']} · {result['observations']} daily returns · Opening baseline: {result['baseline']} close · Earlier small-capital activity excluded")
    latest_day = result['daily'][-1]
    day_quality = '估算' if latest_day['estimated'] else '正式确认'
    spx_daily = latest_day['spx']
    st.caption(f"最新交易日 {latest_day['date']}（{day_quality}）：策略 {percent(latest_day['strategy']*100)} · NDX {percent(latest_day['ndx']*100)} · SPX {percent(spx_daily*100 if spx_daily is not None else None)}。")
    if spx and spx['price'] is not None:
        quote_time = spx['observed'].strftime('%Y-%m-%d %H:%M:%S ET')
        if spx.get('batch_id'):
            st.caption(f"同批采集：账户 × NDX × SPX · {quote_time} · TradingView watchlist；采集时间不代表交易所行情时间")
        else:
            st.caption(f"SPX {spx['price']:,.2f} ({percent(spx['change'])}) · Quote timestamp {quote_time} · Yahoo Finance · Quote may be delayed")
    latest_point = result['curve'][-1]
    spx_point = spx_summary_point(result['curve'])
    freshness_rows, stale_upload = series_freshness(payload, spx, spx_point)
    if stale_upload:
        st.warning('账户数据已超过3分钟没有成功更新。策略与NDX显示最后有效值，不能当作当前行情；系统恢复后自动续传。')
    st.dataframe(pd.DataFrame(freshness_rows), hide_index=True, use_container_width=True)
    st.caption('同批采集会一起更新三个对象；行情仍各有延迟，采集时间不是成交时间。缺少完整同批数据时保留上一有效批次，断线恢复后由后台自动续传。')
    if spx and spx['history_only']:
        st.caption('SPX 报价暂未更新，已完成的历史收盘继续显示。')
    if latest_point['spx'] is None:
        if spx_point:
            st.caption(f"SPX 暂无 {latest_point['date']} 的匹配数据。SPX 累计收益及超额收益截至 {spx_point['date']} 收盘。")
        else:
            st.caption('所选区间暂无可核对的 SPX 收益。')
    metrics = [
        ('Cumulative strategy return', percent(stats['cumulative'])),
        ('Cumulative Nasdaq 100', percent(stats['benchmark'])),
        ('Cumulative S&P 500', percent(spx_point['spx'] if spx_point else None)),
        ('Excess vs NDX · pp', percent(stats['excess'], ' pp')),
        ('Excess vs SPX · pp', percent(spx_point['excessSpx'] if spx_point else None, ' pp')),
    ]
    for column, (label, value) in zip(st.columns(len(metrics)), metrics):
        column.metric(label, value)
    st.plotly_chart(figure('Cumulative Returns',result['curve'],[('strategy','Strategy TWR',LIME),('ndx','Nasdaq 100',BLUE),('spx','S&P 500 (SPX)',AMBER)]),use_container_width=True)
    st.caption(f"Official TWR confirmed through {payload.get('officialThrough','—')}. All series use the same opening date. Current synchronized points share one collection batch; exchange delays can differ. {result['estimatedDays']} strategy sessions are provisional. Dashed estimates can be hidden.")
    a,b = st.columns(2)
    with a:
        st.plotly_chart(figure('Cumulative Excess Return',result['curve'],[('excess','Strategy − NDX',TEAL),('excessSpx','Strategy − SPX',AMBER)],'Percentage points'),use_container_width=True)
    with b:
        st.plotly_chart(figure('Drawdown Comparison',result['curve'],[('drawdownStrategy','Strategy',LIME),('drawdownNdx','NDX',BLUE),('drawdownSpx','SPX',AMBER)],'Drawdown (%)'),use_container_width=True)
    daily = go.Figure()
    for key,label,color in [('strategy','Strategy',LIME),('ndx','NDX',BLUE),('spx','SPX',AMBER)]:
        values = [r[key]*100 if r[key] is not None else None for r in result['daily']]
        if any(value is not None for value in values):
            daily.add_bar(x=[r['date'] for r in result['daily']],y=values,name=label,marker_color=color,hovertemplate='%{x}<br>%{y:.2f}%<extra>'+label+'</extra>')
    daily.update_layout(title='Daily Return Comparison',barmode='group',height=300,xaxis=dict(type='category'),yaxis_title='Daily return (%)',margin=dict(l=10,r=10,t=50,b=20),legend=dict(orientation='h'))
    st.plotly_chart(daily,use_container_width=True)
    left,right = st.columns([1.2,1])
    with left:
        st.subheader('Risk & Return Metrics')
        metrics = [
            ('Cumulative return','cumulative','benchmark',True),('Max drawdown','maxDrawdown','benchmarkMaxDrawdown',True),
            ('Annualized volatility','volatility','benchmarkVolatility',True),('Sharpe ratio','sharpe','benchmarkSharpe',False),
            ('Information ratio','informationRatio',None,False),('Tracking error','trackingError',None,True),
            ('Beta','beta',None,False),('Correlation','correlation',None,False),
            ('Positive days','positiveDays','benchmarkPositiveDays',True),
            ('Best day','bestDay','benchmarkBestDay',True),('Worst day','worstDay','benchmarkWorstDay',True),
        ]
        def value(key,is_percent):
            if key is None or stats.get(key) is None:
                return '—'
            return percent(stats[key]) if is_percent else f'{stats[key]:.2f}'
        table = [{'Metric':label,'Strategy':value(key,is_percent),'NDX':('1.00' if label in ('Beta','Correlation') else value(other,is_percent))} for label,key,other,is_percent in metrics]
        st.dataframe(pd.DataFrame(table),hide_index=True,use_container_width=True)
        st.caption(f"Based on {result['observations']} daily returns. Risk ratios require at least 5 complete sessions and use 252 sessions per year. Short-sample estimates change as new data arrives. Excess return is TWR minus NDX, rather than Jensen alpha.")
    with right:
        st.subheader('Monthly Returns')
        monthly = [{'Month':m['month'],'Strategy':percent(m['strategy']),'NDX':percent(m['ndx']),'Excess':percent(m['excess'],' pp'),'Sessions':m['days']} for m in result['monthly']]
        st.dataframe(pd.DataFrame(monthly),hide_index=True,use_container_width=True)
        st.caption('Selected live period only; first and last months may be partial.')
        st.metric('Days outperforming NDX',percent(stats['outperformDays']))
    st.caption('TradingView account snapshots + IBKR Flex official daily TWR · Public performance refreshes every minute · Account details remain private')


dashboard()
