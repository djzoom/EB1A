#!/usr/bin/env node
/**
 * Independent verification of V22 EB-1A prediction model.
 *
 * This script replicates the core simulation from index.html and validates
 * the prediction against actual Visa Bulletin history.
 *
 * Run: node scripts/verify_prediction.js
 */

const MS_PER_DAY = 86400000;

// === MODEL PARAMETERS (must match index.html PRESETS.realistic) ===
const PARAMS = {
  chinaBaseQuota: 2803,
  spilloverROW: 500,
  spilloverIndia: 0,
  eb4eb5Spillover: 200,
  familyMultiplier: 1.9,
  densityHigh: 12,
  densityPeak: 15
};

const TOTAL_SUPPLY = PARAMS.chinaBaseQuota + PARAMS.spilloverROW + PARAMS.spilloverIndia + PARAMS.eb4eb5Spillover;

// === DENSITY FUNCTION (must match getPDDensity in index.html) ===
const D_2021     = new Date('2021-01-01').getTime();
const D_2022_06  = new Date('2022-06-01').getTime();
const D_2023_01  = new Date('2023-01-01').getTime();
const D_2024_06  = new Date('2024-06-01').getTime();
const D_2025     = new Date('2025-01-01').getTime();

function getPDDensity(pdDate) {
  const d_low = 5, d_med = 10;
  const d_high = PARAMS.densityHigh, d_peak = PARAMS.densityPeak;
  if (pdDate < D_2021) return d_low;
  if (pdDate < D_2022_06) return d_low + (d_med - d_low) * (pdDate - D_2021) / (D_2022_06 - D_2021);
  if (pdDate < D_2023_01) return d_med;
  if (pdDate < D_2024_06) return d_med + (d_high - d_med) * (pdDate - D_2023_01) / (D_2024_06 - D_2023_01);
  if (pdDate < D_2025) return d_high + (d_peak - d_high) * (pdDate - D_2024_06) / (D_2025 - D_2024_06);
  return d_peak;
}

function gaussian(mean, sd) {
  let u = 0, v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  return mean + sd * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

// === VISA BULLETIN HISTORY (EB-1 China Table A) ===
const HISTORY = [
  ['2023-01-15', '2022-02-01'],
  ['2023-10-15', '2022-02-15'],
  ['2024-01-15', '2022-07-01'],
  ['2024-04-15', '2022-09-01'],
  ['2024-07-15', '2022-11-01'],
  ['2024-10-15', '2022-11-08'],
  ['2025-04-15', '2022-11-08'],
  ['2025-07-15', '2022-11-15'],
  ['2025-10-15', '2022-12-22'],
  ['2025-12-15', '2023-01-22'],
  ['2026-01-15', '2023-02-01'],
  ['2026-03-15', '2023-03-15'],
  ['2026-04-15', '2023-04-01'],
  ['2026-06-15', '2023-04-01'],
];

// === CURRENT STATE ===
const TODAY = new Date('2026-05-27').getTime();
const CURRENT_CUTOFF = new Date('2023-04-01').getTime();
const USER_PD = new Date('2024-06-20').getTime();
const GAP_DAYS = (USER_PD - CURRENT_CUTOFF) / MS_PER_DAY;

console.log('=== EB-1A PREDICTION VERIFICATION ===\n');
console.log('Parameters:');
console.log(`  Total supply: ${TOTAL_SUPPLY} visas/year`);
console.log(`  = base(${PARAMS.chinaBaseQuota}) + ROW(${PARAMS.spilloverROW}) + India(${PARAMS.spilloverIndia}) + EB45(${PARAMS.eb4eb5Spillover})`);
console.log(`  Family multiplier: ${PARAMS.familyMultiplier}`);
console.log(`  Main applicants/year: ${(TOTAL_SUPPLY / PARAMS.familyMultiplier).toFixed(0)}`);
console.log(`  Monthly main applicants: ${(TOTAL_SUPPLY / PARAMS.familyMultiplier / 12).toFixed(1)}`);
console.log(`  densityHigh: ${PARAMS.densityHigh}, densityPeak: ${PARAMS.densityPeak}`);
console.log(`\nCurrent state:`);
console.log(`  Cutoff: 2023-04-01, User PD: 2024-06-20`);
console.log(`  Gap: ${GAP_DAYS.toFixed(0)} days (${(GAP_DAYS/30).toFixed(1)} months)`);

// === TEST 1: Historical advance rate validation ===
console.log('\n--- TEST 1: Historical advance rates ---');
for (let i = 1; i < HISTORY.length; i++) {
  const [prevBulletin, prevCutoff] = HISTORY[i-1];
  const [currBulletin, currCutoff] = HISTORY[i];
  const calDays = (new Date(currBulletin) - new Date(prevBulletin)) / MS_PER_DAY;
  const cutoffDays = (new Date(currCutoff) - new Date(prevCutoff)) / MS_PER_DAY;
  const rate = calDays > 0 ? (cutoffDays / calDays * 365).toFixed(0) : 'N/A';
  console.log(`  ${prevBulletin} → ${currBulletin}: cutoff +${cutoffDays}d in ${calDays}d (annualized: ${rate} d/y)`);
}

// FY-level advance rates
console.log('\n  FY summary:');
const fyRanges = [
  ['FY24', '2023-10-15', '2024-10-15', '2022-02-15', '2022-11-08'],
  ['FY25', '2024-10-15', '2025-10-15', '2022-11-08', '2022-12-22'],
  ['FY26 (9mo)', '2025-10-15', '2026-06-15', '2022-12-22', '2023-04-01'],
];
for (const [label, bs, be, cs, ce] of fyRanges) {
  const calDays = (new Date(be) - new Date(bs)) / MS_PER_DAY;
  const cutDays = (new Date(ce) - new Date(cs)) / MS_PER_DAY;
  const annRate = cutDays / calDays * 365;
  const avgDensity = getPDDensity((new Date(cs).getTime() + new Date(ce).getTime()) / 2);
  const impliedSupply = annRate * avgDensity * PARAMS.familyMultiplier;
  console.log(`  ${label}: +${cutDays}d in ${calDays}d = ${annRate.toFixed(0)} d/y | zone density=${avgDensity.toFixed(1)} | implied supply=${impliedSupply.toFixed(0)}`);
}

// === TEST 2: Density at key points ===
console.log('\n--- TEST 2: Density at key PD dates ---');
const testDates = ['2022-01-01','2022-06-01','2023-01-01','2023-06-01','2024-01-01','2024-06-01','2024-09-19','2025-01-01','2025-06-01'];
for (const d of testDates) {
  const ts = new Date(d).getTime();
  console.log(`  PD ${d}: density = ${getPDDensity(ts).toFixed(2)}`);
}

// === TEST 3: Deterministic simulation (with MONTHLY_WEIGHTS) ===
const MONTHLY_WEIGHTS = [0.338, 0.183, 0.139, 0.110, 0.057, 0.037, 0.047, 0.017, 0.022, 0.026, 0.020, 0.004];
console.log('\n--- TEST 3: Deterministic simulation (monthly weights, no noise) ---');
let cutoff = CURRENT_CUTOFF;
const mainPerFY = TOTAL_SUPPLY / PARAMS.familyMultiplier;
for (let m = 0; m < 72; m++) {
  const md = new Date(2026, 4 + m, 15);
  const jsM = md.getMonth();
  const fyMonth = (jsM - 9 + 12) % 12;
  const monthlyMain = mainPerFY * MONTHLY_WEIGHTS[fyMonth];
  const density = getPDDensity(cutoff);
  let advance = monthlyMain / density;
  if (fyMonth === 0) advance += 30;
  cutoff += advance * MS_PER_DAY;
  if (m % 12 === 0 || cutoff >= USER_PD) {
    const d = new Date(cutoff);
    console.log(`  Month ${m.toString().padStart(2)} (FY-m${fyMonth}): cutoff=${d.toISOString().slice(0,10)}, density=${density.toFixed(1)}, advance=${advance.toFixed(1)}d`);
  }
  if (cutoff >= USER_PD) {
    console.log(`  >>> PD reached at month ${m} = ${(m/12).toFixed(2)} years from now`);
    const crossDate = new Date(TODAY + m * 30.44 * MS_PER_DAY);
    console.log(`  >>> Calendar date: ~${crossDate.toISOString().slice(0,7)}`);
    break;
  }
}

// === TEST 4: Monte Carlo simulation (with weights + Oct jump + retrogression) ===
console.log('\n--- TEST 4: Monte Carlo (3000 runs, weights+jump+retro) ---');
const results = [];
const N = 3000;
for (let sim = 0; sim < N; sim++) {
  let cutoff = CURRENT_CUTOFF;
  let currentFY = null, mainFY = 0;
  let crossed = false;

  for (let i = 0; i < 120; i++) {
    const md = new Date(2026, 4 + i, 15);
    const jsM = md.getMonth();
    const fy = jsM >= 9 ? md.getFullYear() + 1 : md.getFullYear();
    const fyMonth = (jsM - 9 + 12) % 12;

    if (fy !== currentFY) {
      currentFY = fy;
      const rowSpill = gaussian(PARAMS.spilloverROW, Math.max(60, Math.abs(PARAMS.spilloverROW) * 0.4));
      const indiaSpill = gaussian(PARAMS.spilloverIndia, Math.max(100, Math.abs(PARAMS.spilloverIndia) * 0.6));
      const eb45Spill = gaussian(PARAMS.eb4eb5Spillover, Math.max(30, PARAMS.eb4eb5Spillover * 0.4));
      const totalVisas = Math.max(500, PARAMS.chinaBaseQuota + rowSpill + indiaSpill + eb45Spill);
      mainFY = totalVisas / PARAMS.familyMultiplier;
    }

    const mv = mainFY * MONTHLY_WEIGHTS[fyMonth];
    const density = getPDDensity(cutoff);
    let advanceDays = mv / density;

    if (fyMonth === 0) {
      const isBigJump = Math.random() < 0.25;
      if (isBigJump) advanceDays += 30 * (2 + Math.random() * 2);
      else advanceDays += 30 * (0.7 + Math.random() * 0.6);
    }

    const noise = (Math.random() + Math.random() + Math.random() - 1.5) / 1.5;
    advanceDays *= (1 + noise * 0.3);

    if (jsM >= 6 && jsM <= 8 && Math.random() < 0.08) {
      advanceDays = -45 - Math.random() * 90;
    }

    cutoff += advanceDays * MS_PER_DAY;

    if (cutoff >= USER_PD) {
      results.push(i);
      crossed = true;
      break;
    }
  }
  if (!crossed) results.push(120);
}

results.sort((a, b) => a - b);
const pcts = [10, 25, 50, 75, 90];
console.log('  Percentile results:');
for (const p of pcts) {
  const idx = Math.floor(N * p / 100);
  const months = results[idx];
  const years = (months / 12).toFixed(2);
  const calDate = new Date(2026, 4 + months, 15);
  console.log(`    P${p.toString().padStart(2)}: ${months} months = ${years} years → ~${calDate.toISOString().slice(0,7)}`);
}

// === TEST 5: Cross-check with queue counting ===
console.log('\n--- TEST 5: Queue-counting cross-check ---');
// Estimate total queue between cutoff and PD by integrating density
let totalQueue = 0;
const stepDays = 30;
for (let dayOffset = 0; dayOffset < GAP_DAYS; dayOffset += stepDays) {
  const pdPoint = CURRENT_CUTOFF + dayOffset * MS_PER_DAY;
  const density = getPDDensity(pdPoint);
  const actualDays = Math.min(stepDays, GAP_DAYS - dayOffset);
  totalQueue += density * actualDays;
}
const yearsToClear = totalQueue / (TOTAL_SUPPLY / PARAMS.familyMultiplier);
console.log(`  Integrated queue (cutoff→PD): ${totalQueue.toFixed(0)} main applicants`);
console.log(`  Annual processing capacity: ${(TOTAL_SUPPLY / PARAMS.familyMultiplier).toFixed(0)} main/year`);
console.log(`  Simple estimate: ${yearsToClear.toFixed(2)} years`);

console.log('\n=== VERIFICATION COMPLETE ===');
console.log(`\nFinal answer: P50 = ~${(results[Math.floor(N*0.5)]/12).toFixed(1)} years from now`);
const p50Date = new Date(2026, 4 + results[Math.floor(N*0.5)], 15);
console.log(`Expected PD current date: ~${p50Date.toISOString().slice(0,7)}`);
