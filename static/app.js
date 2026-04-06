const yesChartContainer = document.getElementById("yes-chart");
const noChartContainer = document.getElementById("no-chart");
const healthStatus = document.getElementById("health-status");
const eventCount = document.getElementById("event-count");
const statsEventCount = document.getElementById("stats-event-count");
const eventList = document.getElementById("event-list");
const selectedTitle = document.getElementById("selected-title");
const selectedRange = document.getElementById("selected-range");
const yesChartTitle = document.getElementById("yes-chart-title");
const noChartTitle = document.getElementById("no-chart-title");
const tradeTableBody = document.getElementById("trade-table-body");
const statsTableBody = document.getElementById("stats-table-body");

const chartOptions = {
  layout: {
    background: { color: "#f7f0e8" },
    textColor: "#2d241d",
  },
  grid: {
    vertLines: { color: "rgba(90, 70, 52, 0.12)" },
    horzLines: { color: "rgba(90, 70, 52, 0.12)" },
  },
  rightPriceScale: {
    borderColor: "rgba(90, 70, 52, 0.3)",
  },
  timeScale: {
    borderColor: "rgba(90, 70, 52, 0.3)",
    timeVisible: true,
    secondsVisible: true,
  },
};

const yesChart = LightweightCharts.createChart(yesChartContainer, chartOptions);
const noChart = LightweightCharts.createChart(noChartContainer, chartOptions);

const yesSeries = yesChart.addCandlestickSeries({
  upColor: "#1f7a4d",
  downColor: "#b54a2a",
  borderVisible: false,
  wickUpColor: "#1f7a4d",
  wickDownColor: "#b54a2a",
});
const noSeries = noChart.addCandlestickSeries({
  upColor: "#1c5a80",
  downColor: "#93423b",
  borderVisible: false,
  wickUpColor: "#1c5a80",
  wickDownColor: "#93423b",
});

let selectedEventSlug = null;
let ws = null;
let reconnectTimer = null;
let overviewRefreshTimer = null;
let detailRefreshTimer = null;

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

function chooseDefaultEvent(events) {
  return (
    events.find((event) => event.status === "active" && event.trade_count > 0)?.event_slug ||
    events.find((event) => event.trade_count > 0)?.event_slug ||
    events[0]?.event_slug ||
    null
  );
}

function toChartData(candles) {
  return candles.map((candle) => ({
    time: candle.time,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
  }));
}

function formatTs(timestamp) {
  return new Date(timestamp * 1000).toLocaleString();
}

function renderEvents(events) {
  eventList.innerHTML = "";
  events.forEach((event) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "event-item";
    if (event.event_slug === selectedEventSlug) {
      button.classList.add("active");
    }
    button.innerHTML = `
      <strong>${event.title}</strong>
      <span>${formatTs(event.start_ts)} - ${formatTs(event.end_ts)}</span>
      <small>${event.trade_count} 笔成交</small>
    `;
    button.addEventListener("click", () => {
      selectedEventSlug = event.event_slug;
      renderEvents(events);
      loadEventDetail();
    });
    eventList.appendChild(button);
  });
}

function renderTrades(trades) {
  tradeTableBody.innerHTML = "";
  trades
    .slice(-50)
    .reverse()
    .forEach((trade) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${formatTs(trade.timestamp)}</td>
        <td>${trade.outcome}</td>
        <td>${trade.side}</td>
        <td>${(trade.price * 100).toFixed(1)}¢</td>
        <td>${trade.size.toFixed(2)}</td>
      `;
      tradeTableBody.appendChild(row);
    });
}

function renderStats(rows) {
  statsTableBody.innerHTML = "";
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.outcome}</td>
      <td>${row.bucket}</td>
      <td>${row.buy_threshold_cents}¢</td>
      <td>${row.sell_threshold_cents}¢</td>
      <td>${row.sample_size}</td>
      <td>${row.wins}</td>
      <td>${row.losses}</td>
      <td>${(row.win_rate * 100).toFixed(1)}%</td>
      <td>${row.avg_hold_seconds === null ? "-" : row.avg_hold_seconds}</td>
    `;
    statsTableBody.appendChild(tr);
  });
}

async function loadEventDetail() {
  if (!selectedEventSlug) {
    yesSeries.setData([]);
    noSeries.setData([]);
    tradeTableBody.innerHTML = "";
    return;
  }
  const [detail, yesCandles, noCandles, trades] = await Promise.all([
    fetchJson(`/api/events/${selectedEventSlug}`),
    fetchJson(`/api/events/${selectedEventSlug}/candles?outcome=Yes&bucket_seconds=1`),
    fetchJson(`/api/events/${selectedEventSlug}/candles?outcome=No&bucket_seconds=1`),
    fetchJson(`/api/events/${selectedEventSlug}/trades?limit=500&order=asc`),
  ]);

  const event = detail.event;
  selectedTitle.textContent = event.title;
  selectedRange.textContent = `${formatTs(event.start_ts)} - ${formatTs(event.end_ts)}`;
  yesChartTitle.textContent = `${event.yes_label} 1s K线 (${event.yes_trade_count} 笔)`;
  noChartTitle.textContent = `${event.no_label} 1s K线 (${event.no_trade_count} 笔)`;

  yesSeries.setData(toChartData(yesCandles.candles));
  noSeries.setData(toChartData(noCandles.candles));
  renderTrades(trades.trades);
}

async function refresh() {
  try {
    const [health, eventsPayload, statsPayload] = await Promise.all([
      fetchJson("/api/health"),
      fetchJson("/api/events"),
      fetchJson("/api/stats"),
    ]);

    healthStatus.textContent = health.collector_enabled ? "采集中" : "只读";
    eventCount.textContent = String(eventsPayload.events.length);
    statsEventCount.textContent = String(statsPayload.meta.event_count);
    renderStats(statsPayload.rows);

    const events = eventsPayload.events;
    if (!events.some((event) => event.event_slug === selectedEventSlug)) {
      selectedEventSlug = chooseDefaultEvent(events);
    } else if (!selectedEventSlug && events.length) {
      selectedEventSlug = chooseDefaultEvent(events);
    }
    renderEvents(events);
    await loadEventDetail();
  } catch (error) {
    console.error(error);
    healthStatus.textContent = "加载失败";
  }
}

async function refreshWithoutStats() {
  try {
    const [health, eventsPayload] = await Promise.all([
      fetchJson("/api/health"),
      fetchJson("/api/events"),
    ]);
    healthStatus.textContent = health.collector_enabled ? "采集中" : "只读";
    eventCount.textContent = String(eventsPayload.events.length);
    const events = eventsPayload.events;
    if (!events.some((event) => event.event_slug === selectedEventSlug)) {
      selectedEventSlug = chooseDefaultEvent(events);
    } else if (!selectedEventSlug && events.length) {
      selectedEventSlug = chooseDefaultEvent(events);
    }
    renderEvents(events);
    await loadEventDetail();
  } catch (error) {
    console.error(error);
  }
}

function scheduleOverviewRefresh(includeStats) {
  if (overviewRefreshTimer) {
    clearTimeout(overviewRefreshTimer);
  }
  overviewRefreshTimer = setTimeout(() => {
    overviewRefreshTimer = null;
    if (includeStats) {
      void refresh();
      return;
    }
    void refreshWithoutStats();
  }, 400);
}

function scheduleDetailRefresh() {
  if (detailRefreshTimer) {
    clearTimeout(detailRefreshTimer);
  }
  detailRefreshTimer = setTimeout(() => {
    detailRefreshTimer = null;
    void loadEventDetail();
  }, 250);
}

function connectRealtime() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${protocol}://${window.location.host}/ws`);

  ws.onopen = () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    healthStatus.textContent = "实时连接中";
  };

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "connected") {
      healthStatus.textContent = "实时已连接";
      return;
    }
    if (message.type === "ping") {
      return;
    }
    if (message.type === "refresh") {
      if (message.reason === "trade") {
        scheduleOverviewRefresh(false);
        if (!message.event_slug || message.event_slug === selectedEventSlug) {
          scheduleDetailRefresh();
        }
        return;
      }
      scheduleOverviewRefresh(true);
    }
  };

  ws.onclose = () => {
    healthStatus.textContent = "实时断开，重连中";
    reconnectTimer = setTimeout(connectRealtime, 1500);
  };

  ws.onerror = () => {
    ws.close();
  };
}

const resizeCharts = () => {
  const width = yesChartContainer.clientWidth;
  yesChart.resize(width, 320);
  noChart.resize(noChartContainer.clientWidth, 320);
};

window.addEventListener("resize", resizeCharts);

await refresh();
resizeCharts();
connectRealtime();
setInterval(refresh, 30000);
