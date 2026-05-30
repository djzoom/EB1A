import Foundation

/// The 7 tunable model parameters. Mirrors PARAM_META / PRESETS in index.html.
struct ModelParams: Equatable {
    var chinaBaseQuota: Double   // 法定基础配额 (固定 2803)
    var spilloverROW: Double     // 其他国家溢出
    var spilloverIndia: Double   // 印度影响 (可为负)
    var eb4eb5Spillover: Double  // EB-4/5 跨类溢出
    var familyMultiplier: Double // 家庭系数 (人/主申)
    var densityHigh: Double      // 排队密度 2023–2024 (人/天)
    var densityPeak: Double      // 排队密度 2024+ (人/天)

    static let realistic = ModelParams(
        chinaBaseQuota: 2803, spilloverROW: 500, spilloverIndia: 0,
        eb4eb5Spillover: 200, familyMultiplier: 1.9, densityHigh: 8, densityPeak: 9)

    static let optimistic = ModelParams(
        chinaBaseQuota: 2803, spilloverROW: 1200, spilloverIndia: 600,
        eb4eb5Spillover: 400, familyMultiplier: 1.8, densityHigh: 10, densityPeak: 12)

    static let pessimistic = ModelParams(
        chinaBaseQuota: 2803, spilloverROW: 100, spilloverIndia: -500,
        eb4eb5Spillover: 100, familyMultiplier: 2.0, densityHigh: 15, densityPeak: 20)
}

enum Preset: String, CaseIterable, Identifiable {
    case realistic, optimistic, pessimistic
    var id: String { rawValue }

    var label: String {
        switch self {
        case .realistic: return "现实"
        case .optimistic: return "乐观"
        case .pessimistic: return "悲观"
        }
    }

    var params: ModelParams {
        switch self {
        case .realistic: return .realistic
        case .optimistic: return .optimistic
        case .pessimistic: return .pessimistic
        }
    }
}
