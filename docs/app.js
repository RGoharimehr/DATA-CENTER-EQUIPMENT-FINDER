let CATALOG = [];

const KV_PER_CV = 0.865;
const toNum = (v) => (v === "" || v == null ? null : Number(v));

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
    if (params.brand && String(c.brand).toLowerCase() !== params.brand.toLowerCase()) return false;
    return true;
  });

  const scored = filtered.map((c) => {
    let score = 0;
    score += ndelta(toNum(c.nominal_size_mm), params.size_mm, 0.2);
    if (params.cv != null || params.kv != null) {
      score += ndelta(coeffForTarget(c, params.cv, params.kv), params.cv ?? params.kv, 0.6);
    }
    score += ndelta(toNum(c.capacity_kw), params.capacity_kw, 0.3);
    if (c.estimated_price_usd == null || c.estimated_price_usd === "") score += 0.05;
    return { score, component: c };
  });

  return scored.sort((a, b) => a.score - b.score).slice(0, Math.max(1, params.top_n));
}

function checkCompatibility(partNumbers, requiredMaterial, maxTime) {
  const picked = CATALOG.filter((x) => partNumbers.some((p) => String(x.part_number).toLowerCase() === p.toLowerCase()));
  const reasons = [];

  const eq = {
    NPT: new Set(["NPT", "FPT"]), FPT: new Set(["NPT", "FPT"]),
    ODF: new Set(["ODF", "ODS"]), ODS: new Set(["ODF", "ODS"])
  };
  for (let i = 0; i < picked.length; i++) {
    for (let j = i + 1; j < picked.length; j++) {
      const a = (picked[i].connection_type || "").toUpperCase();
      const b = (picked[j].connection_type || "").toUpperCase();
      if (a && b && a !== b && !(eq[a] && eq[a].has(b))) {
        reasons.push(`Connection mismatch: ${picked[i].part_number}(${a}) vs ${picked[j].part_number}(${b})`);
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
      if (t != null && t > maxTime) reasons.push(`Connection time too high: ${p.part_number} requires ${t} min`);
    }
  }

  return { is_compatible: reasons.length === 0, reasons, selected_count: picked.length, requested_count: partNumbers.length };
}

function bindUi() {
  document.getElementById("find").addEventListener("click", () => {
    const params = {
      category: document.getElementById("category").value.trim() || null,
      brand: document.getElementById("brand").value.trim() || null,
      size_mm: toNum(document.getElementById("size").value),
      cv: toNum(document.getElementById("cv").value),
      kv: toNum(document.getElementById("kv").value),
      capacity_kw: toNum(document.getElementById("cap").value),
      top_n: Number(document.getElementById("topn").value || 5)
    };
    const out = findMatches(params);
    document.getElementById("findOut").textContent = JSON.stringify(out, null, 2);
  });

  document.getElementById("compat").addEventListener("click", () => {
    const partNumbers = document.getElementById("parts").value.split(",").map((x) => x.trim()).filter(Boolean);
    const requiredMaterial = document.getElementById("material").value.trim() || null;
    const maxTime = toNum(document.getElementById("maxTime").value);
    const out = checkCompatibility(partNumbers, requiredMaterial, maxTime);
    document.getElementById("compatOut").textContent = JSON.stringify(out, null, 2);
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
