import { useEffect, useRef } from "react";
import { loadChartJs } from "./loadChartJs.js";

/** canvas ref에 Chart.js 인스턴스 마운트 */
export function useChartInstance(config, deps = []) {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !config) return undefined;

    let cancelled = false;
    loadChartJs()
      .then((Chart) => {
        if (cancelled) return;
        chartRef.current?.destroy();
        chartRef.current = new Chart(canvas, config);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
      chartRef.current?.destroy();
      chartRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return canvasRef;
}
