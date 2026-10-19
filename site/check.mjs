// Self-check for the site's data logic: node site/check.mjs
import assert from 'node:assert/strict';
import {parseCsv} from './build.mjs';
import {gapBins, retirementFates, scatterPoints, yearlyMedians} from './charts.mjs';

assert.deepEqual(parseCsv('a,b\n1,"x, ""y"""\r\n2,\n'), [{a: '1', b: 'x, "y"'}, {a: '2', b: ''}]);
assert.throws(() => parseCsv('a,b\n1\n'), /field/);

const models = [
  {model_id: 'o1', access_type: 'open_weights', anticipation_days: '0', first_public_availability_date: '2025-01-10', canonical_name: 'O1'},
  {model_id: 'o2', access_type: 'open_weights', anticipation_days: '40', first_public_availability_date: '2025-03-01', canonical_name: 'O2'},
  {model_id: 'a1', access_type: 'api_only', anticipation_days: '-2', first_public_availability_date: '2025-02-01', canonical_name: 'A1'},
  {model_id: 'a2', access_type: 'api_only', anticipation_days: '', first_public_availability_date: '2025-05-01', canonical_name: 'A2'},
  {model_id: 'a3', access_type: 'api_only', anticipation_days: '', first_public_availability_date: '', canonical_name: 'A3'},
];

const gaps = gapBins(models);
assert.equal(gaps.open_weights.n, 2);
assert.equal(gaps.open_weights.later, 1);
assert.deepEqual(gaps.open_weights.counts, [0, 1, 0, 0, 1, 0, 0]);
assert.deepEqual(gaps.api_only.counts, [1, 0, 0, 0, 0, 0, 0]);

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

console.log('site check: ok');
