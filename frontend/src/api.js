const configuredBaseUrl = String(import.meta.env.VITE_API_BASE_URL || "")
  .trim()
  .replace(/\/+$/, "");

export const hasConfiguredApiBaseUrl = Boolean(configuredBaseUrl);

export function apiUrl(path) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${configuredBaseUrl}${normalizedPath}`;
}

const RETRYABLE_STATUS = new Set([502, 503, 504]);

function wait(ms, signal) {
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(signal.reason || new DOMException("Aborted", "AbortError"));
      },
      { once: true }
    );
  });
}

/** Render 무료 인스턴스가 깨어나는 동안의 일시적 게이트웨이 오류를 재시도합니다. */
export async function fetchApi(path, init, options = {}) {
  const retryDelays = options.retryDelays || [1000, 2500];
  let lastError;

  for (let attempt = 0; attempt <= retryDelays.length; attempt += 1) {
    try {
      const response = await fetch(apiUrl(path), init);
      if (!RETRYABLE_STATUS.has(response.status) || attempt === retryDelays.length) {
        return response;
      }
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      if (init?.signal?.aborted || attempt === retryDelays.length) throw error;
      lastError = error;
    }

    options.onRetry?.(attempt + 1, lastError);
    await wait(retryDelays[attempt], init?.signal);
  }

  throw lastError;
}
