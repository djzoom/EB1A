import XCTest
@testable import EB1A

final class EngineTests: XCTestCase {

    private func engine(seed: UInt64 = 42, params: ModelParams = .realistic) -> SimulationEngine<SplitMix64> {
        SimulationEngine(
            params: params,
            cutoffStart: VisaData.currentCutoffA,
            yourPD: EBDate.make(2024, 6, 20),
            today: EBDate.make(2026, 5, 30),
            generator: SplitMix64(seed: seed))
    }

    // Density is deterministic (no RNG) — assert the piecewise-linear anchors.
    func testDensityAnchors() {
        let e = engine()
        let p = ModelParams.realistic
        XCTAssertEqual(e.getPDDensity(EBDate.make(2020, 1, 1).timeIntervalSince1970), 5, accuracy: 1e-6)   // d_low
        XCTAssertEqual(e.getPDDensity(EBDate.make(2022, 6, 1).timeIntervalSince1970), 10, accuracy: 1e-6)  // d_med start
        XCTAssertEqual(e.getPDDensity(EBDate.make(2023, 1, 1).timeIntervalSince1970), 10, accuracy: 1e-6)  // d_med end
        XCTAssertEqual(e.getPDDensity(EBDate.make(2024, 6, 1).timeIntervalSince1970), p.densityHigh, accuracy: 1e-6)
        XCTAssertEqual(e.getPDDensity(EBDate.make(2030, 1, 1).timeIntervalSince1970), p.densityPeak, accuracy: 1e-6)
    }

    // Density rises monotonically across the modeled range.
    func testDensityMonotonic() {
        let e = engine()
        let dates = [2020, 2021, 2022, 2023, 2024, 2025, 2026].map {
            EBDate.make($0, 6, 1).timeIntervalSince1970
        }
        let vals = dates.map { e.getPDDensity($0) }
        for i in 1..<vals.count {
            XCTAssertGreaterThanOrEqual(vals[i] + 1e-9, vals[i - 1])
        }
    }

    func testSimulatePathLength() {
        var e = engine()
        let path = e.simulate()
        XCTAssertEqual(path.count, 144)
        // Cutoff should generally advance over the horizon.
        XCTAssertGreaterThan(path.last!.y, path.first!.y)
    }

    // Percentile bands must be ordered p90 <= p50 <= p10 (cutoff value) per month.
    func testPercentileOrdering() {
        var e = engine()
        let paths = e.monteCarlo(200)
        let bands = e.percentilePaths(paths)
        XCTAssertEqual(bands.p50.count, 144)
        for m in 0..<bands.p50.count {
            XCTAssertLessThanOrEqual(bands.p90[m].y, bands.p50[m].y + 1e-6)
            XCTAssertLessThanOrEqual(bands.p50[m].y, bands.p10[m].y + 1e-6)
        }
    }

    // Crossing percentiles must be ordered p10 <= p50 <= p90 (calendar date).
    func testCrossingOrdering() {
        var e = engine()
        let paths = e.monteCarlo(500)
        let c = e.findCrossingsDistribution(paths)
        XCTAssertNotNil(c.p50)
        if let a = c.p10, let b = c.p50 { XCTAssertLessThanOrEqual(a, b) }
        if let a = c.p50, let b = c.p90 { XCTAssertLessThanOrEqual(a, b) }
    }

    // Reproducibility: same seed -> identical path.
    func testDeterministicWithSeed() {
        var a = engine(seed: 7)
        var b = engine(seed: 7)
        let pa = a.simulate()
        let pb = b.simulate()
        XCTAssertEqual(pa.count, pb.count)
        for i in 0..<pa.count {
            XCTAssertEqual(pa[i].y, pb[i].y, accuracy: 1e-6)
        }
    }
}
