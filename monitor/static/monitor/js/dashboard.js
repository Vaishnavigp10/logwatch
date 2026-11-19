(function () {
  const dataEl = document.getElementById("chart-data");
  if (!dataEl) return;

  let payload = JSON.parse(dataEl.textContent);
  const css = getComputedStyle(document.documentElement);
  const color = (name) => css.getPropertyValue(name).trim();

  function getCookie(name) {
    const match = document.cookie.split("; ").find((row) => row.startsWith(name + "="));
    return match ? decodeURIComponent(match.split("=")[1]) : "";
  }

  function post(url, data) {
    return fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": getCookie("csrftoken"),
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams(data || {}),
    });
  }

  // Shades the minutes the model flagged.
  const bandPlugin = {
    id: "anomalyBands",
    beforeDatasetsDraw(chart) {
      const { ctx, chartArea, scales } = chart;
      if (!chartArea || !scales.x) return;
      const idx = payload.series.anomaly_idx;
      const count = payload.series.labels.length;
      if (!idx.length || count < 2) return;
      const step = (chartArea.right - chartArea.left) / (count - 1);
      ctx.save();
      ctx.fillStyle = color("--danger-tint");
      idx.forEach((i) => {
        const x = scales.x.getPixelForValue(i);
        ctx.fillRect(x - step / 2, chartArea.top, step, chartArea.bottom - chartArea.top);
      });
      ctx.restore();
    },
  };

  let chart = null;
  const canvas = document.getElementById("timeline");

  function datasets(series) {
    return [
      { label: "All events", data: series.total, borderColor: "#3b4b5a", backgroundColor: "#3b4b5a" },
      { label: "Errors", data: series.errors, borderColor: color("--danger"), backgroundColor: color("--danger") },
      { label: "Failed logins", data: series.failed_logins, borderColor: color("--warn"), backgroundColor: color("--warn") },
    ].map((d) => Object.assign({ tension: 0.25, pointRadius: 0, pointHoverRadius: 4, borderWidth: 2 }, d));
  }

  function drawChart() {
    if (!canvas || typeof Chart === "undefined") return;
    chart = new Chart(canvas, {
      type: "line",
      data: { labels: payload.series.labels, datasets: datasets(payload.series) },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { maxTicksLimit: 8, color: color("--muted") } },
          y: { beginAtZero: true, grid: { color: color("--line") }, ticks: { color: color("--muted"), precision: 0 } },
        },
      },
      plugins: [bandPlugin],
    });
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function render() {
    const s = payload.stats;
    document.getElementById("headline").textContent = payload.headline;
    document.getElementById("subline").textContent = payload.subline;
    document.getElementById("stat-total").textContent = s.total_logs.toLocaleString();
    document.getElementById("stat-rate").textContent = s.error_rate;
    document.getElementById("stat-open").textContent = s.open_anomalies;
    document.getElementById("stat-last").textContent = s.last_anomaly;

    const list = document.getElementById("open-list");
    list.innerHTML = payload.open.length
      ? payload.open.map((a) =>
          `<li><a href="${a.url}"><span class="badge badge-${a.severity.toLowerCase()}">${a.severity}</span>` +
          `<span class="alert-time">${a.time}</span><span class="alert-cause">${escapeHtml(a.cause)}</span></a></li>`
        ).join("")
      : '<li class="muted-line">No open anomalies.</li>';

    if (chart) {
      chart.data.labels = payload.series.labels;
      chart.data.datasets = datasets(payload.series);
      chart.update();
    }
  }

  async function refresh() {
    const res = await fetch("/api/series/");
    payload = await res.json();
    render();
  }

  // Live stream
  const toggle = document.getElementById("live-toggle");
  const spikeBtn = document.getElementById("inject-spike");
  const attackBtn = document.getElementById("inject-attack");
  const status = document.getElementById("live-status");
  let timer = null;
  let pending = null;
  let busy = false;

  async function tick() {
    if (busy) return;
    busy = true;
    const mode = pending || "normal";
    pending = null;
    try {
      await post("/api/live-tick/", { mode });
      await refresh();
      status.textContent = mode === "normal"
        ? "Streaming normal traffic."
        : "Injected " + (mode === "spike" ? "an error spike" : "a login attack") + " into the latest minute.";
    } catch (err) {
      status.textContent = "Lost connection to the server. Stop and start the stream again.";
    }
    busy = false;
  }

  function setLive(on) {
    spikeBtn.disabled = !on;
    attackBtn.disabled = !on;
    toggle.textContent = on ? "Stop live stream" : "Start live stream";
    toggle.classList.toggle("live-on", on);
    if (on) {
      status.textContent = "Streaming normal traffic.";
      tick();
      timer = setInterval(tick, 3000);
    } else {
      clearInterval(timer);
      timer = null;
      status.textContent = "Live stream stopped.";
    }
  }

  if (toggle) {
    toggle.addEventListener("click", () => setLive(!timer));
    spikeBtn.addEventListener("click", () => { pending = "spike"; status.textContent = "Error spike queued for the next minute."; });
    attackBtn.addEventListener("click", () => { pending = "attack"; status.textContent = "Login attack queued for the next minute."; });
  }

  drawChart();
})();
