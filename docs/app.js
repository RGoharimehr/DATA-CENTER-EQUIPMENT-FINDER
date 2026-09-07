let CATALOG = [];

const KV_PER_CV = 0.865;
const MM_PER_INCH = 25.4;
const toNum = (v) => (v === "" || v == null ? null : Number(v));
const normalizeTerm = (v) => String(v || "").toLowerCase().replace(/[_-]/g, " ");

function coeffForTarget(item, cv, kv) {
  if (item.flow_coefficient_value == null || !item.flow_coefficient_type) return null;
  const t = String(item.flow_coefficient_type).toLowerCase();
  const x = Number(item.flow_coefficient_value);
  if (cv != null) return t === "cv" ? x : x / KV_PER_CV;
  if (kv != null) return t === "kv" ? x : x * KV_PER_CV;
  return null;
}

function ndelta(a, b, fallback = 1) {
  if (a == null || b == null || Number.isNaN(a) || Number.isNaN(b)) return fallback;
  const scale = Math.max(Math.abs(b), 1e-9);
  return Math.abs(a - b) / scale;
}

function findMatches(params) {
  const filtered = CATALOG.filter((c) => {
    if (params.category && String(c.category).toLowerCase() !== params.category.toLowerCase()) return false;
    if (params.component_subtype && String(c.component_subtype || "").toLowerCase() !== params.component_subtype.toLowerCase()) return false;
    if (params.brand && String(c.brand).toLowerCase() !== params.brand.toLowerCase()) return false;
    return true;
  });

  const scored = filtered.map((c) => {
    let score = 0;
    score += ndelta(toNum(c.nominal_size_mm), params.size_mm, 0.2);
    if (params.connection_size_mm != null) {
      const connMm = toNum(c.nominal_size_mm) ?? (toNum(c.nominal_size_inch) != null ? toNum(c.nominal_size_inch) * MM_PER_INCH : null);
      score += 1.2 * ndelta(connMm, params.connection_size_mm, 0.35);
    }
    const allowsFlow = ["valve", "strainer"].includes(String(c.category || "").toLowerCase());
    if (allowsFlow && (params.cv != null || params.kv != null)) {
      score += ndelta(coeffForTarget(c, params.cv, params.kv), params.cv ?? params.kv, 0.6);
    }
    score += ndelta(toNum(c.capacity_kw), params.capacity_kw, 0.3);
    if (c.estimated_price_usd == null || c.estimated_price_usd === "") score += 0.05;
    return { score, component: c };
  });

  return scored.sort((a, b) => a.score - b.score).slice(0, Math.max(1, params.top_n));
}

function checkCompatibility(partNumbers, requiredMaterial, maxTime, requiredConnectionStandard, requiredCoolant) {
  const picked = CATALOG.filter((x) => partNumbers.some((p) => String(x.part_number).toLowerCase() === p.toLowerCase()));
  const reasons = [];
  const hyd = new Set(["valve", "strainer", "filter_dryer"]);
  const thermal = new Set(["cdu", "chiller"]);

  const eq = {
    NPT: new Set(["NPT", "FPT"]), FPT: new Set(["NPT", "FPT"]),
    ODF: new Set(["ODF", "ODS"]), ODS: new Set(["ODF", "ODS"])
  };
  for (let i = 0; i < picked.length; i++) {
    for (let j = i + 1; j < picked.length; j++) {
      const a = (picked[i].connection_type || "").toUpperCase();
      const b = (picked[j].connection_type || "").toUpperCase();
      const ca = String(picked[i].category || "").toLowerCase();
      const cb = String(picked[j].category || "").toLowerCase();
      if (hyd.has(ca) && hyd.has(cb) && a && b && a !== b && !(eq[a] && eq[a].has(b))) {
        reasons.push(`Connection mismatch: ${picked[i].part_number}(${a}) vs ${picked[j].part_number}(${b})`);
      }
      const sa = String(picked[i].connection_standard || "");
      const sb = String(picked[j].connection_standard || "");
      if (thermal.has(ca) && thermal.has(cb) && sa && sb && sa.toLowerCase() !== sb.toLowerCase()) {
        reasons.push(`Connection standard mismatch: ${picked[i].part_number}(${sa}) vs ${picked[j].part_number}(${sb})`);
      }
    }
  }

  if (requiredMaterial) {
    for (const p of picked) {
      if (p.material && String(p.material).toLowerCase() !== requiredMaterial.toLowerCase()) {
        reasons.push(`Material mismatch: ${p.part_number} material=${p.material}, required=${requiredMaterial}`);
      }
    }
  }

  if (maxTime != null) {
    for (const p of picked) {
      const t = toNum(p.install_connection_time_min);
      const c = String(p.category || "").toLowerCase();
      if (hyd.has(c) && t != null && t > maxTime) reasons.push(`Connection time too high: ${p.part_number} requires ${t} min`);
    }
  }

  if (requiredConnectionStandard) {
    for (const p of picked) {
      if (p.connection_standard && String(p.connection_standard).toLowerCase() !== requiredConnectionStandard.toLowerCase()) {
        reasons.push(`Connection standard mismatch: ${p.part_number} standard=${p.connection_standard}, required=${requiredConnectionStandard}`);
      }
    }
  }

  if (requiredCoolant) {
    for (const p of picked) {
      if (p.coolant_compatibility && !String(p.coolant_compatibility).toLowerCase().includes(requiredCoolant.toLowerCase())) {
        reasons.push(`Coolant mismatch: ${p.part_number} coolant=${p.coolant_compatibility}, required contains=${requiredCoolant}`);
      }
    }
  }

  return { is_compatible: reasons.length === 0, reasons, selected_count: picked.length, requested_count: partNumbers.length };
}

function bindUi() {
  const categoryEl = document.getElementById("category");
  const cvEl = document.getElementById("cv");
  const kvEl = document.getElementById("kv");
  function syncInputHints() {
    const c = categoryEl.value;
    const flowEnabled = !c || c === "valve" || c === "strainer";
    cvEl.disabled = !flowEnabled;
    kvEl.disabled = !flowEnabled;
    if (!flowEnabled) {
      cvEl.value = "";
      kvEl.value = "";
    }
  }
  categoryEl.addEventListener("change", syncInputHints);
  syncInputHints();

  document.getElementById("find").addEventListener("click", () => {
    const params = {
      category: categoryEl.value.trim() || null,
      component_subtype: document.getElementById("subtype").value.trim() || null,
      brand: document.getElementById("brand").value.trim() || null,
      size_mm: toNum(document.getElementById("size").value),
      connection_size_mm: toNum(document.getElementById("connSizeMm").value),
      connection_size_inch: toNum(document.getElementById("connSizeInch").value),
      cv: toNum(document.getElementById("cv").value),
      kv: toNum(document.getElementById("kv").value),
      capacity_kw: toNum(document.getElementById("cap").value),
      top_n: Number(document.getElementById("topn").value || 5)
    };
    if (params.connection_size_mm == null && params.connection_size_inch != null) {
      params.connection_size_mm = params.connection_size_inch * MM_PER_INCH;
    }
    if (params.size_mm == null && params.connection_size_mm != null) {
      params.size_mm = params.connection_size_mm;
    }
    const out = findMatches(params);
    document.getElementById("findOut").textContent = JSON.stringify(out, null, 2);
  });

  document.getElementById("compat").addEventListener("click", () => {
    const partNumbers = document.getElementById("parts").value.split(",").map((x) => x.trim()).filter(Boolean);
    const requiredMaterial = document.getElementById("material").value.trim() || null;
    const requiredConnectionStandard = document.getElementById("connStd").value.trim() || null;
    const requiredCoolant = document.getElementById("coolant").value.trim() || null;
    const maxTime = toNum(document.getElementById("maxTime").value);
    const out = checkCompatibility(partNumbers, requiredMaterial, maxTime, requiredConnectionStandard, requiredCoolant);
    document.getElementById("compatOut").textContent = JSON.stringify(out, null, 2);
  });

  document.getElementById("assist").addEventListener("click", async () => {
    const query = document.getElementById("aiQuery").value.trim();
    const mode = document.getElementById("aiMode").value;
    const apiBase = document.getElementById("apiBase").value.trim();
    if (!query) {
      document.getElementById("aiOut").textContent = "Please enter a query.";
      return;
    }

    if (apiBase) {
      try {
        const res = await fetch(apiBase.replace(/\\/$/, "") + "/api/v1/assistant", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query, mode })
        });
        const data = await res.json();
        document.getElementById("aiOut").textContent = JSON.stringify(data, null, 2);
        return;
      } catch (err) {
        document.getElementById("aiOut").textContent = "API assistant request failed: " + err;
        return;
      }
    }

    const q = query.toLowerCase();
    const normalizedQuery = normalizeTerm(q);
    const pick = (arr) => arr.find((x) => normalizedQuery.includes(normalizeTerm(x))) || null;
    const categories = [...new Set(CATALOG.map((x) => x.category))];
    const brands = [...new Set(CATALOG.map((x) => x.brand))];
    const subtypes = [...new Set(CATALOG.map((x) => x.component_subtype).filter(Boolean))];
    const mm = (q.match(/(\\d+(?:\\.\\d+)?)\\s*mm/) || [])[1];
    const connLeading = q.match(/(?:pipe|piping|connection|port|line|diameter)\\s*(?:size)?\\s*(?:of|=|:)?\\s*(\\d+(?:\\.\\d+)?)\\s*(mm|in|inch|inches|")/);
    const connTrailing = q.match(/(\\d+(?:\\.\\d+)?)\\s*(mm|in|inch|inches|")\\s*(?:pipe|piping|connection|port|line|diameter)/);
    const conn = connLeading || connTrailing;
    const cv = (q.match(/(?:^|\\s)cv\\s*[:=]?\\s*(\\d+(?:\\.\\d+)?)/) || [])[1];
    const kv = (q.match(/(?:^|\\s)kv\\s*[:=]?\\s*(\\d+(?:\\.\\d+)?)/) || [])[1];
    const kw = (q.match(/(\\d+(?:\\.\\d+)?)\\s*k\\s*w/) || [])[1];
    const tons = (q.match(/(\\d+(?:\\.\\d+)?)\\s*(?:tr|ton|tons)/) || [])[1];
    const top = Number((q.match(/top\\s*(\\d+)/) || [])[1] || 5);

    const filters = {
      category: pick(categories),
      component_subtype: pick(subtypes),
      brand: pick(brands),
      size_mm: mm ? Number(mm) : null,
      connection_size_mm: conn ? Number(conn[1]) * (conn[2] === "mm" ? 1 : MM_PER_INCH) : null,
      connection_size_inch: conn && conn[2] !== "mm" ? Number(conn[1]) : null,
      cv: cv ? Number(cv) : null,
      kv: kv ? Number(kv) : null,
      capacity_kw: kw ? Number(kw) : null,
      capacity_tons: tons ? Number(tons) : null,
      top_n: Math.max(1, Math.min(top, 20))
    };
    if (filters.size_mm == null && filters.connection_size_mm != null) {
      filters.size_mm = filters.connection_size_mm;
    }
    if (["cdu", "chiller", "filter_dryer"].includes(String(filters.category || "").toLowerCase())) {
      filters.cv = null;
      filters.kv = null;
    }
    const matches = findMatches(filters);
    document.getElementById("aiOut").textContent = JSON.stringify({
      ok: true,
      data: {
        mode_requested: mode,
        mode_used: "local_static",
        filters,
        matches
      }
    }, null, 2);
  });
}

fetch("./equipment_catalog.json")
  .then((r) => r.json())
  .then((data) => {
    CATALOG = data;
    bindUi();
    document.getElementById("findOut").textContent = `Loaded ${CATALOG.length} components.`;
  })
  .catch((err) => {
    document.getElementById("findOut").textContent = "Failed to load data: " + err;
  });
