# aliases.py — curated nickname/common-name knowledge base for famous works.
# Maps canonical classical & modern-piano titles to the names people actually
# search for ("Moonlight Sonata", "Fate Symphony", "fate knocking at the door",
# "Raindrop Prelude", "Air on the G String", "Ode to Joy", ...), so archive.org /
# HF search hits land on the right track even when the file title uses only the
# formal catalog name (e.g. "Symphony No. 5 in C minor, Op. 67").
# Curated from standard references (Wikipedia list of classical sub-titles and
# nicknames, Limelight, Classical Unpacked) and extended by hand.
# Author: Vaibhav (Vaibhav Agarwal) — the archiver
# Contact: nekomeowpurr@proton.me | GitHub: https://github.com/thisisforlearn/archive
# Project authority: Vaibhav holds final decision power over this project.
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

# Each entry: (composer-regex | None, title-regex, primary alias, alias tuple).
# The composer-regex gates the match to the right composer (checked against
# artist + composer + album); the title-regex must hit the folded title text.
FLAG = re.IGNORECASE


def _fold(text: str) -> str:
    """Fold accents + punctuation to plain lowercase ASCII, single-spaced."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFKD", text)
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    norm = norm.casefold().replace("ss", "ss")  # keep ß->ss via casefold
    norm = re.sub(r"[\u2018\u2019\u201c\u201d'`´’‘]", " ", norm)
    norm = re.sub(r"[^a-z0-9]+", " ", norm)
    return re.sub(r"\s+", " ", norm).strip()


@lru_cache(maxsize=8192)
def folded(s: str) -> str:
    return _fold(s)


ALIAS_TABLE: tuple[tuple[str | None, str, str, tuple[str, ...]], ...] = (
    # ---------------------------------------------------------------- Beethoven
    ("beethoven", r"symphony\s*(number|no|n|#)?\.?\s*5[^0-9]", "Fate Symphony",
     ("The Fate Symphony", "Symphony of Fate", "The Fate Motif", "Fate Knocking at the Door",
      "Schicksals-Sinfonie", "Beethoven's Fifth")),
    ("beethoven", r"symphony\s*(number|no|n|#)?\.?\s*3", "Eroica",
     ("the Eroica", "Heroic Symphony")),
    ("beethoven", r"symphony\s*(number|no|n|#)?\.?\s*6", "Pastoral Symphony",
     ("the Pastoral", "Pastorale")),
    ("beethoven", r"symphony\s*(number|no|n|#)?\.?\s*7", "the Apotheosis of the Dance",
     ("Apotheosis of the Dance")),
    ("beethoven", r"symphony\s*(number|no|n|#)?\.?\s*9", "Choral Symphony",
     ("the Choral Symphony", "Ode to Joy", "An die Freude", "the Ninth")),
    ("beethoven", r"sonata\s*(number|no|n|#)?\.?\s*14", "Moonlight Sonata",
     ("the Moonlight Sonata", "Mondscheinsonate", "Sonata quasi una fantasia")),
    ("beethoven", r"sonata\s*(number|no|n|#)?\.?\s*8", "Pathetique Sonata",
     ("the Pathetique", "Grande Sonate pathetique")),
    ("beethoven", r"sonata\s*(number|no|n|#)?\.?\s*23", "Appassionata",
     ("the Appassionata")),
    ("beethoven", r"sonata\s*(number|no|n|#)?\.?\s*21", "Waldstein Sonata",
     ("the Waldstein")),
    ("beethoven", r"sonata\s*(number|no|n|#)?\.?\s*17", "Tempest Sonata",
     ("the Tempest", "Der Sturm")),
    ("beethoven", r"sonata\s*(number|no|n|#)?\.?\s*26", "Les Adieux",
     ("Les Adieux", "Das Lebewohl", "The Farewell Sonata")),
    ("beethoven", r"elise|bagatelle", "Fur Elise",
     ("Fuer Elise", "For Elise", "Bagatelle in A minor WoO 59")),
    ("beethoven", r"piano\s*concerto\s*(number|no|n|#)?\.?\s*5", "Emperor Concerto",
     ("the Emperor", "Kaiserkonzert")),
    ("beethoven", r"(piano\s*trio|string\s*trio)\s*(number|no|n|#)?\.?\s*7", "Archduke Trio",
     ("the Archduke Trio", "the Archduke")),
    ("beethoven", r"piano\s*trio\s*(number|no|n|#)?\.?\s*5", "Ghost Trio",
     ("the Ghost Trio", "Geistertrio")),
    ("beethoven", r"string\s*quartets?\s*(number|no|n|#)?\.?\s*7", "Razumovsky Quartets",
     ("the Razumovsky Quartets")),
    ("beethoven", r"kreutzer|violin\s*sonata\s*(number|no|n|#)?\.?\s*9", "Kreutzer Sonata",
     ("the Kreutzer Sonata")),
    ("beethoven", r"grosse\s*fuge|gro[sß]?e\s*fuge", "Grosse Fuge",
     ("the Great Fugue")),
    # ---------------------------------------------------------------- Mozart
    ("mozart", r"symphony\s*(number|no|n|#)?\.?\s*41", "Jupiter Symphony",
     ("the Jupiter Symphony", "the Jupiter")),
    ("mozart", r"symphony\s*(number|no|n|#)?\.?\s*40", "Great G minor Symphony",
     ("the famous G minor Symphony")),
    ("mozart", r"eine\s*kleine", "Eine kleine Nachtmusik",
     ("A Little Night Music", "Serenade No. 13 for strings")),
    ("mozart", r"sonata\s*(number|no|n|#)?\.?\s*11|rondo\s*alla\s*turca|alla\s*turca",
     "Turkish March", ("Rondo alla Turca", "the Turkish Rondo")),
    ("mozart", r"piano\s*concerto\s*(number|no|n|#)?\.?\s*21", "Elvira Madigan Concerto",
     ("the Elvira Madigan Andante", "the famous slow movement of Piano Concerto No. 21")),
    ("mozart", r"requiem", "Mozart Requiem",
     ("Lacrimosa", "Dies Irae (Mozart)", "Requiem in D minor K. 626")),
    ("mozart", r"magic\s*flute|zauberfl", "Queen of the Night aria",
     ("Der Holle Rache", "The Magic Flute", "Die Zauberflote")),
    ("mozart", r"clarinet\s*concerto", "the Clarinet Concerto K. 622",
     ("Clarinet Concerto in A major")),
    ("mozart", r"ave\s*verum", "Ave verum corpus",
     ("Ave Verum (Mozart)",)),
    # ---------------------------------------------------------------- Bach
    (r"\bbach\b", r"toccata\s*and\s*fugue", "Toccata and Fugue in D minor",
     ("the horror-movie organ piece", "the Fantasia opening organ", "BWV 565")),
    (r"\bbach\b", r"\bair\b", "Air on the G String",
     ("Air for the G String", "the Air from Orchestral Suite No. 3", "BWV 1068")),
    (r"\bbach\b", r"cello\s*suite", "Cello Suite No. 1 Prelude",
     ("the famous cello prelude", "BWV 1007 Prelude")),
    (r"\bbach\b", r"brandenburg", "Brandenburg Concertos",
     ("the Brandenburgs", "Six Brandenburg Concertos")),
    (r"\bbach\b", r"goldberg", "Goldberg Variations",
     ("the Goldberg Variations", "Aria mit 30 Veraenderungen")),
    (r"\bbach\b", r"well[\-\s]*tempered|wohltemper", "The Well-Tempered Clavier",
     ("WTC", "Prelude in C major from the Well-Tempered Clavier")),
    (r"\bbach\b", r"jesu.*joy|joy.*man", "Jesu, Joy of Man's Desiring",
     ("Jesu bleibet meine Freude", "BWV 147")),
    (r"\bbach\b", r"minuet\s*in\s*g\b", "Minuet in G (Bach/Petzold)",
     ("the Minuet in G", "BWV Anh. 114")),
    (r"\bbach\b", r"matth.*passion|passion\b", "St Matthew Passion",
     ("Erbarne dich", "Mattaus-Passion")),
    # ---------------------------------------------------------------- Vivaldi
    ("vivaldi", r"season|primavera|spring\b", "Four Seasons - Spring (La primavera)",
     ("the Spring concerto from The Four Seasons", "the bird-song Spring movement")),
    ("vivaldi", r"summer|estate", "Four Seasons - Summer (L'estate)",
     ("the summer-storm movement")),
    ("vivaldi", r"autumn|autunno", "Four Seasons - Autumn (L'autunno)",
     ("the hunt movement")),
    ("vivaldi", r"winter|inverno", "Four Seasons - Winter (L'inverno)",
     ("the teeth-chattering Winter")),
    ("vivaldi", r"gloria", "Vivaldi Gloria",
     ("Gloria RV 589",)),
    # ---------------------------------------------------------------- Chopin
    ("chopin", r"prelude\s*(number|no|n|#)?\.?\s*15", "Raindrop Prelude",
     ("the Raindrop Prelude", "Prelude in D-flat major Raindrop")),
    ("chopin", r"prelude\s*(number|no|n|#)?\.?\s*4", "the famous E minor Prelude",
     ("Prelude in E minor Op. 28 No. 4")),
    ("chopin", r"waltz|minute", "Minute Waltz",
     ("the Minute Waltz", "the little dog waltz")),
    ("chopin", r"nocturne.*op.*9|nocturne\s*(number|no|n|#)?\.?\s*2", "the famous E-flat Nocturne",
     ("Nocturne in E-flat major Op. 9 No. 2", "the famous Chopin nocturne")),
    ("chopin", r"tristesse|etude.*(op.*10.*no.*3|\bno\.?\s*3\b)", "Tristesse Etude",
     ("the Farewell Etude", "Etude Op. 10 No. 3")),
    ("chopin", r"revolutionary|etude.*op.*10.*no.*12", "Revolutionary Etude",
     ("the Revolutionary", "Etude on the fall of Warsaw")),
    ("chopin", r"winter\s*wind|etude.*op.*25.*no.*11", "Winter Wind",
     ("the Winter Wind Etude")),
    ("chopin", r"black\s*keys?|etude.*op.*10.*no.*5", "Black Key Etude",
     ("the Black Keys Etude")),
    ("chopin", r"fantaisie|impromptu", "Fantaisie-Impromptu",
     ("the Fantaisie-Impromptu in C-sharp minor")),
    ("chopin", r"polonaise.*(53|herois|heroic)", "Heroic Polonaise",
     ("the Heroic Polonaise", "Polonaise Heroique")),
    ("chopin", r"polonaise.*(40|military)", "Military Polonaise",
     ("the Military Polonaise")),
    ("chopin", r"funeral.*march|marche.*fun", "Funeral March",
     ("Marche funebre", "the Chopin funeral march")),
    # ---------------------------------------------------------------- Liszt
    ("liszt", r"hungarian\s*rhapsody\s*(number|no|n|#)?\.?\s*2", "Hungarian Rhapsody No. 2",
     ("the classic-cartoon classical", "the Tom-and-Jerry piano piece")),
    ("liszt", r"campanella", "La Campanella",
     ("the bell etude")),
    ("liszt", r"liebestraum", "Liebestraum No. 3",
     ("Dream of Love No. 3", "the Liebestraum")),
    ("liszt", r"sospiro", "Un sospiro",
     ("the sighing etude")),
    # ---------------------------------------------------------------- Satie
    ("satie", r"gymnoped", "Gymnopedie No. 1",
     ("the Gymnopedies", "the slow dreamy Satie")),
    ("satie", r"gnossienne", "Gnossienne No. 1",
     ("the Gnossiennes",)),
    # ---------------------------------------------------------------- Debussy
    ("debussy", r"clair\s*de\s*lune|bergamas", "Clair de lune",
     ("the Debussy moonlight piano piece", "Claire de Lune", "Suite bergamasque III")),
    ("debussy", r"arabesque", "Arabesque No. 1",
     ("the Deux Arabesques")),
    ("debussy", r"reverie", "Reverie",
     ("the dreamy Reverie",)),
    ("debussy", r"la\s*mer", "La Mer",
     ("the sea symphonic sketches")),
    ("debussy", r"apres.*midi|faune", "Prelude to the Afternoon of a Faun",
     ("Prelude a l'apres-midi d'un faune", "Afternoon of a Faun")),
    # ---------------------------------------------------------------- Schubert
    ("schubert", r"ave\s*maria|ellen", "Ave Maria (Schubert)",
     ("Ellens dritter Gesang", "the Schubert Ave Maria", "Hail Mary setting")),
    ("schubert", r"standchen|serenade", "Schwanengesang - Standchen (Serenade)",
     ("Serenade D. 957", "the swan-song serenade")),
    ("schubert", r"symphony\s*(number|no|n|#)?\.?\s*8", "Unfinished Symphony",
     ("the Unfinished Symphony", "Die Unvollendete", "Symphony No. 8 Unfinished")),
    ("schubert", r"trout|forelle", "Trout Quintet",
     ("Die Forelle quintet", "the fish quintet")),
    ("schubert", r"erlk", "Erlkonig",
     ("the Erl-King", "the Elf-King song", "Goethe's Erlkonig")),
    ("schubert", r"marche\s*milit|military", "Marche Militaire",
     ("the Military March")),
    # ---------------------------------------------------------------- Tchaikovsky
    (r"tchaikovsk|tschaikowsk|chaikovsk", r"1812", "1812 Overture",
     ("the cannon-fire overture", "Overture Solennelle 1812")),
    (r"tchaikovsk|tschaikowsk|chaikovsk", r"sugar\s*plum|schwalb|fairy", "Dance of the Sugar Plum Fairy",
     ("the celesta fairy dance from The Nutcracker", "Tetris Type-A theme")),
    (r"tchaikovsk|tschaikowsk|chaikovsk", r"nutcracker|casse.?noisette", "The Nutcracker Suite",
     ("Casse-Noisette", "the Christmas ballet suite", "Waltz of the Flowers",
      "Russian Dance Trepak", "Dance of the Reed Flutes")),
    (r"tchaikovsk|tschaikowsk|chaikovsk", r"swan\s*lake|lac\s*des\s*cygnes", "Swan Lake",
     ("the Swan Theme", "Le Lac des Cygnes")),
    (r"tchaikovsk|tschaikowsk|chaikovsk", r"sleeping\s*beauty|belle\s*au", "Sleeping Beauty Waltz",
     ("La Belle au bois Dormant", "the Once-Upon-a-Dream waltz")),
    (r"tchaikovsk|tschaikowsk|chaikovsk", r"piano\s*concerto\s*(number|no|n|#)?\.?\s*1",
     "Tchaikovsky Piano Concerto No. 1", ("the big B-flat minor concerto",)),
    (r"tchaikovsk|tschaikowsk|chaikovsk", r"serenade.*strings?|serenade\s*for", "Serenade for Strings",
     ("the string serenade",)),
    (r"tchaikovsk|tschaikowsk|chaikovsk", r"romeo|juliet", "Romeo and Juliet Fantasy-Overture",
     ("the Romeo & Juliet love theme",)),
    # ---------------------------------------------------------------- Grieg
    ("grieg", r"mountain\s*king|dovregubbens", "In the Hall of the Mountain King",
     ("I Dovregubbens hall", "the troll-cave music", "the tiptoeing crescendo")),
    ("grieg", r"morning|morgenstemning", "Morning Mood",
     ("the Peer Gynt sunrise music", "Morgenstemning")),
    ("grieg", r"anitra", "Anitra's Dance",
     ("Anitras Tanz",)),
    ("grieg", r"as[ei]s\s*death|ase\s", "Ase's Death",
     ("Aase's Death",)),
    ("grieg", r"piano\s*concerto", "Grieg Piano Concerto in A minor",
     ("the A-minor concerto")),
    # ---------------------------------------------------------------- Holst
    ("holst", r"planets|mars|jupiter|venus|mercury|saturn|uranus|neptune", "The Planets",
     ("Mars, the Bringer of War", "Jupiter, the Bringer of Jollity",
      "I Vow to Thee My Country (Jupiter hymn)", "the war-planet music")),
    # ---------------------------------------------------------------- Saint-Saens
    (r"saint[\-\s]*sae?ns|saens", r"carnival|animaux|tortoise|elephant|fossils|aquarium|swan",
     "The Carnival of the Animals",
     ("Le Carnaval des Animaux", "The Swan (cellist's showpiece)", "Aquarium", "Fossils")),
    (r"saint[\-\s]*sae?ns|saens", r"danse\s*macabre|dance\s*of\s*death", "Danse Macabre",
     ("the Dance of Death", "the skeleton-fiddle piece")),
    (r"saint[\-\s]*sae?ns|saens", r"symphony\s*(number|no|n|#)?\.?\s*3", "Organ Symphony",
     ("the Symphony No. 3 Organ")),
    # ---------------------------------------------------------------- Pachelbel
    ("pachelbel", r"kanon|canon", "Pachelbel's Canon in D",
     ("Canon in D Major", "the wedding-processional canon", "Kanon in D-Dur")),
    # ---------------------------------------------------------------- Orff
    ("orff", r"o\s*fortuna|fortuna|carmina", "O Fortuna",
     ("Fortuna Imperatrix Mundi", "the Carmina Burana opening chorus")),
    # ---------------------------------------------------------------- Bizet
    ("bizet", r"habanera|amour.*est.*un.*oiseau", "Habanera (Carmen)",
     ("L'amour est un oiseau rebelle", "the descending-chromatic Carmen aria")),
    ("bizet", r"toreador", "Toreador Song",
     ("Votre toast", "the bullfighter's march from Carmen")),
    ("bizet", r"carmen.*(overture|prelude)", "Carmen Overture",
     ("the bullring opening of Carmen")),
    # ---------------------------------------------------------------- Offenbach
    ("offenbach", r"can[\-\s]*can|galop|infernal", "Can-Can (Infernal Galop)",
     ("Orpheus in the Underworld finale", "the high-kicking Paris dance")),
    # ---------------------------------------------------------------- Rossini
    ("rossini", r"william\s*tell|guillaume", "William Tell Overture",
     ("the Lone Ranger theme", "the galloping finale")),
    # ---------------------------------------------------------------- Mascagni
    ("mascagni", r"intermezzo|cavalleria", "Cavalleria Rusticana Intermezzo",
     ("the Raging Bull intermezzo", "the Godfather III intermezzo")),
    # ---------------------------------------------------------------- Rimsky-Korsakov
    (r"rimsky|korsakov", r"bumble", "Flight of the Bumblebee",
     ("the buzzing violin showpiece", "Flight of the Bumble-Bee")),
    (r"rimsky|korsakov", r"scheherazade|scheh", "Sheherazade",
     ("the Arabian-Nights orchestral suite",)),
    # ---------------------------------------------------------------- Mussorgsky / Smetana
    (r"mussorgsk", r"bald\s*mountain|night.*mountain", "Night on Bald Mountain",
     ("St John's Night on Bald Mountain", "the Fantasia devil-mountain scene")),
    (r"mussorgsk", r"pictures|promenade|exhibition|gate.*kiev|baba\s*yaga", "Pictures at an Exhibition",
     ("Promenade", "The Great Gate of Kiev", "Baba Yaga")),
    ("smetana", r"moldau|vltava", "The Moldau",
     ("Vltava", "the river symphonic poem")),
    # ---------------------------------------------------------------- Dvorak
    (r"dvo[a]?r[a]?k|dv[a]?or[a]?k", r"new\s*world|symphony\s*(number|no|n|#)?\.?\s*9", "New World Symphony",
     ("From the New World", "Symphony No. 9 From the New World", "the English-horn Largo")),
    (r"dvo[a]?r[a]?k|dv[a]?or[a]?k", r"slavonic", "Slavonic Dances",
     ()),
    # ---------------------------------------------------------------- Sibelius
    ("sibelius", r"finlandia", "Finlandia",
     ("the Finlandia hymn", "the Finnish patriotic tone poem")),
    ("sibelius", r"valse\s*triste", "Valse Triste",
     ("the dying-dream waltz",)),
    # ---------------------------------------------------------------- Rachmaninoff
    (r"rachmanin", r"piano\s*concerto\s*(number|no|n|#)?\.?\s*2", "Rachmaninoff Piano Concerto No. 2",
     ("Rach 2", "the Brief Encounter concerto", "the famous weeping romantic concerto")),
    (r"rachmanin", r"paganini", "Rhapsody on a Theme of Paganini",
     ("the 18th Variation", "the love-theme on Paganini")),
    (r"rachmanin", r"vocalise", "Vocalise",
     ("the wordless song",)),
    (r"rachmanin", r"prelude.*c.?sharp|c.?sharp.*prelude", "Prelude in C-sharp minor",
     ("the Bells of Moscow prelude",)),
    # ---------------------------------------------------------------- Mahler
    ("mahler", r"symphony\s*(number|no|n|#)?\.?\s*5", "Adagietto",
     ("the Death-in-Venice Adagietto", "the Mahler love poem movement")),
    ("mahler", r"symphony\s*(number|no|n|#)?\.?\s*2", "Resurrection Symphony",
     ("Auferstehung", "the resurrection finale")),
    ("mahler", r"symphony\s*(number|no|n|#)?\.?\s*1", "Titan Symphony",
     ("Symphony No. 1 Titan",)),
    # ---------------------------------------------------------------- Brahms
    ("brahms", r"lullaby|wiegenlied|cradle", "Brahms' Lullaby",
     ("Wiegenlied", "Lullaby and Good Night", "the universal lullaby")),
    ("brahms", r"hungarian\s*dance", "Hungarian Dance No. 5",
     ("Ungarische Tanze", "the gypsy dance")),
    ("brahms", r"academic", "Academic Festival Overture",
     ("the student-drinking-songs overture",)),
    # ---------------------------------------------------------------- Elgar
    ("elgar", r"pomp.*circumstance", "Pomp and Circumstance March No. 1",
     ("Land of Hope and Glory", "the graduation-ceremony march")),
    ("elgar", r"enigma|nimrod", "Enigma Variations",
     ("Nimrod", "Variation IX Nimrod")),
    # ---------------------------------------------------------------- Handel
    (r"hande?l|h[a]ndel", r"messiah|hallelujah", "Hallelujah Chorus",
     ("the Messiah Hallelujah", "the chorus where audiences stand")),
    (r"hande?l", r"water\s*music", "Water Music",
     ("the royal barge suite on the Thames",)),
    (r"hande?l", r"fireworks", "Music for the Royal Fireworks",
     ("the 1749 fireworks spectacle",)),
    (r"hande?l", r"sarabande", "Sarabande (HWV 437)",
     ("the Barry-Lyndon slow keyboard piece",)),
    # ---------------------------------------------------------------- Haydn
    ("haydn", r"symphony\s*(number|no|n|#)?\.?\s*94", "Surprise Symphony",
     ("the loud-chord surprise symphony", "Symphony No. 94 Surprise")),
    ("haydn", r"symphony\s*(number|no|n|#)?\.?\s*101", "The Clock Symphony",
     ("Symphony No. 101 The Clock",)),
    ("haydn", r"symphony\s*(number|no|n|#)?\.?\s*100", "Military Symphony",
     ("Symphony No. 100 Military",)),
    ("haydn", r"symphony\s*(number|no|n|#)?\.?\s*104", "London Symphony",
     ("Symphony No. 104 London",)),
    ("haydn", r"trumpet\s*concerto", "Haydn Trumpet Concerto",
     ("the famous high-trumpet concerto",)),
    ("haydn", r"creation|schopf", "The Creation",
     ("Die Schoepfung",)),
    # ---------------------------------------------------------------- R. Strauss
    (r"richard\s*strauss|\br\.?\s*strauss\b", r"zarathustra|sprach", "Also sprach Zarathustra",
     ("the 2001 A Space Odyssey sunrise theme", "Thus Spoke Zarathustra", "the F-to-C trumpet opening")),
    (r"richard\s*strauss|\br\.?\s*strauss\b", r"eulenspiegel", "Till Eulenspiegel",
     ("Till Eulenspiegels lustige Streiche", "the prankster rondo")),
    (r"richard\s*strauss|\br\.?\s*strauss\b", r"heldenleben", "Ein Heldenleben",
     ("A Hero's Life",)),
    # ---------------------------------------------------------------- J. Strauss II
    (r"johann\s*strauss|\bj\.?\s*strauss\b", r"blue\s*danube|donau", "The Blue Danube",
     ("An der schoenen blauen Donau", "the 2001 space-docking waltz", "the most famous Viennese waltz")),
    (r"johann\s*strauss|\bj\.?\s*strauss\b", r"vienna\s*woods|wiener\s*wald", "Tales from the Vienna Woods",
     ("Geschichten aus dem Wienerwald",)),
    (r"johann\s*strauss|\bj\.?\s*strauss\b", r"kaiser", "Emperor Waltz",
     ("Kaiser-Walzer",)),
    ("strauss", r"radetzky", "Radetzky March",
     ("the clap-along New Year march",)),
    # ---------------------------------------------------------------- Sousa
    ("sousa", r"stars\s*and\s*stripes", "The Stars and Stripes Forever",
     ("the march-king standard", "the piccolo feature")),
    ("sousa", r"washington\s*post", "The Washington Post March",
     ("the two-step march",)),
    ("sousa", r"liberty\s*bell", "The Liberty Bell",
     ("Monty Python's Flying Circus theme",)),
    # ---------------------------------------------------------------- Joplin
    ("joplin", r"entertainer", "The Entertainer",
     ("The Sting piano theme", "the ragtime standard")),
    ("joplin", r"maple\s*leaf", "Maple Leaf Rag",
     ("the original ragtime smash",)),
    ("joplin", r"solace", "Solace",
     ("the melancholy Mexican serenade",)),
    # ---------------------------------------------------------------- Gershwin
    ("gershwin", r"rhapsody\s*in\s*blue", "Rhapsody in Blue",
     ("the clarinet-glissando jazz classic",)),
    ("gershwin", r"summertime", "Summertime (from Porgy and Bess)",
     ("the lullaby aria from Porgy and Bess",)),
    ("gershwin", r"american\s*in\s*paris", "An American in Paris",
     ("the taxi-horn symphonic poem",)),
    # ---------------------------------------------------------------- Copland
    ("copland", r"appalachian|hoe.?down|simple\s*gifts", "Appalachian Spring",
     ("the Simple Gifts hoedown", "the American-prairie music")),
    ("copland", r"fanfare", "Fanfare for the Common Man",
     ("the brass-and-timpani common-man fanfare",)),
    # ---------------------------------------------------------------- Barber
    ("barber", r"adagio", "Adagio for Strings",
     ("the Platoon funeral adagio", "the Agnus Dei vocal version")),
    # ---------------------------------------------------------------- Bruch
    ("bruch", r"kol\s*nidrei", "Kol Nidrei", ()),
    ("bruch", r"violin\s*concerto", "Bruch Violin Concerto No. 1",
     ("the G-minor romantic violin showpiece",)),
    # ---------------------------------------------------------------- Puccini
    ("puccini", r"nessun\s*dorma", "Nessun dorma",
     ("none shall sleep", "the Pavarotti World Cup aria from Turandot")),
    ("puccini", r"mio\s*babbino", "O mio babbino caro",
     ("Oh My Dear Papa", "the crying aria from Gianni Schicchi")),
    ("puccini", r"un\s*bel\s*d", "Un bel di, vedremo",
     ("One Fine Day", "the Madama Butterfly aria")),
    ("puccini", r"bohem", "La boheme", ()),
    # ---------------------------------------------------------------- Verdi
    ("verdi", r"donna.*mobile", "La donna e mobile",
     ("Rigoletto's catchy street aria",)),
    ("verdi", r"libiamo", "Libiamo (the drinking song)",
     ("the Traviata brindisi",)),
    ("verdi", r"pensiero", "Va, pensiero",
     ("the Chorus of the Hebrew Slaves", "Nabucco's chorus")),
    ("verdi", r"requiem", "Verdi Requiem",
     ("Dies Irae (Verdi)", "the Libera me finale")),
    # ---------------------------------------------------------------- Ravel
    ("ravel", r"bolero", "Bolero",
     ("the ten-minute snare-drum crescendo",)),
    ("ravel", r"pavane", "Pavane pour une infante defunte",
     ("the Pavane for a Dead Princess",)),
    # ---------------------------------------------------------------- Faure
    (r"faur[éa]?|faure", r"pavane", "Faure Pavane",
     ("the bittersweet pavane",)),
    (r"faur[éa]?|faure", r"requiem|paradisum", "Faure Requiem",
     ("In Paradisum", "the gentle requiem")),
    (r"faur[éa]?|faure", r"sicilienne", "Sicilienne",
     ("the Sicilian-tinged cello melody",)),
    # ---------------------------------------------------------------- Delibes
    ("delibes", r"copp|waltz", "Coppelia Waltz",
     ("the clockwork-doll ballet waltz",)),
    ("delibes", r"flower\s*duet|dome", "Flower Duet (Lakme)",
     ("Sous le dome epais", "the British-Airways duet")),
    # ---------------------------------------------------------------- Schumann
    ("schumann", r"traumer|kinderszen|childhood", "Traumerei",
     ("the Dreams piece from Kinderszenen", "Scenes from Childhood No. 7")),
    ("schumann", r"arabeske", "Arabeske", ()),
    # ---------------------------------------------------------------- Berlioz
    ("berlioz", r"fantastique", "Symphonie Fantastique",
     ("March to the Scaffold", "the opium-dream symphony", "Witches' Sabbath")),
    # ---------------------------------------------------------------- Albinoni
    (r"albinoni|giazotto", r"adagio", "Adagio in G minor",
     ("the neo-baroque Adagio (Albinoni/Giazotto)",)),
    # ---------------------------------------------------------------- Mendelssohn
    ("mendelssohn", r"wedding\s*march", "Wedding March (Mendelssohn)",
     ("A Midsummer Night's Dream wedding music", "the traditional wedding-exit march")),
    ("mendelssohn", r"hebrides|fingal", "The Hebrides (Fingal's Cave)", ()),
    ("mendelssohn", r"songs\s*without\s*words|lieder", "Songs Without Words",
     ("Lieder ohne Worte", "the Spring Song")),
    ("mendelssohn", r"violin\s*concerto", "Mendelssohn Violin Concerto",
     ("the E-minor violin standard",)),
    # ---------------------------------------------------------------- Wagner
    ("wagner", r"bridal|bride|lohen?gr?in", "Bridal Chorus (Here Comes the Bride)",
     ("Treulich gefuhrt", "the aisle-walking chorus", "Lohengrin wedding music")),
    ("wagner", r"valkyries|walkuren?|valkyr", "Ride of the Valkyries",
     ("Walkurenritt", "the Apocalypse-Now helicopter music")),
    ("wagner", r"liebestod|tristan", "Liebestod (Tristan und Isolde)",
     ("the Love-Death finale",)),
    ("wagner", r"pilgrims|tannh", "Pilgrims' Chorus",
     ("from Tannhauser",)),
    # ---------------------------------------------------------------- Modern piano / film
    ("einaudi", r"nuvole", "Nuvole Bianche",
     ("the white-clouds piano piece",)),
    ("einaudi", r"experience", "Experience (Einaudi)", ()),
    ("einaudi", r"una\s*mattina", "Una Mattina",
     ("the Untouchable-ones piano theme",)),
    ("einaudi", r"i\s*giorni", "I Giorni", ("The Days",)),
    ("tiersen", r"comptine|amelie", "Comptine d'un autre ete: L'apres-midi",
     ("the Amelie piano theme",)),
    ("zimmer", r"\btime\b", "Time (Hans Zimmer)",
     ("the Inception ending cue",)),
    ("zimmer", r"interstellar|cornfield", "Interstellar Main Theme",
     ("the cornfield-chase organ theme",)),
    ("zimmer", r"now\s*we\s*are\s*free|gladiator", "Now We Are Free (Gladiator)",
     ("the Lisa-Gerrard Gladiator finale",)),
    ("richter", r"nature\s*of\s*daylight", "On the Nature of Daylight",
     ("the Arrival / Shutter Island string piece",)),
    ("hisaishi", r"merry.go.round|howl", "Merry-Go-Round of Life",
     ("Howl's Moving Castle waltz", "the Ghibli carousel theme")),
    ("hisaishi", r"one\s*summer|spirited", "One Summer's Day",
     ("the Spirited-Away opening", "Spirited Away piano theme")),
)


_COMPILED = tuple(
    (re.compile(c, FLAG) if c else None, re.compile(t, FLAG), p, a)
    for c, t, p, a in ALIAS_TABLE
)


def aliases_for(title: str, artist: str = "", composer: str = "",
                album: str = "") -> tuple[str, tuple[str, ...]]:
    """Return (primary_alias_or_empty, all_aliases) for a track."""
    ft = folded(title)
    if not ft:
        return "", ()
    fj = " ".join(x for x in (folded(artist), folded(composer), folded(album)) if x) + " " + ft
    primary, acc = "", ()
    seen: set[str] = set()
    for cre, tre, p, al in _COMPILED:
        if cre is not None and not cre.search(fj):
            continue
        if not tre.search(ft) and not tre.search(fj):
            continue
        if not primary:
            primary = p
        for a in (p, *al):
            low = a.casefold()
            if low not in seen:
                seen.add(low)
                acc = acc + (a,)
    return primary, acc


def styled_title(title: str, artist: str = "", composer: str = "",
                 album: str = "", primary: str | None = None,
                 aliases: tuple[str, ...] = ()) -> str:
    """`Original title — "Primary Alias"` (never duplicates, never truncates meaning)."""
    base = (title or "").strip()
    if primary is None:
        primary, aliases = aliases_for(base, artist, composer, album)
    if not aliases or not primary:
        return base
    fb = folded(base)
    if fb and folded(primary) and folded(primary) in fb:
        return base  # nickname already present in the original title
    stripped = re.sub(r"[ -]+$", "", base)
    return f"{stripped} — “{primary}”" if len(base) < 130 else base


def aliases_for_row(row) -> tuple[str, tuple[str, ...]]:
    """Row-friendly wrapper for sqlite3.Row / dict rows."""
    return aliases_for(
        row["title"] or "", row["artist"] or "", row["composer"] or "",
        row["album"] or "",
    )


def item_alias_subject(rows) -> list[str]:
    """Aggregate alias tags for the IA item `subject` (site-internal search)."""
    out: list[str] = []
    seen: set[str] = set()
    for r in rows[:60]:
        primary, alias = aliases_for_row(r)
        for a in (primary, *alias):
            k = a.casefold()
            if a and k not in seen:
                seen.add(k)
                out.append(a)
        if len(out) >= 28:
            break
    return out[:28]


def alias_description_notes(rows) -> str:
    """'Notable works & common names' paragraph for item descriptions."""
    lines: list[str] = []
    for r in rows[:12]:
        primary, alias = aliases_for_row(r)
        if alias:
            styled = styled_title(r["title"], r["artist"], r["composer"])
            extra = ", ".join(a for a in alias[1:4])
            lines.append(
                f"- {styled}"
                + (f" (aka: {extra})" if extra else "")
            )
    if not lines:
        return ""
    return ("Notable works and their common names (search aliases):\n"
            + "\n".join(lines))
