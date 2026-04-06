const yesChartContainer = document.getElementById("yes-chart");
const noChartContainer = document.getElementById("no-chart");
const healthStatus = document.getElementById("health-status");
const eventCount = document.getElementById("event-count");
const statsEventCount = document.getElementById("stats-event-count");
const eventList = document.getElementById("event-list");
const eventToggle = document.getElementById("event-toggle");
const selectedTitle = document.getElementById("selected-title");
const selectedRange = document.getElementById("selected-range");
const yesChartTitle = document.getElementById("yes-chart-title");
const noChartTitle = document.getElementById("no-chart-title");
const tradeTableBody = document.getElementById("trade-table-body");
const statsGroups = document.getElementById("stats-groups");
const archiveButton = document.getElementById("archive-button");
const archiveStatus = document.getElementById("archive-status");

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
let showAllEvents = false;

const VISIBLE_EVENT_COUNT = 10;

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (error) {
      // Ignore JSON parse failures and fall back to the status code.
    }
    throw new Error(detail);
  }
  return response.json();
}

async function fetchJson(url) {
  return requestJson(url);
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

function formatPercent(value) {
  return `${(value * 100).toFixed(1)}%`;
}

function setArchiveStatus(message, isError = false) {
  archiveStatus.textContent = message;
  archiveStatus.classList.toggle("is-error", isError);
}

function isSelectedInHistory(events) {
  return events.slice(VISIBLE_EVENT_COUNT).some((event) => event.event_slug === selectedEventSlug);
}

function createEventButton(event, events) {
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
    void loadEventDetail();
  });
  return button;
}

function renderEvents(events) {
  eventList.innerHTML = "";

  const recentEvents = events.slice(0, VISIBLE_EVENT_COUNT);
  const historyEvents = events.slice(VISIBLE_EVENT_COUNT);
  const autoExpanded = !showAllEvents && isSelectedInHistory(events);
  const expanded = showAllEvents || autoExpanded;

  recentEvents.forEach((event) => {
    eventList.appendChild(createEventButton(event, events));
  });

  if (expanded && historyEvents.length) {
    const divider = document.createElement("div");
    divider.className = "event-divider";
    divider.textContent = "更早的历史事件";
    eventList.appendChild(divider);
    historyEvents.forEach((event) => {
      eventList.appendChild(createEventButton(event, events));
    });
  }

  if (!historyEvents.length) {
    eventToggle.hidden = true;
    eventToggle.disabled = false;
    return;
  }

  eventToggle.hidden = false;
  eventToggle.disabled = autoExpanded;
  eventToggle.textContent = autoExpanded
    ? "历史事件已展开（当前选中事件在其中）"
    : expanded
      ? "收起历史事件"
      : `展开其余 ${historyEvents.length} 个事件`;
  eventToggle.onclick = () => {
    showAllEvents = !expanded;
    renderEvents(events);
  };
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

function renderStats(groups) {
  statsGroups.innerHTML = "";

  if (!groups.length) {
    const emptyState = document.createElement("div");
    emptyState.className = "empty-state";
    emptyState.textContent = "暂无可展示的策略统计";
    statsGroups.appendChild(emptyState);
    return;
  }

  groups.forEach((group) => {
    const section = document.createElement("section");
    section.className = "stats-buy-group";
    section.innerHTML = `
      <div class="stats-buy-header">
        <div>
          <p class="stats-buy-eyebrow">按买入价分组</p>
          <h3>${group.label}</h3>
        </div>
        <span>${group.strategies.length} 个卖出策略</span>
      </div>
    `;

    const strategyGrid = document.createElement("div");
    strategyGrid.className = "stats-strategy-grid";

    group.strategies.forEach((strategy) => {
      const card = document.createElement("article");
      card.className = "stats-card";
      card.innerHTML = `
        <div class="stats-card-header">
          <h4>${strategy.label}</h4>
          <span>${strategy.buckets.length} 个时间段</span>
        </div>
      `;

      const tableWrap = document.createElement("div");
      tableWrap.className = "table-wrap";
      const table = document.createElement("table");
      table.className = "stats-table";
      table.innerHTML = `
        <thead>
          <tr>
            <th>时间段</th>
            <th>Outcome</th>
            <th>样本</th>
            <th>胜利</th>
            <th>失败</th>
            <th>胜率</th>
            <th>平均持仓秒数</th>
          </tr>
        </thead>
      `;

      const tbody = document.createElement("tbody");
      strategy.buckets.forEach((bucket) => {
        bucket.rows.forEach((row) => {
          const tr = document.createElement("tr");
          if (row.outcome === "Combined") {
            tr.classList.add("is-combined");
          }
          tr.innerHTML = `
            <td>${bucket.bucket}</td>
            <td>${row.outcome}</td>
            <td>${row.sample_size}</td>
            <td>${row.wins}</td>
            <td>${row.losses}</td>
            <td>${formatPercent(row.win_rate)}</td>
            <td>${row.avg_hold_seconds === null ? "-" : row.avg_hold_seconds}</td>
          `;
          tbody.appendChild(tr);
        });
      });

      table.appendChild(tbody);
      tableWrap.appendChild(table);
      card.appendChild(tableWrap);
      strategyGrid.appendChild(card);
    });

    section.appendChild(strategyGrid);
    statsGroups.appendChild(section);
  });
}

async function loadEventDetail() {
  if (!selectedEventSlug) {
    selectedTitle.textContent = "K 线";
    selectedRange.textContent = "暂无选中事件";
    yesChartTitle.textContent = "YES";
    noChartTitle.textContent = "NO";
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
    statsEventCount.textContent = String(statsPayload.meta.events_with_samples);
    renderStats(statsPayload.groups || []);

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

async function archiveData() {
  const confirmed = window.confirm(
    "这会把当前 SQLite 数据归档到单独文件，并从空库重新开始统计。确认继续吗？",
  );
  if (!confirmed) {
    return;
  }

  archiveButton.disabled = true;
  archiveButton.textContent = "归档中...";
  setArchiveStatus("正在归档当前数据...");

  try {
    const payload = await requestJson("/api/archive", { method: "POST" });
    showAllEvents = false;
    selectedEventSlug = null;
    await refresh();
    setArchiveStatus(`已归档到 ${payload.archive_file}，当前统计已重置。`);
  } catch (error) {
    console.error(error);
    setArchiveStatus(`归档失败：${error.message}`, true);
  } finally {
    archiveButton.disabled = false;
    archiveButton.textContent = "归档并重置统计";
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
archiveButton.addEventListener("click", () => {
  void archiveData();
});

await refresh();
resizeCharts();
connectRealtime();
setInterval(refresh, 30000);
