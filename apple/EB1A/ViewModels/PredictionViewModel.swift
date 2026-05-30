import Foundation

/// Chart-ready rows (Date-typed for Swift Charts).
struct LineRow: Identifiable {
    let id = UUID()
    let x: Date
    let y: Date
}

struct BandRow: Identifiable {
    let id = UUID()
    let x: Date
    let low: Date   // pessimistic edge (p90)
    let high: Date  // optimistic edge (p10)
}

/// Wait-time row: x = priority date, y = wait in years.
struct WaitRow: Identifiable {
    let id = UUID()
    let pd: Date
    let wait: Double
}

private let kYear: Double = 365.25 * 86_400
private let kDay: Double = 86_400

/// Full result of one Monte Carlo run.
struct PredictionResult {
    let crossings: Crossings
    let bands: PercentileBands
    let currentCutoff: Date
    let yourPD: Date
    let today: Date
    let alreadyReached: Bool

    private static func dt(_ ts: TimeInterval) -> Date { Date(timeIntervalSince1970: ts) }
    private static let focusStart = EBDate.make(2023, 1, 1).timeIntervalSince1970

    // MARK: Trend rows (X = calendar date, Y = cutoff date)

    var historyATrend: [LineRow] {
        VisaData.historyA.filter { $0.x >= Self.focusStart }
            .map { LineRow(x: Self.dt($0.x), y: Self.dt($0.y)) }
    }
    var historyBTrend: [LineRow] {
        VisaData.historyB.filter { $0.x >= Self.focusStart }
            .map { LineRow(x: Self.dt($0.x), y: Self.dt($0.y)) }
    }
    var p50Line: [LineRow] { bands.p50.map { LineRow(x: Self.dt($0.x), y: Self.dt($0.y)) } }
    var p10Line: [LineRow] { bands.p10.map { LineRow(x: Self.dt($0.x), y: Self.dt($0.y)) } }
    var p90Line: [LineRow] { bands.p90.map { LineRow(x: Self.dt($0.x), y: Self.dt($0.y)) } }
    var trendBand: [BandRow] {
        zip(bands.p90, bands.p10).map { lo, hi in
            BandRow(x: Self.dt(lo.x), low: Self.dt(lo.y), high: Self.dt(hi.y))
        }
    }

    /// X domain: 2023-01 → min(last path month, p90 crossing + buffer). Mirrors web.
    var trendXDomain: ClosedRange<Date> {
        let todayTS = today.timeIntervalSince1970
        let capX: TimeInterval = crossings.p90.map { $0 + 1.2 * kYear }
            ?? crossings.p50.map { $0 + 3 * kYear }
            ?? (todayTS + 7 * kYear)
        let maxPathX = bands.p50.last?.x ?? (todayTS + 144 * 30 * kDay)
        let xMax = max(Self.focusStart + kYear, min(maxPathX, capX))
        return Self.dt(Self.focusStart)...Self.dt(xMax)
    }

    /// Y domain: clamp top to just above the user's PD / current cutoff. Mirrors web.
    var trendYDomain: ClosedRange<Date> {
        var ys: [Double] = [yourPD.timeIntervalSince1970]
        for p in VisaData.historyA where p.x >= Self.focusStart { ys.append(p.y) }
        for p in VisaData.historyB where p.x >= Self.focusStart { ys.append(p.y) }
        for p in bands.p50 { ys.append(p.y) }
        for p in bands.p10 { ys.append(p.y) }
        for p in bands.p90 { ys.append(p.y) }
        let cutoffNow = currentCutoff.timeIntervalSince1970
        var yMin = ys.min() ?? cutoffNow
        var yMax = min(ys.max() ?? cutoffNow, max(yourPD.timeIntervalSince1970, cutoffNow) + 240 * kDay)
        if yMax <= yMin { yMax = yMin + kYear }
        let pad = (yMax - yMin) * 0.05
        return Self.dt(yMin - pad)...Self.dt(yMax + pad)
    }

    // MARK: Wait-time rows (X = priority date, Y = wait years)

    private func toWait(_ line: [SimPoint]) -> [WaitRow] {
        let lastHistPD = VisaData.historyA.last?.y ?? 0
        return line.compactMap { p -> WaitRow? in
            let wait = (p.x - p.y) / kYear
            guard wait >= 0, p.y > lastHistPD else { return nil }
            return WaitRow(pd: Self.dt(p.y), wait: wait)
        }.sorted { $0.pd < $1.pd }
    }
    var historyWait: [WaitRow] {
        VisaData.historyA.compactMap { p -> WaitRow? in
            let wait = (p.x - p.y) / kYear
            return wait >= 0 ? WaitRow(pd: Self.dt(p.y), wait: wait) : nil
        }.sorted { $0.pd < $1.pd }
    }
    var p10Wait: [WaitRow] { toWait(bands.p10) }
    var p50Wait: [WaitRow] { toWait(bands.p50) }
    var p90Wait: [WaitRow] { toWait(bands.p90) }

    /// Wait chart X range: cutoff − 1yr → today + 1yr (fixed, mirrors web).
    var waitXDomain: ClosedRange<Date> {
        Self.dt(currentCutoff.timeIntervalSince1970 - kYear)...Self.dt(today.timeIntervalSince1970 + kYear)
    }

    /// Wait (years) for the median crossing, used for the marker dot.
    var medianWaitYears: Double? {
        guard let c = crossings.p50 else { return nil }
        let w = (c - yourPD.timeIntervalSince1970) / kYear
        return (w >= 0 && w < 20) ? w : nil
    }

    static func compute(pd: Date, params: ModelParams) -> PredictionResult {
        // Seed the RNG from the PD so the same input always yields the same
        // result (no jitter on re-run). Different PD -> different seed.
        let seed = UInt64(bitPattern: Int64(pd.timeIntervalSince1970.rounded()))
        var engine = SimulationEngine(
            params: params,
            cutoffStart: VisaData.currentCutoffA,
            yourPD: pd,
            today: Date(),
            generator: SplitMix64(seed: seed))

        let paths = engine.monteCarlo(500)
        let bands = engine.percentilePaths(paths)
        let crossings = engine.findCrossingsDistribution(paths)

        return PredictionResult(
            crossings: crossings,
            bands: bands,
            currentCutoff: VisaData.currentCutoffA,
            yourPD: pd,
            today: Date(),
            alreadyReached: VisaData.currentCutoffA >= pd)
    }
}

@MainActor
final class PredictionViewModel: ObservableObject {
    @Published var result: PredictionResult?
    @Published var isRunning = false
    @Published var preset: Preset = .realistic {
        didSet { if oldValue != preset, let pd = lastPD { run(pd: pd) } }
    }

    private var lastPD: Date?

    func run(pd: Date) {
        lastPD = pd
        isRunning = true
        let params = preset.params
        Task.detached(priority: .userInitiated) {
            let res = PredictionResult.compute(pd: pd, params: params)
            await MainActor.run {
                self.result = res
                self.isRunning = false
            }
        }
    }
}
