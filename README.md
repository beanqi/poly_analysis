# Polymarket BTC 5m Monitor

用 Python 持续监控 Polymarket 上 `btc-updown-5m-*` 事件，自动把事件信息和逐笔成交写入 SQLite，并提供本地只读网页看双边 K 线和策略历史胜率。

## 功能

- 自动发现新的 5 分钟 BTC 事件
- 从公开 `trades` 接口拉取逐笔成交并去重入库
- 用公开 `market` WebSocket 做低延迟触发，加快补采
- SQLite 持久化保存事件和成交
- 本地网页查看最新事件、逐笔成交、双边 K 线
- 统计 10/20、20/40、30/60、30/70、30/80、30/90 六组买卖阈值
- 分析 `0-1m`、`1-2m`、`2-3m`、`3-4m`、`4-5m` 五个时间段的胜率

## 启动

```bash
python3 -m venv .venv
./.venv/bin/pip install fastapi uvicorn httpx websockets pytest
./.venv/bin/python main.py
```

启动后打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

SQLite 默认写到 `data/polymarket.sqlite3`。

## 测试

```bash
./.venv/bin/pytest
```

## 胜率统计口径

- 当某一边价格在指定时间段内第一次 `< 买入阈值` 时，视为买入
- 买入后若在该 5 分钟事件结束前第一次 `> 卖出阈值`，视为成功卖出
- 如果事件结束前没有触发卖出阈值，记为失败
- 统计按两边分别计算，同时给出合并样本
