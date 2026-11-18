import AppKit
import CoreGraphics

private let home = FileManager.default.homeDirectoryForCurrentUser
private let applicationID = "com.t3tools.t3code"
private let size = NSSize(width: 240, height: 126)
private let ink = NSColor(srgbRed: 0.15, green: 0.26, blue: 0.17, alpha: 1)
private let lcd = NSColor(srgbRed: 0.53, green: 0.73, blue: 0.49, alpha: 1)
typealias Object = [String: Any]

private func object(_ path: URL) -> Object? {
    guard let data = try? Data(contentsOf: path) else { return nil }
    return (try? JSONSerialization.jsonObject(with: data)) as? Object
}

private func isoDate(_ value: Any?) -> Date? {
    guard let text = value as? String else { return nil }
    let parser = ISO8601DateFormatter()
    parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let result = parser.date(from: text) { return result }
    parser.formatOptions = [.withInternetDateTime]
    return parser.date(from: text)
}

struct Limit {
    let id: String
    let name: String
    let used: Double
    let reset: Date?
}

struct Provider {
    let id: String
    let name: String
    let windows: [Limit]
    let status: String
    let checked: Date?
}

private func providers() -> [Provider]? {
    let root = ProcessInfo.processInfo.environment["T3CODE_HOME"].flatMap {
        $0.isEmpty ? nil : URL(fileURLWithPath: $0, isDirectory: true)
    } ?? home.appendingPathComponent(".t3")
    guard let settings = object(root.appendingPathComponent("userdata/settings.json")) else { return nil }
    let configured = settings["providerInstances"] as? [String: Object] ?? [:]
    let dir = root.appendingPathComponent("caches")
    var entries: [String: Object] = [:]
    for file in (try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)) ?? [] where file.pathExtension == "json" {
        if let data = object(file), let id = data["instanceId"] as? String,
           configured[id] != nil || data["enabled"] as? Bool == true {
            entries[id] = data
        }
    }
    let ids = Set(configured.keys).union(entries.keys)
    return ids.map { id in
        let data = entries[id] ?? [:]
        let config = configured[id] ?? [:]
        let name = config["displayName"] as? String ?? data["displayName"] as? String ?? id
        let limits = data["usageLimits"] as? Object ?? [:]
        let enabled = (config["enabled"] as? Bool ?? data["enabled"] as? Bool) != false
        let windows: [Limit] = (limits["windows"] as? [Object] ?? []).compactMap { w in
            guard let value = w["usedPercent"] as? Double, value.isFinite, (0...100).contains(value),
                  let key = w["id"] as? String else { return nil }
            return Limit(id: key, name: w["label"] as? String ?? key, used: value, reset: isoDate(w["resetsAt"]))
        }
        let status: String
        if !enabled { status = "Provider disabled" }
        else if (data["auth"] as? Object)?["status"] as? String == "unauthenticated" { status = "Sign-in required" }
        else if limits["zeroSpendCap"] as? Bool == true { status = "Zero spend cap" }
        else if (limits["unavailable"] as? Object)?["reason"] as? String == "probeFailed" { status = "Usage check failed" }
        else if (limits["unavailable"] as? Object)?["reason"] as? String == "unsupported" { status = "Quota not supported" }
        else if limits["unavailable"] != nil { status = "Usage unavailable" }
        else if data.isEmpty { status = "Awaiting T3 data" }
        else { status = "Quota not reported" }
        return Provider(id: id, name: name, windows: status == "Quota not reported" ? windows : [], status: status, checked: isoDate(limits["checkedAt"]))
    }.sorted { a, b in
        if (a.id == "codex") != (b.id == "codex") { return a.id == "codex" }
        let order = a.name.localizedCaseInsensitiveCompare(b.name)
        return order == .orderedSame ? a.id < b.id : order == .orderedAscending
    }
}

private func color(_ hex: Int) -> NSColor {
    return NSColor(srgbRed: CGFloat((hex >> 16) & 255) / 255, green: CGFloat((hex >> 8) & 255) / 255,
                   blue: CGFloat(hex & 255) / 255, alpha: 1)
}

private func box(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat, _ shade: NSColor) {
    shade.setFill()
    NSBezierPath(rect: NSRect(x: x, y: y, width: w, height: h)).fill()
}

private func poly(_ points: [(CGFloat, CGFloat)], _ shade: NSColor) {
    let path = NSBezierPath()
    for (index, p) in points.enumerated() {
        if index == 0 { path.move(to: NSPoint(x: p.0, y: p.1)) }
        else { path.line(to: NSPoint(x: p.0, y: p.1)) }
    }
    path.close()
    shade.setFill()
    path.fill()
}

private func text(_ string: String, _ rect: NSRect, _ fontSize: CGFloat, weight: NSFont.Weight = .medium,
                  alignment: NSTextAlignment = .left, shade: NSColor = ink) {
    let style = NSMutableParagraphStyle()
    style.alignment = alignment
    style.lineBreakMode = .byTruncatingTail
    (string as NSString).draw(in: rect, withAttributes: [
        .font: NSFont.monospacedSystemFont(ofSize: fontSize, weight: weight),
        .foregroundColor: shade, .paragraphStyle: style
    ])
}

private final class Rocker: NSButton {
    let upper: Bool
    init(upper: Bool, target: AnyObject, action: Selector) {
        self.upper = upper
        super.init(frame: NSRect(x: 207, y: upper ? 18 : 63, width: 30, height: 44))
        self.target = target
        self.action = action
        isBordered = false
        title = ""
        let label = upper ? "Previous provider" : "Next provider"
        toolTip = label
        setAccessibilityLabel(label)
    }
    required init?(coder: NSCoder) { fatalError() }
    override var isFlipped: Bool { true }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func draw(_ dirtyRect: NSRect) {
        let face = isHighlighted ? 0xC73142 : 0xEF4753
        let outline: [(CGFloat, CGFloat)] = upper ? [(0,0),(17,0),(26,4),(30,12),(30,44),(0,44)] :
            [(0,0),(30,0),(30,32),(26,40),(17,44),(0,44)]
        poly(outline, color(0x241F29))
        poly(upper ? [(3,3),(16,3),(23,6),(27,13),(27,41),(3,41)] :
                [(3,3),(27,3),(27,31),(23,38),(16,41),(3,41)], color(face))
        box(3,3,upper ? 13 : 24,2,color(0xFF8A88))
        let tip: CGFloat = upper ? 18 : 26
        let base: CGFloat = upper ? 25 : 19
        poly([(9,base),(15,tip),(21,base)],color(0x852938))
    }
}

private final class Face: NSButton {
    var provider: Provider?
    var limit: Limit?
    var position = ""
    var windowIndex = 0
    override var isFlipped: Bool { true }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    func update(_ item: Provider?, limitIndex: Int, position: String) {
        provider = item
        windowIndex = limitIndex
        limit = item?.windows.indices.contains(limitIndex) == true ? item?.windows[limitIndex] : nil
        self.position = position
        let quotaText = remainingPercent == nil ? "Quota remaining unknown" : "\(percentText) remaining"
        let desc = [item?.name, limit?.name, quotaText, resetText].compactMap { $0 }.joined(separator: ", ")
        toolTip = desc + ((item?.windows.count ?? 0) > 1 ? "\nClick the LCD for the next quota window." : "")
        setAccessibilityLabel(desc)
        setAccessibilityHelp((item?.windows.count ?? 0) > 1 ? "Click the LCD for the next quota window." : nil)
        needsDisplay = true
    }

    var expired: Bool { limit?.reset.map { $0 <= Date() } ?? false }
    var remainingPercent: Double? {
        guard let limit, !expired else { return nil }
        return 100 - limit.used
    }
    var percentText: String {
        guard let value = remainingPercent else { return "—" }
        return "\(Int(value.rounded()))%"
    }
    var resetText: String {
        guard let limit = limit else { return provider?.status ?? "Awaiting T3 data" }
        if expired { return "Awaiting reset update" }
        guard let date = limit.reset else { return "Reset not reported" }
        let format = DateFormatter()
        format.locale = .autoupdatingCurrent
        format.timeZone = .autoupdatingCurrent
        format.setLocalizedDateFormatFromTemplate(Calendar.autoupdatingCurrent.isDateInToday(date) ? "jm" : "MMMdjm")
        return "Reset " + format.string(from: date)
    }

    // Seven-segment numerals drawn on integer coordinates like the reference LCD.
    func number(_ n: Int, x: CGFloat, y: CGFloat) {
        let masks = [0x3f,0x06,0x5b,0x4f,0x66,0x6d,0x7d,0x07,0x7f,0x6f]
        let segments: [(CGFloat, CGFloat, CGFloat, CGFloat)] = [(2,0,12,3),(13,2,3,10),(13,14,3,10),(2,23,12,3),(0,14,3,10),(0,2,3,10),(2,12,12,3)]
        for (i,s) in segments.enumerated() where masks[n] & (1 << i) != 0 {
            box(x+s.0,y+s.1,s.2,s.3,ink)
        }
    }

    override func draw(_ dirtyRect: NSRect) {
        box(0,0,bounds.width,bounds.height,lcd)
        box(0,0,bounds.width,2,color(0x759A68))
        text(provider?.name ?? "Providers",NSRect(x:7,y:5,width:141,height:17),12,weight:.bold)
        text(position,NSRect(x:149,y:6,width:34,height:15),10,alignment:.right)
        box(7,24,175,1,color(0x6D9364))
        let nums = percentText.compactMap { $0.wholeNumberValue }
        if nums.isEmpty { box(11,43,25,3,ink) }
        for (i,n) in nums.enumerated() { number(n,x:9+CGFloat(i)*19,y:32) }
        if !nums.isEmpty {
            text("%",NSRect(x:11+CGFloat(nums.count)*19,y:39,width:16,height:18),14,weight:.bold)
        }
        text("LEFT",NSRect(x:109,y:29,width:68,height:14),9,weight:.bold)
        if let remaining = remainingPercent {
            let filled = Int(ceil(remaining * 12 / 100))
            for i in 0..<12 {
                box(109+CGFloat(i)*6,46,4,9,i < filled ? ink : color(0x749D6B))
            }
        }
        if let l = limit {
            let count = provider?.windows.count ?? 1
            let pager = count > 1 ? "\(windowIndex+1)/\(count) ›" : ""
            text(l.name,NSRect(x:7,y:63,width:pager.isEmpty ? 173 : 142,height:15),10,weight:.semibold)
            text(pager,NSRect(x:148,y:63,width:35,height:14),9,alignment:.right)
        } else {
            text("No quota window",NSRect(x:7,y:63,width:173,height:15),10)
        }
        text(resetText,NSRect(x:7,y:81,width:179,height:16),11,weight:.bold)
        if let checked = provider?.checked, limit != nil, Date().timeIntervalSince(checked)>1800 {
            text("OLD", NSRect(x:143,y:29,width:37,height:14),9,alignment:.right)
        }
    }
}

private final class Housing: NSView {
    override var isFlipped: Bool { true }
    override func draw(_ dirtyRect: NSRect) {
        poly([(30,0),(173,0),(180,6),(218,6),(232,18),(232,104),(221,119),(180,119),(173,126),(30,126),(25,120),(8,120),(1,112),(1,14),(9,6),(25,6)],color(0x252834))
        box(33,1,136,6,color(0x454451))
        box(33,119,136,6,color(0x383B46))
        poly([(9,9),(218,9),(229,20),(229,102),(219,116),(9,116),(4,110),(4,15)],color(0xA6A9B2))
        poly([(11,10),(215,10),(224,17),(205,17),(205,109),(9,109),(6,106),(6,16)],color(0xE3E2DE))
        box(10,12,192,102,color(0x343B3E))
        box(12,14,188,98,color(0xA4B99A))
        box(7,112,4,2,color(0xF7F5EF))
    }
}

private final class Monitor: NSObject {
    let panel = NSPanel(contentRect:NSRect(origin:.zero,size:size),styleMask:[.borderless,.nonactivatingPanel],
                        backing:.buffered,defer:false)
    let face = Face(frame:NSRect(x:13,y:15,width:186,height:96))
    var items: [Provider] = []
    var selectedID = UserDefaults.standard.string(forKey:"selectedProvider") ?? "codex"
    var windowID: String?
    var lastRead = Date.distantPast
    var timer: Timer?

    override init() {
        super.init()
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.canJoinAllSpaces,.fullScreenAuxiliary,.ignoresCycle]
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.isReleasedWhenClosed = false
        panel.title = "Sinnoh Usage Monitor"
        let housing = Housing(frame:NSRect(origin:.zero,size:size))
        panel.contentView = housing
        face.isBordered = false
        face.title = ""
        face.target = self
        face.action = #selector(nextWindow)
        housing.addSubview(face)
        housing.addSubview(Rocker(upper:true,target:self,action:#selector(previousProvider)))
        housing.addSubview(Rocker(upper:false,target:self,action:#selector(nextProvider)))
    }

    var index: Int? { items.firstIndex { $0.id == selectedID } }
    func refresh() {
        if let snapshot = providers() { items = snapshot }
        if index == nil, let first = items.first { selectedID = first.id; windowID = nil }
        display()
    }
    func display() {
        guard let i = index else { face.update(nil,limitIndex:0,position:""); return }
        let item = items[i]
        let preferred = item.windows.indices.filter { (item.windows[$0].reset ?? .distantFuture) > Date() }
            .max { item.windows[$0].used < item.windows[$1].used }
        let w = item.windows.firstIndex { $0.id == windowID } ?? preferred ?? 0
        face.update(item,limitIndex:w,position:"\(i+1)/\(items.count)")
    }
    func step(_ delta: Int) {
        guard let i = index else { return }
        selectedID = items[(i+delta+items.count)%items.count].id
        windowID = nil
        if !CommandLine.arguments.contains("--check") { UserDefaults.standard.set(selectedID,forKey:"selectedProvider") }
        display()
    }
    @objc func previousProvider() { step(-1) }
    @objc func nextProvider() { step(1) }
    @objc func nextWindow() {
        guard let i = index else { return }
        let windows = items[i].windows
        guard windows.count>1 else { return }
        windowID = windows[(face.windowIndex+1)%windows.count].id
        display()
    }

    func follow() {
        guard let app = NSWorkspace.shared.frontmostApplication, app.bundleIdentifier == applicationID,
              let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly,.excludeDesktopElements],kCGNullWindowID) as? [Object],
              let primary = NSScreen.screens.first else { if panel.isVisible { panel.orderOut(nil) }; return }
        let window = list.lazy.compactMap { record -> CGRect? in
            guard record[kCGWindowOwnerPID as String] as? pid_t == app.processIdentifier,
                  record[kCGWindowLayer as String] as? Int == 0,
                  let raw = record[kCGWindowBounds as String] as? NSDictionary,
                  let r = CGRect(dictionaryRepresentation:raw), r.width>=410, r.height>=300 else { return nil }
            return r
        }.first
        guard let r = window else { panel.orderOut(nil); return }
        // CG uses a top-left origin on the primary display; AppKit uses bottom-left.
        let origin = NSPoint(x:r.maxX-size.width-14,y:primary.frame.maxY-r.maxY+90)
        if panel.frame.origin != origin { panel.setFrameOrigin(origin) }
        if !panel.isVisible || Date().timeIntervalSince(lastRead)>=10 {
            refresh()
            lastRead = Date()
        }
        if !panel.isVisible { panel.orderFrontRegardless() }
    }
    func start() {
        follow()
        timer = Timer.scheduledTimer(withTimeInterval:0.6,repeats:true) { [weak self] _ in self?.follow() }
        timer?.tolerance = 0.12
        NSWorkspace.shared.notificationCenter.addObserver(self,selector:#selector(activated),
            name:NSWorkspace.didActivateApplicationNotification,object:nil)
    }
    @objc private func activated() { follow() }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
private let monitor = Monitor()
if CommandLine.arguments.contains("--check") {
    monitor.refresh()
    let original = monitor.selectedID
    let next = monitor.panel.contentView!.subviews.compactMap { $0 as? Rocker }.first { !$0.upper }!
    let prev = monitor.panel.contentView!.subviews.compactMap { $0 as? Rocker }.first { $0.upper }!
    var visited = Set<String>()
    for _ in monitor.items {
        precondition(visited.insert(monitor.selectedID).inserted)
        let item = monitor.items[monitor.index!]
        var seen = Set<String>()
        for _ in item.windows {
            precondition(seen.insert(monitor.face.limit!.id).inserted)
            monitor.face.performClick(nil)
        }
        print(item.name, "|", monitor.face.percentText, "|", monitor.face.resetText)
        next.performClick(nil)
    }
    precondition(monitor.selectedID == original && visited.count == monitor.items.count)
    prev.performClick(nil); next.performClick(nil)
    precondition(monitor.selectedID == original)
    if let p = CommandLine.arguments.firstIndex(of:"--png"), p+1<CommandLine.arguments.count {
        let housing = monitor.panel.contentView!
        let bitmap = housing.bitmapImageRepForCachingDisplay(in:housing.bounds)!
        housing.cacheDisplay(in:housing.bounds,to:bitmap)
        try bitmap.representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:CommandLine.arguments[p+1]))
    }
} else {
    monitor.start()
    app.run()
}
