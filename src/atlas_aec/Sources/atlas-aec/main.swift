//
// Capture et lecture audio avec l'annulation d'écho d'Apple.
// stdin  : [0x01][taille:4 BE][pcm]  joue le bloc (PCM 16 kHz mono s16le)
//          [0x02][0:4]               vide la file de lecture (barge-in)
// stdout : flux continu de PCM 16 kHz mono s16le capturé, écho retiré.
// stderr : messages en français.
//
// L'unité VoiceProcessingIO est pilotée directement par AudioToolbox. Sous
// macOS 27, le mode voice processing d'AVAudioEngine échoue toujours (-10875
// à l'initialisation), alors que l'unité brute s'initialise et démarre avec le
// 16 kHz mono imposé des deux côtés (sonde S2, étapes H et I). L'unité
// convertit elle-même de et vers le matériel : plus de rééchantillonnage ici.
// Les files partagées avec le fil temps réel sont dans Tampons.swift.

import AudioToolbox
import AVFoundation  // seulement AVCaptureDevice, pour expliquer un micro refusé
import Foundation

let frequence = 16000
let echantillonsParBloc = 320  // 20 ms, soit 640 octets s16le par bloc de stdout
let tailleMaxTrame = 64 * 1024  // au-delà, le flux stdin est désynchronisé
let secondesAvantContrePression = 30

func journal(_ message: String) {
    try? FileHandle.standardError.write(contentsOf: Data((message + "\n").utf8))
}

/// Le statut, suivi de son code à quatre caractères quand il en a un ('nope', '!dev'…).
func decrire(_ statut: OSStatus) -> String {
    let octets = withUnsafeBytes(of: UInt32(bitPattern: statut).bigEndian, Array.init)
    guard octets.allSatisfy({ (0x20...0x7E).contains($0) }) else { return "\(statut)" }
    return "\(statut) ('\(String(decoding: octets, as: UTF8.self))')"
}

/// Étape de mise en route : un échec donne une ligne en français, puis une sortie non nulle.
func verifier(_ statut: OSStatus, _ etape: String) {
    guard statut != noErr else { return }
    journal("Impossible \(etape) : statut \(decrire(statut)).")
    exit(1)
}

// Une écriture sur un tube dont personne ne lit lève désormais une erreur
// Swift normale au lieu de tuer le processus par SIGPIPE.
signal(SIGPIPE, SIG_IGN)

// --- permission du micro ---------------------------------------------------
//
// Un micro refusé ne fait pas forcément échouer l'unité : macOS peut lui
// livrer du silence, et Python recevrait un flux muet sans explication.
switch AVCaptureDevice.authorizationStatus(for: .audio) {
case .denied, .restricted:
    journal("Accès au micro refusé par macOS : autorisez l'application qui lance Atlas "
        + "(le Terminal, par exemple) dans Réglages Système > Confidentialité et sécurité > Micro, "
        + "puis relancez.")
    exit(1)
case .notDetermined:
    journal("macOS va demander l'accès au micro : si la capture reste muette après l'avoir accordé, relancez.")
default:
    break
}

// --- l'unité d'annulation d'écho -------------------------------------------

func creerUnite() -> AudioUnit {
    var description = AudioComponentDescription(
        componentType: kAudioUnitType_Output,
        componentSubType: kAudioUnitSubType_VoiceProcessingIO,
        componentManufacturer: kAudioUnitManufacturer_Apple,
        componentFlags: 0, componentFlagsMask: 0)
    guard let composant = AudioComponentFindNext(nil, &description) else {
        journal("Impossible de trouver l'unité d'annulation d'écho d'Apple (VoiceProcessingIO).")
        exit(1)
    }
    var instance: AudioUnit?
    verifier(AudioComponentInstanceNew(composant, &instance), "de créer l'unité d'annulation d'écho")
    guard let unite = instance else {
        journal("Impossible de créer l'unité d'annulation d'écho : aucune instance rendue.")
        exit(1)
    }
    return unite
}

let unite = creerUnite()

func regler<T>(_ propriete: AudioUnitPropertyID, _ portee: AudioUnitScope,
               _ element: AudioUnitElement, _ valeur: T) -> OSStatus {
    withUnsafePointer(to: valeur) {
        AudioUnitSetProperty(unite, propriete, portee, element, $0, UInt32(MemoryLayout<T>.size))
    }
}

// --- mémoire partagée avec le fil temps réel, allouée avant le démarrage ----

let tamponSortie = TamponSortie(tailleBloc: echantillonsParBloc * 2)
let accumulateur = AccumulateurCapture(echantillonsParBloc: echantillonsParBloc, sortie: tamponSortie)
let fileLecture = FileLecture(seuil: secondesAvantContrePression * frequence,
                              trameMax: tailleMaxTrame / 2)

/// Où `AudioUnitRender` dépose le micro. Sa taille dépend de l'unité
/// initialisée : rempli plus bas, avant le démarrage, jamais dans un rappel.
struct TamponRendu {
    let liste: UnsafeMutablePointer<AudioBufferList>
    let echantillons: UnsafeMutablePointer<Float>
    let capacite: Int
}
let rendu = UnsafeMutablePointer<TamponRendu>.allocate(capacity: 1)

// --- rappels temps réel (fil de Core Audio) --------------------------------
//
// Ni allocation, ni tableau, ni entrée-sortie, ni attente : des copies dans
// de la mémoire préallouée, sous des verrous tenus quelques instructions.

/// Le micro a une tranche prête : rendue dans le tampon préalloué, puis
/// découpée en blocs de 20 ms pour le fil d'écriture.
let rappelCapture: AURenderCallback = { _, drapeaux, horodatage, _, nbTrames, _ in
    let r = rendu.pointee
    // Tranche plus grande que prévu : perdue, plutôt que rendue hors du tampon.
    guard Int(nbTrames) <= r.capacite else { return noErr }
    r.liste.pointee.mBuffers.mDataByteSize = nbTrames * 4
    r.liste.pointee.mBuffers.mData = UnsafeMutableRawPointer(r.echantillons)
    guard AudioUnitRender(unite, drapeaux, horodatage, 1, nbTrames, r.liste) == noErr,
          let donnees = r.liste.pointee.mBuffers.mData else { return noErr }
    let rendus = min(Int(nbTrames), Int(r.liste.pointee.mBuffers.mDataByteSize) / 4)
    accumulateur.ajouter(donnees.assumingMemoryBound(to: Float.self), rendus)
    return noErr
}

/// Le haut-parleur réclame une tranche : prise dans la file de lecture,
/// complétée par du silence. Format mono entrelacé : un seul tampon.
let rappelLecture: AURenderCallback = { _, _, _, _, nbTrames, ioData in
    guard let ioData, let sortie = ioData.pointee.mBuffers.mData else { return noErr }
    let n = min(Int(nbTrames), Int(ioData.pointee.mBuffers.mDataByteSize) / 4)
    fileLecture.remplir(sortie.assumingMemoryBound(to: Float.self), n)
    return noErr
}

// --- configuration : les appels de l'étape I de la sonde, plus les rappels ---

verifier(regler(kAudioOutputUnitProperty_EnableIO, kAudioUnitScope_Input, 1, UInt32(1)),
         "d'activer le micro de l'unité d'annulation d'écho")
// Même format des deux côtés application : ce que le micro nous rend (bus 1,
// portée sortie) et ce que nous envoyons au haut-parleur (bus 0, portée entrée).
let format16k = AudioStreamBasicDescription(
    mSampleRate: Float64(frequence), mFormatID: kAudioFormatLinearPCM,
    mFormatFlags: kAudioFormatFlagIsFloat | kAudioFormatFlagIsPacked,
    mBytesPerPacket: 4, mFramesPerPacket: 1, mBytesPerFrame: 4,
    mChannelsPerFrame: 1, mBitsPerChannel: 32, mReserved: 0)
verifier(regler(kAudioUnitProperty_StreamFormat, kAudioUnitScope_Output, 1, format16k),
         "d'imposer le 16 kHz mono au micro")
verifier(regler(kAudioUnitProperty_StreamFormat, kAudioUnitScope_Input, 0, format16k),
         "d'imposer le 16 kHz mono au haut-parleur")
verifier(regler(kAudioOutputUnitProperty_SetInputCallback, kAudioUnitScope_Global, 0,
                AURenderCallbackStruct(inputProc: rappelCapture, inputProcRefCon: nil)),
         "d'installer le rappel de capture")
verifier(regler(kAudioUnitProperty_SetRenderCallback, kAudioUnitScope_Input, 0,
                AURenderCallbackStruct(inputProc: rappelLecture, inputProcRefCon: nil)),
         "d'installer le rappel de lecture")

// Atlas garde l'unité ouverte en permanence, et le voice processing baisse par
// défaut le son des autres applications : la musique resterait plus basse tant
// qu'Atlas tourne. Atténuation réglée au minimum ; un échec n'arrête rien.
let attenuation = AUVoiceIOOtherAudioDuckingConfiguration(
    mEnableAdvancedDucking: false, mDuckingLevel: .min)
let statutAttenuation = regler(kAUVoiceIOProperty_OtherAudioDuckingConfiguration,
                               kAudioUnitScope_Global, 0, attenuation)
if statutAttenuation != noErr {
    journal("Avertissement : impossible de réduire l'atténuation des autres sons "
        + "(statut \(decrire(statutAttenuation))) ; la musique des autres applications "
        + "restera plus basse tant qu'Atlas tourne.")
}

verifier(AudioUnitInitialize(unite),
         "d'initialiser l'unité d'annulation d'écho (micro refusé, ou périphérique indisponible)")

/// La plus grande tranche que l'unité initialisée peut demander ; 4096 si elle ne le dit pas.
func tranchesMax() -> Int {
    var trames: UInt32 = 0
    var taille = UInt32(MemoryLayout<UInt32>.size)
    let statut = AudioUnitGetProperty(unite, kAudioUnitProperty_MaximumFramesPerSlice,
                                      kAudioUnitScope_Global, 0, &trames, &taille)
    return statut == noErr && trames > 0 ? min(Int(trames), 65536) : 4096
}

let capaciteRendu = tranchesMax()
let echantillonsRendus = UnsafeMutablePointer<Float>.allocate(capacity: capaciteRendu)
echantillonsRendus.initialize(repeating: 0, count: capaciteRendu)
let listeRendu = UnsafeMutablePointer<AudioBufferList>.allocate(capacity: 1)
listeRendu.initialize(to: AudioBufferList(
    mNumberBuffers: 1,
    mBuffers: AudioBuffer(mNumberChannels: 1, mDataByteSize: UInt32(capaciteRendu * 4),
                          mData: UnsafeMutableRawPointer(echantillonsRendus))))
rendu.initialize(to: TamponRendu(liste: listeRendu, echantillons: echantillonsRendus,
                                 capacite: capaciteRendu))

// --- fin du processus ------------------------------------------------------

let verrouFin = NSLock()

/// Arrête l'unité, l'efface, puis quitte. Le fil d'écriture (tube cassé) et le
/// fil principal (fin de stdin, flux désynchronisé) peuvent y arriver en même
/// temps ; appeler `exit` deux fois est un comportement indéfini, donc le
/// premier arrivé garde le verrou et l'autre attend ici la fin du processus.
func terminer(_ code: Int32) -> Never {
    verrouFin.lock()
    AudioOutputUnitStop(unite)
    AudioUnitUninitialize(unite)
    AudioComponentInstanceDispose(unite)
    exit(code)
}

// --- écriture sur stdout, hors du fil temps réel ---------------------------

let blocSortie = UnsafeMutableRawPointer.allocate(byteCount: echantillonsParBloc * 2, alignment: 16)
let filEcriture = Thread {
    while true {
        tamponSortie.prendre(dans: blocSortie)
        do {
            try FileHandle.standardOutput.write(
                contentsOf: UnsafeRawBufferPointer(start: blocSortie, count: echantillonsParBloc * 2))
        } catch {
            // Python a fermé sa lecture (tube cassé) : ce n'est PAS un arrêt
            // volontaire, donc code de sortie non nul pour qu'un superviseur
            // distingue cette mort de celle d'un arrêt propre demandé.
            terminer(1)
        }
    }
}
filEcriture.name = "atlas.ecriture-stdout"

verifier(AudioOutputUnitStart(unite),
         "de démarrer l'unité d'annulation d'écho (micro refusé, ou périphérique indisponible)")
filEcriture.start()
journal("Annulation d'écho active : micro et haut-parleur en 16 kHz mono, "
    + "tranches de \(capaciteRendu) trames au plus.")

// --- commandes sur stdin ----------------------------------------------------

let entete = UnsafeMutableRawPointer.allocate(byteCount: 5, alignment: 8)
let charge = UnsafeMutableRawPointer.allocate(byteCount: tailleMaxTrame, alignment: 16)

/// Lit exactement `n` octets de stdin. Rend false à la fin du flux, même au
/// milieu d'une trame : l'autre bout est parti, ce n'est pas une désynchronisation.
func lireExactement(_ destination: UnsafeMutableRawPointer, _ n: Int) -> Bool {
    var lus = 0
    while lus < n {
        let recus = read(STDIN_FILENO, destination + lus, n - lus)
        if recus > 0 {
            lus += recus
        } else if recus == 0 {
            return false
        } else {
            let erreur = errno
            if erreur == EINTR { continue }
            journal("Lecture de l'entrée standard impossible : \(String(cString: strerror(erreur))).")
            terminer(1)
        }
    }
    return true
}

func desynchronise(_ detail: String) -> Never {
    journal("Flux stdin désynchronisé (\(detail)) : arrêt.")
    terminer(1)
}

while lireExactement(entete, 5) {
    let type = entete.load(as: UInt8.self)
    let taille = (1...4).reduce(0) { $0 << 8 | Int(entete.load(fromByteOffset: $1, as: UInt8.self)) }
    switch type {
    case 0x01:
        guard taille > 0, taille % 2 == 0, taille <= tailleMaxTrame else {
            desynchronise("trame de lecture de \(taille) octets, attendu un nombre pair de 2 à \(tailleMaxTrame)")
        }
        guard lireExactement(charge, taille) else { terminer(0) }
        fileLecture.ajouter(UnsafeRawBufferPointer(start: charge, count: taille))
    case 0x02:
        // Vidage immédiat : rien de ce qui a été reçu avant ne sera jamais entendu.
        guard taille == 0 else { desynchronise("trame de vidage annonçant \(taille) octets") }
        fileLecture.vider()
    default:
        desynchronise(String(format: "type de trame inconnu 0x%02X", type))
    }
}
terminer(0)  // fin de stdin : Python a fermé le tube, arrêt propre
