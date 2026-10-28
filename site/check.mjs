// Self-check for the site's data logic: node site/check.mjs
import assert from 'node:assert/strict';
import {marketPayload, parseCsv} from './build.mjs';
import {NO_COUNTRY, createLedger, marketOn, perMillion} from './ledger-engine.mjs';
import {accessGroup, annotateGroups, annualCounts, capabilityFrontier, frontierLag, gapBins, mentionBins, opennessTier, renderFrontier, renderGap, retirementFates, scatterPoints,
  yearlyMedians} from './charts.mjs';

assert.deepEqual(parseCsv('a,b\n1,"x, ""y"""\r\n2,\n'), [{a: '1', b: 'x, "y"'}, {a: '2', b: ''}]);
assert.throws(() => parseCsv('a,b\n1\n'), /field/);

const models = [
  {model_id: 'o1', access_type: 'open_weights', anticipation_days: '0', first_public_availability_date: '2025-01-10', canonical_name: 'O1'},
  {model_id: 'o2', access_type: 'open_weights', anticipation_days: '40', first_public_availability_date: '2025-03-01', canonical_name: 'O2'},
  {model_id: 'a1', access_type: 'api_only', anticipation_days: '-2', first_public_availability_date: '2025-02-01', canonical_name: 'A1'},
  {model_id: 'a2', access_type: 'api_only', anticipation_days: '', first_public_availability_date: '2025-05-01', canonical_name: 'A2'},
  {model_id: 'a3', access_type: 'api_only', anticipation_days: '', first_public_availability_date: '', canonical_name: 'A3'},
];

annotateGroups(models, [{org_id: 'us-lab', country: 'US'}], []);
assert.deepEqual(models.map(m => m.access_group), ['open_weights', 'open_weights', 'api_only', 'api_only', 'api_only']);
assert.deepEqual(models.map(m => m.country_group), ['other', 'other', 'other', 'other', 'other']);
const olmo = {access_type: 'open_weights', license_family: 'osi_approved', training_data_released: 'true', training_code_released: 'true'};
assert.equal(accessGroup(olmo), 'fully_open');
assert.equal(accessGroup({...olmo, training_data_released: 'partial'}), 'open_weights');
assert.equal(accessGroup({...olmo, license_family: 'open_weights_restricted'}), 'open_weights');
assert.deepEqual([olmo, {...olmo, training_code_released: ''}, {...olmo, license_family: 'open_weights_restricted'}, {...olmo, license_family: ''}].map(opennessTier),
  ['fully_open', 'open_license', 'restricted', 'unknown']);
const rows = [{model_id: 'x', developer_org_id: 'us-lab', access_type: 'api_only', first_public_availability_date: '2025-02-01'}];
const keyed = [{model_id: 'x'}, {model_id: 'not-in-ledger'}];
annotateGroups(rows, [{org_id: 'us-lab', country: 'US'}], keyed);
assert.deepEqual(keyed, [{model_id: 'x', access_group: 'api_only', country_group: 'US'}, {model_id: 'not-in-ledger'}]);
assert.deepEqual(annualCounts(models, m => m.access_group), {2025: {open_weights: 2, api_only: 2}});

const gaps = gapBins(models);
assert.equal(gaps.open_weights.n, 2);
assert.equal(gaps.open_weights.later, 1);
assert.deepEqual(gaps.open_weights.counts, [0, 1, 0, 0, 1, 0, 0]);
assert.deepEqual(gaps.api_only.counts, [1, 0, 0, 0, 0, 0, 0]);
assert.equal(gaps.open_weights.median, 20);
assert.ok(!renderGap(gaps).includes('Fully open'), 'a group with no dated models gets no column');
const firstMentions = mentionBins(['5', '200', '', '-3', '9'].map((days_to_first_mention, i) =>
  ({access_group: i < 3 ? 'open_weights' : 'api_only', days_to_first_mention})));
assert.deepEqual([firstMentions.open_weights.n, firstMentions.open_weights.median, firstMentions.api_only.median], [2, 102.5, 3]);
assert.deepEqual(firstMentions.api_only.counts, [1, 0, 0, 1, 0, 0, 0]);

const events = [
  {model_id: 'a1', event_type: 'retired', platform: '', date: '2026-01-01'},
  {model_id: 'a2', event_type: 'retired', platform: '', date: '2027-01-01'},
  {model_id: 'a3', event_type: 'retired', platform: 'azure', date: '2026-01-01'},
  {model_id: 'o1', event_type: 'api_ga', platform: '', date: '2025-01-10'},
];
const fates = retirementFates(models, events, '2026-06-01');
assert.deepEqual(fates.api_only.counts, {retired: 1, scheduled: 1, host_only: 1, none: 0});
assert.deepEqual(fates.open_weights.counts, {retired: 0, scheduled: 0, host_only: 0, none: 2});

const attributes = [{model_id: 'o1', price_output: '0'}, {model_id: 'o2', price_output: '2'}, {model_id: 'a1', price_output: '10'}, {model_id: 'a3', price_output: '5'}];
const {points, zero} = scatterPoints(models, attributes, 'price_output');
assert.equal(zero, 1);
assert.deepEqual(points.map(p => p.id), ['o2', 'a1']);

const medians = yearlyMedians([1, 2, 3, 10].map((value, i) => ({access: 'api_only', date: `2025-0${i + 1}-01`, value})));
assert.deepEqual(medians, [{access: 'api_only', year: '2025', n: 4, median: 2.5}]);
assert.deepEqual(yearlyMedians([{access: 'api_only', date: '2025-01-01', value: 1}]), []);

const scored = [['o1', 'open_weights', '2025-01-10', '120'], ['o2', 'open_weights', '2025-03-01', '110'],
  ['o3', 'open_weights', '2025-06-01', '140'], ['a1', 'api_only', '2024-12-01', '130'],
  ['a2', 'api_only', '2025-02-01', '145'], ['a3', 'api_only', '', '160']]
  .map(([model_id, access_group, first_public_availability_date, eci]) =>
    ({model_id, access_group, first_public_availability_date, eci, canonical_name: model_id}));
const frontier = capabilityFrontier(scored);
assert.deepEqual(frontier.open_weights.map(s => s.id), ['o1', 'o3']);
assert.deepEqual(frontier.api_only.map(s => s.id), ['a1', 'a2']);
const lag = frontierLag(frontier.open_weights, frontier.api_only);
assert.deepEqual([lag.best.id, lag.first.id, lag.days], ['o3', 'a2', 120]);
const unmatched = capabilityFrontier(scored.slice(0, 4));
assert.equal(frontierLag(unmatched.open_weights, unmatched.api_only), null);
assert.deepEqual(frontier.fully_open, []);
assert.match(renderFrontier(frontier, '2025-01-01', '2025-12-31'), /data-model="a1"/);

const observed = {
  availability: [
    {source: 'openrouter', provider: 'openrouter', api_id: 'acme/a1', model_id: 'a1', first_observed: '2026-10-01', last_observed: '2026-10-05', source_url: 'https://openrouter.ai/api/v1/models'},
    {source: 'models_dev', provider: 'x', api_id: 'unmapped', model_id: '', first_observed: '2026-10-01', last_observed: '2026-10-05', source_url: 'https://models.dev/api.json'},
  ],
  price: [
    {source: 'openrouter', provider: 'openrouter', api_id: 'acme/a1', price_input: '0.0000025', price_output: '0.00001', price_cached: '', unit: 'per_token', first_observed: '2026-10-01', last_observed: '2026-10-02'},
    {source: 'openrouter', provider: 'openrouter', api_id: 'acme/a1', price_input: '-1', price_output: '0.000012', price_cached: '', unit: 'per_token', first_observed: '2026-10-03', last_observed: '2026-10-05'},
  ],
  capability: [],
};
const payload = marketPayload(models, observed);
assert.deepEqual(Object.keys(payload.models), ['a1']);
assert.deepEqual([payload.first, payload.last], ['2026-10-01', '2026-10-05']);
const [early] = marketOn(payload, '2026-10-02');
assert.deepEqual(early.price, {input: 2.5, output: 10, cached: null});
assert.equal(early.cap, null);
assert.deepEqual(marketOn(payload, '2026-10-04')[0].price, {input: null, output: 12, cached: null});
assert.deepEqual(marketOn(payload, '2026-10-06'), []);
assert.equal(perMillion('2', 'per_1m_tokens'), 2);

const explorer = createLedger({
  organizations: [{org_id: 'us-lab', country: 'US'}, {org_id: 'cn-lab', country: 'CN'}, {org_id: 'no-hq', country: ''}],
  models: ['us-lab', 'cn-lab', 'no-hq'].map(org => ({model_id: `${org}-m`, canonical_name: org, family: '', developer_org_id: org,
    access_type: 'open_weights', first_public_availability_date: '2025-01-01', first_availability_via: '', first_availability_confidence: ''})),
  events: [], claims: [], crosswalk: [], attributes: [],
});
assert.deepEqual(explorer.query({country: 'CN'}).map(r => r.model.model_id), ['cn-lab-m']);
assert.deepEqual(explorer.query({country: NO_COUNTRY}).map(r => r.model.model_id), ['no-hq-m']);
assert.equal(explorer.query({}).length, 3);

console.log('site check: ok');
