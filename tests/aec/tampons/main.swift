import Foundation
setvbuf(stdout, nil, _IONBF, 0)
alarm(150)  // chien de garde : un blocage tue le harnais au lieu de pendre

var echecs = 0
func verifie(_ ok: Bool, _ quoi: String, ligne: Int = #line) {
    if !ok { echecs += 1; print("ÉCHEC l.\(ligne) : \(quoi)") }
}
func trame(_ valeurs: [Int16]) -> [UInt8] {
    valeurs.flatMap { v in withUnsafeBytes(of: v.littleEndian) { Array($0) } }
}
func ajouter(_ f: FileLecture, _ valeurs: [Int16]) {
    trame(valeurs).withUnsafeBytes { f.ajouter($0) }
}
func lire(_ f: FileLecture, _ n: Int) -> [Int16] {
    var sortie = [Float](repeating: -9, count: n)
    sortie.withUnsafeMutableBufferPointer { f.remplir($0.baseAddress!, n) }
    return sortie.map { Int16(($0 * 32767).rounded()) }
}

// 1. Bouclage : capacité 14 (seuil 10 + trame 4), 200 échantillons en tranches irrégulières.
do {
    let f = FileLecture(seuil: 10, trameMax: 4)
    var suivant: Int16 = 1, attendu: Int16 = 1
    for tour in 0..<100 {
        let t = [Int16](suivant..<(suivant + 2)); suivant += 2
        ajouter(f, t)
        let lus = lire(f, [1, 2, 3][tour % 3])  // 2 en moyenne : autant que produit
        for v in lus { verifie(v == attendu, "ordre au tour \(tour) : \(v) ≠ \(attendu)"); attendu += 1 }
    }
    let reste = lire(f, 60)
    let nonNuls = reste.prefix { $0 != 0 }
    for v in nonNuls { verifie(v == attendu, "reste : \(v) ≠ \(attendu)"); attendu += 1 }
    verifie(attendu == suivant, "tout relu : \(attendu) vs \(suivant)")
    verifie(reste.dropFirst(nonNuls.count).allSatisfy { $0 == 0 }, "silence après la fin")
}

// 2. Vidage : rien d'avant ne ressort ; ce qui suit ressort seul.
do {
    let f = FileLecture(seuil: 10, trameMax: 4)
    ajouter(f, [1, 2, 3, 4]); ajouter(f, [5, 6])
    _ = lire(f, 1)
    f.vider()
    verifie(lire(f, 5) == [0, 0, 0, 0, 0], "silence après vidage")
    ajouter(f, [7, 8])
    verifie(lire(f, 4) == [7, 8, 0, 0], "seulement l'après-vidage")
}

// 3. Contre-pression : bloque au-delà du seuil, repart quand le rappel draine.
do {
    let f = FileLecture(seuil: 10, trameMax: 4)
    for i in 0..<3 { ajouter(f, [Int16(4 * i + 1), Int16(4 * i + 2), Int16(4 * i + 3), Int16(4 * i + 4)]) }  // 12 > 10
    let fini = DispatchSemaphore(value: 0)
    Thread { ajouter(f, [13, 14, 15, 16]); fini.signal() }.start()
    verifie(fini.wait(timeout: .now() + 0.3) == .timedOut, "le lecteur doit attendre au-dessus du seuil")
    _ = lire(f, 1)  // 11 : toujours au-dessus
    verifie(fini.wait(timeout: .now() + 0.3) == .timedOut, "11 > 10 : toujours en attente")
    _ = lire(f, 1)  // 10 : sous le seuil (≤)
    verifie(fini.wait(timeout: .now() + 2) == .success, "réveillé à 10")
    verifie(lire(f, 16) == [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 0, 0], "ordre après contre-pression")
}

// 4. Un vidage réveille un lecteur en attente, et sa trame passe après le vidage.
do {
    let f = FileLecture(seuil: 10, trameMax: 4)
    for i in 0..<3 { ajouter(f, [1, 1, 1, 1]) ; _ = i }
    let fini = DispatchSemaphore(value: 0)
    Thread { ajouter(f, [42, 43]); fini.signal() }.start()
    verifie(fini.wait(timeout: .now() + 0.3) == .timedOut, "en attente")
    f.vider()
    verifie(fini.wait(timeout: .now() + 2) == .success, "le vidage réveille")
    verifie(lire(f, 4) == [42, 43, 0, 0], "seule la trame d'après le vidage")
}

// 5. Rappel concurrent : un producteur et un « rappel » sur deux fils, 200 000 échantillons.
do {
    let f = FileLecture(seuil: 1000, trameMax: 320)
    let total = 200_000
    let prod = Thread {
        var v = 0
        while v < total {
            let n = min(320, total - v)
            ajouter(f, (0..<n).map { Int16(truncatingIfNeeded: (v + $0) % 30000 + 1) }); v += n
        }
    }
    prod.start()
    var attendu = 0, silences = 0
    while attendu < total {
        for x in lire(f, 173) {
            if x == 0 { silences += 1; continue }
            verifie(Int(x) == attendu % 30000 + 1, "concurrent : \(x) à \(attendu)"); attendu += 1
            if echecs > 5 { break }
        }
        if echecs > 5 { break }
    }
    print("concurrent : \(attendu) échantillons dans l'ordre, \(silences) silences de sous-alimentation")
}

// 6. TamponSortie : 300 blocs sans lecteur -> on garde les 250 derniers, puis la file est vide.
do {
    let t = TamponSortie(tailleBloc: 4)
    for i in 0..<300 { var b = UInt32(i); withUnsafeBytes(of: &b) { t.ajouter($0.baseAddress!) } }
    var dest = UInt32(0)
    var ok = true
    for i in 50..<300 {
        withUnsafeMutableBytes(of: &dest) { _ = t.prendre(dans: $0.baseAddress!, delai: 5) }
        if dest != UInt32(i) { ok = false; print("bloc \(i) : reçu \(dest)"); break }
    }
    verifie(ok, "les 250 plus récents, dans l'ordre")
    var d = UInt32(0)
    let vide = withUnsafeMutableBytes(of: &d) { t.prendre(dans: $0.baseAddress!, delai: 1) }
    verifie(!vide, "file vide : prendre expire (sémaphore = contenu)")
    let fini = DispatchSemaphore(value: 0)
    Thread { var d = UInt32(0); let ok = withUnsafeMutableBytes(of: &d) { t.prendre(dans: $0.baseAddress!, delai: 5) }; if ok && d == 999 { fini.signal() } }.start()
    usleep(200_000)
    var b = UInt32(999); withUnsafeBytes(of: &b) { t.ajouter($0.baseAddress!) }
    verifie(fini.wait(timeout: .now() + 3) == .success, "un ajout réveille prendre, sans rien perdre après une attente expirée")
}

// 7. Accumulateur : tranches irrégulières -> blocs de 4 échantillons, écrêtage, NaN.
do {
    let t = TamponSortie(tailleBloc: 8)
    let a = AccumulateurCapture(echantillonsParBloc: 4, sortie: t)
    let source: [Float] = [0.5, -0.5, 2.0, -2.0, .nan, 1.0, -1.0, 0.25, 0, 0.001]
    source.withUnsafeBufferPointer { p in
        a.ajouter(p.baseAddress!, 3); a.ajouter(p.baseAddress! + 3, 5); a.ajouter(p.baseAddress! + 8, 2)
    }
    var blocs: [[Int16]] = []
    for _ in 0..<2 {
        var d = [UInt8](repeating: 0, count: 8)
        d.withUnsafeMutableBytes { _ = t.prendre(dans: $0.baseAddress!, delai: 5) }
        blocs.append(stride(from: 0, to: 8, by: 2).map { Int16(littleEndian: Int16(d[$0]) | Int16(d[$0 + 1]) << 8) })
    }
    verifie(blocs[0] == [16383, -16383, 32767, -32767], "bloc 1 : \(blocs[0])")
    verifie(blocs[1] == [0, 32767, -32767, 8191], "bloc 2 (NaN → 0) : \(blocs[1])")
}

// 8. TamponSortie sous concurrence : producteur rapide, consommateur lent. Abandons
//    permis, mais jamais de doublon, de désordre, ni de plantage (invariant du sémaphore).
do {
    let t = TamponSortie(tailleBloc: 8)
    let total = 100_000
    Thread {
        for i in 0..<total { var b = UInt64(i); withUnsafeBytes(of: &b) { t.ajouter($0.baseAddress!) } }
    }.start()
    var dernier = -1, recus = 0
    var d = UInt64(0)
    while dernier < total - 1 {
        withUnsafeMutableBytes(of: &d) { _ = t.prendre(dans: $0.baseAddress!, delai: 5) }
        let v = Int(d)
        if v <= dernier { verifie(false, "désordre ou doublon : \(v) après \(dernier)"); break }
        dernier = v; recus += 1
        if recus % 64 == 0 { usleep(200) }
    }
    print("sortie concurrente : \(recus) blocs reçus sur \(total), dernier = \(dernier)")
}

// 9. Diagnostic sans aucune perte notée : le micro ne livre rien.
do {
    let t = TamponSortie(tailleBloc: 4)
    let m = t.diagnosticSansCapture(delai: 2, capacite: 4096)
    verifie(m == "Capture interrompue : aucun bloc du micro depuis 2 s, et aucune erreur relevée : le micro ne livre rien.", m)
}

// 10. Échecs d'AudioUnitRender : compte et dernier statut ; un bloc publié remet à zéro.
do {
    let t = TamponSortie(tailleBloc: 4)
    t.noterPerte(statut: -10863, trames: 170); t.noterPerte(statut: -10863, trames: 171); t.noterPerte(statut: 1852797029, trames: 172)
    let m = t.diagnosticSansCapture(delai: 2, capacite: 4096)
    verifie(m == "Capture interrompue : aucun bloc du micro depuis 2 s. Tranches perdues : 3 ; la dernière faisait 172 trames, refusée par AudioUnitRender (statut 1852797029 ('nope')).", m)
    var b = UInt32(1); withUnsafeBytes(of: &b) { t.ajouter($0.baseAddress!) }
    let m2 = t.diagnosticSansCapture(delai: 2, capacite: 4096)
    verifie(m2.hasSuffix("le micro ne livre rien."), "remise à zéro après un bloc : \(m2)")
}

// 11. Tranche trop grande : le message le dit, avec la capacité.
do {
    let t = TamponSortie(tailleBloc: 4)
    t.noterPerte(statut: noErr, trames: 5000)
    let m = t.diagnosticSansCapture(delai: 2, capacite: 4096)
    verifie(m == "Capture interrompue : aucun bloc du micro depuis 2 s. Tranches perdues : 1 ; la dernière faisait 5000 trames, plus que le tampon de capture (4096).", m)
    verifie(decrire(-10875) == "-10875", "decrire sans code à quatre caractères")
}

// 12. Concurrence : un « rappel » alterne pertes et blocs pendant que le fil
//     d'écriture prend avec délai et lit le diagnostic. Aucune course (TSan).
do {
    let t = TamponSortie(tailleBloc: 8)
    let total = 20_000
    let fin = DispatchSemaphore(value: 0)
    Thread {
        for i in 0..<total {
            if i % 3 == 0 { t.noterPerte(statut: -10863, trames: i) }
            else { var b = UInt64(i); withUnsafeBytes(of: &b) { t.ajouter($0.baseAddress!) } }
        }
        fin.signal()
    }.start()
    var recus = 0, dernier = -1, d = UInt64(0)
    while withUnsafeMutableBytes(of: &d, { t.prendre(dans: $0.baseAddress!, delai: 1) }) {
        if Int(d) <= dernier { verifie(false, "désordre : \(d) après \(dernier)"); break }
        dernier = Int(d); recus += 1
        if recus % 500 == 0 { _ = t.diagnosticSansCapture(delai: 2, capacite: 4096) }
    }
    verifie(fin.wait(timeout: .now() + 5) == .success, "le producteur a fini")
    print("pertes et blocs concurrents : \(recus) blocs reçus, dernier = \(dernier), puis attente expirée")
}

print(echecs == 0 ? "TOUT BON" : "\(echecs) échec(s)")
exit(echecs == 0 ? 0 : 1)
