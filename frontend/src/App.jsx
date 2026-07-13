import React, { useState, useEffect, useLayoutEffect, useMemo, useRef, useId } from "react";
import { createRoot } from "react-dom/client";
import {
  TUNING_GOAL_OPTIONS,
  REFLOW_TUNING_GOAL_STORAGE_KEY,
  recommendTuneForGoal,
  validateProfileTune,
  deviationHintAgainstRecommended,
  readReflowTuningGoalInitial as _readReflowTuningGoalInitial
} from "./reflow_tune_engine.js";
import AnalysisReportSlideshow from "./AnalysisReportSlideshow.jsx";
import { apiUrl } from "./api.js";

// 매우 단순한 초기 Web UI:
// - Sn / Ag / Cu / Bi / In 정도만 입력받아 /api/analyze 로 POST
// - core 엔진은 기존 Python 코드(FastAPI)에서 그대로 사용

/** 쉬운 요약(eng): 요약 보고서는 접고, 온도·조직(상분석/IMC)만 펼침 */
const DEFAULT_SECTION_OPEN = {
  phase: true,
  riskAi: false,
  sources: false,
  roles: false,
  reflow: false,
  eng: false,
  lab: false
};

/** 연구소 모드: 상분석/IMC 블록만 펼침 — 나머지는 접음 */
const DEFAULT_SECTION_OPEN_LAB = {
  phase: true,
  riskAi: false,
  sources: false,
  roles: false,
  reflow: false,
  eng: false,
  lab: false
};
const SECTION_LAYOUT_VERSION = 5;

/** 리플로우 곡선·튜너가 사용할 고상/액상/기준피크: 하이브리드 엔진 vs 데이터 추론(3-NN) */
const REFLOW_MELT_BASIS_STORAGE_KEY = "alloyReflowMeltBasis";

/** 웹 리플로우 튜닝 기본값 (프리셋 "범용"과 동일) */
const DEFAULT_REFLOW_TUNE = {
  rampRate: 1.5,
  preheatTime: 90,
  overLiquidusTime: 25,
  coolRate: 2.0,
  peakMargin: 20.0
};

/** 즐겨찾기 API가 응답 없을 때 UI가 영구히 "불러오는 중..."에 머물지 않도록 */
const FAVORITES_FETCH_TIMEOUT_MS = 70000;
const FAVORITES_PUT_TIMEOUT_MS = 70000;

/** /api/about 실패 시에도 데모·보고용 신뢰 문구 표시 */
const TRUST_FALLBACK = {
  methodology: [
    "내장 합금 DB와 유사도 매칭으로 고상선·액상선·피크를 추정합니다.",
    "문헌·AI는 선택 사항이며 API 키·네트워크 상태에 따라 달라질 수 있습니다."
  ],
  data_sources: ["패키지에 포함된 참조 DB", "선택: Gemini, 공개 문헌 메타데이터"],
  alloy_rules: [
    {
      family: "Sn-Ag-Cu (SAC)",
      when: "Ag>0, Cu>0",
      phases: "Ag3Sn, Cu6Sn5(및 Cu3Sn 가능)",
      notes: "범용 무연 솔더. 냉각속도/TAL에 따라 조직 조절"
    },
    {
      family: "Sn-Cu",
      when: "Cu>0, Ag≈0",
      phases: "Cu6Sn5 중심, Cu 과량·장 TAL에서 Cu3Sn",
      notes: "Cu-rich일수록 계면 IMC 성장 관리 중요"
    },
    {
      family: "Sn-In",
      when: "In>=1",
      phases: "In 농화상 / In-Sn 금속간화합물",
      notes: "저온 공정·젖음 개선에 유리"
    },
    {
      family: "Sn-Bi",
      when: "Bi>=3",
      phases: "Bi 농화 공정/분산상 + Sn 기지",
      notes: "저융점화 장점, 고함량에서는 취성 주의"
    }
  ],
  disclaimer:
    "본 도구의 수치·텍스트는 참고용이며, 규제·계약·안전의 최종 근거로 사용하지 마십시오. 공인 시험·제조사 TDS를 따르십시오."
};

const ruleTh = {
  textAlign: "left",
  padding: "8px 10px",
  borderBottom: "1px solid var(--border-muted)",
  color: "var(--text-soft)",
  fontWeight: 700
};

const ruleTd = {
  padding: "8px 10px",
  borderBottom: "1px solid var(--bg-table-head)",
  color: "var(--text-primary)",
  verticalAlign: "top",
  lineHeight: 1.45
};

/** 목표 융점 표 등: wt% 객체 → Sn 88, Ag 3.5, … (청크 단위 줄바꿈은 WtPercentCompositionReadable) */
const DISPLAY_ELEMENT_ORDER = [
  "Sn",
  "Pb",
  "Ag",
  "Cu",
  "Bi",
  "In",
  "Sb",
  "Ni",
  "Zn",
  "Au",
  "Ga",
  "Ge",
  "P",
  "Fe",
  "Cr",
  "Co",
  "Mn",
  "Al",
  "Mg",
  "Ti",
  "Si"
];

function getWtPercentCompositionChunks(comp) {
  if (!comp || typeof comp !== "object") return [];
  const fmt = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n) || n <= 0) return null;
    const r = Math.round(n * 1000) / 1000;
    let s = r.toFixed(3);
    s = s.replace(/\.?0+$/, "");
    return s;
  };
  const keys = Object.keys(comp);
  const ordered = [
    ...DISPLAY_ELEMENT_ORDER.filter((el) => keys.includes(el)),
    ...keys.filter((k) => !DISPLAY_ELEMENT_ORDER.includes(k)).sort()
  ];
  const chunks = [];
  for (const el of ordered) {
    const s = fmt(comp[el]);
    if (s != null) chunks.push(`${el} ${s}`);
  }
  return chunks;
}

/** FastAPI 오류 detail(문자열·검증 배열·객체)을 UI에 표시 가능한 문자열로 변환 */
function formatApiDetail(detail, status = 500) {
  if (detail == null || detail === "") return `HTTP ${status}`;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (!item || typeof item !== "object") return String(item);
      const msg = item.msg != null ? String(item.msg) : JSON.stringify(item);
      const loc = Array.isArray(item.loc)
        ? item.loc.filter((x) => x !== "body").join(".")
        : "";
      return loc ? `${loc}: ${msg}` : msg;
    });
    return parts.length ? parts.join("; ") : `HTTP ${status}`;
  }
  if (typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {
      return `HTTP ${status}`;
    }
  }
  return String(detail);
}

/** 화면 총합(소수 둘째 자리 반올림)이 100.00%일 때만 분석 — 99.50% 등은 불가 */
function compositionTotalIsComplete(total) {
  return Number(Number(total).toFixed(2)) === 100;
}

function cleanCompositionWt(src) {
  return Object.fromEntries(
    Object.entries(src)
      .filter(([_, v]) => v !== "" && !Number.isNaN(Number(v)))
      .map(([k, v]) => [k, Number(v)])
  );
}

/** 조성 패널에 보이는 입력란(activeElems)만 합산·검증 — 주기율표만 눌러 comp에만 남은 값은 제외 */
function compositionWtForPanel(comp, activeElems) {
  const out = {};
  for (const el of activeElems || []) {
    const v = comp[el];
    if (v !== "" && v !== undefined && !Number.isNaN(Number(v))) {
      out[el] = Number(v);
    }
  }
  return out;
}

function compositionTotalPct(obj) {
  return Object.values(obj).reduce((s, v) => s + (Number(v) || 0), 0);
}

/** null이면 분석 가능; 문자열이면 버튼 비활성·제출 차단 사유 */
function compositionAnalyzeBlockReason(obj, label) {
  if (!Object.keys(obj).length) {
    return `${label}에 최소 1개 이상 원소(%)를 입력하세요.`;
  }
  const total = compositionTotalPct(obj);
  const hasPositive = Object.values(obj).some((v) => Number(v) > 0);
  if (!hasPositive || total <= 0) {
    return `${label}에 0보다 큰 wt%를 최소 1개 입력하세요. (현재 총합 ${total.toFixed(2)}%)`;
  }
  if (!compositionTotalIsComplete(total)) {
    return `${label} 총합이 ${total.toFixed(2)}%입니다. 총합이 100.00%가 되도록 맞춘 뒤 분석하세요.`;
  }
  return null;
}

/** 한 줄 문자열(복사·title 등) */
function formatWtPercentCompositionReadable(comp) {
  const chunks = getWtPercentCompositionChunks(comp);
  return chunks.length ? chunks.join(", ") : "—";
}

/** 표 셀용: 줄바꿈 시 원소+wt% 덩어리 단위로 다음 줄에 내려감(구분은 간격만, 점 문자 없음) */
function WtPercentCompositionReadable({ comp }) {
  const chunks = getWtPercentCompositionChunks(comp);
  if (!chunks.length) return "—";
  return (
    <span
      style={{
        display: "inline-flex",
        flexWrap: "wrap",
        alignItems: "baseline",
        columnGap: 10,
        rowGap: 4,
        maxWidth: "100%"
      }}
    >
      {chunks.map((text, i) => (
        <span key={`${text}-${i}`} style={{ whiteSpace: "nowrap" }}>
          {text}
        </span>
      ))}
    </span>
  );
}

/** solder_db `db_close_names` 등 — 백엔드가 ` · `로 이은 문자열을 덩어리 단위로만 줄바꿈(가운뎃점 미표시) */
function splitDbCloseLabels(raw) {
  if (raw == null) return [];
  const s = String(raw).trim();
  if (!s) return [];
  return s.split(/\s*·\s*/u).map((x) => x.trim()).filter(Boolean);
}

function DbCloseNamesReadable({ text }) {
  const parts = splitDbCloseLabels(text);
  if (!parts.length) return "—";
  return (
    <span
      style={{
        display: "inline-flex",
        flexWrap: "wrap",
        alignItems: "baseline",
        columnGap: 8,
        rowGap: 4,
        maxWidth: "100%"
      }}
    >
      {parts.map((p, i) => (
        <span
          key={i}
          style={{
            whiteSpace: "nowrap",
            fontSize: 11,
            color: i === 0 ? "var(--text-primary)" : "var(--text-secondary)"
          }}
        >
          {p}
        </span>
      ))}
    </span>
  );
}

/** 공통 클릭·실행 버튼: tactile-hit + 라벨 (주기율표 periodic-cell-btn과 중복 사용하지 않음) */
function TactileButton({ children, linkTone = false, className = "", labelStyle, type = "button", ...rest }) {
  const cls = ["tactile-hit", linkTone && "tactile-hit--link", className].filter(Boolean).join(" ");
  return (
    <button type={type} className={cls || undefined} {...rest}>
      <span className="tactile-hit-label" style={labelStyle}>
        {children}
      </span>
    </button>
  );
}

export default function App() {
  /** 첫 화면은 비워 둠 (SAC 기본값 자동 입력 없음) */
  const [comp, setComp] = useState({});
  const [compB, setCompB] = useState({});
  /** 입력란에 표시할 원소는 사용자가 선택(주기율표/추가 메뉴)한 것만 */
  const [activeElemsA, setActiveElemsA] = useState([]);
  const [activeElemsB, setActiveElemsB] = useState([]);
  const [addPickA, setAddPickA] = useState("");
  const [addPickB, setAddPickB] = useState("");
  const [mode, setMode] = useState("single"); // "single" | "compare"
  const [reportMode, setReportMode] = useState("eng"); // "eng" | "lab"
  const [literatureMode, setLiteratureMode] = useState("fast"); // "fast" | "deep"
  /** 젖음 대표 온도: auto = 액상선+30℃ 후 측정 DB(250–290℃)에 맞춤, 그 외 고정 온도 */
  const [wettingTempSelect, setWettingTempSelect] = useState("auto");
  const [showMetalsOnly, setShowMetalsOnly] = useState(true);
  const [favorites, setFavorites] = useState([]);
  const [selectedFavoriteName, setSelectedFavoriteName] = useState("");
  /** 비교 모드 조성 B용 즐겨찾기 선택 */
  const [selectedFavoriteNameB, setSelectedFavoriteNameB] = useState("");
  const [favSyncStatus, setFavSyncStatus] = useState("idle"); // idle | syncing | ok | offline | error
  const [favSyncMessage, setFavSyncMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [analysisStage, setAnalysisStage] = useState("");
  const [analysisElapsedSec, setAnalysisElapsedSec] = useState(0);
  const [analysisLogs, setAnalysisLogs] = useState([]);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [compareResult, setCompareResult] = useState(null);
  /** 온도별 젖음 표(250–290℃)는 기본 분석에 포함하지 않음 — 별도 로드 */
  const [wettingGridRows, setWettingGridRows] = useState(null);
  const [wettingGridLoading, setWettingGridLoading] = useState(false);
  const [wettingGridError, setWettingGridError] = useState("");
  /** 온도별 젖음 블록 접기/펼치기 — 기본은 접음 */
  const [wettingSectionOpen, setWettingSectionOpen] = useState(false);
  /** 리플로우: 피크 온도 + 구간 튜닝 (데스크톱 peak-based 템플릿과 동일) */
  const [reflowPeakUser, setReflowPeakUser] = useState(null);
  const [reflowTune, setReflowTune] = useState(DEFAULT_REFLOW_TUNE);
  const [reflowMeltBasis, setReflowMeltBasis] = useState(() => {
    if (typeof window === "undefined") return "hybrid";
    try {
      const v = window.localStorage.getItem(REFLOW_MELT_BASIS_STORAGE_KEY);
      if (v === "inference" || v === "hybrid") return v;
    } catch {
      /* noop */
    }
    return "hybrid";
  });
  const [sectionOpen, setSectionOpen] = useState(DEFAULT_SECTION_OPEN);
  const [resultPanelOpen, setResultPanelOpen] = useState(true);
  const [uiPrefsLoaded, setUiPrefsLoaded] = useState(false);
  const [aboutInfo, setAboutInfo] = useState(null);
  const [trustOpen, setTrustOpen] = useState(false);
  const [chartReportOpen, setChartReportOpen] = useState(false);
  /** 목표 융점 → POST /api/recommend_melt (기본 액상만; 고상은 옵션) */
  const [meltRecSolidus, setMeltRecSolidus] = useState("");
  const [meltRecLiquidus, setMeltRecLiquidus] = useState("");
  const [meltRecAlsoSolidusTarget, setMeltRecAlsoSolidusTarget] = useState(false);
  const [meltRecLoading, setMeltRecLoading] = useState(false);
  const [meltRecError, setMeltRecError] = useState("");
  const [meltRecResult, setMeltRecResult] = useState(null);
  /** idle | checking | yes | no — about+OpenAPI로 POST /api/recommend_melt 지원 여부 */
  const [meltSupport, setMeltSupport] = useState("idle");
  /** 비교 모드에서는 조성 A/B가 먼저 보이도록 기본 접음 */
  const [meltSearchOpen, setMeltSearchOpen] = useState(true);
  const [imcSubstrate, setImcSubstrate] = useState("Cu-OSP");
  const [imcTalMode, setImcTalMode] = useState("auto");
  const [imcTalRef, setImcTalRef] = useState("liq");
  const [imcTalDeltaC, setImcTalDeltaC] = useState(3);
  const [imcTalSec, setImcTalSec] = useState(35);
  const analysisLogScrollRef = useRef(null);
  /** 단일 분석 완료 후 KPI 카드 스크롤 앵커 */
  const resultKpiScrollRef = useRef(null);

  const showMeltRecommendPanel =
    Boolean(meltRecError) ||
    Boolean(meltRecResult?.meta?.disclaimer) ||
    (Array.isArray(meltRecResult?.candidates) && meltRecResult.candidates.length > 0);

  useEffect(() => {
    let cancelled = false;
    setMeltSupport("checking");

    const check = async () => {
      try {
        const [aboutRes, openApiRes] = await Promise.all([
          fetch(apiUrl(`/api/about?_=${Date.now()}`)),
          fetch(apiUrl(`/openapi.json?_=${Date.now()}`))
        ]);
        if (cancelled) return;
        let aboutOk = false;
        if (aboutRes.ok) {
          const j = await aboutRes.json();
          if (j && typeof j === "object" && j.product) {
            setAboutInfo(j);
            aboutOk = j.api_features?.recommend_melt === true;
          }
        }
        if (aboutOk) {
          setMeltSupport("yes");
          return;
        }
        if (!openApiRes.ok) {
          setMeltSupport("no");
          return;
        }
        const spec = await openApiRes.json();
        const has = !!(spec?.paths?.["/api/recommend_melt"]?.post);
        setMeltSupport(has ? "yes" : "no");
      } catch {
        if (!cancelled) setMeltSupport("no");
      }
    };
    check();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (mode === "compare") setMeltSearchOpen(false);
  }, [mode]);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    try {
      window.localStorage.setItem(REFLOW_MELT_BASIS_STORAGE_KEY, reflowMeltBasis);
    } catch {
      /* noop */
    }
    return undefined;
  }, [reflowMeltBasis]);

  // Popup(새 창) ↔ 메인 동기화 채널
  useEffect(() => {
    if (typeof window === "undefined") return undefined;

    const applyPayload = (payload) => {
      if (!payload || typeof payload !== "object") return;
      if (payload.type !== "apply_reflow_tune") return;
      if (!payload.tune || typeof payload.tune !== "object") return;

      const t = payload.tune;
      setReflowTune((prev) => ({
        ...prev,
        rampRate: Number.isFinite(Number(t.rampRate)) ? Number(t.rampRate) : prev.rampRate,
        preheatTime: Number.isFinite(Number(t.preheatTime)) ? Number(t.preheatTime) : prev.preheatTime,
        overLiquidusTime: Number.isFinite(Number(t.overLiquidusTime)) ? Number(t.overLiquidusTime) : prev.overLiquidusTime,
        coolRate: Number.isFinite(Number(t.coolRate)) ? Number(t.coolRate) : prev.coolRate,
        peakMargin: Number.isFinite(Number(t.peakMargin)) ? Number(t.peakMargin) : prev.peakMargin
      }));

      if (Number.isFinite(Number(payload.peakUser))) {
        setReflowPeakUser(Number(payload.peakUser));
      }
    };

    const onStorage = (ev) => {
      if (!ev || ev.key !== "reflowTuneSync") return;
      try {
        applyPayload(JSON.parse(String(ev.newValue || "")));
      } catch {
        /* noop */
      }
    };
    window.addEventListener("storage", onStorage);

    let bc = null;
    if (typeof BroadcastChannel !== "undefined") {
      bc = new BroadcastChannel("reflowTuneSync");
      bc.onmessage = (ev) => applyPayload(ev?.data);
    }

    return () => {
      window.removeEventListener("storage", onStorage);
      try {
        bc?.close?.();
      } catch {
        /* noop */
      }
    };
  }, []);

  const normalizeFavorites = (data) => {
    if (!Array.isArray(data)) return [];
    return data.filter(
      (x) =>
        x &&
        typeof x === "object" &&
        typeof x.name === "string" &&
        x.name.trim() &&
        x.comp &&
        typeof x.comp === "object"
    );
  };

  const saveFavoritesLocal = (nextFavorites) => {
    try {
      window.localStorage.setItem("alloyFavorites", JSON.stringify(nextFavorites));
    } catch {
      // ignore
    }
  };

  const syncFavoritesToServer = async (
    nextFavorites,
    { silent = false, allowEmpty = false } = {}
  ) => {
    if (!silent) {
      setFavSyncStatus("syncing");
      setFavSyncMessage("즐겨찾기 서버 동기화 중...");
    }
    const putAc = new AbortController();
    const putT = window.setTimeout(() => putAc.abort(), FAVORITES_PUT_TIMEOUT_MS);
    try {
      const res = await fetch(apiUrl("/api/favorites"), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          favorites: nextFavorites,
          allow_empty: allowEmpty
        }),
        signal: putAc.signal
      });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const j = await res.json();
          detail = j.detail || detail;
        } catch {
          // ignore
        }
        throw new Error(detail);
      }
      setFavSyncStatus("ok");
      setFavSyncMessage(`서버 동기화 완료 (${new Date().toLocaleTimeString()})`);
      return true;
    } catch (e) {
      const msg = String(e?.message || e || "알 수 없는 오류");
      if (e?.name === "AbortError" || /aborted|timeout/i.test(msg)) {
        setFavSyncStatus("offline");
        setFavSyncMessage("서버 응답 지연: 브라우저 저장소 기준으로 사용합니다.");
        return false;
      }
      if (/Failed to fetch|NetworkError|ECONNREFUSED/i.test(msg)) {
        setFavSyncStatus("offline");
        setFavSyncMessage("서버 연결 실패: 현재 브라우저에만 저장되었습니다.");
      } else {
        setFavSyncStatus("error");
        setFavSyncMessage(`동기화 실패: ${msg}`);
      }
      return false;
    } finally {
      window.clearTimeout(putT);
    }
  };

  // 프로필 로드 + 즐겨찾기: 서버(web_favorites.json) 우선 → 없으면 localStorage → 서버가 비었고 로컬만 있으면 업로드
  useEffect(() => {
    try {
      const profRaw = window.localStorage.getItem("alloyProfile");
      if (profRaw) {
        const p = JSON.parse(profRaw);
        let loadedReportMode = "eng";
        if (p.reportMode === "lab") {
          loadedReportMode = "lab";
          setReportMode("lab");
        } else if (p.reportMode === "eng") {
          loadedReportMode = "eng";
          setReportMode("eng");
        }
        if (p.literatureMode) setLiteratureMode(p.literatureMode === "deep" ? "deep" : "fast");
        if (p.wettingTempSelect === "auto" || ["250", "260", "270", "280", "290"].includes(p.wettingTempSelect)) {
          setWettingTempSelect(p.wettingTempSelect);
        }
        if (typeof p.showMetalsOnly === "boolean") {
          setShowMetalsOnly(p.showMetalsOnly);
        }
        if (typeof p.imcSubstrate === "string" && p.imcSubstrate) {
          setImcSubstrate(p.imcSubstrate);
        }
        if (typeof p.imcTalMode === "string" && p.imcTalMode) {
          setImcTalMode(p.imcTalMode);
        }
        if (typeof p.imcTalRef === "string" && p.imcTalRef) {
          setImcTalRef(p.imcTalRef);
        }
        if (typeof p.resultPanelOpen === "boolean") {
          setResultPanelOpen(p.resultPanelOpen);
        } else {
          setResultPanelOpen(true);
        }
        if (Number.isFinite(Number(p.imcTalDeltaC))) {
          setImcTalDeltaC(Math.max(0, Math.min(30, Number(p.imcTalDeltaC))));
        }
        if (Number.isFinite(Number(p.imcTalSec))) {
          setImcTalSec(Math.max(5, Math.min(180, Number(p.imcTalSec))));
        }
        if (p.reflowTune && typeof p.reflowTune === "object") {
          const rt = p.reflowTune;
          setReflowTune((prev) => ({
            ...prev,
            rampRate: Number.isFinite(Number(rt.rampRate))
              ? Math.max(0.3, Math.min(4, Number(rt.rampRate)))
              : prev.rampRate,
            preheatTime: Number.isFinite(Number(rt.preheatTime))
              ? Math.max(30, Math.min(180, Number(rt.preheatTime)))
              : prev.preheatTime,
            overLiquidusTime: Number.isFinite(Number(rt.overLiquidusTime))
              ? Math.max(10, Math.min(120, Number(rt.overLiquidusTime)))
              : prev.overLiquidusTime,
            coolRate: Number.isFinite(Number(rt.coolRate))
              ? Math.max(0.5, Math.min(8, Number(rt.coolRate)))
              : prev.coolRate,
            peakMargin: Number.isFinite(Number(rt.peakMargin))
              ? Math.max(5, Math.min(80, Number(rt.peakMargin)))
              : prev.peakMargin
          }));
        }
        if (
          Number(p.sectionLayoutVersion || 0) >= SECTION_LAYOUT_VERSION &&
          p.sectionOpen &&
          typeof p.sectionOpen === "object"
        ) {
          setSectionOpen((prev) => ({ ...prev, ...p.sectionOpen }));
        } else {
          setSectionOpen(
            loadedReportMode === "lab" ? DEFAULT_SECTION_OPEN_LAB : DEFAULT_SECTION_OPEN
          );
        }
      }
    } catch {
      // ignore
    } finally {
      setUiPrefsLoaded(true);
    }

    let cancelled = false;
    (async () => {
      /** 빠른 응답이면 "불러오는 중" 문구를 잠깐도 보이지 않게 해 첫 로드 불안 완화 */
      let hasLocalSeed = false;
      let loadingTimer = window.setTimeout(() => {
        if (!cancelled) {
          setFavSyncStatus("syncing");
          setFavSyncMessage("즐겨찾기 불러오는 중...");
        }
      }, 420);
      let fromLocal = [];
      try {
        const raw = window.localStorage.getItem("alloyFavorites");
        if (raw) {
          fromLocal = normalizeFavorites(JSON.parse(raw));
        }
      } catch {
        // ignore
      }

      if (fromLocal.length > 0 && !cancelled) {
        hasLocalSeed = true;
        setFavorites(fromLocal);
        setFavSyncStatus("syncing");
        setFavSyncMessage("저장된 즐겨찾기를 먼저 표시하고 서버와 동기화 중...");
      }

      if (hasLocalSeed && loadingTimer) {
        window.clearTimeout(loadingTimer);
        loadingTimer = null;
      }

      const getAc = new AbortController();
      const getT = window.setTimeout(() => getAc.abort(), FAVORITES_FETCH_TIMEOUT_MS);
      try {
        const res = await fetch(apiUrl("/api/favorites"), { signal: getAc.signal });
        window.clearTimeout(loadingTimer);
        loadingTimer = null;
        if (res.ok) {
          const j = await res.json();
          const fromServer = normalizeFavorites(j.favorites);
          if (cancelled) return;
          if (fromServer.length > 0) {
            setFavorites(fromServer);
            saveFavoritesLocal(fromServer);
            setFavSyncStatus("ok");
            setFavSyncMessage("서버 즐겨찾기 로드 완료");
            return;
          }
          if (fromLocal.length > 0) {
            await syncFavoritesToServer(fromLocal, { silent: false });
            return;
          }
          setFavorites([]);
          setFavSyncStatus("ok");
          setFavSyncMessage("저장된 즐겨찾기가 없습니다.");
          return;
        }
        // HTTP 오류: 아래에서 로컬 폴백
      } catch {
        // 네트워크·타임아웃(Abort)·JSON 오류 등 → 아래에서 로컬 폴백
      } finally {
        window.clearTimeout(getT);
        if (loadingTimer) window.clearTimeout(loadingTimer);
      }
      if (cancelled) return;
      setFavorites(fromLocal);
      if (fromLocal.length > 0) {
        setFavSyncStatus("offline");
        setFavSyncMessage("오프라인 모드: 브라우저 저장소 즐겨찾기 사용 중");
      } else {
        setFavSyncStatus("offline");
        setFavSyncMessage("오프라인 모드: 저장된 즐겨찾기가 없습니다.");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch(apiUrl("/api/about"))
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (!cancelled && j && typeof j === "object" && j.product) setAboutInfo(j);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // 프로필 저장
  useEffect(() => {
    if (!uiPrefsLoaded) return;
    try {
      const p = {
        reportMode,
        literatureMode,
        showMetalsOnly,
        sectionOpen,
        resultPanelOpen,
        sectionLayoutVersion: SECTION_LAYOUT_VERSION,
        imcSubstrate,
        imcTalMode,
        imcTalRef,
        imcTalDeltaC,
        imcTalSec,
        wettingTempSelect,
        reflowTune
      };
      window.localStorage.setItem("alloyProfile", JSON.stringify(p));
    } catch {
      // ignore
    }
  }, [
    reportMode,
    literatureMode,
    showMetalsOnly,
    sectionOpen,
    resultPanelOpen,
    uiPrefsLoaded,
    imcSubstrate,
    imcTalMode,
    imcTalRef,
    imcTalDeltaC,
    imcTalSec,
    wettingTempSelect,
    reflowTune
  ]);

  useEffect(() => {
    if (!selectedFavoriteName) return;
    if (!favorites.some((f) => f.name === selectedFavoriteName)) {
      setSelectedFavoriteName("");
    }
  }, [favorites, selectedFavoriteName]);

  useEffect(() => {
    if (!selectedFavoriteNameB) return;
    if (!favorites.some((f) => f.name === selectedFavoriteNameB)) {
      setSelectedFavoriteNameB("");
    }
  }, [favorites, selectedFavoriteNameB]);

  useLayoutEffect(() => {
    if (!loading) return;
    const el = analysisLogScrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [loading, analysisLogs, analysisStage]);

  useEffect(() => {
    if (mode !== "single" || !result || loading) return;
    const scrollToKpi = () => {
      const el = resultKpiScrollRef.current;
      if (!el?.isConnected) return;
      el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    };
    const t = window.setTimeout(scrollToKpi, 120);
    return () => window.clearTimeout(t);
  }, [result, mode, loading]);

  const handleChange = (elem, value) => {
    setComp((prev) => ({
      ...prev,
      [elem]: value === "" ? "" : Number(value)
    }));
  };

  const handleChangeB = (elem, value) => {
    setCompB((prev) => ({
      ...prev,
      [elem]: value === "" ? "" : Number(value)
    }));
  };

  const analyzeBlockReason = useMemo(() => {
    const a = compositionWtForPanel(comp, activeElemsA);
    if (mode === "single") {
      return compositionAnalyzeBlockReason(a, "조성 A");
    }
    const b = compositionWtForPanel(compB, activeElemsB);
    return compositionAnalyzeBlockReason(a, "조성 A") || compositionAnalyzeBlockReason(b, "조성 B");
  }, [comp, compB, mode, activeElemsA, activeElemsB]);

  const analyzeReady = analyzeBlockReason === null;

  const handleAnalyze = async () => {
    if (!analyzeReady) {
      if (analyzeBlockReason) setError(analyzeBlockReason);
      return;
    }
    setLoading(true);
    setAnalysisStage("입력값 검증 중...");
    setAnalysisElapsedSec(0);
    setAnalysisLogs([{ t: 0, msg: "분석 요청을 시작합니다." }]);
    setError("");
    setResult(null);
    setCompareResult(null);
    let stageTimer = null;
    let elapsedTimer = null;
    try {
      const startedAt = Date.now();
      const appendLog = (msg) => {
        const t = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
        setAnalysisLogs((prev) => [...prev.slice(-11), { t, msg }]);
      };
      const steps =
        mode === "single"
          ? [
              "조성 데이터 정규화 중...",
              "DB 최근접 합금/융점 계산 중...",
              "물성/리스크 평가 중...",
              reportMode === "lab"
                ? "연구소 보고서 본문 생성 중..."
                : "엔지니어 요약 생성 중...",
              "문헌/출처 정리 중..."
            ]
          : [
              "조성 A/B 정규화 중...",
              "각 조성의 DB 매칭/융점 계산 중...",
              "물성 비교 지표 계산 중...",
              "비교 결과 정리 중..."
            ];
      let idx = 0;
      elapsedTimer = window.setInterval(() => {
        setAnalysisElapsedSec(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
      }, 250);
      stageTimer = window.setInterval(() => {
        const msg = steps[Math.min(idx, steps.length - 1)];
        setAnalysisStage(msg);
        appendLog(msg);
        idx += 1;
      }, 900);

      const a = compositionWtForPanel(comp, activeElemsA);
      const b = compositionWtForPanel(compB, activeElemsB);

      const checkTotal = (obj, label) => {
        const msg = compositionAnalyzeBlockReason(obj, label);
        return msg ? { block: true, msg } : null;
      };

      if (mode === "single") {
        if (!Object.keys(a).length) {
          setError("조성 A에 최소 1개 이상 원소(%)를 입력하세요.");
          appendLog("입력 검증 실패: 조성 A가 비어 있습니다.");
          setLoading(false);
          return;
        }
        const totalCheck = checkTotal(a, "조성 A");
        if (totalCheck?.block) {
          setError(totalCheck.msg);
          appendLog(`입력 검증: ${totalCheck.msg}`);
          setLoading(false);
          return;
        }
      } else {
        if (!Object.keys(a).length || !Object.keys(b).length) {
          setError("비교 모드에서는 조성 A와 B 모두에 최소 1개 이상 원소(%)가 필요합니다.");
          appendLog("입력 검증 실패: 비교 모드에서 조성 A/B가 모두 필요합니다.");
          setLoading(false);
          return;
        }
        const checkA = checkTotal(a, "조성 A");
        const checkB = checkTotal(b, "조성 B");
        const blockMsg =
          (checkA && checkA.block && checkA.msg) || (checkB && checkB.block && checkB.msg) || null;
        if (blockMsg) {
          setError(blockMsg);
          appendLog(`입력 검증: ${blockMsg}`);
          setLoading(false);
          return;
        }
      }

      let res;
      if (mode === "single") {
        appendLog("POST /api/analyze 요청 전송");
        const payload = { comp: a, mode: reportMode, literature_mode: literatureMode };
        if (wettingTempSelect !== "auto") {
          payload.wetting_temp_c = Number(wettingTempSelect);
        }
        res = await fetch(apiUrl("/api/analyze"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
      } else {
        appendLog("POST /api/compare 요청 전송");
        const payload = { comp_a: a, comp_b: b, literature_mode: literatureMode };
        if (wettingTempSelect !== "auto") {
          payload.wetting_temp_c = Number(wettingTempSelect);
        }
        res = await fetch(apiUrl("/api/compare"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
      }

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const detail = formatApiDetail(data.detail, res.status);
        appendLog(`서버 오류 응답: ${detail}`);
        throw new Error(detail);
      }
      setAnalysisStage("응답 데이터 반영 중...");
      appendLog("서버 응답 수신, 결과 반영 중...");
      const data = await res.json();
      if (mode === "single") {
        setResult(data);
        setWettingGridRows(null);
        setWettingGridError("");
        setWettingSectionOpen(false);
        setResultPanelOpen(true);
        setSectionOpen(reportMode === "lab" ? DEFAULT_SECTION_OPEN_LAB : DEFAULT_SECTION_OPEN);
      } else {
        setCompareResult(data);
        setResultPanelOpen(true);
      }
      appendLog("분석 완료");
    } catch (e) {
      let msg = String(e.message || e);
      if (
        /failed to fetch|networkerror|load failed|fetch/i.test(msg) ||
        msg === "Failed to fetch"
      ) {
        msg +=
          "\n\n백엔드(127.0.0.1:8000)에 연결되지 않았습니다.\n• start_all.bat 실행 후 그 창을 열어 둔 채 새로고침\n• 또는 run_api_server.bat → http://localhost:8000/";
      }
      setError(msg);
      setAnalysisLogs((prev) => [
        ...prev.slice(-11),
        { t: analysisElapsedSec, msg: `오류: ${String(e.message || e)}` }
      ]);
    } finally {
      if (stageTimer) window.clearInterval(stageTimer);
      if (elapsedTimer) window.clearInterval(elapsedTimer);
      setAnalysisStage("");
      setLoading(false);
    }
  };

  const handleReset = () => {
    if (loading) return;
    setComp({});
    setCompB({});
    setActiveElemsA([]);
    setActiveElemsB([]);
    setAddPickA("");
    setAddPickB("");
    setSelectedFavoriteName("");
    setSelectedFavoriteNameB("");
    setError("");
    setResult(null);
    setCompareResult(null);
    setWettingGridRows(null);
    setWettingGridError("");
    setWettingSectionOpen(false);
    setReflowPeakUser(null);
    setReflowTune(DEFAULT_REFLOW_TUNE);
    setWettingTempSelect("auto");
    setAnalysisStage("");
    setAnalysisElapsedSec(0);
    setAnalysisLogs([]);
    setResultPanelOpen(true);
    setSectionOpen(reportMode === "lab" ? DEFAULT_SECTION_OPEN_LAB : DEFAULT_SECTION_OPEN);
  };

  const loadWettingGrid = async () => {
    if (!result?.norm || typeof result.norm !== "object") return;
    setWettingGridLoading(true);
    setWettingGridError("");
    try {
      const res = await fetch(apiUrl("/api/wetting_grid"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ comp: result.norm })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(formatApiDetail(data.detail, res.status));
      }
      const rows = Array.isArray(data.wetting_by_temp) ? data.wetting_by_temp : [];
      setWettingGridRows(rows);
      setWettingSectionOpen(true);
    } catch (e) {
      setWettingGridError(String(e.message || e));
      setWettingGridRows(null);
    } finally {
      setWettingGridLoading(false);
    }
  };

  const runMeltRecommend = async () => {
    setMeltRecError("");
    setMeltRecResult(null);
    // Sn1Ag0.8Cu8In10Bi 근처 SAC-In-Bi: Ag·Cu·In·Bi 스윕, 나머지 Sn.
    // 세밀한 0.1% 격자(1225점)는 융점 계산만 수분 걸려 UI가 멈춘 것처럼 보이므로,
    // 응답 시간을 위해 완만한 step(81점 전후)으로 스윕한다.
    const fixed_comp = {};
    const free_axes = [
      { element: "Ag", min: 0.8, max: 1.2, step: 0.2 },
      { element: "Cu", min: 0.6, max: 1.0, step: 0.2 },
      { element: "In", min: 5, max: 11, step: 3 },
      { element: "Bi", min: 8, max: 14, step: 3 }
    ];
    const balance_element = "Sn";
    const max_grid_points = 15_000;
    const solidus_tolerance_c = 20;
    const liquidus_tolerance_c = 20;
    const solidusTrim = String(meltRecSolidus || "").trim();
    const liquidusTrim = String(meltRecLiquidus || "").trim();
    let solidus_c = null;
    let liquidus_c = null;
    if (!meltRecAlsoSolidusTarget) {
      liquidus_c = liquidusTrim === "" ? null : Number(meltRecLiquidus);
      if (liquidus_c === null) {
        setMeltRecError("목표 액상(℃)을 입력하세요.");
        return;
      }
      if (!Number.isFinite(liquidus_c)) {
        setMeltRecError("목표 액상 온도가 숫자가 아닙니다.");
        return;
      }
    } else {
      solidus_c = solidusTrim === "" ? null : Number(meltRecSolidus);
      liquidus_c = liquidusTrim === "" ? null : Number(meltRecLiquidus);
      if (solidus_c === null && liquidus_c === null) {
        setMeltRecError("목표 고상(℃) 또는 액상(℃) 중 하나 이상을 입력하세요.");
        return;
      }
      if (solidus_c !== null && !Number.isFinite(solidus_c)) {
        setMeltRecError("목표 고상 온도가 숫자가 아닙니다.");
        return;
      }
      if (liquidus_c !== null && !Number.isFinite(liquidus_c)) {
        setMeltRecError("목표 액상 온도가 숫자가 아닙니다.");
        return;
      }
    }
    setMeltRecLoading(true);
    try {
      const res = await fetch(apiUrl("/api/recommend_melt"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fixed_comp,
          free_axes,
          balance_element,
          target: {
            solidus_c,
            solidus_tolerance_c,
            liquidus_c,
            liquidus_tolerance_c
          },
          max_results: 10,
          max_db_similar_alloys: 12,
          max_db_registered_in_candidates: 4,
          // 고상·액상 둘 다 지정 시 true면 한 축만 맞춰도 상위(액상만 맞고 고상은 어긋나기 쉬움) → |Δ고상|+|Δ액상| 합으로 정렬
          rank_match_any_axis: false,
          max_grid_points
        })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        let detail = formatApiDetail(data.detail, res.status);
        if (res.status === 405) {
          detail =
            "HTTP 405 — 백엔드에 POST /api/recommend_melt 없음. 127.0.0.1:8000에서 최신 python api_server.py 실행 확인.";
        }
        throw new Error(detail);
      }
      setMeltRecResult(data);
      const cand = Array.isArray(data?.candidates) ? data.candidates : [];
      if (cand.length === 0 && !data?.meta?.disclaimer) {
        setMeltRecError("탐색은 끝났지만 후보 행이 없습니다. 목표 온도·허용 범위를 넓히거나 백엔드 로그를 확인하세요.");
      }
    } catch (e) {
      let msg = String(e.message || e);
      if (
        /failed to fetch|networkerror|load failed|fetch/i.test(msg) ||
        msg === "Failed to fetch"
      ) {
        msg +=
          "\n\n백엔드(127.0.0.1:8000)에 연결되지 않았습니다. start_all.bat 또는 run_api_server.bat 실행 후 새로고침하세요.";
      }
      setMeltRecError(msg);
    } finally {
      setMeltRecLoading(false);
    }
  };

  useEffect(() => {
    if (!result) return;
    const name = pickPresetName(result);
    const pset = { ...REFLOW_PRESETS.범용, ...(REFLOW_PRESETS[name] || {}) };
    setReflowTune({
      rampRate: pset.ramp_rate,
      preheatTime: pset.preheat_time,
      overLiquidusTime: pset.over_liquidus_time,
      coolRate: pset.cool_rate,
      peakMargin: pset.peak_margin
    });
  }, [result]);

  useEffect(() => {
    if (!result) return;
    const md = getReflowMeltDisplay(result, reflowMeltBasis);
    if (Number.isFinite(md.modelPeak)) setReflowPeakUser(Number(md.modelPeak));
  }, [result, reflowMeltBasis]);

  const reflowProfile = useMemo(() => {
    if (!result) return null;
    try {
      return buildPeakProfilePoints(result, reflowTune, reflowPeakUser, reflowMeltBasis);
    } catch {
      return null;
    }
  }, [result, reflowTune, reflowPeakUser, reflowMeltBasis]);

  const reflowMeltDisplay = useMemo(
    () => (result ? getReflowMeltDisplay(result, reflowMeltBasis) : null),
    [result, reflowMeltBasis]
  );

  const imcProfileMeltOverride = useMemo(() => {
    if (reflowMeltBasis !== "inference" || !result) return null;
    const inf = getAlloyInferenceMelt(result);
    if (!inf) return null;
    return { solidus: inf.solidus, liquidus: inf.liquidus };
  }, [reflowMeltBasis, result]);

  useEffect(() => {
    if (!result) return;
    if (reflowMeltBasis === "inference" && !getAlloyInferenceMelt(result)) {
      setReflowMeltBasis("hybrid");
    }
  }, [result, reflowMeltBasis]);

  const reflowPeakEffective = Number(reflowProfile?.meta?.peak ?? result?.peak ?? 0);

  const handleElemClick = (target, elem) => {
    const cur = target === "A" ? comp[elem] ?? "" : compB[elem] ?? "";
    const input = window.prompt(`${target} - ${elem} (%) 값 입력`, cur === "" ? "" : String(cur));
    if (input === null) return;
    const v = Number(input);
    if (!Number.isFinite(v) || v < 0) {
      setError("0 이상의 숫자를 입력하세요.");
      return;
    }
    if (target === "A") {
      setActiveElemsA((prev) => (prev.includes(elem) ? prev : [...prev, elem]));
      setComp((prev) => ({ ...prev, [elem]: v }));
    } else {
      setActiveElemsB((prev) => (prev.includes(elem) ? prev : [...prev, elem]));
      setCompB((prev) => ({ ...prev, [elem]: v }));
    }
  };

  const addElemRowA = (el) => {
    if (!el || activeElemsA.includes(el)) return;
    setActiveElemsA((prev) => [...prev, el]);
    setComp((prev) => ({ ...prev, [el]: prev[el] ?? "" }));
  };

  const addElemRowB = (el) => {
    if (!el || activeElemsB.includes(el)) return;
    setActiveElemsB((prev) => [...prev, el]);
    setCompB((prev) => ({ ...prev, [el]: prev[el] ?? "" }));
  };

  const removeElemRowA = (el) => {
    setActiveElemsA((prev) => prev.filter((x) => x !== el));
    setComp((prev) => {
      const next = { ...prev };
      delete next[el];
      return next;
    });
  };

  const removeElemRowB = (el) => {
    setActiveElemsB((prev) => prev.filter((x) => x !== el));
    setCompB((prev) => {
      const next = { ...prev };
      delete next[el];
      return next;
    });
  };

  const autoFillSn = (target) => {
    const src = target === "A" ? comp : compB;
    const others = Object.entries(src).reduce(
      (sum, [k, v]) => (k === "Sn" ? sum : sum + (Number(v) || 0)),
      0
    );
    if (others >= 100) {
      setError(`Sn 외 합계 ${others.toFixed(2)}% >= 100% 입니다.`);
      return;
    }
    const snVal = Number((100 - others).toFixed(4));
    if (target === "A") {
      setActiveElemsA((prev) => (prev.includes("Sn") ? prev : [...prev, "Sn"]));
      setComp((prev) => ({ ...prev, Sn: snVal }));
    } else {
      setActiveElemsB((prev) => (prev.includes("Sn") ? prev : [...prev, "Sn"]));
      setCompB((prev) => ({ ...prev, Sn: snVal }));
    }
  };

  const solderElems = [
    "Sn",
    "Ag",
    "Cu",
    "Bi",
    "In",
    "Sb",
    "Ni",
    "P",
    "Zn",
    "Pb",
    "Au",
    "Pd",
    "Pt",
    "Al",
    "Ga",
    "Ge",
    "Fe",
    "Co",
    "Mn",
    "Mo",
    "Se",
    "Te"
  ];

  const allElems = [
    "H",
    "Li",
    "Be",
    "B",
    "C",
    "N",
    "O",
    "F",
    "Ne",
    "Na",
    "Mg",
    "Al",
    "Si",
    "P",
    "S",
    "Cl",
    "Ar",
    ...solderElems.filter((x) => !["Al"].includes(x))
  ];

  const elemList = showMetalsOnly ? solderElems : allElems;

  /** 이름 기준 숫자 인식 정렬 (22, 48, 75, 75-1, 75-2, 86 …) */
  const favoritesSorted = useMemo(
    () =>
      [...favorites].sort((a, b) =>
        String(a.name).localeCompare(String(b.name), undefined, {
          numeric: true,
          sensitivity: "base"
        })
      ),
    [favorites]
  );

  /** 비교 모드: 한쪽이라도 입력 중인 원소만 elemList 순 — 0%·미입력 placeholder 행 없음 */
  const compareElemVisible = (el, side) => {
    const active = side === "A" ? activeElemsA : activeElemsB;
    const composition = side === "A" ? comp : compB;
    if (!active.includes(el)) return false;
    const v = composition[el];
    if (v === "" || v === undefined) return true;
    const n = Number(v);
    return Number.isFinite(n) && n > 0;
  };

  /** 비교 모드: 열마다 보이는 원소만 elemList 순 — 빈 칸·줄 맞춤 없이 아래로 붙임 */
  const compareVisibleElemsA = useMemo(
    () => elemList.filter((el) => compareElemVisible(el, "A")),
    [activeElemsA, comp, elemList]
  );
  const compareVisibleElemsB = useMemo(
    () => elemList.filter((el) => compareElemVisible(el, "B")),
    [activeElemsB, compB, elemList]
  );

  const panelWtA = useMemo(() => compositionWtForPanel(comp, activeElemsA), [comp, activeElemsA]);
  const panelWtB = useMemo(() => compositionWtForPanel(compB, activeElemsB), [compB, activeElemsB]);
  const totalA = compositionTotalPct(panelWtA);
  const totalB = compositionTotalPct(panelWtB);
  const compositionAHasInput = useMemo(
    () => Object.values(panelWtA).some((v) => Number(v) > 0),
    [panelWtA]
  );
  const compositionBHasInput = useMemo(
    () => Object.values(panelWtB).some((v) => Number(v) > 0),
    [panelWtB]
  );

  const renderCompareComposeInputRow = (el, side) => {
    const composition = side === "A" ? comp : compB;
    const onChange = side === "A" ? handleChange : handleChangeB;
    const onRemove = side === "A" ? removeElemRowA : removeElemRowB;
    return (
      <div className="compare-compose-input-row">
        <label>{el}</label>
        <input
          type="number"
          step="0.01"
          value={composition[el] ?? ""}
          onChange={(e) => onChange(el, e.target.value)}
          style={{
            background: "var(--bg-page)",
            borderRadius: 6,
            border: "1px solid var(--border-muted)",
            padding: "6px 8px",
            color: "#e5e7eb"
          }}
        />
        <TactileButton
          onClick={() => onRemove(el)}
          title="목록에서 제거"
          aria-label={`${el} 제거`}
          style={{
            flexShrink: 0,
            minHeight: 44,
            padding: "10px 12px",
            borderRadius: 6,
            border: "1px solid #475569",
            background: "var(--border-default)",
            color: "#e5e7eb",
            fontSize: 13,
            cursor: "pointer"
          }}
        >
          ×
        </TactileButton>
      </div>
    );
  };

  const _renderFavoriteControls = ({ label, value, onChange, onDelete, optionPrefix = "" }) => {
    const hasFavorites = favoritesSorted.length > 0;
    const canDelete = hasFavorites && Boolean(value);
    return (
      <div className="compare-compose-fav-row" style={{ minHeight: 44 }}>
        <span style={{ fontSize: 13, color: "#9ca3af" }}>{label}</span>
        <select
          onChange={(e) => onChange(e.target.value)}
          value={value}
          disabled={!hasFavorites}
          style={{
            background: "var(--bg-page)",
            color: "#e5e7eb",
            borderRadius: 6,
            border: "1px solid var(--border-muted)",
            fontSize: 13,
            padding: "3px 6px",
            minWidth: 160,
            opacity: hasFavorites ? 1 : 0.72
          }}
        >
          <option value="" disabled>
            {hasFavorites ? "선택..." : "저장된 즐겨찾기 없음"}
          </option>
          {hasFavorites &&
            favoritesSorted.map((f) => (
              <option key={`${optionPrefix}${f.name}`} value={f.name}>
                {f.name}
              </option>
            ))}
        </select>
        <TactileButton
          onClick={onDelete}
          disabled={!canDelete}
          style={{
            minHeight: 44,
            padding: "10px 12px",
            borderRadius: 6,
            border: "1px solid #7f1d1d",
            background: canDelete ? "#7f1d1d" : "var(--border-muted)",
            color: "white",
            fontSize: 13,
            cursor: canDelete ? "pointer" : "default",
            opacity: canDelete ? 1 : 0.8
          }}
        >
          삭제
        </TactileButton>
        {!hasFavorites && favSyncStatus === "syncing" && (
          <span style={{ fontSize: 13, color: favSyncColor }}>저장된 즐겨찾기 불러오는 중...</span>
        )}
        {!hasFavorites && favSyncStatus === "ok" && (
          <span style={{ fontSize: 13, color: "#9ca3af" }}>저장된 즐겨찾기가 없습니다.</span>
        )}
      </div>
    );
  };

  const totalColor = (t, hasInput) => {
    if (!hasInput && Number(t) < 0.01) return "#64748b";
    if (compositionTotalIsComplete(t)) return "#22c55e";
    if (t >= 95 && t <= 105) return "#fbbf24";
    return "#f97316";
  };
  const favSyncColor =
    favSyncStatus === "ok"
      ? "#22c55e"
      : favSyncStatus === "syncing"
        ? "#60a5fa"
        : favSyncStatus === "error"
          ? "#fb7185"
          : "#f59e0b";

  const saveFavoriteA = async () => {
    const clean = Object.fromEntries(
      Object.entries(comp)
        .filter(([_, v]) => v !== "" && !Number.isNaN(Number(v)))
        .map(([k, v]) => [k, Number(v)])
    );
    if (!Object.keys(clean).length) {
      setError("저장할 조성이 없습니다.");
      return;
    }
    const name = window.prompt("즐겨찾기 이름을 입력하세요.", "조성 A");
    if (!name || !name.trim()) return;
    const fav = { name: name.trim(), comp: clean };
    const next = [fav, ...favorites.filter((f) => f.name !== fav.name)].slice(
      0,
      20
    );
    setFavorites(next);
    setSelectedFavoriteName(fav.name);
    saveFavoritesLocal(next);
    await syncFavoritesToServer(next, { silent: false });
  };

  const loadFavoriteToA = (name) => {
    const fav = favorites.find((f) => f.name === name);
    if (!fav) return;
    const c = fav.comp || {};
    setSelectedFavoriteName(name);
    setComp(c);
    setActiveElemsA(
      Object.keys(c).filter((k) => {
        const v = Number(c[k]);
        return Number.isFinite(v) && v > 0;
      })
    );
  };

  const deleteFavoriteA = async () => {
    if (!selectedFavoriteName) return;
    const removed = selectedFavoriteName;
    const next = favorites.filter((f) => f.name !== removed);
    setFavorites(next);
    setSelectedFavoriteName("");
    if (selectedFavoriteNameB === removed) setSelectedFavoriteNameB("");
    saveFavoritesLocal(next);
    await syncFavoritesToServer(next, { silent: false, allowEmpty: true });
  };

  const saveFavoriteB = async () => {
    const clean = Object.fromEntries(
      Object.entries(compB)
        .filter(([_, v]) => v !== "" && !Number.isNaN(Number(v)))
        .map(([k, v]) => [k, Number(v)])
    );
    if (!Object.keys(clean).length) {
      setError("저장할 조성 B가 없습니다.");
      return;
    }
    const name = window.prompt("즐겨찾기 이름을 입력하세요.", "조성 B");
    if (!name || !name.trim()) return;
    const fav = { name: name.trim(), comp: clean };
    const next = [fav, ...favorites.filter((f) => f.name !== fav.name)].slice(
      0,
      20
    );
    setFavorites(next);
    setSelectedFavoriteNameB(fav.name);
    saveFavoritesLocal(next);
    await syncFavoritesToServer(next, { silent: false });
  };

  const loadFavoriteToB = (name) => {
    const fav = favorites.find((f) => f.name === name);
    if (!fav) return;
    const c = fav.comp || {};
    setSelectedFavoriteNameB(name);
    setCompB(c);
    setActiveElemsB(
      Object.keys(c).filter((k) => {
        const v = Number(c[k]);
        return Number.isFinite(v) && v > 0;
      })
    );
  };

  const deleteFavoriteB = async () => {
    if (!selectedFavoriteNameB) return;
    const removed = selectedFavoriteNameB;
    const next = favorites.filter((f) => f.name !== removed);
    setFavorites(next);
    setSelectedFavoriteNameB("");
    if (selectedFavoriteName === removed) setSelectedFavoriteName("");
    saveFavoritesLocal(next);
    await syncFavoritesToServer(next, { silent: false, allowEmpty: true });
  };

  const toggleSection = (key) => {
    setSectionOpen((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const getImcTooltip = (name) => {
    const t = String(name || "").toLowerCase();
    if (t.includes("bi 농화") || t.includes("bi-rich")) {
      return "Bi 농화 분산상: Ag3Sn/Cu6Sn5 같은 연속 IMC층이 아니라, 주로 입계·기지에 분산되는 조직입니다.";
    }
    if (t.includes("ag3sn")) {
      return "Ag3Sn: Ag 첨가 시 형성되는 대표 IMC/분산상으로, 판상·침상 형태가 나타날 수 있습니다.";
    }
    if (t.includes("cu6sn5")) {
      return "Cu6Sn5: Sn-Cu 계면에서 우세한 IMC로, 리플로우 조건(TAL)에 따라 성장량이 달라집니다.";
    }
    if (t.includes("cu3sn")) {
      return "Cu3Sn: 장시간 TAL/고온 노출에서 Cu6Sn5 하부에 성장할 수 있는 계면 IMC입니다.";
    }
    if (t.includes("ni3sn4") || t.includes("(ni,cu)6sn5")) {
      return "Ni 계 IMC: Ni 미량 첨가/표면처리에서 계면 안정화에 기여할 수 있습니다.";
    }
    if (t.includes("in 농화") || t.includes("in-rich")) {
      return "In 농화상: Sn-In 계에서 저온 공정성 및 젖음 개선과 함께 나타날 수 있는 상입니다.";
    }
    return "입력 조성 및 공정 조건 기반의 상대적 상/IMC 예측 항목입니다.";
  };

  return (
    <div
      className="app-shell"
      style={{
        minHeight: "100vh",
        background: "var(--bg-page)",
        color: "var(--text-primary)",
        fontFamily: "var(--font-sans)",
        padding: "28px 26px"
      }}
    >
      <main
        id="main-content"
        style={{ maxWidth: 1200, margin: "0 auto", width: "100%" }}
        aria-labelledby="app-title"
      >
        <a href="#app-title" className="skip-to-content">
          본문으로 건너뛰기
        </a>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "baseline",
            gap: 12,
            marginBottom: 10
          }}
        >
          <h1 id="app-title" tabIndex={-1} style={{ fontSize: 28, fontWeight: 700, margin: 0 }}>
            {aboutInfo?.product || "AI 합금 분석기"}
          </h1>
          <span
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: "#94a3b8",
              padding: "3px 12px",
              borderRadius: 999,
              border: "1px solid #334155",
              background: "var(--bg-table-head)"
            }}
          >
            {aboutInfo ? `v${aboutInfo.version}` : "웹 UI"}
          </span>
          <span style={{ fontSize: 13, color: "#64748b" }}>
            FastAPI + React · 데스크톱 GUI와 동일 엔진
          </span>
        </div>
        <p
          style={{
            color: "#9ca3af",
            marginBottom: 10,
            lineHeight: 1.55,
            maxWidth: 820
          }}
        >
          {aboutInfo?.tagline ||
            "합금 조성을 입력하면 융점·상·IMC·리플로우 추천을 한 번에 제공합니다."}
        </p>
        {(favSyncStatus === "offline" || favSyncStatus === "error") && (
          <div
            role="status"
            style={{
              marginBottom: 14,
              padding: "12px 14px",
              borderRadius: 10,
              border: "1px solid rgba(245, 158, 11, 0.45)",
              background: "rgba(120, 53, 15, 0.35)",
              color: "#fde68a",
              fontSize: 13,
              lineHeight: 1.5,
              maxWidth: 820
            }}
          >
            <strong style={{ color: "#fef3c7" }}>API 오프라인</strong>
            {" — "}
            백엔드(
            <code style={{ fontSize: 12, color: "#fcd34d" }}>127.0.0.1:8000</code>)에 연결되지
            않았습니다. 즐겨찾기는 이 브라우저에만 저장됩니다.{" "}
            <code style={{ fontSize: 12, color: "#fcd34d" }}>start_all.bat</code> 또는{" "}
            <code style={{ fontSize: 12, color: "#fcd34d" }}>run_api_server.bat</code> 실행 후{" "}
            <a
              href="http://localhost:8000/"
              style={{ color: "#fcd34d", textDecoration: "underline" }}
            >
              http://localhost:8000/
            </a>
            에서 새로고침하세요.
          </div>
        )}
        {aboutInfo?.runtime && aboutInfo.runtime.cloud_llm_any === false ? (
          <div
            role="status"
            style={{
              marginBottom: 14,
              padding: "12px 14px",
              borderRadius: 10,
              border: "1px solid rgba(56, 189, 248, 0.4)",
              background: "rgba(12, 74, 110, 0.35)",
              color: "#bae6fd",
              fontSize: 13,
              lineHeight: 1.5,
              maxWidth: 820
            }}
          >
            <strong style={{ color: "#e0f2fe" }}>로컬·제한 모드</strong>
            {" — "}
            {(aboutInfo.runtime.user_visible_notes && aboutInfo.runtime.user_visible_notes[0]) ||
              "클라우드 AI 키가 없어 요약·보고 품질이 제한될 수 있습니다. 아래 「처리 방식」에서 자세히 보세요."}
          </div>
        ) : null}
        <TactileButton
          linkTone
          onClick={() => setTrustOpen((o) => !o)}
          aria-expanded={trustOpen}
          style={{
            marginBottom: trustOpen ? 12 : 20,
            fontSize: 13,
            color: "var(--link)",
            background: "transparent",
            border: "1px solid transparent",
            borderRadius: 8,
            cursor: "pointer",
            textDecoration: "underline",
            padding: "10px 4px",
            minHeight: 44,
            textAlign: "left"
          }}
        >
          {trustOpen
            ? "▼ 처리 방식·출처·면책 접기"
            : "▸ 처리 방식·데이터 출처·면책 보기 (발표·보고용)"}
        </TactileButton>
        {trustOpen ? (
          <div
            style={{
              marginBottom: 24,
              padding: 16,
              borderRadius: 12,
              border: "1px solid var(--border-accent)",
              background: "var(--bg-elevated)",
              fontSize: 13,
              lineHeight: 1.6,
              color: "var(--text-soft)"
            }}
          >
            {aboutInfo?.composition_input?.wt_percent_sum_guidance ? (
              <>
                <div style={{ fontWeight: 700, color: "#e2e8f0", marginBottom: 8 }}>조성 입력(wt%)</div>
                <p style={{ margin: "0 0 14px 0", color: "#94a3b8", fontSize: 13, lineHeight: 1.55 }}>
                  {aboutInfo.composition_input.wt_percent_sum_guidance}
                </p>
                {aboutInfo.composition_input.strict_mode_env ? (
                  <p style={{ margin: "0 0 14px 0", color: "#64748b", fontSize: 12, lineHeight: 1.5 }}>
                    {aboutInfo.composition_input.strict_mode_env}
                  </p>
                ) : null}
              </>
            ) : null}
            {aboutInfo?.runtime ? (
              <>
                <div style={{ fontWeight: 700, color: "#e2e8f0", marginBottom: 8 }}>연동·폴백 상태(이 서버)</div>
                <ul style={{ margin: "0 0 14px 1.1em", padding: 0 }}>
                  <li style={{ marginBottom: 6 }}>
                    Gemini 키: {aboutInfo.runtime.gemini_configured ? "감지됨" : "없음"}
                    {" · "}
                    Cerebras 키: {aboutInfo.runtime.cerebras_configured ? "감지됨" : "없음"}
                  </li>
                  {(aboutInfo.runtime.user_visible_notes || []).map((line, i) => (
                    <li key={`rt-${i}`} style={{ marginBottom: 6 }}>
                      {line}
                    </li>
                  ))}
                  {aboutInfo.runtime.literature_hint ? (
                    <li style={{ marginBottom: 6 }}>{aboutInfo.runtime.literature_hint}</li>
                  ) : null}
                </ul>
              </>
            ) : null}
            <div style={{ fontWeight: 700, color: "#e2e8f0", marginBottom: 8 }}>처리 개요</div>
            <ul style={{ margin: "0 0 14px 1.1em", padding: 0 }}>
              {(aboutInfo?.methodology?.length
                ? aboutInfo.methodology
                : TRUST_FALLBACK.methodology
              ).map((line, i) => (
                <li key={i} style={{ marginBottom: 6 }}>
                  {line}
                </li>
              ))}
            </ul>
            <div style={{ fontWeight: 700, color: "#e2e8f0", marginBottom: 8 }}>데이터·연동</div>
            <ul style={{ margin: "0 0 14px 1.1em", padding: 0 }}>
              {(aboutInfo?.data_sources?.length
                ? aboutInfo.data_sources
                : TRUST_FALLBACK.data_sources
              ).map((line, i) => (
                <li key={i} style={{ marginBottom: 6 }}>
                  {line}
                </li>
              ))}
            </ul>
            <div style={{ fontWeight: 700, color: "#e2e8f0", marginBottom: 8 }}>조성별 적용 규칙(요약)</div>
            <div
              style={{
                marginBottom: 14,
                border: "1px solid var(--border-muted)",
                borderRadius: 8,
                overflowX: "auto",
                background: "var(--bg-page)"
              }}
            >
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ background: "var(--bg-table-head)" }}>
                    <th style={ruleTh}>계열</th>
                    <th style={ruleTh}>적용 조건</th>
                    <th style={ruleTh}>주요 상/IMC</th>
                    <th style={ruleTh}>해석 포인트</th>
                  </tr>
                </thead>
                <tbody>
                  {(
                    aboutInfo?.alloy_rules?.length
                      ? aboutInfo.alloy_rules
                      : TRUST_FALLBACK.alloy_rules
                  ).map((r, i) => (
                    <tr key={`${r.family}-${i}`}>
                      <td style={ruleTd}>{r.family}</td>
                      <td style={ruleTd}>{r.when}</td>
                      <td style={ruleTd}>{r.phases}</td>
                      <td style={ruleTd}>{r.notes}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ fontWeight: 700, color: "#e2e8f0", marginBottom: 8 }}>면책</div>
            <p style={{ margin: 0, color: "#94a3b8", fontSize: 13, lineHeight: 1.55 }}>
              {aboutInfo?.disclaimer || TRUST_FALLBACK.disclaimer}
            </p>
          </div>
        ) : null}

        <div className={`app-main-grid${mode === "compare" ? " app-main-grid--compare" : ""}`}>
          {/* 입력 패널 */}
          <div
            className="compose-input-panel"
            style={{
              background: "var(--bg-page)",
              borderRadius: 12,
              border: "1px solid var(--border-default)",
              padding: 16,
              minWidth: 0
            }}
          >
            <CollapsibleSection
              title="목표 융점 탐색 (℃)"
              open={meltSearchOpen}
              onToggle={() => setMeltSearchOpen((v) => !v)}
              rightHint={mode === "compare" ? "선택" : ""}
            >
            <p style={{ margin: "0 0 10px", fontSize: 12, color: "#64748b", lineHeight: 1.45 }}>
              기본은 데이터시트에 흔한 <strong style={{ color: "#94a3b8" }}>목표 액상</strong> 한 가지만 넣습니다.{" "}
              <strong style={{ color: "#94a3b8" }}>Ag·Cu·In·Bi</strong> 격자를 스윕하고 나머지는{" "}
              <strong style={{ color: "#94a3b8" }}>Sn</strong>으로 맞춥니다. 표에는 격자 후보와 목표 온도에 맞는{" "}
              <strong style={{ color: "#94a3b8" }}>DB 등록 합금</strong>이 함께 나옵니다. 결과는 오른쪽 분석 패널
              상단에 붙습니다.
            </p>
            {meltSupport === "checking" ? (
              <p role="status" style={{ margin: "0 0 8px", color: "#94a3b8", fontSize: 11 }}>
                API 확인 중…
              </p>
            ) : null}
            <p style={{ margin: "0 0 10px", fontSize: 11, color: "#64748b", lineHeight: 1.45 }}>
              실행 시 약 <strong style={{ color: "#94a3b8" }}>10~20초</strong> 걸릴 수 있습니다. 끝날 때까지 이
              페이지를 두세요.
            </p>
            {meltSupport === "no" ? (
              <div
                role="alert"
                style={{
                  margin: "0 0 10px",
                  padding: 8,
                  borderRadius: 8,
                  background: "rgba(180, 83, 9, 0.22)",
                  border: "1px solid rgba(251, 191, 36, 0.35)",
                  color: "#fde68a",
                  fontSize: 11,
                  lineHeight: 1.45
                }}
              >
                <code style={{ color: "#e7e5e4" }}>/api/recommend_melt</code> 없음 — 8000 포트·최신{" "}
                <code style={{ color: "#e7e5e4" }}>api_server.py</code> 재실행 확인
              </div>
            ) : null}
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 10,
                marginBottom: 14,
                paddingBottom: 14,
                borderBottom: "1px solid var(--border-muted)"
              }}
            >
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 10,
                  alignItems: "flex-end"
                }}
              >
                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <span style={{ fontWeight: 600, color: "#9ca3af" }}>목표 액상 ℃</span>
                  <input
                    value={meltRecLiquidus}
                    onChange={(e) => setMeltRecLiquidus(e.target.value)}
                    placeholder="예: 200"
                    inputMode="decimal"
                    style={{
                      width: 96,
                      padding: "6px 8px",
                      borderRadius: 6,
                      border: "1px solid var(--border-muted)",
                      background: "var(--bg-page)",
                      color: "#e5e7eb",
                      fontSize: 13
                    }}
                  />
                </label>
                <label
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    cursor: "pointer",
                    padding: "6px 0",
                    fontSize: 12,
                    color: "#94a3b8",
                    userSelect: "none"
                  }}
                >
                  <input
                    type="checkbox"
                    checked={meltRecAlsoSolidusTarget}
                    onChange={(e) => setMeltRecAlsoSolidusTarget(e.target.checked)}
                    style={{ width: 15, height: 15, accentColor: "var(--accent)" }}
                  />
                  고상 목표도 지정
                </label>
                <TactileButton
                  type="button"
                  onClick={runMeltRecommend}
                  disabled={meltRecLoading}
                  style={{
                    padding: "8px 14px",
                    borderRadius: 6,
                    border: "1px solid var(--accent)",
                    background: meltRecLoading
                      ? "rgba(55, 65, 81, 0.5)"
                      : "rgba(37, 99, 235, 0.35)",
                    color: "var(--text-primary)",
                    cursor: meltRecLoading ? "wait" : "pointer",
                    fontSize: 13
                  }}
                >
                  {meltRecLoading ? "탐색 중…" : "탐색 실행"}
                </TactileButton>
              </div>
              {meltRecAlsoSolidusTarget ? (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}>
                  <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <span style={{ fontWeight: 600, color: "#9ca3af" }}>목표 고상 ℃</span>
                    <input
                      value={meltRecSolidus}
                      onChange={(e) => setMeltRecSolidus(e.target.value)}
                      placeholder="선택 (고상만 맞출 때 가능)"
                      inputMode="decimal"
                      style={{
                        width: 220,
                        maxWidth: "100%",
                        padding: "6px 8px",
                        borderRadius: 6,
                        border: "1px solid var(--border-muted)",
                        background: "var(--bg-page)",
                        color: "#e5e7eb",
                        fontSize: 13
                      }}
                    />
                  </label>
                  <span style={{ fontSize: 11, color: "#64748b", lineHeight: 1.45, maxWidth: 320 }}>
                    고상·액상 중 하나만 넣어도 됩니다. 둘 다 넣으면 두 축 밴드에 맞춥니다.
                  </span>
                </div>
              ) : null}
            </div>
            </CollapsibleSection>

            <h2 style={{ fontSize: 18, marginBottom: 12 }}>조성 입력 (wt%)</h2>

            <div
              style={{
                paddingBottom: 14,
                marginBottom: 14,
                borderBottom: "1px solid var(--border-muted)"
              }}
            >
              {/* 모드 토글: 동일 너비 슬롯으로 고정해 전환 시 버튼 위치·탭 순서가 밀리지 않게 함 */}
              <div
                role="tablist"
                aria-label="분석 모드"
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 8,
                  marginBottom: 12,
                  width: "100%",
                  minWidth: 0
                }}
              >
                <ModeButton
                  active={mode === "single"}
                  onClick={() => setMode("single")}
                  ariaSelected={mode === "single"}
                >
                  단일 분석
                </ModeButton>
                <ModeButton
                  active={mode === "compare"}
                  onClick={() => setMode("compare")}
                  ariaSelected={mode === "compare"}
                >
                  비교 분석
                </ModeButton>
              </div>

              <div style={{ fontSize: 13, color: "#9ca3af", marginBottom: 6 }}>
                {mode === "single"
                  ? "조성 A만 입력 후 분석을 실행합니다."
                  : "조성 A·B 입력 후 분석을 실행합니다."}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 0 }}>
                <span style={{ fontSize: 13, color: "#9ca3af" }}>문헌 검색:</span>
                <SmallToggleButton
                  active={literatureMode === "fast"}
                  onClick={() => setLiteratureMode("fast")}
                  label="빠름"
                />
                <SmallToggleButton
                  active={literatureMode === "deep"}
                  onClick={() => setLiteratureMode("deep")}
                  label="정밀"
                />
                <span style={{ fontSize: 13, color: "#64748b" }}>
                  {literatureMode === "deep" ? "출처를 더 깊게 검색(느릴 수 있음)" : "속도 우선"}
                </span>
              </div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  marginTop: 10,
                  flexWrap: "wrap"
                }}
              >
                <label
                  htmlFor="wetting-temp-select"
                  style={{ fontSize: 13, color: "#9ca3af", fontWeight: 600 }}
                >
                  젖음 예측 온도
                </label>
                <select
                  id="wetting-temp-select"
                  value={wettingTempSelect}
                  onChange={(e) => setWettingTempSelect(e.target.value)}
                  style={{
                    background: "var(--bg-page)",
                    color: "#e5e7eb",
                    borderRadius: 6,
                    border: "1px solid var(--border-muted)",
                    fontSize: 13,
                    padding: "6px 10px",
                    minWidth: 200
                  }}
                >
                  <option value="auto">
                    {mode === "compare" ? "자동 (A·B 공통 온도)" : "자동 (액상선+30℃)"}
                  </option>
                  <option value="250">250 ℃</option>
                  <option value="260">260 ℃</option>
                  <option value="270">270 ℃</option>
                  <option value="280">280 ℃</option>
                  <option value="290">290 ℃</option>
                </select>
                <span style={{ fontSize: 12, color: "#64748b", maxWidth: 420, lineHeight: 1.45 }}>
                  {mode === "compare"
                    ? "비교 시 A·B 모두 동일 온도에서 젖음을 봅니다. 자동이면 각 액상선+30℃ 스냅값 중 더 높은 BD 격자(250–290℃)를 씁니다."
                    : "기본은 액상선보다 약 +30℃를 목표로 하고, 젖음 DB와 동일한 250–290℃ 중 가장 가까운 값으로 맞춥니다. 필요하면 위에서 고정 온도를 고르세요."}
                </span>
              </div>
            </div>

            {/* 총합 · 즐겨찾기 — 단일 모드만 공통 영역 / 비교 모드는 각 열 내부 */}
            <div
              style={{
                paddingBottom: 14,
                marginBottom: 14,
                borderBottom: "1px solid var(--border-muted)"
              }}
            >
            {mode !== "compare" ? (
              <>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    marginBottom: 8,
                    flexWrap: "wrap"
                  }}
                >
                  <span
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      color: totalColor(totalA, compositionAHasInput)
                    }}
                  >
                    조성 A 총합: {totalA.toFixed(2)} %
                  </span>
                  <label style={{ fontSize: 13, color: "#9ca3af", marginLeft: "auto" }}>
                    <input
                      type="checkbox"
                      checked={showMetalsOnly}
                      onChange={(e) => setShowMetalsOnly(e.target.checked)}
                      style={{ marginRight: 4 }}
                    />
                    금속만 보기
                  </label>
                </div>
                <div className="compare-compose-fav-row" style={{ marginBottom: 8 }}>
                  <TactileButton
                    onClick={saveFavoriteA}
                    style={{
                      minHeight: 44,
                      padding: "10px 12px",
                      borderRadius: 6,
                      border: "1px solid var(--accent)",
                      background: "rgba(37, 99, 235, 0.35)",
                      color: "var(--text-primary)",
                      fontSize: 13,
                      cursor: "pointer"
                    }}
                  >
                    조성 A 즐겨찾기 저장
                  </TactileButton>
                  {(
                    <>
                      <span style={{ fontSize: 13, color: "#9ca3af" }}>합금 불러오기</span>
                      <select
                        onChange={(e) => loadFavoriteToA(e.target.value)}
                        value={selectedFavoriteName}
                        style={{
                          background: "var(--bg-page)",
                          color: "#e5e7eb",
                          borderRadius: 6,
                          border: "1px solid var(--border-muted)",
                          fontSize: 13,
                          padding: "3px 6px"
                        }}
                      >
                        <option value="" disabled>
                          선택…
                        </option>
                        {favoritesSorted.map((f) => (
                          <option key={f.name} value={f.name}>
                            {f.name}
                          </option>
                        ))}
                      </select>
                      <TactileButton
                        onClick={deleteFavoriteA}
                        disabled={!selectedFavoriteName}
                        style={{
                          minHeight: 44,
                          padding: "10px 12px",
                          borderRadius: 6,
                          border: "1px solid #7f1d1d",
                          background: selectedFavoriteName ? "#7f1d1d" : "var(--border-muted)",
                          color: "white",
                          fontSize: 13,
                          cursor: selectedFavoriteName ? "pointer" : "default"
                        }}
                      >
                        선택 삭제
                      </TactileButton>
                    </>
                  )}
                </div>
              </>
            ) : (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  marginBottom: 8,
                  flexWrap: "wrap"
                }}
              >
                <label style={{ fontSize: 13, color: "#9ca3af", marginLeft: "auto" }}>
                  <input
                    type="checkbox"
                    checked={showMetalsOnly}
                    onChange={(e) => setShowMetalsOnly(e.target.checked)}
                    style={{ marginRight: 4 }}
                  />
                  금속만 보기
                </label>
              </div>
            )}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
              {(favSyncStatus === "syncing" || favSyncStatus === "offline" || favSyncStatus === "error") && (
              <span style={{ fontSize: 13, color: favSyncColor }}>
                즐겨찾기 상태: {favSyncMessage}
              </span>
              )}
              {(favSyncStatus === "offline" || favSyncStatus === "error") && (
                <TactileButton
                  onClick={() => syncFavoritesToServer(favorites, { silent: false })}
                  style={{
                    minHeight: 44,
                    padding: "10px 12px",
                    borderRadius: 6,
                    border: "1px solid #334155",
                    background: "var(--bg-table-head)",
                    color: "var(--text-soft)",
                    fontSize: 13,
                    cursor: "pointer"
                  }}
                >
                  동기화 재시도
                </TactileButton>
              )}
            </div>
            </div>

            <div
              className={mode === "compare" ? "compare-dual-compose" : undefined}
              style={mode !== "compare" ? { display: "contents" } : undefined}
            >
            <div
              className={mode === "compare" ? "compare-compose-col compare-compose-col--a" : undefined}
              style={mode !== "compare" ? { display: "contents" } : undefined}
            >
            {mode === "compare" && (
              <>
                <div className="compare-compose-col-head" style={{ color: "#60a5fa" }}>
                  조성 A
                </div>
                <div
                  className="compare-compose-col-total"
                  style={{ color: totalColor(totalA, compositionAHasInput) }}
                >
                  조성 A 총합: {totalA.toFixed(2)} %
                </div>
                <div className="compare-compose-fav-row">
                  <TactileButton
                    onClick={saveFavoriteA}
                    style={{
                      minHeight: 44,
                      padding: "10px 12px",
                      borderRadius: 6,
                      border: "1px solid var(--accent)",
                      background: "rgba(37, 99, 235, 0.35)",
                      color: "var(--text-primary)",
                      fontSize: 13,
                      cursor: "pointer"
                    }}
                  >
                    A 즐겨찾기
                  </TactileButton>
                  {(
                    <>
                      <span style={{ fontSize: 13, color: "#9ca3af" }}>불러오기</span>
                      <select
                        onChange={(e) => loadFavoriteToA(e.target.value)}
                        value={selectedFavoriteName}
                        style={{
                          background: "var(--bg-page)",
                          color: "#e5e7eb",
                          borderRadius: 6,
                          border: "1px solid var(--border-muted)",
                          fontSize: 13,
                          padding: "3px 6px"
                        }}
                      >
                        <option value="" disabled>
                          선택…
                        </option>
                        {favoritesSorted.map((f) => (
                          <option key={f.name} value={f.name}>
                            {f.name}
                          </option>
                        ))}
                      </select>
                      <TactileButton
                        onClick={deleteFavoriteA}
                        disabled={!selectedFavoriteName}
                        style={{
                          minHeight: 44,
                          padding: "10px 12px",
                          borderRadius: 6,
                          border: "1px solid #7f1d1d",
                          background: selectedFavoriteName ? "#7f1d1d" : "var(--border-muted)",
                          color: "white",
                          fontSize: 13,
                          cursor: selectedFavoriteName ? "pointer" : "default"
                        }}
                      >
                        삭제
                      </TactileButton>
                    </>
                  )}
                </div>
              </>
            )}
            {/* 주기율표 스타일(솔더 관련 원소) 버튼 — narrow 뷰 터치 타겟은 index.css `.periodic-element-grid` */}
            <div
              className={
                mode === "compare"
                  ? "periodic-element-grid-wrap compare-periodic-scroll"
                  : "periodic-element-grid-wrap"
              }
            >
            <div
              className="periodic-element-grid"
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(7, minmax(0, 1fr))",
                gap: 6,
                marginBottom: mode === "compare" ? 0 : 10
              }}
            >
              {elemList.map((el) => {
                const isActive = !!comp[el];
                return (
                  <button
                    key={el}
                    type="button"
                    className={`periodic-cell-btn${isActive ? " is-active" : ""}`}
                    onClick={() => handleElemClick("A", el)}
                    style={{
                      minHeight: 44,
                      padding: "8px 0",
                      borderRadius: 6,
                      border: isActive
                        ? undefined
                        : "1px solid var(--border-muted)",
                      background: isActive ? undefined : "var(--bg-page)",
                      color: "#e5e7eb",
                      fontSize: 13,
                      fontWeight: isActive ? 600 : 500,
                      cursor: "pointer"
                    }}
                  >
                    <span className="tactile-hit-label">
                      {el}
                      {comp[el] ? `\n${Number(comp[el]).toFixed(1)}%` : ""}
                    </span>
                  </button>
                );
              })}
            </div>
            </div>

            <div className={mode === "compare" ? "compare-compose-sn-row" : undefined}>
              <TactileButton
                onClick={() => autoFillSn("A")}
                title="SAC(무연 솔더)에 맞춰 Sn·Ag·Cu 비율을 채웁니다. 필요 시 수동으로 조정하세요."
                style={{
                  marginBottom: 8,
                  minHeight: 44,
                  padding: "10px 12px",
                  borderRadius: 6,
                  border: "1px solid #0f766e",
                  background: "#064e3b",
                  color: "white",
                  fontSize: 13,
                  cursor: "pointer"
                }}
              >
                A Sn 자동완성
              </TactileButton>
            </div>

            <div className={mode === "compare" ? "compare-compose-add-block" : undefined}>
              {mode !== "compare" && <div style={{ fontWeight: 600, marginBottom: 4 }}>조성 A</div>}
              <p style={{ fontSize: 13, color: "#64748b", margin: "0 0 8px 0" }}>
                {mode === "compare"
                  ? "주기율표·원소 추가로 입력란을 만듭니다."
                  : "위 주기율표에서 원소를 클릭하거나, 아래에서 원소를 추가하면 입력란이 나타납니다."}
              </p>
              <select
                value={addPickA}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v) {
                    addElemRowA(v);
                    setAddPickA("");
                  }
                }}
                style={{
                  width: "100%",
                  marginBottom: 10,
                  background: "var(--bg-page)",
                  color: "#e5e7eb",
                  borderRadius: 6,
                  border: "1px solid var(--border-muted)",
                  fontSize: 13,
                  padding: "6px 8px"
                }}
              >
                <option value="">원소 추가…</option>
                {elemList
                  .filter((el) => !activeElemsA.includes(el))
                  .map((el) => (
                    <option key={`add-a-${el}`} value={el}>
                      {el}
                    </option>
                  ))}
              </select>
            </div>
            {mode === "compare" ? (
              <div className="compare-compose-inputs">
                {compareVisibleElemsA.length === 0 ? (
                  <p style={{ fontSize: 13, color: "#64748b", margin: 0 }}>아직 선택된 원소가 없습니다.</p>
                ) : (
                  compareVisibleElemsA.map((el) => renderCompareComposeInputRow(el, "A"))
                )}
              </div>
            ) : (
            <div>
              {activeElemsA.length === 0 ? (
                <p style={{ fontSize: 13, color: "#64748b", margin: 0 }}>아직 선택된 원소가 없습니다.</p>
              ) : (
                activeElemsA.map((el) => (
                  <div
                    key={el}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      marginBottom: 8
                    }}
                  >
                    <label style={{ width: 44, flexShrink: 0 }}>{el}</label>
                    <input
                      type="number"
                      step="0.01"
                      value={comp[el] ?? ""}
                      onChange={(e) => handleChange(el, e.target.value)}
                      style={{
                        flex: 1,
                        background: "var(--bg-page)",
                        borderRadius: 6,
                        border: "1px solid var(--border-muted)",
                        padding: "6px 8px",
                        color: "#e5e7eb"
                      }}
                    />
                    <TactileButton
                      onClick={() => removeElemRowA(el)}
                      title="목록에서 제거"
                      aria-label={`${el} 제거`}
                      style={{
                        flexShrink: 0,
                        minHeight: 44,
                        padding: "10px 12px",
                        borderRadius: 6,
                        border: "1px solid #475569",
                        background: "var(--border-default)",
                        color: "#e5e7eb",
                        fontSize: 13,
                        cursor: "pointer"
                      }}
                    >
                      ×
                    </TactileButton>
                  </div>
                ))
              )}
            </div>
            )}

            </div>
            {mode === "compare" && (
              <div className="compare-compose-col compare-compose-col--b">
                <div className="compare-compose-col-head" style={{ color: "#fb923c" }}>
                  조성 B
                </div>
                <div
                  className="compare-compose-col-total"
                  style={{ color: totalColor(totalB, compositionBHasInput) }}
                >
                  조성 B 총합: {totalB.toFixed(2)} %
                </div>
                <div className="compare-compose-fav-row">
                  <TactileButton
                    onClick={saveFavoriteB}
                    style={{
                      minHeight: 44,
                      padding: "10px 12px",
                      borderRadius: 6,
                      border: "1px solid #7c3aed",
                      background: "rgba(124, 58, 237, 0.25)",
                      color: "var(--text-primary)",
                      fontSize: 13,
                      cursor: "pointer"
                    }}
                  >
                    B 즐겨찾기
                  </TactileButton>
                  {(
                    <>
                      <span style={{ fontSize: 13, color: "#9ca3af" }}>불러오기</span>
                      <select
                        onChange={(e) => loadFavoriteToB(e.target.value)}
                        value={selectedFavoriteNameB}
                        style={{
                          background: "var(--bg-page)",
                          color: "#e5e7eb",
                          borderRadius: 6,
                          border: "1px solid var(--border-muted)",
                          fontSize: 13,
                          padding: "3px 6px"
                        }}
                      >
                        <option value="" disabled>
                          선택…
                        </option>
                        {favoritesSorted.map((f) => (
                          <option key={`b-${f.name}`} value={f.name}>
                            {f.name}
                          </option>
                        ))}
                      </select>
                      <TactileButton
                        onClick={deleteFavoriteB}
                        disabled={!selectedFavoriteNameB}
                        style={{
                          minHeight: 44,
                          padding: "10px 12px",
                          borderRadius: 6,
                          border: "1px solid #7f1d1d",
                          background: selectedFavoriteNameB ? "#7f1d1d" : "var(--border-muted)",
                          color: "white",
                          fontSize: 13,
                          cursor: selectedFavoriteNameB ? "pointer" : "default"
                        }}
                      >
                        삭제
                      </TactileButton>
                    </>
                  )}
                </div>

                {/* 조성 B용 주기율표 버튼 */}
                <div className="periodic-element-grid-wrap compare-periodic-scroll">
                <div
                  className="periodic-element-grid"
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(7, minmax(0, 1fr))",
                    gap: 6,
                    marginBottom: 0
                  }}
                >
                  {elemList.map((el) => {
                    const isActive = !!compB[el];
                    return (
                      <button
                        key={`B-btn-${el}`}
                        type="button"
                        className={`periodic-cell-btn${isActive ? " is-active" : ""}`}
                        onClick={() => handleElemClick("B", el)}
                        style={{
                          minHeight: 44,
                          padding: "8px 0",
                          borderRadius: 6,
                          border: isActive
                            ? undefined
                            : "1px solid var(--border-muted)",
                          background: isActive ? undefined : "var(--bg-page)",
                          color: "#e5e7eb",
                          fontSize: 13,
                          fontWeight: isActive ? 600 : 500,
                          cursor: "pointer"
                        }}
                      >
                        <span className="tactile-hit-label">
                          {el}
                          {compB[el] ? `\n${Number(compB[el]).toFixed(1)}%` : ""}
                        </span>
                      </button>
                    );
                  })}
                </div>
                </div>

                <div className="compare-compose-sn-row">
                  <TactileButton
                    onClick={() => autoFillSn("B")}
                    title="SAC(무연 솔더)에 맞춰 Sn·Ag·Cu 비율을 채웁니다. 필요 시 수동으로 조정하세요."
                    style={{
                      marginBottom: 8,
                      minHeight: 44,
                      padding: "10px 12px",
                      borderRadius: 6,
                      border: "1px solid #0f766e",
                      background: "#064e3b",
                      color: "white",
                      fontSize: 13,
                      cursor: "pointer"
                    }}
                  >
                    B Sn 자동완성
                  </TactileButton>
                </div>
                <div className="compare-compose-add-block">
                  <p style={{ fontSize: 13, color: "#64748b", margin: "0 0 8px 0" }}>
                    주기율표·원소 추가로 입력란을 만듭니다.
                  </p>
                  <select
                    value={addPickB}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (v) {
                        addElemRowB(v);
                        setAddPickB("");
                      }
                    }}
                    style={{
                      width: "100%",
                      marginBottom: 10,
                      background: "var(--bg-page)",
                      color: "#e5e7eb",
                      borderRadius: 6,
                      border: "1px solid var(--border-muted)",
                      fontSize: 13,
                      padding: "6px 8px"
                    }}
                  >
                    <option value="">원소 추가…</option>
                    {elemList
                      .filter((el) => !activeElemsB.includes(el))
                      .map((el) => (
                        <option key={`add-b-${el}`} value={el}>
                          {el}
                        </option>
                      ))}
                  </select>
                </div>
                <div className="compare-compose-inputs">
                  {compareVisibleElemsB.length === 0 ? (
                    <p style={{ fontSize: 13, color: "#64748b", margin: 0 }}>아직 선택된 원소가 없습니다.</p>
                  ) : (
                    compareVisibleElemsB.map((el) => renderCompareComposeInputRow(el, "B"))
                  )}
                </div>
              </div>
            )}
            </div>

            <div style={{ marginTop: 12 }}>
              {analyzeBlockReason && !loading && (
                <p
                  role="status"
                  style={{
                    margin: "0 0 8px 0",
                    fontSize: 12,
                    color: "#f97316",
                    lineHeight: 1.45
                  }}
                >
                  {analyzeBlockReason}
                </p>
              )}
              <div style={{ display: "flex", gap: 8 }}>
              <TactileButton
                onClick={handleAnalyze}
                disabled={loading || !analyzeReady}
                aria-disabled={loading || !analyzeReady}
                title={analyzeBlockReason && !loading ? analyzeBlockReason : undefined}
                style={{
                  flex: 1,
                  padding: "8px 12px",
                  borderRadius: 8,
                  border: "none",
                  background: loading || !analyzeReady ? "#4b5563" : "#2563eb",
                  color: "white",
                  fontWeight: 600,
                  cursor: loading || !analyzeReady ? "not-allowed" : "pointer",
                  opacity: loading || !analyzeReady ? 0.65 : 1,
                  pointerEvents: loading || !analyzeReady ? "none" : "auto"
                }}
              >
                {loading ? (
                  <>
                    <span className="btn-spinner" />
                    분석 중...
                  </>
                ) : (
                  "분석"
                )}
              </TactileButton>
              <TactileButton
                onClick={handleReset}
                disabled={loading}
                style={{
                  flex: "0 0 auto",
                  padding: "8px 12px",
                  borderRadius: 8,
                  border: "1px solid #475569",
                  background: "#0b1220",
                  color: "#e2e8f0",
                  fontWeight: 600,
                  cursor: loading ? "default" : "pointer"
                }}
              >
                초기화
              </TactileButton>
            </div>
            {!loading && (
              <p
                style={{
                  margin: "10px 0 0",
                  fontSize: 12,
                  color: "#64748b",
                  lineHeight: 1.45
                }}
              >
                융점·상분석·문헌 요약은 오른쪽 <span style={{ color: "#94a3b8", fontWeight: 600 }}>분석 결과</span>{" "}
                카드에서 확인합니다.
              </p>
            )}
            {loading && (
              <>
                <div
                  role="status"
                  aria-live="polite"
                  aria-atomic="true"
                  style={{
                    marginTop: 8,
                    fontSize: 13,
                    color: "#93c5fd",
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    flexWrap: "wrap"
                  }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: 999,
                      background: "#60a5fa",
                      boxShadow: "0 0 8px rgba(96,165,250,0.9)",
                      flexShrink: 0
                    }}
                  />
                  <span style={{ fontWeight: 600 }}>
                    {analysisStage || "분석 요청 처리 중..."}
                  </span>
                  <span style={{ color: "#64748b", fontVariantNumeric: "tabular-nums" }}>
                    (경과 {analysisElapsedSec}s)
                  </span>
                </div>
                <div
                  ref={analysisLogScrollRef}
                  aria-label="분석 진행 로그"
                  style={{
                    marginTop: 6,
                    padding: 8,
                    border: "1px solid var(--border-muted)",
                    borderRadius: 8,
                    background: "#0b1220",
                    maxHeight: 120,
                    overflow: "auto"
                  }}
                >
                  {analysisLogs.map((x, i) => (
                    <div key={`${x.t}-${i}`} style={{ fontSize: 13, color: "var(--text-soft)", lineHeight: 1.45 }}>
                      [{String(x.t).padStart(2, "0")}s] {x.msg}
                    </div>
                  ))}
                </div>
              </>
            )}
            {error && (
              <p style={{ marginTop: 12, color: "#f97316", whiteSpace: "pre-wrap" }}>
                오류: {error}
              </p>
            )}
            </div>
          </div>

          {/* 결과 패널 */}
          <div
            className={mode === "compare" ? "result-panel--compare" : undefined}
            style={{
              background: "var(--bg-page)",
              borderRadius: 12,
              border: "1px solid var(--border-default)",
              padding: 16,
              minHeight: 220,
              minWidth: 0
            }}
          >
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                marginBottom: 8,
                gap: 8
              }}
            >
              <h2 style={{ fontSize: 18, marginBottom: 0 }}>분석 결과</h2>
              {((mode === "single" && result) || (mode === "compare" && compareResult)) && (
                <TactileButton
                  onClick={() => setResultPanelOpen((v) => !v)}
                  style={{
                    marginLeft: 6,
                    minHeight: 44,
                    padding: "10px 12px",
                    border: "1px solid #334155",
                    background: "#111827",
                    color: "var(--text-soft)",
                    borderRadius: 8,
                    fontSize: 13,
                    cursor: "pointer"
                  }}
                >
                  {resultPanelOpen ? "분석 결과 접기" : "분석 결과 펼치기"}
                </TactileButton>
              )}
              <div
                style={{
                  marginLeft: "auto",
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 6
                }}
              >
                <SmallToggleButton
                  active={reportMode === "eng"}
                  onClick={() => setReportMode("eng")}
                  label="쉬운 요약"
                />
                <SmallToggleButton
                  active={reportMode === "lab"}
                  onClick={() => {
                    setReportMode("lab");
                    if (result) {
                      setResultPanelOpen(true);
                      setSectionOpen(DEFAULT_SECTION_OPEN_LAB);
                      setWettingSectionOpen(false);
                    }
                  }}
                  label="연구소 모드"
                />
              </div>
            </div>
            {showMeltRecommendPanel ? (
              <div
                style={{
                  marginBottom: 16,
                  paddingBottom: 16,
                  borderBottom: "1px solid var(--border-muted)"
                }}
              >
                <div
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: "#94a3b8",
                    marginBottom: 8
                  }}
                >
                  목표 융점 탐색 결과
                </div>
                {meltRecError ? (
                  <pre
                    style={{
                      margin: "0 0 10px",
                      padding: 10,
                      borderRadius: 6,
                      background: "rgba(127, 29, 29, 0.25)",
                      color: "#fecaca",
                      fontSize: 12,
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word"
                    }}
                  >
                    {meltRecError}
                  </pre>
                ) : null}
                {meltRecResult?.meta?.disclaimer ? (
                  <p style={{ margin: "0 0 10px", color: "#fbbf24", fontSize: 12 }}>
                    {meltRecResult.meta.disclaimer}
                  </p>
                ) : null}
                {meltRecResult?.meta?.melting_engine_version ? (
                  <p style={{ margin: "0 0 8px", color: "#94a3b8", fontSize: 11 }}>
                    융점 엔진 v{meltRecResult.meta.melting_engine_version}. 입력은 기본 액상만이며, 고상 목표도
                    지정을 켜면 두 축을 넣을 수 있고 DB는 두 축 모두 허용 밴드에 들어간 행만 합칩니다. 값이
                    반영되지 않으면 API(8000)를 재시작했는지 확인하세요.
                  </p>
                ) : null}
                {Array.isArray(meltRecResult?.candidates) && meltRecResult.candidates.length ? (
                  <div style={{ overflowX: "auto" }}>
                    <table
                      className="melt-rec-table"
                      style={{
                        width: "100%",
                        borderCollapse: "collapse",
                        fontSize: 12,
                        color: "#e5e7eb"
                      }}
                    >
                      <caption
                        style={{
                          captionSide: "top",
                          textAlign: "left",
                          padding: "0 0 10px",
                          fontSize: 11,
                          color: "#64748b",
                          lineHeight: 1.45
                        }}
                      >
                        <strong style={{ color: "#94a3b8" }}>격자·DB 통합</strong>
                        — solder_db는 목표 융점 밴드에 들어가는 <strong>기준(등록) 조성</strong>을,
                        모델 행은 고정·가변 wt%를 스윕한 <strong>미지 후보</strong>입니다. 같은 조성이
                        아니라 빼고·늘리고 맞추는 탐색 결과이며, 목표에 더 가까운 행이 위로 옵니다. 고상·액상을
                        둘 다 넣은 경우 정렬은{" "}
                        <code style={{ color: "#94a3b8" }}>|Δ고상|+|Δ액상|</code> 합이 작은 순입니다.
                        {typeof meltRecResult.meta?.melt_candidates_db_registered_cap === "number" ? (
                          <span style={{ color: "#94a3b8" }}>
                            {" "}
                            (표 안 DB 등록 행 최대 {meltRecResult.meta.melt_candidates_db_registered_cap}건)
                          </span>
                        ) : null}
                        {meltRecResult.candidates.length > 0 ? (
                          <>
                            {" "}
                            현재 {meltRecResult.candidates.length}행 표시
                            {typeof meltRecResult.meta?.melt_unified_max_rows === "number" ? (
                              <span style={{ color: "#94a3b8" }}>
                                {" "}
                                (밴드 일치 DB{" "}
                                {typeof meltRecResult.meta?.db_temperature_match_count === "number"
                                  ? meltRecResult.meta.db_temperature_match_count
                                  : "—"}
                                건 · 상한 {meltRecResult.meta.melt_unified_max_rows}행)
                              </span>
                            ) : typeof meltRecResult.meta?.db_temperature_match_count === "number" ? (
                              <span style={{ color: "#94a3b8" }}>
                                {" "}
                                · 밴드 일치 DB {meltRecResult.meta.db_temperature_match_count}건
                              </span>
                            ) : null}
                          </>
                        ) : null}
                      </caption>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-muted)" }}>
                          <th style={{ textAlign: "left", padding: "6px 8px" }}>#</th>
                          <th style={{ textAlign: "left", padding: "6px 8px" }}>출처</th>
                          <th style={{ textAlign: "left", padding: "6px 8px" }}>조성 (wt%)</th>
                          <th className="melt-rec-num" style={{ textAlign: "right", padding: "6px 8px" }}>
                            고상
                          </th>
                          <th className="melt-rec-num" style={{ textAlign: "right", padding: "6px 8px" }}>
                            액상
                          </th>
                          <th
                            className="melt-rec-num"
                            style={{ textAlign: "right", padding: "6px 8px" }}
                            title="액상 − 고상(℃). 값이 작을수록 응고(과냉각) 구간이 짧아 동시에 고형·액체가 공존하는 온도 범위가 좁습니다."
                          >
                            구간(ΔT)
                          </th>
                          <th style={{ textAlign: "left", padding: "6px 8px" }}>DB근접</th>
                        </tr>
                      </thead>
                      <tbody>
                        {meltRecResult.candidates.map((row, i) => (
                          <tr
                            key={i}
                            style={{ borderBottom: "1px solid var(--bg-table-head)" }}
                          >
                            <td style={{ padding: "6px 8px", verticalAlign: "top" }}>{i + 1}</td>
                            <td style={{ padding: "6px 8px", whiteSpace: "nowrap", verticalAlign: "top" }}>
                              {row.melt_row_source === "solder_db_registered" ? (
                                <span
                                  style={{
                                    fontSize: 10,
                                    padding: "2px 6px",
                                    borderRadius: 4,
                                    background: "rgba(22, 163, 74, 0.35)",
                                    color: "#bbf7d0"
                                  }}
                                  title={
                                    row.registered_name
                                      ? `solder_db 등록: ${row.registered_name}`
                                      : "solder_db 등록 고상·액상 — 목표 밴드에 맞는 기준(닻) 조성"
                                  }
                                >
                                  기준(DB)
                                </span>
                              ) : (
                                <span
                                  style={{ fontSize: 10, color: "#94a3b8" }}
                                  title="고정·가변 wt% 격자 스윕 — 등록과 다른 미지 후보(모델 예측)"
                                >
                                  탐색
                                </span>
                              )}
                            </td>
                            <td
                              style={{
                                padding: "6px 8px",
                                fontFamily: "var(--font-sans)",
                                fontSize: 12,
                                letterSpacing: "0.02em",
                                maxWidth: 340,
                                lineHeight: 1.5,
                                color: "#e5e7eb",
                                verticalAlign: "top"
                              }}
                              title={formatWtPercentCompositionReadable(row.comp)}
                            >
                              <WtPercentCompositionReadable comp={row.comp} />
                            </td>
                            <td
                              className="melt-rec-num"
                              style={{ padding: "6px 8px", textAlign: "right", verticalAlign: "top" }}
                            >
                              {Number(row.solidus).toFixed(1)}
                            </td>
                            <td
                              className="melt-rec-num"
                              style={{ padding: "6px 8px", textAlign: "right", verticalAlign: "top" }}
                            >
                              {Number(row.liquidus).toFixed(1)}
                            </td>
                            <td
                              className="melt-rec-num"
                              style={{
                                padding: "6px 8px",
                                textAlign: "right",
                                color: "#cbd5e1",
                                verticalAlign: "top"
                              }}
                              title="액상 − 고상(℃)"
                            >
                              {(row.plastic_range_c != null && Number.isFinite(Number(row.plastic_range_c))
                                ? Number(row.plastic_range_c)
                                : Number(row.liquidus) - Number(row.solidus)
                              ).toFixed(1)}
                            </td>
                            <td
                              style={{ padding: "6px 8px", maxWidth: 320, verticalAlign: "top", lineHeight: 1.35 }}
                              title={String(row.db_close_names || row.best_name || "").trim() || undefined}
                            >
                              <DbCloseNamesReadable text={row.db_close_names || row.best_name} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </div>
            ) : null}
            {loading && !result && !compareResult && !showMeltRecommendPanel && (
              <ResultAnalyzeSkeleton compareMode={mode === "compare"} />
            )}
            {!result && !compareResult && !error && !showMeltRecommendPanel && !loading && (
              <div className="empty-state-guide">
                <div className="empty-state-guide__icon" style={{ fontSize: 32, opacity: 0.8 }}>⚗️</div>
                <p style={{ margin: 0, fontSize: 14, color: "#94a3b8", fontWeight: 600 }}>
                  {mode === "compare" ? (
                    <>
                      왼쪽에서 <strong style={{ color: "#60a5fa" }}>조성 A</strong>와{" "}
                      <strong style={{ color: "#fb923c" }}>조성 B</strong>를 입력한 뒤{" "}
                      <strong style={{ color: "#e5e7eb" }}>분석</strong>을 누르면 융점·물성 차이와
                      IMC·위험도 비교가 여기 표시됩니다.
                    </>
                  ) : (
                    <>
                      왼쪽에서 원소와 wt%를 입력한 뒤 <strong style={{ color: "#e5e7eb" }}>분석</strong>을
                      누르면 융점·상·문헌·AI 요약이 여기 표시됩니다.
                    </>
                  )}
                </p>
              </div>
            )}
            {!result && !compareResult && error && (
              <p style={{ color: "#f97316", whiteSpace: "pre-wrap", marginTop: 4 }} role="alert">
                {error}
              </p>
            )}
            {mode === "compare" && compareResult && !resultPanelOpen && (
              <p style={{ color: "#64748b", marginTop: 6 }}>
                분석 결과가 접혀 있습니다. “분석 결과 펼치기”로 비교 표·IMC 요약을 확인하세요.
              </p>
            )}
            {mode === "single" && result && !resultPanelOpen && (
              <p style={{ color: "#64748b", marginTop: 6 }}>
                상세 분석(탭·문헌·리플로우)이 접혀 있습니다. KPI는 아래에 표시됩니다. “분석 결과 펼치기”로 전체를
                확인하세요.
              </p>
            )}
            {mode === "single" && result && !resultPanelOpen && (
              <>
                <div
                  style={{
                    marginBottom: 10,
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    flexWrap: "wrap"
                  }}
                >
                  <AiModeBadge result={result} />
                  <AiSessionUsageRow usage={result.ai_usage_snapshot} />
                  <AiStatusDetail result={result} />
                </div>
                <ResultSummaryBlock
                  result={result}
                  kpiGridRef={resultKpiScrollRef}
                  wettingSectionOpen={wettingSectionOpen}
                  setWettingSectionOpen={setWettingSectionOpen}
                  wettingGridRows={wettingGridRows}
                  wettingGridLoading={wettingGridLoading}
                  wettingGridError={wettingGridError}
                  loadWettingGrid={loadWettingGrid}
                />
              </>
            )}
            {mode === "single" && result && resultPanelOpen && (
              <>
                <div
                  style={{
                    marginBottom: 10,
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    flexWrap: "wrap"
                  }}
                >
                  <AiModeBadge result={result} />
                  <AiSessionUsageRow usage={result.ai_usage_snapshot} />
                  <AiStatusDetail result={result} />
                </div>
                <ResultSummaryBlock
                  result={result}
                  showDbMeta
                  kpiGridRef={resultKpiScrollRef}
                  wettingSectionOpen={wettingSectionOpen}
                  setWettingSectionOpen={setWettingSectionOpen}
                  wettingGridRows={wettingGridRows}
                  wettingGridLoading={wettingGridLoading}
                  wettingGridError={wettingGridError}
                  loadWettingGrid={loadWettingGrid}
                />
                <div style={{ marginBottom: 12, display: "flex", flexWrap: "wrap", gap: 8 }}>
                  <TactileButton
                    type="button"
                    onClick={() => setChartReportOpen(true)}
                    style={{
                      minHeight: 44,
                      padding: "10px 16px",
                      borderRadius: 8,
                      border: "1px solid #2563eb",
                      background: "linear-gradient(180deg, #1d4ed8 0%, #1e40af 100%)",
                      color: "#f8fafc",
                      fontSize: 14,
                      fontWeight: 700,
                      cursor: "pointer"
                    }}
                  >
                    슬라이드 보고서
                  </TactileButton>
                </div>
                {result.evidence?.wetting?.source === "Heuristic" && (
                  <p style={{ fontSize: 12, color: "#64748b", margin: "0 0 12px 0" }}>
                    젖음: 측정 DB 보간 대신 조성·온도 휴리스틱 추정입니다. (융점 DB 최근접 거리는 요약·신뢰도 블록 참고)
                  </p>
                )}

                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 6,
                    marginBottom: 12
                  }}
                >
                  <SmallToggleButton
                    active={sectionOpen.phase}
                    onClick={() => toggleSection("phase")}
                    label={reportMode === "eng" ? "온도·조직(쉬운 설명)" : "상분석/IMC"}
                  />
                  <SmallToggleButton
                    active={sectionOpen.riskAi}
                    onClick={() => toggleSection("riskAi")}
                    label="리스크·AI"
                  />
                  <SmallToggleButton
                    active={sectionOpen.sources}
                    onClick={() => toggleSection("sources")}
                    label="출처"
                  />
                  <SmallToggleButton
                    active={sectionOpen.roles}
                    onClick={() => toggleSection("roles")}
                    label="원소역할·도펀트"
                  />
                  <SmallToggleButton
                    active={sectionOpen.reflow}
                    onClick={() => toggleSection("reflow")}
                    label="리플로우"
                  />
                  {(reportMode === "eng" || reportMode === "lab") && (
                    <SmallToggleButton
                      active={sectionOpen.eng}
                      onClick={() => toggleSection("eng")}
                      label={reportMode === "eng" ? "요약 보고서" : "원문(ENG)"}
                    />
                  )}
                  {reportMode === "lab" ? (
                    <SmallToggleButton
                      active={sectionOpen.lab}
                      onClick={() => toggleSection("lab")}
                      label="원문(LAB)"
                    />
                  ) : null}
                </div>

                <CollapsibleSection
                  title={
                    reportMode === "eng"
                      ? "납땜 온도·합금층 (쉬운 설명)"
                      : "상분석 / IMC"
                  }
                  open={sectionOpen.phase}
                  onToggle={() => toggleSection("phase")}
                >
                  <div className="result-prose-scroll" style={{ marginBottom: 14 }}>
                    <AnalysisProse text={result.phase} />
                  </div>
                  <div className="result-section-label">
                    {reportMode === "eng"
                      ? "기판과 만날 때 생길 수 있는 합금층"
                      : "예상 IMC"}
                  </div>
                  <p style={{ fontSize: 13, color: "var(--text-dim)", margin: "0 0 10px 0" }}>
                    {reportMode === "eng"
                      ? "IMC는 금속 사이 얇은 반응층을 뜻합니다. 항목에 마우스를 올리면 부가 설명을 봅니다."
                      : "항목에 마우스를 올리면 간단 설명을 볼 수 있습니다."}
                  </p>
                  <div className="result-imc-wrap">
                    {(result.imc || []).map((x, idx) => (
                      <span key={idx} className="result-imc-chip" title={getImcTooltip(x)}>
                        {x}
                      </span>
                    ))}
                  </div>
                </CollapsibleSection>

                <CollapsibleSection
                  title="신뢰성 리스크 / AI 요약"
                  open={sectionOpen.riskAi}
                  onToggle={() => toggleSection("riskAi")}
                >
                  <div
                    className="result-risk-grid"
                    style={{
                      display: "grid",
                      gridTemplateColumns:
                        "repeat(auto-fit, minmax(min(100%, 300px), 1fr))",
                      gap: 16,
                      alignItems: "start"
                    }}
                  >
                    <section style={{ minWidth: 0 }}>
                      <h3>신뢰성 리스크</h3>
                      <ul className="result-prose-ul" style={{ marginBottom: 0 }}>
                        {(result.risk || []).map((x, idx) => (
                          <li key={idx} className="result-prose-li">
                            {x}
                          </li>
                        ))}
                      </ul>
                    </section>
                    <section style={{ minWidth: 0 }}>
                      <h3>AI 요약</h3>
                      <div className="result-prose-scroll result-prose-scroll--tall">
                        <AnalysisProse text={result.ai_summary} compact />
                      </div>
                    </section>
                  </div>
                </CollapsibleSection>

                <CollapsibleSection
                  title="참고 문헌 / 출처"
                  open={sectionOpen.sources}
                  onToggle={() => toggleSection("sources")}
                >
                  {(() => {
                    const aiCited = Array.isArray(result.ai_cited_sources)
                      ? result.ai_cited_sources
                      : [];
                    const retrieved = Array.isArray(result.retrieved_candidates)
                      ? result.retrieved_candidates
                      : Array.isArray(result.ai_sources)
                        ? result.ai_sources
                        : [];
                    return (
                      <>
                  <p style={{ fontSize: 13, color: "#64748b", margin: "0 0 8px 0" }}>
                    AI가 실제로 인용한 출처와 자동 검색 후보를 분리해 표시합니다. DOI/URL이 포함된
                    항목은 링크로 열 수 있습니다.
                  </p>
                  {Array.isArray(result.evidence?.standards_refs) &&
                  result.evidence.standards_refs.length > 0 ? (
                    <div style={{ marginBottom: 14 }}>
                      <div
                        style={{
                          fontSize: 13,
                          fontWeight: 600,
                          color: "#94a3b8",
                          marginBottom: 6
                        }}
                      >
                        업계 표준 참고 (IPC·JIS)
                      </div>
                      <ul
                        style={{
                          margin: 0,
                          paddingLeft: 18,
                          fontSize: 13,
                          color: "var(--text-soft)",
                          lineHeight: 1.5
                        }}
                      >
                        {result.evidence.standards_refs.map((x, i) => (
                          <li key={i}>
                            {x.family} {x.id}: {x.note}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {Array.isArray(result.evidence?.strength_literature?.refs) &&
                  result.evidence.strength_literature.refs.length > 0 ? (
                    <div style={{ marginBottom: 14 }}>
                      <div
                        style={{
                          fontSize: 13,
                          fontWeight: 600,
                          color: "#94a3b8",
                          marginBottom: 6
                        }}
                      >
                        기계적 물성 문헌 참고
                      </div>
                      <ul
                        style={{
                          margin: 0,
                          paddingLeft: 18,
                          fontSize: 13,
                          color: "var(--text-soft)",
                          lineHeight: 1.5
                        }}
                      >
                        {result.evidence.strength_literature.refs.map((x, i) => (
                          <li key={i}>
                            {x.alloy}: UTS≈{x.tensile_mpa} MPa — {x.source}
                            {x.doi ? ` (DOI: ${x.doi})` : ""}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  <div style={{ marginBottom: 10 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "#94a3b8", marginBottom: 6 }}>
                      AI 실제 인용 출처
                    </div>
                    {aiCited.length > 0 ? (
                      <ul style={{ margin: 0, paddingLeft: 18, listStyleType: "disc" }}>
                        {aiCited.map((s, idx) => (
                          <SourceListItem key={`ai-${idx}`} s={s} />
                        ))}
                      </ul>
                    ) : (
                      <p style={{ color: "#64748b", fontSize: 13, margin: 0 }}>
                        이번 요청에서 AI가 직접 인용한 DOI/URL이 없습니다.
                      </p>
                    )}
                  </div>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "#94a3b8", marginBottom: 6 }}>
                      자동 검색 참고 후보 (Crossref/Semantic Scholar)
                    </div>
                    {retrieved.length > 0 ? (
                      <ul style={{ margin: 0, paddingLeft: 18, listStyleType: "disc" }}>
                        {retrieved.map((s, idx) => (
                          <SourceListItem key={`retr-${idx}`} s={s} />
                        ))}
                      </ul>
                    ) : (
                      <p style={{ color: "#64748b", fontSize: 13, margin: 0 }}>
                        아직 표시할 자동 검색 후보가 없습니다. 네트워크 제한 시 비어 있을 수 있습니다.
                      </p>
                    )}
                  </div>
                      </>
                    );
                  })()}
                </CollapsibleSection>

                {/* 구성 원소 역할 & 도펀트 추천 */}
                <CollapsibleSection
                  title="구성 원소 역할 / 도펀트 추천"
                  open={sectionOpen.roles}
                  onToggle={() => toggleSection("roles")}
                >
                  <h3 style={{ fontSize: 15, marginBottom: 8 }}>구성 원소 역할</h3>
                  <div className="result-prose-scroll" style={{ maxHeight: 220, marginBottom: 16 }}>
                    <AnalysisProse text={result.element_roles} compact />
                  </div>
                  <h3 style={{ fontSize: 15, marginBottom: 8 }}>도펀트 추천</h3>
                  <div className="result-prose-scroll" style={{ maxHeight: 220 }}>
                    <AnalysisProse text={result.dopant_rec} compact />
                  </div>
                </CollapsibleSection>

                {/* 리플로우 & 규제 요약 + 그래프 */}
                <CollapsibleSection
                  title="리플로우 프로파일 & 규제 요약"
                  open={sectionOpen.reflow}
                  onToggle={() => toggleSection("reflow")}
                >
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns:
                        "repeat(auto-fit, minmax(min(100%, 280px), 1fr))",
                      gap: 10,
                      marginBottom: 10,
                      alignItems: "start"
                    }}
                  >
                    <ReflowCard
                      solidus={reflowMeltDisplay.solidus}
                      liquidus={reflowMeltDisplay.liquidus}
                      peak={reflowPeakEffective}
                      modelPeak={reflowMeltDisplay.modelPeak}
                      profileMeta={reflowProfile?.meta}
                    />
                    <RegulationCard norm={result.norm} />
                  </div>
                  <ReflowChart
                    profile={reflowProfile}
                    solidus={reflowMeltDisplay.solidus}
                    liquidus={reflowMeltDisplay.liquidus}
                    expandable
                    expandPayload={{
                      result,
                      initialTune: reflowTune,
                      initialPeakUser: reflowPeakUser,
                      meltBasis: reflowMeltBasis
                    }}
                  />
                  {getAlloyInferenceMelt(result) ? (
                    <div
                      style={{
                        marginTop: 4,
                        marginBottom: 8,
                        padding: "8px 10px",
                        borderRadius: 8,
                        border: "1px solid #334155",
                        background: "rgba(15,23,42,0.5)",
                        fontSize: 12,
                        color: "#cbd5e1",
                        display: "flex",
                        flexWrap: "wrap",
                        gap: 10,
                        alignItems: "center"
                      }}
                    >
                      <span style={{ fontWeight: 600, color: "#94a3b8" }}>리플로우 곡선 기준</span>
                      <span style={{ color: "#64748b" }}>(고상·액상·초기 피크 슬라이더)</span>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                        <TactileButton
                          type="button"
                          onClick={() => setReflowMeltBasis("hybrid")}
                          style={{
                            padding: "5px 10px",
                            borderRadius: 6,
                            border:
                              reflowMeltBasis === "hybrid"
                                ? "1px solid #38bdf8"
                                : "1px solid #475569",
                            background:
                              reflowMeltBasis === "hybrid"
                                ? "rgba(56,189,248,0.15)"
                                : "transparent",
                            color: "#e2e8f0",
                            fontSize: 12,
                            fontWeight: 700,
                            cursor: "pointer"
                          }}
                        >
                          하이브리드 엔진
                        </TactileButton>
                        <TactileButton
                          type="button"
                          onClick={() => setReflowMeltBasis("inference")}
                          style={{
                            padding: "5px 10px",
                            borderRadius: 6,
                            border:
                              reflowMeltBasis === "inference"
                                ? "1px solid #a78bfa"
                                : "1px solid #475569",
                            background:
                              reflowMeltBasis === "inference"
                                ? "rgba(167,139,250,0.15)"
                                : "transparent",
                            color: "#e2e8f0",
                            fontSize: 12,
                            fontWeight: 700,
                            cursor: "pointer"
                          }}
                        >
                          데이터 추론(3-NN)
                        </TactileButton>
                      </div>
                      <span style={{ color: "#64748b", fontSize: 11 }}>
                        적용 중: {reflowMeltDisplay.label}
                      </span>
                    </div>
                  ) : (
                    <div style={{ fontSize: 11, color: "#64748b", marginBottom: 6 }}>
                      데이터 추론(3-NN) 결과가 없어 리플로우는 하이브리드 엔진 융점만 사용합니다.
                    </div>
                  )}
                  <ReflowTuneBar
                    liquidus={reflowMeltDisplay.liquidus}
                    modelPeak={reflowMeltDisplay.modelPeak}
                    reflowPeakUser={reflowPeakUser}
                    reflowPeakEffective={reflowPeakEffective}
                    presetName={reflowProfile?.meta?.presetName}
                    reflowTune={reflowTune}
                    onReflowTuneChange={setReflowTune}
                    onPeakChange={setReflowPeakUser}
                    onResetPeak={() => {
                      const md = getReflowMeltDisplay(result, reflowMeltBasis);
                      if (Number.isFinite(md.modelPeak)) setReflowPeakUser(Number(md.modelPeak));
                    }}
                    onResetTune={() => {
                      const name = pickPresetName(result);
                      const pset = { ...REFLOW_PRESETS.범용, ...(REFLOW_PRESETS[name] || {}) };
                      setReflowTune({
                        rampRate: pset.ramp_rate,
                        preheatTime: pset.preheat_time,
                        overLiquidusTime: pset.over_liquidus_time,
                        coolRate: pset.cool_rate,
                        peakMargin: pset.peak_margin
                      });
                    }}
                  />
                  <ImcInterfaceCard
                    result={result}
                    substrate={imcSubstrate}
                    talMode={imcTalMode}
                    talRef={imcTalRef}
                    talDeltaC={imcTalDeltaC}
                    talSec={imcTalSec}
                    reflowProfile={reflowProfile}
                    reflowTune={reflowTune}
                    presetName={reflowProfile?.meta?.presetName || pickPresetName(result)}
                    profileMeltOverride={imcProfileMeltOverride}
                    onSubstrateChange={setImcSubstrate}
                    onTalModeChange={setImcTalMode}
                    onTalRefChange={setImcTalRef}
                    onTalDeltaChange={(v) => setImcTalDeltaC(v)}
                    onTalSecChange={(v) => setImcTalSec(v)}
                  />
                </CollapsibleSection>

                {/* 엔지니어 원문: 엔지니어/연구소 모드 모두에서 표시. 엔지니어 모드일 때는 연구소 원문 블록을 숨김 */}
                {(reportMode === "eng" || reportMode === "lab") && (
                  <CollapsibleSection
                    title={
                      reportMode === "eng"
                        ? "한 장 요약 보고서 (비전문가용)"
                        : "엔지니어 기술 요약 보고서 (원문)"
                    }
                    open={sectionOpen.eng}
                    onToggle={() => toggleSection("eng")}
                  >
                    <div className="result-prose-scroll result-prose-scroll--tall" style={{ maxHeight: 440 }}>
                      <AnalysisProse text={result.eng_report} compact />
                    </div>
                  </CollapsibleSection>
                )}

                {reportMode === "lab" && result.lab_report && (
                  <CollapsibleSection
                    title="연구소 기술 보고서 (원문)"
                    open={sectionOpen.lab}
                    onToggle={() => toggleSection("lab")}
                  >
                    <p style={{ fontSize: 13, color: "#64748b", margin: "0 0 8px 0" }}>
                      이 블록은 &quot;연구소 모드&quot;로 분석을 실행했을 때만 서버에서 생성됩니다. 토글만
                      바꾼 경우에는 다시 &quot;분석&quot;을 눌러 주세요.
                    </p>
                    <div className="result-prose-scroll result-prose-scroll--tall" style={{ maxHeight: 500 }}>
                      <AnalysisProse text={result.lab_report} compact labReport />
                    </div>
                  </CollapsibleSection>
                )}
                {reportMode === "lab" && !result.lab_report && (
                  <p style={{ fontSize: 13, color: "#94a3b8", marginTop: 10 }}>
                    연구소 보고서를 보려면 상단에서 &quot;연구소 모드&quot;를 선택한 뒤 다시
                    &quot;분석&quot;을 실행하세요.
                  </p>
                )}
              </>
            )}

            {mode === "compare" && compareResult && resultPanelOpen && (
              <CompareView data={compareResult} compA={comp} compB={compB} />
            )}
          </div>
        </div>

        {mode === "single" && result ? (
          <AnalysisReportSlideshow
            open={chartReportOpen}
            onClose={() => setChartReportOpen(false)}
            payload={{
              result,
              profile: reflowProfile,
              melt: reflowMeltDisplay
            }}
          />
        ) : null}

        <footer
          style={{
            marginTop: 28,
            paddingTop: 16,
            borderTop: "1px solid var(--border-default)",
            fontSize: 13,
            color: "var(--text-muted)",
            lineHeight: 1.5
          }}
        >
          <div>
            제품·버전·면책은 상단 &quot;처리 방식·데이터 출처·면책&quot; 또는 데스크톱 GUI
            &quot;도움말 → 프로그램 정보&quot;와 동일 출처입니다.
          </div>
          <div style={{ marginTop: 6 }}>
            API 문서(Swagger):{" "}
            <a href="/docs" style={{ color: "var(--link)" }}>
              /docs
            </a>{" "}
            (FastAPI 서버 실행 시)
          </div>
        </footer>
      </main>
    </div>
  );
}

function tryKeyValLine(line) {
  const t = line.trim();
  const m = t.match(/^([^:[\]\n]{2,52}):\s*(.+)$/);
  if (!m) return null;
  const k = m[1].trim();
  const v = m[2].trim();
  if (!v) return null;
  if (/^https?$/i.test(k)) return null;
  // 문장 중 ':' 오인 (한글 서술이 키:값으로 잘리며 띄어쓰기가 깨지는 현상) 방지
  if (k.length > 40) return null;
  const kw = k.split(/\s+/).filter(Boolean);
  if (kw.length > 4) return null;
  if (k.length > 20 && kw.length > 1) return null;
  const hangul = /[\uAC00-\uD7A3]/.test(k);
  if (hangul) {
    if (k.length > 18) return null;
    if (kw.length > 2) return null;
  }
  return { k, v };
}

function parseAnalysisBlocks(raw) {
  const lines = String(raw || "").split(/\r?\n/);
  const out = [];
  let bulletRun = [];
  let paraLines = [];

  const flushBullets = () => {
    if (bulletRun.length) {
      out.push({ type: "bullets", items: bulletRun.slice() });
      bulletRun = [];
    }
  };
  const flushPara = () => {
    if (paraLines.length) {
      out.push({ type: "para", text: paraLines.join("\n").trim() });
      paraLines = [];
    }
  };

  const isBullet = (t) => {
    const s = t.trim();
    return /^[-•·*]\s/.test(s) || /^\d+[.)]\s/.test(s);
  };
  const stripBullet = (t) =>
    t
      .trim()
      .replace(/^[-•·*]\s*/, "")
      .replace(/^\d+[.)]\s*/, "");

  for (const line of lines) {
    const t = line.trim();
    if (!t) {
      flushBullets();
      flushPara();
      continue;
    }

    if (/^\[[^\]]+\]$/.test(t)) {
      flushBullets();
      flushPara();
      out.push({ type: "head", text: t });
      continue;
    }

    // [8] 물성 예측 … 처럼 번호·소제목을 한 줄에 쓴 경우(연구소 보고서) — 첫 ]에서 잘리지 않게 전체를 제목으로
    if (/^\[(\d+|\*)\]\s+.+/.test(t)) {
      flushBullets();
      flushPara();
      out.push({ type: "head", text: t });
      continue;
    }

    if (/^\[[^\]]+\]/.test(t)) {
      const end = t.indexOf("]");
      const head = t.slice(0, end + 1);
      const rest = t.slice(end + 1).trim();
      flushBullets();
      flushPara();
      out.push({ type: "head", text: head });
      if (rest) {
        const kv = tryKeyValLine(rest);
        if (kv) out.push({ type: "kv", k: kv.k, val: kv.v });
        else paraLines.push(rest);
      }
      continue;
    }

    if (isBullet(t)) {
      flushPara();
      bulletRun.push(stripBullet(t));
      continue;
    }

    if (bulletRun.length) flushBullets();

    const kv = tryKeyValLine(t);
    if (kv) {
      flushPara();
      out.push({ type: "kv", k: kv.k, val: kv.v });
      continue;
    }

    paraLines.push(t);
  }
  flushBullets();
  flushPara();
  return out;
}

/** 연구소 보고서: [8] 물성 예측 … 을 번호 배지 + 소제목으로 나란히 표시 */
function LabSectionHead({ text }) {
  const m = String(text).match(/^\[(\d+|\*)\]\s+(.+)$/);
  if (!m) {
    return <div className="result-prose-head">{text}</div>;
  }
  return (
    <div className="result-prose-head result-prose-head--section">
      <span className="result-prose-sec-badge" aria-hidden>
        [{m[1]}]
      </span>
      <span className="result-prose-sec-title">{m[2]}</span>
    </div>
  );
}

function AnalysisProse({ text, compact = false, labReport = false }) {
  const raw = String(text || "").trim();
  if (!raw || raw === "N/A") {
    return <p className="result-prose-muted">N/A</p>;
  }
  const blocks = parseAnalysisBlocks(raw);
  if (blocks.length === 0) {
    return <p className="result-prose-p">{raw}</p>;
  }
  const wrapClass = [
    compact ? "result-prose result-prose--compact" : "result-prose",
    labReport ? "result-prose--lab-report" : ""
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={wrapClass}>
      {blocks.map((b, i) => {
        if (b.type === "head") {
          if (labReport) {
            return <LabSectionHead key={i} text={b.text} />;
          }
          return (
            <div key={i} className="result-prose-head">
              {b.text}
            </div>
          );
        }
        if (b.type === "kv") {
          return (
            <div key={i} className="result-prose-kv">
              <span className="result-prose-kv-key">{b.k}</span>
              <span className="result-prose-kv-val">{b.val}</span>
            </div>
          );
        }
        if (b.type === "bullets") {
          return (
            <ul key={i} className="result-prose-ul">
              {b.items.map((item, j) => (
                <li key={j} className="result-prose-li">
                  {item}
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p key={i} className="result-prose-p">
            {b.text}
          </p>
        );
      })}
    </div>
  );
}

function CollapsibleSection({ title, open, onToggle, children, rightHint = "" }) {
  const triggerId = useId();
  const panelId = useId();
  return (
    <section style={{ marginTop: 10, minWidth: 0 }}>
      <button
        id={triggerId}
        type="button"
        className="tactile-hit collapsible-section-trigger"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        style={{
          width: "100%",
          display: "block",
          textAlign: "left",
          background: "#0b1220",
          border: "1px solid var(--border-muted)",
          borderRadius: 8,
          color: "#e5e7eb",
          padding: "8px 10px",
          cursor: "pointer",
          marginBottom: open ? 8 : 0
        }}
      >
        <span
          className="tactile-hit-label"
          style={{
            display: "flex",
            width: "100%",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8
          }}
        >
          <span style={{ fontSize: 15, fontWeight: 600 }}>
            {open ? "▾" : "▸"} {title}
          </span>
          {rightHint ? <span style={{ fontSize: 13, color: "#94a3b8" }}>{rightHint}</span> : null}
        </span>
      </button>
      {open ? (
        <div id={panelId} role="region" aria-labelledby={triggerId}>
          {children}
        </div>
      ) : null}
    </section>
  );
}

function AiSessionUsageRow({ usage }) {
  const snap = usage && typeof usage === "object" ? usage : {};
  const calls = Number(snap.full_analysis_calls ?? 0) || 0;
  const aiUsed = Number(snap.full_analysis_ai_used ?? 0) || 0;
  const fallbacks = Number(snap.full_analysis_fallbacks ?? 0) || 0;
  const qerr = Number(snap.ask_quota_errors ?? 0) || 0;
  const cerebrasOk = Number(snap.ask_cerebras_success ?? 0) || 0;
  const cerebrasTry = Number(snap.ask_cerebras_fallback ?? 0) || 0;
  const quotaLimited = qerr > 0 || Boolean(snap.quota_limited);
  const quotaTitle =
    quotaLimited && qerr > 0
      ? `AI 호출이 한도에 도달한 횟수: ${qerr}. Cerebras 폴백이 활성화되어 있으면 자동 전환됩니다.`
      : quotaLimited
        ? "쿼터 한도로 AI 문단이 생략될 수 있습니다. Cerebras 폴백이 활성화되어 있으면 자동 전환됩니다."
        : undefined;
  const quotaLabel =
    quotaLimited && qerr > 0
      ? `AI 호출 한도 · ${qerr}회`
      : "AI 호출 제한";
  const showSessionLine = calls > 0 || aiUsed > 0 || fallbacks > 0 || cerebrasOk > 0;
  const showCerebras = cerebrasOk > 0 || cerebrasTry > 0;
  if (!showSessionLine && !quotaLimited && !showCerebras) return null;
  return (
    <>
      {showSessionLine ? (
        <span
          style={{
            fontSize: 13,
            color: "#94a3b8",
            fontWeight: 500
          }}
        >
          AI 세션: 요청 {calls} / AI {aiUsed}
          {fallbacks > 0 ? ` / 로컬 폴백 ${fallbacks}` : ""}
          {cerebrasOk > 0 ? ` / Cerebras ${cerebrasOk}` : ""}
        </span>
      ) : null}
      {quotaLimited ? (
        <span
          title={quotaTitle}
          style={{
            fontSize: 13,
            fontWeight: 700,
            padding: "3px 10px",
            borderRadius: 6,
            border: "1px solid #b45309",
            background: "#78350f",
            color: "#fef3c7"
          }}
        >
          {quotaLabel}
        </span>
      ) : null}
      {showCerebras ? (
        <span
          title={`Gemini가 한도/오류일 때 Cerebras로 자동 전환된 횟수: 시도 ${cerebrasTry} / 성공 ${cerebrasOk}.`}
          style={{
            fontSize: 13,
            fontWeight: 700,
            padding: "3px 10px",
            borderRadius: 6,
            border: "1px solid #4338ca",
            background: "#312e81",
            color: "#e0e7ff"
          }}
        >
          Cerebras 폴백 · {cerebrasOk}회
        </span>
      ) : null}
    </>
  );
}

function AiModeBadge({ result }) {
  const summary = String(result?.ai_summary || "");
  const isLocalSummary =
    summary.startsWith("[로컬 하이브리드 요약]") ||
    summary.startsWith("[쉬운 요약 · 로컬 전용]") ||
    summary.startsWith("[쉬운 요약 · Gemini 미연결]");
  const rawMode = String(result?.ai_mode || "").toLowerCase();
  const isCerebras = rawMode === "cerebras";
  const isCache = rawMode === "cache" || String(result?.ai_source || "").toLowerCase() === "cache";
  const used = typeof result?.ai_used_this_request === "boolean"
    ? result.ai_used_this_request
    : (rawMode
      ? rawMode === "gemini" || rawMode === "cerebras" || rawMode === "cache"
      : !isLocalSummary);
  const mode = isCerebras ? "cerebras" : (isCache ? "cache" : (used ? "gemini" : "local"));
  const palette =
    mode === "cerebras"
      ? { border: "#4338ca", bg: "#4f46e5", title: "Gemini 한도/오류로 인해 이번 요청은 Cerebras 폴백으로 응답되었습니다.", label: "✓ 이번 요청: Cerebras 폴백 (AI+DB)" }
      : mode === "cache"
        ? { border: "#0e7490", bg: "#0891b2", title: "이전에 Gemini로 생성한 AI 응답을 디스크 캐시에서 재사용했습니다. 이번 요청에는 외부 API를 호출하지 않았습니다.", label: "✓ 이번 요청: AI 응답 캐시 재사용" }
        : mode === "gemini"
          ? { border: "#14532d", bg: "#16a34a", title: "Gemini 요약·문단이 포함된 하이브리드 결과입니다.", label: "✓ 이번 요청: AI+DB 하이브리드 분석" }
          : { border: "#9a3412", bg: "#ea580c", title: "융점·상분석·IMC 등은 DB/규칙으로 계산되었습니다. AI 문단은 쿼터·설정에 따라 생략될 수 있습니다.", label: "⚠ 이번 요청: DB/규칙 기반 분석" };
  return (
    <span
      title={palette.title}
      style={{
        fontSize: 13,
        padding: "3px 10px",
        borderRadius: 999,
        border: `1px solid ${palette.border}`,
        background: palette.bg,
        color: "white",
        fontWeight: 700,
        letterSpacing: 0.2
      }}
    >
      {palette.label}
    </span>
  );
}

function friendlyAiStatusMessage(raw) {
  const s = String(raw || "").trim();
  if (!s) return "";
  if (/^연결됨$/i.test(s)) return "";
  if (/Cerebras 폴백/i.test(s)) {
    if (/쿼터|429/i.test(s)) {
      return "Gemini 한도(429) 도달 — Cerebras로 자동 전환되어 응답을 생성했습니다.";
    }
    return "Gemini 호출 오류 — Cerebras 폴백으로 응답을 생성했습니다.";
  }
  if (/쿼터.*429|429.*쿼터|AI 쿼터 초과/i.test(s)) {
    return "AI 호출 한도에 도달해 일부 문단은 로컬 요약으로 대체되었습니다.";
  }
  if (/로컬 폴백/i.test(s)) {
    return "일부 AI 문단은 로컬 요약으로 제공됩니다.";
  }
  if (/GEMINI_API_KEY 없음|키 없음/i.test(s)) return "AI 키가 설정되지 않았습니다. DB·규칙 분석은 계속됩니다.";
  if (/SDK|초기화 실패|미설치/i.test(s)) return "AI 엔진 초기화에 문제가 있습니다. DB·규칙 분석은 계속됩니다.";
  if (/AI 호출 오류/i.test(s)) return "AI 호출 중 오류가 있었습니다. DB·규칙 분석은 계속됩니다.";
  return "";
}

function AiStatusDetail({ result }) {
  const status = String(result?.ai_status_detail || "").trim();
  if (!status || /^연결됨$/i.test(status)) return null;
  const friendly = friendlyAiStatusMessage(status);
  if (!friendly) return null;
  const isCerebras = /Cerebras/i.test(status);
  const palette = isCerebras
    ? { fg: "#e0e7ff", bg: "#312e81", border: "#4338ca", title: "Gemini 대신 Cerebras 폴백으로 응답이 생성되었습니다. 수치·DB 분석은 그대로 반영됩니다." }
    : { fg: "#fef3c7", bg: "#7c2d12", border: "#b45309", title: "수치·DB 분석 결과는 그대로 사용할 수 있습니다." };
  return (
    <span
      style={{
        fontSize: 13,
        color: palette.fg,
        background: palette.bg,
        border: `1px solid ${palette.border}`,
        borderRadius: 6,
        padding: "3px 8px",
        fontWeight: 600
      }}
      title={palette.title}
    >
      {friendly}
    </span>
  );
}

function sourceLinkFromString(s) {
  const t = String(s).trim();
  const upper = t.toUpperCase();
  // URL이 함께 있으면 URL을 우선 사용 (DOI 파싱 오류 가능성 회피)
  if (upper.startsWith("URL:")) {
    const u = t.slice(4).trim().split(/\s/)[0].replace(/[)\],.;]+$/g, "");
    if (u) return { href: u, text: t };
  }
  const um = t.match(/\bURL:\s*(\S+)/i);
  if (um && um[1]) {
    const u = String(um[1]).trim().replace(/[)\],.;]+$/g, "");
    if (u) return { href: u, text: t };
  }

  // DOI는 trailing punctuation 제거 + doi.org 접두 정규화
  const normalizeDoi = (raw) =>
    String(raw || "")
      .trim()
      .replace(/^https?:\/\/(dx\.)?doi\.org\//i, "")
      .replace(/[)\],.;]+$/g, "")
      .split(/\s/)[0];

  if (upper.startsWith("DOI:")) {
    const doi = normalizeDoi(t.slice(4));
    if (doi) return { href: `https://doi.org/${doi}`, text: t };
  }
  const m = t.match(/\bDOI:\s*([^\s]+)/i);
  if (m && m[1]) {
    const doi = normalizeDoi(m[1]);
    if (doi) return { href: `https://doi.org/${doi}`, text: t };
  }
  return { href: null, text: t };
}

function SourceListItem({ s }) {
  const { href, text } = sourceLinkFromString(s);
  return (
    <li style={{ fontSize: 13, marginBottom: 10, wordBreak: "break-word", lineHeight: 1.45 }}>
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: "#7dd3fc", textDecoration: "underline" }}
        >
          {text}
        </a>
      ) : (
        <span style={{ color: "var(--text-soft)" }}>{text}</span>
      )}
    </li>
  );
}

function ModeButton({ active, onClick, children, ariaSelected }) {
  return (
    <TactileButton
      role="tab"
      onClick={onClick}
      aria-selected={ariaSelected ?? active}
      labelStyle={{ display: "block", width: "100%", textAlign: "center" }}
      style={{
        width: "100%",
        minWidth: 0,
        minHeight: 44,
        padding: "10px 14px",
        borderRadius: 999,
        border: active ? "1px solid var(--accent)" : "1px solid var(--border-muted)",
        background: active ? "rgba(37,99,235,0.3)" : "var(--bg-page)",
        color: active ? "var(--text-primary)" : "var(--text-secondary)",
        fontSize: 13,
        fontWeight: active ? 650 : 500,
        boxShadow: active ? "0 0 0 2px rgba(96, 165, 250, 0.2), inset 0 1px 0 rgba(255,255,255,0.06)" : "none",
        cursor: "pointer"
      }}
    >
      {children}
    </TactileButton>
  );
}

function SmallToggleButton({ active, onClick, label }) {
  return (
    <TactileButton
      onClick={onClick}
      labelStyle={{ display: "block", width: "100%", textAlign: "center" }}
      style={{
        minHeight: 44,
        padding: "10px 12px",
        borderRadius: 999,
        border: active ? "1px solid var(--accent)" : "1px solid var(--border-muted)",
        background: active ? "rgba(37,99,235,0.3)" : "var(--bg-elevated)",
        color: active ? "var(--text-primary)" : "var(--text-secondary)",
        fontSize: 13,
        fontWeight: active ? 600 : 500,
        boxShadow: active
          ? "0 0 0 1px rgba(96, 165, 250, 0.18)"
          : "inset 0 0 0 1px var(--border-muted)",
        minWidth: 52,
        cursor: "pointer"
      }}
    >
      {label}
    </TactileButton>
  );
}

const SUMMARY_VARIANT_HINT = {
  solidus: "응고가 시작되는 쪽 온도(추정)",
  liquidus: "완전 액상(추정)",
  peak: "DSC/DTA 등 주요 열역학 신호(추정)",
  wetting:
    "젖음 측정 DB에서 IDW 보간한 Fmax(mN)·T₀(s). 상단에서 예측 온도(자동 또는 250–290℃) 선택 후 분석",
  tensileDb: "물성 DB 유사 합금 IDW 인장(MPa). BD 근접(≤3)이면 MODEL과 블렌드, 멀면 MODEL 대신 IDW·문헌만 표시"
};

/** 하단 폰트·숫자 비율 조정(젖음·인장 카드) — 설명 문구는 카드 밖 `SummaryWettingTensileFootnotes`로 표시 */
const SUMMARY_COMPACT_VALUE_VARIANTS = new Set(["wetting", "tensileDb"]);

function SummaryWettingTensileFootnotes() {
  return (
    <div className="summary-wetting-tensile-footnotes">
      <p>
        <span className="summary-footnote-label--wetting">젖음 Fmax</span>
        {" — "}
        {SUMMARY_VARIANT_HINT.wetting}
      </p>
      <p>
        <span className="summary-footnote-label--tensile">물성 DB 인장</span>
        {" — "}
        {SUMMARY_VARIANT_HINT.tensileDb}
      </p>
    </div>
  );
}

function formatWettingFmaxPrimary(props) {
  const f = Number(props?.wetting_fmax_pred_mn);
  const t0 = Number(props?.wetting_t0_pred_s);
  const tc = Number(props?.wetting_temp_c);
  if (!Number.isFinite(f)) return "—";
  let s = `${f.toFixed(2)} mN`;
  if (Number.isFinite(t0)) s += `\nT₀ ${t0.toFixed(2)} s`;
  if (Number.isFinite(tc)) s += ` @ ${tc.toFixed(0)}℃`;
  return s;
}

function formatTensileDbMpa(props) {
  const v = Number(props?.tensile_strength_db_mpa);
  return Number.isFinite(v) ? `${v.toFixed(1)} MPa` : "—";
}

function formatTensilePrimary(props) {
  const v = Number(props?.tensile_strength);
  return Number.isFinite(v) ? `${v.toFixed(1)} MPa` : formatTensileDbMpa(props);
}

function formatDensityPrimary(props) {
  const v = Number(props?.density);
  return Number.isFinite(v) ? `${v.toFixed(2)} g/cm³` : "N/A";
}

function tensileSummaryLabel(props) {
  const basis = props?.tensile_strength_basis;
  if (basis === "db_priority") return "인장 (DB우선)";
  if (basis === "db_idw") return "인장 (BD유사 IDW)";
  if (basis === "lit_ref") return "인장 (문헌 참고)";
  if (basis === "lit_blend") return "인장 (문헌 보정)";
  if (basis === "db_blend") return "인장 (BD 블렌드)";
  return "물성 DB 인장";
}

function tensileCompareLabel(a, b) {
  const bases = [a?.props?.tensile_strength_basis, b?.props?.tensile_strength_basis];
  if (bases.some((x) => x === "db_priority")) return "인장 (DB우선)";
  if (bases.some((x) => x === "db_idw")) return "인장 (BD유사)";
  if (bases.some((x) => x === "lit_ref")) return "인장 (문헌)";
  if (bases.some((x) => x === "lit_blend")) return "인장 (문헌보정)";
  return "인장";
}

function showCompareDbTensileRow(a, b) {
  const hideA = ["db_priority", "db_idw"].includes(a?.props?.tensile_strength_basis);
  const hideB = ["db_priority", "db_idw"].includes(b?.props?.tensile_strength_basis);
  if (hideA && hideB) return false;
  const hasA = !hideA && Number.isFinite(Number(a?.props?.tensile_strength_db_mpa));
  const hasB = !hideB && Number.isFinite(Number(b?.props?.tensile_strength_db_mpa));
  return hasA || hasB;
}

function SummaryCard({ label, value, variant }) {
  const gradients = {
    solidus: {
      background:
        "linear-gradient(145deg, #172554 0%, #1e40af 42%, #3b82f6 100%)",
      border: "1px solid rgba(147, 197, 253, 0.45)",
      boxShadow:
        "inset 0 1px 0 rgba(255,255,255,0.1), 0 4px 18px rgba(37, 99, 235, 0.28)",
      labelColor: "rgba(219, 234, 254, 0.92)",
      valueColor: "#f8fafc"
    },
    liquidus: {
      background:
        "linear-gradient(145deg, #431407 0%, #b45309 48%, #f97316 100%)",
      border: "1px solid rgba(253, 186, 116, 0.45)",
      boxShadow:
        "inset 0 1px 0 rgba(255,255,255,0.1), 0 4px 18px rgba(234, 88, 12, 0.26)",
      labelColor: "rgba(255, 237, 213, 0.95)",
      valueColor: "#fffbeb"
    },
    peak: {
      background:
        "linear-gradient(145deg, #3b0764 0%, #7c3aed 50%, #c084fc 100%)",
      border: "1px solid rgba(216, 180, 254, 0.45)",
      boxShadow:
        "inset 0 1px 0 rgba(255,255,255,0.1), 0 4px 18px rgba(124, 58, 237, 0.28)",
      labelColor: "rgba(237, 233, 254, 0.95)",
      valueColor: "#faf5ff"
    },
    dbConfidence: {
      background:
        "linear-gradient(145deg, #064e3b 0%, #059669 52%, #34d399 100%)",
      border: "1px solid rgba(110, 231, 183, 0.45)",
      boxShadow:
        "inset 0 1px 0 rgba(255,255,255,0.1), 0 4px 18px rgba(16, 185, 129, 0.24)",
      labelColor: "rgba(209, 250, 229, 0.95)",
      valueColor: "#ecfdf5"
    },
    overallConfidence: {
      background:
        "linear-gradient(145deg, #134e4a 0%, #0d9488 50%, #2dd4bf 100%)",
      border: "1px solid rgba(94, 234, 212, 0.45)",
      boxShadow:
        "inset 0 1px 0 rgba(255,255,255,0.1), 0 4px 18px rgba(13, 148, 136, 0.26)",
      labelColor: "rgba(204, 251, 241, 0.95)",
      valueColor: "#f0fdfa"
    },
    bestMatch: {
      background:
        "linear-gradient(145deg, #312e81 0%, #4f46e5 48%, #818cf8 100%)",
      border: "1px solid rgba(165, 180, 252, 0.45)",
      boxShadow:
        "inset 0 1px 0 rgba(255,255,255,0.1), 0 4px 18px rgba(79, 70, 229, 0.26)",
      labelColor: "rgba(224, 231, 255, 0.95)",
      valueColor: "#eef2ff"
    },
    wetting: {
      background:
        "linear-gradient(145deg, #0c4a6e 0%, #0369a1 48%, #38bdf8 100%)",
      border: "1px solid rgba(125, 211, 252, 0.45)",
      boxShadow:
        "inset 0 1px 0 rgba(255,255,255,0.1), 0 4px 18px rgba(14, 165, 233, 0.26)",
      labelColor: "rgba(224, 242, 254, 0.95)",
      valueColor: "#f0f9ff"
    },
    tensileDb: {
      background:
        "linear-gradient(145deg, #14532d 0%, #15803d 48%, #4ade80 100%)",
      border: "1px solid rgba(134, 239, 172, 0.45)",
      boxShadow:
        "inset 0 1px 0 rgba(255,255,255,0.1), 0 4px 18px rgba(22, 163, 74, 0.26)",
      labelColor: "rgba(220, 252, 231, 0.95)",
      valueColor: "#f0fdf4"
    }
  };
  const g = variant && gradients[variant] ? gradients[variant] : null;
  const compactValue = variant && SUMMARY_COMPACT_VALUE_VARIANTS.has(variant);
  const hintText =
    variant &&
    SUMMARY_VARIANT_HINT[variant] &&
    !SUMMARY_COMPACT_VALUE_VARIANTS.has(variant)
      ? SUMMARY_VARIANT_HINT[variant]
      : null;
  return (
    <div
      className="summary-card"
      style={{
        height: "100%",
        boxSizing: "border-box",
        display: "flex",
        flexDirection: "column",
        padding: 10,
        borderRadius: 10,
        border: g ? g.border : "1px solid var(--border-muted)",
        background: g ? g.background : "var(--bg-table-head)",
        boxShadow: g ? g.boxShadow : undefined
      }}
    >
      <div
        style={{
          fontSize: 13,
          color: g ? g.labelColor : "#9ca3af",
          marginBottom: 4,
          fontWeight: g ? 600 : 400,
          letterSpacing: g ? 0.02 : undefined,
          flexShrink: 0
        }}
      >
        {label}
      </div>
      <div
        style={{
          flex: "1 1 auto",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          minHeight: 0
        }}
      >
        <div
          style={{
            fontSize: compactValue ? 18 : 16,
            fontWeight: 700,
            color: g ? g.valueColor : undefined,
            wordBreak: "break-word",
            lineHeight: compactValue ? 1.3 : 1.35,
            textShadow: g ? "0 1px 2px rgba(0,0,0,0.25)" : undefined,
            whiteSpace: variant === "wetting" ? "pre-line" : undefined
          }}
        >
          {value}
        </div>
      </div>
      {hintText ? (
        <div
          style={{
            fontSize: compactValue ? 9 : 11,
            marginTop: compactValue ? 6 : 8,
            lineHeight: compactValue ? 1.32 : 1.35,
            fontWeight: 400,
            color: g ? g.labelColor : "#94a3b8",
            opacity: compactValue ? 0.82 : g ? 0.88 : 0.95,
            flexShrink: 0
          }}
        >
          {hintText}
        </div>
      ) : null}
    </div>
  );
}

function WettingByTempTable({ rows, proxyTemp, source, liquidus, basis, targetC, onLoadGrid, loadPending, loadError }) {
  const list = Array.isArray(rows) ? rows : [];
  const hi =
    Number.isFinite(Number(proxyTemp)) && list.some((r) => Number(r.temp_c) === Number(proxyTemp));
  if (list.length === 0) {
    const hint =
      source === "Heuristic"
        ? "젖음: 측정 DB 보간(IDW) 없이 휴리스틱만 사용했습니다. 온도별 표는 IDW 성공 시에만 의미가 있습니다."
        : "온도별 Fmax·T₀ 전체 표는 기본 분석에 포함하지 않습니다. 아래에서 불러오세요.";
    return (
      <div style={{ marginBottom: 16 }}>
        <div
          style={{
            marginBottom: 10,
            padding: 12,
            borderRadius: 10,
            border: "1px solid var(--border-muted)",
            background: "var(--bg-elevated)",
            fontSize: 12,
            color: "#94a3b8",
            lineHeight: 1.5
          }}
        >
          {hint}
        </div>
        {typeof onLoadGrid === "function" ? (
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
            <TactileButton
              onClick={onLoadGrid}
              disabled={!!loadPending}
              style={{
                padding: "8px 14px",
                borderRadius: 8,
                border: "1px solid var(--accent)",
                background: "rgba(37,99,235,0.2)",
                color: "var(--text-primary)",
                fontSize: 13,
                cursor: loadPending ? "wait" : "pointer"
              }}
            >
              {loadPending ? "온도별 젖음 표 불러오는 중…" : "온도별 Fmax·T₀ 표 불러오기"}
            </TactileButton>
            {loadError ? (
              <span style={{ fontSize: 12, color: "#f97316" }}>{loadError}</span>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  }
  return (
    <div style={{ marginBottom: 16 }}>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: 8,
          marginBottom: 8
        }}
      >
        <div
          style={{
            fontSize: 13,
            fontWeight: 700,
            color: "var(--text-primary)"
          }}
        >
          젖음 예측 (IDW)
        {Number.isFinite(Number(proxyTemp)) ? (
          <span style={{ fontWeight: 500, color: "#94a3b8", marginLeft: 8 }}>
            {basis === "compare_shared"
              ? `대표 행: 비교 공통 ${Number(proxyTemp).toFixed(0)}℃`
              : basis === "user" && Number.isFinite(Number(targetC))
                ? `대표 행: 선택 ${Number(targetC).toFixed(0)}℃ · ${Number(proxyTemp).toFixed(0)}℃`
                : basis === "auto_liq_plus_30" &&
                    Number.isFinite(Number(liquidus)) &&
                    Number.isFinite(Number(targetC))
                  ? `대표 행: 액상선 ${Number(liquidus).toFixed(1)}℃ +30°(목표≈${Number(targetC).toFixed(1)}℃) · ${Number(proxyTemp).toFixed(0)}℃`
                  : `대표 행: ${Number(proxyTemp).toFixed(0)}℃`}
          </span>
        ) : null}
        </div>
        {typeof onLoadGrid === "function" ? (
          <TactileButton
            onClick={onLoadGrid}
            disabled={!!loadPending}
            style={{
              padding: "6px 12px",
              borderRadius: 8,
              border: "1px solid var(--border-muted)",
              background: "var(--bg-elevated)",
              color: "var(--text-secondary)",
              fontSize: 12,
              cursor: loadPending ? "wait" : "pointer"
            }}
          >
            {loadPending ? "새로고침 중…" : "온도별 표 다시 불러오기"}
          </TactileButton>
        ) : null}
      </div>
      <div
        style={{
          border: "1px solid var(--border-muted)",
          borderRadius: 8,
          overflowX: "auto",
          background: "var(--bg-page)"
        }}
      >
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "var(--bg-table-head)" }}>
              <th style={ruleTh}>온도 (℃)</th>
              <th style={ruleTh}>Fmax (mN)</th>
              <th style={ruleTh}>T₀ (s)</th>
            </tr>
          </thead>
          <tbody>
            {list.map((r) => {
              const rowHi =
                hi && Number(r.temp_c) === Number(proxyTemp);
              const cell = {
                ...ruleTd,
                ...(rowHi
                  ? { background: "rgba(37, 99, 235, 0.14)", fontWeight: 600 }
                  : {})
              };
              return (
                <tr key={r.temp_c}>
                  <td style={cell}>{Number(r.temp_c).toFixed(0)}</td>
                  <td style={cell}>
                    {Number.isFinite(Number(r.fmax_mn)) ? Number(r.fmax_mn).toFixed(2) : "—"}
                  </td>
                  <td style={cell}>
                    {Number.isFinite(Number(r.t0_s)) ? Number(r.t0_s).toFixed(2) : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {loadError ? (
        <p style={{ fontSize: 12, color: "#f97316", margin: "8px 0 0 0" }}>{loadError}</p>
      ) : null}
      <p style={{ fontSize: 11, color: "#64748b", margin: "8px 0 0 0", lineHeight: 1.45 }}>
        높은 Fmax·낮은 T₀가 일반적으로 유리합니다. 상단 카드는 선택한 예측 온도(측정 DB 250–290℃에 맞춘 값)에서의 대표값입니다.
      </p>
    </div>
  );
}

function ResultAnalyzeSkeleton({ compareMode = false }) {
  return (
    <div className="result-analyze-skeleton" role="status" aria-live="polite" aria-label="분석 중">
      <p style={{ margin: "0 0 12px 0", fontSize: 14, color: "#94a3b8" }}>
        {compareMode
          ? "조성 A·B 융점·물성·IMC를 비교 계산하고 있습니다…"
          : "융점·상분석·문헌 요약을 계산하고 있습니다…"}
      </p>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 140px), 1fr))",
          gap: 8,
          opacity: 0.45
        }}
        aria-hidden
      >
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            style={{
              minHeight: 88,
              borderRadius: 10,
              background: "var(--bg-table-head)",
              border: "1px solid var(--border-muted)"
            }}
          />
        ))}
      </div>
    </div>
  );
}

function ResultSummaryBlock({
  result,
  showDbMeta = false,
  kpiGridRef,
  wettingSectionOpen,
  setWettingSectionOpen,
  wettingGridRows,
  wettingGridLoading,
  wettingGridError,
  loadWettingGrid
}) {
  const compNotes = Array.isArray(result.composition_notes) ? result.composition_notes : [];
  const compSum =
    typeof result.comp_input_wt_sum === "number" && Number.isFinite(result.comp_input_wt_sum)
      ? result.comp_input_wt_sum
      : null;
  return (
    <>
      {compNotes.length > 0 || compSum != null ? (
        <div
          role="status"
          style={{
            marginBottom: 12,
            padding: "10px 12px",
            borderRadius: 8,
            border: "1px solid rgba(245, 158, 11, 0.4)",
            background: "rgba(120, 53, 15, 0.25)",
            color: "#fde68a",
            fontSize: 12,
            lineHeight: 1.5
          }}
        >
          {compSum != null ? (
            <div style={{ marginBottom: compNotes.length ? 8 : 0, fontWeight: 600 }}>
              입력 wt% 합계(정규화 전): {compSum.toFixed(2)}%
            </div>
          ) : null}
          {compNotes.map((line, i) => (
            <div key={`cn-${i}`}>{line}</div>
          ))}
        </div>
      ) : null}
      <div
        ref={kpiGridRef}
        id="results-kpi-strip"
        className="result-fade-in"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 140px), 1fr))",
          gap: 8,
          marginBottom: 8,
          alignItems: "stretch"
        }}
      >
        <SummaryCard label="고상선" value={`${result.solidus.toFixed(1)} ℃`} variant="solidus" />
        <SummaryCard label="액상선" value={`${result.liquidus.toFixed(1)} ℃`} variant="liquidus" />
        <SummaryCard label="피크" value={`${result.peak.toFixed(1)} ℃`} variant="peak" />
        {showDbMeta ? (
          <>
            <SummaryCard label="DB 신뢰도" value={`${result.confidence.toFixed(1)} %`} variant="dbConfidence" />
            <SummaryCard
              label="종합 신뢰도"
              value={`${result.confidence_overall.toFixed(1)} %`}
              variant="overallConfidence"
            />
            <SummaryCard label="최적 일치" value={result.best_name || "N/A"} variant="bestMatch" />
          </>
        ) : null}
        <SummaryCard
          label="젖음 Fmax (IDW·측정 DB)"
          value={formatWettingFmaxPrimary(result.props)}
          variant="wetting"
        />
        {Number.isFinite(Number(result.props?.density)) ? (
          <SummaryCard
            label="비중"
            value={formatDensityPrimary(result.props)}
            variant="overallConfidence"
          />
        ) : null}
      </div>
      <SummaryWettingTensileFootnotes />
      {result.alloy_inference &&
      result.alloy_inference.solidus != null &&
      result.alloy_inference.liquidus != null ? (
        <div
          role="region"
          aria-label="데이터 추론 융점 및 리플로우 가이드"
          style={{
            marginBottom: 12,
            padding: "12px 14px",
            borderRadius: 8,
            border: "1px solid rgba(56, 189, 248, 0.35)",
            background: "rgba(15, 23, 42, 0.65)",
            color: "#e2e8f0",
            fontSize: 12,
            lineHeight: 1.55,
            whiteSpace: "pre-wrap"
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 8, color: "#7dd3fc" }}>
            데이터 추론 (상위 3개 DB 이웃 + 함량 민감도)
          </div>
          <div style={{ marginBottom: 6 }}>
            추정 고상선 {Number(result.alloy_inference.solidus).toFixed(1)} ℃ · 액상선{" "}
            {Number(result.alloy_inference.liquidus).toFixed(1)} ℃ · 권장 피크(참고) 약{" "}
            {Number(result.alloy_inference.recommended_peak_c).toFixed(1)} ℃
          </div>
          {Array.isArray(result.alloy_inference.neighbors) && result.alloy_inference.neighbors.length ? (
            <div style={{ marginBottom: 8, color: "#94a3b8", fontSize: 11 }}>
              이웃:{" "}
              {result.alloy_inference.neighbors
                .map((n) => `${n.name || "?"}(w=${Number(n.weight).toFixed(3)})`)
                .join(" · ")}
            </div>
          ) : null}
          <div style={{ marginBottom: 8, color: "#94a3b8", fontSize: 11, lineHeight: 1.45 }}>
            하이브리드 엔진 대비 Δ(추론 − 하이브리드): 고상{" "}
            {(Number(result.alloy_inference.solidus) - Number(result.solidus)).toFixed(2)} ℃ · 액상{" "}
            {(Number(result.alloy_inference.liquidus) - Number(result.liquidus)).toFixed(2)} ℃
            {Number.isFinite(Number(result.alloy_inference.recommended_peak_c)) &&
            Number.isFinite(Number(result.peak))
              ? ` · 권장피크(추) − 엔진피크 ${(
                  Number(result.alloy_inference.recommended_peak_c) - Number(result.peak)
                ).toFixed(1)} ℃`
              : null}
          </div>
          <div style={{ color: "#cbd5e1" }}>{String(result.alloy_inference.process_report || "").trim()}</div>
        </div>
      ) : null}
      <CollapsibleSection
        title="온도별 젖음 (Fmax·T₀)"
        open={wettingSectionOpen}
        onToggle={() => setWettingSectionOpen((v) => !v)}
      >
        <WettingByTempTable
          rows={wettingGridRows ?? result.props?.wetting_by_temp}
          proxyTemp={result.props?.wetting_temp_c}
          source={result.evidence?.wetting?.source}
          liquidus={result.liquidus}
          basis={result.props?.wetting_temp_basis}
          targetC={result.props?.wetting_temp_target_c}
          onLoadGrid={loadWettingGrid}
          loadPending={wettingGridLoading}
          loadError={wettingGridError}
        />
      </CollapsibleSection>
    </>
  );
}

function compareCompSumPct(comp) {
  if (!comp || typeof comp !== "object") return 0;
  return Object.values(comp).reduce((s, v) => s + (Number(v) || 0), 0);
}

/** 비교 헤더용: 입력 조성(wt%) — DB 최근접명(best.name)과 혼동되지 않게 표시 */
function formatCompareCompositionLabel(comp) {
  if (!comp || typeof comp !== "object") return "—";
  const keys = Object.keys(comp).filter((k) => Number(comp[k]) > 0);
  if (keys.length === 0) return "—";
  keys.sort((a, b) => {
    if (a === "Sn") return -1;
    if (b === "Sn") return 1;
    return a.localeCompare(b);
  });
  const parts = [];
  for (const k of keys) {
    const v = Number(comp[k]);
    if (!Number.isFinite(v) || v <= 0) continue;
    const t = Number.isInteger(v) ? String(v) : v >= 10 ? v.toFixed(1) : v.toFixed(2);
    parts.push(`${k} ${t}%`);
  }
  return parts.length ? parts.join(" · ") : "—";
}

function fmtDelta(na, nb, unit = "") {
  if (!Number.isFinite(na) || !Number.isFinite(nb)) return "-";
  const d = nb - na;
  const sign = d > 0 ? "+" : "";
  return `${sign}${d.toFixed(2)}${unit}`;
}

function fmtTextCell(v) {
  if (v === null || v === undefined) return "N/A";
  const s = String(v).trim();
  return s || "N/A";
}

/** 비교 표 텍스트를 문단(\n\n) 단위로 나눔 — A/B를 같은 행에 두어 가로 대응 */
function splitCompareParagraphs(v) {
  const cell = fmtTextCell(v);
  if (cell === "N/A") return ["N/A"];
  const parts = cell
    .split(/\n{2,}/)
    .map((s) => s.trim())
    .filter(Boolean);
  return parts.length > 0 ? parts : [cell];
}

/** 비교 모드: IMC·위험도는 수치 표 밖 2열 카드로 표시 (가독성) */
function CompareSummaryPair({ title, textA, textB, isLast, compact = false }) {
  const partsA = splitCompareParagraphs(textA);
  const partsB = splitCompareParagraphs(textB);
  const pStyle = (first) => ({
    margin: first ? 0 : compact ? "6px 0 0 0" : "12px 0 0 0",
    fontSize: compact ? 11 : 13,
    lineHeight: compact ? 1.45 : 1.65,
    color: "var(--text-soft)",
    whiteSpace: "pre-line",
    wordBreak: "keep-all",
    overflowWrap: "anywhere"
  });
  const card = (accent) => ({
    padding: compact ? "8px 10px" : "12px 14px",
    borderRadius: compact ? 8 : 10,
    border: "1px solid var(--border-default)",
    background: "#0b1220",
    borderLeft: `3px solid ${accent}`,
    minWidth: 0
  });
  return (
    <div className={compact ? "compare-summary-pair compare-summary-pair--compact" : undefined} style={{ marginBottom: isLast ? 0 : compact ? 8 : 18 }}>
      <div style={{ fontSize: compact ? 12 : 13, fontWeight: 600, color: "#e2e8f0", marginBottom: compact ? 6 : 10 }}>{title}</div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 280px), 1fr))",
          gap: 12,
          alignItems: "stretch"
        }}
      >
        <div style={card("#60a5fa")}>
          <div
            style={{
              fontSize: 11,
              fontWeight: 700,
              color: "#60a5fa",
              marginBottom: 8,
              letterSpacing: "0.02em"
            }}
          >
            A (기준)
          </div>
          {partsA.map((p, i) => (
            <p key={`a-${i}`} className={compact ? "compare-summary-pair__text" : undefined} style={pStyle(i === 0)} title={compact ? p : undefined}>
              {p}
            </p>
          ))}
        </div>
        <div style={card("#fb923c")}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#fb923c", marginBottom: compact ? 4 : 8 }}>B</div>
          {partsB.map((p, i) => (
            <p key={`b-${i}`} className={compact ? "compare-summary-pair__text" : undefined} style={pStyle(i === 0)} title={compact ? p : undefined}>
              {p}
            </p>
          ))}
        </div>
      </div>
    </div>
  );
}

function buildCompareHints(a, b) {
  const hints = [];
  const lsA = Number(a?.liquidus);
  const lsB = Number(b?.liquidus);
  const solA = Number(a?.solidus);
  const solB = Number(b?.solidus);
  if (Number.isFinite(lsA) && Number.isFinite(lsB) && Math.abs(lsA - lsB) > 0.5) {
    if (lsB > lsA) {
      hints.push(
        `액상선이 B가 ${(lsB - lsA).toFixed(1)}℃ 더 높습니다. B는 리플로우 피크·상한이 상대적으로 높아질 수 있습니다.`
      );
    } else {
      hints.push(
        `액상선이 A가 ${(lsA - lsB).toFixed(1)}℃ 더 높습니다. A 쪽 공정 온도 여유가 상대적으로 큽니다.`
      );
    }
  }
  const rangeA =
    Number.isFinite(lsA) && Number.isFinite(solA) ? lsA - solA : NaN;
  const rangeB =
    Number.isFinite(lsB) && Number.isFinite(solB) ? lsB - solB : NaN;
  if (
    Number.isFinite(rangeA) &&
    Number.isFinite(rangeB) &&
    Math.abs(rangeA - rangeB) > 3
  ) {
    hints.push(
      rangeB > rangeA
        ? `용융 구간(액상-고상)은 B(${rangeB.toFixed(1)}℃)가 A(${rangeA.toFixed(1)}℃)보다 넓습니다.`
        : `용융 구간은 A(${rangeA.toFixed(1)}℃)가 B(${rangeB.toFixed(1)}℃)보다 넓습니다.`
    );
  }
  const shA = Number(a?.props?.shear_strength);
  const shB = Number(b?.props?.shear_strength);
  if (Number.isFinite(shA) && Number.isFinite(shB) && Math.abs(shA - shB) > 3) {
    hints.push(
      shA > shB
        ? `물성 DB 유사 합금 기준 전단강도는 A가 약 ${(shA - shB).toFixed(1)} MPa 더 높게 나왔습니다.`
        : `물성 DB 유사 합금 기준 전단강도는 B가 약 ${(shB - shA).toFixed(1)} MPa 더 높게 나왔습니다.`
    );
  }
  const fmaxA = Number(a?.props?.wetting_fmax_pred_mn);
  const fmaxB = Number(b?.props?.wetting_fmax_pred_mn);
  const wetT = Number(a?.props?.wetting_temp_c);
  const wetTempNote = Number.isFinite(wetT) ? `${wetT.toFixed(0)}℃ 공통 온도에서 ` : "";
  if (Number.isFinite(fmaxA) && Number.isFinite(fmaxB) && Math.abs(fmaxB - fmaxA) > 0.05) {
    hints.push(
      fmaxB > fmaxA
        ? `${wetTempNote}예측 Fmax는 B가 약 ${(fmaxB - fmaxA).toFixed(2)} mN 더 큽니다.`
        : `${wetTempNote}예측 Fmax는 A가 약 ${(fmaxA - fmaxB).toFixed(2)} mN 더 큽니다.`
    );
  }
  const t0A = Number(a?.props?.wetting_t0_pred_s);
  const t0B = Number(b?.props?.wetting_t0_pred_s);
  if (Number.isFinite(t0A) && Number.isFinite(t0B) && Math.abs(t0B - t0A) > 0.03) {
    hints.push(
      t0B < t0A
        ? `${wetTempNote}예측 T₀는 B가 약 ${(t0A - t0B).toFixed(2)} s 더 짧습니다(젖음 속도 유리).`
        : `${wetTempNote}예측 T₀는 A가 약 ${(t0B - t0A).toFixed(2)} s 더 짧습니다(젖음 속도 유리).`
    );
  }
  return hints.slice(0, 6);
}

function compareTempScale(a, b) {
  const vals = [a?.solidus, a?.liquidus, a?.peak, b?.solidus, b?.liquidus, b?.peak]
    .map((v) => Number(v))
    .filter(Number.isFinite);
  if (!vals.length) return { min: 200, max: 260 };
  const rawMin = Math.min(...vals);
  const rawMax = Math.max(...vals);
  const pad = Math.max(6, (rawMax - rawMin) * 0.12);
  const min = Math.floor(rawMin - pad);
  const max = Math.ceil(rawMax + pad);
  return { min, max: Math.max(min + 24, max) };
}

function compareDeltaTone(delta) {
  if (delta == null || !Number.isFinite(delta)) return "flat";
  if (Math.abs(delta) < 0.05) return "flat";
  return delta > 0 ? "up" : "down";
}

function CompareTempBarChart({ a, b }) {
  const width = 640;
  const height = 176;
  const padL = 48;
  const padR = 28;
  const padT = 14;
  const padB = 36;
  const groupInset = 20;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;
  const { min, max } = compareTempScale(a, b);
  const baseY = padT + plotH;

  const mapY = (temp) => {
    const n = Number(temp);
    if (!Number.isFinite(n)) return null;
    const span = max - min;
    if (span <= 0) return padT;
    return padT + plotH - ((n - min) / span) * plotH;
  };

  const categories = [
    { id: "solidus", label: "고상선", va: a?.solidus, vb: b?.solidus },
    { id: "liquidus", label: "액상선", va: a?.liquidus, vb: b?.liquidus },
    { id: "peak", label: "피크", va: a?.peak, vb: b?.peak }
  ];

  const groupW = (plotW - groupInset * 2) / categories.length;
  const barW = Math.min(26, groupW * 0.2);
  const barGap = 5;
  const yTicks = [min, min + (max - min) * 0.5, max].map((t) => Math.round(t));

  const renderBar = (val, x, tone) => {
    const yTop = mapY(val);
    if (yTop == null) return null;
    const h = Math.max(2, baseY - yTop);
    const fill = tone === "a" ? "url(#compareBarGradA)" : "url(#compareBarGradB)";
    const n = Number(val);
    return (
      <g key={`${tone}-${x}`}>
        <rect
          x={x}
          y={yTop}
          width={barW}
          height={h}
          rx={4}
          fill={fill}
          stroke={tone === "a" ? "rgba(96, 165, 250, 0.55)" : "rgba(251, 146, 60, 0.55)"}
          strokeWidth={1}
        />
        <text
          x={x + barW / 2}
          y={yTop - 5}
          textAnchor="middle"
          fill="#e2e8f0"
          fontSize={10}
          fontFamily="inherit"
          fontWeight={600}
        >
          {n.toFixed(1)}
        </text>
      </g>
    );
  };

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      className="compare-hero-chart"
      role="img"
      aria-label="조성 A·B 융점 막대 비교 그래프"
    >
      <defs>
        <linearGradient id="compareBarGradA" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(96, 165, 250, 0.95)" />
          <stop offset="100%" stopColor="rgba(37, 99, 235, 0.45)" />
        </linearGradient>
        <linearGradient id="compareBarGradB" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(251, 146, 60, 0.95)" />
          <stop offset="100%" stopColor="rgba(234, 88, 12, 0.45)" />
        </linearGradient>
      </defs>

      <rect
        x={padL}
        y={padT}
        width={plotW}
        height={plotH}
        rx={6}
        fill="rgba(2, 6, 23, 0.55)"
        stroke="rgba(51, 65, 85, 0.75)"
        strokeWidth={1}
      />

      {yTicks.map((tick) => {
        const yy = mapY(tick);
        if (yy == null) return null;
        return (
          <g key={tick}>
            <line
              x1={padL}
              y1={yy}
              x2={padL + plotW}
              y2={yy}
              stroke="rgba(51, 65, 85, 0.55)"
              strokeWidth={1}
              strokeDasharray={tick === min || tick === max ? undefined : "4 4"}
            />
            <text
              x={padL - 8}
              y={yy + 4}
              textAnchor="end"
              fill="#64748b"
              fontSize={10}
              fontFamily="inherit"
            >
              {tick}℃
            </text>
          </g>
        );
      })}

      <line
        x1={padL}
        y1={baseY}
        x2={padL + plotW}
        y2={baseY}
        stroke="#64748b"
        strokeWidth={1.5}
      />
      <line x1={padL} y1={padT} x2={padL} y2={baseY} stroke="#64748b" strokeWidth={1.5} />

      {categories.map((cat, i) => {
        const cx = padL + groupInset + groupW * i + groupW / 2;
        const xA = cx - barW - barGap / 2;
        const xB = cx + barGap / 2;
        return (
          <g key={cat.id}>
            {renderBar(cat.va, xA, "a")}
            {renderBar(cat.vb, xB, "b")}
            <text
              x={cx}
              y={height - 18}
              textAnchor="middle"
              fill="#94a3b8"
              fontSize={11}
              fontFamily="inherit"
              fontWeight={600}
            >
              {cat.label}
            </text>
          </g>
        );
      })}

      <text
        x={16}
        y={padT + plotH / 2}
        textAnchor="middle"
        fill="#64748b"
        fontSize={10}
        fontFamily="inherit"
        transform={`rotate(-90 16 ${padT + plotH / 2})`}
      >
        온도 (℃)
      </text>

    </svg>
  );
}

function CompareHeroPanel({ a, b, compA, compB }) {
  const meltA =
    Number.isFinite(Number(a?.liquidus)) && Number.isFinite(Number(a?.solidus))
      ? Number(a.liquidus) - Number(a.solidus)
      : null;
  const meltB =
    Number.isFinite(Number(b?.liquidus)) && Number.isFinite(Number(b?.solidus))
      ? Number(b.liquidus) - Number(b.solidus)
      : null;

  const deltaSpecs = [
    { label: "액상선", va: a?.liquidus, vb: b?.liquidus, unit: "℃" },
    { label: "피크", va: a?.peak, vb: b?.peak, unit: "℃" },
    { label: "용융 구간", va: meltA, vb: meltB, unit: "℃" }
  ];

  return (
    <section className="compare-hero-panel result-fade-in" aria-label="비교 결과 시각 요약">
      <h3 className="compare-hero-panel__title">비교 결과</h3>
      <div className="compare-hero-chips">
        <div className="compare-hero-chip">
          <span className="compare-hero-chip__badge compare-hero-chip__badge--a">A</span>
          <span className="compare-hero-chip__text" title="입력 wt%">
            {formatCompareCompositionLabel(compA)}
            {a?.name ? (
              <span className="compare-hero-chip__db">DB 근접: {a.name}</span>
            ) : null}
          </span>
        </div>
        <div className="compare-hero-chip">
          <span className="compare-hero-chip__badge compare-hero-chip__badge--b">B</span>
          <span className="compare-hero-chip__text" title="입력 wt%">
            {formatCompareCompositionLabel(compB)}
            {b?.name ? (
              <span className="compare-hero-chip__db">DB 근접: {b.name}</span>
            ) : null}
          </span>
        </div>
      </div>

      <div className="compare-hero-legend" role="presentation" aria-hidden="true">
        <span className="compare-hero-legend__item compare-hero-legend__item--a">A</span>
        <span className="compare-hero-legend__item compare-hero-legend__item--b">B</span>
      </div>
      <div className="compare-hero-chart-wrap">
        <CompareTempBarChart a={a} b={b} />
      </div>

      <div className="compare-hero-deltas">
        {deltaSpecs.map(({ label, va, vb, unit }) => {
          const na = Number(va);
          const nb = Number(vb);
          const delta = Number.isFinite(na) && Number.isFinite(nb) ? nb - na : null;
          const tone = compareDeltaTone(delta);
          return (
            <span
              key={label}
              className={`compare-hero-delta compare-hero-delta--${tone}`}
              title="B − A (기준: 조성 A)"
            >
              <span className="compare-hero-delta__label">{label}</span>
              <span>
                {delta == null ? "—" : fmtDelta(na, nb, unit)}
              </span>
            </span>
          );
        })}
      </div>
    </section>
  );
}

function CompareView({ data, compA, compB }) {
  const { a, b } = data;
  const sumA = compareCompSumPct(compA);
  const sumB = compareCompSumPct(compB);
  const warnA = sumA > 0 && (sumA < 99 || sumA > 101);
  const warnB = sumB > 0 && (sumB < 99 || sumB > 101);
  const hints = buildCompareHints(a, b);

  const compareLabelTd = {
    padding: "8px 10px 8px 0",
    borderBottom: "1px solid var(--bg-table-head)",
    whiteSpace: "nowrap",
    verticalAlign: "middle",
    color: "#e2e8f0",
    fontWeight: 500,
    fontSize: 13
  };
  const compareNumTd = {
    padding: "8px 10px",
    borderBottom: "1px solid var(--bg-table-head)",
    fontVariantNumeric: "tabular-nums",
    verticalAlign: "middle",
    fontSize: 13
  };
  const compareNumTdRight = {
    ...compareNumTd,
    textAlign: "right"
  };

  const rowD = (label, va, vb, unit = "") => {
    const na = Number(va);
    const nb = Number(vb);
    const dText = fmtDelta(na, nb, unit);
    const dNum = Number.isFinite(na) && Number.isFinite(nb) ? nb - na : null;
    return (
      <tr>
        <td style={compareLabelTd}>{label}</td>
        <td style={compareNumTdRight}>{fmt(va, unit)}</td>
        <td style={compareNumTdRight}>{fmt(vb, unit)}</td>
        <td
          style={{
            ...compareNumTdRight,
            color:
              dNum == null
                ? "#64748b"
                : dNum > 0
                  ? "#fbbf24"
                  : dNum < 0
                    ? "#38bdf8"
                    : "#94a3b8"
          }}
          title="B − A (기준: 조성 A)"
        >
          {dText}
        </td>
      </tr>
    );
  };

  const meltA =
    Number.isFinite(Number(a?.liquidus)) && Number.isFinite(Number(a?.solidus))
      ? Number(a.liquidus) - Number(a.solidus)
      : NaN;
  const meltB =
    Number.isFinite(Number(b?.liquidus)) && Number.isFinite(Number(b?.solidus))
      ? Number(b.liquidus) - Number(b.solidus)
      : NaN;
  const compareWetT = Number(a?.props?.wetting_temp_c);
  const wetAtLabel = Number.isFinite(compareWetT) ? `(@${compareWetT.toFixed(0)}℃)` : "";
  const wetFmaxLabel = wetAtLabel ? `젖음Fmax ${wetAtLabel}` : "젖음Fmax";
  const shearLabel =
    a?.props?.shear_strength_basis === "db_idw" || b?.props?.shear_strength_basis === "db_idw"
      ? "전단 (BD유사)"
      : "전단";
  const showDbTensile = showCompareDbTensileRow(a, b);
  const wetT0Label = wetAtLabel ? `젖음T₀ ${wetAtLabel}` : "젖음T₀";

  return (
    <div className="compare-view">
      <AiSessionUsageRow usage={data?.ai_usage_snapshot} />

      {(warnA || warnB) && (
        <div className="compare-view__warn">
          <strong>조성 합계</strong>
          {warnA ? <span>A {sumA.toFixed(2)}%</span> : null}
          {warnB ? <span>B {sumB.toFixed(2)}%</span> : null}
        </div>
      )}

      <div className="compare-view__grid">
        <div className="compare-view__primary">
          <CompareHeroPanel a={a} b={b} compA={compA} compB={compB} />

          <table className="compare-metrics-table">
            <colgroup>
              <col className="compare-metrics-col-label" />
              <col className="compare-metrics-col-num" />
              <col className="compare-metrics-col-num" />
              <col className="compare-metrics-col-diff" />
            </colgroup>
            <thead>
              <tr>
                <th className="compare-metrics-th compare-metrics-th--label" />
                <th className="compare-metrics-th compare-metrics-th--a">A</th>
                <th className="compare-metrics-th compare-metrics-th--b">B</th>
                <th className="compare-metrics-th compare-metrics-th--diff" title="B − A (기준: 조성 A)">
                  B−A
                </th>
              </tr>
            </thead>
            <tbody>
              {rowD("고상선", a?.solidus, b?.solidus, "℃")}
              {rowD("액상선", a?.liquidus, b?.liquidus, "℃")}
              {rowD(
                "용융구간",
                Number.isFinite(meltA) ? meltA : null,
                Number.isFinite(meltB) ? meltB : null,
                "℃"
              )}
              {rowD("피크", a?.peak, b?.peak, "℃")}
              {rowD("신뢰도", a?.confidence, b?.confidence, "%")}
              {rowD(shearLabel, a?.props?.shear_strength, b?.props?.shear_strength, " MPa")}
              {rowD(wetFmaxLabel, a?.props?.wetting_fmax_pred_mn, b?.props?.wetting_fmax_pred_mn, " mN")}
              {rowD(wetT0Label, a?.props?.wetting_t0_pred_s, b?.props?.wetting_t0_pred_s, " s")}
              {rowD("비중", a?.props?.density, b?.props?.density, " g/cm³")}
              {showDbTensile
                ? rowD(
                    "DB인장",
                    ["db_priority", "db_idw"].includes(a?.props?.tensile_strength_basis)
                      ? null
                      : a?.props?.tensile_strength_db_mpa,
                    ["db_priority", "db_idw"].includes(b?.props?.tensile_strength_basis)
                      ? null
                      : b?.props?.tensile_strength_db_mpa,
                    " MPa"
                  )
                : null}
            </tbody>
          </table>
        </div>

        <div className="compare-view__secondary">
          {hints.length > 0 && (
            <details className="compare-hints">
              <summary>해석 힌트 ({hints.length})</summary>
              <ul>
                {hints.map((h, i) => (
                  <li key={i}>{h}</li>
                ))}
              </ul>
            </details>
          )}

          <CompareSummaryPair title="IMC" textA={a?.imc_line} textB={b?.imc_line} />
          <CompareSummaryPair title="위험도" textA={a?.risk_line} textB={b?.risk_line} isLast />
        </div>
      </div>

      <PropertyBars a={a} b={b} />
    </div>
  );
}

function fmt(v, unit = "") {
  if (v === null || v === undefined) return "N/A";
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  return `${n.toFixed(2)}${unit}`;
}

function PropertyBars({ a, b }) {
  const metrics = [
    { key: "shear_strength", label: "전단강도 (MPa)" },
    { key: "yield_strength", label: "항복강도 (MPa)" },
    { key: "elongation", label: "연신율 (%)" },
    { key: "wetting_fmax_pred_mn", label: "Fmax (mN)" },
    { key: "wetting_t0_pred_s", label: "T₀ (s)" },
    { key: "tensile_strength_db_mpa", label: "물성 DB 인장 (MPa)" },
    { key: "tensile_strength_lit_mpa", label: "문헌 참고 인장 (MPa)" }
  ];

  const trackStyle = {
    flex: 1,
    minWidth: 0,
    background: "var(--bg-page)",
    borderRadius: 4,
    border: "1px solid #111827",
    overflow: "hidden",
    height: 12
  };

  const rowStyle = {
    display: "flex",
    alignItems: "center",
    gap: 8,
    fontSize: 13
  };

  return (
    <div
      style={{
        marginTop: 6,
        paddingTop: 6,
        borderTop: "1px solid var(--bg-table-head)"
      }}
    >
      <div style={{ fontSize: 13, color: "#9ca3af", marginBottom: 6 }}>
        물성 시각 비교
      </div>
      {metrics.map((mtr) => {
        const rawA = a?.props?.[mtr.key];
        const rawB = b?.props?.[mtr.key];
        const hasA = rawA !== null && rawA !== undefined && rawA !== "";
        const hasB = rawB !== null && rawB !== undefined && rawB !== "";
        if (!hasA && !hasB) return null;
        const av = hasA ? Number(rawA) : 0;
        const bv = hasB ? Number(rawB) : 0;
        /* 항목마다 스케일 분리: MPa·%·지수를 한 max로 나누면 왜곡됨 */
        const denom = Math.max(av, bv, 1e-9);
        const awPct = av > 0 ? (av / denom) * 100 : 0;
        const bwPct = bv > 0 ? (bv / denom) * 100 : 0;
        /* 0이 아닌 값은 최소 몇 px 보이게 (너무 얇아지는 것 방지) */
        const barW = (pct) =>
          pct <= 0 ? "0%" : `${Math.max(pct, 3)}%`;

        return (
          <div key={mtr.key} style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 13, color: "#9ca3af", marginBottom: 4 }}>
              {mtr.label}
            </div>
            <div style={{ ...rowStyle, marginBottom: 4 }}>
              <span
                style={{
                  width: 16,
                  flexShrink: 0,
                  fontSize: 10,
                  fontWeight: 700,
                  color: "#60a5fa"
                }}
              >
                A
              </span>
              <div style={trackStyle}>
                <div
                  style={{
                    height: "100%",
                    width: barW(awPct),
                    background:
                      "linear-gradient(90deg, rgba(59,130,246,0.95), rgba(59,130,246,0.35))"
                  }}
                />
              </div>
              <span
                style={{
                  minWidth: 52,
                  flexShrink: 0,
                  textAlign: "right",
                  color: "#60a5fa",
                  fontVariantNumeric: "tabular-nums"
                }}
              >
                {av.toFixed(1)}
              </span>
            </div>
            <div style={rowStyle}>
              <span
                style={{
                  width: 16,
                  flexShrink: 0,
                  fontSize: 10,
                  fontWeight: 700,
                  color: "#fb923c"
                }}
              >
                B
              </span>
              <div style={trackStyle}>
                <div
                  style={{
                    height: "100%",
                    width: barW(bwPct),
                    background:
                      "linear-gradient(90deg, rgba(234,88,12,0.95), rgba(234,88,12,0.35))"
                  }}
                />
              </div>
              <span
                style={{
                  minWidth: 52,
                  flexShrink: 0,
                  textAlign: "right",
                  color: "#fb923c",
                  fontVariantNumeric: "tabular-nums"
                }}
              >
                {bv.toFixed(1)}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

const IMC_TAL_DEFAULT = {
  "Cu-OSP": 45,
  ENIG: 40,
  ImmAg: 42,
  ImmSn: 38
};

/** 데스크톱 `gui.py` `_build_peak_profile_curve` 프리셋 테이블과 동일 */
const REFLOW_PRESETS = {
  SAC: { ramp_rate: 1.6, preheat_time: 90.0, over_liquidus_time: 45.0, cool_rate: 3.0, peak_margin: 25.0 },
  "86(Sn-0.3Ag-0.7Cu)": {
    ramp_rate: 1.5,
    preheat_time: 90.0,
    over_liquidus_time: 25.0,
    cool_rate: 3.0,
    peak_margin: 25.0,
    reflow_thr: 227.0,
    peak_min: 240.0,
    peak_max: 255.0
  },
  "90(Sn-1.0Ag-0.7Cu)": {
    ramp_rate: 1.5,
    preheat_time: 90.0,
    over_liquidus_time: 25.0,
    cool_rate: 3.0,
    peak_margin: 25.0,
    reflow_thr: 224.0,
    peak_min: 240.0,
    peak_max: 255.0
  },
  "51(Sn-3Ag-0.5Cu-3Bi)": {
    ramp_rate: 1.5,
    preheat_time: 90.0,
    over_liquidus_time: 25.0,
    cool_rate: 3.0,
    peak_margin: 30.0,
    peak_min: 230.0,
    peak_max: 255.0
  },
  "92(Sn-0.3Ag-0.5Cu-3Bi)": {
    ramp_rate: 1.5,
    preheat_time: 90.0,
    over_liquidus_time: 25.0,
    cool_rate: 3.0,
    peak_margin: 30.0,
    peak_min: 235.0,
    peak_max: 255.0
  },
  "78(Sn-0.4Ag-57.6Bi)": {
    ramp_rate: 1.5,
    preheat_time: 90.0,
    over_liquidus_time: 75.0,
    cool_rate: 2.5,
    peak_margin: 35.0,
    preheat_start: 100.0,
    preheat_end: 125.0,
    reflow_thr: 140.0,
    peak_min: 175.0,
    peak_max: 190.0
  },
  "73(Sn-3Ag-15Bi-0.03In)": {
    ramp_rate: 1.5,
    preheat_time: 90.0,
    over_liquidus_time: 65.0,
    cool_rate: 2.5,
    peak_margin: 35.0,
    preheat_start: 100.0,
    preheat_end: 125.0,
    reflow_thr: 206.0,
    peak_min: 236.0,
    peak_max: 250.0
  },
  "Sn-Bi(저융점)": { ramp_rate: 1.3, preheat_time: 80.0, over_liquidus_time: 30.0, cool_rate: 2.5, peak_margin: 20.0 },
  "Sn-In(저융점)": { ramp_rate: 1.3, preheat_time: 80.0, over_liquidus_time: 30.0, cool_rate: 2.5, peak_margin: 20.0 },
  "Sn-Pb": { ramp_rate: 1.5, preheat_time: 90.0, over_liquidus_time: 40.0, cool_rate: 3.0, peak_margin: 25.0 },
  "Sn-Cu": { ramp_rate: 1.6, preheat_time: 90.0, over_liquidus_time: 45.0, cool_rate: 3.0, peak_margin: 25.0 },
  "Sn-Ag": { ramp_rate: 1.6, preheat_time: 90.0, over_liquidus_time: 45.0, cool_rate: 3.0, peak_margin: 25.0 },
  범용: { ramp_rate: 1.5, preheat_time: 90.0, over_liquidus_time: 25.0, cool_rate: 2.0, peak_margin: 20.0 }
};

function pickPresetName(result) {
  const r = result || {};
  const md = r.melting_detail && typeof r.melting_detail === "object" ? r.melting_detail : {};
  const family = String(md.family || "").trim();
  const norm = r.norm && typeof r.norm === "object" ? r.norm : {};
  const ag = Number(norm.Ag || 0);
  const cu = Number(norm.Cu || 0);
  const bi = Number(norm.Bi || 0);
  const inp = Number(norm.In || 0);
  if (bi >= 40.0 && family === "SnBi") return "78(Sn-0.4Ag-57.6Bi)";
  if (bi >= 10.0 && bi < 40.0 && ag >= 1.0 && cu < 0.3) {
    // 73 타입(Sn-3Ag-15Bi-0.03In 등) — wide-paste 중-Bi
    return "73(Sn-3Ag-15Bi-0.03In)";
  }
  if (bi < 1.0 && inp < 1.0 && Math.abs(cu - 0.7) <= 0.25) {
    if (Math.abs(ag - 0.3) <= 0.35) return "86(Sn-0.3Ag-0.7Cu)";
    if (Math.abs(ag - 1.0) <= 0.35) return "90(Sn-1.0Ag-0.7Cu)";
  }
  if (bi >= 2.0 && Math.abs(cu - 0.5) <= 0.35) {
    return ag >= 2.0 ? "51(Sn-3Ag-0.5Cu-3Bi)" : "92(Sn-0.3Ag-0.5Cu-3Bi)";
  }
  if (family === "SAC") return "SAC";
  if (family === "SnBi") return "Sn-Bi(저융점)";
  if (family === "SnIn") return "Sn-In(저융점)";
  if (family === "SnPb") return "Sn-Pb";
  if (family === "SnCu") return "Sn-Cu";
  if (family === "SnAg") return "Sn-Ag";
  return "범용";
}

/** alloy_inference가 유효하면 { solidus, liquidus, modelPeak } — 없으면 null */
function getAlloyInferenceMelt(result) {
  const ai = result?.alloy_inference;
  if (!ai || ai.solidus == null || ai.liquidus == null) return null;
  const solidus = Number(ai.solidus);
  const liquidus = Number(ai.liquidus);
  const recPeak = Number(ai.recommended_peak_c);
  if (!Number.isFinite(solidus) || !Number.isFinite(liquidus)) return null;
  return {
    solidus,
    liquidus,
    modelPeak: Number.isFinite(recPeak) ? recPeak : liquidus + 22
  };
}

/** 리플로우 차트/튜너에 쓸 고상·액상·기준 피크 */
function getReflowMeltDisplay(result, meltBasis) {
  const inf = getAlloyInferenceMelt(result);
  if (meltBasis === "inference" && inf) {
    return { ...inf, basis: "inference", label: "데이터 추론(3-NN)" };
  }
  const r = result || {};
  return {
    solidus: Number(r.solidus || 0),
    liquidus: Number(r.liquidus || 0),
    modelPeak: Number(r.peak || 0),
    basis: "hybrid",
    label: "하이브리드 엔진"
  };
}

/**
 * 데스크톱 `gui.py` `_build_peak_profile_curve`와 동일 규칙.
 * @returns {{ points: {t:number,y:number}[], meta: object }}
 */
function buildPeakProfilePoints(result, tune, peakUser, meltBasis = "hybrid") {
  const r = result || {};
  const md = getReflowMeltDisplay(r, meltBasis);
  const solidus = Number(md.solidus || 0);
  const liquidus = Number(md.liquidus || 0);
  const peakInModel = Number(md.modelPeak || 0);
  const presetName = pickPresetName(result);
  const base = REFLOW_PRESETS.범용;
  const pset = { ...base, ...(REFLOW_PRESETS[presetName] || {}) };

  const ramp_rate = Number.isFinite(tune?.rampRate) ? tune.rampRate : pset.ramp_rate;
  const cool_rate = Number.isFinite(tune?.coolRate) ? tune.coolRate : pset.cool_rate;
  const preheat_time = Number.isFinite(tune?.preheatTime) ? tune.preheatTime : pset.preheat_time;
  const over_liquidus_time = Number.isFinite(tune?.overLiquidusTime)
    ? tune.overLiquidusTime
    : pset.over_liquidus_time;
  const peak_margin = Number.isFinite(tune?.peakMargin) ? tune.peakMargin : pset.peak_margin;

  const peak_in = Number.isFinite(peakUser) ? Number(peakUser) : peakInModel;

  const t_ambient = 25.0;
  const t_pre_start = pset.preheat_start != null ? Number(pset.preheat_start) : 150.0;
  const t_pre_end =
    pset.preheat_end != null
      ? Number(pset.preheat_end)
      : Math.min(190.0, Math.max(t_pre_start + 20.0, solidus - 5.0));
  const t_reflow_thr =
    pset.reflow_thr != null ? Number(pset.reflow_thr) : Math.max(liquidus, t_pre_end + 15.0);

  let peak = Math.max(peak_in, liquidus + Math.max(10.0, peak_margin));
  if (pset.peak_min != null) peak = Math.max(Number(pset.peak_min), peak);
  if (pset.peak_max != null) peak = Math.min(Number(pset.peak_max), peak);

  const dt_a = Math.max(25.0, (t_pre_start - t_ambient) / ramp_rate);
  const dt_b = Math.max(60.0, Math.min(140.0, preheat_time));
  const dt_c = Math.max(15.0, (t_reflow_thr - t_pre_end) / ramp_rate);
  const dt_d = Math.max(10.0, (peak - t_reflow_thr) / ramp_rate);
  const dt_e = Math.max(25.0, Math.min(120.0, over_liquidus_time));
  const t_cool_end = Math.min(160.0, Math.max(80.0, t_pre_end));
  const dt_f = Math.max(30.0, (peak - t_cool_end) / cool_rate);

  const t0 = 0.0;
  const tA = t0 + dt_a;
  const tB = tA + dt_b;
  const tC = tB + dt_c;
  const tD = tC + dt_d;
  const tE = tD + dt_e;
  const tF = tE + dt_f;

  const time = [t0, tA, tB, tC, tD, tE, tF];
  const temp = [t_ambient, t_pre_start, t_pre_end, t_reflow_thr, peak, peak - 5.0, t_cool_end];
  const points = time.map((t, i) => ({ t, y: temp[i] }));

  return {
    points,
    meta: {
      presetName,
      peak,
      liquidus,
      solidus,
      ramp_rate,
      cool_rate,
      peak_margin,
      dt_b,
      dt_e,
      dt_a,
      dt_c,
      dt_d,
      dt_f,
      t_pre_start,
      t_pre_end,
      t_reflow_thr,
      t0,
      tA,
      tB,
      tC,
      tD,
      tE,
      tF,
      meltBasis: md.basis || meltBasis
    }
  };
}

function calcAbove(points, thresholdC) {
  let tot = 0;
  for (let i = 0; i < points.length - 1; i += 1) {
    const p0 = points[i];
    const p1 = points[i + 1];
    const dt = p1.t - p0.t;
    if (dt <= 0) continue;
    const y0 = p0.y;
    const y1 = p1.y;
    if (y0 <= thresholdC && y1 <= thresholdC) continue;
    if (y0 >= thresholdC && y1 >= thresholdC) {
      tot += dt;
      continue;
    }
    const ratio = (thresholdC - y0) / (y1 - y0 || 1e-9);
    const tcross = p0.t + ratio * dt;
    if (y0 > thresholdC && y1 < thresholdC) tot += Math.max(0, tcross - p0.t);
    else if (y0 < thresholdC && y1 > thresholdC) tot += Math.max(0, p1.t - tcross);
  }
  return tot;
}

function calcInRange(points, lowC, highC) {
  if (!Number.isFinite(lowC) || !Number.isFinite(highC) || highC <= lowC) return 0;
  let tot = 0;
  for (let i = 0; i < points.length - 1; i += 1) {
    const p0 = points[i];
    const p1 = points[i + 1];
    const dt = p1.t - p0.t;
    if (dt <= 0) continue;
    const y0 = p0.y;
    const y1 = p1.y;
    const m = (y1 - y0) / dt;
    const cuts = [0, dt];
    if (Math.abs(m) > 1e-9) {
      const a = (lowC - y0) / m;
      const b = (highC - y0) / m;
      if (a > 0 && a < dt) cuts.push(a);
      if (b > 0 && b < dt) cuts.push(b);
    }
    cuts.sort((a, b) => a - b);
    for (let j = 0; j < cuts.length - 1; j += 1) {
      const a = cuts[j];
      const b = cuts[j + 1];
      const midT = (a + b) / 2;
      const ymid = y0 + m * midT;
      if (ymid >= lowC && ymid <= highC) tot += b - a;
    }
  }
  return tot;
}

function computeProfileMetrics(result, talRef, talDeltaC, profileOpts = {}) {
  const mo = profileOpts.meltOverride;
  const solidus = Number.isFinite(mo?.solidus) ? Number(mo.solidus) : Number(result?.solidus || 0);
  const liquidus = Number.isFinite(mo?.liquidus) ? Number(mo.liquidus) : Number(result?.liquidus || 0);
  const modelPeak = Number(result?.peak || 0);
  const pts = profileOpts.points;
  let peak = Number.isFinite(profileOpts.peakForMetrics)
    ? Number(profileOpts.peakForMetrics)
    : modelPeak;
  if (!Number.isFinite(peak)) peak = modelPeak;
  if (!pts || pts.length < 2) {
    const ref = talRef === "liq3" ? "Liquidus+3C" : talRef === "delta" ? "Liquidus+Δ" : "Liquidus";
    const thr = liquidus + (talRef === "liq3" ? 3 : talRef === "delta" ? Number(talDeltaC || 0) : 0);
    return {
      talS: 0,
      talRefLabel: ref,
      talThrC: thr,
      tSlS: 0,
      tPk5S: 0
    };
  }
  const ref = talRef === "liq3" ? "Liquidus+3C" : talRef === "delta" ? "Liquidus+Δ" : "Liquidus";
  const thr = liquidus + (talRef === "liq3" ? 3 : talRef === "delta" ? Number(talDeltaC || 0) : 0);
  return {
    talS: calcAbove(pts, thr),
    talRefLabel: ref,
    talThrC: thr,
    tSlS: calcInRange(pts, solidus, liquidus),
    tPk5S: calcAbove(pts, peak - 5)
  };
}

/** peakC: 리플로우 튜닝 적용 피크(없으면 분석 peak) — TAL 시간과 동일 프로파일 기준 */
function computeImcLayers(result, substrate, talSec, peakC, liquidusOverride) {
  const modelPeak = Number(result?.peak || 240);
  const peak = Number.isFinite(peakC) ? Number(peakC) : modelPeak;
  const liquidus = Number.isFinite(liquidusOverride)
    ? Number(liquidusOverride)
    : Number(result?.liquidus || 217);
  const T = Math.max(liquidus + 1, peak);
  const R = 8.314;
  const Tk = T + 273.15;
  const t = Math.max(1, Number(talSec || 30));
  const arr = (k0, q) => k0 * Math.exp(-q / (R * Tk));
  const sqt = Math.sqrt(t);

  let cu3sn = arr(0.020, 55000) * sqt;
  let cu6sn5 = arr(0.090, 40000) * sqt;
  let ni3sn4 = 0;
  const agPct = Number(result?.norm?.Ag || 0);
  let ag3sn = agPct > 0 ? Math.max(0.08, agPct * 0.05) : 0;

  if (substrate === "ENIG") {
    ni3sn4 = arr(0.050, 50000) * sqt;
    cu3sn *= 0.45;
    cu6sn5 *= 0.65;
  } else if (substrate === "ImmAg") {
    cu3sn *= 0.70;
    cu6sn5 *= 1.08;
    ag3sn *= 1.2;
  } else if (substrate === "ImmSn") {
    cu3sn *= 0.85;
    cu6sn5 *= 1.02;
  }

  const base = [
    { name: substrate === "ENIG" ? "Ni/Pd/Au 표면층" : `${substrate} 표면층`, um: 0.35, color: "#fbbf24" },
    { name: "Cu Pad", um: 12.0, color: "#f59e0b" },
    { name: "Cu3Sn", um: Math.max(0.08, cu3sn), color: "#ca8a04" },
    { name: "Cu6Sn5", um: Math.max(0.15, cu6sn5), color: "#f59e0b" }
  ];
  if (ni3sn4 > 0.02) base.splice(2, 0, { name: "Ni3Sn4", um: ni3sn4, color: "#a78bfa" });
  base.push({ name: "Solder Matrix", um: 20.0, color: "#94a3b8" });
  if (ag3sn > 0) {
    base.push({ name: "Ag3Sn 분산상", um: ag3sn, color: "#d1d5db" });
  }
  return base;
}

function imcSubstrateVisuals(substrate) {
  switch (substrate) {
    case "ENIG":
      return {
        padFill: "#d4b896",
        padStroke: "#92400e",
        padLabel: "Cu 패드 (ENIG, Ni/Pd/Au 위에 IMC 성장)",
        finishFill: "#fde68a",
        finishLabel: "Ni/Pd/Au 표면층"
      };
    case "ImmAg":
      return {
        padFill: "#e8d5b0",
        padStroke: "#b45309",
        padLabel: "Cu 패드 (ImmAg)",
        finishFill: "#e2e8f0",
        finishLabel: "ImmAg 표면층"
      };
    case "ImmSn":
      return {
        padFill: "#dcc8a0",
        padStroke: "#92400e",
        padLabel: "Cu 패드 (ImmSn)",
        finishFill: "var(--text-soft)",
        finishLabel: "ImmSn 표면층"
      };
    default:
      return {
        padFill: "#e9d8a6",
        padStroke: "#a16207",
        padLabel: "Cu 패드 (OSP)",
        finishFill: "#fbbf24",
        finishLabel: "Cu-OSP 표면층"
      };
  }
}

function ImcInterfaceCard({
  result,
  substrate,
  talMode,
  talRef,
  talDeltaC,
  talSec,
  reflowProfile,
  reflowTune,
  presetName,
  profileMeltOverride,
  onSubstrateChange,
  onTalModeChange,
  onTalRefChange,
  onTalDeltaChange,
  onTalSecChange
}) {
  // Hooks는 early-return 보다 위에서 호출되어야 함(React rules-of-hooks).
  const guardrailRes = useMemo(
    () => validateProfileTune(reflowTune, presetName),
    [reflowTune, presetName]
  );
  if (!result) return null;
  const guardrailHeadline = (() => {
    if (guardrailRes.errors.length > 0) return { tone: "ERR", msg: guardrailRes.errors[0] };
    if (guardrailRes.warnings.length > 0) return { tone: "WARN", msg: guardrailRes.warnings[0] };
    if (guardrailRes.oks.length > 0) return { tone: "OK", msg: guardrailRes.oks[0] };
    return null;
  })();
  const metrics = computeProfileMetrics(result, talRef, talDeltaC, {
    points: reflowProfile?.points,
    peakForMetrics: reflowProfile?.meta?.peak,
    meltOverride: profileMeltOverride
  });
  const talS = talMode === "manual" ? Number(talSec || 0) : metrics.talS;
  const liqImc = Number.isFinite(profileMeltOverride?.liquidus)
    ? Number(profileMeltOverride.liquidus)
    : Number(result?.liquidus || 217);
  const layers = computeImcLayers(result, substrate, talS, reflowProfile?.meta?.peak, liqImc);
  const sumUm = layers.reduce((a, x) => a + Number(x.um || 0), 0);
  const norm = result?.norm || {};
  const visAg = Number(norm.Ag || 0);
  const visCu = Number(norm.Cu || 0);
  const visBi = Number(norm.Bi || 0);
  const visIn = Number(norm.In || 0);
  const visSb = Number(norm.Sb || 0);
  const visNi = Number(norm.Ni || 0);
  const visZn = Number(norm.Zn || 0);
  const visPb = Number(norm.Pb || 0);

  const bulkLegend = [{ name: "β-Sn matrix", color: "#bfd6ea", type: "grain" }];
  if (visAg > 0) bulkLegend.push({ name: "Ag3Sn 분산상", color: "#9ca3af", type: "dash" });
  if (visCu > 0) bulkLegend.push({ name: "Cu6Sn5 분산상", color: "#b45309", type: "hex" });
  if (visBi > 0) bulkLegend.push({ name: "Bi 농화 분산상", color: "#d97706", type: "dot" });
  if (visIn > 0) bulkLegend.push({ name: "In 농화상", color: "#7dd3fc", type: "dot2" });
  if (visSb > 0) bulkLegend.push({ name: "SnSb 계 분산상", color: "#f97316", type: "dot2" });
  if (visNi > 0) bulkLegend.push({ name: "Ni 계 안정화상", color: "#a78bfa", type: "dot2" });
  if (visZn > 0) bulkLegend.push({ name: "Zn 농화 분산상", color: "#22c55e", type: "dot2" });
  if (visPb > 0) bulkLegend.push({ name: "Pb 농화 분산상", color: "#f59e0b", type: "dot2" });

  const pickUm = (name) => {
    const hit = layers.find((x) => String(x.name || "").toLowerCase() === String(name).toLowerCase());
    return Number(hit?.um || 0);
  };
  const topUm = pickUm(substrate === "ENIG" ? "Ni/Pd/Au 표면층" : `${substrate} 표면층`);
  const cu3Um = pickUm("Cu3Sn");
  const cu6Um = pickUm("Cu6Sn5");
  const ni3Um = pickUm("Ni3Sn4");
  const ag3Um = pickUm("Ag3Sn 분산상");
  const subVis = imcSubstrateVisuals(substrate);
  const showNiLayer = ni3Um > 0.02;
  const showFinishStrip = topUm > 0.001;
  const scallopDipY = Math.max(124, 168 - Math.min(48, 6 + cu6Um * 11));
  const hCu3Px = Math.max(20, Math.min(46, 18 + Math.min(cu3Um, 4) * 6));
  const hNiPx = showNiLayer ? Math.max(10, Math.min(26, 8 + ni3Um * 14)) : 0;
  const hFinPx = showFinishStrip ? 12 : 0;
  const yCu3Top = 206;
  const yCu3Bot = yCu3Top + hCu3Px;
  const yNiTop = yCu3Bot;
  const yNiBot = yNiTop + hNiPx;
  const yAfterMetal = showNiLayer ? yNiBot : yCu3Bot;
  const yFinTop = yAfterMetal;
  const yFinBot = yFinTop + hFinPx;
  const yPadTop = yFinBot;
  const yPadBot = 320;

  return (
    <div
      style={{
        marginTop: 12,
        padding: 12,
        borderRadius: 10,
        border: "1px solid #334155",
        background: "linear-gradient(180deg, var(--bg-table-head) 0%, var(--bg-page) 100%)"
      }}
    >
      <div style={{ fontSize: 13, color: "#e2e8f0", marginBottom: 8, fontWeight: 600 }}>
        IMC 계면 3D 단면(직관형)
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 8 }}>
        <label style={{ fontSize: 13, color: "var(--text-soft)" }}>
          기판
          <select
            value={substrate}
            onChange={(e) => onSubstrateChange(e.target.value)}
            style={ctlStyle}
          >
            <option>Cu-OSP</option>
            <option>ENIG</option>
            <option>ImmAg</option>
            <option>ImmSn</option>
          </select>
        </label>
        <label style={{ fontSize: 13, color: "var(--text-soft)" }}>
          TAL 모드
          <select value={talMode} onChange={(e) => onTalModeChange(e.target.value)} style={ctlStyle}>
            <option value="auto">AUTO(profile)</option>
            <option value="manual">사용자입력</option>
          </select>
        </label>
        <label style={{ fontSize: 13, color: "var(--text-soft)" }}>
          TAL 기준
          <select value={talRef} onChange={(e) => onTalRefChange(e.target.value)} style={ctlStyle}>
            <option value="liq">Liquidus</option>
            <option value="liq3">Liquidus+3C</option>
            <option value="delta">Liquidus+Δ</option>
          </select>
        </label>
        <label style={{ fontSize: 13, color: "var(--text-soft)" }}>
          ΔC
          <input
            type="number"
            min={0}
            max={30}
            step={0.5}
            value={talDeltaC}
            disabled={talRef !== "delta"}
            onChange={(e) => onTalDeltaChange(Number(e.target.value || 0))}
            style={ctlStyle}
          />
        </label>
        <label style={{ fontSize: 13, color: "var(--text-soft)" }}>
          TAL(s)
          <input
            type="number"
            min={5}
            max={180}
            step={1}
            value={talMode === "manual" ? talSec : Math.round(metrics.talS)}
            disabled={talMode !== "manual"}
            onChange={(e) => onTalSecChange(Number(e.target.value || IMC_TAL_DEFAULT[substrate] || 35))}
            style={ctlStyle}
          />
        </label>
      </div>

      <div style={{ marginTop: 10, fontSize: 13, color: "#93c5fd", lineHeight: 1.5 }}>
        TAL {talS.toFixed(1)}s ({metrics.talRefLabel}={metrics.talThrC.toFixed(1)}℃) | S~L{" "}
        {metrics.tSlS.toFixed(1)}s | Peak-5 {metrics.tPk5S.toFixed(1)}s
      </div>

      {/* ─── 튜닝 가드레일 미니 요약 (리플로우 튜너와 동일 규칙) ─── */}
      {guardrailHeadline ? (
        <details
          style={{
            marginTop: 8,
            padding: "6px 8px",
            borderRadius: 6,
            border: "1px solid #334155",
            background: "var(--bg-page)"
          }}
        >
          <summary
            style={{
              fontSize: 12,
              cursor: "pointer",
              color:
                guardrailHeadline.tone === "ERR"
                  ? "#f87171"
                  : guardrailHeadline.tone === "WARN"
                  ? "#fbbf24"
                  : "#86efac"
            }}
          >
            {guardrailHeadline.tone === "ERR" ? "❌" : guardrailHeadline.tone === "WARN" ? "⚠" : "✓"}{" "}
            튜닝 가드레일: {guardrailHeadline.msg}
            {guardrailRes.errors.length + guardrailRes.warnings.length + guardrailRes.oks.length > 1 ? (
              <span style={{ marginLeft: 6, color: "#64748b" }}>
                (+{guardrailRes.errors.length + guardrailRes.warnings.length + guardrailRes.oks.length - 1})
              </span>
            ) : null}
          </summary>
          <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 3 }}>
            {guardrailRes.errors.map((m, i) => (
              <div key={`ie-${i}`} style={{ fontSize: 12, color: "#f87171" }}>❌ {m}</div>
            ))}
            {guardrailRes.warnings.map((m, i) => (
              <div key={`iw-${i}`} style={{ fontSize: 12, color: "#fbbf24" }}>⚠ {m}</div>
            ))}
            {guardrailRes.oks.map((m, i) => (
              <div key={`io-${i}`} style={{ fontSize: 12, color: "#86efac" }}>✓ {m}</div>
            ))}
          </div>
        </details>
      ) : null}

      <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "minmax(260px,1.2fr) minmax(210px,0.8fr)", gap: 10 }}>
        <div
          style={{
            padding: 10,
            border: "1px solid var(--border-default)",
            borderRadius: 8,
            background: "var(--bg-page)"
          }}
        >
          <div style={{ fontSize: 13, color: "var(--text-soft)", marginBottom: 8, fontWeight: 600 }}>
            솔더 벌크 미세구조(개념도)
          </div>
          <svg viewBox="0 0 360 180" style={{ width: "100%", border: "1px solid #60a5fa", borderRadius: 6, background: "#dbeafe" }}>
            <polygon points="24,120 48,44 88,88 76,140 48,164" fill="#bfdbfe" stroke="#93c5fd" />
            <polygon points="104,132 126,50 168,90 152,144 126,164" fill="#bfdbfe" stroke="#93c5fd" />
            <polygon points="184,126 210,40 248,84 232,136 206,156" fill="#bfdbfe" stroke="#93c5fd" />
            <polygon points="262,122 286,60 312,98 294,136 270,150" fill="#bfdbfe" stroke="#93c5fd" />
            {visAg > 0 ? (
              <>
                <line x1="30" y1="102" x2="42" y2="98" stroke="#6b7280" strokeWidth="2.6" />
                <line x1="90" y1="112" x2="103" y2="108" stroke="#6b7280" strokeWidth="2.6" />
                <line x1="157" y1="72" x2="170" y2="68" stroke="#6b7280" strokeWidth="2.6" />
                <line x1="230" y1="108" x2="243" y2="104" stroke="#6b7280" strokeWidth="2.6" />
                <line x1="292" y1="86" x2="304" y2="82" stroke="#6b7280" strokeWidth="2.6" />
              </>
            ) : null}
            {visCu > 0 ? (
              <>
                <polygon points="68,52 73,48 78,52 78,58 73,62 68,58" fill="#b45309" />
                <polygon points="144,42 150,38 156,42 156,48 150,52 144,48" fill="#b45309" />
                <polygon points="332,122 338,118 344,122 344,128 338,132 332,128" fill="#b45309" />
                <polygon points="212,146 218,142 224,146 224,152 218,156 212,152" fill="#b45309" />
              </>
            ) : null}
            {visBi > 0 ? (
              <>
                <circle cx="114" cy="150" r="4.2" fill="#d97706" />
                <circle cx="188" cy="156" r="3.8" fill="#d97706" />
                <circle cx="276" cy="144" r="4.2" fill="#d97706" />
              </>
            ) : null}
            {visIn > 0 ? <circle cx="248" cy="60" r="3.4" fill="#7dd3fc" /> : null}
            {visSb > 0 ? <circle cx="220" cy="74" r="3.4" fill="#f97316" /> : null}
            {visNi > 0 ? <circle cx="315" cy="63" r="3.4" fill="#a78bfa" /> : null}
            {visZn > 0 ? <circle cx="40" cy="150" r="3.4" fill="#22c55e" /> : null}
            {visPb > 0 ? <circle cx="330" cy="50" r="3.4" fill="#f59e0b" /> : null}
          </svg>
        </div>
        <div
          style={{
            padding: 10,
            border: "1px solid var(--border-default)",
            borderRadius: 8,
            background: "var(--bg-page)",
            fontSize: 13
          }}
        >
          <div style={{ color: "var(--text-soft)", marginBottom: 8, fontWeight: 600 }}>범례 / 조성</div>
          {bulkLegend.map((x, i) => (
            <div key={`${x.name}-${i}`} style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 5 }}>
              <span style={{ width: 10, height: 10, borderRadius: x.type === "grain" ? 2 : 999, background: x.color, flexShrink: 0 }} />
              <span style={{ color: "#e2e8f0", flex: 1 }}>{x.name}</span>
            </div>
          ))}
          <div style={{ marginTop: 8, borderTop: "1px solid var(--border-muted)", paddingTop: 8, color: "var(--text-soft)" }}>
            <div style={{ marginBottom: 4, fontWeight: 600 }}>입력 조성 (wt%)</div>
            <div>Sn {Number(norm.Sn || 0).toFixed(1)} / Ag {visAg.toFixed(1)} / Cu {visCu.toFixed(1)}</div>
            {visBi > 0 ? <div>Bi {visBi.toFixed(1)}</div> : null}
            {visIn > 0 ? <div>In {visIn.toFixed(1)}</div> : null}
            {visSb > 0 ? <div>Sb {visSb.toFixed(1)}</div> : null}
            {visNi > 0 ? <div>Ni {visNi.toFixed(2)}</div> : null}
          </div>
        </div>
      </div>

      <div style={{ marginTop: 10, padding: 10, border: "1px solid var(--border-default)", borderRadius: 8, background: "#f8fafc" }}>
        <div style={{ fontSize: 13, color: "var(--text-soft)", marginBottom: 8, fontWeight: 600 }}>
          <span style={{ color: "#334155" }}>계면 IMC (Interfacial Intermetallic Compound) 구조</span>
        </div>
        <div style={{ border: "1px solid var(--text-soft)", borderRadius: 6, overflow: "hidden", background: "#ffffff" }}>
          <svg viewBox="0 0 740 320" style={{ width: "100%", display: "block" }}>
            <rect x="0" y="0" width="740" height="160" fill="#dbeafe" />
            <polygon points="18,145 40,68 80,102 66,148 40,156" fill="#bfdbfe" stroke="#93c5fd" />
            <polygon points="170,145 192,64 232,100 216,148 190,156" fill="#bfdbfe" stroke="#93c5fd" />
            <polygon points="320,145 344,66 382,102 368,148 344,156" fill="#bfdbfe" stroke="#93c5fd" />
            <polygon points="470,145 492,64 532,102 516,148 492,156" fill="#bfdbfe" stroke="#93c5fd" />
            <polygon points="620,145 642,66 682,102 666,148 642,156" fill="#bfdbfe" stroke="#93c5fd" />
            {visAg > 0 ? (
              <>
                <line x1="95" y1="112" x2="118" y2="104" stroke="#6b7280" strokeWidth="3.2" />
                <line x1="255" y1="104" x2="278" y2="96" stroke="#6b7280" strokeWidth="3.2" />
                <line x1="410" y1="110" x2="433" y2="102" stroke="#6b7280" strokeWidth="3.2" />
                <line x1="570" y1="112" x2="593" y2="104" stroke="#6b7280" strokeWidth="3.2" />
              </>
            ) : null}
            <text x="370" y="24" textAnchor="middle" fontSize="14" fill="#334155" fontWeight="700">
              솔더 벌크 (β-Sn + 조성 기반 분산상)
            </text>

            {/* Cu6Sn5 scallop layer — cu6Um 클수록 파고드는 깊이(scallopDipY) 변화 */}
            <g>
              {Array.from({ length: 14 }).map((_, i) => (
                <path
                  key={`scallop-${substrate}-${i}-${scallopDipY.toFixed(0)}`}
                  d={`M ${i * 56} ${yCu3Top} Q ${i * 56 + 28} ${scallopDipY} ${i * 56 + 56} ${yCu3Top} Z`}
                  fill="#f59e0b"
                  stroke="#d97706"
                  strokeWidth="1"
                />
              ))}
            </g>
            <text x="370" y={yCu3Top - 12} textAnchor="middle" fontSize="13" fill="#334155" fontWeight="700">
              Cu₆Sn₅(η) 스캘럽형태 ≈ {Math.max(0.1, cu6Um).toFixed(2)} um
            </text>

            {/* Cu3Sn layer — 두께는 계산값에 비례 */}
            <rect x="0" y={yCu3Top} width="740" height={hCu3Px} fill="#ca8a04" />
            <text
              x="370"
              y={yCu3Top + hCu3Px / 2 + 5}
              textAnchor="middle"
              fontSize="13"
              fill="var(--border-muted)"
              fontWeight="700"
            >
              Cu₃Sn(ε) ≈ {Math.max(0.08, cu3Um).toFixed(2)} um
            </text>

            {showNiLayer ? (
              <>
                <rect x="0" y={yNiTop} width="740" height={hNiPx} fill="#a78bfa" opacity={0.92} />
                <text
                  x="370"
                  y={yNiTop + hNiPx / 2 + 4}
                  textAnchor="middle"
                  fontSize="12"
                  fill="#1e1b4b"
                  fontWeight="700"
                >
                  Ni₃Sn₄ (ENIG 계면) ≈ {ni3Um.toFixed(2)} um
                </text>
              </>
            ) : null}

            {showFinishStrip ? (
              <rect x="0" y={yFinTop} width="740" height={hFinPx} fill={subVis.finishFill} opacity={0.95} />
            ) : null}

            {/* Cu 패드 + PCB (기판 종류에 따라 색·라벨 변경) */}
            <rect x="0" y={yPadTop} width="740" height={yPadBot - yPadTop} fill={subVis.padFill} />
            <g stroke={subVis.padStroke} strokeWidth="1.2" opacity={0.85}>
              <line x1="40" y1={yPadTop} x2="90" y2={yPadTop + (yPadBot - yPadTop) * 0.55} />
              <line x1="120" y1={yPadTop} x2="170" y2={yPadTop + (yPadBot - yPadTop) * 0.55} />
              <line x1="200" y1={yPadTop} x2="250" y2={yPadTop + (yPadBot - yPadTop) * 0.55} />
              <line x1="280" y1={yPadTop} x2="330" y2={yPadTop + (yPadBot - yPadTop) * 0.55} />
              <line x1="360" y1={yPadTop} x2="410" y2={yPadTop + (yPadBot - yPadTop) * 0.55} />
              <line x1="440" y1={yPadTop} x2="490" y2={yPadTop + (yPadBot - yPadTop) * 0.55} />
              <line x1="520" y1={yPadTop} x2="570" y2={yPadTop + (yPadBot - yPadTop) * 0.55} />
              <line x1="600" y1={yPadTop} x2="650" y2={yPadTop + (yPadBot - yPadTop) * 0.55} />
            </g>
            <text
              x="370"
              y={yPadTop + (yPadBot - yPadTop) / 2 + 5}
              textAnchor="middle"
              fontSize="13"
              fill="#334155"
              fontWeight="700"
            >
              {subVis.padLabel}
            </text>
          </svg>
          <div style={{ padding: "8px 10px", borderTop: "1px solid #e2e8f0", background: "#f8fafc" }}>
            <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 13, color: "#334155" }}>
              {visCu > 0 ? (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <span style={{ width: 11, height: 11, borderRadius: 2, background: "#f59e0b" }} /> Cu₆Sn₅(η)
                </span>
              ) : null}
              {visCu > 0 ? (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <span style={{ width: 11, height: 11, borderRadius: 2, background: "#ca8a04" }} /> Cu₃Sn(ε)
                </span>
              ) : null}
              {visAg > 0 ? (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <span style={{ width: 11, height: 3, borderRadius: 2, background: "#6b7280" }} /> Ag₃Sn 분산상
                </span>
              ) : null}
              {visBi > 0 ? (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <span style={{ width: 11, height: 11, borderRadius: 999, background: "#d97706" }} /> Bi 농화 분산상
                </span>
              ) : null}
              {ni3Um > 0.02 ? (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <span style={{ width: 11, height: 11, borderRadius: 2, background: "#a78bfa" }} /> Ni₃Sn₄
                </span>
              ) : null}
              {topUm > 0 ? (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <span style={{ width: 11, height: 11, borderRadius: 2, background: "#fbbf24" }} /> {substrate} 표면층
                </span>
              ) : null}
              {ag3Um > 0 ? (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <span style={{ width: 11, height: 11, borderRadius: 999, background: "#d1d5db" }} /> Ag₃Sn 분산상(벌크)
                </span>
              ) : null}
            </div>
          </div>
        </div>
        <div style={{ marginTop: 8, color: "#334155", fontSize: 13 }}>
          층별 총합(상대): {sumUm.toFixed(2)} um
        </div>
      </div>
    </div>
  );
}

const ctlStyle = {
  marginTop: 4,
  width: "100%",
  background: "var(--bg-page)",
  border: "1px solid #334155",
  borderRadius: 6,
  color: "#e2e8f0",
  padding: "6px 8px",
  fontSize: 13
};

/** 데스크톱 GUI peak-based 템플릿: 구간별 ramp / preheat / over-liquidus / cool / peak margin */
function ReflowTuneBar({
  liquidus,
  modelPeak,
  reflowPeakUser,
  reflowPeakEffective,
  presetName,
  reflowTune,
  onReflowTuneChange,
  onPeakChange,
  onResetPeak,
  onResetTune,
  storageWindow
}) {
  const sw = storageWindow || (typeof window !== "undefined" ? window : null);
  const liq = Number(liquidus);
  const mp = Number(modelPeak);
  const peakMin = Number.isFinite(liq) ? liq + 10 : 200;
  const peakMax = Number.isFinite(liq) ? liq + 65 : 320;
  const peakInput = Number.isFinite(reflowPeakUser) ? reflowPeakUser : mp;
  const rt = reflowTune || DEFAULT_REFLOW_TUNE;
  const patch = (key, v) => onReflowTuneChange({ ...rt, [key]: v });

  /** 튜닝 목표 — localStorage에 유지(새로고침·탭 이동 후에도 동일) */
  const [tuningGoal, setTuningGoal] = useState(() => {
    try {
      const v = sw?.localStorage?.getItem?.(REFLOW_TUNING_GOAL_STORAGE_KEY);
      if (v && TUNING_GOAL_OPTIONS.includes(v)) return v;
    } catch {
      /* noop */
    }
    return "없음";
  });
  useEffect(() => {
    try {
      sw?.localStorage?.setItem?.(REFLOW_TUNING_GOAL_STORAGE_KEY, tuningGoal);
    } catch {
      /* noop */
    }
  }, [tuningGoal, sw]);

  const validation = useMemo(() => validateProfileTune(rt, presetName || "AUTO"), [rt, presetName]);

  /** 목표를 고른 경우에만: 슬라이더 현재값이 권장 대비 얼마나 벗어났는지 한 줄 표시 */
  const vsRecommendedLine = useMemo(
    () => deviationHintAgainstRecommended(tuningGoal, rt, presetName),
    [tuningGoal, rt, presetName]
  );
  const [applyToast, setApplyToast] = useState(null);
  const applyToastTimerRef = useRef(null);

  /** 권장값 적용 시: 변경 전/후 diff를 만들어 토스트로 노출 */
  const applyRecommended = () => {
    const rec = recommendTuneForGoal(tuningGoal, presetName);
    const labels = {
      rampRate: "1차 램프(℃/s)",
      preheatTime: "프리히트(s)",
      overLiquidusTime: "TAL(s)",
      coolRate: "냉각(℃/s)",
      peakMargin: "피크 여유(℃)"
    };
    const diff = [];
    for (const k of Object.keys(rec)) {
      const before = Number(rt?.[k]);
      const after = Number(rec[k]);
      if (!Number.isFinite(after)) continue;
      const delta = Number.isFinite(before) ? after - before : 0;
      if (!Number.isFinite(before) || Math.abs(delta) > 0.005) {
        diff.push({ key: k, label: labels[k] || k, before, after, delta });
      }
    }
    onReflowTuneChange({ ...rt, ...rec });
    setApplyToast({
      goal: tuningGoal,
      preset: presetName || "—",
      ts: Date.now(),
      diff
    });
    if (applyToastTimerRef.current) clearTimeout(applyToastTimerRef.current);
    applyToastTimerRef.current = setTimeout(() => setApplyToast(null), 6000);
  };

  return (
    <div
      style={{
        marginTop: 14,
        marginBottom: 12,
        padding: 12,
        borderRadius: 10,
        border: "1px solid #334155",
        background: "linear-gradient(180deg, var(--bg-table-head) 0%, var(--bg-page) 100%)"
      }}
    >
      <div style={{ fontSize: 14, color: "#e2e8f0", fontWeight: 600, marginBottom: 6 }}>리플로우 튜닝</div>
      <p style={{ fontSize: 12, color: "#94a3b8", margin: "0 0 10px 0", lineHeight: 1.45 }}>
        <strong style={{ color: "var(--text-soft)" }}>위 그래프 바로 아래</strong>에서 수치를 바꾸면 곡선·구간색·요약 카드가
        즉시 갱신됩니다. 조성에 맞춰 AUTO 프리셋이 선택되며, 1차 램프·프리히트(시간)·액상선 이상 유지·냉각·피크
        마진을 조절할 수 있습니다. TAL·S~L·Peak-5·IMC 블록에도 동일 프로파일이 반영됩니다.
      </p>
      <div style={{ fontSize: 12, color: "#64748b", marginBottom: 10 }}>
        프리셋(AUTO): <strong style={{ color: "var(--text-soft)" }}>{presetName || "—"}</strong>
      </div>

      {/* ─── 튜닝 목표 + 권장값 적용 ─── */}
      <div
        style={{
          display: "flex", flexWrap: "wrap", gap: 8,
          alignItems: "center", marginBottom: 10
        }}
      >
        <span style={{ fontSize: 12, color: "var(--text-soft)", fontWeight: 600 }}>튜닝 목표</span>
        <select
          value={tuningGoal}
          onChange={(e) => setTuningGoal(e.target.value)}
          style={{
            background: "var(--bg-page)", border: "1px solid #334155",
            color: "#e2e8f0", padding: "6px 8px", borderRadius: 6, fontSize: 13
          }}
        >
          {TUNING_GOAL_OPTIONS.map((g) => (
            <option key={g} value={g}>{g}</option>
          ))}
        </select>
        <TactileButton
          onClick={applyRecommended}
          style={{
            padding: "6px 10px", borderRadius: 6,
            border: "1px solid #166534", background: "#16a34a",
            color: "#fff", fontSize: 12, fontWeight: 700, cursor: "pointer"
          }}
        >
          권장값 적용
        </TactileButton>
        <span style={{ fontSize: 11, color: "#64748b" }}>
          (현재 합금 프리셋 + 목표 → 공급사 가이드 기반 권장값으로 한 번에 세팅)
        </span>
      </div>
      {tuningGoal !== "없음" && vsRecommendedLine ? (
        <div
          style={{
            marginBottom: 10,
            fontSize: 11,
            color: "#94a3b8",
            lineHeight: 1.45
          }}
        >
          <span style={{ color: "#64748b", fontWeight: 600 }}>목표 대비 Δ(현재 − 권장)</span>: {vsRecommendedLine}
        </div>
      ) : null}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 160px), 1fr))",
          gap: 10,
          alignItems: "end"
        }}
      >
        <label style={{ fontSize: 12, color: "var(--text-soft)", display: "block" }}>
          피크 목표 (℃)
          <input
            type="number"
            min={peakMin}
            max={peakMax}
            step={0.5}
            value={Number.isFinite(peakInput) ? peakInput : ""}
            onChange={(e) => onPeakChange(Number(e.target.value))}
            style={{ ...ctlStyle, marginTop: 4 }}
          />
        </label>
        <label style={{ fontSize: 12, color: "var(--text-soft)", display: "block" }}>
          1차 램프 (℃/s)
          <input
            type="number"
            min={0.3}
            max={4}
            step={0.1}
            value={rt.rampRate}
            onChange={(e) => patch("rampRate", Number(e.target.value))}
            style={{ ...ctlStyle, marginTop: 4 }}
          />
        </label>
        <label style={{ fontSize: 12, color: "var(--text-soft)", display: "block" }}>
          프리히트 (s)
          <input
            type="number"
            min={30}
            max={180}
            step={1}
            value={rt.preheatTime}
            onChange={(e) => patch("preheatTime", Number(e.target.value))}
            style={{ ...ctlStyle, marginTop: 4 }}
          />
        </label>
        <label style={{ fontSize: 12, color: "var(--text-soft)", display: "block" }}>
          액상선 이상 유지 (s)
          <input
            type="number"
            min={10}
            max={120}
            step={1}
            value={rt.overLiquidusTime}
            onChange={(e) => patch("overLiquidusTime", Number(e.target.value))}
            style={{ ...ctlStyle, marginTop: 4 }}
          />
        </label>
        <label style={{ fontSize: 12, color: "var(--text-soft)", display: "block" }}>
          냉각 (℃/s)
          <input
            type="number"
            min={0.5}
            max={8}
            step={0.1}
            value={rt.coolRate}
            onChange={(e) => patch("coolRate", Number(e.target.value))}
            style={{ ...ctlStyle, marginTop: 4 }}
          />
        </label>
        <label style={{ fontSize: 12, color: "var(--text-soft)", display: "block" }}>
          피크 마진 (℃)
          <input
            type="number"
            min={5}
            max={80}
            step={0.5}
            value={rt.peakMargin}
            onChange={(e) => patch("peakMargin", Number(e.target.value))}
            style={{ ...ctlStyle, marginTop: 4 }}
          />
        </label>
      </div>
      {/* ─── 권장값 적용 결과 토스트 (변경 전/후 diff) ─── */}
      {applyToast ? (
        <div
          style={{
            marginTop: 12,
            padding: "8px 10px",
            borderRadius: 8,
            border: "1px solid #166534",
            background: "rgba(22,163,74,0.10)"
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: 12, color: "#86efac", fontWeight: 700 }}>
              권장값 적용됨 — 목표: {applyToast.goal} · 프리셋: {applyToast.preset}
            </span>
            <button
              type="button"
              onClick={() => setApplyToast(null)}
              style={{
                marginLeft: "auto", background: "transparent",
                border: "1px solid #166534", color: "#86efac",
                padding: "2px 6px", borderRadius: 4, fontSize: 11, cursor: "pointer"
              }}
            >
              닫기
            </button>
          </div>
          {applyToast.diff.length === 0 ? (
            <div style={{ fontSize: 12, color: "#86efac" }}>
              변경된 항목이 없습니다(현재값이 이미 권장값과 같음).
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              {applyToast.diff.map((d) => {
                const sign = d.delta > 0 ? "+" : "";
                const isInt = d.key === "preheatTime" || d.key === "overLiquidusTime" || d.key === "peakMargin";
                const fmt = (v) => (Number.isFinite(v) ? (isInt ? v.toFixed(0) : v.toFixed(2)) : "—");
                return (
                  <div key={d.key} style={{ fontSize: 12, color: "#e2e8f0" }}>
                    <span style={{ color: "#94a3b8" }}>{d.label}: </span>
                    <span>{fmt(d.before)}</span>
                    <span style={{ color: "#64748b", margin: "0 4px" }}>→</span>
                    <span style={{ fontWeight: 700 }}>{fmt(d.after)}</span>
                    {Number.isFinite(d.delta) ? (
                      <span style={{ marginLeft: 6, color: d.delta > 0 ? "#86efac" : "#fbbf24" }}>
                        ({sign}{isInt ? d.delta.toFixed(0) : d.delta.toFixed(2)})
                      </span>
                    ) : null}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ) : null}

      {/* ─── 가드레일 검증 ─── */}
      <div
        style={{
          marginTop: 12,
          padding: "8px 10px",
          borderRadius: 8,
          border: "1px solid #334155",
          background: "var(--bg-page)"
        }}
      >
        <div style={{ fontSize: 12, color: "#93c5fd", fontWeight: 700, marginBottom: 6 }}>
          가드레일 검증
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          {validation.errors.map((m, i) => (
            <div key={`e-${i}`} style={{ fontSize: 12, color: "#f87171" }}>❌ {m}</div>
          ))}
          {validation.warnings.map((m, i) => (
            <div key={`w-${i}`} style={{ fontSize: 12, color: "#fbbf24" }}>⚠ {m}</div>
          ))}
          {validation.errors.length === 0 && validation.warnings.length === 0 && validation.oks.length > 0 ? (
            <div style={{ fontSize: 12, color: "#86efac", fontWeight: 600 }}>
              ✅ 가드레일 통과 — 오류·경고 없음 (아래 ✓ 참고)
            </div>
          ) : null}
          {validation.oks.map((m, i) => (
            <div key={`o-${i}`} style={{ fontSize: 12, color: "#86efac" }}>✓ {m}</div>
          ))}
          {validation.errors.length === 0 &&
          validation.warnings.length === 0 &&
          validation.oks.length === 0 ? (
            <div style={{ fontSize: 12, color: "#64748b" }}>
              검증 결과 없음 — 분석 후 AUTO가 합금에 맞는 프리셋으로 확정되면 카테고리별 밴드가 채워집니다.
            </div>
          ) : null}
        </div>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginTop: 12 }}>
        <TactileButton
          onClick={onResetPeak}
          style={{
            padding: "8px 12px",
            borderRadius: 8,
            border: "1px solid var(--border-muted)",
            background: "var(--bg-elevated)",
            color: "var(--text-secondary)",
            fontSize: 13,
            cursor: "pointer"
          }}
        >
          분석 피크로 되돌리기
        </TactileButton>
        <TactileButton
          onClick={onResetTune}
          style={{
            padding: "8px 12px",
            borderRadius: 8,
            border: "1px solid var(--border-muted)",
            background: "var(--bg-elevated)",
            color: "var(--text-secondary)",
            fontSize: 13,
            cursor: "pointer"
          }}
        >
          프리셋 기본값으로 구간 초기화
        </TactileButton>
        <span style={{ fontSize: 12, color: "#64748b" }}>
          적용 피크: <strong style={{ color: "#e2e8f0" }}>{reflowPeakEffective.toFixed(1)} ℃</strong>
          {Number.isFinite(mp) && Math.abs(reflowPeakEffective - mp) > 0.05 ? (
            <span style={{ marginLeft: 6 }}>(분석 {mp.toFixed(1)} ℃ 대비)</span>
          ) : null}
        </span>
      </div>
    </div>
  );
}

function ReflowCard({ solidus, liquidus, peak, modelPeak, profileMeta }) {
  if (!Number.isFinite(solidus) || !Number.isFinite(liquidus) || !Number.isFinite(peak)) {
    return (
      <div
        style={{
          padding: 10,
          borderRadius: 10,
          border: "1px solid var(--border-muted)",
          background: "var(--bg-page)"
        }}
      >
        <div style={{ fontSize: 13, color: "#9ca3af", marginBottom: 4 }}>리플로우 프로파일</div>
        <div style={{ fontSize: 13, color: "#64748b" }}>온도 정보가 부족합니다.</div>
      </div>
    );
  }

  const deltaT = liquidus - solidus;
  const peakMin = liquidus + 20;
  const peakMax = liquidus + 40;
  const tlTime = Math.max(30, Math.round(20 + deltaT * 2));

  /** Peak-based 곡선과 동일: SAC·Sn-3Ag-0.5Cu 등은 일반적으로 150~190℃ 프리히트 소구간 */
  const usePeakMeta =
    profileMeta &&
    Number.isFinite(profileMeta.t_pre_start) &&
    Number.isFinite(profileMeta.t_pre_end);
  let preheatLo;
  let preheatHi;
  let soakTime;
  if (usePeakMeta) {
    preheatLo = profileMeta.t_pre_start;
    preheatHi = profileMeta.t_pre_end;
    soakTime = Number.isFinite(profileMeta.dt_b) ? Math.round(profileMeta.dt_b) : 90;
  } else {
    const preheatMax = Math.min(solidus - 20, 150);
    preheatLo = preheatMax - 30;
    preheatHi = preheatMax;
    soakTime = deltaT > 5 ? 60 : 40;
  }

  return (
    <div
      style={{
        padding: 10,
        borderRadius: 10,
        border: "1px solid var(--border-muted)",
        background: "var(--bg-page)"
      }}
    >
      <div style={{ fontSize: 13, color: "#9ca3af", marginBottom: 4 }}>리플로우 프로파일</div>
      <div style={{ fontSize: 13, marginBottom: 2 }}>
        프리히트: {preheatLo.toFixed(1)}–{preheatHi.toFixed(1)} ℃ ({soakTime}s)
        {usePeakMeta ? (
          <span style={{ color: "#64748b", fontSize: 12 }}> · 그래프 Peak-based 구간</span>
        ) : null}
      </div>
      <div style={{ fontSize: 13, marginBottom: 2 }}>
        TL 이상 유지 시간: {tlTime} s (ΔT={deltaT.toFixed(1)} ℃)
      </div>
      <div style={{ fontSize: 13, marginBottom: 2 }}>
        피크 권장 범위: {peakMin.toFixed(1)}–{peakMax.toFixed(1)} ℃
      </div>
      <div style={{ fontSize: 13, marginBottom: 2, color: "#7dd3fc" }}>
        적용 중인 피크: {peak.toFixed(1)} ℃
        {Number.isFinite(modelPeak) && Math.abs(peak - modelPeak) > 0.05 ? (
          <span style={{ color: "#94a3b8" }}> (분석 피크 {modelPeak.toFixed(1)} ℃)</span>
        ) : null}
      </div>
      <div style={{ fontSize: 13, marginTop: 4, color: "#64748b" }}>
        실제 프로파일 설계 시 부품/PCB 스펙과 함께 검토해야 합니다.
      </div>
    </div>
  );
}

function RegulationCard({ norm }) {
  const n = norm || {};
  const pb = Number(n.Pb || 0);
  const hg = Number(n.Hg || 0);
  const cd = Number(n.Cd || 0);
  const cr = Number(n.Cr || 0);
  const bi = Number(n.Bi || 0);
  const sb = Number(n.Sb || 0);
  const inn = Number(n.In || 0);
  const tl = Number(n.Tl || 0);
  const se = Number(n.Se || 0);
  const te = Number(n.Te || 0);

  const issues = [];
  if (pb > 0) issues.push("Pb 함유 → RoHS 규제 대상. 용도/예외조항 확인 필요");
  if (hg > 0) issues.push("Hg 함유 → RoHS 엄격 규제. 사용 지양 권장");
  if (cd > 0) issues.push("Cd 함유 → RoHS/REACH 매우 엄격 규제");
  if (cr > 0) issues.push("Cr 포함: 6가 크롬 여부 확인 필수");
  if (bi > 0)
    issues.push("Bi 포함: REACH SVHC 후보(용도별). 함량/용도에 따른 규제 가능성 검토");
  if (sb > 0) issues.push("Sb 포함: REACH SVHC 후보. 환경/독성 평가 필요");
  if (inn > 0) issues.push("In 포함: REACH 희소금속 모니터링. 장기 공급 안정성 고려");
  if (tl > 0) issues.push("Tl 포함: REACH SVHC. 매우 엄격한 관리 필요");
  if (se > 0 || te > 0)
    issues.push("Se/Te 포함: REACH 환경 모니터링 대상. 폐기/환경영향 검토");

  const level =
    pb > 0 || hg > 0 || cd > 0 ? "HIGH" : issues.length > 0 ? "MEDIUM" : "LOW";
  const badgeColor =
    level === "HIGH" ? "#dc2626" : level === "MEDIUM" ? "#ea580c" : "#16a34a";
  const badgeText =
    level === "HIGH" ? "높음" : level === "MEDIUM" ? "주의" : "낮음";

  return (
    <div
      style={{
        padding: 10,
        borderRadius: 10,
        border: "1px solid var(--border-muted)",
        background: "var(--bg-page)"
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <div style={{ fontSize: 13, color: "#9ca3af" }}>RoHS / REACH 규제 요약</div>
        <span
          style={{
            fontSize: 13,
            padding: "2px 6px",
            borderRadius: 999,
            background: badgeColor,
            color: "white"
          }}
        >
          규제 리스크: {badgeText}
        </span>
      </div>
      {issues.length === 0 ? (
        <div style={{ fontSize: 13, color: "#16a34a" }}>
          주요 RoHS/REACH 규제 물질이 조성에 포함되지 않았습니다.
        </div>
      ) : (
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
          {issues.map((x, idx) => (
            <li key={idx}>{x}</li>
          ))}
        </ul>
      )}
      <div style={{ fontSize: 13, color: "#64748b", marginTop: 4 }}>
        실제 인증 여부는 부품/제품 단위 시험·법규 검토가 필요합니다.
      </div>
    </div>
  );
}

function ReflowChart({ profile, solidus, liquidus, layoutScale = 1, expandable = false, expandPayload = null }) {
  if (!profile?.points?.length || !profile.meta) return null;
  const peak = Number(profile.meta.peak);
  if (!Number.isFinite(solidus) || !Number.isFinite(liquidus) || !Number.isFinite(peak)) {
    return null;
  }

  const points = profile.points;
  const m = profile.meta;
  const tEnd = Math.max(1e-6, points[points.length - 1].t);
  const axisTMax = Math.max(tEnd * 1.15, 120);

  const minY = Math.min(...points.map((p) => p.y), 20);
  const maxY = Math.max(...points.map((p) => p.y), peak + 10);

  const sc = Math.max(0.75, Math.min(2.5, Number(layoutScale) || 1));
  const width = Math.round(560 * sc);
  const height = Math.round(200 * sc);
  const padX = Math.round(52 * sc);
  const padY = Math.round(28 * sc);
  const plotW = width - 2 * padX;
  const plotH = height - 2 * padY;
  const fsAxis = Math.round(11 * sc);
  const fsTitle = Math.min(18, Math.round(13 * sc));
  const glowW = 8 + 5 * Math.max(0, sc - 1);
  const lineW = 2.5 + 1.5 * Math.max(0, sc - 1);

  const mapX = (t) => padX + Math.min(1, t / axisTMax) * plotW;
  const mapY = (y) => height - padY - ((y - minY) / (maxY - minY || 1)) * plotH;

  const pathD = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${mapX(p.t).toFixed(1)} ${mapY(p.y).toFixed(1)}`)
    .join(" ");

  const refLines = [
    { val: solidus, stroke: "#22d3ee", sw: 1.5 * sc },
    { val: liquidus, stroke: "#c4b5fd", sw: 1.5 * sc },
    { val: peak, stroke: "#fb923c", sw: 2 * sc }
  ];

  const yMinLbl = Math.round(minY);
  const yMaxLbl = Math.round(maxY);

  const z = (t0, t1, fill) => {
    const x0 = mapX(t0);
    const x1 = mapX(Math.min(t1, axisTMax));
    if (x1 <= x0) return null;
    return (
      <rect
        key={`${t0}-${t1}`}
        x={x0}
        y={padY}
        width={x1 - x0}
        height={plotH}
        fill={fill}
      />
    );
  };

  return (
    <div
      style={{
        marginTop: 8,
        padding: Math.round(12 * Math.min(sc, 1.25)),
        borderRadius: 10,
        border: "1px solid #334155",
        background: "linear-gradient(180deg, var(--bg-table-head) 0%, var(--bg-page) 100%)"
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 10,
          marginBottom: 8
        }}
      >
        <div style={{ fontSize: fsTitle, color: "#e2e8f0", fontWeight: 600 }}>
          리플로우 온도–시간 곡선 (Peak-based, 구간색)
        </div>
        {expandable ? (
          <TactileButton
            onClick={() =>
              openReflowChartInNewWindow(
                expandPayload || { profile, solidus, liquidus }
              )
            }
            style={{
              padding: "8px 14px",
              borderRadius: 8,
              border: "1px solid #475569",
              background: "linear-gradient(180deg, var(--border-default) 0%, var(--bg-table-head) 100%)",
              color: "#e2e8f0",
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
              whiteSpace: "nowrap"
            }}
          >
            새 창으로 확대
          </TactileButton>
        ) : null}
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        style={{ maxWidth: width, display: "block", height: "auto" }}
        role="img"
        aria-label="리플로우 온도 시간 개략 곡선"
      >
        <defs>
          <linearGradient id="reflowCurveGlow" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#38bdf8" stopOpacity="0" />
          </linearGradient>
        </defs>

        <rect
          x={padX}
          y={padY}
          width={plotW}
          height={plotH}
          rx={6}
          fill="var(--bg-page)"
          stroke="#334155"
          strokeWidth={1}
        />

        {/* 구간 배경: 1차 램프 / 프리히트 / 리플로우(2차램프~피크 유지) / 냉각 */}
        {z(m.t0, m.tA, "rgba(59, 130, 246, 0.22)")}
        {z(m.tA, m.tB, "rgba(234, 179, 8, 0.2)")}
        {z(m.tB, m.tE, "rgba(185, 28, 28, 0.18)")}
        {z(m.tE, m.tF, "rgba(22, 163, 74, 0.2)")}

        {[0.25, 0.5, 0.75].map((r) => {
          const yy = padY + plotH * r;
          return (
            <line
              key={r}
              x1={padX}
              y1={yy}
              x2={padX + plotW}
              y2={yy}
              stroke="var(--border-default)"
              strokeWidth={1}
            />
          );
        })}

        {refLines.map((r, idx) => (
          <line
            key={idx}
            x1={padX}
            y1={mapY(r.val)}
            x2={padX + plotW}
            y2={mapY(r.val)}
            stroke={r.stroke}
            strokeDasharray="6 5"
            strokeWidth={r.sw}
            opacity={0.95}
          />
        ))}

        <line
          x1={mapX(tEnd)}
          y1={padY}
          x2={mapX(tEnd)}
          y2={height - padY}
          stroke="#94a3b8"
          strokeDasharray="5 4"
          strokeWidth={1.2}
          opacity={0.75}
        />

        <text
          x={padX - 8}
          y={height - padY + 4}
          textAnchor="end"
          fill="#94a3b8"
          fontSize={fsAxis}
          fontFamily="inherit"
        >
          {yMinLbl}℃
        </text>
        <text
          x={padX - 8}
          y={padY + 4}
          textAnchor="end"
          fill="#94a3b8"
          fontSize={fsAxis}
          fontFamily="inherit"
        >
          {yMaxLbl}℃
        </text>

        <line
          x1={padX}
          y1={height - padY}
          x2={padX + plotW}
          y2={height - padY}
          stroke="#64748b"
          strokeWidth={1.5}
        />
        <line x1={padX} y1={padY} x2={padX} y2={height - padY} stroke="#64748b" strokeWidth={1.5} />

        <text
          x={padX + plotW / 2}
          y={height - Math.round(6 * sc)}
          textAnchor="middle"
          fill="#94a3b8"
          fontSize={fsAxis}
          fontFamily="inherit"
        >
          시간 (s) · 축 0–{Math.round(axisTMax)}s · 프로파일 끝 {Math.round(tEnd)}s
        </text>
        <text
          x={14 * sc}
          y={padY + plotH / 2}
          textAnchor="middle"
          fill="#94a3b8"
          fontSize={fsAxis}
          fontFamily="inherit"
          transform={`rotate(-90 ${14 * sc} ${padY + plotH / 2})`}
        >
          온도 (℃)
        </text>

        <path
          d={pathD}
          fill="none"
          stroke="url(#reflowCurveGlow)"
          strokeWidth={glowW}
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity={0.9}
        />
        <path
          d={pathD}
          fill="none"
          stroke="#38bdf8"
          strokeWidth={lineW}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 10,
          marginTop: 10,
          alignItems: "center"
        }}
      >
        {[
          { name: "Solidus", v: solidus, color: "#22d3ee" },
          { name: "Liquidus", v: liquidus, color: "#c4b5fd" },
          { name: "Peak", v: peak, color: "#fb923c" }
        ].map((item) => (
          <div
            key={item.name}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "6px 10px",
              borderRadius: 8,
              border: "1px solid #334155",
              background: "var(--bg-table-head)",
              fontSize: Math.round(13 * Math.min(sc, 1.2)),
              color: "#e2e8f0"
            }}
          >
            <span
              style={{
                width: 10,
                height: 10,
                borderRadius: 2,
                background: item.color,
                flexShrink: 0
              }}
            />
            <span style={{ fontWeight: 600 }}>{item.name}</span>
            <span style={{ color: "#94a3b8" }}>{item.v.toFixed(1)}℃</span>
          </div>
        ))}
      </div>

      <div
        style={{
          fontSize: Math.round(12 * Math.min(sc, 1.2)),
          color: "#94a3b8",
          marginTop: 8,
          lineHeight: 1.5,
          fontFamily: "ui-monospace, monospace"
        }}
      >
        Preset: {m.presetName || "—"} | ramp={m.ramp_rate.toFixed(2)}℃/s | preheat={m.dt_b.toFixed(0)}s | over(liq)≈
        {m.dt_e.toFixed(0)}s | TAL(calc)는 위 IMC 블록 | cool={m.cool_rate.toFixed(2)}℃/s | peak_margin={m.peak_margin.toFixed(0)}℃
        | 끝 {m.tF.toFixed(0)}s
      </div>

      <div
        style={{
          fontSize: Math.round(13 * Math.min(sc, 1.15)),
          color: "#64748b",
          marginTop: 6,
          lineHeight: 1.45
        }}
      >
        색 구간: 파랑 1차 램프 → 황색 프리히트 → 적색 리플로우(2차 램프~액상 유지) → 녹색 냉각. 장비 실측과는 다를 수 있습니다.
      </div>
    </div>
  );
}

function PopupReflowTuner({ result, initialTune, initialPeakUser, hostWindow, meltBasis = "hybrid" }) {
  const [peakUser, setPeakUser] = useState(
    Number.isFinite(initialPeakUser) ? Number(initialPeakUser) : Number(result?.peak || 0)
  );
  const [tune, setTune] = useState(initialTune || DEFAULT_REFLOW_TUNE);

  const profile = useMemo(() => {
    try {
      return buildPeakProfilePoints(result, tune, peakUser, meltBasis);
    } catch {
      return null;
    }
  }, [result, tune, peakUser, meltBasis]);

  const md = getReflowMeltDisplay(result, meltBasis);
  const solidus = Number(md.solidus || 0);
  const liquidus = Number(md.liquidus || 0);
  const modelPeak = Number(md.modelPeak || 0);
  const reflowPeakEffective = Number(profile?.meta?.peak ?? modelPeak ?? 0);

  return (
    <div style={{ padding: 16, maxWidth: 1160, margin: "0 auto" }}>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 10,
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 10
        }}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "baseline" }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: "#e2e8f0" }}>리플로우 프로파일 (확대)</div>
          <div style={{ fontSize: 12, color: "#64748b" }}>
            새 창에서도 피크·튜닝을 바꾸면 곡선이 즉시 갱신됩니다.
          </div>
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          <TactileButton
            onClick={() => {
              const payload = {
                type: "apply_reflow_tune",
                ts: Date.now(),
                tune,
                peakUser
              };
              try {
                const BC = hostWindow?.BroadcastChannel || BroadcastChannel;
                if (typeof BC !== "undefined") {
                  const bc = new BC("reflowTuneSync");
                  bc.postMessage(payload);
                  bc.close?.();
                } else {
                  (hostWindow?.localStorage || window.localStorage).setItem("reflowTuneSync", JSON.stringify(payload));
                }
              } catch {
                try {
                  (hostWindow?.localStorage || window.localStorage).setItem("reflowTuneSync", JSON.stringify(payload));
                } catch {
                  /* noop */
                }
              }
            }}
            style={{
              padding: "8px 12px",
              borderRadius: 8,
              border: "1px solid #166534",
              background: "#16a34a",
              color: "#fff",
              fontSize: 13,
              fontWeight: 800,
              cursor: "pointer",
              whiteSpace: "nowrap"
            }}
          >
            메인에 적용
          </TactileButton>
          <TactileButton
            onClick={() => hostWindow?.close?.()}
            style={{
              padding: "8px 12px",
              borderRadius: 8,
              border: "1px solid #475569",
              background: "linear-gradient(180deg, var(--border-default) 0%, var(--bg-table-head) 100%)",
              color: "#e2e8f0",
              fontSize: 13,
              fontWeight: 700,
              cursor: "pointer",
              whiteSpace: "nowrap"
            }}
          >
            닫기
          </TactileButton>
        </div>
      </div>

      <ReflowChart profile={profile} solidus={solidus} liquidus={liquidus} layoutScale={2} expandable={false} />
      <ReflowTuneBar
        liquidus={liquidus}
        modelPeak={modelPeak}
        reflowPeakUser={peakUser}
        reflowPeakEffective={reflowPeakEffective}
        presetName={profile?.meta?.presetName}
        reflowTune={tune}
        onReflowTuneChange={setTune}
        onPeakChange={setPeakUser}
        onResetPeak={() => {
          const m = getReflowMeltDisplay(result, meltBasis);
          if (Number.isFinite(m.modelPeak)) setPeakUser(Number(m.modelPeak));
        }}
        onResetTune={() => {
          const name = pickPresetName(result);
          const pset = { ...REFLOW_PRESETS.범용, ...(REFLOW_PRESETS[name] || {}) };
          setTune({
            rampRate: pset.ramp_rate,
            preheatTime: pset.preheat_time,
            overLiquidusTime: pset.over_liquidus_time,
            coolRate: pset.cool_rate,
            peakMargin: pset.peak_margin
          });
        }}
        storageWindow={hostWindow}
      />
    </div>
  );
}

/** 메인 페이지의 「새 창으로 확대」에서 사용 — 팝업에 차트 + 튜닝 UI 렌더 */
function openReflowChartInNewWindow(payload) {
  const p = payload || {};
  const result = p.result;
  const profile = p.profile;
  const solidus = p.solidus;
  const liquidus = p.liquidus;
  const initialTune = p.initialTune;
  const initialPeakUser = p.initialPeakUser;
  const meltBasis = p.meltBasis === "inference" ? "inference" : "hybrid";

  if (result) {
    // ok
  } else if (!profile?.points?.length) {
    return;
  }
  const w = window.open("", "reflowProfileExpand", "width=1080,height=840,scrollbars=yes,resizable=yes");
  if (!w) {
    window.alert("팝업이 차단되었습니다. 브라우저에서 이 사이트의 팝업을 허용해 주세요.");
    return;
  }
  try {
    // best-effort: noopener
    w.opener = null;
  } catch {
    /* noop */
  }

  try {
    // Reuse the same popup tab/window if already opened.
    if (w.closed) return;
    if (!w.__reflowRoot) {
      w.document.open();
      w.document.write(
        "<!DOCTYPE html><html lang=\"ko\"><head><meta charset=\"utf-8\"/><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/><title>리플로우 프로파일 (확대)</title></head><body style=\"margin:0;background:#020617;\"></body></html>"
      );
      w.document.close();

      // 메인과 동일한 CSS/스타일을 팝업에도 주입(동일 origin 가정)
      try {
        const srcNodes = document.querySelectorAll("link[rel=\"stylesheet\"], style");
        srcNodes.forEach((n) => {
          const clone = n.cloneNode(true);
          w.document.head.appendChild(clone);
        });
      } catch {
        /* noop */
      }

      w.__reflowRoot = createRoot(w.document.body);
    }
    w.__reflowRoot.render(
      result ? (
        <PopupReflowTuner
          result={result}
          initialTune={initialTune}
          initialPeakUser={initialPeakUser}
          hostWindow={w}
          meltBasis={meltBasis}
        />
      ) : (
        <ReflowChart profile={profile} solidus={solidus} liquidus={liquidus} layoutScale={2} expandable={false} />
      )
    );
    w.focus?.();
  } catch (e) {
    const msg = e && typeof e === "object" && "message" in e ? String(e.message) : String(e);
    window.alert(`새 창 렌더링 실패: ${msg}`);
  }
}
