// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "atlas-aec",
    platforms: [.macOS(.v14)],
    targets: [.executableTarget(name: "atlas-aec")]
)
