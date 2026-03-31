# Day Phase Tracker (DPT)

Diese Home-Assistant-Custom-Integration erstellt konfigurierbare Tagesphasen auf Basis von:

- `sun.sun` Elevation (Primärsignal)
- `fallback_time` pro Phase (Sekundärsignal)

## Struktur

- Hauptsensor: `<name> Dayphase`
- Optionaler Sensor: `<name> Master Phase`

## Config Flow

1. **Name** eingeben (z. B. `Lights Dayphase`)
2. **Phasen als JSON** eingeben (mindestens 2 Einträge)
3. Optional **Masterphasen als JSON** zuordnen

## Beispiel: 8 Phasen

```json
[
  {"name":"early_morning","elevation_trigger":-5.4,"direction":"rising","fallback_time":"06:30"},
  {"name":"late_morning","elevation_trigger":2.2,"direction":"rising","fallback_time":"08:00"},
  {"name":"forenoon","elevation_trigger":14.4,"direction":"rising","fallback_time":"10:00"},
  {"name":"afternoon","elevation_trigger":14.4,"direction":"falling","fallback_time":"13:30"},
  {"name":"early_evening","elevation_trigger":7.8,"direction":"falling","fallback_time":"17:00"},
  {"name":"late_evening","elevation_trigger":-1.8,"direction":"falling","fallback_time":"21:00"},
  {"name":"early_night","elevation_trigger":-5.8,"direction":"falling","fallback_time":"22:30"},
  {"name":"late_night","elevation_trigger":-11.4,"direction":"falling","fallback_time":"00:00"}
]
```

## Masterphasen-Beispiel

```json
{
  "morning": ["early_morning", "late_morning"],
  "midday": ["forenoon", "afternoon"],
  "evening": ["early_evening", "late_evening"],
  "night": ["early_night", "late_night"]
}
```

## Update-Mechanik

- Trigger bei Änderungen von `sun.sun`
- Zusätzlich alle 60 Sekunden als Sicherheitsnetz
