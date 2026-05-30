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

/// Full result of one Monte Carlo run.
struct PredictionResult {
    let crossings: Crossings
    let currentCutoff: Date
    let alreadyReached: Bool

    let historyA: [LineRow]
    let p50Line: [LineRow]
    let band: [BandRow]

    static func date(_ ts: TimeInterval) -> Date { Date(timeIntervalSince1970: ts) }

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

        let historyA = VisaData.historyA.map { LineRow(x: date($0.x), y: date($0.y)) }
        let p50Line = bands.p50.map { LineRow(x: date($0.x), y: date($0.y)) }

        // Pair p10 (high) and p90 (low) per month for the confidence band.
        let band = zip(bands.p90, bands.p10).map { lo, hi in
            BandRow(x: date(lo.x), low: date(lo.y), high: date(hi.y))
        }

        return PredictionResult(
            crossings: crossings,
            currentCutoff: VisaData.currentCutoffA,
            alreadyReached: VisaData.currentCutoffA >= pd,
            historyA: historyA,
            p50Line: p50Line,
            band: band)
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
