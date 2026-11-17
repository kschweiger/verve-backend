# Starter exercise catalog

[`exercise_catalog.json`](exercise_catalog.json) is the first bundled Verve
catalog: the 50 selected exercise variants plus lateral band walks, monster walks,
terminal knee extensions, machine lateral raises, and kneeling counterweight-assisted
triceps dips and pull-ups. It contains 56 exercises, 34 muscle codes, and 22 default
display groups. These counts describe this revision, not format limits.

Names are stored in the `exercises`, `muscles`, and `muscle_groups` sections of
[`en.json`](../locales/en.json) and [`de.json`](../locales/de.json). The
[format documentation](../../docs/exercise-catalog-format.md) describes the
contract and its JSON Schema. The existing RepDB CLI does not consume this new
format; the separate catalog sync is a later change.

## Origin

The starting source is
[free-exercise-db at `f00c92c`](https://github.com/yuhonas/free-exercise-db/tree/f00c92c7dcf1216a928a52c3706c7ce8e2f71ed5),
released under the [Unlicense](LICENSE-free-exercise-db.txt). Its upstream IDs
identify starting entries for 43 variants. Thirteen entries have no upstream ID
because they are independently specified variants or lack a sufficiently clear
match. Labels and detailed muscle roles were curated for Verve. Images and
exercise instructions are not copied into the catalog.

The upstream commit records provenance. Our exercise codes are permanent Verve
identities and do not change when a label or upstream reference changes.

## Muscle-role convention

- Primary muscles have a substantial role in the exercise's intended movement or
  holding task. More than one primary muscle is allowed.
- Secondary muscles have a relevant assisting or supporting role.
- Omitted muscles are not declared inactive. The catalog deliberately avoids
  exhaustive lists of minor stabilizers.
- Roles are qualitative editorial classifications. They do not represent EMG
  percentages, equivalent sets, or measured training dose.

This vocabulary combines individual muscles, deltoid/trapezius portions, and
useful anatomical families such as quadriceps, hamstrings, hip flexors, and
adductors. Adductor involvement in hip extension mainly refers to adductor
magnus. Grouped codes do not assert equal involvement of every family member.
The anatomy basis is described in the official OpenStax chapters on
[upper-limb muscles](https://openstax.org/books/anatomy-and-physiology-2e/pages/11-5-muscles-of-the-pectoral-girdle-and-upper-limbs)
and [lower-limb muscles](https://openstax.org/books/anatomy-and-physiology-2e/pages/11-6-appendicular-muscles-of-the-pelvic-girdle-and-lower-limbs).

## Variant assumptions

- **Dead hang:** passive straight-arm hanging. Forearm flexors are primary;
  active scapular depression and substantial lat training are not assumed.
- **Wide seated machine row:** a guided seated row with the elbows traveling
  outward. It is separate from the close neutral-grip cable row. Handle height
  and machine path can change the relative role of the shoulder and back muscles.
- **Seated back-extension machine:** resisted trunk/lumbar extension with a back
  pad. It is separate from a hip-hinge hyperextension bench. Erector spinae is
  primary; no generic hamstring/glute assignment is inferred from the name.
- **Face pull:** a rope pull toward the face with hand separation and an
  outward-rotation finish. The external-rotator assignments refer to that finish.
- **Dips:** parallel bars with an upright torso and a triceps emphasis. A
  forward-leaning chest-dip variant is not a second entry in this first catalog.
- **Assisted triceps dips:** the same upright dip movement with knees on the
  moving support pad of a counterweight-assisted dip/chin-up machine. This is a
  separate entry from unassisted dips and from a seated dip/push-down machine.
  The stack specifies assistance, not added resistance; future weight logging
  must retain that distinction. The knee-supported device type is illustrated by
  the manufacturer's [Kneeling Easy Chin Dip](https://www.technogym.com/en-US/product/kneeling-easy-chin-dip_MB91.html).
- **Assisted pull-ups:** overhand grip with knees on the moving support pad of
  the same counterweight-assisted dip/chin-up machine. The entry has its own code
  and retains the qualitative muscle roles of the free overhand pull-up. Its
  selected stack likewise records assistance, not additional resistance. There is
  no matching assisted upstream entry, so `upstream_id` is omitted.
- **Machine lateral raise:** seated, guided shoulder abduction against the
  machine pads. It has its own code alongside the dumbbell lateral raise. The
  qualitative role set includes the lateral deltoid as primary and the
  supraspinatus/scapular upward rotators as secondary. These added machine variants
  have no matching upstream entry and therefore omit `upstream_id`.
- **Squat and leg press:** ordinary stance; quadriceps and gluteus maximus are
  primary. Hamstrings are not listed as main targets of these two-joint movements.
- **Calf raises:** both gastrocnemius and soleus are primary with the knee
  extended. The seated variant puts soleus primary and gastrocnemius secondary.
- **Machine crunch:** resisted trunk flexion. A linked hip-flexion/leg-lift
  mechanism is not assumed.
- **Planks:** forearm-supported holds. Holding muscles can be primary despite
  the absence of visible joint movement.
- **Hanging knee raise:** bent-knee hip flexion without an assumed deliberate
  pelvic curl. Hip flexors are primary and the abdominal muscles assist. A
  pelvic-curl emphasis would require revisiting that assignment.

## Added band exercises

| Code | Defined variant | Primary | Secondary |
| --- | --- | --- | --- |
| `lateral_band_walk_loop_band` | Sideways steps with one closed loop band. | Gluteus medius and minimus | Gluteus maximus and tensor fasciae latae |
| `monster_walk_loop_band` | Forward/backward monster-walk steps with one closed loop band, maintaining stance width. | Gluteus medius and minimus | Gluteus maximus and tensor fasciae latae |
| `terminal_knee_extension_band` | Standing terminal knee extension against an anchored band behind the knee. | Quadriceps | None recorded |

The walking variants assume a shallow squat and a loop around the ankles for the
initial curation. Band position and posture can change relative involvement; the
roles are broad qualitative assignments, not position-specific measurements.
The first catalog keeps each walk as one entry rather than creating separate
knee-, ankle-, and foot-band variants.

The original studies by
[Cambridge et al.](https://www.sciencedirect.com/science/article/abs/pii/S0268003312000460),
[Lewis et al. on band position](https://pubmed.ncbi.nlm.nih.gov/30615490/), and
[Lewis et al. on posture](https://pubmed.ncbi.nlm.nih.gov/26161629/)
support involvement of gluteus medius/maximus and TFL and show effects of band
placement and posture. Gluteus minimus is included from its anatomical hip
abduction role; it was not measured in those surface-EMG comparisons. The
primary/secondary boundary remains our curation.

Band terminal knee extension appears in the knee protocol of
[Ferber et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC4560005/).
The entry represents quadriceps involvement and makes no selective vastus
medialis/VMO claim.

## Display groups

The 22 groups are a proposed default mapping for the future body map, including
separate front, side, and rear shoulders. Every current muscle has one default
group. The format also permits overlapping groups and unmapped muscles.

Groups describe presentation regions. Deep muscles are associated with a useful
region rather than claiming that every muscle has a visible surface shape. The
frontend still needs its own mapping from these codes to SVG shapes. The sync
policy for existing/admin-edited group memberships remains a separate decision.

## Checks for this revision

The data is checked against the agreed JSON Schema, with additional checks for
unique codes, known muscle references, disjoint roles, upstream-ID existence,
coverage of the 56 selected variants, and English/German label coverage.
Existing activity and tag translations are preserved.
