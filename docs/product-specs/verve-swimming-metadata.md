# Verve Swimming Metadata Contract

## Status

Final contract for sharing swimming workout metadata between Verve-compatible exporters, importers, and backend services.

## Purpose

Swimming metadata extends a Verve activity file with source-neutral pool, lap, set, stroke, and SWOLF data. The contract describes swimming concepts, not a source API such as Apple HealthKit.

## Placement

Swimming metadata is stored in the root Verve GeoJSON properties object under the canonical metadata envelope:

```json
{
  "type": "FeatureCollection",
  "properties": {
    "verveVersion": "1.0",
    "activityType": "Swimming",
    "activitySubType": "Outdoor Pool",
    "metadata": {
      "target": "SwimmingMetaData",
      "version": "1.0",
      "data": {
        "poolLengthMeters": 50,
        "totalStrokeCount": 337,
        "averageSwolf": 97.1,
        "lapCount": 10,
        "setCount": 8,
        "strokeStyles": ["breaststroke", "freestyle"],
        "laps": [],
        "sets": []
      }
    }
  },
  "features": []
}
```

This envelope is the Verve file transfer representation. Backend activity APIs expose the imported metadata in the backend core representation described in [Backend/API Representation](#backendapi-representation).

## Envelope

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `target` | string | yes | Metadata target. Swimming metadata uses `"SwimmingMetaData"`. |
| `version` | string | yes | Metadata contract version. Current value is `"1.0"`. |
| `data` | object | yes | Source-neutral swimming metadata payload. |

Importers must use `target` and `version` to decide how to parse `data`.

## Backend/API Representation

When a Verve file is imported, the backend unwraps the file metadata envelope and stores the validated core metadata object in `Activity.meta_data`. Activity API responses that include `meta_data` return this backend representation, not the Verve file envelope.

The backend representation uses Python/backend field names and is shaped like `SwimmingMetaData`:

```json
{
  "target": "SwimmingMetaData",
  "pool_length_meters": 50,
  "total_stroke_count": 337,
  "avg_swofl": 97.1,
  "lap_count": 10,
  "set_count": 8,
  "styles": ["breaststroke", "freestyle"],
  "laps": [],
  "sets": []
}
```

The backend representation is intended for Verve API consumers and internal persistence. The Verve file representation is intended for portable import/export between Verve-compatible systems.

### Backend Data Object

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `target` | string | yes | Metadata target. Swimming metadata uses `"SwimmingMetaData"`. |
| `pool_length_meters` | integer | no | Pool length in meters. |
| `total_stroke_count` | integer | no | Total counted swim strokes for the whole workout. |
| `avg_swofl` | number | no | Average swim efficiency score across the workout or imported laps. This is the current backend field name. |
| `lap_count` | integer | no | Number of lap objects stored or reported by the source. |
| `set_count` | integer | no | Number of set objects stored or reported by the source. |
| `styles` | array of strings | no | Distinct stroke styles present in laps or sets. |
| `laps` | array of backend lap objects | no | Atomic lap records. |
| `sets` | array of backend set objects | no | Higher-level groupings of one or more laps. |

### Backend Lap Object

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `index` | integer | yes | Lap index. |
| `start_time` | string | no | ISO-8601 lap start time. |
| `end_time` | string | no | ISO-8601 lap end time. |
| `durations` | string | no | Lap duration encoded as an ISO-8601 duration string. |
| `distance_meters` | integer | no | Lap distance in meters. |
| `style` | string | no | Stroke style enum value. |
| `stroke_count` | integer | no | Stroke count for this lap. |
| `swolf` | number | no | SWOLF score for this lap. |
| `rest_after` | string | no | Rest after the lap encoded as an ISO-8601 duration string. |

Example:

```json
{
  "index": 0,
  "start_time": "2026-05-27T14:58:06Z",
  "end_time": "2026-05-27T14:59:01Z",
  "durations": "PT54.34S",
  "distance_meters": 50,
  "style": "breaststroke",
  "stroke_count": 26,
  "swolf": 80.34,
  "rest_after": "PT6S"
}
```

### Backend Set Object

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `index` | integer | yes | Set index. |
| `start_time` | string | no | ISO-8601 set start time. |
| `end_time` | string | no | ISO-8601 set end time. |
| `durations` | string | no | Set duration encoded as an ISO-8601 duration string. |
| `lap_start_index` | integer | no | Index of the first included lap. |
| `lap_end_index` | integer | no | Index of the last included lap. |
| `lap_count` | integer | no | Number of laps in the set. |
| `distance_meters` | integer | no | Set distance in meters. |
| `style` | string | no | Single style if all included laps agree; `mixed` if styles differ. |
| `stroke_count` | integer | no | Total stroke count for the set. |
| `avg_swofl` | number | no | Average SWOLF for the set. This is the current backend field name. |
| `rest_after` | string | no | Rest after the set encoded as an ISO-8601 duration string. |

Example:

```json
{
  "index": 0,
  "start_time": "2026-05-27T14:57:39Z",
  "end_time": "2026-05-27T15:00:02Z",
  "durations": "PT143S",
  "lap_start_index": 0,
  "lap_end_index": 1,
  "lap_count": 2,
  "distance_meters": 100,
  "style": "breaststroke",
  "stroke_count": 56,
  "avg_swofl": 82.69,
  "rest_after": "PT62S"
}
```

### Import/Export Mapping

| Verve file field | Backend/API field |
| --- | --- |
| `metadata.target` | `meta_data.target` |
| `metadata.version` | Not stored in core `meta_data` |
| `metadata.data.poolLengthMeters` | `meta_data.pool_length_meters` |
| `metadata.data.totalStrokeCount` | `meta_data.total_stroke_count` |
| `metadata.data.averageSwolf` | `meta_data.avg_swofl` |
| `metadata.data.lapCount` | `meta_data.lap_count` |
| `metadata.data.setCount` | `meta_data.set_count` |
| `metadata.data.strokeStyles` | `meta_data.styles` |
| `lap.durationSeconds` / `set.durationSeconds` | `durations` |
| `lap.strokeStyle` / `set.strokeStyle` | `style` |
| `lap.restAfterSeconds` / `set.restAfterSeconds` | `rest_after` |
| `set.averageSwolf` | `avg_swofl` |

On import, the backend validates the Verve file envelope and converts it into the core `meta_data` shape before storing the activity. On export, the backend converts core `meta_data` back into the Verve file envelope.

## Data Object

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `poolLengthMeters` | number | no | Pool length in meters. Omit for open-water swims or when unknown. |
| `totalStrokeCount` | integer | no | Total counted swim strokes for the whole workout. |
| `averageSwolf` | number | no | Average swim efficiency score across the workout or exported laps. |
| `lapCount` | integer | no | Number of lap objects exported or reported by the source. |
| `setCount` | integer | no | Number of set objects exported or reported by the source. |
| `strokeStyles` | array of strings | no | Distinct stroke styles present in laps or sets. |
| `laps` | array of lap objects | no | Atomic lap records, usually one pool length each. |
| `sets` | array of set objects | no | Higher-level groupings of one or more laps. |

## Validity Rule

The whole `metadata` envelope is optional. If a swimming metadata envelope is present, it must contain:

- `target: "SwimmingMetaData"`
- `version: "1.0"`
- `data` with at least one meaningful swim field

Meaningful swim fields are:

- `poolLengthMeters`
- `totalStrokeCount`
- `averageSwolf`
- `lapCount`
- `setCount`
- non-empty `strokeStyles`
- non-empty `laps`
- non-empty `sets`

Exporters must omit swimming metadata when `data` would be empty. Importers may accept and ignore an empty `data` object for tolerance, but empty swim metadata is not meaningful Verve swimming metadata.

## Stroke Styles

Use lowercase strings:

- `freestyle`
- `backstroke`
- `breaststroke`
- `butterfly`
- `kickboard`
- `mixed`
- `unknown`

`mixed` means a set contains more than one known style, or the source classified the interval as mixed. `unknown` means the style is unavailable or not confidently classified.

## Lap Object

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `index` | integer | yes | Zero-based lap array index within the workout. |
| `startTime` | string | no | ISO-8601 lap start time. |
| `endTime` | string | no | ISO-8601 lap end time. |
| `durationSeconds` | number | no | Lap duration in seconds. |
| `distanceMeters` | number | no | Lap distance in meters. For pool swims this is normally `poolLengthMeters`. |
| `strokeStyle` | string | no | Stroke style enum value. |
| `strokeCount` | integer | no | Stroke count for this lap. |
| `swolf` | number | no | SWOLF score for this lap. |
| `restAfterSeconds` | number | no | Time from this lap end to the next lap start. Omit for the final lap or when unknown. |

Example:

```json
{
  "index": 0,
  "startTime": "2026-05-27T14:58:06Z",
  "endTime": "2026-05-27T14:59:01Z",
  "durationSeconds": 54.34,
  "distanceMeters": 50,
  "strokeStyle": "breaststroke",
  "strokeCount": 26,
  "swolf": 80.34,
  "restAfterSeconds": 6.0
}
```

## Set Object

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `index` | integer | yes | Zero-based set array index within the workout. |
| `startTime` | string | no | ISO-8601 set start time. |
| `endTime` | string | no | ISO-8601 set end time. |
| `durationSeconds` | number | no | Set duration in seconds. |
| `lapStartIndex` | integer | no | Zero-based index of the first included lap. |
| `lapEndIndex` | integer | no | Zero-based index of the last included lap. |
| `lapCount` | integer | no | Number of laps in the set. |
| `distanceMeters` | number | no | Set distance in meters. |
| `strokeStyle` | string | no | Single style if all included laps agree; `mixed` if styles differ. |
| `strokeCount` | integer | no | Total stroke count for the set. |
| `averageSwolf` | number | no | Average SWOLF for the set. |
| `restAfterSeconds` | number | no | Time from this set end to the next set start. Omit for the final set or when unknown. |

Example:

```json
{
  "index": 0,
  "startTime": "2026-05-27T14:57:39Z",
  "endTime": "2026-05-27T15:00:02Z",
  "durationSeconds": 143.0,
  "lapStartIndex": 0,
  "lapEndIndex": 1,
  "lapCount": 2,
  "distanceMeters": 100,
  "strokeStyle": "breaststroke",
  "strokeCount": 56,
  "averageSwolf": 82.69,
  "restAfterSeconds": 62.0
}
```

## SWOLF

SWOLF means swim golf:

```text
SWOLF = length duration in seconds + stroke count for that length
```

Lower values are better for a fixed pool length because the swimmer covered the same distance with less time, fewer strokes, or both. Example: a 50 m length completed in `54` seconds with `26` strokes has a SWOLF score of `80`.

For sets, `averageSwolf` should represent the average of the included lap SWOLF values when available. If a source provides set-level SWOLF directly, the exporter may use it when it is semantically an average over the set.

## Derivation Rules

- `lapCount` should equal `laps.length` when laps are exported.
- `setCount` should equal `sets.length` when sets are exported.
- `strokeStyles` should be derived from available lap and set styles, excluding `unknown` unless all available styles are unknown.
- `strokeCount` for a lap may be inferred from `swolf - durationSeconds` only when the source definition is known to use standard SWOLF for that pool length.
- `strokeCount` for a set may be summed from included laps when direct set stroke count is unavailable.
- `distanceMeters` for a pool lap may be set from `poolLengthMeters`.
- `distanceMeters` for a set may be computed as the sum of included lap distances.
- `restAfterSeconds` should be computed from adjacent interval boundaries, not inferred from pauses unless interval boundaries are unavailable.
- If a source provides only set-level data, omit `lapStartIndex` and `lapEndIndex`.

## Non-Goals

- Do not store swimming location type inside `metadata.data`. Use root `activityType` and `activitySubType` for classification such as `Swimming` + `Indoor`, `Outdoor Pool`, or `Open Water`.
- Do not store source-specific field names such as Apple HealthKit metadata keys.
- Do not require every exporter to provide laps and sets. Partial swim metadata is valid when it contains at least one meaningful field.
- Do not duplicate root activity fields such as total workout duration or root total distance unless a future version defines a swim-specific distinction.
