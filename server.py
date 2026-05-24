from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import sqlite3
import os
import yaml

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
with open(CONFIG_PATH, "r") as f:
    _cfg = yaml.safe_load(f)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), _cfg["database"]["path"])


def _init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        '''CREATE TABLE IF NOT EXISTS people_count
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         direction TEXT,
         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'''
    )
    conn.commit()
    conn.close()


_init_db()

app = FastAPI()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/api/stats")
def get_stats():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM people_count WHERE direction='IN'")
    in_count = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) as cnt FROM people_count WHERE direction='OUT'")
    out_count = cursor.fetchone()["cnt"]
    cursor.execute("SELECT COUNT(*) as cnt FROM people_count")
    total = cursor.fetchone()["cnt"]
    conn.close()
    return {"in_count": in_count, "out_count": out_count, "total": total}


@app.get("/api/timeline")
def get_timeline():
    """Return recent events grouped by minute for real-time curve."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT strftime('%Y-%m-%d %H:%M', created_at) as minute,
                  SUM(CASE WHEN direction='IN' THEN 1 ELSE 0 END) as in_count,
                  SUM(CASE WHEN direction='OUT' THEN 1 ELSE 0 END) as out_count
           FROM people_count
           GROUP BY minute
           ORDER BY minute DESC LIMIT 60"""
    )
    rows = cursor.fetchall()
    conn.close()
    rows.reverse()
    return [
        {"time": row["minute"], "in_count": row["in_count"], "out_count": row["out_count"]}
        for row in rows
    ]


@app.get("/api/trend")
def get_trend():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT DATE(created_at) as day,
                  SUM(CASE WHEN direction='IN' THEN 1 ELSE 0 END) as in_count,
                  SUM(CASE WHEN direction='OUT' THEN 1 ELSE 0 END) as out_count
           FROM people_count
           GROUP BY DATE(created_at)
           ORDER BY day DESC LIMIT 30"""
    )
    rows = cursor.fetchall()
    conn.close()
    rows.reverse()
    return [
        {"day": row["day"], "in_count": row["in_count"], "out_count": row["out_count"]}
        for row in rows
    ]


@app.get("/", response_class=HTMLResponse)
def index():
    return """
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>People Counter</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, sans-serif; background: #f5f5f5; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        h1 { text-align: center; margin-bottom: 20px; color: #333; }
        .cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 30px; }
        .card { background: white; border-radius: 12px; padding: 25px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .card .label { font-size: 14px; color: #888; margin-bottom: 8px; }
        .card .value { font-size: 36px; font-weight: bold; }
        .card.in .value { color: #22c55e; }
        .card.out .value { color: #ef4444; }
        .card.total .value { color: #3b82f6; }
        .chart-container { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .chart-title { font-size: 16px; font-weight: 600; color: #555; margin-bottom: 12px; }
        .updated { text-align: center; color: #999; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>People Counter Dashboard</h1>
        <div class="cards">
            <div class="card in"><div class="label">IN</div><div class="value" id="in-count">0</div></div>
            <div class="card out"><div class="label">OUT</div><div class="value" id="out-count">0</div></div>
            <div class="card total"><div class="label">Total</div><div class="value" id="total-count">0</div></div>
        </div>
        <div class="chart-container">
            <div class="chart-title">Real-time Trend (last 60 min)</div>
            <canvas id="timelineChart"></canvas>
        </div>
        <div class="chart-container">
            <div class="chart-title">Daily Summary (last 30 days)</div>
            <canvas id="trendChart"></canvas>
        </div>
        <div class="updated" id="updated"></div>
    </div>

    <script>
        let timelineChart, trendChart;

        async function loadStats() {
            const res = await fetch("/api/stats");
            const data = await res.json();
            document.getElementById("in-count").textContent = data.in_count;
            document.getElementById("out-count").textContent = data.out_count;
            document.getElementById("total-count").textContent = data.total;
            document.getElementById("updated").textContent = "Updated: " + new Date().toLocaleTimeString();
        }

        async function loadTimeline() {
            const res = await fetch("/api/timeline");
            const data = await res.json();
            const labels = data.map(d => d.time);
            const inData = data.map(d => d.in_count);
            const outData = data.map(d => d.out_count);

            if (timelineChart) {
                timelineChart.data.labels = labels;
                timelineChart.data.datasets[0].data = inData;
                timelineChart.data.datasets[1].data = outData;
                timelineChart.update();
            } else {
                const ctx = document.getElementById("timelineChart").getContext("2d");
                timelineChart = new Chart(ctx, {
                    type: "line",
                    data: {
                        labels,
                        datasets: [
                            { label: "IN", data: inData, borderColor: "#22c55e", backgroundColor: "rgba(34,197,94,0.1)", fill: true, tension: 0.3, pointRadius: 3 },
                            { label: "OUT", data: outData, borderColor: "#ef4444", backgroundColor: "rgba(239,68,68,0.1)", fill: true, tension: 0.3, pointRadius: 3 }
                        ]
                    },
                    options: {
                        responsive: true,
                        scales: {
                            x: { ticks: { maxRotation: 45, font: { size: 10 } } },
                            y: { beginAtZero: true }
                        }
                    }
                });
            }
        }

        async function loadTrend() {
            const res = await fetch("/api/trend");
            const data = await res.json();
            const labels = data.map(d => d.day);
            const inData = data.map(d => d.in_count);
            const outData = data.map(d => d.out_count);

            if (trendChart) {
                trendChart.data.labels = labels;
                trendChart.data.datasets[0].data = inData;
                trendChart.data.datasets[1].data = outData;
                trendChart.update();
            } else {
                const ctx = document.getElementById("trendChart").getContext("2d");
                trendChart = new Chart(ctx, {
                    type: "bar",
                    data: {
                        labels,
                        datasets: [
                            { label: "IN", data: inData, backgroundColor: "#22c55e" },
                            { label: "OUT", data: outData, backgroundColor: "#ef4444" }
                        ]
                    },
                    options: {
                        responsive: true,
                        scales: {
                            x: { stacked: true },
                            y: { stacked: true, beginAtZero: true }
                        }
                    }
                });
            }
        }

        loadStats();
        loadTimeline();
        loadTrend();
        setInterval(loadStats, 5000);
        setInterval(loadTimeline, 10000);
        setInterval(loadTrend, 60000);
    </script>
</body>
</html>
"""

