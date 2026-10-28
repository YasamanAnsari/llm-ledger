// Figures for the site: pure functions that summarize the ledger, and
// renderers that turn those summaries into HTML/SVG strings.

export const ACCESS = [
  {key: 'fully_open', label: 'Fully open', noun: 'fully open models', color: '#2b5f8e'},
  {key: 'open_weights', label: 'Other open weights', noun: 'other open-weight models', color: '#2f6b52'},
  {key: 'api_only', label: 'API only', noun: 'API-only models', color: '#b57a2c'},
];
export const OPENNESS = [
  {key: 'fully_open', label: 'Fully open: weights, data and code', noun: 'fully open', color: '#2b5f8e'},
  {key: 'open_license', label: 'OSI or permissive license', noun: 'open license', color: '#5f9a7a'},
  {key: 'restricted', label: 'Restricted license', noun: 'restricted license', color: '#d0b27a'},
  {key: 'unknown', label: 'License not recorded', noun: 'license not recorded', color: '#d4d9d0'},
];
export const COUNTRIES = [
  {key: 'US', label: 'United States', noun: 'US models', color: '#3a5a8c'},
  {key: 'CN', label: 'China', noun: 'Chinese models', color: '#b0413e'},
  {key: 'other', label: 'Elsewhere or unstated', noun: 'models from elsewhere', color: '#a7aea6'},
];
const OPEN_LICENSES = new Set(['osi_approved', 'permissive']);

/** Fully open: open weights with training data and code released, under
 * an OSI-approved or permissive license. Blank data/code means not
 * reviewed, so those models stay with the other open weights. */
export function accessGroup(m) {
  if (m.access_type !== 'open_weights') return m.access_type;
  return OPEN_LICENSES.has(m.license_family) && m.training_data_released === 'true' && m.training_code_released === 'true'
    ? 'fully_open' : 'open_weights';
}

/** Where an open-weight model sits between fully open and unlicensed. */
export function opennessTier(m) {
  if (accessGroup(m) === 'fully_open') return 'fully_open';
  if (OPEN_LICENSES.has(m.license_family)) return 'open_license';
  return m.license_family === 'open_weights_restricted' ? 'restricted' : 'unknown';
}

/** Adds `access_group` and `country_group` (from the developer's
 * headquarters) to each model, and copies them onto rows keyed by model_id. */
export function annotateGroups(models, organizations, keyedRows = []) {
  const country = new Map(organizations.map(o => [o.org_id, o.country]));
  const byId = new Map();
  for (const m of models) {
    const c = country.get(m.developer_org_id);
    Object.assign(m, {access_group: accessGroup(m), country_group: c === 'US' || c === 'CN' ? c : 'other'});
    byId.set(m.model_id, m);
  }
  for (const r of keyedRows) {
    const m = byId.get(r.model_id);
    if (m) Object.assign(r, {access_group: m.access_group, country_group: m.country_group});
  }
}

/** {year: {group key: models}} by year of first public availability. */
export function annualCounts(models, groupOf) {
  const out = {};
  for (const m of models) {
    if (!m.first_public_availability_date) continue;
    const year = m.first_public_availability_date.slice(0, 4);
    out[year] ??= {};
    out[year][groupOf(m)] = (out[year][groupOf(m)] || 0) + 1;
  }
  return out;
}
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const num = n => new Intl.NumberFormat('en-US').format(n);
const pct = (part, whole) => whole ? Math.round(part / whole * 100) : 0;

export const GAP_BINS = [
  {label: 'Before', test: d => d < 0},
  {label: 'Same day', test: d => d === 0},
  {label: '1–7 days', test: d => d >= 1 && d <= 7},
  {label: '8–30 days', test: d => d >= 8 && d <= 30},
  {label: '31–90 days', test: d => d >= 31 && d <= 90},
  {label: '91–365 days', test: d => d >= 91 && d <= 365},
  {label: 'Over a year', test: d => d > 365},
];

/** A day-count column binned per access type, with the group median. */
function dayBins(rows, field) {
  const out = {};
  for (const {key} of ACCESS) {
    const days = rows.filter(r => r.access_group === key && r[field] !== '').map(r => Number(r[field])).sort((a, b) => a - b);
    const mid = days.length / 2;
    out[key] = {
      n: days.length,
      counts: GAP_BINS.map(b => days.filter(b.test).length),
      later: days.filter(d => d > 0).length,
      median: !days.length ? null : days.length % 2 ? days[Math.floor(mid)] : (days[mid - 1] + days[mid]) / 2,
    };
  }
  return out;
}

/** Days from announcement to first availability (models.anticipation_days). */
export const gapBins = models => dayBins(models, 'anticipation_days');

/** Days from first availability to the first arXiv paper naming the model
 * (research_first_mentions.days_to_first_mention). */
export const mentionBins = rows => dayBins(rows, 'days_to_first_mention');

export const FATES = [
  {key: 'retired', label: 'Shut down by the developer', color: '#7b3a33'},
  {key: 'scheduled', label: 'Shutdown scheduled', color: '#c9867c'},
  {key: 'host_only', label: 'Dropped by a host only', color: '#d9c49a'},
  {key: 'none', label: 'No retirement on record', color: '#e3e9dc'},
];

/** What happened to each model after launch, per access type. A retirement
 * with no platform is the developer's own; a platform one is one host. */
export function retirementFates(models, events, today) {
  const byModel = new Map();
  for (const e of events) if (e.event_type === 'retired') {
    if (!byModel.has(e.model_id)) byModel.set(e.model_id, []);
    byModel.get(e.model_id).push(e);
  }
  const out = {};
  for (const {key} of ACCESS) {
    const counts = Object.fromEntries(FATES.map(f => [f.key, 0]));
    const group = models.filter(m => m.access_group === key);
    for (const m of group) {
      const retired = byModel.get(m.model_id) || [];
      const own = retired.filter(e => !e.platform);
      const fate = own.some(e => e.date <= today) ? 'retired' : own.length ? 'scheduled' : retired.length ? 'host_only' : 'none';
      counts[fate]++;
    }
    out[key] = {n: group.length, counts};
  }
  return out;
}

export const METRICS = {
  price_output: {label: 'Output price', unit: 'USD per million output tokens', format: v => `$${v < 1 ? +v.toPrecision(2) : num(+v.toFixed(1))}`},
  context_length: {label: 'Context window', unit: 'tokens', format: v => v >= 1e6 ? `${+(v / 1e6).toFixed(1)}M` : `${Math.round(v / 1e3)}K`},
};

/** One point per dated model with a positive value for `metric`; values of
 * zero (free listings) cannot sit on a log axis and are counted instead. */
export function scatterPoints(models, attributes, metric) {
  const attr = new Map(attributes.map(a => [a.model_id, a]));
  const points = [];
  let zero = 0;
  for (const m of models) {
    const raw = attr.get(m.model_id)?.[metric];
    if (!m.first_public_availability_date || raw === undefined || raw === '' || !ACCESS.some(a => a.key === m.access_group)) continue;
    const value = Number(raw);
    if (value > 0) points.push({id: m.model_id, name: m.canonical_name, access: m.access_group, date: m.first_public_availability_date, value});
    else zero++;
  }
  return {points, zero};
}

/** Median value per launch year and access type, for years with at least three points. */
export function yearlyMedians(points) {
  const groups = new Map();
  for (const p of points) {
    const k = `${p.access}|${p.date.slice(0, 4)}`;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(p.value);
  }
  const out = [];
  for (const [k, values] of groups) {
    if (values.length < 3) continue;
    const [access, year] = k.split('|');
    values.sort((a, b) => a - b);
    const mid = values.length / 2;
    out.push({access, year, n: values.length, median: values.length % 2 ? values[Math.floor(mid)] : (values[mid - 1] + values[mid]) / 2});
  }
  return out.sort((a, b) => a.access.localeCompare(b.access) || a.year.localeCompare(b.year));
}

export function dataTable(caption, headers, rows) {
  return `<details class="figure-table"><summary>View as table</summary><table><caption class="sr-only">${esc(caption)}</caption><thead><tr>${headers.map(h => `<th scope="col">${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${r.map((c, i) => i ? `<td>${esc(c)}</td>` : `<th scope="row">${esc(c)}</th>`).join('')}</tr>`).join('')}</tbody></table></details>`;
}

export function legend(items) {
  return `<div class="figure-legend">${items.map(i => `<span><i class="${esc(i.shape || 'square')}" style="--c:${i.color}"></i>${esc(i.label)}</span>`).join('')}</div>`;
}

export function renderGap(gaps, caption = 'Days from announcement to first availability, by access type') {
  const rows = GAP_BINS.map((b, i) => `<div class="gap-row"><span class="gap-label">${esc(b.label)}</span><div class="gap-bars">${ACCESS.map(a => {
    const g = gaps[a.key], share = pct(g.counts[i], g.n);
    return `<div class="gap-bar"><i style="width:${g.n ? g.counts[i] / g.n * 100 : 0}%;--c:${a.color}"></i><span>${share}% <small>(${num(g.counts[i])})</small></span></div>`;
  }).join('')}</div></div>`).join('');
  const table = dataTable(caption, ['Gap', ...ACCESS.map(a => `${a.label} (n=${gaps[a.key].n})`)],
    GAP_BINS.map((b, i) => [b.label, ...ACCESS.map(a => `${gaps[a.key].counts[i]} (${pct(gaps[a.key].counts[i], gaps[a.key].n)}%)`)]));
  const head = `<div class="gap-row gap-head"><span></span><div class="gap-bars">${ACCESS.map(a => `<span style="--c:${a.color}"><i></i>${esc(a.label)} <small>n=${num(gaps[a.key].n)}</small></span>`).join('')}</div></div>`;
  return `<div class="gap-chart">${head}${rows}</div>` + table;
}

export function renderAnnual(annual, partialYear, groups = ACCESS, caption = 'Models by year of first public availability and access type') {
  const years = Object.keys(annual).sort();
  const total = y => groups.reduce((s, a) => s + (annual[y][a.key] || 0), 0);
  const max = Math.max(...years.map(total));
  const bars = years.map(y => `<div class="annual-bar" title="${y}: ${groups.map(a => `${num(annual[y][a.key] || 0)} ${a.noun}`).join(', ')}${y === partialYear ? ' (year to date)' : ''}"><div class="stack" style="height:${total(y) / max * 85}%"><span class="bar-value">${num(total(y))}</span>${groups.slice().reverse().map(a => `<i style="flex:${annual[y][a.key] || 0};--c:${a.color}"></i>`).join('')}</div><span class="bar-year">${y}${y === partialYear ? '*' : ''}</span></div>`).join('');
  const table = dataTable(caption, ['Year', ...groups.map(a => a.label), 'Total'],
    years.map(y => [y + (y === partialYear ? ' (to date)' : ''), ...groups.map(a => num(annual[y][a.key] || 0)), num(total(y))]));
  return legend(groups) + `<div class="annual-chart">${bars}</div>` + table;
}

export function renderFates(fates) {
  const bars = ACCESS.map(a => {
    const f = fates[a.key];
    return `<div class="fate-row"><span class="fate-label">${esc(a.label)} <small>n=${num(f.n)}</small></span><div class="fate-bar">${FATES.map(x => f.counts[x.key] ? `<i style="flex:${f.counts[x.key]};--c:${x.color}" title="${esc(x.label)}: ${num(f.counts[x.key])} (${pct(f.counts[x.key], f.n)}%)">${pct(f.counts[x.key], f.n) >= 6 ? `${pct(f.counts[x.key], f.n)}%` : ''}</i>` : '').join('')}</div></div>`;
  }).join('');
  const table = dataTable('Retirement status by access type', ['Status', ...ACCESS.map(a => a.label)],
    FATES.map(x => [x.label, ...ACCESS.map(a => `${num(fates[a.key].counts[x.key])} (${pct(fates[a.key].counts[x.key], fates[a.key].n)}%)`)]));
  return legend(FATES) + `<div class="fate-chart">${bars}</div>` + table;
}

const W = 640, H = 300, M = {top: 14, right: 16, bottom: 30, left: 56};

export function renderScatter(points, metric, start, end) {
  const spec = METRICS[metric];
  const t0 = Date.parse(start), t1 = Date.parse(end);
  const values = points.map(p => p.value);
  const lo = Math.floor(Math.log10(Math.min(...values))), hi = Math.ceil(Math.log10(Math.max(...values)));
  const x = d => M.left + (Date.parse(d) - t0) / (t1 - t0) * (W - M.left - M.right);
  const y = v => H - M.bottom - (Math.log10(v) - lo) / (hi - lo) * (H - M.top - M.bottom);
  const yTicks = Array.from({length: hi - lo + 1}, (_, i) => 10 ** (lo + i));
  const years = [];
  for (let yr = new Date(start).getUTCFullYear() + 1; yr <= new Date(end).getUTCFullYear(); yr++) years.push(yr);
  const grid = yTicks.map(v => `<line x1="${M.left}" x2="${W - M.right}" y1="${y(v)}" y2="${y(v)}"/><text x="${M.left - 8}" y="${y(v) + 3}" text-anchor="end">${esc(spec.format(v))}</text>`).join('')
    + years.map(yr => `<line x1="${x(`${yr}-01-01`)}" x2="${x(`${yr}-01-01`)}" y1="${M.top}" y2="${H - M.bottom}"/><text x="${x(`${yr}-01-01`)}" y="${H - M.bottom + 18}" text-anchor="middle">${yr}</text>`).join('');
  const inRange = points.filter(p => p.date >= start && p.date <= end);
  const mark = (p, color) => {
    const cx = x(p.date).toFixed(1), cy = y(p.value).toFixed(1);
    const label = `${p.name}: ${spec.format(p.value)} · first available ${p.date}`;
    return p.access !== 'api_only'
      ? `<rect class="pt" data-model="${esc(p.id)}" x="${cx - 3}" y="${cy - 3}" width="6" height="6" transform="rotate(45 ${cx} ${cy})" fill="${color}"><title>${esc(label)}</title></rect>`
      : `<circle class="pt" data-model="${esc(p.id)}" cx="${cx}" cy="${cy}" r="3.2" fill="${color}"><title>${esc(label)}</title></circle>`;
  };
  const dots = ACCESS.map(a => inRange.filter(p => p.access === a.key).map(p => mark(p, a.color)).join('')).join('');
  const medians = yearlyMedians(inRange);
  const lines = ACCESS.map(a => {
    const pts = medians.filter(m => m.access === a.key).map(m => `${x(`${m.year}-07-01`).toFixed(1)},${y(m.median).toFixed(1)}`);
    return pts.length > 1 ? `<polyline class="median" points="${pts.join(' ')}" stroke="${a.color}"/>` : '';
  }).join('');
  const svg = `<svg class="scatter" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(spec.label)} by first availability date, log scale, by access group"><g class="grid">${grid}</g>${dots}${lines}</svg>`;
  const table = dataTable(`Median ${spec.label.toLowerCase()} by launch year`, ['Year', ...ACCESS.map(a => `${a.label} median (n)`)],
    [...new Set(medians.map(m => m.year))].sort().map(yr => [yr, ...ACCESS.map(a => {
      const m = medians.find(r => r.access === a.key && r.year === yr);
      return m ? `${spec.format(m.median)} (${m.n})` : '–';
    })]));
  return legend([...ACCESS.map(a => ({...a, shape: a.key === 'api_only' ? 'dot' : 'diamond'})), {label: 'Yearly median', color: '#6f7a73', shape: 'line'}]) + svg + table;
}

/** Best ECI score on record per group as of each ledger release date:
 * the running maximum, one step per model that raised it. */
export function capabilityFrontier(rows, groups = ACCESS, groupOf = r => r.access_group) {
  const out = {};
  for (const {key} of groups) {
    const group = rows.filter(r => groupOf(r) === key && r.first_public_availability_date && r.eci !== '')
      .sort((a, b) => a.first_public_availability_date.localeCompare(b.first_public_availability_date));
    const steps = [];
    for (const r of group) {
      const value = Number(r.eci);
      if (!steps.length || value > steps.at(-1).value) steps.push({date: r.first_public_availability_date, value, id: r.model_id, name: r.canonical_name});
    }
    out[key] = steps;
  }
  return out;
}

/** How long before the trailing group's best model the leading group
 * first scored at least as high; null when it never has. */
export function frontierLag(trailing, leading) {
  const best = trailing.at(-1);
  const first = best && leading.find(s => s.value >= best.value);
  return first ? {best, first, days: Math.round((Date.parse(best.date) - Date.parse(first.date)) / 864e5)} : null;
}

export function renderFrontier(frontier, start, end, groups = ACCESS, subject = 'access group') {
  // The step in force on `start` is drawn from the left edge.
  const shown = Object.fromEntries(groups.map(a => [a.key,
    frontier[a.key].filter((p, i, all) => !(all[i + 1]?.date <= start))]));
  const values = Object.values(shown).flat().map(s => s.value);
  const lo = Math.floor(Math.min(...values) / 10) * 10, hi = Math.ceil(Math.max(...values) / 10) * 10;
  const t0 = Date.parse(start), t1 = Date.parse(end);
  const x = d => M.left + (Math.max(Date.parse(d), t0) - t0) / (t1 - t0) * (W - M.left - M.right);
  const y = v => H - M.bottom - (v - lo) / (hi - lo) * (H - M.top - M.bottom);
  const years = [];
  for (let yr = new Date(start).getUTCFullYear() + 1; yr <= new Date(end).getUTCFullYear(); yr++) years.push(yr);
  const yTicks = Array.from({length: (hi - lo) / 10 + 1}, (_, i) => lo + i * 10);
  const grid = yTicks.map(v => `<line x1="${M.left}" x2="${W - M.right}" y1="${y(v)}" y2="${y(v)}"/><text x="${M.left - 8}" y="${y(v) + 3}" text-anchor="end">${v}</text>`).join('')
    + years.map(yr => `<line x1="${x(`${yr}-01-01`)}" x2="${x(`${yr}-01-01`)}" y1="${M.top}" y2="${H - M.bottom}"/><text x="${x(`${yr}-01-01`)}" y="${H - M.bottom + 18}" text-anchor="middle">${yr}</text>`).join('');
  const lines = groups.map(a => {
    const s = shown[a.key];
    if (!s.length) return '';
    const path = s.map((p, i) => `${i ? `H${x(p.date).toFixed(1)}V` : `M${x(p.date).toFixed(1)},`}${y(p.value).toFixed(1)}`).join('') + `H${x(end).toFixed(1)}`;
    const marks = s.map(p => `<circle class="pt" data-model="${esc(p.id)}" cx="${x(p.date).toFixed(1)}" cy="${y(p.value).toFixed(1)}" r="3.2" fill="${a.color}"><title>${esc(`${p.name}: ECI ${p.value} · first available ${p.date}`)}</title></circle>`).join('');
    return `<path class="median" d="${path}" stroke="${a.color}"/>${marks}`;
  }).join('');
  const svg = `<svg class="scatter" viewBox="0 0 ${W} ${H}" role="img" aria-label="Best Epoch Capabilities Index score on record by ledger release date, by ${esc(subject)}"><g class="grid">${grid}</g>${lines}</svg>`;
  const table = dataTable(`Models that raised the best ECI score of their ${subject}`, ['First available', 'Group', 'Model', 'ECI'],
    groups.flatMap(a => frontier[a.key].map(s => [s.date, a.label, s.name, s.value])).sort((p, q) => p[0].localeCompare(q[0])));
  return legend(groups.filter(a => frontier[a.key].length).map(a => ({...a, shape: 'line'}))) + svg + table;
}
