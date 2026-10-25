from datetime import date
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from performance import calculate

PUBLIC_DATA_URL = 'https://alpha-sight-live-1023.j38903016.chatgpt.site/api/public-performance'
LIME, BLUE, TEAL = '#C8FF70', '#7DACF7', '#43D9C4'

st.set_page_config(page_title='Alpha Sight · 实盘策略与 Nasdaq 100', page_icon='📈', layout='wide')
st.markdown('<style>.block-container{max-width:1400px;padding-top:2rem}div[data-testid="stMetric"]{background:#17212D;padding:18px;border:1px solid #2A3544;border-radius:10px}h1{font-size:2rem}div[data-testid="stMetricValue"]{font-size:1.9rem}</style>', unsafe_allow_html=True)
st.caption('ALPHA SIGHT  /  PUBLIC PERFORMANCE')
st.title('实盘策略 × Nasdaq 100')
st.caption('仅公开正式实盘阶段的归一化收益与评估指标。账户金额、持仓、逐笔成交和访问凭证不对外提供。')


@st.cache_data(ttl=45, show_spinner=False)
def load_data():
    response = requests.get(PUBLIC_DATA_URL, timeout=20)
    response.raise_for_status()
    payload = response.json()
    if not payload.get('ready'):
        raise ValueError('正式实盘阶段的基准数据尚未就绪')
    return payload


def percent(value, suffix='%'):
    return '—' if value is None else f'{value:+.2f}{suffix}'


def figure(title, rows, series, y_title='收益率（%）'):
    fig = go.Figure()
    for field, name, color in series:
        first_estimate = next((i for i,r in enumerate(rows) if r.get('estimated')), len(rows))
        solid = rows[:first_estimate]
        if solid:
            fig.add_trace(go.Scatter(x=[r['date'] for r in solid],y=[r[field] for r in solid],name=name,
                                    mode='lines',line=dict(color=color,width=2.5),hovertemplate='%{x}<br>%{y:.2f}%<extra>'+name+'</extra>'))
        if first_estimate < len(rows):
            tail = rows[max(0,first_estimate-1):]
            fig.add_trace(go.Scatter(x=[r['date'] for r in tail],y=[r[field] for r in tail],name=name+' · API 暂估',
                                    mode='lines+markers',line=dict(color=color,width=2.5,dash='dot'),marker=dict(size=5),
                                    hovertemplate='%{x}<br>%{y:.2f}%<extra>API 暂估</extra>'))
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
        st.error('暂时无法读取已验证的策略数据，请稍后刷新。此处不会显示模拟数据。')
        return
    first = date.fromisoformat(payload['startDate'])
    last = date.fromisoformat(payload['points'][-1]['date'])
    last_is_estimated = payload['points'][-1].get('estimated',False)
    st.caption(f"最新可用策略数据：{last.isoformat()}（{'API 暂估，勾选下方开关即可纳入' if last_is_estimated else '官方确认'}）· 官方确认至 {payload.get('officialThrough','—')}")
    controls = st.columns([2,2,2,2])
    full_period = controls[0].checkbox('全部正式实盘阶段', value=True)
    start = controls[1].date_input('起始交易日',value=first,min_value=first,max_value=last,disabled=full_period)
    end = controls[2].date_input('结束交易日',value=last,min_value=first,max_value=last,disabled=full_period)
    include_estimated = controls[3].toggle('包含最新 API 暂估', value=True)
    if full_period:
        start, end = first, last
    if start > end:
        st.error('起始日不能晚于结束日。')
        return
    risk_free = st.number_input('Sharpe 无风险年利率（%）',min_value=0.,max_value=30.,value=0.,step=.1)
    result = calculate(payload,start.isoformat(),end.isoformat(),include_estimated,risk_free/100)
    if not result:
        st.info('所选区间没有可对齐的策略与指数收益。')
        return
    stats = result['stats']
    st.caption(f"统计区间 {result['from']} → {result['through']} · {result['observations']} 个日收益 · {result['baseline']} 收盘为期初基准 · 此前小资金交易均不计入")
    cards = st.columns(4)
    for column,label,value in zip(cards,['策略累计收益 · TWR','同期 Nasdaq 100','超额收益 · 百分点','策略最大回撤'],[stats['cumulative'],stats['benchmark'],stats['excess'],stats['maxDrawdown']]):
        column.metric(label,percent(value, ' pp' if '百分点' in label else '%'))
    st.plotly_chart(figure('累计收益对比',result['curve'],[('strategy','策略 TWR',LIME),('ndx','Nasdaq 100',BLUE)]),use_container_width=True)
    st.caption(f"官方 TWR 确认至 {payload.get('officialThrough','—')}，策略与 NDX 使用完全相同的期初基准。{result['estimatedDays']} 个交易日为 API 净值与当日盈亏核对后的暂估值，以虚线表示，可关闭。")
    a,b = st.columns(2)
    with a:
        st.plotly_chart(figure('累计超额收益',result['curve'],[('excess','策略 − NDX',TEAL)],'百分点'),use_container_width=True)
    with b:
        st.plotly_chart(figure('回撤对比',result['curve'],[('drawdownStrategy','策略',LIME),('drawdownNdx','NDX',BLUE)],'回撤（%）'),use_container_width=True)
    daily = go.Figure()
    for key,label,color in [('strategy','策略',LIME),('ndx','NDX',BLUE)]:
        daily.add_bar(x=[r['date'] for r in result['daily']],y=[r[key]*100 for r in result['daily']],name=label,marker_color=color,hovertemplate='%{x}<br>%{y:.2f}%<extra>'+label+'</extra>')
    daily.update_layout(title='每日收益对比',barmode='group',height=300,xaxis=dict(type='category'),yaxis_title='日收益（%）',margin=dict(l=10,r=10,t=50,b=20),legend=dict(orientation='h'))
    st.plotly_chart(daily,use_container_width=True)
    left,right = st.columns([1.2,1])
    with left:
        st.subheader('多维绩效评估')
        metrics = [
            ('累计收益','cumulative','benchmark',True),('最大回撤','maxDrawdown','benchmarkMaxDrawdown',True),
            ('年化波动率','volatility','benchmarkVolatility',True),('Sharpe 比率','sharpe','benchmarkSharpe',False),
            ('信息比率','informationRatio',None,False),('跟踪误差','trackingError',None,True),
            ('Beta','beta',None,False),('相关系数','correlation',None,False),
            ('正收益日比例','positiveDays','benchmarkPositiveDays',True),
            ('最好单日','bestDay','benchmarkBestDay',True),('最差单日','worstDay','benchmarkWorstDay',True),
        ]
        def value(key,is_percent):
            if key is None or stats.get(key) is None:
                return '—'
            return percent(stats[key]) if is_percent else f'{stats[key]:.2f}'
        table = [{'指标':label,'策略':value(key,is_percent),'NDX':('1.00' if label in ('Beta','相关系数') else value(other,is_percent))} for label,key,other,is_percent in metrics]
        st.dataframe(pd.DataFrame(table),hide_index=True,use_container_width=True)
        st.caption(f"基于 {result['observations']} 个日收益；至少 5 个完整交易日才计算风险比率，按 252 日年化。短样本估计会随新交易日变化。超额收益是 TWR 减 NDX，并非 Jensen Alpha。")
    with right:
        st.subheader('月度收益对比')
        monthly = [{'月份':m['month'],'策略':percent(m['strategy']),'NDX':percent(m['ndx']),'超额':percent(m['excess'],' pp'),'观察日':m['days']} for m in result['monthly']]
        st.dataframe(pd.DataFrame(monthly),hide_index=True,use_container_width=True)
        st.caption('只统计所选正式实盘区间，首尾月可能不完整。')
        st.metric('跑赢 NDX 的交易日比例',percent(stats['outperformDays']))
    st.caption('IBKR 真实 TWR + 同日 NDX · 公开收益数据每分钟更新 · 私人账户信息保留在受保护的后台')


dashboard()
