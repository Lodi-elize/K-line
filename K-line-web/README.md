# K-line-web

均线信号扫描器前端。展示扫描状态、最新信号表格、历史 K 线/均线图、信号标注和可调算法项。

## 启动

```powershell
npm install
npm run dev
```

访问：

```text
http://127.0.0.1:5173
```

Vite 会把 `/api` 代理到 `http://127.0.0.1:8000`。

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
