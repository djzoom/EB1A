import Foundation

// MARK: - Result types

/// Percentile bands across the 144-month horizon (one SimPoint per month).
struct PercentileBands {
    var p10: [SimPoint] = []
    var p25: [SimPoint] = []
    var p50: [SimPoint] = []
    var p75: [SimPoint] = []
    var p90: [SimPoint] = []
}

/// Distribution of calendar dates at which the cutoff reaches the user's PD.
/// nil means "did not cross within 144 months" (rendered as 12年+).
struct Crossings {
    var p10: TimeInterval?
    var p25: TimeInterval?
    var p50: TimeInterval?
    var p75: TimeInterval?
    var p90: TimeInterval?
}

/// A seedable RNG so simulations can be reproduced in tests. SplitMix64.
struct SplitMix64: RandomNumberGenerator {
    private var state: UInt64
    init(seed: UInt64) { state = seed }
    mutating func next() -> UInt64 {
        state &+= 0x9E3779B97F4A7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58476D1CE4E5B9
        z = (z ^ (z >> 27)) &* 0x94D049BB133111EB
        return z ^ (z >> 31)
    }
}

// Density zone boundaries (getPDDensity in index.html).
private let kD2021 = EBDate.make(2021, 1, 1).timeIntervalSince1970
private let kD2022_06 = EBDate.make(2022, 6, 1).timeIntervalSince1970
private let kD2023_01 = EBDate.make(2023, 1, 1).timeIntervalSince1970
private let kD2024_06 = EBDate.make(2024, 6, 1).timeIntervalSince1970
private let kD2025 = EBDate.make(2025, 1, 1).timeIntervalSince1970

private let kSecPerDay: Double = 86_400

/// Monte Carlo cutoff-advance simulator. Faithful port of index.html
/// (lines 465–575). Generic over RNG for reproducibility.
struct SimulationEngine<RNG: RandomNumberGenerator> {
    let params: ModelParams
    let cutoffStart: Date
    let yourPD: Date
    let today: Date
    var generator: RNG

    private var random01: Double {
        mutating get { Double.random(in: 0..<1, using: &generator) }
    }

    // MARK: gaussian (Box-Muller)
    mutating func gaussian(_ mu: Double, _ sigma: Double) -> Double {
        let u1 = max(1e-12, random01) // guard log(0)
        let u2 = random01
        return mu + (-2 * log(u1)).squareRoot() * cos(2 * .pi * u2) * sigma
    }

    // MARK: getPDDensity — 5-segment piecewise linear, persons/day in queue
    func getPDDensity(_ pdDate: TimeInterval) -> Double {
        let dLow = 5.0, dMed = 10.0
        let dHigh = params.densityHigh, dPeak = params.densityPeak
        if pdDate < kD2021 { return dLow }
        if pdDate < kD2022_06 { return dLow + (dMed - dLow) * (pdDate - kD2021) / (kD2022_06 - kD2021) }
        if pdDate < kD2023_01 { return dMed }
        if pdDate < kD2024_06 { return dMed + (dHigh - dMed) * (pdDate - kD2023_01) / (kD2024_06 - kD2023_01) }
        if pdDate < kD2025 { return dHigh + (dPeak - dHigh) * (pdDate - kD2024_06) / (kD2025 - kD2024_06) }
        return dPeak
    }

    // MARK: simulate — one 144-month path
    mutating func simulate() -> [SimPoint] {
        let months = 144
        var path: [SimPoint] = []
        path.reserveCapacity(months)
        var cutoff = cutoffStart.timeIntervalSince1970
        let familyMultiplier = params.familyMultiplier

        let startComps = EBDate.utc.dateComponents([.year, .month], from: today)
        let base = EBDate.make(startComps.year!, startComps.month!, 15)

        var currentFY: Int? = nil
        var mainPerFY: Double = 0

        // Path-level "regime" factors (constant for the whole path) capture
        // structural uncertainty so long paths don't all converge to the mean.
        let regimeSupply = max(0.4, gaussian(1.0, 0.30))
        let regimeDensity = max(0.6, gaussian(1.0, 0.15))

        for i in 0..<months {
            let monthDate = EBDate.utc.date(byAdding: .month, value: i, to: base)!
            let comps = EBDate.utc.dateComponents([.year, .month], from: monthDate)
            let jsMonth = comps.month! - 1            // 0-based, Jan = 0
            let year = comps.year!
            let fyYear = jsMonth >= 9 ? year + 1 : year
            let fyMonth = ((jsMonth - 9) % 12 + 12) % 12

            if fyYear != currentFY {
                currentFY = fyYear
                let rowSpill = gaussian(params.spilloverROW, max(60, abs(params.spilloverROW) * 0.4))
                let indiaSpill = gaussian(params.spilloverIndia, max(100, abs(params.spilloverIndia) * 0.6))
                let eb45Spill = gaussian(params.eb4eb5Spillover, max(30, params.eb4eb5Spillover * 0.4))
                let totalVisas = max(500, (params.chinaBaseQuota + rowSpill + indiaSpill + eb45Spill) * regimeSupply)
                mainPerFY = totalVisas / familyMultiplier
            }

            let monthlyMain = mainPerFY * VisaData.monthlyWeights[fyMonth]
            let density = getPDDensity(cutoff) * regimeDensity
            var advanceDays = monthlyMain / density

            // October "fresh fiscal year" jump.
            if fyMonth == 0 {
                let isBigJump = random01 < 0.25
                if isBigJump { advanceDays += 30 * (2 + random01 * 2) }
                else { advanceDays += 30 * (0.7 + random01 * 0.6) }
            }

            // ±30% stochastic noise (sum of 3 uniforms ≈ triangular).
            let noise = (random01 + random01 + random01 - 1.5) / 1.5
            advanceDays *= (1 + noise * 0.3)

            cutoff += advanceDays * kSecPerDay
            path.append(SimPoint(x: monthDate.timeIntervalSince1970, y: cutoff))
            // No early termination: running every path full-length avoids
            // survivorship bias in the percentile bands.
        }
        return path
    }

    // MARK: monteCarlo
    mutating func monteCarlo(_ n: Int) -> [[SimPoint]] {
        var paths: [[SimPoint]] = []
        paths.reserveCapacity(n)
        for _ in 0..<n { paths.append(simulate()) }
        return paths
    }

    // MARK: percentilePaths — per-month bands.
    // p10 = optimistic (highest cutoff → 90th value); p90 = pessimistic (10th value).
    func percentilePaths(_ allPaths: [[SimPoint]]) -> PercentileBands {
        var maxLen = 0
        for p in allPaths { maxLen = max(maxLen, p.count) }
        var bands = PercentileBands()
        for m in 0..<maxLen {
            var values: [Double] = []
            var refX: TimeInterval? = nil
            for p in allPaths where m < p.count {
                values.append(p[m].y)
                if refX == nil { refX = p[m].x }
            }
            if values.isEmpty { break }
            values.sort()
            let n = values.count
            let rx = refX!
            bands.p10.append(SimPoint(x: rx, y: values[Int(Double(n) * 0.9)]))
            bands.p25.append(SimPoint(x: rx, y: values[Int(Double(n) * 0.75)]))
            bands.p50.append(SimPoint(x: rx, y: values[Int(Double(n) * 0.5)]))
            bands.p75.append(SimPoint(x: rx, y: values[Int(Double(n) * 0.25)]))
            bands.p90.append(SimPoint(x: rx, y: values[Int(Double(n) * 0.1)]))
        }
        return bands
    }

    // MARK: crossing detection
    func findCrossingDate(_ path: [SimPoint]) -> TimeInterval? {
        let pd = yourPD.timeIntervalSince1970
        for pt in path where pt.y >= pd { return pt.x }
        return nil
    }

    func findCrossingsDistribution(_ allPaths: [[SimPoint]]) -> Crossings {
        let total = allPaths.count
        var crossings: [TimeInterval] = []
        for p in allPaths { if let c = findCrossingDate(p) { crossings.append(c) } }
        crossings.sort()
        let n = crossings.count
        func pct(_ p: Double) -> TimeInterval? {
            let idx = Int(p * Double(total))
            return idx >= n ? nil : crossings[idx]
        }
        return Crossings(p10: pct(0.10), p25: pct(0.25), p50: pct(0.50), p75: pct(0.75), p90: pct(0.90))
    }
}
