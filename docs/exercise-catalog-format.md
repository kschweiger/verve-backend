# Bundled exercise catalog format

Status: accepted format, version 1. This describes our own curated catalog, with
free-exercise-db as a starting point. The offline importer consumes this format.

The [first catalog](../verve_backend/data/exercise_catalog.json) contains the 50
agreed exercise variants plus lateral band walks, monster walks, terminal knee
extensions, machine lateral raises, and assisted kneeling triceps dips and pull-ups.
Its [curation notes](../verve_backend/data/README.md) document variant
assumptions, provenance, and default groups. The examples below demonstrate the
format with two entries; they are not the complete catalog.

## Files

- [JSON Schema](../verve_backend/data/exercise_catalog.schema.json)
- [Example catalog](examples/exercise-catalog/catalog.json)
- [Example English labels](examples/exercise-catalog/en.json)
- [Example German labels](examples/exercise-catalog/de.json)

Use one catalog JSON document for exercises, detailed muscles, and default display
groups. Keep translated labels in separate locale JSON documents. The three
namespaces in the language examples can become sections in the application's
existing `verve_backend/locales/en.json` and `de.json`.

## Catalog fields

| Field | Meaning |
| --- | --- |
| `$schema` | Optional relative path or URI for editor schema support. |
| `schema_version` | Raw-data format version. Initially `1`; not a catalog content revision. |
| `source` | Stable identity of our catalog, initially `verve`. Keep this unchanged across releases. |
| `upstream` | Optional provenance for the source snapshot used to create entries. |
| `muscles` | List of all detailed muscle codes used by the catalog. |
| `muscle_groups` | Default display groups and their muscle members. |
| `exercises` | Concrete exercise variants and their muscle assignments. |

Codes use lower-case ASCII letters, digits, and underscores. They start with a
letter. Examples: `chest_press_machine`, `pectoralis_major`, `front_shoulders`.
Codes are permanent identities. Display-name changes do not change codes.

### Exercises

```json
{
  "code": "chest_press_machine",
  "is_active": true,
  "primary_muscles": ["pectoralis_major"],
  "secondary_muscles": ["anterior_deltoid", "triceps_brachii"],
  "upstream_id": "Leverage_Chest_Press"
}
```

`code`, `primary_muscles`, and `secondary_muscles` are required. The arrays describe
complete assignment sets, not additive patches. Several primary and secondary
muscles are allowed. Both arrays may be empty. A muscle cannot occur twice or in
both roles for the same exercise.

`is_active` is optional and defaults to `true`. The loader must apply that default;
the JSON Schema annotation does not insert the value. Retain retired exercises
explicitly with `is_active: false`, including their labels. Omitting an entry does
not request a database deletion. Never reuse a retired code for a new exercise.

Each agreed equipment/execution variant gets a separate exercise code. There is
no equipment field or exercise-family model in this format; the localized name
identifies the variant.

The primary/secondary roles are qualitative catalog classifications. They do not
encode activation percentages, set-count multipliers, or measured training load.

### Muscles and default display groups

```json
{
  "muscles": ["gastrocnemius", "soleus"],
  "muscle_groups": [
    {
      "code": "calves",
      "muscles": ["gastrocnemius", "soleus"]
    }
  ]
}
```

Exercise muscle codes and group member codes must refer to the root `muscles`
list. Group member arrays are complete default member sets. Empty groups, muscles
without a group, and membership in several groups are allowed.

The frontend maps group codes to its body-map shapes. Group labels use the
`muscle_groups` locale namespace. SVG paths, colors, and weights are outside this
format.

The bundled group definitions are authoritative. Synchronization creates missing
groups and replaces memberships with the declared sets, preserving IDs for
retained codes. An empty member array clears a group. Groups absent from the
input are deleted with their memberships. Exercises and muscles are retained.
Do not maintain a second group-definition document in the locale files.

A matching completed checkpoint may skip synchronization. Use `--force` to
reapply the bundle after direct database edits. See the
[importer documentation](exercise-import.md).

### Upstream provenance

```json
{
  "upstream": {
    "source": "free-exercise-db",
    "repository": "https://github.com/yuhonas/free-exercise-db",
    "revision": "f00c92c7dcf1216a928a52c3706c7ce8e2f71ed5",
    "license": "Unlicense"
  }
}
```

`upstream_id` is optional per exercise. If present, the root `upstream` object is
required. The ID identifies the starting entry at that immutable upstream commit;
our names and muscle assignments may differ. Omit `upstream_id` for independently
added entries. Version 1 records one shared upstream snapshot; selecting rows from
several source revisions would require an explicit extension of this format.

This provenance stays in the raw data. It is not the database identity and is not
an instruction to download or automatically merge upstream changes. Keep the
source license and attribution information with the actual catalog distribution.

## Translated labels

For example, the German locale contains:

```json
{
  "exercises": {
    "chest_press_machine": "Brustpresse (Maschine)"
  },
  "muscles": {
    "pectoralis_major": "Großer Brustmuskel"
  },
  "muscle_groups": {
    "chest": "Brust"
  }
}
```

Every key refers to a stable catalog code. Values are nonempty strings. The
English and German examples cover all of their catalog codes. Preserve labels for
retired exercises. Translations remain application resources and are never synced
into database name columns.

## Database mapping

| Raw data | Database value |
| --- | --- |
| Root `source` | `ExerciseCatalogSyncState.catalog_code`, the catalog checkpoint key. |
| Exercise `code` | Unique `Exercise.code`, used to find and retain its UUID. |
| Content checksum | `ExerciseCatalogSyncState.content_hash`. |
| Sync behavior version | `ExerciseCatalogSyncState.sync_version`, maintained by the importer. |
| Exercise `is_active` | `Exercise.is_active`, defaulting to `true`. |
| Detailed muscle code | Unique `Muscle.code`. |
| Exercise muscle arrays | `ExerciseMuscle` rows and their roles. |
| Group code and member codes | `MuscleGroup.code` and `MuscleGroupMember` links. |
| `upstream` and `upstream_id` | Raw-data provenance only. |

UUIDs are generated once and retained when codes match. Codes must not change
when labels change. The upstream Git SHA describes the original starting data;
the catalog checksum describes our current bundled data.

The checksum is SHA-256 of the parsed document without the root `$schema` hint.
Canonical JSON uses sorted object keys, UTF-8, compact separators, and no trailing
newline. Array order is significant. Defaults are not inserted before hashing.
Locale files are excluded. A matching checksum and sync version skip a normal
run; `--force` applies the catalog again.

## Validation boundaries

The JSON Schema checks field names, required fields, types, code syntax, list
duplicates, and the requirement for upstream metadata when an ID is used. Unknown
fields are rejected so spelling errors do not silently disappear.

The Pydantic runtime loader also checks the structure and, before database access:

- Unique exercise codes and unique group codes. Object-level `uniqueItems` alone
  does not reject two objects with the same code and different content.
- All exercise and group muscle references exist.
- No muscle appears in both roles for one exercise.
- Duplicate JSON object keys are rejected when parsing instead of silently taking
  the last value.
- Referenced upstream IDs exist at the recorded revision when preparing imported
  entries. Runtime sync reads bundled files and does not contact upstream.

Tests validate the bundled document against the maintained JSON Schema and check
English/German locale coverage. `jsonschema` is a test dependency. Runtime
validation uses the existing Pydantic dependency and does not fetch schema URLs.
