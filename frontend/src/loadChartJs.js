/** Chart.js CDN — 한 번만 로드 */
let loadPromise = null;

export function loadChartJs() {
  if (typeof window !== "undefined" && window.Chart) {
    return Promise.resolve(window.Chart);
  }
  if (loadPromise) return loadPromise;
  loadPromise = new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js";
    s.async = true;
    s.onload = () => resolve(window.Chart);
    s.onerror = () => reject(new Error("Chart.js load failed"));
    document.head.appendChild(s);
  });
  return loadPromise;
}
