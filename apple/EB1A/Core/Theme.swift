import SwiftUI

/// Color palette mirrored 1:1 from the web app's CSS :root variables, so the
/// native app matches djzoom.github.io/EB1A.
extension Color {
    init(hex: UInt32) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: 1)
    }
}

enum Theme {
    // Surfaces
    static let bg = Color(hex: 0xF6F8F7)        // --bg
    static let card = Color.white               // --card
    static let border = Color(hex: 0xE3EBE6)    // --border

    // Text
    static let text = Color(hex: 0x0F1F19)      // --text
    static let text2 = Color(hex: 0x475A51)     // --text2
    static let text3 = Color(hex: 0x6B7D73)     // --text3

    // Primary (dark green — web's --blue)
    static let primary = Color(hex: 0x15734F)   // --blue
    static let primaryLight = Color(hex: 0xBFE0D0)
    static let primaryBg = Color(hex: 0xE7F4EE)

    static let orange = Color(hex: 0xDD8324)    // --orange
    static let green = Color(hex: 0x10B981)     // --green

    // Chart-specific (from drawForecastChart strokes)
    static let chartHistory = Color(hex: 0xF59E0B) // 表A 历史线 / PD 线
    static let chartP50 = Color(hex: 0x15734F)     // 中位
    static let chartP10 = Color(hex: 0x10B981)     // 快
    static let chartP90 = Color(hex: 0xEF4444)     // 慢
    static let chartHistB = Color(hex: 0x64748B)   // 表B 历史线
    static let chartToday = Color(hex: 0xCBD5E1)   // 今天线
}
