// Figures for the site: pure functions that summarize the ledger, and
// renderers that turn those summaries into HTML/SVG strings.
import {perMillion} from './ledger-engine.mjs';

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

export const AGE_BINS = [
  {label: 'Before', test: d => d < 0},
  {label: 'Under 3 months', test: d => d >= 0 && d <= 90},
  {label: '3–6 months', test: d => d >= 91 && d <= 182},
  {label: '6–12 months', test: d => d >= 183 && d <= 365},
  {label: '1–2 years', test: d => d >= 366 && d <= 730},
  {label: 'Over 2 years', test: d => d > 730},
];

/** A day-count column binned per access type, with the group median. */
function dayBins(rows, field, bins = GAP_BINS) {
  const out = {};
  for (const {key} of ACCESS) {
    const days = rows.filter(r => r.access_group === key && r[field] !== '').map(r => Number(r[field])).sort((a, b) => a - b);
    const mid = days.length / 2;
    out[key] = {
      n: days.length,
      counts: bins.map(b => days.filter(b.test).length),
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

/** Age at technical or usage obsolescence (obsolescence.csv `*_age_days`). */
export const ageBins = (rows, field) => dayBins(rows, field, AGE_BINS);

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

export function renderGap(gaps, caption = 'Days from announcement to first availability, by access type', bins = GAP_BINS) {
  const groups = ACCESS.filter(a => gaps[a.key].n);
  const rows = bins.map((b, i) => `<div class="gap-row"><span class="gap-label">${esc(b.label)}</span><div class="gap-bars">${groups.map(a => {
    const g = gaps[a.key], share = pct(g.counts[i], g.n);
    return `<div class="gap-bar"><i style="width:${g.counts[i] / g.n * 100}%;--c:${a.color}"></i><span>${share}% <small>(${num(g.counts[i])})</small></span></div>`;
  }).join('')}</div></div>`).join('');
  const table = dataTable(caption, ['Gap', ...groups.map(a => `${a.label} (n=${gaps[a.key].n})`)],
    bins.map((b, i) => [b.label, ...groups.map(a => `${gaps[a.key].counts[i]} (${pct(gaps[a.key].counts[i], gaps[a.key].n)}%)`)]));
  const head = `<div class="gap-row gap-head"><span></span><div class="gap-bars">${groups.map(a => `<span style="--c:${a.color}"><i></i>${esc(a.label)} <small>n=${num(gaps[a.key].n)}</small></span>`).join('')}</div></div>`;
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

/** Highest LMArena rating per group on each published leaderboard. Ratings
 * are refit every publication, so a line can fall; it is not a record. */
export function arenaBest(rows, groups, groupOf) {
  const out = Object.fromEntries(groups.map(g => [g.key, new Map()]));
  for (const r of rows) {
    const best = out[groupOf(r)];
    if (best && !(best.get(r.date)?.value >= r.value)) best.set(r.date, r);
  }
  return Object.fromEntries(Object.entries(out).map(([key, byDate]) =>
    [key, [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date))]));
}

const ECI_METRIC = {label: 'ECI', step: 10, when: 'first available', axis: 'Best Epoch Capabilities Index score on record by ledger release date',
  caption: 'Models that raised the best ECI score of their', dateHead: 'First available'};
export const ARENA_METRIC = {label: 'Arena rating', step: 50, when: 'leaderboard of', axis: 'Highest LMArena text rating (style control) on each published leaderboard',
  caption: 'Highest-rated model on each LMArena text leaderboard, per', dateHead: 'Leaderboard'};

export function renderFrontier(frontier, start, end, groups = ACCESS, subject = 'access group', metric = ECI_METRIC) {
  // The step in force on `start` is drawn from the left edge.
  const shown = Object.fromEntries(groups.map(a => [a.key,
    frontier[a.key].filter((p, i, all) => !(all[i + 1]?.date <= start))]));
  const values = Object.values(shown).flat().map(s => s.value);
  const {step} = metric;
  const lo = Math.floor(Math.min(...values) / step) * step, hi = Math.ceil(Math.max(...values) / step) * step;
  const t0 = Date.parse(start), t1 = Date.parse(end);
  const x = d => M.left + (Math.max(Date.parse(d), t0) - t0) / (t1 - t0) * (W - M.left - M.right);
  const y = v => H - M.bottom - (v - lo) / (hi - lo) * (H - M.top - M.bottom);
  const years = [];
  for (let yr = new Date(start).getUTCFullYear() + 1; yr <= new Date(end).getUTCFullYear(); yr++) years.push(yr);
  const yTicks = Array.from({length: (hi - lo) / step + 1}, (_, i) => lo + i * step);
  const grid = yTicks.map(v => `<line x1="${M.left}" x2="${W - M.right}" y1="${y(v)}" y2="${y(v)}"/><text x="${M.left - 8}" y="${y(v) + 3}" text-anchor="end">${v}</text>`).join('')
    + years.map(yr => `<line x1="${x(`${yr}-01-01`)}" x2="${x(`${yr}-01-01`)}" y1="${M.top}" y2="${H - M.bottom}"/><text x="${x(`${yr}-01-01`)}" y="${H - M.bottom + 18}" text-anchor="middle">${yr}</text>`).join('');
  const lines = groups.map(a => {
    const s = shown[a.key];
    if (!s.length) return '';
    const path = s.map((p, i) => `${i ? `H${x(p.date).toFixed(1)}V` : `M${x(p.date).toFixed(1)},`}${y(p.value).toFixed(1)}`).join('') + `H${x(end).toFixed(1)}`;
    const marks = s.map(p => `<circle class="pt" data-model="${esc(p.id)}" cx="${x(p.date).toFixed(1)}" cy="${y(p.value).toFixed(1)}" r="3.2" fill="${a.color}"><title>${esc(`${p.name}: ${metric.label} ${p.value} · ${metric.when} ${p.date}`)}</title></circle>`).join('');
    return `<path class="median" d="${path}" stroke="${a.color}"/>${marks}`;
  }).join('');
  const svg = `<svg class="scatter" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`${metric.axis}, by ${subject}`)}"><g class="grid">${grid}</g>${lines}</svg>`;
  const table = dataTable(`${metric.caption} ${subject}`, [metric.dateHead, 'Group', 'Model', metric.label],
    groups.flatMap(a => frontier[a.key].map(s => [s.date, a.label, s.name, s.value])).sort((p, q) => p[0].localeCompare(q[0])));
  return legend(groups.filter(a => frontier[a.key].length).map(a => ({...a, shape: 'line'}))) + svg + table;
}

// Price, adoption and obsolescence figures. site/build.mjs runs the
// summaries at build time and writes each one as the figure's CSV.

export const OPEN_OR_API = [
  {key: 'open', label: 'Open weights', color: '#2f6b52'},
  {key: 'api_only', label: 'API only', color: '#b57a2c'},
];
const OPEN_OR_API_OF = {fully_open: 'open', open_weights: 'open', api_only: 'api_only'};
const PALETTE = ['#a7aea6', '#7b3a33', '#b57a2c', '#2f6b52', '#2b5f8e', '#6b4f8e', '#3f8f9a'];
const PRICE_SOURCES = new Set(['litellm', 'litellm_git']);

/** USD per 1M tokens at three input tokens to one output token; null unless
 * both prices are positive (a $0 entry is a local runtime or a free tier). */
export function blendedPrice(run) {
  const input = perMillion(run.price_input, run.unit), output = perMillion(run.price_output, run.unit);
  return input > 0 && output > 0 ? Number(((3 * input + output) / 4).toPrecision(12)) : null;
}

/** The first of each month from `start`'s month until `end`, then `end`. */
export function sampleDays(start, end) {
  const days = [];
  for (const d = new Date(`${start.slice(0, 7)}-01T00:00:00Z`); d.toISOString().slice(0, 10) < end; d.setUTCMonth(d.getUTCMonth() + 1)) days.push(d.toISOString().slice(0, 10));
  return [...days, end];
}

/** Map of day -> Map(model_id -> the cheapest blended price any provider in
 * LiteLLM's price table listed for the model that day). */
export function cheapestPrices(runs, days) {
  const out = new Map(days.map(d => [d, new Map()]));
  for (const r of runs) {
    const price = r.model_id && PRICE_SOURCES.has(r.source) ? blendedPrice(r) : null;
    if (price === null) continue;
    for (const d of days) {
      const byModel = out.get(d);
      if (r.first_observed <= d && d <= r.last_observed && !(byModel.get(r.model_id) <= price)) byModel.set(r.model_id, price);
    }
  }
  return out;
}

/** Map of model_id -> {id, name, group, eci}: the model's highest ECI entry,
 * grouped open weights or API only. */
export function eciScores(capability) {
  const out = new Map();
  for (const r of capability) {
    const eci = Number(r.eci), group = OPEN_OR_API_OF[r.access_group];
    if (r.eci !== '' && group && !(out.get(r.model_id)?.eci >= eci)) out.set(r.model_id, {id: r.model_id, name: r.canonical_name, group, eci});
  }
  return out;
}

const listings = (prices, scores) => [...prices].map(([date, byModel]) =>
  [date, [...byModel].filter(([id]) => scores.has(id)).map(([id, price]) => ({...scores.get(id), price}))]);
const cheapest = models => models.reduce((best, m) => !best || m.price < best.price ? m : best, null);
const topScored = models => models.reduce((best, m) => !best || m.eci > best.eci ? m : best, null);
const figureRow = (date, m, extra = {}) => ({date, ...extra, model_id: m.id, model: m.name, group: m.group, eci: m.eci, price: m.price});

/** The cheapest listed model scoring at least each ECI threshold, per group and day. */
export function priceToScore(prices, scores, thresholds) {
  const rows = [];
  for (const [date, models] of listings(prices, scores)) for (const threshold of thresholds) for (const {key} of OPEN_OR_API) {
    const best = cheapest(models.filter(m => m.group === key && m.eci >= threshold));
    if (best) rows.push(figureRow(date, best, {threshold}));
  }
  return rows;
}

/** On each of `dates`, the listed models no cheaper model matches on ECI, cheapest first. */
export function priceScoreFrontier(prices, scores, dates) {
  const rows = [];
  for (const [date, models] of listings(prices, scores)) {
    if (!dates.includes(date)) continue;
    let top = -Infinity;
    for (const m of models.sort((a, b) => a.price - b.price || b.eci - a.eci)) {
      if (m.eci > top) { top = m.eci; rows.push(figureRow(date, m)); }
    }
  }
  return rows;
}

/** The highest-ECI listed model each day, overall and at or under `budget` USD per 1M blended. */
export function budgetBest(prices, scores, budget) {
  const rows = [];
  for (const [date, models] of listings(prices, scores)) {
    for (const [series, pool] of [['overall', models], ['under_budget', models.filter(m => m.price <= budget)]]) {
      const best = topScored(pool);
      if (best) rows.push(figureRow(date, best, {series, budget}));
    }
  }
  return rows;
}

/** On each weekly hub-stats day, the Hub's 30-day downloads summed over the
 * repos of ledger models, by the year the model was first available. */
export function downloadsByCohort(runs, models) {
  const cohort = new Map(models.filter(m => m.first_public_availability_date).map(m => {
    const year = m.first_public_availability_date.slice(0, 4);
    return [m.model_id, year <= '2022' ? '2022 or earlier' : year];
  }));
  const hub = runs.filter(r => r.source === 'hub_stats' && r.downloads_30d !== '' && cohort.has(r.model_id));
  const days = [...new Set(hub.map(r => r.first_observed))].sort();
  const sums = new Map();
  for (const r of hub) for (const date of days) {
    if (date < r.first_observed || date > r.last_observed) continue;
    const key = `${date}|${cohort.get(r.model_id)}`;
    if (!sums.has(key)) sums.set(key, {date, cohort: cohort.get(r.model_id), downloads_30d: 0, repos: 0});
    const s = sums.get(key);
    s.downloads_30d += Number(r.downloads_30d);
    s.repos++;
  }
  return [...sums.values()].sort((a, b) => a.date.localeCompare(b.date) || a.cohort.localeCompare(b.cohort));
}

export const USAGE_AGES = [
  {key: 'under_3m', label: 'Under 3 months old', color: '#2b5f8e'},
  {key: '3_12m', label: '3–12 months old', color: '#2f6b52'},
  {key: 'over_1y', label: 'Over a year old', color: '#b57a2c'},
  {key: 'before', label: 'Used before its ledger date', color: '#7b3a33'},
  {key: 'unknown', label: 'Not in the ledger or undated', color: '#a7aea6'},
  {key: 'other', label: 'Outside the daily top 50', color: '#d4d9d0'},
];

function usageAge(row, released) {
  if (row.model_permaslug === 'other') return 'other';
  const day = released.get(row.model_id);
  if (!day) return 'unknown';
  const age = (Date.parse(row.date) - Date.parse(day)) / 864e5;
  return age < 0 ? 'before' : age <= 90 ? 'under_3m' : age <= 365 ? '3_12m' : 'over_1y';
}

/** Each model-age group's share of a month's OpenRouter tokens; age is days
 * from first public availability to the day of use. */
export function tokenShareByAge(usage, models) {
  const released = new Map(models.filter(m => m.first_public_availability_date).map(m => [m.model_id, m.first_public_availability_date]));
  const tokens = new Map(), totals = new Map(), seen = new Set();
  for (const r of usage) {
    const month = r.date.slice(0, 7), key = `${month}|${usageAge(r, released)}`;
    tokens.set(key, (tokens.get(key) || 0) + Number(r.total_tokens));
    if (!seen.has(r.date)) {
      seen.add(r.date);
      totals.set(month, (totals.get(month) || 0) + Number(r.day_total_tokens));
    }
  }
  return [...tokens].map(([key, n]) => {
    const [month, age] = key.split('|');
    return {month, age, tokens: n, share: n / totals.get(month)};
  }).sort((a, b) => a.month.localeCompare(b.month) || a.age.localeCompare(b.age));
}

/** Axis from data values to pixels between `from` and `to`, with labelled ticks. */
function axis({type, step, format}, values, from, to) {
  let lo = Math.min(...values), hi = Math.max(...values), ticks;
  if (type === 'time') {
    ticks = [];
    for (let yr = new Date(lo).getUTCFullYear() + 1; Date.UTC(yr, 0, 1) <= hi; yr++) ticks.push([Date.UTC(yr, 0, 1), String(yr)]);
  } else if (type === 'log') {
    [lo, hi] = [Math.floor(Math.log10(lo)), Math.ceil(Math.log10(hi))];
    ticks = Array.from({length: hi - lo + 1}, (_, i) => [10 ** (lo + i), format(10 ** (lo + i))]);
  } else {
    [lo, hi] = [Math.floor(lo / step) * step, Math.ceil(hi / step) * step];
    ticks = Array.from({length: Math.round((hi - lo) / step) + 1}, (_, i) => [lo + i * step, format(lo + i * step)]);
  }
  const position = type === 'log' ? v => Math.log10(v) : v => v;
  return {at: v => from + (position(v) - lo) / (hi - lo || 1) * (to - from), ticks};
}

/** Lines sharing two axes. `series`: {label, color, points: [{x, y, id?, title}]};
 * time x values are epoch milliseconds. `step` holds each value until the next point. */
export function renderLines(series, {x, y, label, step = false}) {
  const shown = series.filter(s => s.points.length);
  const points = shown.flatMap(s => s.points);
  const sx = axis(x, points.map(p => p.x), M.left, W - M.right), sy = axis(y, points.map(p => p.y), H - M.bottom, M.top);
  const grid = sy.ticks.map(([v, t]) => `<line x1="${M.left}" x2="${W - M.right}" y1="${sy.at(v).toFixed(1)}" y2="${sy.at(v).toFixed(1)}"/><text x="${M.left - 8}" y="${(sy.at(v) + 3).toFixed(1)}" text-anchor="end">${esc(t)}</text>`).join('')
    + sx.ticks.map(([v, t]) => `<line x1="${sx.at(v).toFixed(1)}" x2="${sx.at(v).toFixed(1)}" y1="${M.top}" y2="${H - M.bottom}"/><text x="${sx.at(v).toFixed(1)}" y="${H - M.bottom + 18}" text-anchor="middle">${esc(t)}</text>`).join('');
  const lines = shown.map(s => {
    const xy = s.points.map(p => [sx.at(p.x).toFixed(1), sy.at(p.y).toFixed(1)]);
    const path = xy.map(([px, py], i) => !i ? `M${px},${py}` : step ? `H${px}V${py}` : `L${px},${py}`).join('');
    const marks = s.points.map((p, i) => `<circle class="pt"${p.id ? ` data-model="${esc(p.id)}"` : ''} cx="${xy[i][0]}" cy="${xy[i][1]}" r="${p.id ? 3.2 : 2.4}" fill="${s.color}"><title>${esc(p.title)}</title></circle>`).join('');
    return `<path class="median" d="${path}" stroke="${s.color}"/>${marks}`;
  }).join('');
  return legend(shown.map(s => ({...s, shape: 'line'}))) + `<svg class="scatter" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}"><g class="grid">${grid}</g>${lines}</svg>`;
}

const TIME = {type: 'time'};
export const usd = v => `$${v < 1 ? +v.toPrecision(2) : num(+v.toFixed(2))}`;
const compact = v => new Intl.NumberFormat('en-US', {notation: 'compact'}).format(v);
const ECI_AXIS = {type: 'linear', step: 10, format: v => String(v)};
const at = date => Date.parse(date);

export function renderPriceToScore(rows, threshold) {
  const picked = rows.filter(r => r.threshold === threshold);
  const series = OPEN_OR_API.map(g => ({...g, points: picked.filter(r => r.group === g.key)
    .map(r => ({x: at(r.date), y: r.price, id: r.model_id, title: `${r.model} (ECI ${r.eci}): ${usd(r.price)} per 1M tokens on ${r.date}`}))}));
  return renderLines(series, {x: TIME, y: {type: 'log', format: usd}, label: `Cheapest price of a model scoring at least ${threshold} on ECI, log scale, open weights and API only`})
    + dataTable(`Cheapest model scoring at least ECI ${threshold}`, ['Day', 'Group', 'Model', 'ECI', 'USD per 1M tokens'],
      picked.map(r => [r.date, OPEN_OR_API.find(g => g.key === r.group).label, r.model, r.eci, usd(r.price)]));
}

export function renderPriceFrontier(rows) {
  const dates = [...new Set(rows.map(r => r.date))].sort();
  const series = dates.map((date, i) => ({label: date, color: PALETTE[(i + 1) % PALETTE.length], points: rows.filter(r => r.date === date)
    .map(r => ({x: r.price, y: r.eci, id: r.model_id, title: `${r.model}: ECI ${r.eci} at ${usd(r.price)} per 1M tokens on ${date}`}))}));
  return renderLines(series, {x: {type: 'log', format: usd}, y: ECI_AXIS, label: 'Best ECI score available at each price, log price scale, on selected days', step: true})
    + dataTable('Models on the price-score frontier', ['Day', 'Model', 'ECI', 'USD per 1M tokens'], rows.map(r => [r.date, r.model, r.eci, usd(r.price)]));
}

export function renderBudgetBest(rows) {
  const budget = rows.find(r => r.series === 'under_budget')?.budget;
  const series = [['overall', 'Best listed model', '#2b5f8e'], ['under_budget', `Best at or under ${usd(budget)} per 1M tokens`, '#b57a2c']]
    .map(([key, label, color]) => ({label, color, points: rows.filter(r => r.series === key)
      .map(r => ({x: at(r.date), y: r.eci, id: r.model_id, title: `${r.model}: ECI ${r.eci} at ${usd(r.price)} per 1M tokens on ${r.date}`}))}));
  return renderLines(series, {x: TIME, y: ECI_AXIS, label: 'Best ECI score among listed models, overall and under a budget', step: true})
    + dataTable('Best listed model overall and under the budget', ['Day', 'Series', 'Model', 'ECI', 'USD per 1M tokens'],
      rows.map(r => [r.date, r.series === 'overall' ? 'Overall' : 'Under budget', r.model, r.eci, usd(r.price)]));
}

export function renderCohortDownloads(rows) {
  const cohorts = [...new Set(rows.map(r => r.cohort))].sort();
  const series = cohorts.map((cohort, i) => ({label: cohort, color: PALETTE[i % PALETTE.length], points: rows.filter(r => r.cohort === cohort && r.downloads_30d > 0)
    .map(r => ({x: at(r.date), y: r.downloads_30d, title: `${cohort} models, ${r.date}: ${num(r.downloads_30d)} downloads in 30 days over ${num(r.repos)} repos`}))}));
  return renderLines(series, {x: TIME, y: {type: 'log', format: compact}, label: 'Hugging Face downloads in the past 30 days by release year of the model, log scale'})
    + dataTable('Hub downloads in the past 30 days by release year', ['Day', 'Released', 'Downloads (30 days)', 'Repos'],
      rows.map(r => [r.date, r.cohort, num(r.downloads_30d), num(r.repos)]));
}

export function renderTokenAge(rows) {
  const series = USAGE_AGES.map(g => ({...g, points: rows.filter(r => r.age === g.key)
    .map(r => ({x: at(`${r.month}-01`), y: r.share * 100, title: `${g.label}, ${r.month}: ${(r.share * 100).toFixed(1)}% of tokens`}))}));
  return renderLines(series, {x: TIME, y: {type: 'linear', step: 20, format: v => `${v}%`}, label: 'Share of OpenRouter tokens by model age, per month'})
    + dataTable('Share of OpenRouter tokens by model age', ['Month', 'Age', 'Share of tokens'],
      rows.map(r => [r.month, USAGE_AGES.find(g => g.key === r.age).label, `${(r.share * 100).toFixed(1)}%`]));
}
