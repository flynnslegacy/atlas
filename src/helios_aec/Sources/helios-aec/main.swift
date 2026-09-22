//
// Capture et lecture audio avec le Voice Processing d'Apple.
// stdin  : [0x01][taille:4 BE][pcm]  joue le bloc
//          [0x02][0:4]               vide la file de lecture (barge-in)
// stdout : flux continu de PCM 16 kHz mono s16le capturé, écho retiré.

import AVFoundation
import Foundation

let frequence = 16000.0
let tailleBloc = 640

let moteur = AVAudioEngine()
let lecteur = AVAudioPlayerNode()
let fileLecture = DispatchQueue(label: "helios.lecture")

let format = AVAudioFormat(commonFormat: .pcmFormatFloat32,
                           sampleRate: frequence, channels: 1, interleaved: false)!

try moteur.inputNode.setVoiceProcessingEnabled(true)
try moteur.outputNode.setVoiceProcessingEnabled(true)
moteur.attach(lecteur)
moteur.connect(lecteur, to: moteur.mainMixerNode, format: format)

// --- capture : on écrit sur stdout au fil de l'eau ---
var tampon = Data()
moteur.inputNode.installTap(onBus: 0, bufferSize: 320,
                            format: moteur.inputNode.outputFormat(forBus: 0)) { buf, _ in
    guard let canal = buf.floatChannelData?[0] else { return }
    var pcm = Data(capacity: Int(buf.frameLength) * 2)
    for i in 0..<Int(buf.frameLength) {
        let v = Int16(max(-1.0, min(1.0, canal[i])) * 32767.0)
        withUnsafeBytes(of: v.littleEndian) { pcm.append(contentsOf: $0) }
    }
    tampon.append(pcm)
    while tampon.count >= tailleBloc {
        FileHandle.standardOutput.write(tampon.prefix(tailleBloc))
        tampon.removeFirst(tailleBloc)
    }
}

try moteur.start()
lecteur.play()

// --- commandes sur stdin ---
func lireExactement(_ n: Int) -> Data? {
    var reste = n, accu = Data()
    while reste > 0 {
        guard let bout = try? FileHandle.standardInput.read(upToCount: reste),
              !bout.isEmpty else { return nil }
        accu.append(bout); reste -= bout.count
    }
    return accu
}

func jouer(_ pcm: Data) {
    let cadre = AVAudioFrameCount(pcm.count / 2)
    guard let buf = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: cadre) else { return }
    buf.frameLength = cadre
    pcm.withUnsafeBytes { brut in
        let source = brut.bindMemory(to: Int16.self)
        for i in 0..<Int(cadre) {
            buf.floatChannelData![0][i] = Float(Int16(littleEndian: source[i])) / 32767.0
        }
    }
    lecteur.scheduleBuffer(buf, completionHandler: nil)
}

while true {
    guard let entete = lireExactement(5) else { break }
    let type = entete[entete.startIndex]
    let taille = entete.subdata(in: entete.startIndex+1..<entete.startIndex+5)
        .withUnsafeBytes { $0.load(as: UInt32.self).bigEndian }
    if type == 0x02 {
        fileLecture.sync { lecteur.stop(); lecteur.play() }   // vidage immédiat
        continue
    }
    guard let pcm = lireExactement(Int(taille)) else { break }
    jouer(pcm)
}
moteur.stop()
