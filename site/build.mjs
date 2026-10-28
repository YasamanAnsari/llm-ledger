// Builds the static site into site/dist from the repository's own data.
// Every table is copied row for row; only the summary counts are computed.
import {execSync} from 'node:child_process';
import {cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';

const SITE = dirname(fileURLToPath(import.meta.url));
const REPO = join(SITE, '..');
const DIST = join(SITE, 'dist');
const STATIC = ['index.html', 'market.html', 'styles.css', 'app.js', 'market.js',
  'ledger-engine.mjs', 'charts.mjs', 'assets'];
const OBSERVATIONS = {
  availability: 'data/observations/availability_observations.csv',
  price: 'data/observations/price_observations.csv',
  capability: 'data/observations/capability_observations.csv',
};
const TABLES = {
  models: 'data/core/models.csv',
  events: 'data/core/events.csv',
  claims: 'data/core/claims.csv',
  organizations: 'data/core/organizations.csv',
  attributes: 'data/core/attributes.csv',
  crosswalk: 'data/core/crosswalk.csv',
  capability: 'data/generated/llm_ledger_capability.csv',
  first_mentions: 'data/generated/research_first_mentions.csv',
};
const DOWNLOADS = [
  'data/core/models.csv', 'data/core/events.csv', 'data/core/claims.csv',
  'data/core/organizations.csv', 'data/core/attributes.csv', 'data/core/crosswalk.csv',
  'data/generated/models_latest.csv', 'data/generated/llm_ledger_wide.csv',
  'data/generated/llm_ledger_enriched.csv', 'data/generated/reschedules.csv',
  'data/generated/market_on_date.csv', 'data/generated/price_changes.csv',
  'data/generated/llm_ledger_capability.csv', 'data/generated/research_mentions_monthly.csv',
  'data/generated/research_first_mentions.csv', 'data/observations/research_mentions.csv',
  ...Object.values(OBSERVATIONS),
  'data/observations/model_versions.csv',
];

/** RFC 4180 CSV text -> array of row objects keyed by the header. */
export function parseCsv(text) {
  const rows = [];
  let row = [], field = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(field); rows.push(row); row = []; field = '';
    } else field += c;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  const [header, ...body] = rows.filter(r => r.length > 1 || r[0] !== '');
  return body.map((r, n) => {
    if (r.length !== header.length) throw new Error(`row ${n + 2} has ${r.length} fields, header has ${header.length}`);
    return Object.fromEntries(header.map((h, i) => [h, r[i]]));
  });
}

function readTable(path) {
  const full = join(REPO, path);
  if (!existsSync(full)) throw new Error(`required table missing: ${path}`);
  const rows = parseCsv(readFileSync(full, 'utf8'));
  if (!rows.length) throw new Error(`required table is empty: ${path}`);
  return rows;
}

function count(rows, key) {
  const out = {};
  for (const r of rows) out[r[key]] = (out[r[key]] || 0) + 1;
  return out;
}

function commitSha() {
  if (process.env.VERCEL_GIT_COMMIT_SHA) return process.env.VERCEL_GIT_COMMIT_SHA;
  return execSync('git rev-parse HEAD', {cwd: REPO}).toString().trim();
}

const subject = r => `${r.source}|${r.provider}|${r.api_id}`;

/** Observation runs for listings that name a ledger model, as arrays
 * (market.html joins them for any day with marketOn). */
export function marketPayload(models, observations) {
  const listed = observations.availability.filter(r => r.model_id);
  const subjects = new Set(listed.map(subject));
  const used = new Set(listed.map(r => r.model_id));
  const runs = rows => rows.filter(r => subjects.has(subject(r)));
  return {
    first: listed.map(r => r.first_observed).sort()[0],
    last: listed.map(r => r.last_observed).sort().at(-1),
    models: Object.fromEntries(models.filter(m => used.has(m.model_id))
      .map(m => [m.model_id, [m.canonical_name, m.developer_org_id, m.access_type]])),
    availability: listed.map(r => [r.source, r.provider, r.api_id, r.model_id,
      r.first_observed, r.last_observed, r.source_url]),
    price: runs(observations.price).map(r => [subject(r), r.price_input, r.price_output,
      r.price_cached, r.unit, r.first_observed, r.last_observed]),
    capability: runs(observations.capability).map(r => [subject(r), r.context_length,
      r.max_output, r.modalities_in, r.tool_use, r.first_observed, r.last_observed]),
  };
}

function main() {
  const data = Object.fromEntries(Object.entries(TABLES).map(([name, path]) => [name, readTable(path)]));
  const dated = data.models.filter(m => m.first_public_availability_date);
  const annual = {};
  for (const m of dated) {
    const year = m.first_public_availability_date.slice(0, 4);
    annual[year] ??= {};
    annual[year][m.access_type] = (annual[year][m.access_type] || 0) + 1;
  }
  // The data's own last-change date, not the build date: a code-only
  // deploy must not make an old snapshot look new.
  const snapshot = data.models.map(m => m.record_updated.slice(0, 10)).sort().at(-1);
  data.meta = {
    snapshot,
    commit: commitSha(),
    models: data.models.length,
    organizations: data.organizations.length,
    events: data.events.length,
    liveClaims: data.claims.filter(c => !c.superseded_on).length,
    confidence: count(data.events, 'confidence'),
    access: count(data.models, 'access_type'),
    annual,
    undated: data.models.length - dated.length,
    icons: readdirSync(join(REPO, 'assets/orgs')).filter(f => f.endsWith('.svg')).map(f => f.slice(0, -4)),
  };

  rmSync(DIST, {recursive: true, force: true});
  mkdirSync(join(DIST, 'data'), {recursive: true});
  for (const item of STATIC) cpSync(join(SITE, item), join(DIST, item), {recursive: true});
  cpSync(join(REPO, 'assets/orgs'), join(DIST, 'assets/orgs'), {recursive: true, filter: f => !f.endsWith('.md')});
  for (const path of DOWNLOADS) cpSync(join(REPO, path), join(DIST, 'data', path.split('/').at(-1)));
  writeFileSync(join(DIST, 'data/ledger.json'), JSON.stringify(data));
  const observations = Object.fromEntries(Object.entries(OBSERVATIONS).map(([name, path]) => [name, readTable(path)]));
  const marketData = {...marketPayload(data.models, observations), commit: data.meta.commit,
    orgs: Object.fromEntries(data.organizations.map(o => [o.org_id, o.short_name || o.canonical_name])),
    icons: data.meta.icons};
  writeFileSync(join(DIST, 'data/market.json'), JSON.stringify(marketData));
  console.log(`site: ${data.meta.models} models, ${data.meta.events} events, snapshot ${snapshot} -> ${DIST}`);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main();
