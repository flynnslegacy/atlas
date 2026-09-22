//
// Capture et lecture audio avec le Voice Processing d'Apple.
// stdin  : [0x01][taille:4 BE][pcm]  joue le bloc
//          [0x02][0:4]               vide la file de lecture (barge-in)
// stdout : flux continu de PCM 16 kHz mono s16le capturé, écho retiré.

import AVFoundation
import Dispatch
import Foundation

let frequence = 16000.0
let tailleBloc = 640

let moteur = AVAudioEngine()
let lecteur = AVAudioPlayerNode()
let fileLecture = DispatchQueue(label: "helios.lecture")

let format = AVAudioFormat(commonFormat: .pcmFormatFloat32,
                           sampleRate: frequence, channels: 1, interleaved: false)!

do {
    try moteur.inputNode.setVoiceProcessingEnabled(true)
    try moteur.outputNode.setVoiceProcessingEnabled(true)
} catch {
    // Même cause possible qu'à `moteur.start()` plus bas (micro refusé) :
    // sans ce message, l'échec serait un crash Swift muet, sans rien sur
    // la sortie d'erreur pour guider quelqu'un qui lance le binaire à la main.
    FileHandle.standardError.write(
        "Impossible d'activer l'annulation d'écho (micro refusé, ou périphérique indisponible) : \(error)\n"
            .data(using: .utf8)!)
    exit(1)
}
moteur.attach(lecteur)
moteur.connect(lecteur, to: moteur.mainMixerNode, format: format)

// --- écriture sur stdout, hors du fil de rendu audio --------------------
//
// Le rappel du tap ci-dessous tourne sur le fil temps réel du moteur : une
// écriture bloquante là-dedans gèlerait aussi la lecture, puisque capture
// et lecture partagent le même AVAudioEngine. On accumule donc les blocs
// capturés dans un tampon borné sous verrou, et un fil dédié les écrit sur
// la sortie standard. Politique d'abandon si Python ne lit plus assez
// vite : on jette le bloc le PLUS ANCIEN pour garder une mémoire bornée —
// mieux vaut perdre un peu de passé que de laisser grossir indéfiniment un
// tampon qui de toute façon ne sera jamais consommé à temps.
final class TamponSortie {
    private var blocs: [Data] = []
    private let capaciteMax = 250  // ~5 s de capture à 20 ms/bloc
    private let verrou = NSLock()
    private let disponible = DispatchSemaphore(value: 0)

    func ajouter(_ bloc: Data) {
        verrou.lock()
        if blocs.count >= capaciteMax {
            // Plein : on remplace le plus ancien par le nouveau, le nombre
            // d'éléments réellement disponibles ne change pas — donc pas de
            // signal ici. Un signal sur cette branche désynchroniserait le
            // compte du sémaphore du contenu réel du tableau : après une
            // rafale d'abandons, `prendre()` finirait par franchir `wait()`
            // sur un tableau déjà vide et planter sur `removeFirst()`.
            blocs.removeFirst()
            blocs.append(bloc)
            verrou.unlock()
            return
        }
        blocs.append(bloc)
        verrou.unlock()
        disponible.signal()
    }

    func prendre() -> Data {
        disponible.wait()
        verrou.lock()
        let bloc = blocs.removeFirst()
        verrou.unlock()
        return bloc
    }
}

let tamponSortie = TamponSortie()

// Une écriture sur un tube dont personne ne lit lève désormais une erreur
// Swift normale au lieu de tuer le processus par SIGPIPE.
signal(SIGPIPE, SIG_IGN)

let filEcriture = Thread {
    while true {
        let bloc = tamponSortie.prendre()
        do {
            try FileHandle.standardOutput.write(contentsOf: bloc)
        } catch {
            // Python a fermé sa lecture (tube cassé) : ce n'est PAS un arrêt
            // volontaire, donc code de sortie non nul pour qu'un superviseur
            // distingue cette mort de celle d'un arrêt propre demandé.
            exit(1)
        }
    }
}
filEcriture.name = "helios.ecriture-stdout"
filEcriture.start()

// --- capture : rééchantillonnée vers 16 kHz mono, publiée par blocs -----
//
// Le tap ne peut recevoir que le format natif du nœud d'entrée — le format
// MATÉRIEL du micro, typiquement 48 kHz sur un Mac, jamais 16 kHz. Tout le
// reste du système (VAD, Whisper, `TAILLE_BLOC` côté Python) suppose du
// 16 kHz mono s16le. Le tap est donc la frontière carte son au sens de la
// spec : la conversion s'y fait, dans le corps du rappel, via un
// AVAudioConverter du format matériel vers `format` (16 kHz mono float32).
let formatMateriel = moteur.inputNode.outputFormat(forBus: 0)
guard let convertisseurCapture = AVAudioConverter(from: formatMateriel, to: format) else {
    FileHandle.standardError.write(
        "Impossible de créer le convertisseur 16 kHz pour la capture.\n".data(using: .utf8)!)
    exit(1)
}

var tampon = Data()
moteur.inputNode.installTap(onBus: 0, bufferSize: 320, format: formatMateriel) { buf, _ in
    let ratio = format.sampleRate / formatMateriel.sampleRate
    let capacite = AVAudioFrameCount(Double(buf.frameLength) * ratio) + 32
    guard let convertie = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: capacite) else { return }

    var epuise = false
    let statut = convertisseurCapture.convert(to: convertie, error: nil) { _, aFournir in
        if epuise {
            aFournir.pointee = .noDataNow
            return nil
        }
        epuise = true
        aFournir.pointee = .haveData
        return buf
    }
    guard statut != .error, let canal = convertie.floatChannelData?[0] else { return }

    var pcm = Data(capacity: Int(convertie.frameLength) * 2)
    for i in 0..<Int(convertie.frameLength) {
        let v = Int16(max(-1.0, min(1.0, canal[i])) * 32767.0)
        withUnsafeBytes(of: v.littleEndian) { pcm.append(contentsOf: $0) }
    }
    tampon.append(pcm)
    while tampon.count >= tailleBloc {
        tamponSortie.ajouter(Data(tampon.prefix(tailleBloc)))
        tampon.removeFirst(tailleBloc)
    }
}

do {
    try moteur.start()
} catch {
    // Cas réaliste sur un premier lancement : permission micro refusée.
    // Sans ce message, Python ne voit qu'un tube qui ne délivre jamais rien.
    FileHandle.standardError.write(
        "Impossible de démarrer le moteur audio (micro refusé, ou périphérique indisponible) : \(error)\n"
            .data(using: .utf8)!)
    exit(1)
}
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
