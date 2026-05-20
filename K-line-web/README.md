# K-line-web

均线信号扫描器前端。展示扫描状态、最新信号表格、历史 K 线/均线图、信号标注和可调算法项。

## 当前行为

- 前端开发端口固定为 `8081`。
- Vite 将 `/api` 和 `/ws` 代理到 `http://127.0.0.1:9091`。
- 扫描状态不再轮询 `/api/scan/status`，而是订阅 `WS /ws/scan/status`；页面初始加载仍会读取一次最近状态。
- 模块更新状态订阅 `WS /ws/modules/sync`。
- 图表维度当前只开放“日 / 周 / 月”；“时”维度已暂时关闭。
- 日/周/月均以 K 线箱体展示；周/月会把一个周期聚合成一个 K 线点。
- 图表指标和 tooltip 展示收盘、涨跌幅、MA5、MA10、MA20。
- 底部信号列表展示最近多日信号，但同一天只展示一个信号。

## 启动

```powershell
npm install
npm run dev
```

访问：

```text
http://127.0.0.1:8081
```

Vite 会把 `/api` 和 `/ws` 代理到 `http://127.0.0.1:9091`。

## 构建

```powershell
npm run build
```

## 主要模块

- `src/main.tsx`：页面入口和数据加载。
- `src/components/SignalTable.tsx`：最新信号表格。
- `src/components/KLineChart.tsx`：历史 K 线、均线和信号标注图。
- `src/api/client.ts`：后端 API 调用。
- `src/types/labels.ts`：中文标签映射。
