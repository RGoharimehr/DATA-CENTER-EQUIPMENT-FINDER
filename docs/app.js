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

  // Mirrors matching.py. These two implementations rank the same catalog, so they
  // have to agree: the site previously kept the old scoring and quietly gave
  // different answers from the CLI for the same query.
  const UNKNOWN_PENALTY = 0.75;
  const UNVERIFIED_PENALTY = 0.05;
  const DISPUTED_PENALTY = 0.4;
  const FLOW_CATEGORIES = ["valve", "strainer", "quick_disconnect"];

  const delta = (value, target) => {
    if (target == null) return null;
    if (value == null) return UNKNOWN_PENALTY;
    return Math.abs(value - target) / Math.max(Math.abs(target), 1e-9);
  };

  const scored = [];
  for (const c of filtered) {
    const category = String(c.category || "").toLowerCase();
    const pressure = toNum(c.pressure_rating_bar);
    const maxTemp = toNum(c.max_temperature_c);
    const warnings = [];

    // Duty limits are hard filters, as in the engine.
    if (params.required_pressure_bar != null) {
      if (pressure != null && pressure < params.required_pressure_bar) continue;
      if (pressure == null) warnings.push("pressure rating not published");
    }
    if (params.required_temperature_c != null) {
      if (maxTemp != null && maxTemp < params.required_temperature_c) continue;
      if (maxTemp == null) warnings.push("maximum temperature not published");
    }

    const flow = FLOW_CATEGORIES.includes(category);
    const w = flow
      ? { capacity: 1.0, size: 0.8, connection: 1.0, coefficient: 2.0 }
      : { capacity: 2.0, size: 0.6, connection: 0.8, coefficient: 1.0 };

    let weighted = 0;
    let total = 0;
    const add = (d, weight) => {
      if (d == null) return;
      weighted += weight * d;
      total += weight;
    };

    add(delta(toNum(c.nominal_size_mm), params.size_mm), w.size);
    const connMm = toNum(c.nominal_size_mm) ?? (toNum(c.nominal_size_inch) != null ? toNum(c.nominal_size_inch) * MM_PER_INCH : null);
    add(delta(connMm, params.connection_size_mm), w.connection);
    const targetCoeff = params.cv != null ? params.cv : params.kv;
    if (flow && targetCoeff != null) {
      add(delta(coeffForTarget(c, params.cv, params.kv), targetCoeff), w.coefficient);
    }
    add(delta(toNum(c.capacity_kw), params.capacity_kw), w.capacity);

    let score = total ? weighted / total : 0;
    const status = String(c.verification_status || "unverified").toLowerCase();
    if (status === "disputed") {
      score += DISPUTED_PENALTY;
      warnings.push("vendor literature does not support this entry");
    } else if (status !== "verified") {
      score += UNVERIFIED_PENALTY;
      warnings.push("specifications not verified against a source document");
    }

    scored.push({ score, warnings, component: c });
  }

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
  // Build the vocabulary from the catalog rather than the markup.
  for (const category of [...new Set(CATALOG.map((x) => x.category))].sort()) {
    const option = document.createElement("option");
    option.value = category;
    option.textContent = category;
    categoryEl.appendChild(option);
  }
  const cvEl = document.getElementById("cv");
  const kvEl = document.getElementById("kv");
  function syncInputHints() {
    const c = categoryEl.value;
    // Cv/Kv apply to quick disconnects too.
    const flowEnabled = !c || ["valve", "strainer", "quick_disconnect"].includes(c);
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
      required_pressure_bar: toNum(document.getElementById("reqBar").value),
      required_temperature_c: toNum(document.getElementById("reqC").value),
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
