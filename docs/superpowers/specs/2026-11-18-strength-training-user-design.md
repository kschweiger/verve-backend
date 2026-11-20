# Trainingsvorlagen und Trainingsdetails aus Nutzersicht

Datum: 18. November 2026

Status: Entwurf auf Basis der bisherigen Produktentscheidungen.

## Ziel

Ich möchte bei einer Krafttraining-Aktivität sehen, welche Übungen zu meinem
Training gehören und welche Muskelgruppen diese Übungen ansprechen. Meinen
wiederkehrenden Trainingsplan möchte ich einmal zusammenstellen und bei späteren
Aktivitäten wiederverwenden.

Die erste Version hilft mir, mein Training zuzuordnen und anzusehen. Ich muss
während des Trainings keine einzelnen Sätze protokollieren. Angaben zu Gewicht,
Sätzen und Wiederholungen sind freiwillig.

Dieses Dokument beschreibt das gewünschte Verhalten. Datenbanktabellen,
API-Endpunkte und die genaue Gestaltung der Oberfläche werden separat geplant.

## Begriffe

| Begriff | Bedeutung für den Nutzer |
| --- | --- |
| Übung | Eine auswählbare Übung aus dem vorhandenen Katalog. Geräte- und Ausführungsvarianten sind eigene Übungen. |
| Trainingsvorlage | Mein gespeicherter, wiederverwendbarer Trainingsplan. Sie gehört mir und kann bearbeitet oder kopiert werden. |
| Trainingsdetails | Die Übungen und freiwilligen Angaben einer bestimmten Aktivität. Der Begriff ist ein vorläufiger Vorschlag für die Oberfläche. |
| Verknüpfte Vorlage | Die Vorlage, die ich für diese Aktivität ausgewählt habe. Die Verbindung bleibt auch bei Abweichungen erhalten. |
| Übereinstimmung | Die Übungen der Aktivität und der verknüpften Vorlage sind dieselben. Gewicht, Sätze und Wiederholungen zählen für diesen Vergleich nicht. |

## Gewählter Ansatz

Eine Vorlage liefert die Ausgangswerte für eine Aktivität. Die Aktivität erhält
eigene Trainingsdetails, die ich unabhängig bearbeiten kann. Die Verbindung zur
Vorlage bleibt als Zuordnung erhalten.

Eine direkte Übernahme aller späteren Änderungen aus der Vorlage würde frühere
Aktivitäten nachträglich verändern. Deshalb bleiben deren gespeicherte Übungen
und Angaben erhalten. Eine vollständig unabhängige Kopie ohne Verknüpfung würde
dagegen die gewünschte Übersicht über Aktivitäten zu einer Vorlage erschweren.
Die Kombination aus eigenen Trainingsdetails und einer ausdrücklichen
Vorlagenverknüpfung erfüllt beide Ziele.

## Meine Trainingsvorlagen

### Eine Vorlage erstellen

Ich erstelle eine Vorlage mit einem eigenen Namen und wähle Übungen aus dem
Katalog aus. Für jede Übung kann ich Gewicht, Satzanzahl und Wiederholungen
eintragen. Jede dieser Angaben kann auch einzeln fehlen.

Eine Vorlage mit Brustpresse, Latzug und Monster Walks ist auch dann nutzbar, wenn
nur für die Brustpresse ein Gewicht eingetragen ist. Fehlende Angaben verhindern
weder die Verwendung noch die Muskelvisualisierung.

Die Übungen haben keine festgelegte Trainingsreihenfolge. Ich muss sie nicht
sortieren und kann keine Reihenfolge für die Ausführung festlegen. Eine einfache
Sortierung zur Anzeige ist davon unabhängig.

### Eine Vorlage bearbeiten oder kopieren

Ich kann die Übungen und die freiwilligen Angaben einer bestehenden Vorlage
ändern. Diese Änderungen gelten beim nächsten Übernehmen der Vorlage. Bereits
gespeicherte Aktivitäten behalten ihre Trainingsdetails.

Für eine zusätzliche Variante kann ich eine Vorlage kopieren und die Kopie
bearbeiten. Die ursprüngliche Vorlage bleibt dabei erhalten. Auch Vorlagen mit
derselben Übungsauswahl können getrennte Vorlagen bleiben, etwa mit verschiedenen
Namen oder Vorgaben.

Meine Vorlagen gehören zu meinem Nutzerkonto. Eine gemeinsame Vorlagenbibliothek
oder die Freigabe an andere Nutzer ist nicht Teil dieses ersten Schritts.

## Trainingsdetails einer Aktivität

### Eine Vorlage übernehmen

Ich öffne eine Aktivität und wähle eine meiner Trainingsvorlagen aus. Die Übungen
und vorhandenen Angaben werden in die Trainingsdetails dieser Aktivität
übernommen. Ich kann erkennen, welche Vorlage verknüpft ist.

Anschließend kann ich für diese Aktivität:

- Übungen hinzufügen, entfernen oder durch andere Katalogübungen ersetzen;
- Gewicht, Satzanzahl und Wiederholungen ändern oder entfernen;
- alle übernommenen Angaben unverändert lassen.

Diese Änderungen werden zunächst nur bei der Aktivität gespeichert. Die Vorlage
wird dadurch nicht automatisch bearbeitet. Ich muss bei einer einmaligen
Abweichung auch keine neue Vorlage erstellen.

### Ohne Vorlage beginnen

Ich kann einer Aktivität direkt Übungen hinzufügen und die freiwilligen Angaben
eintragen. Dafür muss ich keine Vorlage anlegen. Die Aktivität besitzt dann
Trainingsdetails ohne Vorlagenverknüpfung. Auch dafür ist die Muskelvisualisierung
verfügbar.

Eine Aktivität kann weiterhin ohne Trainingsdetails bestehen.

Der Ablauf „erst Übungen einzeln hinzufügen, danach eine Vorlage laden“ ist noch
kein festgelegter Ablauf für V1. Das Zusammenführen vorhandener Trainingsdetails
mit einer Vorlage wird separat betrachtet. Aus den bisherigen Überlegungen folgt
insbesondere keine automatische Zusammenführung und kein stilles Überschreiben.

## Änderungen als Vorlage weiterverwenden

Wenn ich die Trainingsdetails einer Aktivität angepasst habe, stehen mir drei
getrennte Möglichkeiten offen:

| Aktion | Gewünschtes Ergebnis |
| --- | --- |
| Nur bei der Aktivität speichern | Meine Änderung gilt für diese Aktivität. Die verknüpfte Vorlage bleibt erhalten und unverändert. |
| Verknüpfte Vorlage aktualisieren | Die aktuelle Übungsauswahl und ihre freiwilligen Angaben werden zu den neuen Vorgaben dieser Vorlage. Andere Aktivitäten behalten ihre eigenen Trainingsdetails. |
| Als neue Vorlage speichern | Aus den Trainingsdetails entsteht eine neue Vorlage in meinem Konto. Eine bisherige Vorlage wird nicht verändert. |

Die beiden Vorlagenaktionen sind auch bei reinen Gewichtsänderungen sinnvoll.
Eine unveränderte Übungsauswahl schließt das Aktualisieren der Vorgaben nicht aus.
Ohne verknüpfte Vorlage kann ich eine neue Vorlage speichern.

Vorschlag für V1: Nach „Als neue Vorlage speichern“ wird diese neue Vorlage mit
der Aktivität verknüpft. Damit ist direkt erkennbar, zu welchem wiederverwendbaren
Plan diese Zusammenstellung gehört. Diese Zuordnung ist noch als Produktdetail
zu bestätigen.

## Verknüpfung und Übereinstimmung

Die Verknüpfung beantwortet: „Welche Vorlage habe ich für diese Aktivität
ausgewählt?“ Sie bleibt bestehen, wenn ich Übungen oder Angaben ändere.

Die Übereinstimmung beantwortet: „Enthält diese Aktivität dieselben Übungen wie
die verknüpfte Vorlage?“ Verglichen werden die unterschiedlichen Übungs-IDs mit
der aktuellen Vorlage; mehrfache Einträge derselben Übung sind erlaubt und
beeinflussen den Vergleich nicht. Dafür gilt:

- Es werden dieselben Katalogübungen verglichen. Zwei Gerätevarianten sind dabei
  verschiedene Übungen.
- Gewicht, Satzanzahl und Wiederholungen verändern das Ergebnis nicht.
- Die Reihenfolge verändert das Ergebnis nicht.
- Die Auswahl weicht ab, sobald eine andere Katalogübung hinzukommt, fehlt oder
  durch eine andere ersetzt wird. Ein weiterer Eintrag derselben Übung ändert
  die Auswahl nicht.
- Die Zuordnung einzelner Übungen zu Muskeln oder Darstellungsgruppen bestimmt
  nicht, ob die Übungsauswahl der Vorlage entspricht.

Eine passende Bezeichnung in der Oberfläche wäre „Übungsauswahl entspricht der
Vorlage“ oder „Übungsauswahl angepasst“. „Unverändert“ wäre zu weitgehend, weil
beispielsweise die Gewichte trotzdem abweichen können.

„Vorlage befolgt“ meint in diesem Umfang nur diese Übereinstimmung der Übungen.
Die Aussage ist kein Nachweis über absolvierte Sätze oder erreichte Leistungen.

### Beispiel: fortlaufend höhere Gewichte

Meine Vorlage enthält Brustpresse, Bizepscurls und Latzug. Bei einer Aktivität
erhöhe ich das Gewicht an der Brustpresse von 40 auf 45 kg. Die Übungsauswahl
entspricht weiterhin der Vorlage. Meine nächste Aktivität kann dieselbe Vorlage
verwenden. Die erste Aktivität behält ihren eigenen Gewichtswert.

Entferne ich dagegen den Latzug aus einer Aktivität, bleibt die Vorlage
verknüpft, aber die Übungsauswahl weicht ab.

### Spätere Änderungen an der Vorlage

Für V1 bezieht sich der Vergleich auf die aktuelle Übungsauswahl der Vorlage.

Füge ich der Vorlage später eine weitere Übung hinzu, behalten ältere Aktivitäten
ihre bisherigen Übungen. Ihr Vergleich mit der aktuellen Vorlage kann danach
eine Abweichung anzeigen. Eine Änderung nur am Vorlagennamen oder an ihren
Gewichts-, Satz- oder Wiederholungsvorgaben verändert die Übereinstimmung nicht.

## Von einer Vorlage zu meinen Aktivitäten

Bei einer Vorlage möchte ich zwei Fragen beantworten können:

1. Welche Aktivitäten sind mit dieser Vorlage verknüpft?
2. Welche dieser Aktivitäten haben eine übereinstimmende Übungsauswahl?

Die erste Ansicht umfasst auch Aktivitäten mit angepassten Übungen. Die zweite
ist eine Teilmenge davon. Beide Übersichten sollen auch mit wachsender
Aktivitätszahl gezielt und zügig nutzbar bleiben.

Aktivitäten ohne diese ausdrückliche Verknüpfung werden nicht nach passenden
Vorlagen durchsucht. Eine zufällig identische Übungsauswahl erzeugt daher keine
Zuordnung. Dasselbe gilt für Aktivitäten, die mit einer anderen Vorlage mit
identischer Übungsauswahl verknüpft sind.

## Muskelvisualisierung bei einer Aktivität

Die Aktivität zeigt eine Körperdarstellung mit den Muskelgruppen, die ihren
hinterlegten Übungen zugeordnet sind. Grundlage sind die Trainingsdetails der
Aktivität und die Muskelzuordnungen aus dem Katalog.

Entferne oder ergänze ich dort eine Übung, wird die Darstellung entsprechend
angepasst. Eine Änderung nur an der Vorlage schreibt die Übungen der Aktivität
nicht um. Die Darstellung ist auch ohne Vorlagenverknüpfung und ohne Gewicht,
Satzanzahl oder Wiederholungen verfügbar.

Die Darstellung beschreibt die Muskelzuordnung der Übungsauswahl. Für V1 werden
daraus keine gemessene Belastung, Aktivierungsprozente oder tatsächlich
absolvierte Satzmengen abgeleitet. Die genaue grafische Gestaltung wird separat
festgelegt.

## Grenzen der ersten Version

Die erste Version umfasst wiederverwendbare Vorlagen, eigene Trainingsdetails
pro Aktivität, die ausdrückliche Verknüpfung, den Vergleich der Übungsauswahl und
die Muskelvisualisierung.

Folgende Erweiterungen gehören zu späteren Schritten:

- Begleitung während des Trainings, Satzbestätigung, Timer oder Pausensteuerung;
- ein Protokoll mit einzelnen Sätzen, wechselnden Satzgewichten und tatsächlich
  erreichten Wiederholungen;
- eine festgelegte Reihenfolge, Supersätze oder andere Trainingsblöcke;
- automatische Zuordnung anhand passender Übungen;
- Zusammenführen bereits vorhandener Trainingsdetails mit einer später geladenen
  Vorlage;
- Vorlagenhistorie mit wiederherstellbaren früheren Ständen;
- Belastungsberechnung oder automatische Gewichtssteigerung.

Ein späteres Satzprotokoll soll neben den bisherigen freiwilligen Angaben
ergänzbar bleiben. Die erste Version verpflichtet den Nutzer deshalb nicht zur
Erfassung solcher Daten.

Beim Löschen einer Vorlage bleiben die Trainingsdetails bisheriger Aktivitäten
erhalten; ihre Vorlagenverknüpfung wird entfernt.

## Noch festzulegende Produktdetails

Die folgenden Punkte sind Vorschläge oder offene Entscheidungen, keine bereits
bestätigten Anforderungen:

- Verknüpfung mit der neu erstellten Vorlage nach „Als neue Vorlage speichern“.
- Eindeutige Beschriftung freiwilliger Gewichtsangaben, insbesondere bei Geräten
  mit Gegengewicht. Eine fehlende Angabe wird nicht als Gewicht von null gewertet.

## Prüffälle aus Nutzersicht

| Situation | Erwartetes Verhalten |
| --- | --- |
| Ich erstelle eine Vorlage ohne Gewichts-, Satz- oder Wiederholungsangaben. | Die Vorlage kann verwendet und visualisiert werden. |
| Ich übernehme eine Vorlage in eine Aktivität. | Die Aktivität erhält eigene Trainingsdetails und bleibt mit der Vorlage verknüpft. |
| Ich ändere nur Gewicht, Sätze oder Wiederholungen in der Aktivität. | Die Übungsauswahl entspricht weiterhin der Vorlage; deren Vorgaben bleiben unverändert. |
| Ich entferne eine Übung aus der Aktivität. | Die Verknüpfung bleibt erhalten; die Übungsauswahl wird als angepasst erkennbar und die Darstellung folgt der geänderten Auswahl. |
| Ich bearbeite die Vorlage später. | Bereits gespeicherte Übungen und Angaben der Aktivitäten bleiben erhalten. |
| Ich aktualisiere die Vorlage aus einer Aktivität. | Andere Aktivitäten behalten ihre Trainingsdetails. |
| Ich kopiere eine Vorlage oder speichere eine Aktivität als neue Vorlage. | Die bisherige Vorlage bleibt erhalten. |
| Ich füge einer Aktivität direkt eine Übung hinzu. | Dafür entsteht keine Pflicht, eine Vorlage anzulegen; die Visualisierung ist verfügbar. |
| Eine Aktivität ohne Vorlagenverknüpfung enthält zufällig dieselben Übungen. | Sie erscheint nicht automatisch unter den Aktivitäten dieser Vorlage. |
| Eine Übungsauswahl weicht von der verknüpften Vorlage ab. | Die Aktivität bleibt in deren vollständiger Aktivitätsübersicht auffindbar. |

## Vorhandene Grundlage

Der gebündelte Übungskatalog liefert die Übungen, Muskelzuordnungen und
Darstellungsgruppen. Namen werden aus den vorhandenen Sprachdateien angezeigt.
Der Katalog und sein Import sind bereits umgesetzt; die hier beschriebenen
Nutzerfunktionen sind das darauf aufbauende Ziel.

- [Katalogformat](../../exercise-catalog-format.md)
- [Katalog und fachliche Annahmen](../../../verve_backend/data/README.md)
