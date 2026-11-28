// mac_record.swift - record the Mac's default audio input to a mono 32-bit float WAV, every sample kept.
//
// usage: swiftc -O tools/mac_record.swift -o build/mac_record && build/mac_record SECONDS OUT.wav
//
// Why: ffmpeg's AVFoundation capture drops buffers on this Mac (12 s asked, 10-11 s written; a frame of the Probe's
// tones loses bits in the middle). AVAudioEngine's input tap hands over every buffer; this writes them all, at the
// input's own rate, and prints how many samples it got against how many the time asked for.
import AVFoundation
import Foundation

let args = CommandLine.arguments
guard args.count == 3, let seconds = Double(args[1]) else {
    FileHandle.standardError.write("usage: mac_record SECONDS OUT.wav\n".data(using: .utf8)!)
    exit(2)
}
let engine = AVAudioEngine()
let input = engine.inputNode
let fmt = input.outputFormat(forBus: 0)
let rate = fmt.sampleRate
let want = Int(seconds * rate)
var samples = [Float]()
samples.reserveCapacity(want + 8192)
let lock = NSLock()
input.installTap(onBus: 0, bufferSize: 4096, format: fmt) { buf, _ in
    guard let ch = buf.floatChannelData else { return }
    let n = Int(buf.frameLength)
    lock.lock()
    samples.append(contentsOf: UnsafeBufferPointer(start: ch[0], count: n))
    lock.unlock()
}
do { try engine.start() } catch {
    FileHandle.standardError.write("mac_record: cannot start the input: \(error)\n".data(using: .utf8)!)
    exit(1)
}
while true {
    lock.lock(); let have = samples.count; lock.unlock()
    if have >= want { break }
    Thread.sleep(forTimeInterval: 0.05)
}
engine.stop()
input.removeTap(onBus: 0)
let out = Array(samples.prefix(want))

// WAV: IEEE float, mono
var d = Data()
func u32(_ v: UInt32) { var x = v.littleEndian; d.append(Data(bytes: &x, count: 4)) }
func u16(_ v: UInt16) { var x = v.littleEndian; d.append(Data(bytes: &x, count: 2)) }
let bytes = UInt32(out.count * 4)
d.append("RIFF".data(using: .ascii)!); u32(36 + bytes); d.append("WAVE".data(using: .ascii)!)
d.append("fmt ".data(using: .ascii)!); u32(16); u16(3); u16(1); u32(UInt32(rate)); u32(UInt32(rate) * 4); u16(4); u16(32)
d.append("data".data(using: .ascii)!); u32(bytes)
out.withUnsafeBufferPointer { d.append(Data(buffer: $0)) }
do { try d.write(to: URL(fileURLWithPath: args[2])) } catch {
    FileHandle.standardError.write("mac_record: cannot write \(args[2]): \(error)\n".data(using: .utf8)!)
    exit(1)
}
print("mac_record: \(out.count) samples at \(Int(rate)) Hz (\(String(format: "%.3f", Double(out.count) / rate)) s)")
