// Files à capacité fixe partagées avec le fil temps réel de Core Audio.
//
// Règles communes, pour que les rappels temps réel restent sûrs :
// - toute la mémoire est allouée ET mise à zéro à la construction, avant le
//   démarrage de l'unité : aucune allocation, ni premier accès à une page
//   neuve, dans un rappel ;
// - aucun tableau Swift, donc ni croissance ni `removeFirst` ;
// - l'état mutable vit derrière des pointeurs, jamais dans des propriétés
//   `var` : Swift contrôle dynamiquement l'exclusivité des accès aux
//   propriétés de classe, et ce contrôle alloue, au premier accès d'un fil,
//   une structure propre à ce fil ;
// - verrous os_unfair_lock, tenus le temps d'une copie courte et jamais
//   pendant une entrée-sortie ou une attente. Ils enregistrent leur
//   propriétaire, ce qui permet au système de prêter la priorité du fil temps
//   réel qui attend au fil qui tient le verrou.

import Foundation

/// Un os_unfair_lock ne doit jamais changer d'adresse : il vit dans sa propre allocation.
private func nouveauVerrou() -> UnsafeMutablePointer<os_unfair_lock> {
    let verrou = UnsafeMutablePointer<os_unfair_lock>.allocate(capacity: 1)
    verrou.initialize(to: os_unfair_lock())
    return verrou
}

/// Le statut, suivi de son code à quatre caractères quand il en a un ('nope', '!dev'…).
/// Hors temps réel seulement : sert aux messages d'erreur et au diagnostic de capture.
func decrire(_ statut: OSStatus) -> String {
    let octets = withUnsafeBytes(of: UInt32(bitPattern: statut).bigEndian, Array.init)
    guard octets.allSatisfy({ (0x20...0x7E).contains($0) }) else { return "\(statut)" }
    return "\(statut) ('\(String(decoding: octets, as: UTF8.self))')"
}

// --- capture : blocs en attente d'écriture sur stdout ---------------------
//
// Le rappel de capture tourne sur le fil temps réel : une écriture bloquante
// là-dedans gèlerait aussi la lecture, puisque capture et lecture partagent
// la même unité. On range donc les blocs capturés dans une file bornée, et un
// fil dédié les écrit sur la sortie standard. Politique d'abandon si Python
// ne lit plus assez vite : on jette le bloc le PLUS ANCIEN pour garder une
// mémoire bornée — mieux vaut perdre un peu de passé que de laisser grossir
// indéfiniment un tampon qui de toute façon ne sera jamais consommé à temps.
// `ajouter` tournant sur le fil temps réel, la file est un anneau de cases
// fixes, et non plus un tableau de `Data` alloués bloc par bloc.
//
// Le rappel y note aussi les tranches du micro qu'il perd : sans bloc pendant
// un moment, le fil d'écriture peut ainsi expliquer en français pourquoi le
// micro se tait, au lieu de laisser Python attendre sans un mot.
final class TamponSortie {
    private struct Etat {
        var debut = 0
        var compte = 0
        // Tranches du micro perdues depuis le dernier bloc publié.
        var pertes = 0
        var dernierStatut: OSStatus = noErr
        var derniereTranche = 0
    }

    private let tailleBloc: Int
    private let capaciteMax: Int
    private let cases: UnsafeMutableRawPointer
    private let etat: UnsafeMutablePointer<Etat>
    private let verrou = nouveauVerrou()
    private let disponible = DispatchSemaphore(value: 0)

    init(tailleBloc: Int) {
        let capaciteMax = 250  // ~5 s de capture à 20 ms/bloc
        self.tailleBloc = tailleBloc
        self.capaciteMax = capaciteMax
        cases = .allocate(byteCount: capaciteMax * tailleBloc, alignment: 16)
        etat = .allocate(capacity: 1)
        cases.initializeMemory(as: UInt8.self, repeating: 0, count: capaciteMax * tailleBloc)
        etat.initialize(to: Etat())
    }

    /// Fil temps réel : recopie un bloc de `tailleBloc` octets, sans jamais attendre.
    func ajouter(_ bloc: UnsafeRawPointer) {
        os_unfair_lock_lock(verrou)
        etat.pointee.pertes = 0  // un bloc publié clôt l'épisode de pertes
        let debut = etat.pointee.debut, compte = etat.pointee.compte
        if compte == capaciteMax {
            // Plein : le nouveau bloc prend la case du plus ancien, et le
            // nombre de blocs disponibles ne change pas — donc pas de signal
            // ici. Un signal sur cette branche désynchroniserait le compte du
            // sémaphore du contenu réel de la file : après une rafale
            // d'abandons, `prendre()` finirait par franchir `wait()` sur une
            // file déjà vide.
            (cases + debut * tailleBloc).copyMemory(from: bloc, byteCount: tailleBloc)
            etat.pointee.debut = (debut + 1) % capaciteMax
            os_unfair_lock_unlock(verrou)
            return
        }
        let fin = (debut + compte) % capaciteMax
        (cases + fin * tailleBloc).copyMemory(from: bloc, byteCount: tailleBloc)
        etat.pointee.compte = compte + 1
        os_unfair_lock_unlock(verrou)
        disponible.signal()
    }

    /// Fil temps réel : note une tranche du micro perdue, trop grande pour le
    /// tampon de capture ou refusée par AudioUnitRender. Même verrou court que
    /// `ajouter` : ni attente, ni allocation, ni entrée-sortie.
    func noterPerte(statut: OSStatus, trames: Int) {
        os_unfair_lock_lock(verrou)
        etat.pointee.pertes += 1
        etat.pointee.dernierStatut = statut
        etat.pointee.derniereTranche = trames
        os_unfair_lock_unlock(verrou)
    }

    /// Fil d'écriture : attend un bloc au plus `delai` secondes ; s'il en vient
    /// un, le recopie dans `destination` et rend true. Le sémaphore ne compte
    /// jamais plus de blocs qu'il n'y en a : après un `wait` réussi, il y en a
    /// au moins un ; une attente expirée ne consomme rien.
    func prendre(dans destination: UnsafeMutableRawPointer, delai: Int) -> Bool {
        guard disponible.wait(timeout: .now() + .seconds(delai)) == .success else { return false }
        os_unfair_lock_lock(verrou)
        let debut = etat.pointee.debut
        destination.copyMemory(from: cases + debut * tailleBloc, byteCount: tailleBloc)
        etat.pointee.debut = (debut + 1) % capaciteMax
        etat.pointee.compte -= 1
        os_unfair_lock_unlock(verrou)
        return true
    }

    /// Fil d'écriture, après `delai` secondes sans bloc : une ligne en français
    /// qui dit pourquoi, d'après les pertes notées depuis le dernier bloc.
    func diagnosticSansCapture(delai: Int, capacite: Int) -> String {
        os_unfair_lock_lock(verrou)
        let releve = etat.pointee
        os_unfair_lock_unlock(verrou)
        let debut = "Capture interrompue : aucun bloc du micro depuis \(delai) s"
        guard releve.pertes > 0 else {
            return debut + ", et aucune erreur relevée : le micro ne livre rien."
        }
        let detail = "\(debut). Tranches perdues : \(releve.pertes) ; la dernière faisait "
            + "\(releve.derniereTranche) trames"
        if releve.derniereTranche > capacite {
            return detail + ", plus que le tampon de capture (\(capacite))."
        }
        return detail + ", refusée par AudioUnitRender (statut \(decrire(releve.dernierStatut)))."
    }
}

// --- capture : assemblage des blocs de 20 ms ------------------------------
//
// L'unité rend des tranches de taille variable ; Python attend des blocs de
// 640 octets. L'accumulateur a la capacité fixe d'un bloc : plein, il est
// recopié d'un coup dans la file de sortie et repart de zéro, sans jamais
// décaler d'éléments. Seul le rappel de capture y touche : pas de verrou.
final class AccumulateurCapture {
    private let taille: Int
    private let bloc: UnsafeMutablePointer<Int16>
    private let remplis: UnsafeMutablePointer<Int>
    private let sortie: TamponSortie

    init(echantillonsParBloc: Int, sortie: TamponSortie) {
        taille = echantillonsParBloc
        bloc = .allocate(capacity: echantillonsParBloc)
        remplis = .allocate(capacity: 1)
        self.sortie = sortie
        bloc.initialize(repeating: 0, count: echantillonsParBloc)
        remplis.initialize(to: 0)
    }

    /// Fil temps réel : convertit en s16le avec écrêtage, publie chaque bloc complet.
    func ajouter(_ source: UnsafePointer<Float>, _ n: Int) {
        var remplis = self.remplis.pointee
        for i in 0..<n {
            // NaN devient silence ; au-delà de ±1, écrêtage (Int16(_:) planterait).
            let x = source[i]
            bloc[remplis] = (x.isNaN ? 0 : Int16(max(-1, min(1, x)) * 32767)).littleEndian
            remplis += 1
            if remplis == taille {
                sortie.ajouter(UnsafeRawPointer(bloc))
                remplis = 0
            }
        }
        self.remplis.pointee = remplis
    }
}

// --- lecture : échantillons en attente du haut-parleur --------------------
//
// Le lecteur de stdin (fil principal) ajoute, le rappel de lecture (fil temps
// réel) retire, dans un anneau de capacité fixe. Tout accès aux échantillons
// ou aux indices se fait verrou tenu : un vidage tombe donc entièrement avant
// ou entièrement après la copie d'une tranche, jamais au milieu.
//
// Contre-pression : si la file contient plus de `seuil` échantillons, le
// lecteur de stdin attend que le rappel l'ait ramenée sous ce seuil. Il cesse
// alors de lire stdin, le tube se remplit, et le `drain()` de Python freine.
// La capacité vaut le seuil plus une trame maximale : la trame acceptée juste
// sous le seuil tient donc toujours, et la file ne grossit jamais au-delà.
final class FileLecture {
    private struct Etat {
        var lecture = 0               // indice du prochain échantillon à jouer
        var compte = 0                // échantillons en attente
        var lecteurEnAttente = false  // le lecteur de stdin dort sur `reveil`
    }

    private let seuil: Int
    private let trameMax: Int
    private let capacite: Int
    private let echantillons: UnsafeMutablePointer<Float>
    private let conversion: UnsafeMutablePointer<Float>  // fil principal seulement
    private let etat: UnsafeMutablePointer<Etat>
    private let verrou = nouveauVerrou()
    private let reveil = DispatchSemaphore(value: 0)

    init(seuil: Int, trameMax: Int) {
        self.seuil = seuil
        self.trameMax = trameMax
        capacite = seuil + trameMax
        echantillons = .allocate(capacity: seuil + trameMax)
        conversion = .allocate(capacity: trameMax)
        etat = .allocate(capacity: 1)
        echantillons.initialize(repeating: 0, count: capacite)
        conversion.initialize(repeating: 0, count: trameMax)
        etat.initialize(to: Etat())
    }

    /// Fil principal : convertit une trame s16le en Float32 et l'ajoute. Si la
    /// file dépasse le seuil, attend d'abord que le rappel l'ait ramenée dessous.
    func ajouter(_ pcm: UnsafeRawBufferPointer) {
        let n = pcm.count / 2
        precondition(n <= trameMax, "trame plus longue que la trame maximale")
        for i in 0..<n {  // conversion hors verrou
            let brut = pcm.loadUnaligned(fromByteOffset: 2 * i, as: Int16.self)
            conversion[i] = Float(Int16(littleEndian: brut)) / 32767
        }
        os_unfair_lock_lock(verrou)
        while etat.pointee.compte > seuil {
            // Drapeau posé verrou tenu : le rappel ne signale que s'il le voit,
            // et le baisse en signalant. Un signal par attente, aucun de perdu.
            etat.pointee.lecteurEnAttente = true
            os_unfair_lock_unlock(verrou)
            reveil.wait()
            os_unfair_lock_lock(verrou)
        }
        let fin = (etat.pointee.lecture + etat.pointee.compte) % capacite
        let avantBouclage = min(n, capacite - fin)
        (echantillons + fin).update(from: conversion, count: avantBouclage)
        echantillons.update(from: conversion + avantBouclage, count: n - avantBouclage)
        etat.pointee.compte += n
        os_unfair_lock_unlock(verrou)
    }

    /// Fil principal : jette tout ce qui attend d'être joué (barge-in).
    ///
    /// Le réveil ci-dessous est défensif et ne peut pas se produire aujourd'hui :
    /// le seul lecteur qui puisse attendre la contre-pression est le fil même
    /// qui exécute ce vidage. Il ne sert qu'à garder l'invariant du sémaphore
    /// si le vidage changeait un jour de fil. Limite connue de la phase 1 : sous
    /// contre-pression, une trame de vidage attend derrière tout ce qui la
    /// précède dans le tube, consommé au rythme de la lecture (quelques secondes
    /// au pire) ; le remède viendra côté Python.
    func vider() {
        os_unfair_lock_lock(verrou)
        etat.pointee.compte = 0
        let reveiller = etat.pointee.lecteurEnAttente
        etat.pointee.lecteurEnAttente = false
        os_unfair_lock_unlock(verrou)
        if reveiller { reveil.signal() }
    }

    /// Fil temps réel : copie jusqu'à `n` échantillons dans `sortie` et
    /// complète par du silence. Réveille le lecteur de stdin s'il attendait
    /// et que la file est repassée sous le seuil.
    func remplir(_ sortie: UnsafeMutablePointer<Float>, _ n: Int) {
        os_unfair_lock_lock(verrou)
        let lus = min(n, etat.pointee.compte)
        let debut = etat.pointee.lecture
        let avantBouclage = min(lus, capacite - debut)
        sortie.update(from: echantillons + debut, count: avantBouclage)
        (sortie + avantBouclage).update(from: echantillons, count: lus - avantBouclage)
        etat.pointee.lecture = (debut + lus) % capacite
        etat.pointee.compte -= lus
        let reveiller = etat.pointee.lecteurEnAttente && etat.pointee.compte <= seuil
        if reveiller { etat.pointee.lecteurEnAttente = false }
        os_unfair_lock_unlock(verrou)
        (sortie + lus).update(repeating: 0, count: n - lus)
        if reveiller { reveil.signal() }
    }
}
